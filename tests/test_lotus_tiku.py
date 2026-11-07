import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

import requests
from api.lotus_tiku import build_question, parse_answer, answer_from_lotus, LotusError, load_settings


def exam(mode=15, options=None, **extra):
    return {'topic_mode':mode, 'stem':{'content':'Choose the correct word', 'remark':'选择正确单词'},
            'options': options if options is not None else [{'content':'first','answer_tag':9},{'content':'second','answer_tag':3}], **extra}


class LotusTests(unittest.TestCase):
    def parsed(self, e, answers, **extra):
        request,meta=build_question(e,e['topic_mode'])
        return parse_answer({'code':1,'answers':answers,**extra},request,meta)

    def test_original_option_order_and_nonsequential_tags(self):
        for mode in [11,15,16,17,18,21,22,41,42,43,44]:
            with self.subTest(mode=mode):self.assertEqual(self.parsed(exam(mode,stem={'content':'Choose','ph_en_url':'/pack.mp3'}),['B']),3)

    def test_nested_and_string_tags(self):
        e=exam(42,[{'content':'walk','answer_tag':'1#','sub_options':[{'content':'walked','answer_tag':2},{'content':'walking','answer_tag':4}]},{'content':'run','answer_tag':'2#'}])
        self.assertEqual(self.parsed(e,['A']),'1#2')
        self.assertEqual(self.parsed(e,['C']),'2#0')

    def test_manual_invalid_and_wrong_type_never_submit(self):
        for answers,extra in [(['A'],{'manual':True}),(['Z'],{}),(['A','B'],{}),(['explanation'],{}),([],{ }),(['A'],{'type':'completion'})]:
            with self.subTest(answers=answers,extra=extra):self.assertIsNone(self.parsed(exam(),answers,**extra))

    def test_server_no_answer_and_error_are_distinct(self):
        request,meta=build_question(exam(),15)
        self.assertIsNone(parse_answer({'code':0,'error':'NO_ANSWER'},request,meta))
        with self.assertRaises(LotusError):parse_answer({'code':0,'error':'CODEX_NETWORK'},request,meta)

    def test_reversed_judgement_options(self):
        self.assertEqual(self.parsed(exam(15,[{'content':'错误','answer_tag':4},{'content':'正确','answer_tag':8}]),['正确'],type='judgement'),8)

    def test_phrase_blank_order_and_no_fixed_word_reinsertion(self):
        e=exam(32,[{'content':'waste','answer_tag':0},{'content':'free','answer_tag':1}]);e['stem']['content']='A _-_ world'
        self.assertEqual(self.parsed(e,['waste','free']),'waste,free')
        self.assertIsNone(self.parsed(e,['waste']))
        self.assertIsNone(self.parsed(e,['waste','invented']))

    def test_multiword_option_is_one_slot(self):
        e=exam(32,[{'content':'all our','answer_tag':0},{'content':'country','answer_tag':1}]);e['stem']['content']='_ country'
        self.assertEqual(self.parsed(e,['all our']),'all our')

    def test_spelling_length_count_and_json_submission(self):
        e=exam(73,w_lens=[3,4],w_tip='c');e['stem']['content']='{c} {w}'
        self.assertEqual(json.loads(self.parsed(e,['cat','walk'])),['cat','walk'])
        self.assertIsNone(self.parsed(e,['cats','walk']))
        self.assertIsNone(self.parsed(e,['cat']))
        self.assertEqual(self.parsed(exam(51,w_lens=[3],w_tip='c'),['cat']),'cat')

    def test_matching_uses_response_not_relation_text_as_answer(self):
        e=exam(31);e['stem']['remark']=[{'relation':'词一'},{'relation':'词二'}]
        self.assertEqual(self.parsed(e,['B','A']),{'词一':3,'词二':9})
        self.assertIsNone(self.parsed(e,['Z','A']))

    def test_unsupported_audio_and_ambiguous_structure_skip(self):
        for e in [exam(21),exam(999),exam(32),exam(51),exam(15,[{'content':'same'},{'content':'same'}])]:
            with self.subTest(mode=e['topic_mode']),self.assertRaises(ValueError):build_question(e,e['topic_mode'])

    def settings(self,root):
        (Path(root)/'config').mkdir();(Path(root)/'config/lotus.json').write_text(json.dumps({'url':'http://127.0.0.1:1234','token':'test-token'}))

    def test_transport_auth_and_no_response_retries(self):
        with tempfile.TemporaryDirectory() as root:
            self.settings(root);public=SimpleNamespace(path=root,exam=exam())
            response=Mock(status_code=200);response.json.return_value={'code':1,'answers':['B']}
            with patch('api.lotus_tiku.requests.post',return_value=response) as post:
                self.assertEqual(answer_from_lotus(public,15),3)
                self.assertEqual(post.call_args.kwargs['headers']['Authorization'],'Bearer test-token')
                self.assertEqual(post.call_args.args[0],'http://127.0.0.1:1234/search')
                self.assertFalse(post.call_args.kwargs['allow_redirects'])
            for failure in [requests.Timeout,requests.ConnectionError,ValueError]:
                with patch('api.lotus_tiku.requests.post',side_effect=failure) as post,self.assertRaises(LotusError):answer_from_lotus(public,15)
                post.assert_called_once()
            with patch('api.lotus_tiku.requests.post',return_value=Mock(status_code=401)) as post,self.assertRaises(LotusError):answer_from_lotus(public,15)

    def test_missing_config_and_insecure_address_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(LotusError):load_settings(root)
            self.settings(root)
            with patch.dict('os.environ',{'EASY_CIDAREN_LOTUS_URL':'http://example.com/search'}),self.assertRaises(LotusError):load_settings(root)

    def test_lotus_first_then_legacy_fallback(self):
        from answer_questions.answer_questions import answer
        public=SimpleNamespace(exam=exam())
        with patch('api.lotus_tiku.answer_from_lotus',return_value=9),patch('answer_questions.answer_questions.legacy_answer') as legacy:
            self.assertEqual(answer(public,15),9);legacy.assert_not_called();self.assertEqual(public.last_answer_source,'lotus')
        for result in [None,LotusError('test')]:
            with patch('api.lotus_tiku.answer_from_lotus',**({'side_effect':result} if isinstance(result,Exception) else {'return_value':result})),patch('answer_questions.answer_questions.legacy_answer',return_value=3) as legacy:
                self.assertEqual(answer(public,15),3);legacy.assert_called_once();self.assertEqual(public.last_answer_source,'fallback')

    def test_headless_override_only_on_fallback(self):
        from api.runner import HeadlessTaskRunner
        from answer_questions.answer_questions import answer
        runner=object.__new__(HeadlessTaskRunner);runner.public=SimpleNamespace(exam=exam())
        callback=Mock(return_value=8);runner.set_answer_override(callback)
        with patch('api.lotus_tiku.answer_from_lotus',return_value=2):
            self.assertEqual(answer(runner.public,15),2);callback.assert_not_called()
        with patch('api.lotus_tiku.answer_from_lotus',return_value=None):self.assertEqual(answer(runner.public,15),8)

    def test_media_flags_context_and_variant_modes(self):
        import base64
        png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jT1cAAAAASUVORK5CYII='
        e=exam(151,[{'content':png,'answer_tag':7},{'content':png+'other','answer_tag':8}],enable_i_i=1,enable_i_o=1,context='辅助材料')
        e['stem']['content']=png
        req,meta=build_question(e,151)
        self.assertIn('data:image/png;base64,',req['title']);self.assertIn('data:image/png;base64,',req['options'][0]);self.assertEqual(req['context'],'辅助材料')
        self.assertEqual(meta['mode'],15)
        self.assertEqual(parse_answer({'code':1,'answers':['B']},req,meta),8)

    def test_actual_audio_fields_and_tts_path(self):
        e=exam(21,stem={'content':'','ph_en_url':'/Resource/pack.mp3'})
        req,_=build_question(e,21);self.assertEqual(req['audio'],[{'url':'https://resource.vocabgo.com/Resource/pack.mp3'}])
        e=exam(22,stem={'content':'Listen','ph_us_url':'abc.mp3','au_addr':'https://resource-cdn.vocabgo.com'},word_type=2)
        req,_=build_question(e,22);self.assertEqual(req['audio'][0]['url'],'https://resource-cdn.vocabgo.com/AudioTTS/SEN/US/Mabc.mp3')
        req,_=build_question(exam(13),13);self.assertNotIn('audio',req)

    def test_submitted_question_counts_once_after_success(self):
        from answer_questions.answer_questions import submit
        p=SimpleNamespace(exam={'topic_code':'topic-1'},task_id='task',last_answer_source='lotus')
        with patch('answer_questions.answer_questions.submit_result'),patch('answer_questions.answer_questions.next_exam'),patch('answer_questions.answer_questions.time.sleep'):
            submit(p,{'first':1,'second':2});submit(p,1)
        self.assertEqual(p.lotus_answer_count,1)
        p.exam={'topic_code':'topic-2'};p.last_answer_source='fallback'
        with patch('answer_questions.answer_questions.submit_result',side_effect=RuntimeError),self.assertRaises(RuntimeError):submit(p,2)
        self.assertEqual(getattr(p,'fallback_answer_count',0),0)
        with patch('answer_questions.answer_questions.submit_result'),patch('answer_questions.answer_questions.next_exam'),patch('answer_questions.answer_questions.time.sleep'):submit(p,2)
        self.assertEqual(p.fallback_answer_count,1)

    def test_native_images_and_multiple_audio_are_forwarded_without_ownership_guess(self):
        e=exam(15,images=['data:image/png;base64,test'],original_title='原题',suggestion_title='[图片1]',audio=[{'url':'https://example.org/a.mp3'},{'objectId':'a'*32}])
        request,_=build_question(e,15)
        self.assertEqual(request['images'],e['images']);self.assertEqual(request['original_title'],'原题')
        self.assertEqual(request['audio'],e['audio']);self.assertEqual(request['suggestion_title'],'[图片1]')
        e['audio']=['https://example.org/a.mp3']*5
        with self.assertRaises(ValueError):build_question(e,15)

    def test_unsupported_both_providers_skips_without_crashing_task(self):
        from answer_questions.answer_questions import answer
        with patch('api.lotus_tiku.answer_from_lotus',return_value=None):
            self.assertIsNone(answer(SimpleNamespace(exam=exam(999)),999))

    def test_source_switch_updates_final_source_without_double_count(self):
        from answer_questions.answer_questions import count_answer_source
        p=SimpleNamespace()
        count_answer_source(p,('task','topic'),'lotus')
        count_answer_source(p,('task','topic'),'fallback')
        count_answer_source(p,('task','topic'),'fallback')
        self.assertEqual(p.lotus_answer_count,0);self.assertEqual(p.fallback_answer_count,1)

    def test_sorting_word_pool_can_repeat_placeholders(self):
        e=exam(32,[{'content':'trade'},{'content':'sth.'},{'content':'for'},{'content':'sth.'}])
        e['stem']={'content':'_ _ _ _','remark':'用某物交换某物'}
        self.assertEqual(self.parsed(e,['trade','sth.','for','sth.']),'trade,sth.,for,sth.')
        ambiguous=exam(15,[{'content':'same'},{'content':'same'}])
        with self.assertRaises(ValueError):build_question(ambiguous,15)

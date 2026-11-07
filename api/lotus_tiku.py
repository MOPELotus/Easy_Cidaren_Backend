"""Cidaren protocol adapter for Lotus OCS /search, including images and ASR audio."""
import json
import html
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urljoin

import requests

from log.log import Log

DEFAULT_URL = 'https://tiku.lotusshared.cn/search'
logger = Log('lotus_tiku').logger


class LotusError(RuntimeError):
    pass


def load_settings(root):
    path = Path(root) / 'config/lotus.json'
    try:
        config = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        url = os.environ.get('EASY_CIDAREN_LOTUS_URL') or config.get('url') or DEFAULT_URL
        token = os.environ.get('EASY_CIDAREN_LOTUS_TOKEN') or config.get('token') or ''
        timeout = float(config.get('timeout', 240))
        parts = urlsplit(url)
        if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError()
        if parts.scheme == 'http' and parts.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError()
        if not isinstance(token, str) or not token.strip() or '\r' in token or '\n' in token or not 1 <= timeout <= 900:
            raise ValueError()
    except (OSError, ValueError, TypeError, AttributeError):
        raise LotusError('荷花题库配置无效：请设置题库地址和访问令牌。') from None
    return {'url': url.rstrip('/') if parts.path.rstrip('/').endswith('/search') else url.rstrip('/') + '/search',
            'token': token.strip(), 'timeout': timeout}


def _text(value):
    if not isinstance(value, str):
        raise ValueError('题干或选项缺少明确文字')
    return value.strip()


def normalized_mode(mode):
    text = str(mode)
    return int(text[:2]) if text.isdigit() and len(text) > 2 else mode


def render_content(value, is_picture=False):
    value = _text(value)
    if is_picture:
        if not value.startswith('data:image/'):
            value = 'data:image/png;base64,' + value
        return '<img src="' + html.escape(value, quote=True) + '">'
    # Preserve the actual image position, including relative and protocol-relative URLs.
    def absolute(match):
        url = urljoin('https://resource.vocabgo.com/', match.group(2))
        return match.group(1) + html.escape(url, quote=True) + match.group(3)
    return re.sub(r"((?:src|data-src|data-original|data-lazy-src)=[\"'])([^\"']+)([\"'])", absolute, value)


def audio_sources(exam):
    explicit = exam.get('audio')
    if explicit is not None:
        values = explicit if isinstance(explicit, list) else [explicit]
        if not 1 <= len(values) <= 4:
            raise ValueError('音频数量无效')
        result = []
        for value in values:
            item = {'url': value} if isinstance(value, str) else value
            if not isinstance(item, dict) or set(item) not in ({'url'}, {'objectId'}):
                raise ValueError('音频来源不明确')
            key = next(iter(item))
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError('音频来源为空')
            result.append(dict(item))
        return result
    stem = exam.get('stem') or {}
    for language in ('en', 'us'):
        value = stem.get('ph_' + language + '_url')
        if not value:
            continue
        value = _text(value).replace('%', '_')
        if exam.get('word_type') == 2:
            base = stem.get('au_addr')
            if not isinstance(base, str) or not base.startswith('https://'):
                raise ValueError('TTS 资源缺少地址')
            value = base.rstrip('/') + '/AudioTTS/SEN/' + language.upper() + '/M' + value
        return [{'url': urljoin('https://resource.vocabgo.com/', value)}]
    return []


def _options(exam):
    result = []
    for index, item in enumerate(exam.get('options') or []):
        if not isinstance(item, dict):
            raise ValueError('选项结构不明确')
        content = render_content(item.get('content'), exam.get('enable_i_o') == 1)
        tag = item.get('answer_tag', index)
        children = item.get('sub_options') or []
        if children:
            if not isinstance(tag, str):
                raise ValueError('组合选项缺少提交标记')
            for child in children:
                result.append((content + ' ' + _text(child.get('content')), tag + str(child['answer_tag'])))
        else:
            # The donor protocol uses a trailing 0 for string-tagged sentence options.
            if isinstance(tag, str) and normalized_mode(exam['topic_mode']) in (41, 42, 43, 44, 46):
                tag += '0'
            if isinstance(tag, bool) or not isinstance(tag, (str, int)):
                raise ValueError('选项提交标记无效')
            result.append((content, tag))
    if len(result) > 26 or len({x[0] for x in result}) != len(result):
        raise ValueError('选项重复或数量超出协议范围')
    return result


def build_question(exam, mode):
    if not isinstance(exam, dict) or exam.get('topic_mode') != mode:
        raise ValueError('题型不一致')
    mode = normalized_mode(mode)
    stem = exam.get('stem') or {}
    content = render_content(stem.get('content') or '', exam.get('enable_i_i') == 1)
    remark = stem.get('remark')
    title = content
    if isinstance(remark, str) and remark.strip():
        title += '\n中文提示：' + remark.strip()
    audio = audio_sources(exam) if mode in (21, 22, 61) or exam.get('audio') is not None else []
    if mode in (21, 22) and not audio:
        raise ValueError('听音题缺少实际音频')
    if audio and not title.strip():
        title = '根据音频选择正确选项'
    if mode == 31 and isinstance(remark, list) and not title.strip():
        title = '请选择每个项目对应的选项'
    if not title.strip():
        raise ValueError('没有可供题库解答的题干')
    options = _options(exam)
    request = {'type': 'single', 'title': title, 'options': [x[0] for x in options]}
    meta = {'mode': mode, 'options': options}
    if audio:
        request['audio'] = audio
    context = exam.get('context')
    if isinstance(context, str) and context.strip():
        request['context'] = context
    if exam.get('images'):
        images = exam['images']
        if not isinstance(images, list) or not all(isinstance(x, str) and x.startswith('data:image/') for x in images):
            raise ValueError('原生图片必须带明确 data URI')
        request['images'] = images
        for field in ('original_title', 'original_options', 'suggestion_title', 'suggestion_options'):
            if field in exam:
                request[field] = exam[field]
    if mode == 61:
        request['title'] += '\n选择与其他选项发音不同的单词。'
    if mode in (11, 13, 15, 16, 17, 18, 21, 22, 41, 42, 43, 44, 46, 61, 62, 71, 72):
        if len(options) < 2:
            raise ValueError('选择题缺少选项')
    elif mode == 31:
        if not isinstance(remark, list) or not remark:
            raise ValueError('配对题缺少明确的配对项目')
        relations = [_text(x.get('relation')) for x in remark if isinstance(x, dict)]
        if len(relations) != len(remark) or len(set(relations)) != len(relations) or len(options) < 2:
            raise ValueError('配对项目不明确')
        request = {'type': 'completion', 'title': title + '\n按以下项目顺序填写对应选项的大写字母：' + json.dumps(relations, ensure_ascii=False),
                   'options': [x[0] for x in options], 'blankCount': len(relations)}
        meta['relations'] = relations
    elif mode == 32:
        slots = re.findall(r'_-_|_', content)
        count = sum(2 if x == '_-_' else 1 for x in slots)
        if count < 1:
            raise ValueError('短语填空缺少明确空位')
        request.update(type='completion', blankCount=count,
                       title=title + '\n按空位顺序逐项填写英文单词；_-_ 对应两个单词，固定词不要重复填写。')
    elif mode in (51, 52, 53, 54, 55, 56, 57, 58, 73):
        lengths = exam.get('w_lens') or exam.get('wlens') or ([exam['w_len']] if exam.get('w_len') else None)
        if not isinstance(lengths, list) or not lengths or any(type(n) is not int or n < 1 for n in lengths):
            raise ValueError('拼写题缺少明确空位长度')
        if mode != 73 and len(lengths) != 1:
            raise ValueError('单词填空数量不明确')
        request.update(type='completion', blankCount=len(lengths),
                       title=title + '\n按空位顺序填写完整单词。字母数：' + json.dumps(lengths) + '\n已知前缀：' + str(exam.get('w_tip') or ''))
        meta['lengths'] = lengths
    else:
        raise ValueError('该题型缺少已验证的荷花题库映射')
    return request, meta


def parse_answer(payload, request, meta):
    if isinstance(payload, dict) and payload.get('code') != 1 and payload.get('error') in ('NO_ANSWER', 'LOTUS_MANUAL_REQUIRED', 'UNSUPPORTED_TYPE'):
        return None
    if not isinstance(payload, dict) or payload.get('code') != 1:
        raise LotusError('荷花题库未成功返回答案，转入旧逻辑兜底；将使用旧逻辑兜底。')
    if payload.get('manual', False) is not False:
        return None
    kind = payload.get('type', request['type'])
    answers = payload.get('answers')
    if not isinstance(answers, list) or not answers or not all(isinstance(x, str) and x.strip() for x in answers):
        return None
    answers = [x.strip() for x in answers]
    if kind == 'judgement' and request['type'] == 'single' and len(answers) == 1:
        labels = {'正确': True, '错误': False, 'true': True, 'false': False, '对': True, '错': False, '是': True, '否': False}
        values = [labels.get(x[0].strip().lower()) for x in meta['options']]
        if len(values) == 2 and set(values) == {True, False} and answers[0] in ('正确', '错误'):
            return meta['options'][values.index(answers[0] == '正确')][1]
        return None
    if kind != request['type']:
        return None
    if kind == 'single':
        if len(answers) != 1 or not re.fullmatch('[A-Z]', answers[0]):
            return None
        index = ord(answers[0]) - 65
        return meta['options'][index][1] if index < len(meta['options']) else None
    if len(answers) != request['blankCount']:
        return None
    mode = meta['mode']
    if mode == 31:
        if any(not re.fullmatch('[A-Z]', x) or ord(x)-65 >= len(meta['options']) for x in answers):
            return None
        return {relation: meta['options'][ord(value)-65][1] for relation, value in zip(meta['relations'], answers)}
    if mode == 32:
        if any(',' in x for x in answers):
            return None
        pool = [x[0].casefold() for x in meta['options']]
        if pool and any(x.casefold() not in pool and not any(x.casefold() in p.split() for p in pool) for x in answers):
            return None
        return ','.join(answers)
    if any(len(x) != n or not re.fullmatch(r"[A-Za-z'-]+", x) for x,n in zip(answers,meta['lengths'])):
        return None
    return json.dumps(answers) if mode == 73 else answers[0]


def answer_from_lotus(public_info, mode):
    settings = load_settings(public_info.path)
    try:
        request, meta = build_question(public_info.exam, mode)
    except (ValueError, TypeError, KeyError, AttributeError):
        logger.info('荷花题库：题型或结构无法可靠映射，转入旧逻辑兜底。')
        return None
    try:
        # One request only: a timed-out model may still be running on the server.
        response = requests.post(settings['url'], json=request,
                                 headers={'Authorization': 'Bearer ' + settings['token']},
                                 timeout=settings['timeout'], allow_redirects=False)
        if response.status_code != 200:
            raise LotusError(f'荷花题库 HTTP {response.status_code}，转入旧逻辑兜底。')
        result = parse_answer(response.json(), request, meta)
    except (requests.RequestException, ValueError):
        raise LotusError('荷花题库连接或响应无效，转入旧逻辑兜底；不重复题库请求。') from None
    logger.info('荷花题库：%s', '答案已校验' if result is not None else '无可自动提交的答案，跳过')
    return result

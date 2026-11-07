"""Exercise the installed Lotus server/parser/normalizer with a synthetic model."""
import os
import shutil
import subprocess
import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from api.lotus_tiku import answer_from_lotus

SCRIPT = r"""
import {pathToFileURL} from 'node:url';
const root=pathToFileURL(process.argv[1]+'/');
const {createServer}=await import(new URL('src/server.mjs',root));
const {config}=await import(new URL('test/helpers.mjs',root));
const server=createServer(config({backend:'codex',codexModel:'test'}),{
 transcriber:async audio=>{if(!audio[0].url.includes('pack.mp3'))throw new Error('wrong audio');return 'pack';},
 codexRunner:async content=>{
  const text=JSON.stringify(content);
  let answers=['B'];
  if(text.includes('ASR test') && !text.includes('pack'))throw new Error('transcript missing');
  if(text.includes('Image test') && content.filter(x=>x.type==='input_image').length!==2)throw new Error('missing images');
  if(text.includes('Context test') && !text.includes('context-marker'))throw new Error('missing context');
  if(text.includes('waste-free'))answers=['waste','free'];
  if(text.includes('catwalk'))answers=['cat','walk'];
  return JSON.stringify({answers});
 }
});
server.listen(0,'127.0.0.1',()=>console.log('PORT='+server.address().port));
"""

@unittest.skipUnless(os.environ.get('OCS_AI_SOURCE') and shutil.which('node'),'set OCS_AI_SOURCE for real Lotus protocol integration')
class LotusServerTests(unittest.TestCase):
    def test_real_server_transport_and_native_submission_formats(self):
        process=subprocess.Popen(['node','--input-type=module','-e',SCRIPT,os.environ['OCS_AI_SOURCE']],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        try:
            line=process.stdout.readline().strip();self.assertTrue(line.startswith('PORT='))
            port=int(line[5:])
            with tempfile.TemporaryDirectory() as root:
                (Path(root)/'config').mkdir();(Path(root)/'config/lotus.json').write_text(json.dumps({'url':f'http://127.0.0.1:{port}','token':'test-adapter-token-123456'}))
                png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jT1cAAAAASUVORK5CYII='
                image='<img src="data:image/png;base64,'+png+'">'
                cases=[({'topic_mode':15,'stem':{'content':'Choose the word'},'options':[{'content':'first','answer_tag':5},{'content':'second','answer_tag':7}]},7),
                       ({'topic_mode':32,'stem':{'content':'waste-free: _-_','remark':'无废物'},'options':[{'content':'waste'},{'content':'free'}]},'waste,free'),
                       ({'topic_mode':73,'stem':{'content':'catwalk: {c} {w}'},'w_lens':[3,4]},'["cat", "walk"]'),
                       ({'topic_mode':21,'stem':{'content':'ASR test','ph_en_url':'/pack.mp3'},'options':[{'content':'cat','answer_tag':2},{'content':'pack','answer_tag':4}]},4),
                       ({'topic_mode':15,'stem':{'content':'Image test '+image},'options':[{'content':image,'answer_tag':2},{'content':'text','answer_tag':4}]},4),
                       ({'topic_mode':15,'context':'context-marker','stem':{'content':'Context test'},'options':[{'content':'first','answer_tag':2},{'content':'second','answer_tag':4}]},4)]
                for exam,expected in cases:
                    with self.subTest(mode=exam['topic_mode']):self.assertEqual(answer_from_lotus(SimpleNamespace(path=root,exam=exam),exam['topic_mode']),expected)
        finally:
            process.terminate();process.wait(timeout=10);process.stdout.close()

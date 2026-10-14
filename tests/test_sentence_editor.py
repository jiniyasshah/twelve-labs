"""Exact sentence selection, approximate alignment, and immutable WAV edit tests."""
import math
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from sentence_editor import split_sentences, align_words, replace_region, plain_text


def test_markup_aware_split():
    text='[joyful] Hello (((friend))). Good news <laugh> indeed! Dr. Alice is here. Really?'
    spans=split_sentences(text)
    assert len(spans)==4
    assert spans[0]['text']=='[joyful] Hello (((friend))).'
    assert spans[-1]['text']=='Really?'
    assert ''.join(text[p['char_start']:p['char_end']] for p in spans).replace(' ','') == ''.join(s['text'] for s in spans).replace(' ','')
    assert 'Hello friend.' in plain_text(text)


def test_word_aligned_boundaries():
    text='Hello world. This is good. Thanks so much.'
    detected=[{'word':word,'start':a,'end':b} for word,a,b in [
        ('Hello',.10,.30),('world.',.32,.70),('This',1.06,1.20),('is',1.22,1.38),('good.',1.40,1.75),
        ('Thanks',2.20,2.35),('so',2.4,2.6),('much.',2.66,3.1)]]
    parts=align_words(text,detected,3.3)
    assert len(parts)==3
    assert parts[0]['start']==0
    assert .70<=parts[0]['end']<=1.06
    assert 1.75<=parts[1]['end']<=2.20
    assert all(p['confidence']==1 for p in parts)
    assert parts[-1]['end']==3.3


def test_unmatched_words_are_honestly_estimated():
    chunks=align_words('One. Two. Three.',[],3)
    assert len(chunks)==3
    assert all(p['method']=='estimated-review' for p in chunks)
    assert chunks[0]['start']==0 and chunks[-1]['end']==3


def test_localized_splice_retains_remote_audio():
    sr=1000
    orig=np.linspace(-.5,.5,6000,dtype=np.float32)
    new=np.ones(1200,dtype=np.float32)*.12
    edited=replace_region(orig,new,2.0,3.0,sr,fade_ms=20)
    assert np.array_equal(edited[:1960],orig[:1960])
    assert np.array_equal(edited[-1000:],orig[-1000:])
    assert len(edited)==6000-1000+1200-40
    with pytest.raises(ValueError):replace_region(orig,new,3.0,2.0,sr)


class FakeModel:
    sample_rate=24000
    available_voices=['Bruno','Luna']
    device='cpu'
    def __init__(self,*args,**kwargs):self.device=kwargs.get('device','cpu')
    def generate(self,text,**kwargs):
        t=np.linspace(0,1.5,36000,endpoint=False)
        return (.04*np.sin(2*math.pi*220*t)).astype('float32')


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB',tmp_path/'history.sqlite3')
    for name in ('OUTPUTS','REFS','CHUNKS','PREVIEWS'):
        monkeypatch.setattr(server,name,tmp_path/name.lower())
        getattr(server,name).mkdir(exist_ok=True)
    server.init_db()
    server.engine.current_key=None;server.engine.model=None;server.engine.factory=FakeModel
    if hasattr(server.engine,'_aligner'):delattr(server.engine,'_aligner')
    with TestClient(server.app) as c:yield c
    for f in list(server.engine.futures.values()):f.result(timeout=10)


def done(c, id):
    for _ in range(100):
        j=c.get('/api/jobs/'+id).json()
        if j['status'] in ('done','error'):return j
        time.sleep(.035)
    pytest.fail('Job timeout')


def test_generate_align_preview_apply_preserves_original(client):
    c=client
    original=done(c,c.post('/api/generate',json={'text':'Hello world. This is another sentence.','voice':'Bruno'}).json()['job_id'])
    assert original['status']=='done',original['error']
    rid=original['result_id']
    # Align uses optional ASR; missing dependency yields explicitly estimated times.
    aligned=done(c,c.post(f'/api/edit/{rid}/align',json={}).json()['job_id'])
    assert aligned['status']=='done',aligned['error']
    info=c.get(f'/api/edit/{rid}').json()
    assert info['aligned'] and len(info['sentences'])==2
    assert info['sentences'][0]['start']==0
    assert c.get(f'/api/edit/{rid}/waveform').json()['peaks']
    prev=done(c,c.post(f'/api/edit/{rid}/preview',json={
        'sentence_index':1,'text':'This is a corrected sentence.'}).json()['job_id'])
    assert prev['status']=='done',prev['error']
    assert c.get(prev['preview_url']).headers['content-type'].startswith('audio/wav')
    chosen=info['sentences'][1]
    result=done(c,c.post(f'/api/edit/{rid}/apply',json={
        'sentence_index':1,'preview_job_id':prev['id'],
        'start':chosen['start'],'end':chosen['end']}).json()['job_id'])
    assert result['status']=='done',result['error']
    revised=result['result_id']
    assert revised !=rid
    assert c.get(f'/api/audio/{rid}').status_code==200
    assert c.get(f'/api/audio/{revised}').status_code==200
    assert 'corrected sentence' in c.get(f'/api/edit/{revised}').json()['recording']['text']
    assert c.get(f'/api/edit/{revised}').json()['parent_id']==rid
    assert c.get(f'/api/edit/{revised}').json()['aligned'] is False
    assert len(c.get('/api/history').json())==2


def test_invalid_cross_record_preview_is_blocked(client):
    c=client
    a=done(c,c.post('/api/generate',json={'text':'First. Second.'}).json()['job_id'])['result_id']
    b=done(c,c.post('/api/generate',json={'text':'First. Second.'}).json()['job_id'])['result_id']
    done(c,c.post(f'/api/edit/{a}/align',json={}).json()['job_id'])
    done(c,c.post(f'/api/edit/{b}/align',json={}).json()['job_id'])
    p=done(c,c.post(f'/api/edit/{a}/preview',json={'sentence_index':0,'text':'Another.'}).json()['job_id'])
    j=done(c,c.post(f'/api/edit/{b}/apply',json={'sentence_index':0,'preview_job_id':p['id'], 'start':0,'end':.4}).json()['job_id'])
    assert j['status']=='error' and 'belongs to another sentence' in j['error']

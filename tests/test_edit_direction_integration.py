"""v2.8: editing one sentence with expression cues and a delivery override."""
import sys
from pathlib import Path
import math
import time
import numpy as np
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class RecordingModel:
    sample_rate=24000
    device='cpu'
    available_voices=['Bruno']
    calls=[]
    def __init__(self,*args,**kwargs):pass
    def generate(self, text, **kwargs):
        self.calls.append((text,kwargs))
        t=np.arange(24000,dtype=np.float32)/24000
        return (.04*np.sin(2*math.pi*220*t)).astype('float32')

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB',tmp_path/'history.sqlite3')
    for name in ('OUTPUTS','REFS','CHUNKS','PREVIEWS'):
        monkeypatch.setattr(server,name,tmp_path/name.lower())
        getattr(server,name).mkdir(exist_ok=True)
    server.init_db()
    server.engine.current_key=None;server.engine.model=None;server.engine.factory=RecordingModel
    RecordingModel.calls=[]
    with TestClient(server.app) as client:yield client
    for f in list(server.engine.futures.values()):f.result(timeout=10)

def finished(client,job_id):
    for _ in range(150):
        job=client.get('/api/jobs/'+job_id).json()
        if job['status'] in ('done','error'):return job
        time.sleep(.03)
    raise AssertionError('job timeout')

def make_source(c):
    g=finished(c,c.post('/api/generate',json={
        'model':'KittenML/kitten-tts-2',
        'text':'The answer is simple. We made it work!', 'voice':'Bruno',
        'advanced':{'use_emotion':False},'preset':'stable'
    }).json()['job_id'])
    assert g['status']=='done',g.get('error')
    rid=g['result_id']
    a=finished(c,c.post(f'/api/edit/{rid}/align',json={}).json()['job_id'])
    assert a['status']=='done',a.get('error')
    return rid

def test_tagged_sentence_overrides_only_selected_take(client):
    c=client;rid=make_source(c)
    tagged='[excited] We (((finally))) did it <laugh>!'
    prev=finished(c,c.post(f'/api/edit/{rid}/preview',json={
        'sentence_index':1,'text':tagged,'preset':'expressive','device':'cpu'
    }).json()['job_id'])
    assert prev['status']=='done',prev.get('error')
    assert RecordingModel.calls[-1][0]==tagged
    assert RecordingModel.calls[-1][1]['preset']=='expressive'
    assert RecordingModel.calls[-1][1]['advanced']['use_emotion'] is True
    assert prev['preview_data']['cues'] is True
    assert prev['preview_data']['preset']=='expressive'
    aligned=c.get(f'/api/edit/{rid}').json()['sentences'][1]
    new=finished(c,c.post(f'/api/edit/{rid}/apply',json={
        'sentence_index':1,'start':aligned['start'],'end':aligned['end'],
        'preview_job_id':prev['id']
    }).json()['job_id'])
    assert new['status']=='done',new.get('error')
    updated=c.get(f"/api/edit/{new['result_id']}").json()['recording']['text']
    assert updated.startswith('The answer is simple.')
    assert tagged in updated
    assert c.get(f'/api/audio/{rid}').status_code==200
    assert c.get(f"/api/audio/{new['result_id']}").status_code==200

def test_no_tags_keep_prior_conditioning_and_preset(client):
    c=client;rid=make_source(c)
    job=finished(c,c.post(f'/api/edit/{rid}/preview',json={
        'sentence_index':0,'text':'An ordinary sentence.'
    }).json()['job_id'])
    assert job['status']=='done',job.get('error')
    assert RecordingModel.calls[-1][1]['preset']=='stable'
    assert RecordingModel.calls[-1][1]['advanced']['use_emotion'] is False

def test_bad_preset_rejected_early(client):
    c=client;rid=make_source(c)
    r=c.post(f'/api/edit/{rid}/preview',json={'sentence_index':0,'text':'Hello','preset':'bad'})
    assert r.status_code==422

"""FastAPI smoke tests with a small synthetic model (no weight downloads)."""
import math
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class FakeModel:
    sample_rate = 24000
    available_voices = ['Bella', 'Jasper', 'Luna', 'Bruno', 'Rosie', 'Hugo', 'Kiki', 'Leo']
    available_decoders = ['default', 'student_w4']
    device = 'cpu'
    def __init__(self, *args, **kwargs):
        self.device=kwargs.get('device', 'cpu')
    def generate(self, text, **kwargs):
        return np.sin(np.linspace(0, math.pi*12, 2400)).astype('float32')*.08
    def generate_stream(self, text, **kwargs):
        for _ in range(2):
            yield self.generate(text, **kwargs)
    def _join(self, chunks, gap_s=.16):
        return np.concatenate(chunks)

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(server, 'DB', tmp_path/'studio.sqlite3')
    monkeypatch.setattr(server, 'OUTPUTS', tmp_path/'outputs')
    monkeypatch.setattr(server, 'REFS', tmp_path/'references')
    monkeypatch.setattr(server, 'CHUNKS', tmp_path/'chunks')
    for p in (server.OUTPUTS,server.REFS,server.CHUNKS):p.mkdir()
    server.init_db()
    server.engine.model=None
    server.engine.current_key=None
    server.engine.factory=FakeModel
    with TestClient(server.app) as c: yield c
    for fut in list(server.engine.futures.values()):fut.result(timeout=10)

def done(client, job_id):
    for _ in range(100):
        job=client.get('/api/jobs/'+job_id).json()
        if job['status'] in ('done','error','cancelled'):return job
        time.sleep(.04)
    pytest.fail('Timed out')

def test_generate(client):
    r=client.post('/api/generate',json={'text':'Hello world.','voice':'Bruno','model':'KittenML/kitten-tts-2','weights':'emb4'})
    assert r.status_code==200
    job=done(client,r.json()['job_id'])
    assert job['status']=='done',job['error']
    assert client.get('/api/audio/'+job['result_id']).status_code==200
    assert client.get('/api/download/'+job['result_id']).headers['content-type'].startswith('audio/wav')
    assert len(client.get('/api/history').json())==1

def test_stream_and_script(client):
    p={'text':'Hello again.','voice':'Luna','streaming':True}
    job=done(client,client.post('/api/generate',json=p).json()['job_id'])
    assert job['status']=='done',job['error']
    assert len(job['chunks'])==2
    assert client.get(job['chunks'][0]['url']).status_code==200
    job=done(client,client.post('/api/generate',json={'segments':[{'text':'One','voice':'Bruno'},{'text':'Two','voice':'Luna'}],'segment_gap':.2}).json()['job_id'])
    assert job['status']=='done',job['error']
    assert len(job['result_ids'])==2
    assert len(client.get('/api/history').json())==4

def test_reject_bad_model_and_oversized_text(client):
    assert client.post('/api/generate',json={'text':'hello','model':'not-approved'}).status_code==422
    assert client.post('/api/generate',json={'text':'x'*25001}).status_code==422

def test_reference_and_delete(client):
    response=client.post('/api/reference', files={'file':('me.wav',b'RIFFxxxxWAVE', 'audio/wav')})
    assert response.status_code==200
    rid=response.json()['reference_id']
    assert client.get('/api/reference/'+rid).status_code==200
    job=done(client,client.post('/api/generate',json={'text':'test','voice':'Bruno'}).json()['job_id'])
    assert client.delete('/api/history/'+job['result_id']).status_code==200
    assert client.get('/api/audio/'+job['result_id']).status_code==404

def test_origin_blocked(client):
    response=client.post('/api/load',json={'model':'KittenML/kitten-tts-2'}, headers={'Origin':'https://evil.example'})
    assert response.status_code==403

def test_private_cached_snapshot_can_be_used(client,monkeypatch,tmp_path):
    # When a snapshot is already present, load through the local path rather than
    # issuing another Hugging Face repo request over a potentially unstable link.
    sources=[]
    class RecordingModel(FakeModel):
        def __init__(self, source, **kwargs):
            super().__init__(source, **kwargs)
            sources.append(source)
    monkeypatch.setattr(server, 'cached_model_snapshot', lambda *args: str(tmp_path/'cached_model'))
    server.engine.factory=RecordingModel
    job=done(client,client.post('/api/load',json={'model':'KittenML/kitten-tts-2'}).json()['job_id'])
    assert job['status']=='done',job['error']
    assert sources==[str(tmp_path/'cached_model')]

def test_status_does_not_expose_token(client,monkeypatch):
    monkeypatch.setenv('HF_TOKEN','hf_private_secret_should_never_appear_in_response')
    result=client.get('/api/info')
    assert result.status_code==200
    assert result.json()['engine']['authenticated'] is True
    assert 'hf_private_secret_should_never_appear_in_response' not in result.text

def test_hf_token_passed_to_kitten2_model_without_leaking(client, monkeypatch):
    calls = []
    class CaptureModel(FakeModel):
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs.copy()))
            super().__init__(*args, **kwargs)
    monkeypatch.setenv('HF_TOKEN', 'hf_dummy_test_token_do_not_log')
    monkeypatch.setattr(server, 'cached_model_snapshot', lambda *args: None)
    server.engine.factory = CaptureModel
    job = done(client, client.post('/api/load', json={'model':'KittenML/kitten-tts-2'}).json()['job_id'])
    assert job['status'] == 'done', job['error']
    assert calls[0][1]['hf_token'] == 'hf_dummy_test_token_do_not_log'
    assert 'hf_dummy_test_token_do_not_log' not in client.get('/api/info').text


def test_legacy_model_uses_implicit_hf_env_auth(client, monkeypatch):
    calls = []
    class CaptureModel(FakeModel):
        def __init__(self, *args, **kwargs):
            calls.append(kwargs.copy())
            super().__init__(*args, **kwargs)
    monkeypatch.setenv('HF_TOKEN', 'hf_dummy_test_token')
    server.engine.factory = CaptureModel
    job = done(client, client.post('/api/load', json={'model':'KittenML/kitten-tts-mini-0.8'}).json()['job_id'])
    assert job['status'] == 'done', job['error']
    assert 'hf_token' not in calls[0]


def test_dotenv_does_not_override_os_env(monkeypatch, tmp_path):
    from dotenv import load_dotenv
    path = tmp_path / '.env'
    path.write_text('HF_TOKEN=hf_from_local_env_file\n', encoding='utf-8')
    monkeypatch.setenv('HF_TOKEN', 'hf_from_windows_env')
    load_dotenv(dotenv_path=path, override=False)
    assert server.os.getenv('HF_TOKEN') == 'hf_from_windows_env'
    monkeypatch.delenv('HF_TOKEN')
    load_dotenv(dotenv_path=path, override=False)
    assert server.os.getenv('HF_TOKEN') == 'hf_from_local_env_file'


def test_explicit_cuda_request_falls_back_to_cpu_for_cpu_only_torch(client, monkeypatch):
    monkeypatch.setattr(server, 'compute_capabilities', lambda: {
        'torch_cuda': False, 'torch_cuda_build': None, 'torch_version': '2.10.0+cpu',
        'onnx_cuda': False, 'onnx_providers': ['CPUExecutionProvider'], 'torch_error': None,
    })
    monkeypatch.setattr(server, 'cached_model_snapshot', lambda *args: None)
    calls=[]
    class CaptureModel(FakeModel):
        def __init__(self, *args, **kwargs):
            calls.append(kwargs.copy())
            super().__init__(*args, **kwargs)
    server.engine.factory=CaptureModel
    job=done(client,client.post('/api/load',json={'model':'KittenML/kitten-tts-2','device':'cuda'}).json()['job_id'])
    assert job['status']=='done', job['error']
    assert job['device']=='cpu'
    assert 'CUDA was requested' in job['warning']
    assert calls[0]['device']=='cpu'


def test_auto_uses_cuda_only_when_pytorch_reports_usable_gpu(client, monkeypatch):
    monkeypatch.setattr(server, 'compute_capabilities', lambda: {
        'torch_cuda': True, 'torch_cuda_build': '12.8', 'torch_version':'2.10.0+cu128',
        'onnx_cuda': False, 'onnx_providers':['CPUExecutionProvider'], 'torch_error': None,
    })
    monkeypatch.setattr(server, 'cached_model_snapshot', lambda *args: None)
    calls=[]
    class CaptureModel(FakeModel):
        def __init__(self,*args,**kwargs):
            calls.append(kwargs.copy())
            super().__init__(*args,**kwargs)
    server.engine.factory=CaptureModel
    job=done(client, client.post('/api/load',json={'device':'auto'}).json()['job_id'])
    assert job['status']=='done',job['error']
    assert job['warning'] is None
    assert job['device']=='cuda'
    assert calls[0]['device']=='cuda'


def test_onnx_cuda_request_requires_cuda_execution_provider(client,monkeypatch):
    monkeypatch.setattr(server,'compute_capabilities',lambda: {
        'torch_cuda': True, 'torch_cuda_build': '12.8', 'torch_version':'2.10.0+cu128',
        'onnx_cuda': False, 'onnx_providers':['CPUExecutionProvider'], 'torch_error': None,
    })
    calls=[]
    class CaptureModel(FakeModel):
        def __init__(self,*args,**kwargs):
            calls.append(kwargs.copy())
            super().__init__(*args,**kwargs)
    server.engine.factory=CaptureModel
    job=done(client, client.post('/api/load',json={'model':'KittenML/kitten-tts-mini-0.8','device':'cuda'}).json()['job_id'])
    assert job['status']=='done',job['error']
    assert 'ONNX CUDA' in job['warning']
    assert calls[0]['backend']=='cpu'

# v2.4 regression tests: stale reference recovery, saved references, CPU tuning,
# and local Whisper reuse. All are deterministic and never download weights.
def test_reference_list_and_reselection(client):
    response=client.post('/api/reference', files={'file':('my-voice.wav',b'RIFFxxxxWAVE','audio/wav')})
    assert response.status_code==200
    rid=response.json()['reference_id']
    refs=client.get('/api/references').json()
    assert len(refs)==1 and refs[0]['id']==rid and refs[0]['available']
    assert refs[0]['filename']=='my-voice.wav'
    server.REFS.joinpath(rid+'.wav').unlink()
    refs=client.get('/api/references').json()
    assert len(refs)==1 and refs[0]['available'] is False
    assert client.get('/api/reference/'+rid).status_code==404


def test_missing_reference_rejected_before_loading_model(client):
    class ShouldNotLoad:
        def __init__(self,*args,**kwargs):
            pytest.fail('Engine should not load until reference is resolved')
    server.engine.factory=ShouldNotLoad
    payload={'text':'A short hello','voice':'__clone__','reference_id':'f'*32}
    response=client.post('/api/generate',json=payload)
    assert response.status_code==422
    assert 'reference' in str(response.json()).lower()
    response=client.post('/api/generate',json={'segments':[{'text':'hello','voice':'__clone__'}]})
    assert response.status_code==422


def test_valid_cloning_reference_passes_before_model_load(client):
    import tempfile
    response=client.post('/api/reference', files={'file':('voice.wav',b'RIFFxxxxWAVE','audio/wav')})
    assert response.status_code==200
    rid=response.json()['reference_id']
    p={'text':'Say hello','voice':'__clone__','reference_id':rid,'reference_text':'The original recording text'}
    job=done(client,client.post('/api/generate',json=p).json()['job_id'])
    assert job['status']=='done',job['error']


def test_torch_cpu_thread_optimizer_can_be_overridden(monkeypatch):
    class FakeTorch:
        def __init__(self):self.threads=[]
        def set_num_threads(self,n):self.threads.append(n)
    fake=FakeTorch()
    monkeypatch.setitem(sys.modules,'torch',fake)
    monkeypatch.setattr(server.os,'cpu_count',lambda:12)
    monkeypatch.setenv('KITTEN_CPU_THREADS','7')
    server.configure_cpu_threads('cpu','v2')
    server.configure_cpu_threads('cuda','v2')
    server.configure_cpu_threads('cpu','onnx')
    assert fake.threads==[7, 7]


def test_local_whisper_cache_reused_by_loaded_transcriber(client,monkeypatch,tmp_path):
    whisper=tmp_path/'whisper'
    whisper.mkdir()
    monkeypatch.setattr(server,'cached_whisper_snapshot',lambda:str(whisper))
    class Transcriber:
        model_name='openai/whisper-large-v3'
    class FakeWithTranscriber(FakeModel):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.transcriber=Transcriber()
    server.engine.factory=FakeWithTranscriber
    job=done(client,client.post('/api/load',json={}).json()['job_id'])
    assert job['status']=='done',job['error']
    assert server.engine.model.transcriber.model_name==str(whisper)


# v2.6: repetition guards are opt-in and manually tuned parameters win.
def test_repetition_guards_off_unchanged():
    out=server.generation_options({}, 'v2')
    assert 'advanced' not in out
    assert server.generation_options({'loop_protection':'off'}, 'v2')==out


def test_repetition_guards_gentle_manual_override():
    out=server.generation_options({'loop_protection':'gentle','advanced':{'repetition_penalty':1.08}}, 'v2')
    assert out['advanced']=={'repetition_penalty':1.08,'token_run_penalty':1.45,'token_run_grace':8}
    strong=server.generation_options({'loop_protection':'strong'},'v2')
    assert strong['advanced']['token_run_grace']==6
    with pytest.raises(ValueError,match='Loop protection'):
        server.generation_options({'loop_protection':'invalid'},'v2')
    assert server.generation_options({'loop_protection':'strong'}, 'onnx')=={'speed':1.0}


def test_generation_timing_and_reused_model(client):
    payload={'text':'Hello there.', 'voice':'Bruno'}
    first=done(client,client.post('/api/generate',json=payload).json()['job_id'])
    assert first['status']=='done',first['error']
    assert first['timings']['reused_model'] is False
    second=done(client,client.post('/api/generate',json=payload).json()['job_id'])
    t=second['timings']
    assert second['status']=='done', second['error']
    assert t['reused_model'] is True
    assert t['audio_s']==.1
    assert t['synthesis_s']>=0
    assert t['model_setup_s']>=0
    assert t['rtf'] is not None


def test_generation_guard_sent_to_model(client):
    seen=[]
    class Spy(FakeModel):
        def generate(self,text,**kwargs):
            seen.append(kwargs)
            return super().generate(text,**kwargs)
    server.engine.factory=Spy
    done(client,client.post('/api/generate',json={'text':'Test','loop_protection':'gentle'}).json()['job_id'])
    assert seen[0]['advanced']['repetition_penalty']==1.15
    assert seen[0]['advanced']['token_run_penalty']==1.45

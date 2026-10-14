"""Optional engines preserve KittenTTS behavior and voice catalog."""
import pathlib
import unittest
import server
from model_backends import KOKORO_VOICES, INDIC_VOICES, KokoroEngine

class ExtensionsTest(unittest.TestCase):
    def test_catalog_languages(self):
        assert server.MODELS['hexgrad/Kokoro-82M']['family']=='kokoro'
        assert server.MODELS['ai4bharat/indic-parler-tts']['family']=='indic'
        assert KOKORO_VOICES['hf_alpha']=='Hindi'
        assert INDIC_VOICES['Nepali · Amrita']=='Nepali'
    def test_generation_options(self):
        assert server.generation_options({},'kokoro')=={}
        assert server.generation_options({'description':'Warm voice'},'indic')=={'description':'Warm voice'}
        with self.assertRaises(ValueError):
            server.generation_options({'description':'a'*501},'indic')
        assert server.generation_options({},'v2')['preset']=='stable'
    def test_gpu_fallback(self):
        actual,message=server.resolve_device('indic','cuda',{'torch_cuda':False,'onnx_cuda':False})
        assert actual=='cpu' and 'PyTorch' in message
        assert server.resolve_device('kokoro','auto',{'torch_cuda':True,'onnx_cuda':False})==('cuda',None)
    def test_kokoro_join(self):
        import numpy as np
        engine=object.__new__(KokoroEngine)
        engine.pipelines={'h':lambda text,voice: [(None,None,np.array([.1,.2])),(None,None,np.array([.3]))]}
        assert np.allclose(engine.generate('नमस्ते',voice='hf_alpha'),[.1,.2,.3])
    def test_dark_voice_cards(self):
        css=(pathlib.Path(__file__).parents[1]/'static/style.css').read_text()
        assert '[data-theme="dark"] .voice-card{background:#1d2028' in css
if __name__ == '__main__':
    unittest.main()

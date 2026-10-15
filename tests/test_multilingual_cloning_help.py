"""Regression tests for actionable model errors and multilingual voice cloning."""
import pathlib
import sys
import unittest
from unittest.mock import patch
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server
import studio
from model_backends import CLONE_LANGUAGES, ChatterboxEngine

class ModelGuidanceTests(unittest.TestCase):
    def test_gated_model_has_approved_help_url_not_raw_traceback(self):
        exc = RuntimeError("403 Client Error: Access to model ai4bharat/indic-parler-tts is restricted and you are not in the authorized list")
        help_data = server.explain_model_error(exc, "ai4bharat/indic-parler-tts")
        self.assertEqual(help_data["code"], "model_access")
        self.assertIn("request or accept access", help_data["message"])
        self.assertEqual(help_data["url"], "https://huggingface.co/ai4bharat/indic-parler-tts")
        self.assertNotIn("Client Error", help_data["message"])

    def test_untrusted_repos_cannot_supply_links(self):
        obj = server.explain_model_error(RuntimeError("GatedRepoError: access denied"),
                                          "evil.example/my-model")
        self.assertEqual(obj["code"], "model_access")
        self.assertIsNone(obj["url"])

    def test_non_gated_failure_does_not_create_access_link(self):
        self.assertIsNone(server.explain_model_error(
            RuntimeError("Connection refused"), "ai4bharat/indic-parler-tts"))

    def test_native_audio_guidance(self):
        obj = server.explain_model_error(
            RuntimeError("Could not load libtorchaudio.pyd"),
            "ai4bharat/indic-parler-tts")
        self.assertEqual(obj["code"], "audio_runtime")
        self.assertIn("--diagnose", obj["message"])

    def test_multilingual_cloning_catalog(self):
        self.assertIn("hi", CLONE_LANGUAGES)
        self.assertNotIn("ne", CLONE_LANGUAGES)
        self.assertEqual(server.MODELS["ResembleAI/chatterbox"]["family"], "chatterbox")
        self.assertEqual(server.MODELS["Firoj112/chatterbox-nepali-runs"]["family"], "nepali_clone")
        self.assertEqual(server.generation_options({"language":"hi"}, "chatterbox"), {"language":"hi"})
        self.assertEqual(server.generation_options({}, "nepali_clone"), {"language":"ne"})
        with self.assertRaisesRegex(ValueError, "supported"):
            server.generation_options({"language":"ne"}, "chatterbox")
        with self.assertRaisesRegex(ValueError, "Nepali"):
            server.generation_options({"language":"en"}, "nepali_clone")

    def test_isolated_clone_setup(self):
        self.assertNotEqual(studio.CLONE_ENV, studio.ENV)
        self.assertNotEqual(studio.CLONE_ENV, studio.INDIC_ENV)
        text = (pathlib.Path(__file__).parents[1] / "studio.py").read_text(encoding="utf-8")
        self.assertIn('chatterbox-tts', text)
        self.assertIn('CLONE_PYTHON', text)
        self.assertIn('"clone"', text)

    def test_clone_requires_reference_preflight(self):
        with self.assertRaisesRegex(ValueError, "reference"):
            server.validate_references({"model":"ResembleAI/chatterbox", "voice":"__clone__"})

    def test_worker_accepts_reference_and_language(self):
        import numpy as np
        from unittest.mock import patch
        engine = object.__new__(ChatterboxEngine)
        engine.nepali = False
        engine.sample_rate = 24000
        engine.available_voices = ["Multilingual default"]
        engine.process = type("FakeProc", (), {"poll":lambda self:None})()
        sent=[]
        class FakeStdin:
            def write(self, msg):sent.append(msg)
            def flush(self):pass
        engine.process.stdin = FakeStdin()
        engine._json = __import__("json")
        engine._receive = lambda: {"sample_rate":24000}
        with patch("soundfile.read", return_value=(np.zeros(2048, dtype=np.float32),24000)), \
             patch.object(pathlib.Path, "is_file", return_value=True):
            result=engine.generate("नमस्ते।", voice="Multilingual default",
                                   language="hi", reference="reference.wav")
        self.assertEqual(result.size,2048)
        sent_data=engine._json.loads(sent[0])
        self.assertEqual(sent_data["language"], "hi")
        self.assertEqual(sent_data["reference"], "reference.wav")
        engine.process = None

if __name__ == "__main__":
    unittest.main()

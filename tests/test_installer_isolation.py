"""Installer regression checks without network/model downloads."""
import pathlib
import unittest
from unittest.mock import patch
import studio

ROOT = pathlib.Path(__file__).resolve().parents[1]

class InstallerIsolationTests(unittest.TestCase):
    def test_separate_indic_venv(self):
        self.assertNotEqual(studio.INDIC_ENV, studio.ENV)
        self.assertNotEqual(studio.INDIC_PYTHON, studio.PYTHON)
        source = (ROOT / "studio.py").read_text(encoding="utf-8")
        self.assertIn('run(INDIC_PYTHON, "-m", "pip", "install"', source)
        self.assertNotIn('run(PYTHON, "-m", "pip", "install",\n                "git+https://github.com/huggingface/parler-tts.git")', source)

    @patch.object(studio, "run")
    @patch.object(studio, "cuda_ready", return_value=True)
    def test_cuda_already_working_never_downloads(self, _ready, run):
        studio.install_gpu(studio.PYTHON)
        run.assert_not_called()

    @patch.object(studio, "run")
    @patch.object(studio, "cuda_ready", side_effect=[False, True])
    def test_missing_cuda_installs_wheels_once(self, _ready, run):
        studio.install_gpu(studio.PYTHON)
        self.assertEqual(run.call_count, 1)
        self.assertIn("--upgrade", run.call_args.args)
        self.assertIn("cu128", " ".join(run.call_args.args))

    def test_worker_uses_isolated_python(self):
        backend = (ROOT / "model_backends.py").read_text(encoding="utf-8")
        self.assertIn('".venv-indic"', backend)
        self.assertIn('"indic_worker.py"', backend)
        self.assertNotIn('from parler_tts import', backend)

if __name__ == "__main__":
    unittest.main()

"""Regression checks for diagnostics and targeted native-audio repair."""
import pathlib
import sys
import unittest
from unittest.mock import patch
import studio
import server

class NativeAudioTests(unittest.TestCase):
    def test_probe_parses_both_cuda_and_audio_errors(self):
        class Result:
            returncode = 0
            stdout = '{"torch":"2.11.0+cu128","cuda_build":"12.8","cuda_available":true,"torchaudio_error":"OSError: missing DLL"}\n'
            stderr = ""
        with patch.object(studio.subprocess, "run", return_value=Result()):
            found = studio.runtime_probe(pathlib.Path(sys.executable))
        self.assertEqual(found["cuda_build"], "12.8")
        self.assertIn("missing DLL", found["torchaudio_error"])

    def test_repair_reinstalls_torchaudio_only(self):
        before = {"torch": "2.11.0+cu128", "cuda_build": "12.8", "torchaudio_error": "missing DLL"}
        after = {"torch": "2.11.0+cu128", "cuda_build": "12.8", "torchaudio": "2.11.0+cu128"}
        with patch.object(studio, "INDIC_PYTHON", pathlib.Path(sys.executable)), \
             patch.object(studio, "runtime_probe", side_effect=[before, after]), \
             patch.object(studio, "run") as runner:
            studio.repair_indic_audio()
        self.assertEqual(runner.call_count, 1)
        args = runner.call_args.args
        self.assertIn("torchaudio==2.11.0", args)
        self.assertIn("--no-deps", args)
        self.assertIn("https://download.pytorch.org/whl/cu128", args)
        self.assertNotIn("torch", args)

    def test_preexisting_cuda_build_does_not_trigger_redownload(self):
        with patch.object(studio, "cuda_ready", return_value=False), \
             patch.object(studio, "runtime_probe", return_value={
                 "torch": "2.11.0+cu128", "torchaudio": "2.11.0+cu128",
                 "cuda_build": "12.8", "cuda_available": False}), \
             patch.object(studio, "run") as runner:
            studio.install_gpu(studio.INDIC_PYTHON)
        runner.assert_not_called()

    def test_unavailable_torchaudio_version_installs_published_pair(self):
        before = {"torch": "2.14.1", "torchaudio_error": "libtorchaudio.pyd failed",
                  "cuda_build": None}
        after = {"torch": "2.11.0+cpu", "torchaudio": "2.11.0+cpu",
                 "cuda_build": None}
        with patch.object(studio, "INDIC_PYTHON", pathlib.Path(sys.executable)), \
             patch.object(studio, "runtime_probe", side_effect=[before, after]), \
             patch.object(studio, "run") as runner:
            studio.repair_indic_audio()
        self.assertEqual(runner.call_count, 1)
        args = runner.call_args.args
        self.assertIn("torch==2.11.0", args)
        self.assertIn("torchaudio==2.11.0", args)
        self.assertIn("https://download.pytorch.org/whl/cpu", args)
        self.assertNotIn("torchaudio==2.14.1", args)

    def test_cuda_repair_uses_matching_cuda_pair(self):
        before = {"torch": "2.14.1", "cuda_build": None,
                  "torchaudio_error": "missing binary"}
        after = {"torch": "2.11.0+cu128", "torchaudio": "2.11.0+cu128",
                 "cuda_build": "12.8"}
        with patch.object(studio, "runtime_probe", side_effect=[before, after]), \
             patch.object(studio, "run") as runner, \
             patch.object(studio, "ensure_env"):
            studio.ensure_indic_pair(cuda=True)
        args = runner.call_args.args
        self.assertIn("torch==2.11.0", args)
        self.assertIn("torchaudio==2.11.0", args)
        self.assertIn("https://download.pytorch.org/whl/cu128", args)

    def test_healthy_pair_skips_pip_completely(self):
        current = {"torch": "2.11.0+cpu", "torchaudio": "2.11.0+cpu",
                   "cuda_build": None}
        with patch.object(studio, "runtime_probe", return_value=current), \
             patch.object(studio, "run") as runner, \
             patch.object(studio, "ensure_env"):
            studio.ensure_indic_pair()
        runner.assert_not_called()

    def test_installer_skips_future_unavailable_torchaudio_versions(self):
        self.assertEqual(studio.INDIC_TORCH_VERSION, "2.11.0")
        self.assertFalse(studio._indic_pair_healthy({
            "torch": "2.14.1", "torchaudio": "2.11.0+cpu"}, cuda=False))
        self.assertFalse(studio._indic_pair_healthy({
            "torch": "2.11.0+cu128", "torchaudio": "2.11.0+cpu",
            "cuda_build": "12.8"}, cuda=True))

    def test_indic_cuda_probes_isolated_environment(self):
        with patch.object(server, "compute_capabilities", return_value={
            "torch_cuda": False, "onnx_cuda": False}), \
             patch.object(server, "indic_cuda_available", return_value=True):
            self.assertEqual(server.resolve_device("indic", "cuda"), ("cuda", None))

    def test_indic_cuda_does_not_assume_main_environment(self):
        with patch.object(server, "compute_capabilities", return_value={
            "torch_cuda": True, "onnx_cuda": False}), \
             patch.object(server, "indic_cuda_available", return_value=False):
            device, warning = server.resolve_device("indic", "cuda")
        self.assertEqual(device, "cpu")
        self.assertIn(".venv-indic", warning)

if __name__ == "__main__":
    unittest.main()

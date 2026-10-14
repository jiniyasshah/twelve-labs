"""Optional local TTS engines. Imported only when selected."""
from __future__ import annotations
import numpy as np

KOKORO_VOICES = {
    'af_heart': 'English', 'af_bella': 'English', 'af_nicole': 'English',
    'am_adam': 'English', 'am_michael': 'English', 'bf_emma': 'English',
    'bm_george': 'English', 'hf_alpha': 'Hindi', 'hf_beta': 'Hindi',
    'hm_omega': 'Hindi', 'hm_psi': 'Hindi',
}
INDIC_VOICES = {
    'Hindi · Rohit': 'Hindi', 'Hindi · Divya': 'Hindi',
    'Hindi · Aman': 'Hindi', 'Hindi · Rani': 'Hindi',
    'Nepali · Amrita': 'Nepali', 'English · Mary': 'English',
    'English · Thoma': 'English',
}

class KokoroEngine:
    sample_rate = 24000
    available_voices = list(KOKORO_VOICES)
    def __init__(self, device='cpu'):
        try:
            from kokoro import KPipeline, KModel
        except ImportError as exc:
            raise RuntimeError('Kokoro is not installed. Run: python studio.py --setup --extras kokoro') from exc
        self.device = device
        model = KModel(repo_id='hexgrad/Kokoro-82M').to(device).eval()
        self.model = model
        self.pipelines = {}
        self.pipeline_type = KPipeline
    def generate(self, text, voice='af_heart', **_):
        if voice not in KOKORO_VOICES:
            raise ValueError('Unknown Kokoro voice')
        lang_code = voice[0]
        if lang_code not in self.pipelines:
            self.pipelines[lang_code] = self.pipeline_type(
                lang_code=lang_code, model=self.model, repo_id='hexgrad/Kokoro-82M')
        parts = [np.asarray(audio, dtype=np.float32).reshape(-1)
                 for _, _, audio in self.pipelines[lang_code](text, voice=voice)]
        if not parts:
            raise ValueError('Kokoro produced no audio')
        return np.concatenate(parts)

class IndicParlerEngine:
    """Persistent isolated Parler worker; cannot downgrade KittenTTS dependencies."""
    available_voices = list(INDIC_VOICES)

    def __init__(self, device="cpu"):
        import pathlib
        import os
        import json
        import subprocess
        self._json = json
        root = pathlib.Path(__file__).resolve().parent
        exe = root / ".venv-indic" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not exe.is_file():
            raise RuntimeError("Indic Parler requires its own environment. Run python studio.py --setup --extras indic")
        self.process = subprocess.Popen(
            [str(exe), "-u", str(root / "indic_worker.py"), device],
            cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, encoding="utf-8", errors="replace", bufsize=1)
        answer = self._receive()
        if answer.get("error"):
            self.close()
            raise RuntimeError(answer["error"])
        self.device = answer["device"]
        self.sample_rate = int(answer["sample_rate"])

    def _receive(self):
        message = self.process.stdout.readline()
        if not message:
            raise RuntimeError("Indic Parler worker exited early. Check the console output for details.")
        try:
            return self._json.loads(message)
        except ValueError as exc:
            raise RuntimeError("Unexpected output from isolated Indic Parler worker") from exc

    def generate(self, text, voice="Hindi · Divya", description=None, **_):
        import tempfile
        import pathlib
        import soundfile as sf
        if voice not in INDIC_VOICES:
            raise ValueError("Unknown Indic Parler voice")
        if self.process.poll() is not None:
            raise RuntimeError("Indic Parler worker has stopped. Restart the model.")
        with tempfile.TemporaryDirectory(prefix="kitten-indic-") as temp:
            out = pathlib.Path(temp) / "speech.wav"
            command = {"text": text, "voice": voice, "description": description or "", "output": str(out)}
            self.process.stdin.write(self._json.dumps(command, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            result = self._receive()
            if result.get("error"):
                raise RuntimeError(result["error"])
            audio, sr = sf.read(str(out), dtype="float32")
            if int(sr) != self.sample_rate:
                raise RuntimeError("Indic worker sample rate changed unexpectedly")
            return np.asarray(audio, dtype=np.float32)

    def close(self):
        proc = getattr(self, "process", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    def __del__(self):
        self.close()

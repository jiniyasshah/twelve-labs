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
    available_voices = list(INDIC_VOICES)
    def __init__(self, device='cpu'):
        try:
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer
            import torch
        except ImportError as exc:
            raise RuntimeError('Indic Parler is not installed. Run: python studio.py --setup --extras indic') from exc
        self.device = device
        name = 'ai4bharat/indic-parler-tts'
        try:
            self.model = ParlerTTSForConditionalGeneration.from_pretrained(name).to(device).eval()
            self.prompt_tokenizer = AutoTokenizer.from_pretrained(name)
            self.description_tokenizer = AutoTokenizer.from_pretrained(self.model.config.text_encoder._name_or_path)
        except Exception as exc:
            if '401' in str(exc) or '403' in str(exc) or 'gated' in str(exc).lower():
                raise RuntimeError('Accept terms at https://huggingface.co/ai4bharat/indic-parler-tts and set HF_TOKEN in .env.') from exc
            raise
        self.sample_rate = int(self.model.config.sampling_rate)
    def generate(self, text, voice='Hindi · Divya', description=None, **_):
        import torch
        if voice not in INDIC_VOICES:
            raise ValueError('Unknown Indic Parler voice')
        speaker = voice.split(' · ', 1)[1]
        prompt = f"{speaker}'s voice delivers natural, clear speech at a moderate pace. The recording is of very high quality, with very clear audio and no background noise."
        directed = f"{speaker}'s voice. {description}" if description else prompt
        description = self.description_tokenizer(directed, return_tensors='pt').to(self.device)
        utterance = self.prompt_tokenizer(text, return_tensors='pt').to(self.device)
        with torch.inference_mode():
            audio = self.model.generate(
                input_ids=description.input_ids, attention_mask=description.attention_mask,
                prompt_input_ids=utterance.input_ids,
                prompt_attention_mask=utterance.attention_mask)
        return np.asarray(audio.cpu().numpy(), dtype=np.float32).reshape(-1)

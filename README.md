# Kitten Studio

Local speech production with KittenTTS, voice cloning, sentence-level replacement, history, Auto-direct and optional multilingual engines.

## One installer on Windows, Linux and macOS

Install Python 3.11 or 3.12, clone the repository, then run:

    python studio.py

On Windows you can also run `py studio.py`. The single entry point creates its own `.venv`, installs or repairs dependencies, then serves http://127.0.0.1:8765.

Optional commands, using that same file:

    python studio.py --setup --extras kokoro,indic,alignment
    python studio.py --setup --gpu
    python studio.py --offline
    python studio.py --cpu

`kokoro` adds fast Kokoro 82M with English/Hindi voices. `indic` adds Indic Parler for Hindi and Nepali (and English); Git must be installed, and its model is gated. `alignment` enables automatic speech sentence detection. `--gpu` installs a CUDA 12.8 PyTorch build for supported NVIDIA Windows/Linux systems. macOS uses CPU; other PyTorch backends depend on your local setup. Only install extras you intend to use.

### Models and limits

| Engine | Languages | Capabilities | Licensing |
| --- | --- | --- | --- |
| KittenTTS 2 | English, Hindi and other bundled voices | Voice cloning and expression tags | Follow model license |
| Kokoro 82M | English, Hindi | Small, fast, several voices; no cloning | Apache 2.0 |
| Indic Parler-TTS | Hindi, Nepali, English and others | Named speakers, optional description prompt; no Kitten tag syntax | Apache 2.0, gated downloads |
| Legacy Kitten ONNX | English | Very small and CPU friendly | Follow model license |

**Indic Parler model access:** First accept terms at https://huggingface.co/ai4bharat/indic-parler-tts, then set `HF_TOKEN` in your environment or copy `.env.example` to `.env`. Never commit credentials. The weights are several GB and are downloaded only when selected.

Expression tags, reference cloning and stream-chunk previews remain KittenTTS 2-only. Quality differences are subjective, so audition engines rather than assuming one is universally better. A script render uses one engine and that engine's voices.

Your `.env`, `.venv`, and `data` directories are ignored by Git and retained across source updates. WAV history lives in `data/`.

Run tests with `python -m pytest -q tests` and `node --test tests/*.test.cjs`. Actual inference with optional model weights has to be verified on a GPU/CPU host with downloads enabled.
# Kitten Studio

Local speech production with KittenTTS, voice cloning, sentence-level replacement, history, Auto-direct and optional multilingual engines.

## One installer on Windows, Linux and macOS

Install Python 3.11 or 3.12, clone the repository, then run:

    python studio.py

On Windows you can also run `py studio.py`. The single entry point creates its own `.venv`, installs or repairs dependencies, then serves http://127.0.0.1:8765.

Optional commands, using that same file:

    python studio.py --setup --extras kokoro,indic,clone,alignment
    python studio.py --setup --gpu
    python studio.py --setup --repair
    python studio.py --offline
    python studio.py --cpu

`kokoro` adds fast Kokoro 82M with English/Hindi voices. `indic` adds Indic Parler for Hindi and Nepali (and English); Git must be installed, and its model is gated. `alignment` enables automatic speech sentence detection. `--gpu` installs a CUDA 12.8 PyTorch build for supported NVIDIA Windows/Linux systems. macOS uses CPU; other PyTorch backends depend on your local setup. Only install extras you intend to use.

### Models and limits

| Engine | Languages | Capabilities | Licensing |
| --- | --- | --- | --- |
| KittenTTS 2 | English, Hindi and other bundled voices | Voice cloning and expression tags | Follow model license |
| Kokoro 82M | English, Hindi | Small, fast, several voices; no cloning | Apache 2.0 |
| Indic Parler-TTS | Hindi, Nepali, English and others | Named speakers, optional description prompt; no Kitten tag syntax | Apache 2.0, gated downloads |
| Chatterbox Multilingual | 23 incl. Hindi | Zero-shot reference voice cloning | MIT |
| Community Chatterbox Nepali | Nepali (experimental) | Reference voice cloning, community fine-tune | See model card |
| Legacy Kitten ONNX | English | Very small and CPU friendly | Follow model license |

**Indic Parler model access:** First accept terms at https://huggingface.co/ai4bharat/indic-parler-tts, then set `HF_TOKEN` in your environment or copy `.env.example` to `.env`. Never commit credentials. The weights are several GB and are downloaded only when selected. Indic Parler is installed in its own `.venv-indic` and runs in a persistent subprocess because it requires an older Transformers version incompatible with KittenTTS. The separate environment consumes additional disk space.

Expression tags, reference cloning and stream-chunk previews remain KittenTTS 2-only. Quality differences are subjective, so audition engines rather than assuming one is universally better. A script render uses one engine and that engine's voices.

Your `.env`, `.venv`, and `data` directories are ignored by Git and retained across source updates. WAV history lives in `data/`.

Run tests with `python -m pytest -q tests` and `node --test tests/*.test.cjs`. Actual inference with optional model weights has to be verified on a GPU/CPU host with downloads enabled.
### Repair after the older shared-environment installer

If you ran the earlier `--extras indic` command and saw Transformers/Hugging Face/protobuf conflicts, run `python studio.py --setup --repair`. This removes the old Parler packages from the main `.venv` and restores compatible core packages without reinstalling CUDA PyTorch. Then run `python studio.py --setup --extras indic` to set up the separate `.venv-indic`. The CUDA installer now skips working PyTorch builds; optional Indic CUDA can require another PyTorch download because its environment is isolated.

### Windows native TorchAudio errors

If the Indic worker reports `Could not load this library: ...libtorchaudio.pyd`, check both environments with `python studio.py --diagnose`. The setup command now validates the actual Parler/TorchAudio imports, and when appropriate attempts to reinstall only a TorchAudio wheel matching the isolated Indic PyTorch build. Manual repair: `python studio.py --setup --repair-indic-audio`. If it still fails, ensure the Microsoft Visual C++ Redistributable x64 is installed; the error can also indicate a missing native DLL. CUDA detection for Indic is independent of the main Studio environment.

## Automated verification

Every pull request and push to main runs Python API, editor, installer, and JavaScript regression tests with Python 3.12 on **Windows, Linux, and macOS**. A separate Windows job installs the actual PyTorch 2.11.0 / TorchAudio 2.11.0 CPU wheel pair, imports the native TorchAudio DLL, installs the open-source Parler Python package, and imports its model class. Tests do not download gated speech model weights or perform full audio inference.

If your older `.venv-indic` has PyTorch 2.14.1, no published TorchAudio 2.14.1 wheel is available from the index shown in your install log. The new installer will replace both incompatible wheels with the supported 2.11.0 pair **inside .venv-indic only**, leaving KittenTTS and existing recordings untouched. Use `python studio.py --setup --repair-indic-audio` (CPU) or `python studio.py --setup --repair-indic-audio --gpu` (NVIDIA CUDA 12.8). This correction requires a one-time PyTorch download when versions do not match.

## Multilingual voice cloning (optional)

Run the **single** installer with `python studio.py --setup --extras clone`. This creates `.venv-clone`, a separate Python environment for upstream Chatterbox and its pinned Torch dependencies; it does not change KittenTTS or Indic Parler. Choose **Chatterbox Multilingual** in Speech > Model, select the **Clone a voice** tab, upload or select a recording you have the rights to use, pick the target speech language, and generate. The voice reference is saved locally and may also be used for sentence-level replacements. No voice training is required.

The official [Chatterbox Multilingual](https://github.com/resemble-ai/chatterbox) model supports **23 languages** (including Hindi); it **does not natively support Nepali**. For Nepali select **Chatterbox Nepali · Experimental cloning**, which loads an open community checkpoint from [Firoj112/chatterbox-nepali-runs](https://huggingface.co/Firoj112/chatterbox-nepali-runs). The community checkpoint is not verified to match the official multilingual model's production reliability, and its quality may vary. It may download significant weights on first use.

A compatible CUDA driver alone does not mean Chatterbox's pinned PyTorch will accelerate on recent RTX GPUs. The installer intentionally preserves the upstream isolated dependencies rather than silently installing incompatible Torch/TorchAudio binaries. Voice cloning may initially run on CPU on some GPUs. This is different from the main KittenTTS CUDA environment.

**Important:** Kokoro and Indic Parler do not offer arbitrary speaker cloning in this Studio integration. The app therefore keeps those voices as built-in speakers rather than pretending to clone them; select a clone-capable model for reference voice work.

### Actionable model errors

When a model returns Hugging Face `403 / gated repo`, the job panel shows **Model access required** and provides the model's approved Hugging Face page. Request or accept the access conditions while signed into the account used for your `HF_TOKEN`; approval may require waiting. The model will not work until permissions are granted. Credentials are never included in job errors or returned URLs. Native audio errors instead point to local diagnostics and repair. This behavior also applies to any clone-capable model that has an explicitly configured access page.

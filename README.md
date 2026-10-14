# Kitten Studio · Windows edition (v2.8)

A clean, private, self-contained local web UI for [KittenML/KittenTTS](https://github.com/KittenML/KittenTTS). This is an independent community interface, not an official KittenML application.

## New in v2.8 — Direct each replacement sentence

The **Edit audio** workspace now has a dedicated **Direct this sentence** toolbar under the replacement text area. Each change affects **only the selected replacement take**; all unaffected audio stays as it was.

1. From **History**, choose **Edit speech** on a recording and detect/review sentence boundaries as before.
2. Select the sentence to replace. Under **Direct this sentence**, set a **leading emotion** such as Joyful, Surprised, Sad, or Tender. Choosing a different emotion *replaces* the previous leading emotion; choosing **No emotion** removes it. KittenTTS 2 treats one leading emotion tag as a direction for the entire sentence (not individual words).
3. To add an event mid-sentence, click where it should occur inside the text area, select the event (e.g. Gasp, Laugh, Sigh, Pause), and choose **Insert**. The editor preserves the text and cursor location instead of moving the event to the beginning.
4. To emphasize an important phrase, **highlight only the spoken words** in the text area, then choose **Emphasize selection**. Click again with the same phrase selected to remove the emphasis, or use **Clear cues** to remove the supported expression tags from that sentence. **Undo change** reverses the latest toolbar action.
5. Choose **Keep original**, **Stable**, or **Expressive** delivery for this replacement. **Keep original** is the default and uses the recording's stored settings. Explicit expression markup enables KittenTTS 2 emotion conditioning for this take, even if the source disabled it.
6. Preview the newly synthesized sentence. If satisfied, click **Replace selected sentence**: Studio saves a **new recording in History** and preserves the original WAV. Changing text, cues, or delivery invalidates any earlier preview, so an out-of-date take cannot accidentally be applied.

Unapplied edits and delivery choices survive switching among detected sentences within the same open recording. Re-aligning resets drafts to the current saved recording. These controls are hidden for legacy ONNX models, which don't support expression tags; the backend also rejects expression-tagged replacements for those models.

**Important:** KittenTTS 2's vocal events and emotion conditioning are beta and depend on the speaker, text, and preset. The tags guide generation, not guaranteed exact acting. They aren't spoken as ordinary words when the model recognizes them. The default model, weights, audio decoder, and original version-preservation workflow are unchanged. **No new Python dependencies or downloads are needed for this update.**

### Update v2.7 → v2.8

Stop Studio, extract this ZIP **over your existing v2.7 installation**, and replace the application files. Keep your local `.venv`, `.env`, and `data` folders exactly as they are. Restart `RUN_WINDOWS.bat` and refresh your browser using **Ctrl+F5** if you still see the old editor. No Python reinstall is required.

## Earlier improvements from v2.5

- **Auto-direct narration:** Click **✦ Auto-direct** in the Speech editor. Studio analyzes the text locally and *suggests* KittenTTS 2-supported `[emotion]`, `<event>` and `(((emphasis)))` markup. It uses local, deterministic linguistic rules and cue words, **not an LLM**; no model download, API call or token is needed. This is intentionally conservative and is not a guarantee of natural emotional interpretation. The voice synthesizer's own emotion support is beta.
- **Preview before applying:** Change intensity (**Subtle**, **Balanced**, **Expressive**), toggle which types of cues to suggest, compare original and suggested narration side-by-side, and click **Apply suggestions**. The original text is not modified before applying. **Undo auto tags** restores your exact previous text unless you've since edited the result (to protect your edits).
- **Script support:** **✦ Auto-direct** on a scene only modifies that scene; **✦ Auto-direct script** works on all scenes while keeping their voices and order. The Script builder has a matching Undo button. Existing manual tags are preserved; the suggestion engine avoids nesting emphasis tags.
- **Reference-inspired dark palette:** Near-black (#101114) canvas, cool charcoal panels, gray separators, and blue (#2563eb) primary actions and focus states, matching your provided design direction. No layout rebuild or change to the light theme. Theme toggle continues to remember your preference.
- **v2.5 note:** The previous release did not modify synthesis. v2.6 adds optional sampling controls; the default remains unchanged.

### Upgrade from an earlier version (keep your recordings and environment)

1. Close Kitten Studio with **Ctrl+C**.
2. Extract v2.8 into the **same folder** where `server.py` and your current `static` directory live. Allow replacing application files.
3. Do **not** delete `.venv`, `.env` or `data`: these hold your Python dependencies, token config, recordings, saved references and history.
4. Launch `RUN_WINDOWS.bat`; hard-refresh the UI with **Ctrl+F5** if an older theme or toolbar stays cached.
5. Select the **KittenTTS 2** model; click **✦ Auto-direct** below the narration. Review the preview and apply. Existing ONNX models do not support expression markup, so the Auto-direct controls are disabled for those models.

### Accuracy and privacy

Automated tagging uses a simple rule-based local suggestion engine. It recognizes explicit signals such as *"No way!"*, *"We won!"*, *"I'm heartbroken"*, or *"Haha"*, while leaving neutral material alone. It will not understand subtle acting instructions, character backstory or implied sarcasm. Always review the suggested markup; use manual direction controls for nuanced scenes. Suggestions are optional and are never silently inserted during generation.

## Install on Windows

1. Extract this folder wherever you like, e.g. `C:\KittenStudio`. **You do not need your existing `C:\KittenTTS` folder or its `.venv`.**
2. Double-click **`INSTALL_WINDOWS.bat`**. This creates **`C:\KittenStudio\.venv`** and installs `kittenml`, PyTorch, FastAPI and dependencies only inside it. It now verifies critical imports before claiming success. Python 3.10–3.12 must already be installed; 3.12 is a good choice. Installation requires internet access to download Python packages.
3. To use authenticated Hugging Face downloads, supply your **newly rotated** token as a standard **`HF_TOKEN` environment variable**. You may also copy `.env.example` to `.env` in the studio folder and fill in `HF_TOKEN=...` (keep that file private). A Windows environment variable takes precedence over `.env`. No credentials are included in this ZIP. Public models do not require authentication.
4. Double-click **`RUN_WINDOWS.bat`**. It now checks and automatically repairs missing Python dependencies (including FastAPI) before starting the web server. It allows missing model assets to download automatically while reusing everything present in the standard Hugging Face cache. Open **http://127.0.0.1:8765** if your browser does not open.
5. In the interface, select the **KittenTTS 2** model with **Compact** weights to match your existing setup, then choose a voice and click **Generate speech**. The model will load on the first generation (or use **Load model** at top right).

### Hugging Face token: standard environment variable (no token wizard)

**Recommended: set `HF_TOKEN` in your Windows user environment** using Windows **System Properties → Environment Variables → User variables → New**. Variable name: `HF_TOKEN`; value: your **newly rotated** Hugging Face token. Restart your terminal/application after setting it. Windows user environment variables are not encrypted secrets; consider their security implications on shared PCs.

Or create `C:\KittenStudio\.env` (in the same folder as `server.py`) with the exact shape:

```dotenv
HF_TOKEN=your_new_hf_token_here
```

The included `.env.example` is an empty template. The real `.env` is ignored by Git and is never included in a release archive. If both are set, Windows `HF_TOKEN` wins. The old DPAPI scripts and token-reset workflow were removed; **older `data\hf_token.dpapi` files are no longer read**. You may delete that old file after confirming the new setup works. The app reports only **token detected**, not **Hugging Face connected**, until the service actually verifies a request. You can also check reachability with `hf auth whoami` in a terminal that has `HF_TOKEN` set.

**Only one Windows PowerShell session:** rather than saving a persistent token, you can enter it without echoing it on screen:

```powershell
$secure = Read-Host 'HF token' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $env:HF_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
.\RUN_WINDOWS.bat
```

### Your previous environment is not used

The Windows launchers use only `kitten-studio\.venv\Scripts\python.exe`. They don't inspect or activate any sibling/parent Python installation or venv. Your old environment can be left alone. Hugging Face's model cache is shared **between** Python environments by design (typically under `C:\Users\<you>\.cache\huggingface`). That saves downloading gigabytes again without sharing Python packages.

### Why the earlier version failed

The original launcher forced `HF_HUB_OFFLINE=1`, even for models and auxiliary files that were missing from the Hugging Face cache. That produced the `OSError: couldn't connect ... files not cached` error. The default launcher now sets `HF_HUB_OFFLINE=0` and the engine tries a complete cached KittenTTS 2 snapshot first where possible, avoiding unnecessary Hub metadata requests. If the requested model, decoder, or speaker asset is absent, the library can download the missing files online.

- `RUN_WINDOWS.bat` — online **plus** local cache; use normally.
- `RUN_WINDOWS_OFFLINE.bat` — cache-only, for a fully downloaded model or when the network is unreliable. Requires all of that model's assets already available.
- `INSTALL_WINDOWS.bat` — create/install the independent virtual environment and verify dependencies.
- `REPAIR_WINDOWS.bat` — rerun the same installer safely if installation was interrupted; existing packages are reused.
- `verify_install.py` — confirm the current Python belongs to this studio and the necessary modules import successfully.

If `WinError 10054` appears in a Hugging Face download traceback, an HTTPS connection was reset. Authentication can improve rate limits, **but does not fix an interrupted TLS connection**. Try another connection or your mobile hotspot. A similar error from Windows `asyncio` Proactor socket cleanup can occur on a local browser disconnect and may not mean synthesis failed; this release uses the Selector event loop to avoid that noisy cleanup path. The model can still be run fully offline once all required files are cached.

## Feature guide

**Speech:** Write or import text, preview auto-suggested direction cues, select voices, add recognized `[emotion]`, `<event>`, and `(((emphasis)))` markup, select `stable`/`expressive` delivery, enable chunk previews and generate/download WAV audio. KittenTTS 2 runs long text in model-managed chunks; streaming is **by completed chunk**, not token-level.

**Voice cloning:** Choose **Clone a voice** and upload 5–30 seconds of a single speaker; providing a transcript avoids downloading Whisper assets for automatic transcription. Only clone voices you own or have permission to use.

**Script builder:** Preview auto-suggested direction cues for an individual scene or the full script; arrange, duplicate, reorder and remove up to 30 scenes with independent speaker selections. Optionally use the same cloned reference throughout a script. Export individual scene WAVs and a merged script WAV (joined by configurable silence gaps).

**Voices:** Browse and search all 47 KittenTTS 2 voices, including nine non-English voice profiles; switching to an ONNX model shows only its 8 supported voices. For non-English text, uncheck **Normalize English text** as the normalizer is English-focused.

**Generation history:** Browse local generated recordings, play and download WAVs, reuse their source text or delete selected recordings.

**Settings:** KittenTTS 2 weight selection (`emb4`, `packed`, `full`), decoder selection (`default`, `student_w4`), CPU/CUDA/automatic device selection, temperature, top-K/top-P/min-P, random seed, max per-chunk token budget, repetition and run penalties, chunk sizing, reference prompt toggle and beta emotion conditioning. Lightweight legacy Mini/Micro/Nano ONNX models have an actual speech-speed control but no cloning/expressive settings.

## Where files live

| Asset | Location |
|---|---|
| Installed Python libraries | `.venv\` (studio's own venv) |
| Saved WAV recordings | `data\outputs\` |
| Voice-cloning uploads | `data\references\` |
| Audio chunk previews | `data\chunks\` |
| History database | `data\studio.sqlite3` |
| HF token (optional) | Windows `HF_TOKEN` environment variable or untracked local `.env` file |
| Hugging Face weights | Standard user HF cache, shared across venvs |
| Editor drafts | Browser localStorage |

Python packages, cached weights, WAV files, private credentials and the database are **not included** in the downloadable ZIP. Only `.env.example` ships, with a blank token.

## Command-line startup

From PowerShell inside the extracted folder after installation:

```powershell
$env:PYTHONUTF8='1'
$env:HF_HUB_OFFLINE='0'
.\.venv\Scripts\python.exe -X utf8 server.py
```

The launcher is preferred because it keeps the independent environment isolated, sets download timeouts, and configures Windows encoding correctly. It accepts the standard `HF_TOKEN` environment variable.

## Security and technical notes

The server binds to `127.0.0.1` by default and checks browser origins for state-changing requests. Keep it local unless you separately configure authentication and a trusted reverse proxy. Private text/voice data stays in the local app; the underlying third-party libraries make requests to download model assets when online. The Studio does not store or display the token. If you elect to use `.env`, that file contains plain text and must be kept private. The `HF_TOKEN` value is read by Hugging Face libraries for Hub requests; the UI exposes only whether credentials were detected, not whether a remote login was verified. KittenTTS software and model weights have separate licenses; check each model's licensing before commercial use.

First launch needs a few GB of disk space and enough RAM/VRAM for the selected model. Actual audio synthesis must be verified on your Windows hardware: the included automated tests exercise app logic with a fake audio model and browser interactions, not inference on an NVIDIA card.

### Moving your previous recordings

If you used the earlier Kitten Studio interface and want to keep its recordings, close both versions, then copy the old `kitten-studio\data\studio.sqlite3`, `kitten-studio\data\outputs\` and `kitten-studio\data\references\` into this version's `data\` directory. Don't copy the old `.venv`; the new application uses its own environment. Keep a backup of your old `data` directory until you've checked your library.

## Fix for missing FastAPI or other imports

If startup previously failed with `ModuleNotFoundError: No module named 'fastapi'`, you had a private `.venv` but the installation of its packages was incomplete. **Run `REPAIR_WINDOWS.bat` once**, or just start using the updated `RUN_WINDOWS.bat` to let it repair automatically. Do not move or copy the old KittenTTS `.venv`.

For a manual repair from PowerShell in the extracted studio folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 verify_install.py
```

If pip reports a network error, try again after restoring connectivity. Do not delete the existing environment or model cache.


## v2.3 — CUDA-safe startup (Windows)

- Fixed `AssertionError: Torch not compiled with CUDA enabled` when the UI requested CUDA but the **Studio private environment** has CPU-only PyTorch. Before loading any model the server probes `torch.version.cuda` and `torch.cuda.is_available()` (or ONNX's CUDA provider) and automatically uses CPU if the requested accelerator is unavailable. The job and UI display the reason for falling back, rather than crashing.
- For optional NVIDIA acceleration, close Studio and run `INSTALL_NVIDIA_GPU_WINDOWS.bat`. It uses matching official CUDA 12.8 wheels for torch **2.10.0** and torchaudio **2.10.0**. This is a large additional download; it requires a compatible NVIDIA card/driver. If you only need CPU, do nothing.
- Voice cloning without manually supplied reference text lazily downloads **Whisper large-v3** (roughly 3 GB). The Whisper warnings in the terminal are from Transformers, and do not necessarily mean generation failed. Enter the exact text spoken in your reference clip to skip automatic transcription, and its substantial download.
- v2.2's `HF_TOKEN`/`.env` handling and Windows Selector event loop remain included. The old local browser socket reset warning is distinct from the CUDA crash.

### Upgrade from v2.1/v2.2

Close Studio, unpack the new release in the existing installation folder and replace app files, but keep `.venv`, `data`, and `.env`. Then run `RUN_WINDOWS.bat`. No token needs to be entered again.

## v2.6 — Generation diagnostics and optional repetition protection

- After generating, Studio displays *model setup*, *synthesis*, *actual audio duration*, and *speed relative to real-time*. Warm runs should show **Reused model**. This distinguishes first-load overhead from model generation. The current job metrics live in memory; existing history WAVs and the database are untouched.
- Optional Repeat protection: Off (upstream KittenTTS 2 defaults, unchanged), Gentle, and Stronger. These strengthen only the model's repetition-related sampling options and **may change the generated speech**; no setting can guarantee no duplicated words. Manual Advanced repetition values take precedence.
- On CPU **and CUDA**, PyTorch CPU orchestration threads are capped at eight by default (or fewer physical/logical threads if available), adjustable with `KITTEN_CPU_THREADS`. No model weights, sampling precision, waveform format, or decoder are changed. This may help on high-core laptops; actual speed must be benchmarked on Windows.
- KittenTTS 2 intentionally splits longer text into chunks and combines them. The studio does not duplicate generation for streaming; enabling chunk previews may incur extra disk writes, so leave that option unchecked when optimizing throughput.
- If speech repeats, use the **Stable** preset, try **Gentle** protection, ensure a fresh seed (no fixed seed), and regenerate. If it persists, test with chunk previews off and share both text and WAV. Avoid automatic audio deduplication: some intentional repetitions are meaningful.

## v2.7 — Sentence editor: replace only what you need

**How to use:**

1. Open **History** and click **Edit speech** beside an existing recording. The new **Edit audio** workspace displays the waveform and saved transcript.
2. Click **Detect sentences**. Studio recognizes spoken words with an **optional free, local** `faster-whisper` CPU model (`base`, multilingual), matches words against the *original source script*, and proposes start/end timestamps. Word alignment is not sample-perfect; review the boundaries. You can change the Start/End fields (seconds) and play just that selected section.
3. Select a transcript sentence, edit just its text (including expression cues if desired), then choose **Generate replacement preview**. KittenTTS loads the original model, voice, and generation settings when available; a new preview WAV is generated without changing the original file. The main model is reused if already loaded.
4. After auditioning the preview, click **Replace selected sentence**. Studio crossfades a short region (~24ms per join), and saves **a new recording** in History. The original WAV and all other sentences are preserved. If replacement duration differs, downstream audio shifts in time (ripple edit). Re-run alignment on the new recording for a subsequent edit.

**One-time optional alignment installation:** Close Studio and run **`INSTALL_ALIGNMENT_WINDOWS.bat`**. This installs `faster-whisper` in Studio's *existing independent `.venv`*, without changing your KittenTTS/PyTorch installation. On first detection it downloads a **small base multilingual Whisper model** from Hugging Face and caches it inside `data\alignment_models`. No transcription service or API fee is involved. Detection runs on CPU to avoid conflicting with GPU synthesis. If you do not install it, the editor can still offer **clearly labeled estimated boundaries** based on text position and local waveform energy — these are much less accurate and must be adjusted manually.

**Accuracy limitations:** ASR word timestamps are estimates, particularly for dramatic pauses, emotion/event tags, non-English narration, skipped text and repeated phrases. Please always audition selected regions before replacement. This feature does **not** provide phoneme-accurate forced alignment or pitch-preserving time-fitting. The selected source boundaries are entirely replaced; if they cut through another word, that word may sound clipped. Only WAVs generated in Kitten Studio and present in History are supported; imported external audio is not yet supported.

**Older generations:** Files created before v2.7 lack the saved generation-options metadata. Those WAVs remain editable, but reproduction of their exact voice/settings may differ; Studio shows a warning. Older cloned references may be unavailable, and those require creating a new recording with a valid reference. A merged multi-voice script is not yet edited in place: edit its separately generated **segment** WAVs, then rebuild the combined script. This avoids applying the wrong voice to a sentence.

**Persistence:** Adds a `recording_meta` table to the *existing* SQLite History database. There is no migration that deletes or rewrites prior recordings. Replacement audio lives in `data\outputs`, temporary previews in `data\previews`, and all versions are visible through the existing History view. Do not delete your `data` folder during upgrades.

**Windows upgrade:** Exit Kitten Studio, unpack v2.8 **over the current install** (same `server.py` directory), preserving `.venv`, `data`, `.env`, then run `RUN_WINDOWS.bat`. For reliable automatic word timestamps run `INSTALL_ALIGNMENT_WINDOWS.bat` once. If it fails due to Hugging Face connectivity, you can retry later without losing saved audio.

**Implementation & verification:** Regression tests cover transcript splitting, word-to-text matching, timing fallback, smooth non-destructive splicing, full preview/apply, immutable originals, and record isolation. Browser interactions are tested with a mocked API; actual inference on Windows should be verified with your own GPU and recordings. This is an original Kitten Studio feature, not a built-in KittenTTS API.

"""Kitten Studio — private, self-contained local interface for KittenML.

Run inside this project’s private venv with UTF-8 mode enabled.
The application binds to loopback by default and never sends text/audio to our own servers.
Model downloads, when enabled, use the official Hugging Face client in KittenML.
"""
from __future__ import annotations

# Some dependencies create asyncio loops themselves. Set the Windows loop policy
# before importing the web server or Hugging Face, not only in __main__.
import os
if os.name == "nt":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import concurrent.futures
from functools import lru_cache
import gc
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from model_backends import KokoroEngine, IndicParlerEngine, KOKORO_VOICES, INDIC_VOICES

import numpy as np
import soundfile as sf
from sentence_editor import (split_sentences, align_words, provisional_alignment,
                             waveform_peaks, replace_region, load_mono, plain_text)
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
# Standard Hugging Face credentials: inherited HF_TOKEN takes precedence; .env is
# an optional local convenience. Load before KittenTTS / huggingface_hub imports.
load_dotenv(dotenv_path=ROOT / ".env", override=False)
DATA = ROOT / "data"
OUTPUTS = DATA / "outputs"
REFS = DATA / "references"
CHUNKS = DATA / "chunks"
PREVIEWS = DATA / "previews"
for folder in (OUTPUTS, REFS, CHUNKS, PREVIEWS):
    folder.mkdir(parents=True, exist_ok=True)
DB = DATA / "studio.sqlite3"

MODELS = {
    "hexgrad/Kokoro-82M": {"label": "Kokoro 82M · English / Hindi", "family": "kokoro", "size": "82M · fast English/Hindi · optional install · Apache 2.0"},
    "ai4bharat/indic-parler-tts": {"label": "Indic Parler · Hindi / Nepali", "family": "indic", "size": "Hindi & Nepali · voice descriptions · HF gated access · Apache 2.0"},
    "KittenML/kitten-tts-2": {"label": "KittenTTS 2", "family": "v2", "size": "1.7B · 47 voices · cloning + expression"},
    "KittenML/kitten-tts-mini-0.8": {"label": "Mini", "family": "onnx", "size": "80M · CPU-friendly"},
    "KittenML/kitten-tts-micro-0.8": {"label": "Micro", "family": "onnx", "size": "40M · CPU-friendly"},
    "KittenML/kitten-tts-nano-0.8": {"label": "Nano", "family": "onnx", "size": "15M · CPU-friendly"},
    "KittenML/kitten-tts-nano-0.8-int8": {"label": "Nano INT8", "family": "onnx", "size": "15M · smallest download"},
}

VOICE_PROFILES = {**{v: ("Kokoro natural voice", lang) for v, lang in KOKORO_VOICES.items()},
    **{v: ("Indic Parler speaker", lang) for v, lang in INDIC_VOICES.items()},
    "Bella": ("Bright and friendly", "English"), "Jasper": ("Easygoing and warm", "English"),
    "Luna": ("Soft and clear", "English"), "Bruno": ("Confident narrator", "English"),
    "Rosie": ("Cheerful and light", "English"), "Hugo": ("Steady and natural", "English"),
    "Kiki": ("Animated and lively", "English"), "Leo": ("Relaxed and natural", "English"),
    "Matthew": ("Exhausted mechanic", "English"), "Elliot": ("Grieving young voice", "English"),
    "Willow": ("Hushed young voice", "English"), "Dolores": ("Southern elderly voice", "English"),
    "Victor": ("Controlled fury, older", "English"), "Dante": ("Playful and smooth", "English"),
    "Alfred": ("Tender older voice", "English"), "Saoirse": ("Joyful Irish voice", "English"),
    "Claire": ("Playful professional", "English"), "Raven": ("Controlled fury, young", "English"),
    "Marcus": ("Smooth radio DJ", "English"), "Herbert": ("Wise elderly professor", "English"),
    "Diana": ("Stern military officer", "English"), "Laurence": ("Dramatic stage actor", "English"),
    "Maeve": ("Cozy warm storyteller", "English"), "Walter": ("Warm grandfather", "English"),
    "Edith": ("Soft elderly grandmother", "English"), "Miles": ("Gentle librarian", "English"),
    "Grace": ("Soothing nurse", "English"), "Reginald": ("Distinguished diplomat", "English"),
    "Iris": ("Hushed museum guide", "English"), "Frank": ("Gravelly war veteran", "English"),
    "Serena": ("Gentle yoga instructor", "English"), "Julian": ("Dreamy, soft poet", "English"),
    "Eleanor": ("Somber historian", "English"), "Otis": ("Rumbling blues musician", "English"),
    "Vincent": ("Hushed museum guide", "English"), "Martha": ("Weathered radio journalist", "English"),
    "Sable": ("Hushed conspirator", "English"), "Victoria": ("Regal narrator", "English"),
    "Arabic": ("Native-language reference", "Arabic"), "Chinese": ("Native-language reference", "Chinese"),
    "French": ("Native-language reference", "French"), "German": ("Native-language reference", "German"),
    "Hindi": ("Native-language reference", "Hindi"), "Italian": ("Native-language reference", "Italian"),
    "Portuguese": ("Native-language reference", "Portuguese"), "Russian": ("Native-language reference", "Russian"),
    "Spanish": ("Native-language reference", "Spanish"),
}
EMOTIONS = ["angry", "contemplative", "excited", "joyful", "mundane", "nervous", "sad", "stern", "surprised", "tender"]
EVENTS = ["gasp", "giggle", "growl", "gulp", "laugh", "pause", "scoff", "sigh", "sob", "um"]
MAX_UPLOAD = 32 * 1024 * 1024
MAX_SCRIPT_CHARS = 25000


def db_connect():
    conn = sqlite3.connect(DB, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS recordings (
            id TEXT PRIMARY KEY, created TEXT NOT NULL, title TEXT NOT NULL,
            text TEXT NOT NULL, model TEXT NOT NULL, voice TEXT NOT NULL,
            duration REAL NOT NULL, sample_rate INTEGER NOT NULL,
            filename TEXT NOT NULL, kind TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS recording_meta (
            recording_id TEXT PRIMARY KEY, options TEXT NOT NULL DEFAULT '{}',
            parent_id TEXT, alignment_json TEXT, method TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS voice_refs (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, original_name TEXT NOT NULL,
            created TEXT NOT NULL)""")


init_db()


# Record only reproducible TTS settings, never credentials or arbitrary input.
META_KEYS = {'model', 'device', 'weights', 'decoder', 'voice', 'preset',
             'normalize', 'streaming', 'speed', 'max_new_tokens',
             'use_reference_prompt', 'temperature', 'top_k', 'top_p', 'min_p',
             'advanced', 'reference_id', 'reference_text', 'loop_protection',
             'segments', 'segment_gap', 'description'}


def recording_meta(rid: str) -> dict:
    with db_connect() as conn:
        row = conn.execute('SELECT * FROM recording_meta WHERE recording_id=?', (rid,)).fetchone()
    if not row:
        return {'options': {}, 'alignment': None, 'parent_id': None, 'method': None}
    try:
        options = json.loads(row['options'])
        alignment = json.loads(row['alignment_json']) if row['alignment_json'] else None
    except (ValueError, TypeError):
        options, alignment = {}, None
    return {'options': options, 'alignment': alignment,
            'parent_id': row['parent_id'], 'method': row['method']}


def save_recording_meta(rid: str, options: dict | None = None,
                        parent_id: str | None = None, alignment=None, method=None):
    serialized = json.dumps({k: v for k, v in (options or {}).items() if k in META_KEYS}, ensure_ascii=False)
    with db_connect() as conn:
        conn.execute("""INSERT OR REPLACE INTO recording_meta
            (recording_id,options,parent_id,alignment_json,method) VALUES (?,?,?,?,?)""",
            (rid, serialized, parent_id, json.dumps(alignment, ensure_ascii=False) if alignment is not None else None, method))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_title(text: str, limit=52):
    candidate = re.sub(r"\[[^\]]+\]|<[^>]+>|[()]", "", text)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    return candidate[:limit] or "Untitled narration"


def get_bool(value, default=False):
    return default if value is None else bool(value)


def ranged(value, low, high, name, cast=float):
    try:
        v = cast(value)
        if not np.isfinite(v) or not low <= v <= high:
            raise ValueError
        return v
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{name} must be between {low} and {high}") from None


def model_choice(payload: dict):
    model_id = payload.get("model", "KittenML/kitten-tts-2")
    if model_id not in MODELS:
        raise ValueError("Unknown model. Choose a model from the supported list.")
    family = MODELS[model_id]["family"]
    device = payload.get("device", "auto")
    if device not in ("auto", "cpu", "cuda"):
        raise ValueError("Device must be auto, cpu or cuda")
    weights = payload.get("weights", "emb4") if family == "v2" else None
    decoder = payload.get("decoder", "default") if family == "v2" else None
    if family == "v2" and weights not in ("emb4", "packed", "full"):
        raise ValueError("Unknown weights. Choose emb4, packed or full.")
    if family == "v2" and decoder not in ("default", "student_w4"):
        raise ValueError("Unknown decoder")
    return (model_id, device, weights, decoder)


def generation_options(payload: dict, family: str):
    if family == "kokoro":
        return {}
    if family == "indic":
        description = str(payload.get("description") or "").strip()
        if len(description) > 500:
            raise ValueError("Voice description must be 500 characters or fewer")
        return {"description": description} if description else {}
    if family == "onnx":
        return {"speed": ranged(payload.get("speed", 1.0), 0.5, 2.0, "Speech speed")}
    preset = payload.get("preset", "stable")
    if preset not in ("stable", "expressive"):
        raise ValueError("Preset must be stable or expressive")
    opts = {
        "preset": preset,
        "max_new_tokens": ranged(payload.get("max_new_tokens", 1000), 100, 5000, "Max tokens", int),
        "normalize": get_bool(payload.get("normalize"), True),
    }
    pref = payload.get("use_reference_prompt", "auto")
    if pref not in ("auto", "on", "off"):
        raise ValueError("Unknown reference-prompt mode")
    if pref != "auto":
        opts["use_reference_prompt"] = pref == "on"
    limits = {
        "temperature": (0.1, 2.0, float), "top_k": (0, 500, int),
        "top_p": (0.01, 1.0, float), "min_p": (0.0, 1.0, float),
    }
    for key, (lo, hi, cast) in limits.items():
        val = payload.get(key)
        if val is not None and str(val).strip() != "":
            opts[key] = ranged(val, lo, hi, key, cast)
    advanced = {}
    adv = payload.get("advanced") or {}
    if not isinstance(adv, dict):
        raise ValueError("Invalid advanced settings")
    adv_limits = {
        "seed": (0, 2**32 - 1, int),
        "repetition_penalty": (0.1, 5.0, float),
        "repetition_window": (1, 10000, int),
        "token_run_penalty": (0.1, 5.0, float),
        "token_run_grace": (1, 1000, int),
        "chunk_chars": (80, 3000, int),
        "chunk_min_chars": (20, 3000, int),
        "chunk_gap_s": (0, 3.0, float),
    }
    for key, (lo, hi, cast) in adv_limits.items():
        val = adv.get(key)
        if val is not None and str(val).strip() != "":
            advanced[key] = ranged(val, lo, hi, key, cast)
    if "use_emotion" in adv and adv["use_emotion"] in (True, False):
        advanced["use_emotion"] = adv["use_emotion"]
    # Conservative, opt-in anti-loop modes. KittenTTS 2 already has guards;
    # only strengthen the repetition-related knobs, never alter decoder,
    # weights, voice, emotion tags, or temperature. Advanced manual settings
    # always take precedence over these suggestions.
    loop_mode = payload.get("loop_protection", "off")
    if loop_mode not in ("off", "gentle", "strong"):
        raise ValueError("Loop protection must be Off, Gentle or Strong")
    protection = {
        "gentle": {"repetition_penalty": 1.15, "token_run_penalty": 1.45, "token_run_grace": 8},
        "strong": {"repetition_penalty": 1.25, "token_run_penalty": 1.7, "token_run_grace": 6},
    }
    for k, v in protection.get(loop_mode, {}).items():
        advanced.setdefault(k, v)
    if advanced:
        opts["advanced"] = advanced
    return opts


def as_audio(samples):
    data = np.asarray(samples, dtype=np.float32).squeeze()
    if data.ndim != 1 or not data.size or not np.isfinite(data).all():
        raise RuntimeError("Generation produced invalid audio")
    return data


def cached_model_snapshot(repo_id: str, weights: str | None, decoder: str | None) -> str | None:
    """Prefer complete local KittenTTS 2 weights before making any HF network calls.

    Virtual environments are isolated, but Hugging Face's user cache is shared.
    A partial cache does NOT count as a valid local model: normal online download
    is then allowed to complete the missing files.
    """
    if repo_id != "KittenML/kitten-tts-2":
        return None
    try:
        from huggingface_hub import snapshot_download
        root = Path(snapshot_download(repo_id=repo_id, local_files_only=True))
        config = json.loads((root / "config.json").read_text(encoding="utf-8"))
        lm_dir = config.get("lm_dir", "lm")
        required = ["config.json", f"{lm_dir}/config.json",
                    config.get("voices", "voices/voices.json"),
                    config.get("speaker_embedding", "speaker/model.safetensors")]
        if weights == "emb4":
            required.append(config["lm_emb4"])
        elif weights == "packed":
            required.append(config["lm_packed"])
        else:
            # The full uncompressed LM has separate files; do not mistake the
            # cached emb4/packed model for a complete full-precision checkpoint.
            return None
        decoder_path = config.get("decoders", {}).get(decoder or config.get("default_decoder", "default"))
        if decoder_path:
            required.append(decoder_path)
        if not all((root / path).is_file() for path in required):
            return None
        voices = json.loads((root / config.get("voices", "voices/voices.json")).read_text(encoding="utf-8"))
        voice_dir = (root / config.get("voices", "voices/voices.json")).parent
        if not all((voice_dir / spec[part]).is_file() for spec in voices.values() for part in ("reference", "artifacts")):
            return None
        return str(root)
    except (OSError, KeyError, ValueError, TypeError, ImportError):
        return None


@lru_cache(maxsize=1)
def compute_capabilities():
    """Probe the *studio's* PyTorch and ONNX runtimes, not system CUDA tools.

    An NVIDIA card/driver does not imply that pip installed a CUDA-enabled torch.
    Never send KittenTTS a CUDA device unless the actual backend can use it.
    """
    torch_cuda = False
    torch_cuda_build = None
    torch_version = None
    torch_error = None
    try:
        import torch
        torch_version = str(torch.__version__)
        torch_cuda_build = getattr(torch.version, 'cuda', None)
        torch_cuda = bool(torch_cuda_build and torch.cuda.is_available())
    except Exception as exc:
        torch_error = f"{type(exc).__name__}: {exc}"
    onnx_cuda = False
    providers = []
    try:
        import onnxruntime as ort
        providers = list(ort.get_available_providers())
        onnx_cuda = 'CUDAExecutionProvider' in providers
    except Exception:
        pass
    return {
        'torch_cuda': torch_cuda,
        'torch_cuda_build': torch_cuda_build,
        'torch_version': torch_version,
        'onnx_cuda': onnx_cuda,
        'onnx_providers': providers,
        'torch_error': torch_error,
    }


def configure_cpu_threads(device: str, family: str):
    """Bound CPU worker threads for PyTorch on CPU *and* GPU inference.

    A GPU model still uses CPU for text, tokenizer and audio orchestration;
    large laptop CPUs can oversubscribe the scheduler. No change to sampling,
    model weights or precision. KITTEN_CPU_THREADS overrides the heuristic.
    """
    if family != "v2":
        return
    try:
        import torch
        available = max(1, os.cpu_count() or 1)
        requested = os.getenv("KITTEN_CPU_THREADS", "8").strip()
        count = min(available, max(1, min(64, int(requested))))
        torch.set_num_threads(count)
    except (ImportError, RuntimeError, ValueError, TypeError):
        pass


def cached_whisper_snapshot() -> str | None:
    """Avoid Hub metadata calls when Whisper-large-v3 was already downloaded.

    Only switch to local path if all core assets exist. The same checkpoint is used;
    generation quality is unchanged. Missing files keep the usual online behavior.
    """
    try:
        from huggingface_hub import snapshot_download
        directory = Path(snapshot_download(repo_id="openai/whisper-large-v3", local_files_only=True))
        keys = ["config.json", "tokenizer.json", "preprocessor_config.json",
                "generation_config.json", "model.safetensors"]
        if all((directory / name).is_file() for name in keys):
            return str(directory)
    except (OSError, ValueError, ImportError):
        pass
    return None


def reference_row(rid: str):
    """Return a valid saved reference without exposing arbitrary disk paths."""
    if not isinstance(rid, str) or not re.fullmatch(r"[a-f0-9]{32}", rid):
        return None
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM voice_refs WHERE id=?", (rid,)).fetchone()
    if not row:
        return None
    path = REFS / row["filename"]
    return dict(row) if path.is_file() else None


def validate_references(payload: dict) -> None:
    """Fail *before* downloading/loading a multi-GB model if reference is stale."""
    parts = payload.get("segments")
    if parts is None:
        parts = [payload]
    if not isinstance(parts, list):
        return
    needs_reference = any(isinstance(part, dict) and
                          (part.get("voice") == "__clone__" or
                           (part.get("voice") is None and payload.get("voice") == "__clone__"))
                          for part in parts)
    if not needs_reference:
        return
    rid = payload.get("reference_id")
    if not rid or reference_row(rid) is None:
        raise ValueError("Your saved voice reference is missing or no longer available. "
                         "Select an existing recording under Clone a voice or upload a new one.")


def resolve_device(family, requested, capabilities=None):
    """Return a usable device and a plain-language reason for any fallback."""
    caps = compute_capabilities() if capabilities is None else capabilities
    supported = caps['torch_cuda'] if family != 'onnx' else caps['onnx_cuda']
    if requested == 'cpu':
        return 'cpu', None
    if supported:
        return 'cuda', None
    if requested == 'cuda':
        if family != 'onnx':
            reason = ('CUDA was requested but PyTorch in this Studio environment cannot use it. '
                      'Using CPU instead. For NVIDIA support, install compatible CUDA-enabled torch '
                      'and torchaudio into the Studio environment.')
        else:
            reason = ('ONNX CUDA was requested, but CUDAExecutionProvider is not installed or available. '
                      'Using CPU instead. ONNX CUDA requires its own compatible onnxruntime-gpu setup.')
        return 'cpu', reason
    return 'cpu', None


def synchronize_cuda(device: str | None):
    """Measure elapsed GPU work accurately, without changing inference."""
    if device != "cuda":
        return
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except (ImportError, RuntimeError, AssertionError):
        pass


class StudioEngine:
    """Single serial worker: avoid simultaneous loads/generations on shared GPU."""

    def __init__(self):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="kitten")
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.futures = {}
        self.model = None
        self.current_key = None
        self.loading = False
        self.factory = None  # test injection, otherwise official KittenTTS class

    def new_job(self, kind, task, payload):
        job_id = uuid.uuid4().hex
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id, "kind": kind, "status": "queued", "message": "Waiting for engine…",
                "created": now(), "result_id": None, "result_ids": [], "chunks": [],
                "completed": 0, "total": 0, "error": None, "warning": None, "device": None,
                "timings": None, "preview_url": None, "preview_data": None,
            }
            self.futures[job_id] = self.executor.submit(self._run, job_id, task, payload)
        return job_id

    def update(self, job_id, **fields):
        with self.lock:
            self.jobs[job_id].update(fields)

    def _run(self, job_id, task, payload):
        with self.lock:
            if self.jobs[job_id]["status"] == "cancelled":
                return
        self.update(job_id, status="running", message="Preparing model…")
        try:
            if task == "load":
                self.load(model_choice(payload), job_id)
                self.update(job_id, status="done", message="Model ready")
            elif task == "generate":
                validate_references(payload)
                self.generate(payload, job_id)
                self.update(job_id, status="done", message="Generation complete")
            elif task == "align":
                self.align_recording(payload['record_id'], job_id)
                self.update(job_id, status="done", message="Sentence alignment ready")
            elif task == "preview":
                self.preview_replacement(payload, job_id)
                self.update(job_id, status="done", message="Preview ready; original unchanged")
            elif task == "apply":
                self.apply_replacement(payload, job_id)
                self.update(job_id, status="done", message="New recording saved; original preserved")
        except Exception as exc:
            # Expected input errors belong in the job UI, not a huge traceback.
            if not isinstance(exc, ValueError):
                traceback.print_exc()
            detail = str(exc)
            if ("couldn't connect to 'https://huggingface.co'" in detail.lower()
                    or "offline mode" in detail.lower() or "local_files_only" in detail.lower()):
                detail = ("Required model files are not fully cached. Run python studio.py "
                          "(online by default), then select Load model again. "
                          "If Hugging Face keeps disconnecting, try another connection or the "
                          "HF_TOKEN in .env. Original error: " + detail[:500])
            elif "Torch not compiled with CUDA enabled" in detail or "CUDA error" in detail:
                detail = ("PyTorch CUDA is unavailable in Studio's private environment. "
                          "Select CPU or Auto, or install matching CUDA PyTorch. " + detail[:500])
            elif "WinError 10054" in detail or "Server disconnected" in detail:
                detail = ("The Hugging Face connection was reset. Your installed Python environment "
                          "is fine. Retry the model load, or try another network. " + detail[:500])
            self.update(job_id, status="error", error=f"{type(exc).__name__}: {detail}", message="Generation failed" if task == "generate" else "Model load failed")

    def snapshot(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise HTTPException(status_code=404, detail="Job not found")
            return dict(self.jobs[job_id], chunks=list(self.jobs[job_id]["chunks"]), result_ids=list(self.jobs[job_id]["result_ids"]))

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            if job["status"] == "queued" and self.futures[job_id].cancel():
                job.update(status="cancelled", message="Removed from queue")
                return True
            return False

    def load(self, key, job_id):
        if self.current_key == key and self.model is not None:
            self.update(job_id, device=str(getattr(self.model, "device", "auto")),
                        message="Reusing loaded model (no reload).")
            return self.model
        model_id, requested_device, weights, decoder = key
        family = MODELS[model_id]["family"]
        device, warning = resolve_device(family, requested_device)
        self.update(job_id, message=f"Loading {MODELS[model_id]['label']} on {device.upper()}…",
                    warning=warning, device=device)
        if warning:
            print("[Kitten Studio] " + warning, flush=True)
        if self.model is not None:
            self.model = None
            self.current_key = None
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
        configure_cpu_threads(device, family)
        if self.factory is None and family in ("v2", "onnx"):
            from kittenml import KittenTTS
            self.factory = KittenTTS
        if family in ("kokoro", "indic"):
            model = (KokoroEngine if family == "kokoro" else IndicParlerEngine)(device=device)
            self.model = model
            self.current_key = key
            return model
        if family == "v2":
            kwargs = {"weights": weights, "decoder": decoder}
            kwargs["device"] = device
            # Pass the token explicitly for KittenTTS 2 snapshot requests in
            # addition to the env variable used by Hugging Face subcomponents.
            hf_token = os.getenv("HF_TOKEN", "").strip()
            if hf_token:
                kwargs["hf_token"] = hf_token
        else:
            kwargs = {}
            kwargs["backend"] = device
        local_snapshot = cached_model_snapshot(model_id, weights, decoder)
        if local_snapshot and self.factory is not None:
            # For actual KittenTTS, local snapshot loading bypasses Hub
            # metadata requests and survives intermittent HF connectivity.
            self.update(job_id, message="Loading model from local cache…")
            try:
                model = self.factory(local_snapshot, **kwargs)
            except (OSError, RuntimeError, ValueError) as cached_error:
                if os.getenv("HF_HUB_OFFLINE", "0") == "1":
                    raise
                self.update(job_id, message="Cached model incomplete; fetching missing assets…")
                model = self.factory(model_id, **kwargs)
        else:
            model = self.factory(model_id, **kwargs)
        if family == "v2" and getattr(model, "transcriber", None) is not None:
            whisper_path = cached_whisper_snapshot()
            if whisper_path:
                model.transcriber.model_name = whisper_path
        self.model = model
        self.current_key = key
        self.update(job_id, message=f"Model loaded on {device.upper()}." + (" CPU fallback active." if warning else ""))
        return model

    def store_audio(self, audio, sample_rate, text, model_id, voice, kind, meta=None, parent_id=None):
        rid = uuid.uuid4().hex
        filename = f"{rid}.wav"
        dest = OUTPUTS / filename
        sf.write(dest, as_audio(audio), sample_rate, subtype="PCM_16")
        duration = len(audio) / sample_rate
        with db_connect() as conn:
            conn.execute("""INSERT INTO recordings
                (id, created, title, text, model, voice, duration, sample_rate, filename, kind)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rid, now(), safe_title(text), text, model_id, voice, duration, sample_rate, filename, kind))
        if meta is not None or parent_id is not None:
            save_recording_meta(rid, meta or {}, parent_id)
        return rid

    def reference_path(self, rid):
        row = reference_row(rid)
        if row is None:
            raise ValueError("Saved reference recording is missing. Choose another recording or upload it again.")
        return str(REFS / row["filename"])

    def generate(self, payload, job_id):
        key = model_choice(payload)
        model_id = key[0]
        family = MODELS[model_id]["family"]
        validate_references(payload)
        opts = generation_options(payload, family)
        reused_model = self.current_key == key and self.model is not None
        load_start = time.perf_counter()
        model = self.load(key, job_id)
        model_setup = time.perf_counter() - load_start
        actual_device = str(getattr(model, "device", self.jobs[job_id].get("device")))
        sample_rate = int(getattr(model, "sample_rate", 24000))
        synthesis_seconds = 0.0
        streaming = bool(payload.get("streaming", False)) and family == "v2"
        segments = payload.get("segments")
        if segments is None:
            segments = [{"text": payload.get("text", ""), "voice": payload.get("voice", "Bruno")}]
            is_batch = False
        else:
            is_batch = True
        if not isinstance(segments, list) or not 1 <= len(segments) <= 30:
            raise ValueError("Provide 1–30 script segments")
        if sum(len(str(s.get("text", ""))) for s in segments if isinstance(s, dict)) > MAX_SCRIPT_CHARS:
            raise ValueError(f"Keep the total script under {MAX_SCRIPT_CHARS:,} characters")
        self.update(job_id, total=len(segments), completed=0)
        all_audio = []
        captions = []
        speakers = []
        for i, segment in enumerate(segments):
            if not isinstance(segment, dict):
                raise ValueError("Invalid segment")
            text = str(segment.get("text", "")).strip()
            if not text:
                raise ValueError(f"Segment {i+1} has no text")
            self.update(job_id, message=f"Synthesizing {i+1} of {len(segments)}…")
            voice = str(segment.get("voice") or payload.get("voice") or "Bruno")
            kwargs = dict(opts)
            if voice == "__clone__":
                if family != "v2":
                    raise ValueError("Voice cloning is only available for KittenTTS 2")
                rid = payload.get("reference_id")
                if not isinstance(rid, str):
                    raise ValueError("Upload a reference recording before cloning")
                kwargs["reference"] = self.reference_path(rid)
                transcript = str(payload.get("reference_text") or "").strip()
                if transcript:
                    kwargs["reference_text"] = transcript
                display_voice = "Cloned voice"
            else:
                if voice not in list(getattr(model, "available_voices", [])):
                    raise ValueError(f"Voice {voice!r} is not available in this model")
                kwargs["voice"] = voice
                display_voice = voice
            synchronize_cuda(actual_device)
            synth_start = time.perf_counter()
            if streaming and not is_batch:
                wavs = []
                for index, chunk in enumerate(model.generate_stream(text, **kwargs)):
                    wave = as_audio(chunk)
                    wavs.append(wave)
                    out_dir = CHUNKS / job_id
                    out_dir.mkdir(exist_ok=True)
                    out = out_dir / f"chunk_{index:03}.wav"
                    sf.write(out, wave, sample_rate, subtype="PCM_16")
                    with self.lock:
                        self.jobs[job_id]["chunks"].append({"index": index, "duration": round(len(wave) / sample_rate, 2), "url": f"/api/chunks/{job_id}/{index}"})
                    self.update(job_id, message=f"Audio chunk {index+1} ready · continuing…")
                if not wavs:
                    raise RuntimeError("Model produced no audio chunks")
                # Use KittenTTS 2's seam processing for the final audio.
                if hasattr(model, "_join"):
                    adv = kwargs.get("advanced", {})
                    joined = model._join(wavs, gap_s=adv.get("chunk_gap_s", 0.16))
                else:
                    joined = np.concatenate(wavs)
                audio = as_audio(joined)
            else:
                audio = as_audio(model.generate(text, **kwargs))
            synchronize_cuda(actual_device)
            synthesis_seconds += time.perf_counter() - synth_start
            all_audio.append(audio)
            captions.append(text)
            speakers.append(display_voice)
            if is_batch:
                segment_meta = {k: v for k, v in payload.items() if k in META_KEYS and k != 'segments'}
                segment_meta['voice'] = voice
                rid = self.store_audio(audio, sample_rate, text, model_id, display_voice, "segment", meta=segment_meta)
                with self.lock:
                    self.jobs[job_id]["result_ids"].append(rid)
            self.update(job_id, completed=i+1)
        if is_batch:
            gap = float(payload.get("segment_gap", 0.4))
            gap = ranged(gap, 0, 3, "Segment gap")
            silence = np.zeros(int(sample_rate * gap), dtype=np.float32)
            portions = []
            for i, wave in enumerate(all_audio):
                if i:
                    portions.append(silence)
                portions.append(wave)
            output_audio = np.concatenate(portions)
            kind = "script"
            voice_name = "Multiple voices" if len(set(speakers)) > 1 else speakers[0]
        else:
            output_audio = all_audio[0]
            kind = "speech"
            voice_name = speakers[0]
        generation_meta = {k: v for k, v in payload.items() if k in META_KEYS}
        rid = self.store_audio(output_audio, sample_rate, "\n\n".join(captions), model_id, voice_name, kind,
                               meta=generation_meta)
        audio_seconds = len(output_audio) / sample_rate
        timings = {
            "model_setup_s": round(model_setup, 2),
            "reused_model": reused_model,
            "synthesis_s": round(synthesis_seconds, 2),
            "audio_s": round(audio_seconds, 2),
            "rtf": round(synthesis_seconds / audio_seconds, 2) if audio_seconds else None,
            "device": actual_device,
            "streaming": streaming,
        }
        self.update(job_id, result_id=rid, timings=timings, message="Saved to local library")
        print("[Kitten Studio] Generation timing: " +
              f"model setup {timings['model_setup_s']:.2f}s, " +
              f"synthesis {timings['synthesis_s']:.2f}s, " +
              f"audio {timings['audio_s']:.2f}s, " +
              f"RTF {timings['rtf']} on {actual_device} " +
              f"(model reused={reused_model}, streaming={streaming})", flush=True)

    def align_recording(self, rid: str, job_id: str):
        item = record(rid)
        samples, sr = load_mono(OUTPUTS / item['filename'])
        duration = len(samples) / sr
        sentences = split_sentences(item['text'])
        if not sentences:
            raise ValueError('This recording has no stored transcript.')
        self.update(job_id, message='Aligning transcript to spoken words on CPU…')
        method = 'whisper-word-timestamps'
        detected = []
        try:
            from faster_whisper import WhisperModel
            # CPU alignment leaves the RTX GPU free for speech synthesis and
            # avoids exhausting 12GB VRAM by loading two speech models at once.
            # Use a small multilingual model (~145 MB) downloaded once.
            aligner = getattr(self, '_aligner', None)
            if aligner is None:
                aligner = WhisperModel('base', device='cpu', compute_type='int8',
                                       download_root=str(DATA / 'alignment_models'))
                self._aligner = aligner
            segments, _ = aligner.transcribe(str(OUTPUTS / item['filename']),
                                              word_timestamps=True, vad_filter=False,
                                              beam_size=3, condition_on_previous_text=False)
            for seg in segments:
                for w in (seg.words or []):
                    detected.append({'word': w.word, 'start': w.start, 'end': w.end})
            aligned = align_words(item['text'], detected, duration, samples, sr)
        except Exception as exc:
            # Still gives a usable editable sentence timeline when the optional
            # alignment model cannot be downloaded. Never call estimates accurate.
            method = 'estimated-no-asr'
            aligned = provisional_alignment(item['text'], duration, samples, sr)
            self.update(job_id, warning=('Speech alignment unavailable; timings are estimated. '
                        'Run INSTALL_ALIGNMENT_WINDOWS.bat and re-align for word timestamps. '
                        + str(exc)[:180]))
        if not aligned:
            raise ValueError('No sentences could be aligned.')
        old_meta = recording_meta(rid)
        save_recording_meta(rid, old_meta['options'], old_meta['parent_id'], aligned, method)
        self.update(job_id, alignment=aligned, alignment_method=method,
                    message=f'{len(aligned)} sentence ranges ready. Please review the boundaries.')

    def preview_replacement(self, payload: dict, job_id: str):
        rid = payload['record_id']
        item = record(rid)
        old = recording_meta(rid)
        sentences = old['alignment']
        index = int(payload['sentence_index'])
        if not sentences or not 0 <= index < len(sentences):
            raise ValueError('Align the recording and select a sentence first.')
        text = str(payload.get('text', '')).strip()
        if not 1 <= len(text) <= 2500:
            raise ValueError('Replacement speech must contain 1–2500 characters.')
        saved = old['options']
        if item['kind'] == 'script':
            raise ValueError('For multi-voice scripts, edit the individual segment in History.')
        voice = saved.get('voice') or item['voice']
        if voice not in VOICE_PROFILES and voice != '__clone__':
            raise ValueError('Original voice settings unavailable. Create a new recording with a built-in voice.')
        selected = {k: v for k, v in saved.items() if k in META_KEYS}
        selected['model'] = item['model']
        selected['voice'] = voice
        # Offer user-selected model compute without switching weights/decoder.
        selected['device'] = payload.get('device', saved.get('device', 'auto'))
        key = model_choice(selected)
        family = MODELS[key[0]]['family']
        if family == 'v2':
            selected.setdefault('preset', 'stable')
        requested_preset=payload.get('preset')
        if requested_preset is not None:
            if family != 'v2':
                raise ValueError('Expressive and Stable delivery overrides require KittenTTS 2.')
            if requested_preset not in ('stable', 'expressive'):
                raise ValueError('Choose Stable or Expressive delivery.')
            selected['preset']=requested_preset
        has_cues = plain_text(text) != text
        if has_cues and family != 'v2':
            raise ValueError('Emotion, event and emphasis tags require KittenTTS 2.')
        validate_references(selected)
        opts = generation_options(selected, family)
        if has_cues:
            # Explicit cues should take effect even if the original recording
            # was made with emotion conditioning disabled. Scoped to this take.
            opts.setdefault('advanced', {})['use_emotion'] = True
        self.update(job_id, message='Generating only the selected sentence…')
        model = self.load(key, job_id)
        if voice == '__clone__':
            kwargs = dict(reference=self.reference_path(selected['reference_id']))
            if selected.get('reference_text'):
                kwargs['reference_text'] = selected['reference_text']
        else:
            kwargs = {'voice': voice}
        sync_device = str(getattr(model, 'device', 'cpu'))
        synchronize_cuda(sync_device)
        start = time.perf_counter()
        audio = as_audio(model.generate(text, **opts, **kwargs))
        synchronize_cuda(sync_device)
        sample_rate = int(getattr(model, 'sample_rate', 24000))
        preview_path = PREVIEWS / (job_id + '.wav')
        sf.write(preview_path, audio, sample_rate, subtype='PCM_16')
        self.update(job_id, preview_url='/api/edit/previews/' + job_id,
                    preview_data={'record_id': rid, 'sentence_index': index, 'text': text,
                                  'duration': len(audio)/sample_rate,
                                  'preset':selected.get('preset'), 'cues':has_cues},
                    timings={'synthesis_s': round(time.perf_counter()-start,2),
                             'audio_s': round(len(audio)/sample_rate,2),
                             'device': sync_device},
                    message='New sentence ready to audition. Original remains untouched.')

    def apply_replacement(self, payload: dict, job_id: str):
        rid = payload['record_id']
        source = record(rid)
        meta = recording_meta(rid)
        sentences = meta['alignment']
        idx = int(payload['sentence_index'])
        if not sentences or not 0 <= idx < len(sentences):
            raise ValueError('Original alignment no longer available.')
        pj = payload['preview_job_id']
        preview_job = self.snapshot(pj)
        pd = preview_job.get('preview_data')
        if preview_job['status'] != 'done' or not pd or pd['record_id'] != rid or pd['sentence_index'] != idx:
            raise ValueError('Preview is missing or belongs to another sentence. Generate a new preview.')
        start = ranged(payload.get('start'), 0, source['duration'], 'Start time')
        end = ranged(payload.get('end'), 0, source['duration'], 'End time')
        if end - start < .04:
            raise ValueError('Selected region must be at least 40 milliseconds.')
        # Prevent selecting over unrelated sentence regions.
        prev_end = sentences[idx-1]['start'] if idx else 0
        next_start = sentences[idx+1]['end'] if idx+1 < len(sentences) else source['duration']
        if start < prev_end or end > next_start:
            raise ValueError('Selected range overlaps other sentence regions.')
        orig, sr = load_mono(OUTPUTS / source['filename'])
        replacement, repl_sr = load_mono(PREVIEWS / (pj + '.wav'))
        if sr != repl_sr:
            raise ValueError('Replacement has a different sample rate; cannot splice safely.')
        # Keep all original samples except selected region and ~24ms per seam.
        revised = replace_region(orig, replacement, start, end, sr)
        target = sentences[idx]
        updated_text = source['text'][:target['char_start']] + pd['text'] + source['text'][target['char_end']:]
        copy_options = dict(meta['options'])
        new_id = self.store_audio(revised, sr, updated_text, source['model'], source['voice'],
                                  'edited', meta=copy_options, parent_id=rid)
        self.update(job_id, result_id=new_id, parent_id=rid,
                    message='Saved a new version. Previous recording remains in History. Re-align to edit again.')

    def info(self):
        model = self.model
        data = {"key": list(self.current_key) if self.current_key else None,
                "ready": model is not None, "offline": os.getenv("HF_HUB_OFFLINE", "0").lower() in ("1", "true", "yes"),
                "environment": str(Path(__file__).parent / ".venv"),
                "authenticated": False, "compute": compute_capabilities()}
        try:
            from huggingface_hub import get_token
            data["authenticated"] = bool(get_token())
        except Exception:
            pass
        if model is not None:
            data.update({"voices": list(getattr(model, "available_voices", [])),
                         "sample_rate": int(getattr(model, "sample_rate", 24000)),
                         "device": str(getattr(model, "device", self.current_key[1])),
                         "decoders": list(getattr(model, "available_decoders", []))})
        return data


engine = StudioEngine()
app = FastAPI(title="Kitten Studio", docs_url=None, redoc_url=None)


@app.middleware("http")
async def loopback_origin_check(request: Request, call_next):
    # Restrict browser-origin writes to local UI. No cross-origin API exposure.
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlsplit
            parsed = urlsplit(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != request.url.port:
                return JSONResponse({"detail": "This local app only accepts requests from its own UI"}, status_code=403)
    return await call_next(request)


@app.get("/api/info")
def api_info():
    return {"models": MODELS, "profiles": VOICE_PROFILES, "emotions": EMOTIONS,
            "events": EVENTS, "engine": engine.info(), "max_chars": MAX_SCRIPT_CHARS}


@app.post("/api/load")
def api_load(payload: dict[str, Any]):
    try:
        model_choice(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"job_id": engine.new_job("load", "load", payload)}


@app.post("/api/generate")
def api_generate(payload: dict[str, Any]):
    try:
        model_choice(payload)
        segments = payload.get("segments")
        content = segments if isinstance(segments, list) else [payload]
        if not content or len(content) > 30:
            raise ValueError("Provide 1–30 script segments")
        total = sum(len(str(item.get("text", ""))) for item in content if isinstance(item, dict))
        if not total or total > MAX_SCRIPT_CHARS:
            raise ValueError(f"Text must contain 1–{MAX_SCRIPT_CHARS:,} characters")
        validate_references(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"job_id": engine.new_job("generate", "generate", payload)}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    return engine.snapshot(job_id)


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel(job_id: str):
    cancelled = engine.cancel(job_id)
    if not cancelled:
        raise HTTPException(409, "A running generation cannot be interrupted safely. Only queued jobs can be cancelled.")
    return {"cancelled": True}


@app.post("/api/reference")
async def api_reference(file: UploadFile = File(...)):
    name = (file.filename or "reference.wav")
    extension = Path(name).suffix.lower()
    if extension not in {".wav", ".flac", ".mp3", ".m4a", ".ogg"}:
        raise HTTPException(422, "Supported reference formats: WAV, FLAC, MP3, M4A, OGG. WAV is recommended.")
    rid = uuid.uuid4().hex
    filename = f"{rid}{extension}"
    path = REFS / filename
    count = 0
    try:
        with path.open("wb") as dest:
            while block := await file.read(1024 * 1024):
                count += len(block)
                if count > MAX_UPLOAD:
                    raise HTTPException(413, "Reference file exceeds the 32 MB limit")
                dest.write(block)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    if count == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "Reference file was empty")
    with db_connect() as conn:
        conn.execute("INSERT INTO voice_refs (id,filename,original_name,created) VALUES (?,?,?,?)", (rid, filename, name[:180], now()))
    return {"reference_id": rid, "filename": name[:180], "url": f"/api/reference/{rid}"}


@app.get("/api/references")
def api_references():
    """Previously uploaded references (including after app restarts)."""
    with db_connect() as conn:
        rows = conn.execute("SELECT id, original_name, created, filename FROM voice_refs ORDER BY created DESC, rowid DESC").fetchall()
    return [{"id": row["id"], "filename": row["original_name"], "created": row["created"],
             "available": (REFS / row["filename"]).is_file()} for row in rows]


@app.get("/api/reference/{rid}")
def api_reference_play(rid: str):
    row = reference_row(rid)
    if row is None:
        raise HTTPException(404, "Reference recording no longer available")
    return FileResponse(REFS / row["filename"])


@app.get("/api/chunks/{job_id}/{index}")
def api_chunk(job_id: str, index: int):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id) or not 0 <= index <= 999:
        raise HTTPException(404, "Chunk not found")
    path = CHUNKS / job_id / f"chunk_{index:03}.wav"
    if not path.is_file():
        raise HTTPException(404, "Chunk not ready")
    return FileResponse(path, media_type="audio/wav")


def record(rid):
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM recordings WHERE id=?", (rid,)).fetchone()
    if not row:
        raise HTTPException(404, "Recording not found")
    return dict(row)


@app.get('/api/edit/{rid}')
def api_edit_info(rid: str):
    item = record(rid)
    meta = recording_meta(rid)
    sentences = meta['alignment'] or split_sentences(item['text'])
    return {'recording': {k: item[k] for k in ('id','title','text','voice','model','kind','duration','sample_rate')},
            'sentences': sentences, 'aligned': bool(meta['alignment']),
            'method': meta['method'], 'parent_id': meta['parent_id'],
            'can_replace': item['kind'] != 'script',
            'has_saved_settings': bool(meta['options'])}


@app.get('/api/edit/{rid}/waveform')
def api_edit_waveform(rid: str):
    item = record(rid)
    return waveform_peaks(OUTPUTS / item['filename'])


@app.post('/api/edit/{rid}/align')
def api_edit_align(rid: str):
    record(rid)
    return {'job_id': engine.new_job('align','align',{'record_id':rid})}


@app.post('/api/edit/{rid}/preview')
def api_edit_preview(rid: str, payload: dict[str, Any]):
    record(rid)
    meta = recording_meta(rid)
    if not meta['alignment']:
        raise HTTPException(422, 'Align sentences before previewing a replacement.')
    try:
        idx = int(payload.get('sentence_index', -1))
        if not 0 <= idx < len(meta['alignment']):
            raise ValueError('Select a valid sentence.')
        if not str(payload.get('text', '')).strip():
            raise ValueError('Enter replacement speech.')
        if payload.get('preset') not in (None, 'stable', 'expressive'):
            raise ValueError('Choose Stable or Expressive delivery.')
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'job_id': engine.new_job('preview','preview',{'record_id':rid, **payload})}


@app.get('/api/edit/previews/{job_id}')
def api_edit_preview_audio(job_id: str):
    if not re.fullmatch(r'[0-9a-f]{32}',job_id):
        raise HTTPException(404, 'Preview not found')
    path = PREVIEWS / (job_id+'.wav')
    if not path.is_file():
        raise HTTPException(404, 'Preview not found')
    return FileResponse(path, media_type='audio/wav')


@app.post('/api/edit/{rid}/apply')
def api_edit_apply(rid: str, payload: dict[str, Any]):
    record(rid)
    for field in ('preview_job_id','sentence_index','start','end'):
        if field not in payload:
            raise HTTPException(422, f'Missing {field}')
    return {'job_id': engine.new_job('apply','apply',{'record_id':rid, **payload})}


@app.get("/api/history")
def api_history(limit: int = 150):
    limit = min(max(int(limit), 1), 500)
    with db_connect() as conn:
        rows = conn.execute("SELECT id,created,title,text,model,voice,duration,sample_rate,kind FROM recordings ORDER BY created DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/audio/{rid}")
def api_audio(rid: str):
    item = record(rid)
    return FileResponse(OUTPUTS / item["filename"], media_type="audio/wav")


@app.get("/api/download/{rid}")
def api_download(rid: str):
    item = record(rid)
    basename = re.sub(r"[^\w .-]", "", item["title"]).strip(" .")[:70] or "kitten-audio"
    return FileResponse(OUTPUTS / item["filename"], media_type="audio/wav", filename=f"{basename}-{rid[:6]}.wav")


@app.delete("/api/history/{rid}")
def api_delete(rid: str):
    item = record(rid)
    with db_connect() as conn:
        conn.execute("DELETE FROM recordings WHERE id=?", (rid,))
        conn.execute("DELETE FROM recording_meta WHERE recording_id=?", (rid,))
    (OUTPUTS / item["filename"]).unlink(missing_ok=True)
    return {"deleted": True}


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


if __name__ == "__main__":
    import uvicorn
    # Windows Proactor may print noisy _call_connection_lost WinError 10054
    # tracebacks when a browser socket closes abruptly. Selector is sufficient
    # for this local HTTP server; real request errors remain logged normally.
    if os.name == "nt":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    host = os.getenv("KITTEN_STUDIO_HOST", "127.0.0.1")
    port = int(os.getenv("KITTEN_STUDIO_PORT", "8765"))
    print(f"\nKitten Studio → http://{host}:{port}\nOffline mode: {os.getenv('HF_HUB_OFFLINE', '0')}\nHF_TOKEN detected: {bool(os.getenv('HF_TOKEN'))} (not network-verified)\nPress Ctrl+C to stop.\n", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")

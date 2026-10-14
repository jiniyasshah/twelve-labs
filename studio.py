#!/usr/bin/env python3
"""Cross-platform installer and launcher. Optional Parler dependencies stay isolated."""
import argparse
import os
import pathlib
import subprocess
import sys
import venv

ROOT = pathlib.Path(__file__).resolve().parent
ENV = ROOT / ".venv"
INDIC_ENV = ROOT / ".venv-indic"

def python_in(folder):
    return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

PYTHON = python_in(ENV)
INDIC_PYTHON = python_in(INDIC_ENV)

def run(python, *args, check=True, silent=False):
    return subprocess.run([str(python), *args], cwd=ROOT, check=check,
                          stdout=subprocess.DEVNULL if silent else None,
                          stderr=subprocess.DEVNULL if silent else None)

def imports_ok(python, code):
    return python.exists() and run(python, "-c", code, check=False, silent=True).returncode == 0

def pip_ok(python):
    return python.exists() and run(python, "-m", "pip", "check", check=False, silent=True).returncode == 0

def ensure_env(folder):
    if not python_in(folder).exists():
        print("Creating isolated Python environment:", folder.name, flush=True)
        venv.create(folder, with_pip=True)

def install_base():
    ensure_env(ENV)
    if not imports_ok(PYTHON, "import fastapi, uvicorn, python_multipart, dotenv, kittenml, soundfile"):
        print("Installing/repairing Kitten Studio base requirements...", flush=True)
        run(PYTHON, "-m", "pip", "install", "-r", "requirements.txt")
    if not imports_ok(PYTHON, "import fastapi, uvicorn, python_multipart, dotenv, kittenml, soundfile"):
        raise RuntimeError("Base dependencies failed to install. Run python studio.py --setup --repair.")

def repair_base():
    print("Restoring KittenTTS dependencies; preserving CUDA PyTorch and user data.", flush=True)
    ensure_env(ENV)
    # The old installer incorrectly put legacy Parler into the main environment.
    # Remove only its top-level packages, and restore base runtime dependencies.
    run(PYTHON, "-m", "pip", "uninstall", "-y",
        "parler-tts", "descript-audiotools", "descript-audio-codec")
    run(PYTHON, "-m", "pip", "install", "--upgrade",
        "transformers>=4.55", "huggingface-hub>=1.32,<2",
        "protobuf>=6.31.1", "kittenml>=0.9.4")
    install_base()
    if not pip_ok(PYTHON):
        print("WARNING: pip check still reports conflicts; review the output:", flush=True)
        run(PYTHON, "-m", "pip", "check", check=False)
    else:
        print("Base dependency checks passed.", flush=True)

def install_extra(name):
    if name == "kokoro":
        run(PYTHON, "-m", "pip", "install", "kokoro>=0.9.2", "misaki[en]", "espeakng-loader")
    elif name == "alignment":
        run(PYTHON, "-m", "pip", "install", "faster-whisper")
    elif name == "indic":
        ensure_env(INDIC_ENV)
        if not imports_ok(INDIC_PYTHON, "import parler_tts, transformers, torch, soundfile"):
            print("Installing Indic Parler in .venv-indic (isolated from KittenTTS)...", flush=True)
            run(INDIC_PYTHON, "-m", "pip", "install",
                "git+https://github.com/huggingface/parler-tts.git")
        if not imports_ok(INDIC_PYTHON, "import parler_tts, transformers, torch, soundfile"):
            raise RuntimeError("Indic Parler setup incomplete in .venv-indic")
    else:
        raise ValueError("Unknown optional engine: " + name)

def cuda_ready(python):
    return imports_ok(python, "import torch; assert torch.cuda.is_available()")

def install_gpu(python):
    if cuda_ready(python):
        print("CUDA PyTorch already works in", python.parent.parent.name, "— skipping download.")
        return
    print("Installing CUDA PyTorch for", python.parent.parent.name, flush=True)
    run(python, "-m", "pip", "install", "--upgrade", "torch", "torchaudio",
        "--index-url", "https://download.pytorch.org/whl/cu128")
    if not cuda_ready(python):
        print("WARNING: CUDA still unavailable here. CPU generation remains possible.")

def main():
    p = argparse.ArgumentParser(description="Setup and launch Kitten Studio")
    p.add_argument("--setup", action="store_true", help="Install/repair without launching")
    p.add_argument("--repair", action="store_true", help="Restore KittenTTS after old Parler installation")
    p.add_argument("--extras", default="", help="Optional: kokoro,indic,alignment")
    p.add_argument("--gpu", action="store_true", help="Install CUDA wheels only when missing")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--cpu", action="store_true")
    args = p.parse_args()
    if sys.version_info < (3, 10):
        p.error("Python 3.10+ required (3.11/3.12 recommended)")
    if args.gpu and sys.platform == "darwin":
        p.error("NVIDIA CUDA is not available on macOS")
    if args.repair:
        repair_base()
    install_base()
    extras = [e.strip().lower() for e in args.extras.split(",") if e.strip()]
    for extra in extras:
        install_extra(extra)
    if args.gpu:
        install_gpu(PYTHON)
        if INDIC_PYTHON.exists():
            install_gpu(INDIC_PYTHON)
    if not pip_ok(PYTHON):
        print("WARNING: Base environment has dependency conflicts. "
              "Run python studio.py --setup --repair", flush=True)
        run(PYTHON, "-m", "pip", "check", check=False)
    if args.setup:
        print("Setup complete. Start with: python studio.py")
        return
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    if args.offline:
        env["HF_HUB_OFFLINE"] = "1"
    if args.cpu:
        env["CUDA_VISIBLE_DEVICES"] = ""
    print("Kitten Studio: http://127.0.0.1:8765", flush=True)
    raise SystemExit(subprocess.call([str(PYTHON), "-X", "utf8", "server.py"], env=env, cwd=ROOT))

if __name__ == "__main__":
    main()

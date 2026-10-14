#!/usr/bin/env python3
"""Cross-platform installer and launcher. Optional Parler dependencies stay isolated."""
import argparse
import os
import pathlib
import json
import re
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
# Official TorchAudio wheels are published in lockstep with PyTorch.
INDIC_TORCH_VERSION = "2.11.0"
CUDA_WHEEL_CHANNEL = "cu128"

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

RUNTIME_PROBE = r"""
import json
report = {}
try:
    import torch
    report['torch'] = str(torch.__version__)
    report['cuda_build'] = str(torch.version.cuda) if torch.version.cuda else None
    try:
        report['cuda_available'] = bool(torch.cuda.is_available())
    except Exception as exc:
        report['cuda_error'] = str(exc)
except Exception as exc:
    report['torch_error'] = str(exc)
try:
    import torchaudio
    report['torchaudio'] = str(torchaudio.__version__)
except Exception as exc:
    report['torchaudio_error'] = f'{type(exc).__name__}: {exc}'
print(json.dumps(report))
"""

def runtime_probe(python):
    if not python.exists():
        return {'error': 'Environment not installed'}
    try:
        result = subprocess.run([str(python), '-c', RUNTIME_PROBE], cwd=ROOT,
                                capture_output=True, text=True, timeout=50)
        if result.returncode:
            return {'error': (result.stderr or result.stdout).strip()[-800:]}
        return json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return {'error': str(exc)}

def diagnose():
    for name, python in [('Main KittenTTS', PYTHON), ('Isolated Indic Parler', INDIC_PYTHON)]:
        d = runtime_probe(python)
        print(f'\n{name}: {python}', flush=True)
        if 'error' in d:
            print('  Environment:', d['error'])
            continue
        print('  PyTorch:', d.get('torch', d.get('torch_error', 'unavailable')))
        print('  CUDA wheel:', d.get('cuda_build') or 'CPU-only')
        print('  CUDA usable:', d.get('cuda_available', False))
        print('  TorchAudio:', d.get('torchaudio', d.get('torchaudio_error', 'missing')))
    print('\nIf Indic TorchAudio is broken, use: python studio.py --setup --repair-indic-audio')

def _version_base(version):
    match = re.match(r'^(\d+\.\d+\.\d+)', str(version or ''))
    return match.group(1) if match else None

def _indic_pair_healthy(details, cuda):
    if details.get('error') or details.get('torch_error') or details.get('torchaudio_error'):
        return False
    if _version_base(details.get('torch')) != INDIC_TORCH_VERSION:
        return False
    if _version_base(details.get('torchaudio')) != INDIC_TORCH_VERSION:
        return False
    expected_build = CUDA_WHEEL_CHANNEL if cuda else 'cpu'
    for name in ('torch', 'torchaudio'):
        version = details[name]
        if '+' in version and version.rsplit('+', 1)[1] != expected_build:
            return False
    if cuda:
        return details.get('cuda_build') == '12.8'
    return not details.get('cuda_build')

def ensure_indic_pair(cuda=False, current=None):
    """Repair only the isolated Indic runtime using a published matching pair.

    The compatible TorchAudio release may lag behind arbitrary PyPI torch
    versions. Never attempt to install torchaudio==<arbitrary torch version>.
    """
    ensure_env(INDIC_ENV)
    details = current if current is not None else runtime_probe(INDIC_PYTHON)
    if _indic_pair_healthy(details, cuda):
        print('Indic PyTorch and TorchAudio are compatible; no download needed.')
        return
    expected_cuda = '12.8' if cuda else None
    correct_torch = (_version_base(details.get('torch')) == INDIC_TORCH_VERSION
                     and details.get('cuda_build') == expected_cuda
                     and not details.get('torch_error'))
    channel = CUDA_WHEEL_CHANNEL if cuda else 'cpu'
    if sys.platform == 'darwin':
        if cuda:
            raise RuntimeError('CUDA is not supported on macOS')
        index = 'https://pypi.org/simple'
    else:
        index = f'https://download.pytorch.org/whl/{channel}'
    packages = [f'torchaudio=={INDIC_TORCH_VERSION}']
    if not correct_torch:
        packages.insert(0, f'torch=={INDIC_TORCH_VERSION}')
        print(f'Indic torch {details.get("torch", "missing")} lacks a supported matching '
              f'TorchAudio wheel. Installing PyTorch/TorchAudio {INDIC_TORCH_VERSION} '
              'in .venv-indic only.', flush=True)
    else:
        print('Existing Indic PyTorch is compatible; repairing only TorchAudio.', flush=True)
    cmd = ['-m', 'pip', 'install', '--force-reinstall']
    # A fresh venv needs PyTorch dependencies. Existing ones should not be
    # replaced when repairing the native extensions.
    if details.get('torch'):
        cmd.append('--no-deps')
    cmd += packages + ['--index-url', index]
    run(INDIC_PYTHON, *cmd)
    after = runtime_probe(INDIC_PYTHON)
    if not _indic_pair_healthy(after, cuda):
        raise RuntimeError('Indic native audio still failed validation: ' + str(after)[:600]
                           + '. On Windows also check the Visual C++ Redistributable x64.')
    print('Validated isolated Indic Torch/TorchAudio ' + INDIC_TORCH_VERSION
          + (' CUDA' if cuda else ' CPU'))

def repair_indic_audio(cuda=None):
    if not INDIC_PYTHON.exists():
        raise RuntimeError('Install Indic first: python studio.py --setup --extras indic')
    details = runtime_probe(INDIC_PYTHON)
    if cuda is None:
        cuda = bool(details.get('cuda_build')) and sys.platform != 'darwin'
    ensure_indic_pair(cuda=cuda, current=details)

def indic_imports_ok():
    return imports_ok(INDIC_PYTHON, 'import torch, torchaudio; from parler_tts import ParlerTTSForConditionalGeneration')

def install_extra(name, gpu=False):
    if name == "kokoro":
        run(PYTHON, "-m", "pip", "install", "kokoro>=0.9.2", "misaki[en]", "espeakng-loader")
    elif name == "alignment":
        run(PYTHON, "-m", "pip", "install", "faster-whisper")
    elif name == "indic":
        ensure_env(INDIC_ENV)
        previous = runtime_probe(INDIC_PYTHON)
        ensure_indic_pair(cuda=gpu or bool(previous.get('cuda_build')))
        if not imports_ok(INDIC_PYTHON, "import parler_tts, transformers, torch, soundfile"):
            print("Installing Indic Parler in .venv-indic (isolated from KittenTTS)...", flush=True)
            run(INDIC_PYTHON, "-m", "pip", "install",
                "git+https://github.com/huggingface/parler-tts.git")
        # Checking plain 'import parler_tts' misses native torchaudio DLL failures.
        if not indic_imports_ok():
            probe = runtime_probe(INDIC_PYTHON)
            if probe.get('torchaudio_error'):
                print("TorchAudio native extension failed. Attempting a matching-wheel repair...", flush=True)
                repair_indic_audio(cuda=gpu or bool(probe.get('cuda_build')))
            if not indic_imports_ok():
                raise RuntimeError("Indic Parler cannot load. Run python studio.py --diagnose and "
                                   "check the separate .venv-indic environment.")
    else:
        raise ValueError("Unknown optional engine: " + name)

def cuda_ready(python):
    return imports_ok(python, "import torch; assert torch.cuda.is_available()")

def install_gpu(python):
    if python == INDIC_PYTHON:
        ensure_indic_pair(cuda=True)
        return
    if cuda_ready(python):
        print("CUDA PyTorch already works in", python.parent.parent.name, "— skipping download.")
        return
    report = runtime_probe(python)
    if report.get("cuda_build"):
        print("CUDA-enabled PyTorch is already installed in", python.parent.parent.name,
              "but the GPU is unavailable. Skipping a costly re-download.")
        print("Check the NVIDIA driver, available GPU memory, and python studio.py --diagnose")
        return
    print("Installing CUDA PyTorch for", python.parent.parent.name, flush=True)
    run(python, "-m", "pip", "install", "--upgrade",
        f"torch=={INDIC_TORCH_VERSION}", f"torchaudio=={INDIC_TORCH_VERSION}",
        "--index-url", "https://download.pytorch.org/whl/cu128")
    if not cuda_ready(python):
        print("WARNING: CUDA still unavailable here. CPU generation remains possible.")

def main():
    p = argparse.ArgumentParser(description="Setup and launch Kitten Studio")
    p.add_argument("--setup", action="store_true", help="Install/repair without launching")
    p.add_argument("--repair", action="store_true", help="Restore KittenTTS after old Parler installation")
    p.add_argument("--extras", default="", help="Optional: kokoro,indic,alignment")
    p.add_argument("--gpu", action="store_true", help="Install CUDA wheels only when missing")
    p.add_argument("--diagnose", action="store_true", help="Check both environments and native audio DLLs")
    p.add_argument("--repair-indic-audio", action="store_true",
                   help="Repair only TorchAudio DLLs in the isolated Indic environment")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--cpu", action="store_true")
    args = p.parse_args()
    if sys.version_info < (3, 10):
        p.error("Python 3.10+ required (3.11/3.12 recommended)")
    if args.gpu and sys.platform == "darwin":
        p.error("NVIDIA CUDA is not available on macOS")
    if args.diagnose:
        diagnose()
        return
    if args.repair_indic_audio:
        repair_indic_audio(cuda=True if args.gpu else None)
    if args.repair:
        repair_base()
    install_base()
    extras = [e.strip().lower() for e in args.extras.split(",") if e.strip()]
    for extra in extras:
        install_extra(extra, gpu=args.gpu)
    if args.gpu:
        install_gpu(PYTHON)
        if INDIC_PYTHON.exists():
            install_gpu(INDIC_PYTHON)
    if args.setup and INDIC_PYTHON.exists():
        info = runtime_probe(INDIC_PYTHON)
        if info.get('torchaudio_error') or not info.get('torchaudio'):
            raise RuntimeError("Indic native audio failed validation: " +
                               str(info.get('torchaudio_error', info))[:500])
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

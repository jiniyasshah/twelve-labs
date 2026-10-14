"""Preflight check for the private Kitten Studio Python environment.

Runs *before* starting server.py, so users see an actionable repair message
instead of a multi-page import traceback. This script does not download models.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REQUIRED = (
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("multipart", "python-multipart"),
    ("numpy", "numpy"),
    ("soundfile", "soundfile"),
    ("kittenml", "kittenml"),
    ("dotenv", "python-dotenv"),
)


def check_dependencies(importer=importlib.import_module):
    problems = []
    for module, package in REQUIRED:
        try:
            importer(module)
        except Exception as exc:
            problems.append((package, f"{type(exc).__name__}: {exc}"))
    return problems


def main() -> int:
    root = Path(__file__).resolve().parent
    venv = root / ".venv"
    exe = Path(sys.executable).resolve()
    try:
        exe.relative_to(venv.resolve())
    except ValueError:
        print("ERROR: Not using Kitten Studio's private .venv Python.")
        print(f"Active Python: {exe}")
        return 1

    issues = check_dependencies()
    if issues:
        print("\nKitten Studio installation is incomplete:")
        for package, detail in issues:
            print(f"  - {package}: {detail}")
        print("\nRun REPAIR_WINDOWS.bat or INSTALL_WINDOWS.bat to repair it.")
        return 1

    print("Kitten Studio dependencies: OK (private .venv)")
    try:
        import torch
        cuda_version = getattr(torch.version, 'cuda', None)
        can_run = bool(cuda_version and torch.cuda.is_available())
        print(f"PyTorch {torch.__version__}; CUDA build: {cuda_version or 'none'}; CUDA usable: {can_run}")
        if not can_run:
            print("CPU mode is supported. Optional NVIDIA installer: INSTALL_NVIDIA_GPU_WINDOWS.bat")
    except Exception as exc:
        print(f"PyTorch CUDA status unavailable: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""One setup and run entry point: Windows, Linux and macOS."""
import argparse
import os
import pathlib
import subprocess
import sys
import venv

ROOT = pathlib.Path(__file__).resolve().parent
ENV = ROOT / '.venv'
PYTHON = ENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

def invoke(*args):
    subprocess.check_call([str(PYTHON), *args], cwd=ROOT)

def healthy():
    if not PYTHON.exists():
        return False
    return subprocess.run([str(PYTHON), '-c',
        'import fastapi, uvicorn, python_multipart, dotenv, kittenml, soundfile'],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

def install_base():
    if not PYTHON.exists():
        print('Creating local Python environment...')
        venv.create(ENV, with_pip=True)
    if not healthy():
        print('Installing or repairing Kitten Studio dependencies...')
        invoke('-m', 'pip', 'install', '--upgrade', 'pip')
        invoke('-m', 'pip', 'install', '-r', 'requirements.txt')
        if not healthy():
            raise RuntimeError('Dependency verification failed. See pip output above.')

def install_extra(name):
    if name == 'kokoro':
        invoke('-m', 'pip', 'install', 'kokoro>=0.9.2', 'misaki[en]', 'espeakng-loader')
    elif name == 'indic':
        invoke('-m', 'pip', 'install', 'git+https://github.com/huggingface/parler-tts.git')
    elif name == 'alignment':
        invoke('-m', 'pip', 'install', 'faster-whisper')
    else:
        raise ValueError(f'Unknown extra: {name}')

def main():
    parser = argparse.ArgumentParser(description='Install, repair, and launch Kitten Studio')
    parser.add_argument('--setup', action='store_true', help='Install or repair without launching')
    parser.add_argument('--extras', default='', help='Optional engines: kokoro,indic,alignment')
    parser.add_argument('--gpu', action='store_true', help='CUDA 12.8 PyTorch (NVIDIA on Windows/Linux)')
    parser.add_argument('--offline', action='store_true', help='Use only cached model files')
    parser.add_argument('--cpu', action='store_true', help='Disable CUDA')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error('Python 3.10+ required; 3.11/3.12 recommended.')
    install_base()
    if args.gpu:
        if sys.platform == 'darwin':
            parser.error('CUDA not available on macOS')
        invoke('-m', 'pip', 'install', '--upgrade', 'torch', 'torchaudio', '--index-url', 'https://download.pytorch.org/whl/cu128')
    for extra in (x.strip().lower() for x in args.extras.split(',') if x.strip()):
        install_extra(extra)
    if args.setup:
        print('Setup complete. Start with: python studio.py')
        return
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    if args.offline:
        env['HF_HUB_OFFLINE'] = '1'
    if args.cpu:
        env['CUDA_VISIBLE_DEVICES'] = ''
    print('Kitten Studio: http://127.0.0.1:8765', flush=True)
    raise SystemExit(subprocess.call([str(PYTHON), '-X', 'utf8', 'server.py'], cwd=ROOT, env=env))

if __name__ == '__main__':
    main()

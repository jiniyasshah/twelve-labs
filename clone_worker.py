"""Isolated Chatterbox multilingual / optional community Nepali fine-tune worker.

No reference audio is uploaded to any Studio service: inference is local.
The official model must download once from Hugging Face to run offline.
"""
import contextlib
import json
import sys

def send(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def main():
    nepali = len(sys.argv) > 2 and sys.argv[2] == "nepali"
    try:
        with contextlib.redirect_stdout(sys.stderr):
            import torch
            import soundfile as sf
            import numpy as np
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            wanted = sys.argv[1] if len(sys.argv) > 1 else "cpu"
            device = "cuda" if wanted == "cuda" and torch.cuda.is_available() else "cpu"
            # Upstream Chatterbox pins torch 2.6, which predates NVIDIA RTX 50
            # Blackwell kernels. Avoid selecting unsupported CUDA accidentally.
            if device == "cuda":
                try:
                    major, _ = torch.cuda.get_device_capability()
                    torch_version = tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2])
                    if major >= 12 and torch_version < (2, 7):
                        print("Chatterbox's pinned PyTorch does not support RTX 50 CUDA kernels; using CPU.", file=sys.stderr)
                        device = "cpu"
                except Exception:
                    device = "cpu"
            # For upstream, V3 is the latest multilingual T3 checkpoint.
            # Community Nepali weights fine-tune the original V2 backbone.
            model = (ChatterboxMultilingualTTS.from_pretrained(device=device)
                     if nepali else ChatterboxMultilingualTTS.from_pretrained(
                         device=device, t3_model="v3"))
            if nepali:
                from huggingface_hub import hf_hub_download
                from safetensors.torch import load_file
                path = hf_hub_download(
                    "Firoj112/chatterbox-nepali-runs",
                    filename="t3_mtl_nepali_final.safetensors")
                weights = load_file(path)
                clean = {k.replace("patched_model.", "").replace("model.", ""): v
                         for k, v in weights.items()}
                # A partial/unexpected checkpoint should not quietly synthesize
                # with untuned weights; fine-tune may legitimately omit keys.
                expected = set(model.t3.state_dict())
                overlap = len(expected & set(clean))
                if not expected or overlap < len(expected) // 2:
                    raise RuntimeError("Nepali checkpoint does not match the Chatterbox model.")
                model.t3.load_state_dict(clean, strict=False)
                model.t3.to(device).eval()
            sample_rate = int(model.sr)
        send({"sample_rate": sample_rate, "device": device})
    except Exception as exc:
        send({"error": str(exc)[:1300]})
        return 1
    for line in sys.stdin:
        try:
            query = json.loads(line)
            language = "ne" if nepali else str(query.get("language", "en"))
            if nepali and query.get("language") != "ne":
                raise ValueError("Nepali fine-tune only supports Nepali in Studio.")
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                kwargs = {"language_id": language}
                if query.get("reference"):
                    kwargs["audio_prompt_path"] = str(query["reference"])
                audio = model.generate(str(query["text"]), **kwargs)
                wave = audio.detach().cpu().numpy().astype("float32").reshape(-1)
                sf.write(str(query["output"]), wave, sample_rate, subtype="PCM_16")
            send({"sample_rate": sample_rate})
        except Exception as exc:
            send({"error": str(exc)[:900]})
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

"""Isolated long-lived Indic Parler inference process. JSON lines via stdin/stdout."""
import contextlib
import json
import os
import sys

def send(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def main():
    try:
        with contextlib.redirect_stdout(sys.stderr):
            import torch
            import soundfile as sf
            import numpy as np
            from parler_tts import ParlerTTSForConditionalGeneration
            from transformers import AutoTokenizer
            name = "ai4bharat/indic-parler-tts"
            wanted = sys.argv[1] if len(sys.argv) > 1 else "cpu"
            device = "cuda" if wanted == "cuda" and torch.cuda.is_available() else "cpu"
            model = ParlerTTSForConditionalGeneration.from_pretrained(name).to(device).eval()
            prompt_tokenizer = AutoTokenizer.from_pretrained(name)
            description_tokenizer = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
            sample_rate = int(model.config.sampling_rate)
        send({"device": device, "sample_rate": sample_rate})
    except Exception as exc:
        send({"error": "Indic model could not load: " + str(exc)[:900]})
        return 1
    for line in sys.stdin:
        try:
            payload = json.loads(line)
            text = str(payload["text"])
            voice = str(payload["voice"])
            if " · " not in voice:
                raise ValueError("Invalid voice")
            speaker = voice.split(" · ", 1)[1]
            prompt = (f"{speaker}'s voice delivers natural, clear speech at a moderate pace. "
                      "The recording is of very high quality, with no background noise.")
            desc = str(payload.get("description", "")).strip()
            prompt = (f"{speaker}'s voice. {desc}") if desc else prompt
            with contextlib.redirect_stdout(sys.stderr), torch.inference_mode():
                description = description_tokenizer(prompt, return_tensors="pt").to(device)
                utterance = prompt_tokenizer(text, return_tensors="pt").to(device)
                audio = model.generate(
                    input_ids=description.input_ids,
                    attention_mask=description.attention_mask,
                    prompt_input_ids=utterance.input_ids,
                    prompt_attention_mask=utterance.attention_mask)
                result = np.asarray(audio.cpu().numpy(), dtype=np.float32).reshape(-1)
                sf.write(str(payload["output"]), result, sample_rate)
            send({"sample_rate": sample_rate})
        except Exception as exc:
            send({"error": str(exc)[:900]})
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

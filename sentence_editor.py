"""Audio edit primitives: conservative script splitting, Whisper word alignment,
waveform previews and non-destructive crossfade replacement.

All timestamps are estimates until checked by the human editor. This module does
not modify the original WAV or require paid services.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

import numpy as np
import soundfile as sf

_SENTENCE_END = re.compile(r'[.!?。！？]+(?:["”’\']+)?(?=\s|$)')
_ABBREV = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "fig", "no", "e.g", "i.e"}
_EMOTION = re.compile(r'\[(?:angry|contemplative|excited|joyful|mundane|nervous|sad|stern|surprised|tender)\]', re.I)
_EVENT = re.compile(r'<(?:gasp|giggle|growl|gulp|laugh|pause|scoff|sigh|sob|um)>', re.I)
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)


def plain_text(text: str) -> str:
    return re.sub(r'\(\(\((.*?)\)\)\)', r'\1', _EVENT.sub(' ', _EMOTION.sub(' ', text)), flags=re.S)


def words(text: str) -> list[str]:
    return [m.group(0).lower().replace('’', "'") for m in _WORD.finditer(plain_text(text))]


def split_sentences(text: str) -> list[dict]:
    """Preserve original character offsets (including expression tags)."""
    if not text.strip():
        return []
    spans = []
    start = 0
    for m in _SENTENCE_END.finditer(text):
        before = text[start:m.end()]
        # Avoid splitting decimals and titles such as Dr. Rivera.
        token = re.search(r'([\w.]+)\.$', text[start:m.end()].rstrip('"”\''))
        if token and token.group(1).lower() in _ABBREV:
            continue
        end = m.end()
        if text[start:end].strip():
            s = start + len(text[start:end]) - len(text[start:end].lstrip())
            spans.append({'text': text[s:end], 'char_start': s, 'char_end': end})
        start = end
    if text[start:].strip():
        s = start + len(text[start:]) - len(text[start:].lstrip())
        e = len(text.rstrip())
        spans.append({'text': text[s:e], 'char_start': s, 'char_end': e})
    # A lone event/tag without text should travel with the next sentence.
    if len(spans) > 180:
        raise ValueError('The editor supports up to 180 sentences per recording.')
    return spans


def align_words(text: str, detected: list[dict], duration: float, audio: np.ndarray | None = None,
                rate: int = 24000) -> list[dict]:
    """Find a monotonic correspondence between original text and ASR word times.

    Sentence boundaries are placed between the end of the preceding sentence's
    recognized words and the start of the following one's. Unmatched boundaries
    are estimated proportionally and flagged for manual review.
    """
    parts = split_sentences(text)
    if not parts:
        return []
    source_tokens = []
    source_sentences = []
    for i, part in enumerate(parts):
        for token in words(part['text']):
            source_tokens.append(token)
            source_sentences.append(i)
    asr_tokens, asr_times = [], []
    for item in detected:
        start, end = float(item.get('start', 0)), float(item.get('end', 0))
        if start < 0 or end <= start or start > duration:
            continue
        ts = words(str(item.get('word', '')))
        for token in ts:
            asr_tokens.append(token)
            asr_times.append((max(0, start), min(duration, end)))
    groups = [[] for _ in parts]
    if source_tokens and asr_tokens:
        matcher = difflib.SequenceMatcher(None, source_tokens, asr_tokens, autojunk=False)
        for block in matcher.get_matching_blocks():
            for off in range(block.size):
                groups[source_sentences[block.a + off]].append(asr_times[block.b + off])
    # Boundary between adjacent sentences; never overlap adjacent intervals.
    boundaries = [0.0] * (len(parts) + 1)
    boundaries[-1] = duration
    for i in range(1, len(parts)):
        before, after = groups[i-1], groups[i]
        if before and after:
            predicted = (max(x[1] for x in before) + min(x[0] for x in after)) / 2
        elif before:
            predicted = max(x[1] for x in before)
        elif after:
            predicted = min(x[0] for x in after)
        else:
            predicted = (parts[i]['char_start'] / max(1, len(text))) * duration
        # A sentence boundary should be a pause if one exists nearby. Small
        # changes only, and do not touch if no waveform is available.
        predicted = max(0, min(duration, predicted))
        if audio is not None and audio.size and 0.25 < predicted < duration - .25:
            predicted = seek_quiet_boundary(audio, rate, predicted, radius=.18)
        boundaries[i] = predicted
    # Guarantee chronological, nonoverlapping intervals for imperfect transcripts.
    min_gap = min(.02, duration / max(2, 2 * len(parts)))
    for i in range(1, len(parts)):
        boundaries[i] = max(boundaries[i-1] + min_gap,
                            min(boundaries[i], duration - min_gap * (len(parts)-i)))
    result = []
    for i, part in enumerate(parts):
        source_count = max(1, len(words(part['text'])))
        confidence = min(1.0, len(groups[i]) / source_count)
        result.append({**part, 'start': round(boundaries[i], 3), 'end': round(boundaries[i+1], 3),
                       'confidence': round(confidence, 2),
                       'method': 'word-aligned' if confidence >= .6 else 'estimated-review'})
    return result


def seek_quiet_boundary(audio, rate: int, target: float, radius: float = .15) -> float:
    """Pick a nearby low-energy 15ms window, not a faraway silence."""
    if rate < 100 or len(audio) < rate // 3:
        return target
    hop = max(1, int(.008 * rate))
    window = max(1, int(.015 * rate))
    lo = max(0, int((target - radius) * rate))
    hi = min(len(audio)-window, int((target + radius) * rate))
    if hi <= lo:
        return target
    samples = np.asarray(audio, dtype=np.float32)
    centers = np.arange(lo, hi, hop)
    if not len(centers):
        return target
    # Prefer silence close to proposed ASR boundary over unrelated distant pauses.
    rms = np.array([float(np.mean(samples[p:p+window]**2)) for p in centers])
    cost = np.sqrt(rms) + (np.abs(centers / rate - target) / max(radius, .01)) * .003
    return float(centers[int(np.argmin(cost))] / rate)


def provisional_alignment(text: str, duration: float, audio: np.ndarray | None = None,
                          rate: int = 24000) -> list[dict]:
    """Honest fallback when optional ASR is missing or unreachable."""
    return align_words(text, [], duration, audio, rate)


def waveform_peaks(file_path: Path, count: int = 900) -> dict:
    with sf.SoundFile(file_path) as audio:
        sr, frames = audio.samplerate, len(audio)
        # Read at most 2.5m samples by striding through file, to limit memory.
        block = audio.read(dtype='float32', always_2d=True)
    mono = block.mean(axis=1)
    count = max(100, min(1800, count))
    bounds = np.linspace(0, len(mono), count+1, dtype=int)
    peaks = [round(float(np.max(np.abs(mono[a:max(a+1,b)]))), 4) for a,b in zip(bounds[:-1], bounds[1:])]
    return {'peaks': peaks, 'duration': round(frames/sr, 3), 'sample_rate': sr}


def replace_region(original: np.ndarray, insert: np.ndarray, start_s: float, end_s: float,
                   rate: int, fade_ms: float = 24.0) -> np.ndarray:
    """Ripple-splice with localized equal-power fades. Original never modified.

    The replacement may be longer or shorter; later audio simply shifts. Only
    ~24ms around either seam is mixed. The untouched samples are bit-exact in
    float32 until the new WAV's PCM encoder quantizes them.
    """
    a, b = int(round(start_s * rate)), int(round(end_s * rate))
    if not (0 <= a < b <= len(original)):
        raise ValueError('Invalid time range for replacement')
    insert = np.asarray(insert, dtype=np.float32)
    original = np.asarray(original, dtype=np.float32)
    if insert.ndim != 1 or len(insert) < max(4, int(rate*.04)) or not np.isfinite(insert).all():
        raise ValueError('Replacement audio is missing or invalid')
    left, right = original[:a], original[b:]
    # A very short segment needs reduced seam fades.
    n = min(int(rate * fade_ms / 1000), len(left), len(right), len(insert)//4)
    if n < 2:
        return np.concatenate([left, insert, right])
    ramp = np.linspace(0, 1, n, dtype=np.float32)
    up, down = np.sin(ramp*np.pi/2), np.cos(ramp*np.pi/2)
    seam_a = left[-n:]*down + insert[:n]*up
    seam_b = insert[-n:]*down + right[:n]*up
    return np.concatenate([left[:-n], seam_a, insert[n:-n], seam_b, right[n:]])


def load_mono(path: Path):
    samples, rate = sf.read(path, dtype='float32', always_2d=True)
    return samples.mean(axis=1), int(rate)

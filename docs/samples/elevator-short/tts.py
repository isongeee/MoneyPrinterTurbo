"""Per-sentence Kokoro TTS -> voice wav + timeline with per-chunk caption timings."""
import json, sys, numpy as np, soundfile as sf
from kokoro_onnx import Kokoro
OUT, M = sys.argv[1], sys.argv[2]
voice = sys.argv[3] if len(sys.argv) > 3 else "am_michael"
sys.path.insert(0, OUT); from script import BEATS
k = Kokoro(f"{M}/kokoro-v1.0.onnx", f"{M}/voices-v1.0.bin")
SENT_GAP, BEAT_GAP = 0.08, 0.16
pieces, timeline, t = [], [], 0.0
for sid, sentences in BEATS:
    beat = {"id": sid, "start": t, "chunks": [], "text": " ".join(s for s, _ in sentences)}
    for text, chunks in sentences:
        samples, sr = k.create(text, voice=voice, speed=1.15, lang="en-us")
        idx = np.where(np.abs(samples) > 0.01)[0]
        samples = samples[max(0, idx[0] - 600): idx[-1] + 1500]
        d = len(samples) / sr
        # split the sentence span across chunks by character count
        total, ct = sum(len(c) for c in chunks), t
        for c in chunks:
            cd = d * len(c) / total
            beat["chunks"].append([ct, ct + cd, c]); ct += cd
        pieces.append(samples); t += d
        gap = SENT_GAP if (text, chunks) != sentences[-1] else BEAT_GAP
        pieces.append(np.zeros(int(gap * sr), dtype=samples.dtype)); t += gap
    beat["end"] = t
    timeline.append(beat)
sf.write(f"{OUT}/voice.wav", np.concatenate(pieces), sr)
json.dump(timeline, open(f"{OUT}/timeline.json", "w"), indent=1)
for b in timeline: print(b["id"], round(b["start"], 2), round(b["end"], 2))

import json, sys, numpy as np, soundfile as sf
from kokoro_onnx import Kokoro
sys.path.insert(0, sys.argv[1]); from script import BEATS
M = sys.argv[2]; OUT = sys.argv[1]
k = Kokoro(f"{M}/kokoro-v1.0.onnx", f"{M}/voices-v1.0.bin")
voice = sys.argv[3] if len(sys.argv) > 3 else "am_michael"
GAP = 0.12
pieces, timeline, t = [], [], 0.0
for sid, text, chunks in BEATS:
    samples, sr = k.create(text, voice=voice, speed=1.15, lang="en-us")
    # trim leading/trailing silence
    idx = np.where(np.abs(samples) > 0.01)[0]
    samples = samples[max(0, idx[0]-600): idx[-1]+1500]
    d = len(samples)/sr
    pieces += [samples, np.zeros(int(GAP*sr), dtype=samples.dtype)]
    timeline.append({"id": sid, "start": t, "speech_end": t+d, "end": t+d+GAP, "text": text, "chunks": chunks})
    t += d + GAP
audio = np.concatenate(pieces)
sf.write(f"{OUT}/voice_{voice}.wav", audio, sr)
json.dump(timeline, open(f"{OUT}/timeline_{voice}.json", "w"), indent=1)
print(voice, round(t, 2))

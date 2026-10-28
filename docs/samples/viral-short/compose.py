"""Final assembly using MoneyPrinterTurbo's own video pipeline (captions + voice + BGM).

Usage: python compose.py <viral_dir> <repo_dir> <visuals.mp4> <out.mp4>
"""
import json, os, sys

VD, REPO, VISUALS, OUT = sys.argv[1:5]
sys.path.insert(0, REPO)
os.chdir(REPO)
from app.models.schema import VideoParams  # noqa: E402
from app.services import video  # noqa: E402

TL = json.load(open(f"{VD}/timeline_am_michael.json"))


def chunk_times(beat):
    chunks = beat["chunks"]
    total = sum(len(c) for c in chunks)
    t, out = beat["start"], []
    span = beat["speech_end"] - beat["start"]
    for c in chunks:
        d = span * len(c) / total
        out.append((t, t + d, c))
        t += d
    return out


def ts(x):
    ms = int(round(x * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


srt = f"{VD}/subtitle.srt"
with open(srt, "w", encoding="utf-8") as f:
    n = 1
    for b in TL:
        for st, en, txt in chunk_times(b):
            f.write(f"{n}\n{ts(st)} --> {ts(en)}\n{txt}\n\n")
            n += 1

params = VideoParams(
    video_subject="MoneyPrinterTurbo",
    video_aspect="9:16",
    subtitle_enabled=True,
    subtitle_position="custom",
    custom_position=77.0,
    font_name="BeVietnamPro-Bold.ttf",
    font_size=96,
    text_fore_color="#FFD60A",
    stroke_color="#000000",
    stroke_width=7,
    bgm_type="custom",
    bgm_file=f"{REPO}/resource/songs/output023.mp3",
    bgm_volume=0.14,
    voice_volume=1.0,
    n_threads=4,
)
ok = video.generate_video(VISUALS, f"{VD}/voice_am_michael.wav", srt, OUT, params)
print("bgm mixed:", ok, "->", OUT)

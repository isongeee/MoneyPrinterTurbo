# Viral short sample

`moneyprinterturbo_viral_short.mp4` is a 29-second vertical (1080x1920) short that promotes
MoneyPrinterTurbo, made in the style of a TikTok/Reels/Shorts "AI tool" video.

- **Script:** hand-written beat sheet in `script.py` (hook, then 6 steps, then "no camera / no editing / no face", batch, name, plot twist, CTA).
- **Voice:** offline [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) TTS (`am_michael`, 1.15x), via `tts.py`.
- **Visuals:** motion graphics rendered frame by frame with Pillow in `render.py`, using crops of `docs/webui-en.jpg`.
- **Final assembly:** `compose.py` calls MoneyPrinterTurbo's own `app.services.video.generate_video` to burn in the
  captions (`subtitle.srt`), mix the voice with the bundled BGM `resource/songs/output023.mp3`, and encode the video.
  The audio was then normalized to -14 LUFS with ffmpeg `loudnorm`.

## Regenerate

```bash
pip install kokoro-onnx soundfile
# download kokoro-v1.0.onnx and voices-v1.0.bin from the kokoro-onnx "model-files-v1.0" release into $MODELS
python docs/samples/viral-short/tts.py "$OUT" "$MODELS" am_michael   # $OUT must contain script.py
python docs/samples/viral-short/render.py "$OUT" . "$OUT/visuals.mp4"
python docs/samples/viral-short/compose.py "$OUT" . "$OUT/visuals.mp4" "$OUT/final.mp4"
ffmpeg -i "$OUT/final.mp4" -c:v copy -af loudnorm=I=-14:TP=-1.5:LRA=11 -c:a aac -b:a 192k out.mp4
```

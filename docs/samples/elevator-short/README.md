# "How an elevator works" sample

`how_elevators_work.mp4` is a 50-second vertical (1080x1920) explainer short of the kind MoneyPrinterTurbo is built
to produce: a hook question, then counterweight, traction, rope safety and overspeed brakes, the 1854 Otis
demonstration, a "close door button" twist, and a call to follow.

- **Script:** `script.py`. Each beat is a list of spoken sentences with their caption chunks.
- **Voice:** offline [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) TTS (`am_michael`, 1.15x), via `tts.py`.
  Each sentence is synthesized separately so caption timing stays tight.
- **Visuals:** `render.py` draws an animated blueprint cross-section (car, counterweight, sheave, motor, governor,
  safety brakes), with a camera that zooms to each part as it is explained. Frames are drawn with Pillow.
- **Final assembly:** `compose.py` uses `app.services.video.generate_video` to burn in the captions, mix in the
  bundled BGM `resource/songs/output011.mp3`, and encode. The audio was then normalized to -14 LUFS.

Regenerate the same way as `docs/samples/viral-short` (see its README), using this folder's scripts.

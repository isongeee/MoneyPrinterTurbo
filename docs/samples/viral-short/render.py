"""Render the visual track for the viral short, one scene per narration beat.

Usage: python render.py <viral_dir> <repo_dir> <out.mp4> [--frames t1,t2,...]
"""
import json, math, random, subprocess, sys
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

VD, REPO, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PREVIEW = None
if len(sys.argv) > 5 and sys.argv[4] == "--frames":
    PREVIEW = [float(x) for x in sys.argv[5].split(",")]

W, H, FPS = 1080, 1920, 30
TL = json.load(open(f"{VD}/timeline_am_michael.json"))
TOTAL = TL[-1]["end"] + 0.6

BG = (9, 12, 11)
GREEN = (34, 227, 122)
YELLOW = (255, 214, 10)
RED = (255, 75, 75)
WHITE = (255, 255, 255)
GREY = (150, 160, 155)

FB = f"{REPO}/resource/fonts/BeVietnamPro-Bold.ttf"
FM = f"{REPO}/resource/fonts/BeVietnamPro-Medium.ttf"
_fc = {}


def font(size, bold=True):
    key = (size, bold)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(FB if bold else FM, size)
    return _fc[key]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_back(x):
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- assets
UI = Image.open(f"{REPO}/docs/webui-en.jpg").convert("RGB")
S = 1.275  # screenshot coords below are measured at 2000px width


def ui_crop(x0, y0, x1, y1):
    return UI.crop((int(x0 * S), int(y0 * S), int(x1 * S), int(y1 * S)))


UI_SCRIPT = ui_crop(0, 140, 482, 640)
UI_AUDIO = ui_crop(1012, 137, 1494, 1195)
UI_SUBS = ui_crop(1518, 137, 1999, 1097)
UI_HEADER = ui_crop(0, 20, 700, 112)
UI_GEN_BTN = ui_crop(0, 1293, 2000, 1360)

# voice envelope for the waveform scene
_v, _sr = sf.read(f"{VD}/voice_am_michael.wav")
_hop = _sr // FPS
ENV = np.array([np.sqrt(np.mean(_v[i:i + _hop] ** 2)) for i in range(0, len(_v), _hop)])
ENV = ENV / (ENV.max() + 1e-9)


def env_at(t):
    i = int(t * FPS)
    return float(ENV[i]) if 0 <= i < len(ENV) else 0.0


# chunk timings (shared with the subtitle writer)
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


# ---------------------------------------------------------------- drawing helpers
def rrect(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


SYM = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SYMBOLS = set("↓★✓♪✦→")


def _runs(txt):
    runs = []
    for ch in txt:
        sym = ch in SYMBOLS
        if runs and runs[-1][0] == sym:
            runs[-1][1] += ch
        else:
            runs.append([sym, ch])
    return runs


def text_img(txt, size, color=WHITE, stroke=0, stroke_color=(0, 0, 0), bold=True):
    """Render text on a transparent image, falling back to DejaVu for symbols."""
    sym_font = _fc.setdefault(("sym", size), ImageFont.truetype(SYM, size))
    parts = [(sym_font if sym else font(size, bold), seg) for sym, seg in _runs(txt)]
    widths = [f.getlength(seg) for f, seg in parts]
    asc = max(f.getmetrics()[0] for f, _ in parts)
    desc = max(f.getmetrics()[1] for f, _ in parts)
    pad = stroke + 4
    im = Image.new("RGBA", (int(sum(widths)) + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = pad
    for (f, seg), w in zip(parts, widths):
        d.text((x, pad + asc), seg, font=f, fill=color, anchor="ls",
               stroke_width=stroke, stroke_fill=stroke_color)
        x += w
    return im.crop(im.getbbox() or (0, 0, 1, 1))


def paste_center(canvas, im, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    if scale != 1.0:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    if alpha < 1.0:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im.putalpha(a)
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def glow(im, color, radius=30, strength=1.0):
    """Return an RGBA glow layer for an RGBA image."""
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    a = a.point(lambda v: int(min(255, v * strength)))
    g = Image.new("RGBA", im.size, color + (0,))
    g.putalpha(a)
    return g


def pop(t, t0, dur=0.35):
    """scale factor for a pop-in starting at t0"""
    return ease_back((t - t0) / dur) if t >= t0 else 0.0


def card(img, pad=26, radius=36, border=GREEN, shadow=True):
    """Wrap a screenshot crop in a rounded card with a glowing border."""
    w, h = img.width + pad * 2, img.height + pad * 2
    out = Image.new("RGBA", (w + 80, h + 80), (0, 0, 0, 0))
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    rrect(d, (0, 0, w - 1, h - 1), radius, fill=(255, 255, 255, 255))
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), 18, fill=255)
    base.paste(img, (pad, pad), mask)
    if shadow:
        sh = Image.new("RGBA", (w, h), border + (0,))
        sh.putalpha(base.getchannel("A"))
        out.alpha_composite(glow(sh, border, 28, 1.3), (40, 40))
    out.alpha_composite(base, (40, 40))
    d2 = ImageDraw.Draw(out)
    rrect(d2, (40, 40, 40 + w - 1, 40 + h - 1), radius, outline=border + (255,), width=6)
    return out


# ---------------------------------------------------------------- background
random.seed(7)
PARTICLES = [(random.uniform(0, W), random.uniform(0, H), random.uniform(18, 46),
              random.uniform(40, 120), random.uniform(0, 6.28)) for _ in range(26)]
_yy, _xx = np.mgrid[0:H, 0:W]
_VIGNETTE = np.clip(1.15 - np.sqrt(((_xx - W / 2) / W) ** 2 + ((_yy - H * 0.42) / H) ** 2) * 1.5, 0.25, 1.0)


def background(t, tint=GREEN):
    base = np.zeros((H, W, 3), np.float32)
    base[:] = BG
    # radial glow following the accent colour
    gx, gy = W / 2 + math.sin(t * 0.7) * 160, H * 0.40 + math.cos(t * 0.5) * 120
    r2 = ((_xx - gx) ** 2 + (_yy - gy) ** 2) / (700.0 ** 2)
    g = np.exp(-r2)[..., None] * 0.22
    base += g * np.array(tint, np.float32)
    base *= _VIGNETTE[..., None]
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(im)
    # moving perspective-ish grid
    off = (t * 60) % 120
    for y in range(-120, H + 120, 120):
        d.line([(0, y + off), (W, y + off)], fill=(255, 255, 255, 5), width=2)
    for x in range(0, W + 1, 120):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 5), width=2)
    # floating $ particles
    for (x, y, s, sp, ph) in PARTICLES:
        yy = (y - t * sp) % (H + 200) - 100
        xx = x + math.sin(t * 1.3 + ph) * 30
        d.text((xx, yy), "$", font=font(int(s)), fill=GREEN + (38,))
    return im


# ---------------------------------------------------------------- scene widgets
def headline(canvas, t, t0, txt, y, size=120, color=WHITE, accent=None):
    s = pop(t, t0)
    im = text_img(txt, size, color, stroke=8)
    if accent:
        paste_center(canvas, glow(im, accent, 26, 1.6), W / 2, y, s)
    paste_center(canvas, im, W / 2, y, s)


def chip(txt, size=44, fg=BG, bg=GREEN):
    ti = text_img(txt, size, fg)
    im = Image.new("RGBA", (ti.width + 60, ti.height + 34), (0, 0, 0, 0))
    rrect(ImageDraw.Draw(im), (0, 0, im.width - 1, im.height - 1), im.height // 2, fill=bg + (255,))
    im.alpha_composite(ti, (30, 17))
    return im


def camera_icon(sz, color):
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0)); d = ImageDraw.Draw(im); w = sz // 18
    rrect(d, (sz * .08, sz * .28, sz * .92, sz * .82), sz * .1, outline=color, width=w)
    d.ellipse((sz * .32, sz * .38, sz * .68, sz * .74), outline=color, width=w)
    rrect(d, (sz * .34, sz * .16, sz * .62, sz * .3), sz * .04, fill=color)
    return im


def scissors_icon(sz, color):
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0)); d = ImageDraw.Draw(im); w = sz // 18
    d.ellipse((sz * .08, sz * .58, sz * .38, sz * .88), outline=color, width=w)
    d.ellipse((sz * .62, sz * .58, sz * .92, sz * .88), outline=color, width=w)
    d.line((sz * .32, sz * .62, sz * .72, sz * .1), fill=color, width=w)
    d.line((sz * .68, sz * .62, sz * .28, sz * .1), fill=color, width=w)
    return im


def face_icon(sz, color):
    im = Image.new("RGBA", (sz, sz), (0, 0, 0, 0)); d = ImageDraw.Draw(im); w = sz // 18
    d.ellipse((sz * .1, sz * .1, sz * .9, sz * .9), outline=color, width=w)
    d.ellipse((sz * .32, sz * .36, sz * .42, sz * .46), fill=color)
    d.ellipse((sz * .58, sz * .36, sz * .68, sz * .46), fill=color)
    d.arc((sz * .3, sz * .42, sz * .7, sz * .72), 20, 160, fill=color, width=w)
    return im


def phone(w, h, inner, t=0.0):
    """Phone frame with a mini 'short video' inside; inner = (hue colour, label)."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    rrect(d, (0, 0, w - 1, h - 1), w * .14, fill=(20, 22, 22, 255), outline=(70, 80, 76, 255), width=5)
    sx0, sy0, sx1, sy1 = int(w * .06), int(h * .035), int(w * .94), int(h * .965)
    col, label = inner
    scr = Image.new("RGB", (sx1 - sx0, sy1 - sy0))
    sd = ImageDraw.Draw(scr)
    for y in range(scr.height):
        k = y / scr.height
        sd.line([(0, y), (scr.width, y)], fill=tuple(int(c * (0.35 + 0.65 * (1 - k))) for c in col))
    # stylised hills / sun so it reads as "footage"
    cx = scr.width * (0.5 + 0.25 * math.sin(t * 1.5))
    sd.ellipse((cx - scr.width * .14, scr.height * .2, cx + scr.width * .14, scr.height * .2 + scr.width * .28),
               fill=(255, 236, 170))
    sd.polygon([(0, scr.height * .62), (scr.width * .4, scr.height * .48), (scr.width, scr.height * .66),
                (scr.width, scr.height), (0, scr.height)], fill=tuple(int(c * .25) for c in col))
    # caption bar
    f = font(max(14, int(w * .085)))
    tb = sd.textbbox((0, 0), label, font=f)
    sd.text(((scr.width - (tb[2] - tb[0])) / 2, scr.height * .74), label, font=f, fill=YELLOW,
            stroke_width=max(2, int(w * .012)), stroke_fill=(0, 0, 0))
    mask = Image.new("L", scr.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, scr.width - 1, scr.height - 1), int(w * .1), fill=255)
    im.paste(scr, (sx0, sy0), mask)
    rrect(d, (w * .36, h * .05, w * .64, h * .075), 8, fill=(10, 10, 10, 255))
    return im


SCRIPT_LINES = [
    "Cats sleep up to 16 hours",
    "a day. But it's not laziness.",
    "Their wild ancestors hunted",
    "at dawn and dusk, so every",
    "nap is saving energy for",
    "the next big chase...",
]
CLIPS = [((235, 140, 60), "sleepy cat"), ((80, 150, 240), "sunny window"), ((140, 90, 230), "cat stretching"),
         ((40, 190, 140), "wild lynx"), ((240, 90, 120), "kitten yawn"), ((230, 190, 60), "night hunt")]


# ---------------------------------------------------------------- scenes
def sc_hook(c, t, b):
    lt = t - b["start"]
    ct = chunk_times(b)
    d = ImageDraw.Draw(c)
    if t < ct[2][0]:
        # a cluttered editing timeline that gets stamped out
        x0, y0 = 90, 520
        rrect(d, (x0, y0, W - 90, y0 + 560), 30, fill=(24, 28, 27, 255), outline=(60, 70, 66, 255), width=4)
        d.text((x0 + 36, y0 + 26), "untitled_final_FINAL_v7.prproj", font=font(34, False), fill=GREY)
        rnd = random.Random(3)
        for row in range(5):
            x = x0 + 40
            while x < W - 140:
                wseg = rnd.randint(70, 210)
                colr = rnd.choice([(80, 120, 230), (230, 120, 80), (120, 200, 120), (200, 90, 200)])
                rrect(d, (x, y0 + 100 + row * 88, min(x + wseg, W - 130), y0 + 170 + row * 88), 10, fill=colr + (255,))
                x += wseg + 10
        ph = x0 + 40 + ((lt * 520) % (W - 260))
        d.line((ph, y0 + 90, ph, y0 + 540), fill=RED + (255,), width=6)
        headline(c, t, b["start"], "8 HOURS", 380, 150, RED, RED)
        headline(c, t, b["start"] + 0.25, "for ONE video?", 1180, 84, WHITE)
        s = pop(t, ct[1][0], 0.25)
        if s:
            x = text_img("X", 620, RED, stroke=14, stroke_color=(40, 0, 0))
            paste_center(c, glow(x, RED, 40, 1.5), W / 2, y0 + 270, 2.2 - 1.2 * s, 0.9)
            paste_center(c, x, W / 2, y0 + 270, 2.2 - 1.2 * s, 0.9)
    else:
        t0 = ct[2][0]
        headline(c, t, t0, "1 TOPIC", 470, 170, WHITE)
        a = text_img("↓", 200, GREEN)
        paste_center(c, a, W / 2, 700 + math.sin(lt * 8) * 18, pop(t, t0 + 0.15))
        headline(c, t, t0 + 0.3, "1 VIDEO", 930, 170, GREEN, GREEN)
        paste_center(c, chip("100% FREE • OPEN SOURCE", 46), W / 2, 1150, pop(t, ct[3][0]))


def sc_topic(c, t, b):
    lt = t - b["start"]
    im = UI_SCRIPT.copy()
    d = ImageDraw.Draw(im)
    fx0, fy0, fx1, fy1 = int(29 * S), int((272 - 140) * S), int(455 * S), int((329 - 140) * S)
    rrect(d, (fx0, fy0, fx1, fy1), 14, fill=(240, 242, 246), outline=RED, width=4)
    msg = "Why cats sleep 16 hours"
    n = int(clamp((lt - 0.1) / 0.7) * len(msg))
    cur = "|" if int(lt * 4) % 2 == 0 else ""
    d.text((fx0 + 22, fy0 + 16), msg[:n] + cur, font=font(38), fill=(30, 30, 30))
    cd = card(im)
    s = 0.95 + 0.08 * ease_out(lt / 1.6)
    paste_center(c, cd, W / 2, 760, s * pop(t, b["start"] - 0.05, 0.3) * 1.25)
    headline(c, t, b["start"], "STEP 1", 250, 70, GREEN)


def sc_script(c, t, b):
    lt = t - b["start"]
    d = ImageDraw.Draw(c)
    headline(c, t, b["start"], "STEP 2", 250, 70, GREEN)
    btn = chip("✦ Generate Script with AI", 46, WHITE, (40, 44, 43))
    paste_center(c, btn, W / 2, 400, pop(t, b["start"]) * (0.94 if 0.15 < lt < 0.3 else 1.0))
    x0, y0 = 90, 500
    rrect(d, (x0, y0, W - 90, y0 + 640), 34, fill=(250, 250, 250, 255), outline=GREEN + (255,), width=6)
    d.text((x0 + 44, y0 + 34), "Video Script", font=font(44), fill=(30, 30, 30))
    chars = int(clamp((lt - 0.25) / 1.1) * sum(len(l) for l in SCRIPT_LINES))
    y = y0 + 120
    for line in SCRIPT_LINES:
        seg = line[:max(0, chars)]
        chars -= len(line)
        d.text((x0 + 44, y), seg, font=font(46, False), fill=(40, 40, 40))
        y += 80


def sc_footage(c, t, b):
    headline(c, t, b["start"], "STEP 3", 250, 70, GREEN)
    for i, clip in enumerate(CLIPS):
        col, row = i % 3, i // 3
        cx, cy = 210 + col * 330, 590 + row * 520
        ph = phone(290, 480, clip, t + i)
        paste_center(c, ph, cx, cy, pop(t, b["start"] + i * 0.12, 0.3), rot=math.sin(t * 2 + i) * 2)
    paste_center(c, chip("Pexels • Pixabay • your own clips", 40, WHITE, (40, 44, 43)), W / 2, 1180,
                 pop(t, b["start"] + 0.6))


def sc_voice(c, t, b):
    lt = t - b["start"]
    headline(c, t, b["start"], "STEP 4", 250, 70, GREEN)
    crop = UI_AUDIO.crop((0, 0, UI_AUDIO.width, int(700 * S - 137 * S)))
    paste_center(c, card(crop), W / 2, 660, 1.0 * pop(t, b["start"] - 0.05, 0.3))
    d = ImageDraw.Draw(c)
    n = 34
    for i in range(n):
        e = env_at(t - abs(i - n / 2) * 0.012)
        hgt = 24 + 200 * e * (0.6 + 0.4 * math.sin(i * 1.7 + t * 20) ** 2)
        x = 120 + i * (W - 240) / (n - 1)
        rrect(d, (x - 9, 1160 - hgt / 2, x + 9, 1160 + hgt / 2), 9, fill=GREEN + (255,))


def sc_subs(c, t, b):
    lt = t - b["start"]
    headline(c, t, b["start"], "STEP 5", 250, 70, GREEN)
    crop = UI_SUBS.crop((0, 0, UI_SUBS.width, int(800 * S - 137 * S)))
    paste_center(c, card(crop, border=YELLOW), W * 0.36, 700, 0.95 * pop(t, b["start"] - 0.05, 0.3))
    # floating music notes on the right
    for i in range(4):
        tt = (lt * 1.2 + i * 0.25) % 1.0
        n = text_img("♪", 120, YELLOW if i % 2 else GREEN)
        paste_center(c, n, 860 + math.sin(i * 2 + lt * 5) * 60, 1100 - tt * 700, 1.0, 1 - tt)
    styles = [(WHITE, (0, 0, 0)), (YELLOW, (0, 0, 0)), (GREEN, (0, 0, 0))]
    fg, st = styles[int(lt * 3) % 3]
    paste_center(c, text_img("Your captions here", 78, fg, stroke=7, stroke_color=st), W / 2, 1180,
                 pop(t, b["start"] + 0.2))


def sc_export(c, t, b):
    lt = t - b["start"]
    ct = chunk_times(b)
    d = ImageDraw.Draw(c)
    headline(c, t, b["start"], "STEP 6", 250, 70, GREEN)
    gb = chip("Generate Video", 56, WHITE, RED)
    paste_center(c, gb, W / 2, 420, pop(t, b["start"]) * (0.92 if 0.1 < lt < 0.25 else 1.0))
    if t < ct[2][0]:
        p = ease_out(lt / max(0.1, ct[2][0] - b["start"] - 0.1))
        rrect(d, (120, 640, W - 120, 720), 40, fill=(40, 44, 43, 255))
        rrect(d, (120, 640, 120 + max(80, (W - 240) * p), 720), 40, fill=GREEN + (255,))
        pct = text_img(f"{int(p * 100)}%", 150, WHITE, stroke=6)
        paste_center(c, pct, W / 2, 880)
        lbl = "final-1.mp4  ✓" if p > 0.98 else "rendering video..."
        paste_center(c, text_img(lbl, 54, GREEN if p > 0.98 else GREY, bold=p > 0.98), W / 2, 1060)
    else:
        v = phone(330, 560, CLIPS[0], t)
        paste_center(c, v, W / 2 - 230, 820, pop(t, ct[2][0]))
        hz = phone(330, 560, CLIPS[1], t).rotate(90, expand=True)
        paste_center(c, hz, W / 2 + 210, 820, pop(t, ct[3][0]) * 0.92)
        paste_center(c, chip("9:16", 46), W / 2 - 230, 1150, pop(t, ct[2][0]))
        paste_center(c, chip("16:9", 46), W / 2 + 210, 1150, pop(t, ct[3][0]))


def sc_nos(c, t, b):
    ct = chunk_times(b)
    icons = [camera_icon, scissors_icon, face_icon]
    labels = ["CAMERA", "EDITING", "FACE"]
    for i, (st, en, _) in enumerate(ct):
        y = 380 + i * 330
        s = pop(t, st - 0.05, 0.25)
        ic = icons[i](220, WHITE)
        paste_center(c, ic, 300, y, s)
        paste_center(c, text_img(labels[i], 92, WHITE, stroke=6), 690, y, s)
        k = clamp((t - st - 0.15) / 0.2)
        if k > 0:
            d = ImageDraw.Draw(c)
            d.line((150, y + 120, 150 + (W - 300) * k, y - 110), fill=RED + (255,), width=22)


def sc_batch(c, t, b):
    ct = chunk_times(b)
    headline(c, t, b["start"], "Videos per Run:", 260, 72, WHITE)
    for i in range(6):
        col, row = i % 3, i // 3
        cx, cy = 210 + col * 330, 640 + row * 470
        paste_center(c, phone(250, 420, CLIPS[(i + 2) % 6], t + i), cx, cy, pop(t, ct[1][0] + i * 0.09, 0.28))
    n = sum(1 for i in range(6) if t >= ct[1][0] + i * 0.09)
    if n:
        paste_center(c, chip(f"x{n}", 70), W - 170, 260, pop(t, ct[1][0]))


def sc_name(c, t, b):
    lt = t - b["start"]
    ct = chunk_times(b)
    hdr = UI_HEADER.convert("RGBA")
    paste_center(c, card(hdr, border=GREEN), W / 2, 560, 0.95 * pop(t, ct[1][0] - 0.1, 0.35))
    s = pop(t, ct[1][0] - 0.1)
    logo = text_img("$$$", 170, GREEN, stroke=6)
    paste_center(c, glow(logo, GREEN, 30, 1.6), W / 2, 330, s)
    paste_center(c, logo, W / 2, 330, s)
    d = ImageDraw.Draw(c)
    k = pop(t, ct[2][0] - 0.05)
    if k:
        repo = Image.new("RGBA", (900, 240), (0, 0, 0, 0)); rd = ImageDraw.Draw(repo)
        rrect(rd, (0, 0, 899, 239), 30, fill=(22, 27, 34, 255), outline=(48, 54, 61, 255), width=4)
        rd.ellipse((40, 40, 110, 110), fill=WHITE)
        rd.text((136, 44), "harry0703 / MoneyPrinterTurbo", font=font(44), fill=(88, 166, 255))
        rd.text((40, 140), "Public  •  MIT License  •  Python", font=font(38, False), fill=(139, 148, 158))
        paste_center(c, repo, W / 2, 900, k)
        paste_center(c, chip("★ Star it on GitHub", 50, BG, YELLOW), W / 2, 1120, pop(t, ct[3][0]))


def sc_twist(c, t, b):
    lt = t - b["start"]
    ct = chunk_times(b)
    jitter = 14 if int(lt * 20) % 5 == 0 else 3
    base = text_img("PLOT TWIST", 150, WHITE, stroke=8)
    for col, dx in ((RED, -jitter), ((60, 200, 255), jitter)):
        tinted = Image.new("RGBA", base.size, col + (0,)); tinted.putalpha(base.getchannel("A").point(lambda v: v // 2))
        paste_center(c, tinted, W / 2 + dx, 420, pop(t, b["start"]))
    paste_center(c, base, W / 2, 420, pop(t, b["start"]))
    if t >= ct[1][0]:
        s = pop(t, ct[1][0])
        # a tiny phone playing "this video" (recursive feel)
        ph = phone(400, 680, ((30, 200, 120), "this video"), t)
        paste_center(c, ph, W / 2, 920, s, rot=math.sin(lt * 3) * 3)
        paste_center(c, chip("made with MoneyPrinterTurbo", 44), W / 2, 1300 - 60, pop(t, ct[2][0]))


def sc_cta(c, t, b):
    lt = t - b["start"]
    s = pop(t, b["start"])
    pulse = 1 + 0.05 * math.sin(lt * 10)
    btn = chip("+ FOLLOW", 110, WHITE, RED)
    paste_center(c, glow(btn, RED, 30, 1.4), W / 2, 640, s * pulse)
    paste_center(c, btn, W / 2, 640, s * pulse)
    headline(c, t, b["start"] + 0.2, "more FREE AI tools", 900, 86, WHITE)
    a = text_img("↓ save this ↓", 60, GREEN)
    paste_center(c, a, W / 2, 1080 + math.sin(lt * 6) * 12, pop(t, b["start"] + 0.5))


SCENES = {"hook": sc_hook, "topic": sc_topic, "script": sc_script, "footage": sc_footage, "voice": sc_voice,
          "subs": sc_subs, "export": sc_export, "nos": sc_nos, "batch": sc_batch, "name": sc_name,
          "twist": sc_twist, "cta": sc_cta}
TINTS = {"hook": RED, "nos": RED, "twist": (60, 200, 255), "subs": YELLOW, "cta": RED}


def beat_at(t):
    for b in TL:
        if t < b["end"]:
            return b
    return TL[-1]


def frame(t):
    b = beat_at(t)
    c = background(t, TINTS.get(b["id"], GREEN))
    SCENES[b["id"]](c, t, b)
    # flash on each beat change
    lt = t - b["start"]
    if lt < 0.06 and b is not TL[0]:
        c.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, 90)))
    # top progress bar (retention)
    d = ImageDraw.Draw(c)
    d.rectangle((0, 0, W, 12), fill=(255, 255, 255, 40))
    d.rectangle((0, 0, int(W * t / TOTAL), 12), fill=GREEN + (255,))
    return c.convert("RGB")


if PREVIEW:
    for t in PREVIEW:
        frame(t).save(f"{OUT}_{t:05.2f}.png")
    sys.exit()

proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                         "-pix_fmt", "yuv420p", OUT], stdin=subprocess.PIPE)
nframes = int(TOTAL * FPS)
for i in range(nframes):
    proc.stdin.write(frame(i / FPS).tobytes())
    if i % 150 == 0:
        print(f"frame {i}/{nframes}", flush=True)
proc.stdin.close()
proc.wait()
print("done", OUT)

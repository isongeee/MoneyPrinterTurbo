"""Render the visual track for the "how an elevator works" short.

Usage: python render.py <dir> <repo_dir> <out.mp4> [--frames t1,t2,...]
"""
import json, math, random, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

VD, REPO, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PREVIEW = None
if len(sys.argv) > 5 and sys.argv[4] == "--frames":
    PREVIEW = [float(x) for x in sys.argv[5].split(",")]

W, H, FPS = 1080, 1920, 30
TL = json.load(open(f"{VD}/timeline.json"))
B = {b["id"]: b for b in TL}
TOTAL = TL[-1]["end"] + 0.6
SCY = 760  # screen y the camera centre maps to (captions live below ~1350)

NAVY = (8, 22, 48)
LINE = (120, 190, 255)
CYAN = (90, 220, 255)
WHITE = (255, 255, 255)
YELLOW = (255, 214, 10)
RED = (255, 75, 75)
GREEN = (60, 230, 140)
STEEL = (180, 195, 215)
SEPIA = (60, 42, 24)

FB = f"{REPO}/resource/fonts/BeVietnamPro-Bold.ttf"
FM = f"{REPO}/resource/fonts/BeVietnamPro-Medium.ttf"
SYM = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SYMBOLS = set("↓↑★✓✗♪✦→←")
_fc = {}


def font(size, bold=True):
    key = (size, bold)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(FB if bold else FM, size)
    return _fc[key]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_back(x):
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def S(sid):
    return B[sid]["start"]


def E(sid):
    return B[sid]["end"]


def C(sid, i):
    return B[sid]["chunks"][i][0]


# ---------------------------------------------------------------- text helpers
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
        d.text((x, pad + asc), seg, font=f, fill=color, anchor="ls", stroke_width=stroke, stroke_fill=stroke_color)
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
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def glow(im, color, radius=26, strength=1.5):
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(min(255, v * strength)))
    g = Image.new("RGBA", im.size, color + (0,))
    g.putalpha(a)
    return g


def pop(t, t0, dur=0.35):
    return ease_back((t - t0) / dur) if t >= t0 else 0.0


def chip(txt, size=48, fg=NAVY, bg=YELLOW):
    ti = text_img(txt, size, fg)
    im = Image.new("RGBA", (ti.width + 64, ti.height + 36), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, im.height - 1), im.height // 2, fill=bg + (255,))
    im.alpha_composite(ti, (32, 18))
    return im


def headline(c, t, t0, txt, y, size=96, color=WHITE, accent=None):
    s = pop(t, t0)
    im = text_img(txt, size, color, stroke=8, stroke_color=(0, 0, 0))
    if accent:
        paste_center(c, glow(im, accent), W / 2, y, s)
    paste_center(c, im, W / 2, y, s)


# ---------------------------------------------------------------- background (blueprint)
_yy, _xx = np.mgrid[0:H, 0:W]
_VIG = np.clip(1.2 - np.sqrt(((_xx - W / 2) / W) ** 2 + ((_yy - H * 0.42) / H) ** 2) * 1.4, 0.3, 1.0)


def background(t, base_col=NAVY, tint=CYAN, grid=LINE):
    arr = np.zeros((H, W, 3), np.float32)
    arr[:] = base_col
    gx, gy = W / 2 + math.sin(t * 0.6) * 140, H * 0.4 + math.cos(t * 0.45) * 120
    arr += np.exp(-(((_xx - gx) ** 2 + (_yy - gy) ** 2) / 720.0 ** 2))[..., None] * 0.18 * np.array(tint, np.float32)
    arr *= _VIG[..., None]
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(im)
    for i, y in enumerate(range(0, H, 60)):
        d.line([(0, y), (W, y)], fill=grid + (12 if i % 5 == 0 else 5,), width=2)
    for i, x in enumerate(range(0, W + 1, 60)):
        d.line([(x, 0), (x, H)], fill=grid + (12 if i % 5 == 0 else 5,), width=2)
    return im


# ---------------------------------------------------------------- world model
SHEAVE = (560, 190, 95)
GOV = (250, 190, 34)
GOV_PULLEY = (250, 1345, 26)
CAR_W, CAR_H, CAR_X = 240, 280, 345   # car spans x 345..585, rope centre x = 465
CW_X, CW_W, CW_H = 625, 60, 220       # counterweight spans 625..685, rope at 655
ROPE_XS = (447, 465, 483)
FLOORS = {1: 1060, 2: 827, 3: 593, 4: 360}


def keyframes(pts, t):
    """piecewise smoothstep interpolation through (t, value) points"""
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t <= t1:
            k = ease_io((t - t0) / max(1e-6, t1 - t0))
            if isinstance(v0, tuple):
                return tuple(lerp(a, b, k) for a, b in zip(v0, v1))
            return lerp(v0, v1, k)
    return pts[-1][1]


FALL_T0 = C("brakes", 0) + 0.25
CLAMP_T = C("brakes", 3) + 0.1
FALL_Y0, FALL_Y1 = FLOORS[2], 1000
FALL_A = 2 * (FALL_Y1 - FALL_Y0) / (CLAMP_T - FALL_T0) ** 2

CAR_KEYS = [(0, FLOORS[1]), (0.5, FLOORS[1]), (3.9, FLOORS[3]), (S("pull") + 0.2, FLOORS[3]),
            (E("pull") - 0.1, FLOORS[4]), (S("balance") + 0.4, FLOORS[4]), (E("balance") - 0.2, FLOORS[2])]


def car_y(t):
    if FALL_T0 <= t:
        if t < CLAMP_T:
            return FALL_Y0 + 0.5 * FALL_A * (t - FALL_T0) ** 2
        # small skid after the clamp
        return FALL_Y1 + 18 * ease_io((t - CLAMP_T) / 0.15)
    return keyframes(CAR_KEYS, t)


def cw_y(t):
    return 1420 - car_y(t)


FULL = (0.95, 470, 640)
CAM_KEYS = [
    (0, FULL), (S("pull"), FULL), (E("pull") - 0.3, (1.0, 480, 640)),
    (C("ropes", 0) + 0.2, (1.0, 480, 640)), (C("ropes", 2) + 0.2, (1.55, 520, 330)),
    (C("ropes", 4), (1.55, 520, 330)), (C("ropes", 5) + 0.25, (1.4, 610, 1100)),
    (E("counter") - 0.2, (1.5, 600, 1090)), (S("balance") + 0.5, FULL), (E("balance") - 0.1, FULL),
    (S("traction") + 0.4, (2.3, 560, 330)), (E("traction") - 0.1, (2.4, 560, 330)),
    (S("snap") + 0.4, (1.25, 480, 560)), (E("snap") - 0.2, (1.25, 480, 560)),
    (S("brakes") + 0.3, (1.1, 460, 800)), (E("brakes"), (1.1, 460, 880)),
]


class Cam:
    def __init__(self, z, cx, cy, shake=(0, 0)):
        self.z, self.cx, self.cy, self.sh = z, cx, cy, shake

    def P(self, x, y):
        return ((x - self.cx) * self.z + W / 2 + self.sh[0], (y - self.cy) * self.z + SCY + self.sh[1])

    def L(self, w):
        return max(1, int(w * self.z))

    def box(self, x0, y0, x1, y1):
        a, b = self.P(x0, y0), self.P(x1, y1)
        return (a[0], a[1], b[0], b[1])


def draw_rope(d, cam, x, y0, y1, color, width, flow=None, dash_col=None):
    d.line([cam.P(x, y0), cam.P(x, y1)], fill=color + (255,), width=cam.L(width))
    if flow is not None and dash_col:
        step = 46
        off = flow % step
        y = y0 + off
        while y < y1:
            ya, yb = y, min(y1, y + 16)
            d.line([cam.P(x, ya), cam.P(x, yb)], fill=dash_col + (255,), width=cam.L(width * 0.6))
            y += step


def draw_wheel(d, cam, cx, cy, r, angle, col=WHITE, spokes=6, groove=True, fill=(14, 36, 70)):
    d.ellipse(cam.box(cx - r, cy - r, cx + r, cy + r), fill=fill + (255,), outline=col + (255,), width=cam.L(6))
    if groove:
        g = r * 0.86
        d.ellipse(cam.box(cx - g, cy - g, cx + g, cy + g), outline=col + (120,), width=cam.L(3))
    for i in range(spokes):
        a = angle + i * 2 * math.pi / spokes
        d.line([cam.P(cx, cy), cam.P(cx + math.cos(a) * r * 0.8, cy + math.sin(a) * r * 0.8)],
               fill=col + (200,), width=cam.L(5))
    hr = r * 0.16
    d.ellipse(cam.box(cx - hr, cy - hr, cx + hr, cy + hr), fill=col + (255,))


def draw_world(c, t, cam, hl=(), broken_rope=None, brake_on=False, motor_glow=0.0):
    d = ImageDraw.Draw(c)
    cy_ = car_y(t)
    wy = cw_y(t)
    sx, sy, sr = SHEAVE
    # machine room
    d.rounded_rectangle(cam.box(180, 60, 860, 300), cam.L(18), outline=LINE + (200,), width=cam.L(4))
    lbl = text_img("MACHINE ROOM", max(14, int(26 * cam.z)), LINE)
    paste_center(c, lbl, *cam.P(300, 88))
    # hoistway walls + floors
    d.line([cam.P(180, 300), cam.P(180, 1390)], fill=LINE + (200,), width=cam.L(5))
    d.line([cam.P(720, 300), cam.P(720, 1390)], fill=LINE + (200,), width=cam.L(5))
    d.line([cam.P(180, 1390), cam.P(720, 1390)], fill=LINE + (200,), width=cam.L(5))
    for n, fy in FLOORS.items():
        y = fy + CAR_H
        d.line([cam.P(80, y), cam.P(180, y)], fill=LINE + (220,), width=cam.L(8))
        paste_center(c, text_img(str(n), max(14, int(44 * cam.z)), LINE), *cam.P(115, y - 40))
    # guide rails
    for rx in (CAR_X - 10, CAR_X + CAR_W + 10):
        d.line([cam.P(rx, 300), cam.P(rx, 1390)], fill=STEEL + (150,), width=cam.L(6))
    # motor (behind sheave) + shaft
    mg = motor_glow
    mcol = tuple(int(lerp(a, b, mg)) for a, b in zip(STEEL, YELLOW))
    d.line([cam.P(sx, sy), cam.P(770, 150)], fill=STEEL + (255,), width=cam.L(14))
    d.rounded_rectangle(cam.box(700, 95, 840, 205), cam.L(14), fill=(20, 48, 90, 255), outline=mcol + (255,),
                        width=cam.L(6 + 4 * mg))
    paste_center(c, text_img("MOTOR", max(12, int(26 * cam.z)), mcol), *cam.P(770, 150))
    ang = cy_ / sr
    # ropes car side and counterweight side (drawn before sheave so the wheel sits on top)
    rope_hl = "ropes" in hl
    for i, rx in enumerate(ROPE_XS):
        col = YELLOW if rope_hl else STEEL
        if broken_rope == i:
            continue
        if "safe" in hl:
            col = GREEN
        draw_rope(d, cam, rx, sy, cy_, col, 6, flow=cy_ if rope_hl else None, dash_col=WHITE)
    for dx in (-12, 0, 12):
        col = YELLOW if rope_hl else STEEL
        if "safe" in hl:
            col = GREEN
        draw_rope(d, cam, sx + sr + dx * 0.0 + (dx / 12) * 6, sy, wy, col, 6,
                  flow=-cy_ if rope_hl else None, dash_col=WHITE)
    if broken_rope is not None:
        bx = ROPE_XS[broken_rope]
        k = clamp((t - broken_rope_t(t)) / 0.5) if broken_rope_t(t) else 1
        top_end = lerp(cy_ - 120, sy + 60, ease_io(k))
        d.line([cam.P(bx, sy), cam.P(bx, top_end)], fill=RED + (255,), width=cam.L(10))
        if k < 1:
            bp = cam.P(bx, cy_ - 120)
            rnd = random.Random(int(t * 40))
            for _ in range(16):
                a = rnd.uniform(0, 2 * math.pi); r = rnd.uniform(20, 110) * (1 - k)
                d.line([bp, (bp[0] + math.cos(a) * r, bp[1] + math.sin(a) * r)], fill=YELLOW + (255,), width=5)
        # lower piece slumps onto the car roof
        pts = [cam.P(bx, cy_ - lerp(120, 10, ease_io(k))), cam.P(bx + 30 * k, cy_ - 30), cam.P(bx - 25 * k, cy_ - 8),
               cam.P(bx, cy_)]
        d.line(pts, fill=RED + (255,), width=cam.L(10), joint="curve")
    # rope wrap over the sheave
    col = YELLOW if rope_hl else STEEL
    if "safe" in hl:
        col = GREEN
    d.arc(cam.box(sx - sr, sy - sr, sx + sr, sy + sr), 180, 360, fill=col + (255,), width=cam.L(12))
    draw_wheel(d, cam, sx, sy, sr - 6, ang, col=WHITE if "sheave" not in hl else YELLOW)
    # governor wheel, governor rope loop + tension pulley
    gx, gy, gr = GOV
    px, py, pr = GOV_PULLEY
    gcol = YELLOW if "gov" in hl else (170, 200, 235)
    d.line([cam.P(gx - gr, gy), cam.P(px - pr, py)], fill=gcol + (200,), width=cam.L(3))
    d.line([cam.P(gx + gr, gy), cam.P(px + pr, py)], fill=gcol + (200,), width=cam.L(3))
    draw_wheel(d, cam, gx, gy, gr, cy_ / gr, col=gcol, spokes=4, groove=False)
    draw_wheel(d, cam, px, py, pr, cy_ / pr, col=gcol, spokes=4, groove=False)
    # car + link arm to the governor rope
    d.line([cam.P(CAR_X, cy_ + 40), cam.P(gx + gr, cy_ + 40)], fill=gcol + (255,), width=cam.L(5))
    carcol = CYAN if "car" not in hl else YELLOW
    d.rounded_rectangle(cam.box(CAR_X, cy_, CAR_X + CAR_W, cy_ + CAR_H), cam.L(12), fill=(16, 52, 96, 255),
                        outline=carcol + (255,), width=cam.L(7))
    # doors
    mid = CAR_X + CAR_W / 2
    d.line([cam.P(mid, cy_ + 30), cam.P(mid, cy_ + CAR_H - 10)], fill=carcol + (140,), width=cam.L(3))
    # rider
    hx, hy = CAR_X + 85, cy_ + 120
    d.ellipse(cam.box(hx - 20, hy - 20, hx + 20, hy + 20), fill=WHITE + (255,))
    d.line([cam.P(hx, hy + 20), cam.P(hx, hy + 100)], fill=WHITE + (255,), width=cam.L(10))
    d.line([cam.P(hx, hy + 100), cam.P(hx - 22, hy + 150)], fill=WHITE + (255,), width=cam.L(9))
    d.line([cam.P(hx, hy + 100), cam.P(hx + 22, hy + 150)], fill=WHITE + (255,), width=cam.L(9))
    d.line([cam.P(hx, hy + 45), cam.P(hx + 30, hy + 80)], fill=WHITE + (255,), width=cam.L(8))
    d.line([cam.P(hx, hy + 45), cam.P(hx - 28, hy + 80)], fill=WHITE + (255,), width=cam.L(8))
    # safety brake wedges
    bcol = RED if brake_on else STEEL
    for side in (-1, 1):
        rx = CAR_X - 10 if side < 0 else CAR_X + CAR_W + 10
        inset = 0 if brake_on else 8
        y0 = cy_ + CAR_H - 70
        poly = [cam.P(rx - side * (34 + inset), y0), cam.P(rx - side * (6 + inset), y0 + 14),
                cam.P(rx - side * (6 + inset), y0 + 56), cam.P(rx - side * (34 + inset), y0 + 70)]
        d.polygon(poly, fill=bcol + (255,))
    # counterweight
    cwcol = CYAN if "cw" not in hl else YELLOW
    d.rounded_rectangle(cam.box(CW_X, wy, CW_X + CW_W, wy + CW_H), cam.L(8), fill=(40, 70, 110, 255),
                        outline=cwcol + (255,), width=cam.L(6))
    for i in range(1, 6):
        yy = wy + i * CW_H / 6
        d.line([cam.P(CW_X + 6, yy), cam.P(CW_X + CW_W - 6, yy)], fill=cwcol + (150,), width=cam.L(3))
    return d


_broken_t = [None]


def broken_rope_t(t):
    return _broken_t[0]


def callout(c, cam, wx, wy, sx, sy, label, t, t0, color=YELLOW, size=52):
    s = pop(t, t0)
    if not s:
        return
    d = ImageDraw.Draw(c)
    p = cam.P(wx, wy)
    k = ease_io((t - t0) / 0.3)
    d.line([p, (lerp(p[0], sx, k), lerp(p[1], sy, k))], fill=color + (255,), width=5)
    d.ellipse((p[0] - 12, p[1] - 12, p[0] + 12, p[1] + 12), fill=color + (255,))
    paste_center(c, chip(label, size, NAVY, color), sx, sy, s)


# ---------------------------------------------------------------- scenes
def sc_world(c, t, b):
    sid = b["id"]
    cam = Cam(*keyframes(CAM_KEYS, t))
    hl, broken, brake_on, mg = set(), None, False, 0.0
    if sid == "ropes":
        hl = {"ropes"} | ({"sheave"} if C("ropes", 2) <= t < C("ropes", 4) else set()) | (
            {"cw"} if t >= C("ropes", 5) else set())
    elif sid == "counter":
        hl = {"cw"} | ({"car"} if t >= C("counter", 2) else set())
    elif sid == "balance":
        mg = 0.5 + 0.5 * math.sin(t * 12)
    elif sid == "traction":
        hl = {"ropes", "sheave"}
    elif sid == "pull":
        hl = {"ropes"} if t >= C("pull", 2) else set()
    elif sid == "snap":
        if t >= C("snap", 1) + 0.15:
            broken = 1
            _broken_t[0] = C("snap", 1) + 0.15
        if t >= C("snap", 3):
            hl = {"safe"}
    elif sid == "brakes":
        hl = {"gov"} if t >= C("brakes", 2) else set()
        brake_on = t >= CLAMP_T
    # impact shake
    for t_hit, amp in ((C("snap", 1) + 0.15, 22), (CLAMP_T, 28)):
        if 0 <= t - t_hit < 0.35:
            a = amp * (1 - (t - t_hit) / 0.35)
            cam.sh = (math.sin(t * 90) * a, math.cos(t * 70) * a)
    draw_world(c, t, cam, hl, broken, brake_on, mg)

    # scene overlays
    if sid == "hook":
        if t < C("hook", 3):
            headline(c, t, 0.0, "1,000 RIDES...", 130, 100, WHITE)
        else:
            headline(c, t, C("hook", 3) - 0.15, "WHAT HOLDS YOU UP?", 130, 82, YELLOW, YELLOW)
            p = cam.P(465, car_y(t) - 40)
            q = text_img("?", 150, YELLOW, stroke=6)
            paste_center(c, q, p[0] + 170, p[1] - 30 + math.sin(t * 7) * 10, pop(t, C("hook", 3)))
    elif sid == "pull":
        paste_center(c, chip("PUSH ✗", 70, WHITE, RED), W / 2 - 220, 150, pop(t, C("pull", 1) - 0.1))
        paste_center(c, chip("PULL ✓", 70, NAVY, GREEN), W / 2 + 220, 150, pop(t, C("pull", 2) - 0.1))
        if t >= C("pull", 2):
            for i in range(3):
                yy = car_y(t) - 60 - ((t * 260 + i * 110) % 330)
                p = cam.P(530, yy)
                paste_center(c, text_img("↑", 80, GREEN), p[0], p[1], 1.0, 0.9)
    elif sid == "ropes":
        callout(c, cam, 465, 700, 860, 1150, "STEEL ROPES", t, C("ropes", 0) + 0.3)
        if C("ropes", 2) <= t < C("ropes", 5):
            callout(c, cam, 560, 190, 300, 120, "SHEAVE", t, C("ropes", 3) - 0.1)
        if t >= C("ropes", 5):
            callout(c, cam, 655, cw_y(t) + 110, 330, 300, "COUNTERWEIGHT", t, C("ropes", 5))
    elif sid == "counter":
        y = 160
        paste_center(c, chip("COUNTERWEIGHT", 54, NAVY, YELLOW), W / 2, y, pop(t, S("counter")))
        paste_center(c, text_img("=", 80, WHITE, stroke=5), W / 2, y + 115, pop(t, C("counter", 1)))
        paste_center(c, chip("CAR", 60, NAVY, CYAN), W / 2 - 200, y + 225, pop(t, C("counter", 2)))
        paste_center(c, text_img("+", 80, WHITE, stroke=5), W / 2 - 40, y + 225, pop(t, C("counter", 3)))
        paste_center(c, chip("~40% LOAD", 60, NAVY, GREEN), W / 2 + 190, y + 225, pop(t, C("counter", 3)))
    elif sid == "balance":
        draw_seesaw(c, t, b)
        callout(c, cam, 770, 150, 800, 520, "small nudge", t, C("balance", 3), GREEN, 46)
    elif sid == "traction":
        headline(c, t, C("traction", 3) - 0.1, "TRACTION", 150, 130, YELLOW, YELLOW)
        draw_groove_inset(c, t, pop(t, C("traction", 1)))
    elif sid == "snap":
        if t >= C("snap", 1) + 0.15:
            headline(c, t, C("snap", 1) + 0.15, "SNAP!", 170, 150, RED, RED)
        if t >= C("snap", 3):
            paste_center(c, chip("MANY TIMES STRONGER", 54, NAVY, GREEN), W / 2, 330, pop(t, C("snap", 3)))
    elif sid == "brakes":
        if t < C("brakes", 2):
            headline(c, t, S("brakes"), "TOO FAST?", 150, 110, RED, RED)
        if C("brakes", 2) <= t:
            callout(c, cam, 250, 190, 560, 150, "GOVERNOR TRIPS", t, C("brakes", 2), YELLOW, 50)
        if t >= CLAMP_T:
            p = cam.P(CAR_X + CAR_W + 30, car_y(t) + CAR_H - 35)
            paste_center(c, chip("BRAKES CLAMP", 56, WHITE, RED), W / 2, 1230, pop(t, CLAMP_T))
            rnd = random.Random(int(t * 30))
            d = ImageDraw.Draw(c)
            if t - CLAMP_T < 0.6:
                for side_x in (cam.P(CAR_X - 10, 0)[0], cam.P(CAR_X + CAR_W + 10, 0)[0]):
                    for _ in range(10):
                        a = rnd.uniform(0, 2 * math.pi); r = rnd.uniform(10, 60)
                        d.line([(side_x, p[1]), (side_x + math.cos(a) * r, p[1] + math.sin(a) * r)],
                               fill=YELLOW + (255,), width=4)


def draw_seesaw(c, t, b):
    """balance beam: car+rider vs counterweight, motor only adds a nudge"""
    cx, cy = W / 2, 130
    s = pop(t, S("balance")) * 0.75
    if not s:
        return
    lay = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    tilt = math.sin(t * 2.2) * 4
    d.polygon([(450, 170), (410, 260), (490, 260)], fill=STEEL + (255,))
    beam = Image.new("RGBA", (820, 200), (0, 0, 0, 0))
    bd = ImageDraw.Draw(beam)
    bd.rounded_rectangle((0, 150, 819, 170), 10, fill=WHITE + (255,))
    bd.rounded_rectangle((30, 40, 250, 150), 14, fill=CYAN + (255,))
    bd.text((140, 95), "CAR + YOU", font=font(34), fill=NAVY, anchor="mm")
    bd.rounded_rectangle((570, 40, 790, 150), 14, fill=YELLOW + (255,))
    bd.text((680, 95), "WEIGHT", font=font(34), fill=NAVY, anchor="mm")
    beam = beam.rotate(tilt, resample=Image.BICUBIC, center=(410, 160))
    lay.alpha_composite(beam, (40, 10))
    paste_center(c, lay, cx, cy, s)


def draw_groove_inset(c, t, s):
    if not s:
        return
    R = 170
    im = Image.new("RGBA", (2 * R + 20, 2 * R + 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((10, 10, 2 * R + 10, 2 * R + 10), fill=(10, 30, 62, 255), outline=YELLOW + (255,), width=6)
    cx, cy = R + 10, R + 10
    # V-groove cross section with three ropes gripped
    for i, ox in enumerate((-90, 0, 90)):
        x = cx + ox
        d.polygon([(x - 42, cy - 70), (x + 42, cy - 70), (x + 14, cy + 40), (x - 14, cy + 40)], fill=STEEL + (255,))
        d.ellipse((x - 26, cy - 50, x + 26, cy + 2), fill=YELLOW + (255,), outline=NAVY + (255,), width=3)
        k = 0.5 + 0.5 * math.sin(t * 14 + i)
        d.line([(x - 34, cy - 18), (x - 24, cy - 18)], fill=RED + (int(255 * k),), width=5)
        d.line([(x + 24, cy - 18), (x + 34, cy - 18)], fill=RED + (int(255 * k),), width=5)
    d.rectangle((cx - 150, cy + 40, cx + 150, cy + 110), fill=STEEL + (255,))
    d.text((cx, 2 * R + 50), "rope gripping the groove", font=font(30), fill=WHITE, anchor="mm")
    paste_center(c, im, W / 2, 1120, s)


def sc_otis(c, t, b):
    lt = t - b["start"]
    d = ImageDraw.Draw(c)
    headline(c, t, b["start"], "1854", 230, 210, (255, 222, 160), (255, 170, 80))
    paste_center(c, chip("New York • Crystal Palace", 42, SEPIA, (240, 214, 170)), W / 2, 400,
                 pop(t, C("otis", 1)))
    # tower + rails
    cx = W / 2
    top, bot = 480, 1300
    for rx in (cx - 230, cx + 230):
        d.rectangle((rx - 14, top, rx + 14, bot), fill=(150, 112, 70, 255))
        for y in range(top + 20, bot, 40):  # ratchet teeth
            d.polygon([(rx - side(rx, cx) * 14, y), (rx - side(rx, cx) * 30, y + 18), (rx - side(rx, cx) * 14, y + 26)],
                      fill=(190, 150, 100, 255))
    d.rectangle((cx - 260, top - 30, cx + 260, top), fill=(150, 112, 70, 255))
    cut_t = C("otis", 2) + 0.3
    drop = 0
    if t >= cut_t:
        drop = 60 * ease_io((t - cut_t) / 0.25)
    py = 1000 + drop
    # rope
    ch = py - 330  # crosshead carried by two rods down to the platform
    d.rectangle((cx - 200, ch, cx + 200, ch + 18), fill=(190, 150, 100, 255))
    for sx_ in (cx - 190, cx + 190):
        d.line([(sx_, ch), (sx_, py)], fill=(190, 150, 100, 255), width=8)
    if t < cut_t:
        d.line([(cx, top), (cx, ch)], fill=(230, 210, 170, 255), width=8)
    else:
        k = ease_io((t - cut_t) / 0.4)
        d.line([(cx, top), (cx, lerp(ch - 40, top + 40, k))], fill=(230, 210, 170, 255), width=8)
        d.line([(cx, ch), (cx + 30 * k, ch - lerp(40, 10, k))], fill=(230, 210, 170, 255), width=8)
        if t - cut_t < 0.3:
            d.line([(cx - 60, ch - 60), (cx + 60, ch - 60)], fill=RED + (255,), width=10)
    # platform + pawls
    d.rectangle((cx - 210, py, cx + 210, py + 26), fill=(210, 170, 110, 255))
    pawl = 1.0 if t >= cut_t + 0.2 else 0.0
    for sgn in (-1, 1):
        d.polygon([(cx + sgn * 210, py), (cx + sgn * (210 + 18 * pawl + 4), py - 10), (cx + sgn * 210, py + 26)],
                  fill=(240, 200, 120, 255))
    # Otis in a top hat, arms out
    hx, hy = cx, py - 220
    ink = (250, 236, 210, 255)
    d.ellipse((hx - 30, hy - 30, hx + 30, hy + 30), fill=ink)
    d.rectangle((hx - 26, hy - 90, hx + 26, hy - 30), fill=(40, 28, 18, 255))
    d.rectangle((hx - 44, hy - 36, hx + 44, hy - 24), fill=(40, 28, 18, 255))
    d.line([(hx, hy + 30), (hx, hy + 140)], fill=ink, width=14)
    arm = 30 if t >= cut_t + 0.3 else 0
    d.line([(hx, hy + 60), (hx - 80, hy + 40 - arm)], fill=ink, width=12)
    d.line([(hx, hy + 60), (hx + 80, hy + 40 - arm)], fill=ink, width=12)
    d.line([(hx, hy + 140), (hx - 35, hy + 215)], fill=ink, width=12)
    d.line([(hx, hy + 140), (hx + 35, hy + 215)], fill=ink, width=12)
    if t >= cut_t + 0.35:
        paste_center(c, chip("SAFETY CATCH HOLDS", 48, SEPIA, (255, 222, 160)), W / 2, 1150,
                     pop(t, cut_t + 0.35))


def side(rx, cx):
    return 1 if rx > cx else -1


def sc_button(c, t, b):
    d = ImageDraw.Draw(c)
    # brushed steel panel
    x0, y0, x1, y1 = 240, 330, 840, 1260
    d.rounded_rectangle((x0, y0, x1, y1), 40, fill=(170, 178, 188, 255), outline=(230, 236, 242, 255), width=6)
    for y in range(y0 + 10, y1 - 10, 6):
        d.line([(x0 + 12, y), (x1 - 12, y)], fill=(160 + (y * 7) % 20, 168 + (y * 7) % 20, 178 + (y * 7) % 20, 255))
    # floor buttons
    for i, n in enumerate((4, 3, 2, 1)):
        bx, by = W / 2, 440 + i * 150
        d.ellipse((bx - 55, by - 55, bx + 55, by + 55), fill=(60, 66, 76, 255), outline=(220, 226, 232, 255), width=5)
        d.text((bx, by), str(n), font=font(56), fill=WHITE, anchor="mm")
    # open / close buttons
    press_t = C("button", 1) + 0.1
    pressed = press_t <= t < press_t + 0.25
    for j, kind in enumerate(("open", "close")):
        bx, by = W / 2 - 110 + j * 220, 1080
        fill = (60, 66, 76, 255)
        ring = (220, 226, 232, 255)
        if kind == "close" and t >= press_t:
            ring = YELLOW + (255,) if pressed else (220, 226, 232, 255)
        r = 62 if not (kind == "close" and pressed) else 56
        d.ellipse((bx - r, by - r, bx + r, by + r), fill=fill, outline=ring, width=6)
        s = 22
        d.rectangle((bx - 3, by - s, bx + 3, by + s), fill=WHITE)
        if kind == "open":  # <|> arrows point outward
            d.polygon([(bx - 10, by - s), (bx - 10, by + s), (bx - 10 - s, by)], fill=WHITE)
            d.polygon([(bx + 10, by - s), (bx + 10, by + s), (bx + 10 + s, by)], fill=WHITE)
        else:  # >|< arrows point inward
            d.polygon([(bx - 10 - s, by - s), (bx - 10 - s, by + s), (bx - 10, by)], fill=WHITE)
            d.polygon([(bx + 10 + s, by - s), (bx + 10 + s, by + s), (bx + 10, by)], fill=WHITE)
    # finger tapping the close button repeatedly
    if C("button", 1) - 0.2 <= t < C("button", 4):
        tap = abs(math.sin((t - press_t) * 9)) * 30
        fx, fy = W / 2 + 110 + 20, 1080 + 40 + tap
        d.rounded_rectangle((fx - 34, fy, fx + 34, fy + 260), 34, fill=(240, 196, 160, 255), outline=(120, 80, 60, 255),
                            width=4)
    headline(c, t, C("button", 0), "THE CLOSE BUTTON", 190, 84, WHITE)
    if t >= C("button", 3):
        stamp = text_img("SWITCHED OFF*", 110, RED, stroke=8, stroke_color=(40, 0, 0))
        paste_center(c, glow(stamp, RED), W / 2, 760, 2.0 - pop(t, C("button", 3), 0.25), rot=-12)
        paste_center(c, stamp, W / 2, 760, 2.0 - pop(t, C("button", 3), 0.25), rot=-12)
    if t >= C("button", 4):
        paste_center(c, chip("FIRE SERVICE MODE", 50, WHITE, RED), W / 2, 1300, pop(t, C("button", 4)))
        paste_center(c, text_img("*on many elevators", 34, (200, 210, 225)), W / 2, 1380, pop(t, C("button", 4)))


def sc_cta(c, t, b):
    lt = t - b["start"]
    s = pop(t, b["start"])
    pulse = 1 + 0.05 * math.sin(lt * 10)
    btn = chip("+ FOLLOW", 110, WHITE, RED)
    paste_center(c, glow(btn, RED), W / 2, 560, s * pulse)
    paste_center(c, btn, W / 2, 560, s * pulse)
    headline(c, t, b["start"] + 0.2, "everyday things,", 800, 84, WHITE)
    headline(c, t, b["start"] + 0.4, "EXPLAINED", 920, 110, YELLOW, YELLOW)
    # mini elevator going up and down
    d = ImageDraw.Draw(c)
    d.rectangle((W / 2 - 70, 1040, W / 2 + 70, 1300), outline=LINE + (255,), width=5)
    yy = 1180 + math.sin(lt * 3) * 90
    d.rounded_rectangle((W / 2 - 55, yy - 40, W / 2 + 55, yy + 40), 10, fill=CYAN + (255,))
    d.line([(W / 2, 1040), (W / 2, yy - 40)], fill=STEEL + (255,), width=5)


SCENES = {"otis": sc_otis, "button": sc_button, "cta": sc_cta}
BGS = {"otis": ((44, 30, 16), (255, 170, 80), (220, 180, 130)), "button": ((24, 28, 36), CYAN, (160, 170, 190)),
       "snap": (NAVY, RED, LINE), "brakes": (NAVY, RED, LINE)}


def beat_at(t):
    for b in TL:
        if t < b["end"]:
            return b
    return TL[-1]


def frame(t):
    b = beat_at(t)
    c = background(t, *BGS.get(b["id"], (NAVY, CYAN, LINE)))
    SCENES.get(b["id"], sc_world)(c, t, b)
    if t - b["start"] < 0.06 and b is not TL[0]:
        c.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, 80)))
    d = ImageDraw.Draw(c)
    d.rectangle((0, 0, W, 12), fill=(255, 255, 255, 40))
    d.rectangle((0, 0, int(W * t / TOTAL), 12), fill=YELLOW + (255,))
    return c.convert("RGB")


if PREVIEW:
    for t in PREVIEW:
        frame(t).save(f"{OUT}_{t:05.2f}.png")
    sys.exit()

proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                         "-pix_fmt", "yuv420p", OUT], stdin=subprocess.PIPE)
n = int(TOTAL * FPS)
for i in range(n):
    proc.stdin.write(frame(i / FPS).tobytes())
    if i % 300 == 0:
        print(f"frame {i}/{n}", flush=True)
proc.stdin.close()
proc.wait()
print("done", OUT)

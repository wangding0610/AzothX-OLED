"""Page renderers for the ROG Azoth X OLED (208x64, 4bpp = 16 gray levels).

Everything is drawn as *binary masks* and then pasted at an explicit gray level,
so no glyph edge ever lands on a gray value: antialiased text is what made the
first clock look soft. Levels used: 255 (primary), 165 (secondary), 90 (faint).
"""
from __future__ import annotations

import sys as _sys
try:                      # ???? UTF-8 ???????
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import datetime
from collections import deque

import psutil
from PIL import Image, ImageDraw, ImageFont

import pxfont

W, H = 208, 64

# 面板是 4bpp（16 级），这里只用 4 档做信息分层：主 / 次 / 弱 / 背景。
# 这是排版取舍，不是硬件实测的"只能显示 4 级"。数值 = 4bpp 值 × 17 取整。
L1, L2, L3, L4 = 255, 165, 90, 45

CJK_FONTS = [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"]
# 数字用 Segoe UI Bold：零没有斜杠、笔画粗，130 PPI 下最立得住。
# 字体缺失时依次回退：Segoe UI Bold -> Arial Bold -> Consolas Bold -> PIL 内置。
MONO_FONTS = [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
              r"C:\Windows\Fonts\consolab.ttf"]

# crisp = 纯二值（0/255）；soft = 4 级量化（0/90/165/255，边缘留一档过渡）
STYLE = "soft"

psutil.cpu_percent(interval=None)   # 预热，避免第一次读到 0


def font(size, mono=False):
    for path in (MONO_FONTS if mono else CJK_FONTS):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def canvas():
    return Image.new("L", (W, H), 0)


def _mask(text, f, pad=2):
    """Render text to a mask; 'crisp' keeps only 0/255, 'soft' keeps 4 levels."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    b = probe.textbbox((0, 0), text, font=f)
    w, h = b[2] - b[0] + pad * 2, b[3] - b[1] + pad * 2
    m = Image.new("L", (max(1, w), max(1, h)), 0)
    ImageDraw.Draw(m).text((pad - b[0], pad - b[1]), text, 255, font=f)
    if STYLE == "soft":
        # 量化到 4 档（与 L1..L4 同一套数值），避免锯齿又不留灰雾
        m = m.point(lambda v: 0 if v < 70 else (L3 if v < 150 else (L2 if v < 225 else L1)))
    else:
        m = m.point(lambda v: 255 if v >= 110 else 0)
    return m, b


def blit_text(img, xy, text, f, level=L1, anchor="la"):
    m, b = _mask(text, f)
    w, h = b[2] - b[0], b[3] - b[1]
    x, y = xy
    if anchor[0] == "c":
        x -= w // 2
    elif anchor[0] == "r":
        x -= w
    if anchor[1] == "c":
        y -= h // 2
    elif anchor[1] == "b":
        y -= h
    img.paste(level, (int(x), int(y)), m)
    return w, h


def fit_font(text, max_w, max_h, mono=False, start=None):
    size = start or max_h + 8
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    while size > 6:
        f = font(size, mono)
        b = d.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_w and b[3] - b[1] <= max_h:
            return f
        size -= 1
    return font(6, mono)


def bar(d, x, y, w, h, frac, fill=L1, back=L4, outline=L3):
    frac = max(0.0, min(1.0, frac))
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=back)
    if frac > 0:
        d.rectangle([x, y, x + max(1, int(w * frac)) - 1, y + h - 1], fill=fill)
    if outline:
        d.rectangle([x, y, x + w - 1, y + h - 1], outline=outline)


# ----------------------------------------------------------------- page: clock
def clock(now=None):
    now = now or datetime.datetime.now()
    img = canvas()
    d = ImageDraw.Draw(img)

    hm = now.strftime("%H:%M")
    # 给右列留出 78px，时间最多 124px 宽，两者不重叠
    f = fit_font(hm, 124, 48, mono=True)
    blit_text(img, (2, 4), hm, f, L1)

    # 右列必须用 5x7 点阵：矢量小字在 130 PPI 上会糊成一团噪点
    pxfont.draw(img, (W - 3, 8), now.strftime("%a").upper(), 2, L2, anchor="ra")
    pxfont.draw(img, (W - 3, 26), now.strftime("%m/%d"), 2, L1, anchor="ra")

    frac = (now.second + now.microsecond / 1e6) / 60.0
    d.rectangle([2, H - 5, W - 3, H - 2], fill=L4)
    w = int((W - 5) * frac)
    if w > 0:
        d.rectangle([2, H - 5, 1 + w, H - 2], fill=L1)
    return img


# ----------------------------------------------------------------- page: stats
_cpu_hist: deque[float] = deque(maxlen=40)


def stats(page_index=0):
    cpu = psutil.cpu_percent(interval=0.12)
    mem = psutil.virtual_memory()
    _cpu_hist.append(cpu)
    img = canvas()
    d = ImageDraw.Draw(img)

    blit_text(img, (2, 1), f"CPU {cpu:3.0f}%", font(14, True), L1)
    bar(d, 2, 18, 118, 7, cpu / 100.0)
    blit_text(img, (2, 30), f"MEM {mem.percent:3.0f}%", font(14, True), L1)
    bar(d, 2, 47, 118, 7, mem.percent / 100.0)

    gx, gy, gw, gh = 126, 2, 80, 34
    d.rectangle([gx, gy, gx + gw, gy + gh], outline=L4)
    if len(_cpu_hist) > 1:
        pts = []
        step = gw / (len(_cpu_hist) - 1)
        for i, v in enumerate(_cpu_hist):
            pts.append((gx + i * step, gy + gh - v / 100.0 * gh))
        d.line(pts, fill=L1, width=1)

    # 右下角只放一行（两行 14px 会在 64px 高里打架）
    pxfont.draw(img, (W - 3, 47), f"{mem.used / 1024**3:.0f}/{mem.total / 1024**3:.0f}G",
                2, L2, anchor="ra")
    return img


# ------------------------------------------------------------------- page: net
_net_hist: deque[float] = deque(maxlen=48)
_last = {"t": None, "sent": 0, "recv": 0}


def _human(n):
    for unit in ("B", "K", "M"):
        if n < 1024:
            return f"{n:.0f}{unit}/s"
        n /= 1024.0
    return f"{n:.1f}G/s"


def net():
    now = datetime.datetime.now().timestamp()
    io = psutil.net_io_counters()
    if _last["t"] is None:
        down = up = 0.0
    else:
        dt = max(1e-3, now - _last["t"])
        down = (io.bytes_recv - _last["recv"]) / dt
        up = (io.bytes_sent - _last["sent"]) / dt
    _last.update(t=now, sent=io.bytes_sent, recv=io.bytes_recv)
    _net_hist.append(down)
    peak = max(max(_net_hist), 1024.0)

    img = canvas()
    d = ImageDraw.Draw(img)
    pxfont.draw(img, (2, 1), f"D {_human(down)}", 3, L1)
    pxfont.draw(img, (2, 24), f"U {_human(up)}", 2, L2)

    gx, gy, gw, gh = 2, 40, W - 5, 21
    d.rectangle([gx, gy, gx + gw, gy + gh], outline=L4)
    n = len(_net_hist)
    if n > 1:
        pts = []
        for i, v in enumerate(_net_hist):
            x = gx + 1 + (gw - 2) * i / (n - 1)
            y = gy + gh - 1 - (v / peak) * (gh - 3)
            pts.append((x, y))
        d.line(pts, fill=L1, width=1)
    return img


# -------------------------------------------------------------- page: pomodoro
def pomodoro(remain_s, total_s, label="FOCUS"):
    frac = max(0.0, min(1.0, remain_s / total_s))
    img = canvas()
    d = ImageDraw.Draw(img)
    m, s = int(remain_s) // 60, int(remain_s) % 60
    txt = f"{m:02d}:{s:02d}"
    f = fit_font(txt, W - 8, 44, mono=True)
    blit_text(img, (W // 2, 12), txt, f, L1, "ca")
    pxfont.draw(img, (3, 2), label, 1, L3)
    bar(d, 8, H - 11, W - 16, 7, frac, back=L4)
    return img


# --------------------------------------------------------------- page: banner
def banner(text, sub=""):
    img = canvas()
    max_h = H - (16 if sub else 4)
    f = fit_font(text, W - 4, max_h)
    blit_text(img, (W // 2, max_h // 2 + 2), text, f, L1, "cc")
    if sub:
        blit_text(img, (W // 2, H - 2), sub, font(10), L2, "cb")
    return img


# ------------------------------------------------------------ page: big digits
def big_value(value, unit="", caption=""):
    img = canvas()
    f = fit_font(value, W - 40, 46, mono=True)
    blit_text(img, ((W - 26) // 2, 6), value, f, L1, "la")
    if unit:
        blit_text(img, (W - 3, 8), unit, font(13), L2, "ra")
    if caption:
        blit_text(img, (W // 2, H - 2), caption, font(10), L2, "cb")
    return img

"""Page renderers for the ROG Azoth X OLED (208x64, 4bpp = 16 gray levels).

Text uses binary masks by default, pasted at explicit brightness levels.
The optional soft style keeps quantized antialiasing. Pixel order is handled
by oled.render_4bpp; font styling cannot correct swapped adjacent pixels.
"""
from __future__ import annotations

import sys as _sys
try:                      # ???? UTF-8 ???????
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import datetime
from collections import deque
from functools import lru_cache

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
STYLE = "crisp"

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
BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8), name="Asia/Shanghai")
WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def beijing_time(now=None):
    """Current Beijing time (UTC+8, no DST); naive samples are Beijing wall time."""
    if now is None:
        return datetime.datetime.now(BEIJING_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=BEIJING_TZ)
    return now.astimezone(BEIJING_TZ)



@lru_cache(maxsize=2)
def _clock_digits(style):
    """Fixed-width cells and a common baseline prevent jumps as digits change."""
    f = fit_font("0123456789", 400, 35, mono=True, start=50)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    top = probe.textbbox((0, 0), "0123456789", font=f)[1]
    masks = []
    for digit in "0123456789":
        b = probe.textbbox((0, 0), digit, font=f)
        mask = Image.new("L", (33, 35), 0)
        ImageDraw.Draw(mask).text(((33 - (b[2] - b[0])) // 2 - b[0], -top),
                                  digit, font=f, fill=255)
        if style == "soft":
            mask = mask.point(lambda v: 0 if v < 70 else
                              (L3 if v < 150 else (L2 if v < 225 else L1)))
        else:
            mask = mask.point(lambda v: 255 if v >= 110 else 0)
        masks.append(mask)
    return tuple(masks)


def clock(now=None):
    now = beijing_time(now)
    img = canvas()
    d = ImageDraw.Draw(img)

    # Move the city/timezone strip to the bottom; shift the entire clock up 11px.
    d.rectangle((4, 57, 6, 59), fill=L1)
    pxfont.draw(img, (11, 55), "BEIJING", 1, L2)
    d.line((59, 58, 168, 58), fill=L4)
    pxfont.draw(img, (204, 55), "UTC+8", 1, L2, anchor="ra")

    digits = _clock_digits(STYLE)
    for x, digit in zip((4, 38, 88, 122), now.strftime("%H%M")):
        img.paste(L1, (x, 1), digits[int(digit)])
    d.rectangle((77, 11, 81, 15), fill=L2)
    d.rectangle((77, 25, 81, 29), fill=L2)

    d.line((165, 6, 165, 32), fill=L3)
    pxfont.draw(img, (190, 5), "SEC", 1, L3, anchor="ca")
    pxfont.draw(img, (190, 18), f"{now.second:02d}", 2, L2, anchor="ca")

    pxfont.draw(img, (4, 38), now.strftime("%m/%d"), 2, L2)
    pxfont.draw(img, (204, 38), WEEKDAYS[now.weekday()], 2, L2, anchor="ra")
    # Twelve five-second ticks provide a restrained, slowly filling minute dial.
    for tick in range(12):
        x = 80 + tick * 6
        level = L1 if tick < now.second // 5 else L4
        d.rectangle((x, 45, x + 3, 47), fill=level)
    return img


# ----------------------------------------------------------------- page: stats
def _compact_count(value):
    if value is None:
        return "--"
    for base, suffix in ((1_000_000_000_000, "T"), (1_000_000_000, "B"),
                         (1_000_000, "M"), (1_000, "K")):
        if value >= base:
            return f"{value / base:.1f}{suffix}"
    return str(int(value))


def codex_stats(snapshot):
    """Four native-stats values, fixed in place on a 208x64 display."""
    img = canvas()
    d = ImageDraw.Draw(img)
    counts = f"{_compact_count(snapshot.get('rounds'))} 轮   {_compact_count(snapshot.get('steps'))} 步"
    blit_text(img, (3, 0), counts, fit_font(counts, 150, 11, start=13), L2)
    pxfont.draw(img, (204, 4), "CODEX", 1, L3, anchor="ra")
    d.line((4, 15, 204, 15), fill=L4)

    value = snapshot.get("tps")
    speed = "--" if value is None else f"{value:.1f}"
    blit_text(img, (3, 17), speed, fit_font(speed, 142, 27, mono=True, start=40), L1)
    pxfont.draw(img, (204, 31), "TOK/S", 1, L2, anchor="ra")

    d.line((4, 48, 204, 48), fill=L4)
    pxfont.draw(img, (4, 55), "TOTAL TOKENS", 1, L3)
    total = _compact_count(snapshot.get("tokens"))
    scale = 2 if pxfont.text_width(total, 2) <= 116 else 1
    pxfont.draw(img, (204, 49 if scale == 2 else 55), total, scale, L2, anchor="ra")
    return img


# ------------------------------------------------------- pages: Claude, offline
def _at(timestamp, fmt="%H:%M"):
    moment = datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc)
    return beijing_time(moment).strftime(fmt)


def _elapsed(seconds):
    s = max(0, int(seconds or 0))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _header(img, text, label, level=L2, inverted=False, max_w=150):
    """Top line shared by the AI pages; inverted = needs the user's attention."""
    d = ImageDraw.Draw(img)
    if inverted:
        d.rectangle((0, 0, W - 1, 14), fill=L1)
    if text:
        blit_text(img, (3, 0), text, fit_font(text, max_w, 11, start=13), 0 if inverted else level)
    pxfont.draw(img, (204, 4), label, 1, 0 if inverted else L3, anchor="ra")
    d.line((4, 15, 204, 15), fill=L4)


def _totals(img, turns, steps, tokens):
    """Bottom line: rounds and steps on the left, cumulative tokens on the right."""
    counts = f"{_compact_count(turns)} 轮  {_compact_count(steps)} 步"
    blit_text(img, (3, 49), counts, fit_font(counts, 96, 11, start=13), L2)
    total = _compact_count(tokens)
    pxfont.draw(img, (204, 50), total, 2, L2, anchor="ra")
    pxfont.draw(img, (199 - pxfont.text_width(total, 2), 57), "TOTAL", 1, L3, anchor="ra")


def _limit_view(info, window, now):
    """(percent, elapsed share of the window); a passed reset leaves no known value."""
    if not info or info.get("pct") is None:
        return None, None
    reset = info.get("resets_at")
    if reset and reset <= now:
        return None, None
    return info["pct"], (max(0.0, min(1.0, 1 - (reset - now) / window)) if reset else None)


def _meter(img, d, y, label, pct, pace=None):
    """Thin bar like the terminal status line; the bright tick marks elapsed window time."""
    x, w = 106, 70
    hot = pct is not None and pct >= 80
    pxfont.draw(img, (86, y), label, 1, L3)
    d.rectangle((x, y + 2, x + w - 1, y + 4), fill=L4)
    filled = 0 if pct is None else round(min(100.0, pct) / 100 * w)
    if filled:
        d.rectangle((x, y + 2, x + filled - 1, y + 4), fill=L1 if hot else L2)
    if pace is not None:
        tick = x + min(w - 1, int(pace * w))
        d.line((tick, y, tick, y + 6), fill=L1)
    pxfont.draw(img, (204, y), "--" if pct is None else f"{pct:.0f}%", 1, L1 if hot else L2, anchor="ra")


def claude_state(snapshot):
    """(header text, brightness, inverted) for one Claude Code session."""
    waiting = snapshot.get("waiting")
    if waiting:
        word = "等待回答" if waiting.get("kind") == "question" else "等待确认"
        return f"{word} {_elapsed(waiting.get('elapsed'))}", L1, True
    state = snapshot.get("state")
    elapsed = snapshot.get("turn_elapsed")
    suffix = "" if elapsed is None else f" {_elapsed(elapsed)}"
    if state == "working":
        return f"思考中{suffix}", L1, False
    if state == "tool":
        return f"运行 {snapshot.get('tool') or '工具'}{suffix}", L1, False
    if state == "interrupted":
        return "已中断", L2, False
    if state == "stopped":
        return "已停止", L3, False
    if state == "new":
        return "新会话", L2, False
    done = snapshot.get("done_ts")
    return ("已完成 " + _at(done)) if done else "已完成", L2, False


def ai_offline(label, title, detail="", bottom=None):
    """Explicit empty state for an AI page whose app is closed or idle."""
    img = canvas()
    _header(img, detail, label, L3)
    blit_text(img, (104, 31), title, fit_font(title, 196, 20, start=22), L2, anchor="cc")
    if bottom is not None:
        d = ImageDraw.Draw(img)
        d.line((4, 48, 204, 48), fill=L4)
        bottom(img, d)
    return img


def codex_offline(title, last=None):
    detail = f"上次 {_at(last['timestamp'])}" if last and last.get("timestamp") else ""
    bottom = (lambda img, d: _totals(img, last.get("rounds"), last.get("steps"), last.get("tokens"))) \
        if last else None
    return ai_offline("CODEX", title, detail, bottom)


def _claude_offline(view, now):
    last = view.get("last")
    detail = ""
    if last:
        detail = (f"上次 {_at(last['updated'])} · {_compact_count(last.get('turns'))}轮 "
                  f"{_compact_count(last.get('tokens'))}")
    limits = view.get("limits") or {}

    def bottom(img, d):
        for x, anchor, name, key, window in ((4, "la", "5H", "five_hour", 5 * 3600),
                                             (204, "ra", "WK", "seven_day", 7 * 86400)):
            info = limits.get(key)
            pct, _ = _limit_view(info, window, now)
            text = f"{name} --"
            if pct is not None:
                text = f"{name} {pct:.0f}%"
                if info.get("resets_at"):
                    reset = info["resets_at"]
                    when = _at(reset) if key == "five_hour" else \
                        f"{WEEKDAYS[beijing_time(datetime.datetime.fromtimestamp(reset, datetime.timezone.utc)).weekday()]} {_at(reset)}"
                    text += f" {when}"
            pxfont.draw(img, (x, 53), text, 1, L2, anchor=anchor + "a")

    return ai_offline("CLAUDE", "Claude 未启动", detail, bottom if limits else None)


def claude_stats(view, now=None):
    """The Claude Code status line on 208x64: state, speed, context and usage limits."""
    now = datetime.datetime.now().timestamp() if now is None else now
    session = view.get("session")
    if not session:
        return _claude_offline(view, now)
    img = canvas()
    d = ImageDraw.Draw(img)
    text, level, inverted = claude_state(session)
    count = view.get("count") or 1
    _header(img, text, f"CLAUDE X{count}" if count > 1 else "CLAUDE", level, inverted,
            max_w=140 if count > 1 else 150)

    tps = session.get("tps")
    speed = "--" if tps is None else f"{tps:.1f}"
    blit_text(img, (3, 15), speed, fit_font(speed, 76, 19, mono=True, start=30), L1)
    pxfont.draw(img, (4, 40), "TOK/S", 1, L3)
    d.line((82, 18, 82, 46), fill=L4)

    # Usage limits are account-wide: prefer the newest values from any session.
    limits = view.get("limits") or {}
    _meter(img, d, 18, "CTX", session.get("context"))
    _meter(img, d, 28, "5H", *_limit_view(limits.get("five_hour") or session.get("five_hour"), 5 * 3600, now))
    _meter(img, d, 38, "WK", *_limit_view(limits.get("seven_day") or session.get("seven_day"), 7 * 86400, now))

    d.line((4, 48, 204, 48), fill=L4)
    _totals(img, session.get("turns"), session.get("steps"), session.get("tokens"))
    return img


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

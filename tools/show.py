"""Push ready-made pages to the keyboard OLED.

    python show.py clock                 # 时钟，每秒刷新
    python show.py stats                 # CPU/内存 + 折线
    python show.py net                   # 上下行速率 + 曲线
    python show.py pomodoro -m 25        # 番茄钟
    python show.py text "你好" 副标题     # 大字 + 小字
    python show.py blank                 # 黑屏

    python show.py clock --once          # 只推一次
    python show.py clock -i 1            # 刷新间隔（秒）
"""
from __future__ import annotations

import sys as _sys
try:                      # ???? UTF-8 ???????
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import argparse
import time

import pages
from oled import RogOled, dongle_pairing, render_4bpp

W, H = pages.W, pages.H


def connect(wait_link=20.0):
    p = dongle_pairing()
    rid = p["ctrl_report_id"] if p else 2
    chunk = 59 if p else 60
    if p:
        print(f"OMNI receiver: paired pid={p['paired_pid']} ctrl rid={rid}")
    else:
        print("no pairing table (direct keyboard?): assuming rid=2, chunk=60")
    return RogOled(0xFF00, rid, chunk=chunk, verbose=False, wait_link=wait_link)


def push(dev, img, frames=2, duration=1000):
    payload = bytearray()
    payload += frames.to_bytes(2, "little")
    for _ in range(frames):
        payload += duration.to_bytes(2, "little")
    payload += render_4bpp(img, W, H) * frames
    dev.animation_upload(bytes(payload))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", choices=["clock", "stats", "net", "pomodoro", "text", "blank"])
    ap.add_argument("value", nargs="?", default="")
    ap.add_argument("sub", nargs="?", default="")
    ap.add_argument("-i", "--interval", type=float, default=1.0)
    ap.add_argument("-m", "--minutes", type=float, default=25.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--preview", action="store_true", help="只存 PNG 不推屏")
    ap.add_argument("--style", choices=["crisp", "soft"], default="crisp",
                    help="crisp=硬边文字（默认）; soft=4 级量化抗锯齿")
    ap.add_argument("--wait-link", type=float, default=20.0,
                    help="开推前最多等多少秒让键盘醒过来（默认 20 秒）")
    args = ap.parse_args()

    pages.STYLE = args.style

    if args.page == "pomodoro":
        total = args.minutes * 60
        start = time.time()

        def make():
            return pages.pomodoro(max(0.0, total - (time.time() - start)), total)
    elif args.page == "clock":
        make = pages.clock
    elif args.page == "stats":
        make = pages.stats
    elif args.page == "net":
        make = pages.net
    elif args.page == "text":
        make = lambda: pages.banner(args.value, args.sub)
    else:
        make = lambda: pages.canvas()

    img = make()
    img.save("preview.png")
    if args.preview:
        print("preview.png 已生成")
        return

    dev = connect(args.wait_link)
    try:
        n = 0
        while True:
            img = make()
            push(dev, img)
            n += 1
            if args.once or args.page in ("text", "blank"):
                break
            # 已经画过的页面不再重复打印，避免刷屏
            time.sleep(max(0.2, args.interval - 0.7))
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        dev.close()


if __name__ == "__main__":
    main()

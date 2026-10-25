"""Push ready-made pages to the keyboard OLED.

    python show.py clock                 # 北京时间（UTC+8），保留秒数，实时位图更新
    python show.py stats                 # CPU/内存 + 折线
    python show.py net                   # 上下行速率 + 曲线
    python show.py pomodoro -m 25        # 番茄钟
    python show.py text "你好" 副标题     # 大字 + 小字
    python show.py blank                 # 黑屏

    python show.py clock --once          # 只推一次
    python show.py clock -i 2            # 刷新间隔（秒）
"""
from __future__ import annotations

import sys as _sys
try:                      # ???? UTF-8 ???????
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import argparse
import contextlib
import io
import time
from pathlib import Path

import pages
from oled import RogOled, clock_connections, render_4bpp

W, H = pages.W, pages.H


def connect(wait_link=20.0):
    errors = []
    for target in clock_connections():
        dev = None
        try:
            dev = RogOled(target["usage_page"], target["report_id"], path=target["path"],
                          chunk=target["chunk"], verbose=False, wait_link=wait_link)
            dev.configure_live(W, H)
        except OSError as exc:
            if dev is not None:
                dev.close()
            errors.append(f"{target['transport']}: {exc}")
            continue
        print(f"[connected] {target['transport']}: ctrl rid={target['report_id']}, "
              f"chunk={target['chunk']}", flush=True)
        return dev
    raise OSError("; ".join(errors))


def push(dev, img, frames=2, duration=1000):
    payload = bytearray()
    payload += frames.to_bytes(2, "little")
    for _ in range(frames):
        payload += duration.to_bytes(2, "little")
    payload += render_4bpp(img, W, H) * frames
    dev.animation_upload(bytes(payload))


def push_live(dev, img):
    dev.live_upload(render_4bpp(img, W, H), W, H)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", choices=["clock", "stats", "net", "pomodoro", "text", "blank"])
    ap.add_argument("value", nargs="?", default="")
    ap.add_argument("sub", nargs="?", default="")
    ap.add_argument("-i", "--interval", type=float, default=None,
                    help="目标刷新间隔（默认 1 秒），实际间隔受上传耗时影响")
    ap.add_argument("-m", "--minutes", type=float, default=25.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--preview", action="store_true", help="只存 PNG 不推屏")
    ap.add_argument("--quiet", action="store_true", help="只输出运行状态，隐藏逐包日志")
    ap.add_argument("--display-state", type=Path,
                    help="后台显示模式文件；可在北京时钟、Codex 和 Claude 统计之间切换")
    ap.add_argument("--style", choices=["crisp", "soft"], default="crisp",
                    help="crisp=硬边文字（默认）; soft=4 级量化抗锯齿")
    ap.add_argument("--wait-link", type=float, default=20.0,
                    help="开推前最多等多少秒让键盘醒过来（默认 20 秒）")
    args = ap.parse_args()
    if args.interval is None:
        args.interval = 1.0
    if args.interval <= 0:
        ap.error("--interval 必须大于 0")

    pages.STYLE = args.style
    managed = None

    if args.page == "pomodoro":
        total = args.minutes * 60
        start = time.time()

        def make():
            return pages.pomodoro(max(0.0, total - (time.time() - start)), total)
    elif args.page == "clock":
        make = pages.clock
        if args.display_state:
            from codex_stats import ManagedDisplay
            managed = ManagedDisplay(args.display_state)
            make = managed.frame
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

    if managed is not None:
        managed.start()
    dev = None
    upload = push_live if args.page == "clock" else push
    try:
        waiting = False
        announced = False
        last_health = 0.0
        last_error = None
        last_wait_log = 0.0
        uploaded = 0
        last_display = None
        while True:
            started = time.monotonic()
            try:
                if dev is None:
                    dev = connect(args.wait_link)
                img = make()
                if args.quiet:
                    with contextlib.redirect_stdout(io.StringIO()):
                        upload(dev, img)
                else:
                    upload(dev, img)
            except OSError as exc:
                if dev is not None:
                    dev.close()
                    dev = None
                if args.once or args.page in ("text", "blank"):
                    raise
                if str(exc) != last_error or time.monotonic() - last_wait_log >= 60:
                    print(f"[waiting] {exc}; rediscovering connection in 3s.", flush=True)
                    last_wait_log = time.monotonic()
                last_error = str(exc)
                waiting = True
                time.sleep(3.0)
                continue
            if args.quiet and (waiting or not announced):
                detail = pages.beijing_time().isoformat(timespec="seconds") if args.page == "clock" else args.page
                print(f"[running] {detail}; upload confirmed", flush=True)
            if managed is not None and managed.current_mode != last_display:
                print(f"[display] {managed.current_mode}; upload confirmed", flush=True)
                last_display = managed.current_mode
            waiting = False
            last_error = None
            announced = True
            uploaded += 1
            if args.quiet and time.monotonic() - last_health >= 60:
                print(f"[health] {pages.beijing_time().isoformat(timespec='seconds')}; "
                      f"successful uploads={uploaded}", flush=True)
                last_health = time.monotonic()
            if args.once or args.page in ("text", "blank"):
                break
            # Account for actual USB transfer time rather than a fixed estimate.
            time.sleep(max(0.05, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        if dev is not None:
            dev.close()
        if managed is not None:
            managed.close()


if __name__ == "__main__":
    main()

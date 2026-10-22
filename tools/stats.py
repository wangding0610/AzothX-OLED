"""Live system stats on the keyboard OLED (loops until Ctrl+C).

    python stats.py --width 256 --height 64
"""
from __future__ import annotations

import argparse
import datetime
import time

import psutil

from oled import RogOled, dongle_pairing, render_4bpp, text_image


def read_cpu_temp():
    try:
        import pythoncom  # noqa: F401
        import wmi

        w = wmi.WMI(namespace="root\\wmi")
        vals = [t.CurrentTemperature for t in w.MSAcpi_ThermalZoneTemperature()]
        return max(vals) / 10.0 - 273.15 if vals else None
    except Exception:
        return None


def frame(lines, width, height):
    from PIL import Image, ImageDraw

    img = Image.new("L", (width, height), 0)
    d = ImageDraw.Draw(img)
    from oled import _font

    f = _font(max(10, height // len(lines) - 2))
    y = 0
    for line in lines:
        d.text((2, y), line, 255, font=f)
        y += (height // len(lines))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=256)
    ap.add_argument("--height", type=int, default=64)
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    pairing = dongle_pairing()
    rid = pairing["ctrl_report_id"] if pairing else 2
    chunk = 59 if pairing else 60
    dev = RogOled(0xFF00, rid, chunk=chunk, verbose=False, wait_link=15)

    try:
        while True:
            cpu = psutil.cpu_percent(interval=0.4)
            mem = psutil.virtual_memory().percent
            temp = read_cpu_temp()
            now = datetime.datetime.now().strftime("%H:%M:%S")
            lines = [f"CPU {cpu:4.0f}%  RAM {mem:4.0f}%"]
            if temp:
                lines.append(f"TEMP {temp:4.1f}C")
            lines.append(now)
            img = frame(lines, args.width, args.height)
            payload = (1).to_bytes(2, "little") + int(args.interval * 1000).to_bytes(2, "little") \
                + render_4bpp(img, args.width, args.height)
            dev.animation_upload(payload)
            time.sleep(max(0.2, args.interval - 0.6))
    except KeyboardInterrupt:
        pass
    finally:
        dev.close()


if __name__ == "__main__":
    main()

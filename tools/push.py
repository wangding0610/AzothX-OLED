"""Push the name at an arbitrary geometry: python push.py --width 320 --height 64 --frames 2"""
import argparse
import time

from PIL import Image, ImageDraw

from oled import RogOled, _font, crisp, dongle_pairing, render_4bpp

ap = argparse.ArgumentParser()
ap.add_argument("--width", type=int, default=208)
ap.add_argument("--height", type=int, default=64)
ap.add_argument("--frames", type=int, default=2)
ap.add_argument("--duration", type=int, default=1000)
ap.add_argument("--text", default="LITTLE CODE\nSAUCE")
ap.add_argument("--thresh", type=int, default=140)
ap.add_argument("--tag", default="name")
args = ap.parse_args()

W, H = args.width, args.height
lines = args.text.split("\\n") if "\\n" in args.text else args.text.split("\n")

img = Image.new("L", (W, H), 0)
d = ImageDraw.Draw(img)
line_h = H // len(lines)
y = 0
for text in lines:
    size = line_h + 2
    while size > 6:
        f = _font(size)
        b = d.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= W - 2 and b[3] - b[1] <= line_h:
            break
        size -= 1
    f = _font(size)
    b = d.textbbox((0, 0), text, font=f)
    d.text(((W - (b[2] - b[0])) // 2 - b[0], y + (line_h - (b[3] - b[1])) // 2 - b[1]),
           text, 255, font=f)
    y += line_h
img = crisp(img, args.thresh)
img.save("preview.png")
img.resize((W * 4, H * 4), Image.NEAREST).save("preview_zoom.png")
print(f"render {W}x{H}, {len(lines)} lines, font size {size}")

payload = bytearray()
payload += args.frames.to_bytes(2, "little")
for _ in range(args.frames):
    payload += args.duration.to_bytes(2, "little")
payload += render_4bpp(img, W, H) * args.frames
print(f"payload {len(payload)} bytes -> {(len(payload) + 58) // 59} packets")

pairing = dongle_pairing()
rid = pairing["ctrl_report_id"] if pairing else 2
for attempt in range(1, 4):
    dev = RogOled(0xFF00, rid, chunk=59 if pairing else 60, verbose=False, wait_link=20)
    try:
        print(f"{args.tag} attempt {attempt}")
        dev.animation_upload(bytes(payload))
        print("ok")
        break
    except Exception as exc:  # noqa: BLE001
        print("  aborted:", exc)
        time.sleep(2.0)
    finally:
        dev.close()

"""One-key test matrix for the OLED framebuffer format.

Run it, look at the keyboard after each push, press Enter for the next one.
Write down the NAME of the variant where "YG" is actually readable.

    python matrix.py                 # 256x64, glyph scale 9
    python matrix.py --width 320 --height 64
"""
import argparse
import sys
import time

from PIL import Image

from oled import RogOled, dongle_pairing
from push_pixel import render_text


def pack_4bpp(img, W, H, hi_left=True):
    px = img.load()
    out = bytearray()
    for y in range(H):
        for x in range(0, W, 2):
            a = (px[x, y] & 0xF0) >> 4
            b = (px[x + 1, y] & 0xF0) >> 4
            out.append((a << 4 | b) if hi_left else (b << 4 | a))
    return bytes(out)


def pack_1bpp(img, W, H, msb_first=True, pages=False):
    px = img.load()
    out = bytearray()
    if not pages:
        for y in range(H):
            for xb in range(W // 8):
                b = 0
                for j in range(8):
                    if px[xb * 8 + j, y] > 127:
                        b |= (0x80 >> j) if msb_first else (1 << j)
                out.append(b)
    else:
        for page in range(H // 8):
            for x in range(W):
                b = 0
                for j in range(8):
                    if px[x, page * 8 + j] > 127:
                        b |= (0x80 >> j) if msb_first else (1 << j)
                out.append(b)
    return bytes(out)


def pack_rgb565(img, W, H, little=True):
    px = img.load()
    out = bytearray()
    for y in range(H):
        for x in range(W):
            v = px[x, y]
            r = g = b = v >> 3
            val = (r << 11) | (g << 5) | b
            out += val.to_bytes(2, "little" if little else "big")
    return bytes(out)


def variants(W, H):
    return [
        ("4bpp_hi_left", pack_4bpp(img, W, H, True)),
        ("4bpp_lo_left", pack_4bpp(img, W, H, False)),
        ("1bpp_row_msb", pack_1bpp(img, W, H, True, False)),
        ("1bpp_row_lsb", pack_1bpp(img, W, H, False, False)),
        ("1bpp_page_msb", pack_1bpp(img, W, H, True, True)),
        ("1bpp_page_lsb", pack_1bpp(img, W, H, False, True)),
        ("rgb565_le", pack_rgb565(img, W, H, True)),
        ("rgb565_be", pack_rgb565(img, W, H, False)),
    ]


ap = argparse.ArgumentParser()
ap.add_argument("--width", type=int, default=208)
ap.add_argument("--height", type=int, default=64)
ap.add_argument("--scale", type=int, default=9)
ap.add_argument("--text", default="YG")
ap.add_argument("--list", action="store_true")
ap.add_argument("--only", default="")
args = ap.parse_args()

W, H = args.width, args.height
img = render_text(args.text, args.scale, W, H)
img.resize((W * 4, H * 4), Image.NEAREST).save("matrix_preview_zoom.png")

vs = variants(W, H)
if args.list:
    for name, fb in vs:
        fr = 1 if len(fb) > 20000 else 2
        print(f"{name:16s} {len(fb):6d} bytes/frame, {fr} frame(s)  "
              f"{(len(fb) * fr + 6 + 58) // 59:4d} packets")
    sys.exit(0)

if args.only:
    vs = [v for v in vs if v[0] == args.only]

pairing = dongle_pairing()
rid = pairing["ctrl_report_id"] if pairing else 2
print(f"panel {W}x{H}, glyph {args.text!r} x{args.scale}")
print(f"looking for the variant where the letters are READABLE\n")

for idx, (name, fb) in enumerate(vs, 1):
    payload = bytearray()
    frames = 1 if len(fb) > 20000 else 2   # big RGB frames stay under the packet budget
    payload += frames.to_bytes(2, "little")
    for _ in range(frames):
        payload += (1000).to_bytes(2, "little")
    payload += fb * frames
    packets = (len(payload) + 58) // 59
    print(f"[{idx}/{len(vs)}] {name}  ({len(fb)} B/frame, {packets} packets)")

    ok = False
    for attempt in range(1, 3):
        dev = RogOled(0xFF00, rid, chunk=59 if pairing else 60, verbose=False, wait_link=15)
        try:
            dev.animation_upload(bytes(payload))
            ok = True
            break
        except Exception as exc:  # noqa: BLE001
            print("   upload aborted:", exc)
            time.sleep(2)
        finally:
            dev.close()

    print("   " + ("uploaded" if ok else "FAILED to upload"))
    input("   看屏幕 -> 记住这个编号，按回车切下一个 ... ")

print("\n把你觉得字最清楚的那个编号告诉我（比如 3 = 1bpp_row_lsb）。")

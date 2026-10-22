"""Try alternative framebuffer packings (the 4bpp/2px-per-byte assumption is wrong).

    python push1bpp.py "YG" --scale 9 --packing row_msb
    python push1bpp.py "YG" --scale 9 --packing row_lsb
    python push1bpp.py "YG" --scale 9 --packing page_msb
    python push1bpp.py "YG" --scale 9 --packing page_lsb
"""
import argparse
import time

from PIL import Image

from oled import RogOled, dongle_pairing
from push_pixel import render_text


def pack(img, W, H, packing):
    px = img.load()
    out = bytearray()
    if packing in ("row_msb", "row_lsb"):
        for y in range(H):
            for xb in range(W // 8):
                b = 0
                for j in range(8):
                    on = px[xb * 8 + j, y] > 127
                    if on:
                        b |= (0x80 >> j) if packing == "row_msb" else (1 << j)
                out.append(b)
    elif packing in ("page_msb", "page_lsb"):
        for page in range(H // 8):
            for x in range(W):
                b = 0
                for j in range(8):
                    on = px[x, page * 8 + j] > 127
                    if on:
                        b |= (1 << j) if packing == "page_lsb" else (0x80 >> j)
                out.append(b)
    else:
        raise SystemExit("unknown packing")
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="YG")
    ap.add_argument("--scale", type=int, default=9)
    ap.add_argument("--width", type=int, default=256)
    ap.add_argument("--height", type=int, default=64)
    ap.add_argument("--packing", default="row_msb")
    ap.add_argument("--frames", type=int, default=2)
    args = ap.parse_args()

    W, H = args.width, args.height
    img = render_text(args.text, args.scale, W, H)
    img.save(f"preview_{args.packing}.png")
    img.resize((W * 4, H * 4), Image.NEAREST).save("preview_zoom.png")
    fb = pack(img, W, H, args.packing)
    print(f"{args.packing}: {W}x{H} -> {len(fb)} bytes/frame, "
          f"{(len(fb) * args.frames + 6 + 58) // 59} packets")

    payload = bytearray()
    payload += args.frames.to_bytes(2, "little")
    for _ in range(args.frames):
        payload += (1000).to_bytes(2, "little")
    payload += fb * args.frames

    pairing = dongle_pairing()
    rid = pairing["ctrl_report_id"] if pairing else 2
    for attempt in range(1, 4):
        dev = RogOled(0xFF00, rid, chunk=59 if pairing else 60, verbose=False, wait_link=20)
        try:
            print("attempt", attempt)
            dev.animation_upload(bytes(payload))
            print("ok")
            break
        except Exception as exc:  # noqa: BLE001
            print("  aborted:", exc)
            time.sleep(2)
        finally:
            dev.close()


if __name__ == "__main__":
    main()

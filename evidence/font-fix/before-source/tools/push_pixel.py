"""True 5x7 bitmap font -> integer upscale. Zero antialias anywhere in the chain.

    python push_pixel.py "YG" --scale 9
    python push_pixel.py "LITTLE CODE" --scale 3
"""
import argparse
import time

from PIL import Image

from oled import RogOled, dongle_pairing, render_4bpp

FONT = {
    "A": "01110 10001 10001 11111 10001 10001 10001",
    "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110",
    "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111",
    "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111",
    "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "11111 00100 00100 00100 00100 00100 11111",
    "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001",
    "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001",
    "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110",
    "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101",
    "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110",
    "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110",
    "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 11011 10001",
    "X": "10001 01010 00100 00100 00100 01010 10001",
    "Y": "10001 01010 00100 00100 00100 00100 00100",
    "Z": "11111 00001 00010 00100 01000 10000 11111",
    "0": "01110 10001 10011 10101 11001 10001 01110",
    "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111",
    "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010",
    "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110",
    "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110",
    "9": "01110 10001 10001 01111 00001 00010 01100",
    " ": "00000 00000 00000 00000 00000 00000 00000",
    "-": "00000 00000 00000 11111 00000 00000 00000",
    ".": "00000 00000 00000 00000 00000 01100 01100",
    "!": "00100 00100 00100 00100 00100 00000 00100",
}


def render_text(text, scale, width, height, gap=1):
    glyphs = []
    for ch in text.upper():
        rows = FONT.get(ch, FONT[" "]).split()
        glyphs.append([[c == "1" for c in row] for row in rows])
    gw, gh = 5, 7
    total_w = len(glyphs) * (gw + gap) * scale - gap * scale
    img = Image.new("L", (width, height), 0)
    px = img.load()
    x0 = max(0, (width - total_w) // 2)
    y0 = max(0, (height - gh * scale) // 2)
    for gi, glyph in enumerate(glyphs):
        for y, row in enumerate(glyph):
            for x, on in enumerate(row):
                if not on:
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        X = x0 + (gi * (gw + gap) + x) * scale + dx
                        Y = y0 + y * scale + dy
                        if 0 <= X < width and 0 <= Y < height:
                            px[X, Y] = 255
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="YG")
    ap.add_argument("--scale", type=int, default=9)
    ap.add_argument("--width", type=int, default=256)
    ap.add_argument("--height", type=int, default=64)
    ap.add_argument("--frames", type=int, default=2)
    args = ap.parse_args()

    W, H = args.width, args.height
    img = render_text(args.text, args.scale, W, H)
    img.save("preview.png")
    img.resize((W * 4, H * 4), Image.NEAREST).save("preview_zoom.png")
    print(f"{args.text!r} @ x{args.scale} -> {W}x{H} (pixel font, 100% binary)")

    payload = bytearray()
    payload += args.frames.to_bytes(2, "little")
    for _ in range(args.frames):
        payload += (1000).to_bytes(2, "little")
    payload += render_4bpp(img, W, H) * args.frames

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

"""Resolution / scaling probe: tells you whether 256x64 is really the panel grid.

    python probe.py                # 256x64
    python probe.py --width 320 --height 64

Read it like this:
  * corners light up + 1px stripes stay 1px  -> geometry correct, blur is a
    rendering/contrast issue, not scaling
  * stripes turn uneven / moire, or a corner block stays dark -> the firmware is
    scaling or clipping, try another --width/--height combination
"""
from PIL import Image, ImageDraw

from oled import RogOled, dongle_pairing, render_4bpp

import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--width", type=int, default=256)
ap.add_argument("--height", type=int, default=64)
args = ap.parse_args()
W, H = args.width, args.height

img = Image.new("L", (W, H), 0)
d = ImageDraw.Draw(img)

# 1 px border: any scaling immediately shows as uneven thickness
d.rectangle([0, 0, W - 1, H - 1], outline=255)

# 1 px vertical stripes in the top third
for x in range(2, W - 1, 2):
    d.point((x, 3), fill=255)
    d.point((x, 4), fill=255)

# 1 px horizontal stripes in the middle
for y in range(H // 3, 2 * H // 3, 2):
    d.line([(2, y), (W - 3, y)], fill=255)

# 2px checkerboard bottom third
y0 = 2 * H // 3 + 1
for y in range(y0, H - 2):
    for x in range(2, W - 2):
        if ((x // 2) + (y // 2)) % 2 == 0:
            d.point((x, y), fill=255)

# corner markers: single pixels at the four extreme points
for pt in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
    d.point(pt, fill=255)

img.save("probe.png")
payload = (1).to_bytes(2, "little") + (0).to_bytes(2, "little") + render_4bpp(img, W, H)

pairing = dongle_pairing()
rid = pairing["ctrl_report_id"] if pairing else 2
dev = RogOled(0xFF00, rid, chunk=59 if pairing else 60, verbose=False, wait_link=20)
try:
    dev.animation_upload(payload)
finally:
    dev.close()

"""Recovery experiments: find what state the OLED transfer is stuck in."""
import time

import hid
from PIL import Image

from oled import (CMD_ANIMATION, CMD_BANNER, RogOled, dongle_pairing,
                  render_4bpp, SUB_ANIM_MODE, SUB_ANIM_SHOW)

W, H = 256, 64
pairing = dongle_pairing()
rid = pairing["ctrl_report_id"] if pairing else 2
print("pairing:", pairing)


def raw(dev, buf):
    buf[0] = rid
    return dev.write(bytes(buf))


def probe(dev, cmd, sub, payload=b"", wait=1.5, tag=""):
    buf = bytearray(65)
    buf[1] = cmd
    buf[2] = sub
    buf[3:3 + len(payload)] = payload
    raw(dev, buf)
    end = time.time() + wait
    got = []
    while time.time() < end:
        d = dev.read(64, 120)
        if d:
            got.append(bytes(d))
    print(f"  {tag or f'{cmd:02x}/{sub:02x}'}: " + (" | ".join(g[:8].hex(" ") for g in got) or "no response"))
    return got


info = None
for d in hid.enumerate(0x0B05, 0x1ACE):
    if d["usage_page"] == 0xFF00:
        info = d
        break
dev = hid.device()
dev.open_path(info["path"])
dev.set_nonblocking(0)

print("\n== state probes ==")
probe(dev, CMD_ANIMATION, SUB_ANIM_SHOW, tag="0x61 show")
probe(dev, 0x24, 0x01, tag="0x24 mode")
probe(dev, 0xA1, 0x00, tag="0xA1 sn")

print("\n== cancel transfer (mode total=0) ==")
buf = bytearray(65)
buf[1] = CMD_ANIMATION
buf[2] = SUB_ANIM_MODE
buf[5:9] = (0).to_bytes(4, "little")
raw(dev, buf)
probe(dev, CMD_ANIMATION, SUB_ANIM_SHOW, tag="show after cancel")

print("\n== short 1-frame upload (139 packets) via RogOled ==")
dev.close()
img = Image.new("L", (W, H), 0)
from PIL import ImageDraw
d = ImageDraw.Draw(img)
d.rectangle([0, 0, W - 1, H - 1], outline=255)
d.line([(0, 32), (W - 1, 32)], fill=255)
payload = (1).to_bytes(2, "little") + (500).to_bytes(2, "little") + render_4bpp(img, W, H)
oled = RogOled(0xFF00, rid, chunk=59, verbose=False, wait_link=10)
try:
    oled.animation_upload(payload)
except Exception as exc:  # noqa: BLE001
    print("  short upload failed:", exc)
finally:
    oled.close()

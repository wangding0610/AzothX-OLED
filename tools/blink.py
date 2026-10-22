"""Blink test + event capture.

Pushes a white/black/white animation (impossible to miss), then listens on the
notify channel so we can see whether the keyboard emits OLED page / key events.
"""
import time

import hid
from PIL import Image

from oled import RogOled, dongle_pairing, render_4bpp

W, H = 256, 64
pairing = dongle_pairing()
rid = pairing["ctrl_report_id"] if pairing else 2
notify = pairing["notify_report_id"] if pairing else 4
print("pairing:", pairing, "notify rid:", notify)

white = Image.new("L", (W, H), 255)
black = Image.new("L", (W, H), 0)
frames = [white, black, white]
durs = [400, 400, 400]

payload = bytearray()
payload += len(frames).to_bytes(2, "little")
for d in durs:
    payload += d.to_bytes(2, "little")
for f in frames:
    payload += render_4bpp(f, W, H)

dev = RogOled(0xFF00, rid, chunk=59, verbose=False, wait_link=20)
try:
    print("pushing blink animation ...")
    dev.animation_upload(bytes(payload))
finally:
    dev.close()

# ---- listen for whatever the keyboard pushes on the notify channel
evt = None
for d in hid.enumerate(0x0B05, 0x1ACE):
    if d["usage_page"] == 0xFFC0:
        evt = hid.device()
        evt.open_path(d["path"])
        evt.set_nonblocking(0)
        break

if evt is None:
    raise SystemExit("notify channel not found")

print("\n正在监听键盘上报 15 秒 —— 现在按几下键盘（尤其是切屏幕的那个键）")
end = time.time() + 15
seen = 0
while time.time() < end:
    data = evt.read(64, 150)
    if data:
        seen += 1
        print(f"  evt {seen:02d}: {bytes(data).hex(' ')}")
print(f"共收到 {seen} 条上报")
evt.close()

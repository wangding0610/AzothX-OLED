"""Distinguish 'wrong channel' from 'device not linked': query dongle SN vs device SN."""
import time

import hid

VID, PID = 0x0B05, 0x1ACE


def open_page(page):
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == page:
            dev = hid.device()
            dev.open_path(d["path"])
            dev.set_nonblocking(0)
            return dev, d
    return None, None


def tx(dev, tag, rid, payload, wait=1.5):
    buf = bytearray(64)
    buf[0] = rid
    buf[1:1 + len(payload)] = payload
    dev.write(bytes(buf))
    end = time.time() + wait
    got = []
    while time.time() < end:
        data = dev.read(64, 150)
        if data:
            got.append(bytes(data))
    for g in got:
        print(f"  [{tag}] rx: {g.hex(' ')}")
    if not got:
        print(f"  [{tag}] no response")


dongle, _ = open_page(0xFF02)
ctrl, _ = open_page(0xFF00)

print("dongle 0xA1 (dongle SN, page FF02 rid 1)")
tx(dongle, "dongle", 1, b"\xA1\x00")
print("device 0xA1 (keyboard SN, page FF00 rid 2)")
tx(ctrl, "ctrl", 2, b"\xA1\x00")
print("device 0xA0 (pairing info on ctrl, sanity check)")
tx(ctrl, "ctrl", 2, b"\xA0\x00")

print("listening for 5s on notify + ctrl")
end = time.time() + 5
evt, _ = open_page(0xFFC0)
while time.time() < end:
    for dev, tag in ((evt, "evt"), (ctrl, "ctrl")):
        data = dev.read(64, 60)
        if data:
            print(f"  [{tag}] {bytes(data).hex(' ')}")

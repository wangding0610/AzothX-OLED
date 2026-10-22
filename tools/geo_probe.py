"""Ask the firmware which framebuffer geometries it accepts (banner mode carries w/h)."""
import time

import hid

from oled import dongle_pairing

pairing = dongle_pairing()
rid = pairing["ctrl_report_id"] if pairing else 2
print("pairing:", pairing)

info = None
for d in hid.enumerate(0x0B05, 0x1ACE):
    if d["usage_page"] == 0xFF00:
        info = d
        break
dev = hid.device()
dev.open_path(info["path"])
dev.set_nonblocking(0)


def banner_mode(w, h, total=1, banner_type=0, direction=0):
    buf = bytearray(64)
    buf[0] = rid
    buf[1] = 0x62
    buf[2] = 0x00
    buf[5] = banner_type
    buf[6] = direction
    buf[7:9] = (w & 0xFFFF).to_bytes(2, "little")
    buf[9:11] = (h & 0xFFFF).to_bytes(2, "little")
    buf[11:13] = (total & 0xFFFF).to_bytes(2, "little")
    dev.write(bytes(buf))
    end = time.time() + 1.0
    while time.time() < end:
        d = dev.read(64, 120)
        if d:
            b = bytes(d)
            return b[:6].hex(" "), (b[1] == 0x62 and b[2] == 0x00)
    return "timeout", False


cands = [(256, 64), (320, 64), (128, 64), (192, 64), (384, 64), (256, 32),
         (320, 170), (368, 64), (400, 64), (448, 64), (512, 64), (256, 128)]
for w, h in cands:
    rsp, ok = banner_mode(w, h, total=0)
    print(f"  {w:4d}x{h:<4d} -> {rsp:24s} {'ACCEPT' if ok else ''}")
    time.sleep(0.15)

print("\nfinished - no data was transferred, only mode packets")
dev.close()

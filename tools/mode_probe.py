"""Query the current OLED page index (cmd 0x24 sub 1) and dump raw responses."""
import time

import hid

from oled import dongle_pairing

pairing = dongle_pairing()
rid = pairing["ctrl_report_id"] if pairing else 2
print("pairing:", pairing)

for d in hid.enumerate(0x0B05, 0x1ACE):
    if d["usage_page"] != 0xFF00:
        continue
    dev = hid.device()
    dev.open_path(d["path"])
    dev.set_nonblocking(0)
    break
else:
    raise SystemExit("ctrl channel not found")


def tx(cmd, sub, payload=b"", wait=1.5, tag=""):
    buf = bytearray(64)
    buf[0] = rid
    buf[1] = cmd
    buf[2] = sub
    buf[3:3 + len(payload)] = payload
    dev.write(bytes(buf))
    end = time.time() + wait
    while time.time() < end:
        data = dev.read(64, 150)
        if data:
            b = bytes(data)
            print(f"  [{tag or f'{cmd:02x}/{sub:02x}'}] {b.hex(' ')}")
            if len(b) > 5:
                print(f"        -> byte5(mode)={b[5]}")


print("get oled mode 0x24/1")
tx(0x24, 1, tag="mode")
print("get profile 0x24/0 (probe)")
tx(0x24, 0, tag="profile?")
print("animation show again (0x61/3) to re-assert custom page")
tx(0x61, 3, tag="anim-show")
time.sleep(0.3)
print("get oled mode again")
tx(0x24, 1, tag="mode-after")
dev.close()

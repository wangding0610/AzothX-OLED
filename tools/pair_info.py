"""Query the ROG OMNI receiver for its pairing table (0xA0 command)."""
import time

import hid

VID, PID = 0x0B05, 0x1ACE


def open_by_usage(page):
    for d in hid.enumerate(VID, PID):
        if d["usage_page"] == page:
            dev = hid.device()
            dev.open_path(d["path"])
            dev.set_nonblocking(0)
            return dev, d
    return None, None


def probe(page, report_id):
    dev, info = open_by_usage(page)
    if dev is None:
        print(f"page 0x{page:04X}: not found")
        return
    print(f"page 0x{page:04X} iface={info['interface_number']} path={info['path'][:70]}")
    buf = bytearray(64)
    buf[0] = report_id
    buf[1] = 0xA0
    buf[2] = 0x00
    dev.write(bytes(buf))
    deadline = time.time() + 2.0
    while time.time() < deadline:
        data = dev.read(64, 300)
        if data:
            b = bytes([0] + list(data)) if len(data) == 63 else bytes(data)
            print("   rx:", b.hex(" "))
            if len(b) > 12 and b[1] == 0xA0:
                pid1 = int.from_bytes(b[5:7], "little")
                pid2 = int.from_bytes(b[9:11], "little")
                print(f"   -> paired1 pid={pid1} ctrl_rid={b[7]} notify_rid={b[8]}")
                print(f"   -> paired2 pid={pid2} ctrl_rid={b[11]} notify_rid={b[12]}")
                break
    dev.close()


for page, rid in ((0xFF02, 1), (0xFF00, 2), (0xFF01, 3)):
    probe(page, rid)
    print()

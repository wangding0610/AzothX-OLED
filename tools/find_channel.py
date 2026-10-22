"""Identify which HID collection carries the ASUS vendor/Aura report (report ID 0x5d)."""
import hid

VID, PID = 0x0B05, 0x1ACE

for d in hid.enumerate(VID, PID):
    try:
        dev = hid.device()
        dev.open_path(d["path"])
    except Exception as e:  # noqa: BLE001
        print("open fail", d["path"], e)
        continue
    try:
        desc = bytes(dev.get_report_descriptor())
    except Exception as e:  # noqa: BLE001
        print("desc fail", e)
        dev.close()
        continue
    ids = [desc[i + 1] for i in range(len(desc) - 1) if desc[i] == 0x85]
    coll = d.get("collection_number", -1)
    print(
        f"iface={d['interface_number']} up={d['usage_page']:04X} u={d['usage']:04X} "
        f"coll={coll} desc_len={len(desc)} ids={[hex(x) for x in ids]}"
    )
    if 0x5D in ids:
        print("   *** report ID 0x5d present (ASUS vendor channel) ***")
        print("   raw:", desc.hex())
    dev.close()

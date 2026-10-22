"""Scan PE files for UTF-16LE / ASCII markers of interest (OLED, HID, packet commands)."""
import re
import sys

PATTERNS = [b"OLED", b"Oled", b"oled", b"Anime", b"Aura", b"Hidden", b"0x5d", b"Image",
            b"GIF", b"Frame", b"HID", b"Report", b"Omni", b"Lcd", b"LCD"]

def scan(path):
    data = open(path, "rb").read()
    print(f"### {path}  ({len(data)} bytes)")
    # .NET check
    print("   .NET CLR dir:", b"mscoree.dll" in data.lower() or b"_CorExeMain" in data)
    hits = {}
    for p in PATTERNS:
        n16 = len(re.findall(re.escape(p.decode().encode("utf-16-le")), data))
        n8 = data.count(p)
        if n16 or n8:
            hits[p.decode()] = (n8, n16)
    for k, v in hits.items():
        print(f"   {k!r}: ascii={v[0]} utf16={v[1]}")
    # dump surrounding utf16 strings containing oled
    for m in re.finditer("OLED".encode("utf-16-le"), data):
        s = max(0, m.start() - 60)
        chunk = data[s:m.start() + 80]
        try:
            txt = chunk.decode("utf-16-le", "ignore")
        except Exception:
            continue
        print("   ctx:", repr(txt))

for p in sys.argv[1:]:
    scan(p)

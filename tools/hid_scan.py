"""Dump HID report descriptors + caps for a given VID:PID (read-only).

Usage:  python hid_scan.py 0B05 1ACE
"""
import ctypes
import ctypes.wintypes as wt
import sys

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
IOCTL_HID_GET_REPORT_DESCRIPTOR = 0x000B0192

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)

CreateFileW = kernel32.CreateFileW
CreateFileW.restype = wt.HANDLE
CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]

DeviceIoControl = kernel32.DeviceIoControl
DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, wt.LPVOID, wt.DWORD, wt.LPVOID, wt.DWORD,
                            ctypes.POINTER(wt.DWORD), wt.LPVOID]
CloseHandle = kernel32.CloseHandle


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", ctypes.c_ushort),
        ("UsagePage", ctypes.c_ushort),
        ("InputReportByteLength", ctypes.c_ushort),
        ("OutputReportByteLength", ctypes.c_ushort),
        ("FeatureReportByteLength", ctypes.c_ushort),
        ("Reserved", ctypes.c_ushort * 17),
        ("NumberLinkCollectionNodes", ctypes.c_ushort),
        ("NumberInputButtonCaps", ctypes.c_ushort),
        ("NumberInputValueCaps", ctypes.c_ushort),
        ("NumberInputDataIndices", ctypes.c_ushort),
        ("NumberOutputButtonCaps", ctypes.c_ushort),
        ("NumberOutputValueCaps", ctypes.c_ushort),
        ("NumberOutputDataIndices", ctypes.c_ushort),
        ("NumberFeatureButtonCaps", ctypes.c_ushort),
        ("NumberFeatureValueCaps", ctypes.c_ushort),
        ("NumberFeatureDataIndices", ctypes.c_ushort),
    ]


def enumerate_paths():
    import hid as pyhid
    return [d for d in pyhid.enumerate() if True]


def dump(path, vid, pid):
    h = CreateFileW(path, GENERIC_READ | GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    if h == wt.HANDLE(-1).value or h is None:
        err = ctypes.get_last_error()
        h = CreateFileW(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if h == wt.HANDLE(-1).value or h is None:
            return None, f"open failed err={err}/{ctypes.get_last_error()}"
    out = {}
    buf = ctypes.create_string_buffer(4096)
    n = wt.DWORD(0)
    ok = DeviceIoControl(h, IOCTL_HID_GET_REPORT_DESCRIPTOR, None, 0, buf, 4096,
                         ctypes.byref(n), None)
    if ok:
        out["descriptor"] = bytes(buf.raw[: n.value])
    else:
        out["descriptor"] = b""
        out["desc_err"] = ctypes.get_last_error()

    pp = ctypes.c_void_p()
    if hid.HidD_GetPreparsedData(wt.HANDLE(h), ctypes.byref(pp)):
        caps = HIDP_CAPS()
        if hid.HidP_GetCaps(pp, ctypes.byref(caps)) >= 0:
            out["caps"] = dict(
                usage_page=caps.UsagePage, usage=caps.Usage,
                in_len=caps.InputReportByteLength,
                out_len=caps.OutputReportByteLength,
                feat_len=caps.FeatureReportByteLength,
                link_collections=caps.NumberLinkCollectionNodes,
            )
        hid.HidD_FreePreparsedData(pp)
    # product string
    sbuf = ctypes.create_unicode_buffer(256)
    if hid.HidD_GetProductString(wt.HANDLE(h), sbuf, 512):
        out["product"] = sbuf.value
    CloseHandle(h)
    return out, None


def pretty(desc: bytes) -> str:
    """Tiny HID item decoder - enough to read collection/report structure."""
    i = 0
    lines = []
    while i < len(desc):
        b = desc[i]
        if b == 0xFE:
            size = desc[i + 1] if i + 1 < len(desc) else 0
            lines.append(f"{i:04x}: LONG {desc[i+2:i+3+size].hex()}")
            i += 3 + size
            continue
        size = [0, 1, 2, 4][b & 0x03]
        typ = (b >> 2) & 0x03
        tag = (b >> 4) & 0x0F
        val = int.from_bytes(desc[i + 1:i + 1 + size], "little") if size else None
        i += 1 + size
        names = {
            (1, 0): "UsagePage", (1, 8): "ReportID", (1, 9): "ReportCount",
            (1, 7): "ReportSize", (1, 4): "Usage", (1, 5): "LogicalMin",
            (1, 6): "LogicalMax", (1, 1): "Input", (1, 2): "Output",
            (1, 3): "Feature", (1, 10): "Push", (1, 11): "Pop",
            (0, 10): "Collection", (0, 12): "EndCollection",
        }
        key = (0 if typ == 0 else 1, tag if typ == 1 else tag)
        label = names.get((typ, tag))
        if label is None:
            label = names.get((0 if typ == 0 else 1, tag), f"item(typ={typ},tag={tag})")
        shown = f"0x{val:0{size*2}X}" if size else ""
        lines.append(f"{i-1-size:04x}: {label} {shown}")
    return "\n".join(lines)


def main():
    vid = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x0B05
    pid = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x1ACE
    for d in enumerate_paths():
        if d["vendor_id"] != vid or d["product_id"] != pid:
            continue
        path = d["path"].decode() if isinstance(d["path"], bytes) else d["path"]
        tag = f"iface={d['interface_number']} up={d['usage_page']:04X} u={d['usage']:04X}"
        info, err = dump(path, vid, pid)
        print("=" * 100)
        print(tag, path)
        if err:
            print("  error:", err)
            continue
        print("  caps:", info.get("caps"))
        desc = info.get("descriptor", b"")
        print(f"  descriptor ({len(desc)} bytes): {desc.hex()}")
        if desc:
            print(pretty(desc))
            # report IDs present in descriptor
            ids = []
            i = 0
            while i < len(desc):
                if desc[i] == 0x85 and i + 1 < len(desc):
                    ids.append(desc[i + 1])
                i += 1
            print("  report IDs:", [hex(x) for x in ids])


if __name__ == "__main__":
    main()

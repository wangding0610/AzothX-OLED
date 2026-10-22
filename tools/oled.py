"""ROG OLED driver for ASUS ROG keyboards (Azoth / Azoth X / 夜魔 / 夜魔X ...).

Everything here was recovered from the shipped ASUS "Gear Link" components:
  * GearLink_KBApi.dll     (custom banner / custom animation / music mode classes)
  * GearLink_KBAgent.exe   (image -> 4bpp binary conversion)
  * GearLink_KBService.dll (OMNI receiver discovery + pairing table)

Transport facts
  OMNI receiver (VID 0B05, PID 1ACE) exposes three 64-byte in/out vendor
  collections on MI_02:
      usage page 0xFF02 (report id 1) -> dongle management (pairing info, dongle SN)
      usage page 0xFF00 (report id 2) -> the paired keyboard   <-- commands go here
      usage page 0xFF01 (report id 3) -> second paired device (mouse)
  The dongle answers every write on a device channel with "FF AA" while the
  paired device is off / asleep / not linked.

  A directly attached keyboard uses the same command block in a 65 byte report
  (report id + 64 bytes), so the data chunk is 60 bytes instead of 59.

Command block (byte 0 is the HID report id)
  custom animation, cmd 0x61:
      sub 1: mode   [5..8]  = u32 total packet count
      sub 2: data   [3..4]  = u16 packet index, [5..] = payload
      sub 3: show
  custom banner, cmd 0x62:
      sub 0: mode   [5] banner_type, [6] direction,
                    [7..8] u16 width, [9..10] u16 height, [11..12] u16 packets
      sub 1: data   [3..4] = u16 packet index, [5..] = payload
      sub 2: show
  Every packet is acknowledged by an echo with the same [1]/[2] and, for data
  packets, the same index.

  Payload layout: 4 bit gray, row major from the top, two pixels per byte,
  low nibble = left pixel, high nibble = right pixel
  (GearLink_KBAgent.ConvertImageToBinary_GRAY / MergePixel).
      animation: u16 frame_count, u16 duration_ms, then the frames
      banner   : raw framebuffer only

Usage
    python oled.py list
    python oled.py test  --width 256 --height 64
    python oled.py text  "你好 ROG"
    python oled.py image picture.png
    python oled.py anim  clip.gif
    python oled.py test  --banner --wait-link    # cmd 0x62 instead of 0x61
"""
from __future__ import annotations

import sys as _sys
try:                      # ???? UTF-8 ???????
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import argparse
import queue
import sys
import threading
import time

import hid

VID = 0x0B05
OMNI_PID = 0x1ACE

CMD_ANIMATION = 0x61
CMD_BANNER = 0x62
SUB_ANIM_MODE, SUB_ANIM_DATA, SUB_ANIM_SHOW = 1, 2, 3
SUB_BANNER_MODE, SUB_BANNER_DATA, SUB_BANNER_SHOW = 0, 1, 2


# --------------------------------------------------------------------- discovery
def enumerate_vendor():
    out = []
    for d in hid.enumerate(VID, 0):
        if 0xFF00 <= d["usage_page"] <= 0xFFFF:
            out.append(d)
    return out


def dongle_pairing():
    """Ask the OMNI receiver what is paired: returns dict or None."""
    for d in hid.enumerate(VID, OMNI_PID):
        if d["usage_page"] != 0xFF02:
            continue
        dev = hid.device()
        dev.open_path(d["path"])
        dev.set_nonblocking(0)
        buf = bytearray(64)
        buf[0] = 1
        buf[1] = 0xA0
        buf[2] = 0x00
        dev.write(bytes(buf))
        end = time.time() + 2.0
        while time.time() < end:
            data = dev.read(64, 200)
            if data and data[1] == 0xA0:
                b = bytes(data)
                info = {
                    "paired_pid": int.from_bytes(b[5:7], "little"),
                    "ctrl_report_id": b[7],
                    "notify_report_id": b[8],
                    "path_management": d["path"],
                }
                dev.close()
                return info
        dev.close()
    return None


def pick_ctrl(report_id: int, usage_page: int = 0xFF00):
    for d in hid.enumerate(VID, 0):
        if d["usage_page"] == usage_page:
            return d
    return None


class RogOled:
    def __init__(self, usage_page=0xFF00, report_id=2, path=None,
                 chunk=59, verbose=True, wait_link=0.0):
        info = None
        if path:
            info = {"path": path}
        else:
            info = pick_ctrl(report_id, usage_page)
            if info is None:
                # direct keyboard: accept any vendor page that carries an output report
                for cand in (0xFF00, 0xFF31, 0xFF02):
                    info = pick_ctrl(report_id, cand)
                    if info:
                        break
        if info is None:
            raise SystemExit("no matching HID collection found (run: python oled.py list)")
        self.info = info
        self.report_id = report_id
        self.chunk = chunk
        self.verbose = verbose
        self.dev = hid.device()
        self.dev.open_path(info["path"])
        self.dev.set_nonblocking(0)
        self.rx: "queue.Queue[bytes]" = queue.Queue()
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()
        self.wait_link = wait_link
        self._link_checked = False

    def _reader(self):
        errs = 0
        while not self._stop.is_set():
            try:
                data = self.dev.read(64, 200)
                errs = 0
            except Exception:
                errs += 1
                if errs in (10, 100):          # handle went stale: reopen quietly
                    try:
                        self.dev.close()
                        self.dev = hid.device()
                        self.dev.open_path(self.info["path"])
                        self.dev.set_nonblocking(0)
                    except Exception:
                        pass
                time.sleep(0.02)
                continue
            if data:
                self.rx.put(bytes(data))

    def close(self):
        self._stop.set()
        try:
            self.dev.close()
        except Exception:
            pass

    # -------------------------------------------------------------- primitives
    def write(self, buf: bytearray):
        buf[0] = self.report_id
        n = self.dev.write(bytes(buf))
        if n < 0:
            raise IOError(f"hid write failed: {self.dev.error()}")
        if self.verbose:
            print("  ->", bytes(buf[:14]).hex(" "))
        return n

    def drain(self):
        while True:
            try:
                self.rx.get_nowait()
            except queue.Empty:
                return

    def wait_for(self, cmd, sub, timeout=2.0):
        end = time.time() + timeout
        while time.time() < end:
            try:
                b = self.rx.get(timeout=max(0.01, end - time.time()))
            except queue.Empty:
                return None
            if len(b) > 2 and b[1] == cmd and b[2] == sub:
                return b
        return None

    def _check_link(self, cmd, sub, payload):
        """Send a probe packet until the device answers. Lets the user wake it."""
        if self._link_checked:
            return
        deadline = time.time() + self.wait_link if self.wait_link else 0
        while True:
            self.drain()
            buf = bytearray(65)
            buf[1] = cmd
            buf[2] = sub
            for i, v in enumerate(payload):
                buf[3 + i] = v
            self.write(buf)
            rsp = self.wait_for(cmd, sub, timeout=2.0)
            if rsp:
                self._link_checked = True
                return
            if time.time() >= deadline:
                print("  !! device did not answer (dongle returns FF AA while the "
                      "keyboard is off/asleep/unlinked)")
                return
            print("  .. waiting for the keyboard link, press a key on it")
            time.sleep(1.0)

    # ------------------------------------------------------------------ commands
    def animation_upload(self, payload):
        total = (len(payload) + self.chunk - 1) // self.chunk
        print(f"[anim] {len(payload)} bytes -> {total} packets of {self.chunk}")

        self.drain()
        buf = bytearray(65)
        buf[1], buf[2] = CMD_ANIMATION, SUB_ANIM_MODE
        buf[5:9] = total.to_bytes(4, "little")
        self.write(buf)
        if not self.wait_for(CMD_ANIMATION, SUB_ANIM_MODE):
            print("  !! no ACK for animation mode")

        self._send_chunks(CMD_ANIMATION, SUB_ANIM_DATA, payload, total)

        buf = bytearray(65)
        buf[1], buf[2] = CMD_ANIMATION, SUB_ANIM_SHOW
        self.write(buf)
        if not self.wait_for(CMD_ANIMATION, SUB_ANIM_SHOW):
            print("  !! no ACK for animation show")

    def banner_upload(self, payload, width, height, banner_type=0, direction=0):
        total = (len(payload) + self.chunk - 1) // self.chunk
        print(f"[banner] {width}x{height} {len(payload)} bytes -> {total} packets")

        self.drain()
        buf = bytearray(65)
        buf[1], buf[2] = CMD_BANNER, SUB_BANNER_MODE
        buf[5] = banner_type & 0xFF
        buf[6] = direction & 0xFF
        buf[7:9] = (width & 0xFFFF).to_bytes(2, "little")
        buf[9:11] = (height & 0xFFFF).to_bytes(2, "little")
        buf[11:13] = total.to_bytes(2, "little")
        self.write(buf)
        if not self.wait_for(CMD_BANNER, SUB_BANNER_MODE):
            print("  !! no ACK for banner mode")

        self._send_chunks(CMD_BANNER, SUB_BANNER_DATA, payload, total)

        buf = bytearray(65)
        buf[1], buf[2] = CMD_BANNER, SUB_BANNER_SHOW
        self.write(buf)
        if not self.wait_for(CMD_BANNER, SUB_BANNER_SHOW):
            print("  !! no ACK for banner show")

    def _send_chunks(self, cmd, sub, payload, total):
        acked = 0
        index = total
        for i in range(total):
            chunk = payload[i * self.chunk:(i + 1) * self.chunk]
            if index:
                index -= 1
            ok = False
            for attempt in range(8):
                if attempt in (3, 6):          # re-sync: firmware sometimes drops the session
                    self._mode_resend(cmd, sub, payload, total)
                buf = bytearray(65)
                buf[1], buf[2] = cmd, sub
                buf[3:5] = index.to_bytes(2, "little")
                buf[5:5 + len(chunk)] = chunk
                self.write(buf)
                rsp = self.wait_for(cmd, sub)
                if rsp and rsp[3] == (index & 0xFF) and rsp[4] == (index >> 8):
                    ok = True
                    break
                print(f"  retry packet {i} (attempt {attempt + 1})")
            if not ok:
                raise IOError(f"packet {i} never acknowledged")
            acked += 1
            if i % 20 == 0 or i == total - 1:
                print(f"  .. {acked}/{total}")
        print(f"[ok] {acked} packets acknowledged")

    def _mode_resend(self, cmd, sub, payload, total):
        """Re-issue the mode packet (animation only) to rebuild the transfer state."""
        if cmd != CMD_ANIMATION:
            return
        buf = bytearray(65)
        buf[1], buf[2] = CMD_ANIMATION, SUB_ANIM_MODE
        buf[5:9] = total.to_bytes(4, "little")
        self.drain()
        self.write(buf)
        self.wait_for(CMD_ANIMATION, SUB_ANIM_MODE)



# --------------------------------------------------------------------- rendering
def render_4bpp(img, width, height):
    from PIL import Image

    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)
    gray = img.convert("L")
    px = gray.load()
    out = bytearray(width * height // 2)
    i = 0
    for y in range(height):
        for x in range(0, width, 2):
            # ASUS MergePixel concatenates right bits + left bits (MSB first).
            # Reversing these nibbles swaps adjacent columns on the OLED.
            out[i] = ((px[x + 1, y] & 0xF0)) | ((px[x, y] & 0xF0) >> 4)
            i += 1
    return bytes(out)


def _font(size, bold=True):
    """Bold faces keep their stroke width on a 4bpp panel; light faces look blurry."""
    from PIL import ImageFont

    order = (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\arialbd.ttf",
             r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\consola.ttf")
    for path in order:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def crisp(img, thresh=128):
    """4 bit gray + antialiased glyphs reads as 'soft' on a small OLED: hard-threshold it."""
    return img.point(lambda p: 255 if p >= thresh else 0)


def text_image(text, width, height, thresh=128):
    from PIL import Image, ImageDraw

    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    lines = text.split("\n") if "\n" in text else [text]
    line_h = height // len(lines)
    y = 0
    for line in lines:
        size = line_h + 2
        while size > 6:
            font = _font(size)
            box = draw.textbbox((0, 0), line, font=font)
            if box[2] - box[0] <= width - 2 and box[3] - box[1] <= line_h:
                break
            size -= 1
        font = _font(size)
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(((width - (box[2] - box[0])) // 2 - box[0],
                   y + (line_h - (box[3] - box[1])) // 2 - box[1]),
                  line, 255, font=font)
        y += line_h
    return crisp(img, thresh)


def test_image(width, height):
    from PIL import Image, ImageDraw

    img = Image.new("L", (width, height), 0)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width - 1, height - 1], outline=255)
    for x in range(width):
        d.line([(x, 2), (x, height // 2 - 2)], fill=int(x * 255 / max(1, width - 1)))
    for y in range(height // 2 + 1, height - 2):
        d.line([(2, y), (width // 2 - 2, y)],
               fill=int((y - height // 2) * 255 / max(1, height // 2 - 2)))
    d.rectangle([width // 2 + 2, height // 2 + 1, width - 3, height - 3], fill=255)
    return img


def build_payload(mode, value, width, height, duration):
    if mode == "test":
        frames = [(test_image(width, height), duration)]
    elif mode == "text":
        frames = [(text_image(value, width, height), duration)]
    elif mode == "image":
        from PIL import Image
        frames = [(Image.open(value), duration)]
    else:  # anim
        from PIL import Image
        gif = Image.open(value)
        frames = []
        try:
            while True:
                frames.append((gif.convert("L").copy(), gif.info.get("duration", duration)))
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
    payload = bytearray()
    if mode in ("test", "text", "image"):
        # a single-frame animation sometimes left the panel on the previous
        # content; two identical frames always refresh (278 packets @ 256x64)
        frames = frames * 2
    payload += len(frames).to_bytes(2, "little")
    for _, d in frames:
        payload += max(1, min(int(d), 0xFFFF)).to_bytes(2, "little")
    for frame, _ in frames:
        payload += render_4bpp(frame, width, height)
    if mode in ("test", "text", "image"):
        frames[0][0].save("preview.png")
        print(f"preview -> preview.png ({width}x{height})")
    return bytes(payload), len(frames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["list", "test", "text", "image", "anim"])
    ap.add_argument("value", nargs="?", default="")
    ap.add_argument("--width", type=int, default=208)
    ap.add_argument("--height", type=int, default=64)
    ap.add_argument("--duration", type=int, default=1000)
    ap.add_argument("--banner", action="store_true", help="use command 0x62")
    ap.add_argument("--banner-type", type=int, default=0)
    ap.add_argument("--direction", type=int, default=0)
    ap.add_argument("--usage-page", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--report-id", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--chunk", type=int, default=None)
    ap.add_argument("--path", default=None, help="explicit HID device path")
    ap.add_argument("--wait-link", type=float, default=0.0,
                    help="seconds to keep retrying while the keyboard is asleep")
    ap.add_argument("--save", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.mode == "list":
        print("vendor collections:")
        for d in enumerate_vendor():
            print(f"  pid=0x{d['product_id']:04X} iface={d['interface_number']} "
                  f"up=0x{d['usage_page']:04X} u=0x{d['usage']:04X} "
                  f"{d['product_string']!r}")
        print("OMNI receiver pairing table:", dongle_pairing())
        return

    payload, nframes = build_payload(args.mode, args.value, args.width, args.height,
                                     args.duration)
    print(f"payload {len(payload)} bytes, {nframes} frame(s)")
    if args.save:
        open(args.save, "wb").write(payload)
        print(f"saved -> {args.save}")
    if args.dry_run:
        return

    pairing = dongle_pairing()
    usage_page = args.usage_page
    report_id = args.report_id
    chunk = args.chunk
    if pairing:
        print(f"OMNI receiver: paired pid={pairing['paired_pid']} "
              f"ctrl rid={pairing['ctrl_report_id']} notify rid={pairing['notify_report_id']}")
        usage_page = 0xFF00 if usage_page is None else usage_page
        report_id = pairing["ctrl_report_id"] if report_id is None else report_id
        chunk = 59 if chunk is None else chunk
    else:
        usage_page = 0xFF00 if usage_page is None else usage_page
        report_id = 2 if report_id is None else report_id
        chunk = 60 if chunk is None else chunk

    dev = RogOled(usage_page, report_id, args.path, chunk, wait_link=args.wait_link)
    try:
        if args.banner:
            dev.banner_upload(payload, args.width, args.height,
                              args.banner_type, args.direction)
        else:
            dev.animation_upload(payload)
        print("done")
    finally:
        dev.close()


if __name__ == "__main__":
    sys.exit(main())

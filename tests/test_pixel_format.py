"""Regression checks against GearLink_KBAgent.MergePixel's wire format."""
import contextlib
import datetime
import io
from pathlib import Path
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oled
import pages
import pxfont
import show


def panel_decode(data, size):
    # Device order: the first pixel is the LOW nibble. Expand 0..15 to 0..255.
    pixels = bytes(v for b in data for v in ((b % 16) * 17, (b // 16) * 17))
    return Image.frombytes("L", size, pixels)


class PixelFormatTests(unittest.TestCase):
    def test_known_asymmetric_pairs_and_row_order(self):
        image = Image.new("L", (4, 2))
        image.putdata([255, 0, 0, 255, 17, 238, 128, 64])
        # MergePixel constructs IntToBits(second) + IntToBits(first).
        self.assertEqual(oled.render_4bpp(image, 4, 2), bytes.fromhex("0f f0 e1 48"))

    def test_every_gray_pair_matches_vendor_conversion(self):
        image = Image.new("L", (512, 256))
        pixels = []
        expected = bytearray()
        for left in range(256):
            for right in range(256):
                pixels.extend((left, right))
                expected.append(int(f"{right // 16:04b}{left // 16:04b}", 2))
        image.putdata(pixels)
        self.assertEqual(oled.render_4bpp(image, 512, 256), bytes(expected))

    def test_odd_aligned_bitmap_text_survives_device_decode(self):
        image = Image.new("L", (208, 64))
        pxfont.draw(image, (147, 25), "10/22", scale=2)
        wire = oled.render_4bpp(image, 208, 64)
        self.assertEqual(panel_decode(wire, image.size).tobytes(), image.tobytes())

    def test_clock_survives_two_frames_and_59_byte_packets(self):
        image = pages.clock(datetime.datetime(2026, 10, 22, 9, 14, 27))
        reports = []
        # Exercise the real upload/packet construction without opening hardware.
        device = oled.RogOled.__new__(oled.RogOled)
        device.chunk = 59
        device.drain = lambda: None
        device.write = lambda b: reports.append(bytes(b))
        device.wait_for = lambda cmd, sub: reports[-1]
        with contextlib.redirect_stdout(io.StringIO()):
            show.push(device, image)
        self.assertEqual(reports[0][1:3], b"\x61\x01")
        self.assertEqual(int.from_bytes(reports[0][5:9], "little"), 226)
        self.assertEqual(reports[-1][1:3], b"\x61\x03")
        data_reports = reports[1:-1]
        self.assertEqual(len(data_reports), 226)
        self.assertEqual([int.from_bytes(r[3:5], "little") for r in data_reports],
                         list(range(225, -1, -1)))
        payload = b"".join(r[5:64] for r in data_reports)[:13318]
        self.assertEqual(payload[:6], bytes.fromhex("02 00 e8 03 e8 03"))
        quantized = image.point(lambda value: (value // 16) * 17)
        for offset in (6, 6662):
            decoded = panel_decode(payload[offset:offset + 6656], image.size)
            self.assertEqual(decoded.tobytes(), quantized.tobytes())


if __name__ == "__main__":
    unittest.main()

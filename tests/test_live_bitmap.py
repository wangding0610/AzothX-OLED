"""Fixed clock updates require a single raw frame AND the redraw trigger."""
import contextlib
import datetime
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oled
import pages
import show


def device_with_reports():
    dev = oled.RogOled.__new__(oled.RogOled)
    dev.chunk = 59
    dev.drain = lambda: None
    reports = []
    dev.write = lambda b: reports.append(bytes(b))
    dev.wait_for = lambda cmd, sub, **kwargs: reports[-1]
    return dev, reports


class LiveBitmapTests(unittest.TestCase):
    def test_clock_packets_preserve_pixels_and_end_with_redraw(self):
        image = pages.clock(datetime.datetime(2026, 10, 23, 0, 8, 9))
        dev, reports = device_with_reports()
        with contextlib.redirect_stdout(io.StringIO()):
            show.push_live(dev, image)
        self.assertEqual(len(reports), 115)  # mode + 113 data packets + redraw
        self.assertTrue(all(r[1] == 0x67 for r in reports))
        self.assertEqual(reports[0][2], 0)
        self.assertEqual(reports[0][5:13], bytes.fromhex("00 00 71 00 d0 00 40 00"))
        self.assertTrue(all(r[2] == 1 for r in reports[1:-1]))
        self.assertEqual([int.from_bytes(r[3:5], "little") for r in reports[1:-1]],
                         list(range(112, -1, -1)))
        data = b"".join(r[5:64] for r in reports[1:-1])[:6656]
        pixels = bytes(v for b in data for v in ((b & 15) * 17, (b >> 4) * 17))
        self.assertEqual(pixels, image.point(lambda v: (v // 16) * 17).tobytes())
        self.assertEqual(reports[-1][2], 2)
        self.assertEqual(reports[-1][3:], bytes(62))

    def test_failed_mode_or_data_does_not_trigger_redraw(self):
        for missing in (0, 1):
            with self.subTest(sub=missing):
                dev, reports = device_with_reports()
                dev.wait_for = lambda cmd, sub, **kwargs: None if sub == missing else reports[-1]
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(OSError):
                    dev.live_upload(bytes(6656), 208, 64)
                self.assertFalse(any(r[2] == 2 for r in reports))

    def test_rejects_animation_header_or_incomplete_frame(self):
        dev, reports = device_with_reports()
        for data in (bytes(6655), bytes(13318)):
            with self.assertRaises(ValueError):
                dev.live_upload(data, 208, 64)
        self.assertEqual(reports, [])


if __name__ == "__main__":
    unittest.main()

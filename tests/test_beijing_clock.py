"""Beijing date rollover and real upload failures used by the resident clock."""
import contextlib
import datetime as dt
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oled
import pages


class BeijingClockTests(unittest.TestCase):
    def test_utc_instant_rolls_to_next_year_in_beijing(self):
        utc = dt.datetime(2026, 12, 31, 16, 0, 1, tzinfo=dt.timezone.utc)
        local = pages.beijing_time(utc)
        self.assertEqual(local.isoformat(), "2027-01-01T00:00:01+08:00")
        self.assertEqual(pages.WEEKDAYS[local.weekday()], "FRI")
        self.assertEqual(pages.clock(utc).tobytes(),
                         pages.clock(dt.datetime(2027, 1, 1, 0, 0, 1)).tobytes())

    def test_live_time_uses_utc_plus_eight(self):
        before = dt.datetime.now(dt.timezone.utc)
        value = pages.beijing_time()
        after = dt.datetime.now(dt.timezone.utc)
        self.assertEqual(value.utcoffset(), dt.timedelta(hours=8))
        self.assertLessEqual(before, value)
        self.assertLessEqual(value, after)

    def test_source_timezone_does_not_change_displayed_instant(self):
        utc = dt.datetime(2026, 10, 22, 15, 59, 59, tzinfo=dt.timezone.utc)
        other = utc.astimezone(dt.timezone(dt.timedelta(hours=-5)))
        self.assertEqual(pages.clock(utc).tobytes(), pages.clock(other).tobytes())

    def test_upload_requires_mode_and_show_acknowledgements(self):
        for missing in (oled.SUB_ANIM_MODE, oled.SUB_ANIM_SHOW):
            with self.subTest(missing=missing):
                device = oled.RogOled.__new__(oled.RogOled)
                device.chunk = 59
                device.drain = lambda: None
                reports = []
                device.write = lambda b: reports.append(bytes(b))
                device.wait_for = lambda cmd, sub, **kwargs: None if sub == missing else reports[-1]
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(OSError):
                        device.animation_upload(bytes(60))
                if missing == oled.SUB_ANIM_MODE:
                    self.assertEqual(len(reports), 1)  # No data after rejected mode.


if __name__ == "__main__":
    unittest.main()

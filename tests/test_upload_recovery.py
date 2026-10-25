"""Avoid the mid-frame rejection and partial-session recovery seen on OMNI."""
import contextlib
import io
from pathlib import Path
import queue
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oled


def fake_device():
    dev = oled.RogOled.__new__(oled.RogOled)
    dev.chunk = 59
    dev.drain = lambda: None
    reports = []
    dev.write = lambda b: reports.append(bytes(b))
    dev.wait_for = lambda cmd, sub, **kwargs: reports[-1]
    return dev, reports


class UploadRecoveryTests(unittest.TestCase):
    def test_cooldown_before_next_frame(self):
        dev, _ = fake_device()
        with patch("oled.time.monotonic", return_value=10), patch("oled.time.sleep") as sleep:
            with contextlib.redirect_stdout(io.StringIO()):
                dev.animation_upload(bytes(60))
                sleep.assert_not_called()
                dev.animation_upload(bytes(60))
            sleep.assert_called_once_with(2.0)

    def test_data_timeout_aborts_without_show_or_partial_restart(self):
        dev, reports = fake_device()
        dev.wait_for = lambda cmd, sub, **kwargs: None if sub == 2 else reports[-1]
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                dev.animation_upload(bytes(120))
        self.assertEqual([r[2] for r in reports], [1, 2])
        # A later retry must send the first packet again, then all remaining data.
        reports.clear()
        dev.wait_for = lambda cmd, sub, **kwargs: reports[-1]
        with patch("oled.time.sleep"), contextlib.redirect_stdout(io.StringIO()):
            dev.animation_upload(bytes(120))
        self.assertEqual([r[2] for r in reports], [1, 2, 2, 2, 3])
        self.assertEqual([int.from_bytes(r[3:5], "little") for r in reports[1:-1]], [2, 1, 0])

    def test_late_packet_echo_is_ignored(self):
        dev = oled.RogOled.__new__(oled.RogOled)
        dev.rx = queue.Queue()
        dev.rx.put(bytes.fromhex("02 61 02 14 00"))
        dev.rx.put(bytes.fromhex("02 61 02 13 00"))
        self.assertEqual(dev.wait_for(0x61, 2, timeout=0.1, index=19),
                         bytes.fromhex("02 61 02 13 00"))


if __name__ == "__main__":
    unittest.main()

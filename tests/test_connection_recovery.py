"""Boot delays and receiver replug must not bind the OLED to a laptop keyboard."""
import contextlib
import io
import queue
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import oled
import show


def interface(pid, page, path, serial=""):
    return {"product_id": pid, "usage_page": page, "path": path, "serial_number": serial}


NKEY = interface(0x19B6, 0xFF31, b"laptop-keyboard")
MANAGEMENT = interface(oled.OMNI_PID, 0xFF02, b"omni-management", "receiver-a")
CONTROL = interface(oled.OMNI_PID, 0xFF00, b"omni-control", "receiver-a")
PAIRING = {"paired_pid": oled.AZOTH_X_PID, "ctrl_report_id": 2,
           "serial_number": "receiver-a"}


class ConnectionDiscoveryTests(unittest.TestCase):
    def test_selects_same_receiver_when_other_asus_devices_exist(self):
        other = interface(oled.OMNI_PID, 0xFF00, b"other-receiver", "receiver-b")
        devices = [NKEY, other, MANAGEMENT, CONTROL]
        with patch("oled.hid.enumerate", return_value=devices), \
                patch("oled.dongle_pairing", return_value=PAIRING):
            target = oled.clock_connection()
        self.assertEqual(target["path"], b"omni-control")
        self.assertEqual((target["report_id"], target["chunk"]), (2, 59))

    def test_unready_receiver_does_not_fall_back_to_wired_mode(self):
        wired = interface(oled.AZOTH_X_PID, 0xFF00, b"wired")
        with patch("oled.hid.enumerate", return_value=[NKEY, MANAGEMENT, CONTROL, wired]), \
                patch("oled.dongle_pairing", return_value=None), \
                self.assertRaisesRegex(OSError, "not ready"):
            oled.clock_connection()

    def test_laptop_keyboard_alone_is_not_an_oled(self):
        with patch("oled.hid.enumerate", return_value=[NKEY]), \
                patch("oled.dongle_pairing") as pairing, \
                self.assertRaisesRegex(OSError, "not found"):
            oled.clock_connection()
        pairing.assert_not_called()

    def test_known_wired_keyboard_uses_60_byte_chunks(self):
        wired = interface(oled.AZOTH_X_USB_PID, 0xFF00, b"wired")
        with patch("oled.hid.enumerate", return_value=[NKEY, wired]):
            target = oled.clock_connection()
        self.assertEqual((target["path"], target["chunk"]), (b"wired", 60))
        self.assertEqual(target["report_id"], 0)

    def test_wired_and_paired_receiver_are_both_candidates(self):
        wired = interface(oled.AZOTH_X_USB_PID, 0xFF00, b"wired")
        with patch("oled.hid.enumerate", return_value=[NKEY, wired, MANAGEMENT, CONTROL]), \
                patch("oled.dongle_pairing", return_value=PAIRING):
            targets = oled.clock_connections()
        self.assertEqual([t["path"] for t in targets], [b"wired", b"omni-control"])

    def test_verified_usb_does_not_wait_for_an_unready_receiver(self):
        wired = interface(oled.AZOTH_X_USB_PID, 0xFF00, b"wired")
        with patch("oled.hid.enumerate", return_value=[wired, MANAGEMENT]), \
                patch("oled.dongle_pairing", return_value=None):
            self.assertEqual(oled.clock_connection()["path"], b"wired")

    def test_wrong_paired_model_is_not_written(self):
        with patch("oled.hid.enumerate", return_value=[MANAGEMENT, CONTROL]), \
                patch("oled.dongle_pairing", return_value={**PAIRING, "paired_pid": 123}), \
                self.assertRaisesRegex(OSError, "not Azoth X"):
            oled.clock_connection()

    def test_pairing_handle_is_closed_after_write_failure(self):
        dev = Mock()
        dev.write.return_value = -1
        dev.error.return_value = "receiver removed"
        with patch("oled.hid.device", return_value=dev), \
                self.assertRaisesRegex(OSError, "receiver removed"):
            oled.dongle_pairing([MANAGEMENT])
        dev.close.assert_called_once()

    def test_short_pairing_responses_are_ignored(self):
        dev = Mock()
        dev.write.return_value = 64
        dev.read.side_effect = [[1], [1, 0xA0], [1, 0xA0, 0, 0, 0, 0x25, 0x1C, 2, 4]]
        with patch("oled.hid.device", return_value=dev):
            pairing = oled.dongle_pairing([MANAGEMENT])
        self.assertEqual(pairing["paired_pid"], oled.AZOTH_X_PID)
        dev.close.assert_called_once()


class ConnectionRecoveryTests(unittest.TestCase):
    def test_unresponsive_cable_falls_back_to_radio(self):
        targets = [
            {"path": b"usb", "report_id": 0, "chunk": 60, "transport": "USB", "usage_page": 0xFF00},
            {"path": b"radio", "report_id": 2, "chunk": 59, "transport": "OMNI", "usage_page": 0xFF00}]
        usb, radio = Mock(), Mock()
        usb.configure_live.side_effect = OSError("not active")
        with patch("show.clock_connections", return_value=targets), \
                patch("show.RogOled", side_effect=[usb, radio]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertIs(show.connect(), radio)
        usb.close.assert_called_once()
        radio.configure_live.assert_called_once_with(208, 64)

    def test_unnumbered_usb_and_numbered_radio_ack_use_same_parser(self):
        for report_id, raw in ((0, bytes.fromhex("67 01 0a 00")), (2, bytes.fromhex("02 67 01 0a 00"))):
            with self.subTest(report_id=report_id):
                dev = oled.RogOled.__new__(oled.RogOled)
                dev.report_id = report_id
                dev._stop = threading.Event()
                dev._read_error = None
                dev.rx = queue.Queue()
                dev.dev = Mock()
                def read_once(*args):
                    dev._stop.set()
                    return raw
                dev.dev.read.side_effect = read_once
                dev._reader()
                self.assertIsNotNone(dev.wait_for(0x67, 1, timeout=.01, index=10))

    def test_startup_delay_and_stale_handle_are_both_rediscovered(self):
        stale, recovered = Mock(), Mock()
        with patch.object(sys, "argv", ["show.py", "clock", "--quiet"]), \
                patch("show.connect", side_effect=[OSError("not ready"), stale, recovered]) as connect, \
                patch("show.push_live", side_effect=[OSError("receiver removed"), None, KeyboardInterrupt]) as upload, \
                patch("show.time.sleep"), patch("PIL.Image.Image.save"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            show.main()
        self.assertEqual(connect.call_count, 3)
        self.assertEqual([call.args[0] for call in upload.call_args_list],
                         [stale, recovered, recovered])
        stale.close.assert_called_once()
        recovered.close.assert_called_once()
        self.assertIn("upload confirmed", output.getvalue())

    def test_reader_failure_prevents_writes_until_reconnect(self):
        dev = oled.RogOled.__new__(oled.RogOled)
        dev._stop = threading.Event()
        dev._read_error = None
        dev.dev = Mock()
        dev.dev.read.side_effect = OSError("device disconnected")
        dev._reader()
        with self.assertRaisesRegex(OSError, "device disconnected"):
            dev.write(bytearray(65))
        dev.dev.write.assert_not_called()
        dev.dev.open_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Keep OLED counters aligned with the plugin; never invent missing values."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import codex_stats

# Synthetic identifiers; never copy IDs from real chats into test fixtures.
THREAD = "00000000-0000-4000-8000-000000000001"
OTHER = "11111111-2222-3333-4444-555555555555"


class StatisticsTests(unittest.TestCase):
    def test_total_and_latest_speed_are_not_recomputed_from_other_fields(self):
        raw = {"available": True, "enabled": True, "threadId": THREAD,
               "rounds": 13, "steps": 180, "throughput": 12,
               "usage": {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1300},
               "generation": {"latest": 36.0, "mean": 20.0, "source": "sub2api-request",
                              "estimated": False}}
        result = codex_stats.metrics(raw, THREAD, timestamp=100)
        self.assertEqual((result["rounds"], result["steps"], result["tps"], result["tokens"]),
                         (13, 180, 36.0, 1300))
        self.assertNotIn("usage", result)

    def test_missing_or_invalid_values_do_not_turn_into_zero(self):
        raw = {"available": True, "enabled": True, "threadId": THREAD,
               "rounds": True, "steps": -1, "generation": {"latest": float("nan")}}
        result = codex_stats.metrics(raw, THREAD)
        self.assertTrue(result["available"])
        for field in ("rounds", "steps", "tps", "tokens"):
            self.assertIsNone(result[field])

    def test_wrong_or_missing_thread_is_rejected(self):
        raw = {"available": True, "enabled": True, "threadId": OTHER}
        self.assertFalse(codex_stats.metrics(raw, THREAD)["available"])
        self.assertFalse(codex_stats.metrics({**raw, "threadId": None}, None)["available"])

    def test_local_prefix_does_not_create_a_second_chat(self):
        status = {"enabled": True, "adapter": {"controllerRunning": True},
                  "ui": {"composers": [
                      {"active": True, "hasControl": True, "threadId": THREAD},
                      {"active": True, "hasControl": True, "threadId": "local:" + THREAD}]}}
        self.assertEqual(codex_stats.active_thread(status), THREAD)
        status["ui"]["composers"][1]["threadId"] = OTHER
        self.assertIsNone(codex_stats.active_thread(status))

    def test_disabled_plugin_does_not_select_a_chat(self):
        status = {"enabled": False, "adapter": {"controllerRunning": True},
                  "ui": {"composers": [{"active": True, "hasControl": True, "threadId": THREAD}]}}
        self.assertIsNone(codex_stats.active_thread(status))

    def test_stale_snapshot_is_hidden_and_clock_can_be_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "display-mode.json"
            codex_stats.write_json(state, {"mode": "codex"})
            display = codex_stats.ManagedDisplay(state)
            display.latest = {"available": True, "timestamp": 100, "tps": 36.0}
            with patch("codex_stats.time.time", return_value=120), \
                    patch("codex_stats.pages.codex_stats") as render, \
                    patch("codex_stats.pages.codex_offline") as offline:
                display.frame()
                render.assert_not_called()
                offline.assert_called_once_with("统计暂停更新", None)
            codex_stats.write_json(state, {"mode": "clock"})
            with patch("codex_stats.pages.clock") as clock:
                display.frame()
                clock.assert_called_once()

    def test_inactive_reason_tells_idle_from_multiple_windows(self):
        status = {"enabled": True, "adapter": {"controllerRunning": True}, "ui": {"composers": []}}
        self.assertEqual(codex_stats.inactive_reason(status), "no-active-chat")
        status["ui"]["composers"] = [{"active": True, "hasControl": True, "threadId": THREAD},
                                     {"active": True, "hasControl": True, "threadId": OTHER}]
        self.assertEqual(codex_stats.inactive_reason(status), "multiple-chats")
        status["adapter"]["controllerRunning"] = False
        self.assertEqual(codex_stats.inactive_reason(status), "plugin-disconnected")
        status["enabled"] = False
        self.assertEqual(codex_stats.inactive_reason(status), "plugin-disabled")

    def test_closed_codex_app_is_reported_without_reading_status(self):
        with tempfile.TemporaryDirectory() as folder:
            source = codex_stats.PluginSource(folder)
            source.adapter = Mock()
            source.adapter.official_pids.return_value = []
            source.server = Mock()
            self.assertEqual(source.query()["reason"], "codex-offline")
            source.server.get_status.assert_not_called()

    def test_offline_page_names_the_reason_and_keeps_last_totals(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "display-mode.json"
            codex_stats.write_json(state, {"mode": "codex"})
            last = {"available": True, "timestamp": 50, "rounds": 3, "steps": 9, "tokens": 900}
            codex_stats.write_json(Path(folder) / "codex-last.json", last)
            display = codex_stats.ManagedDisplay(state)
            display.latest = {"available": False, "timestamp": 100, "reason": "codex-offline"}
            with patch("codex_stats.pages.codex_offline") as offline:
                display.frame()
            offline.assert_called_once_with("Codex 未启动", last)

    def test_reused_worker_pid_does_not_terminate_the_new_process(self):
        with tempfile.TemporaryDirectory() as folder:
            codex_stats.write_json(Path(folder) / "codex-stats-worker.json",
                                   {"pid": 123, "created": 10, "owner_pid": 456, "owner_created": 1})
            process = Mock()
            process.create_time.return_value = 20
            with patch("codex_stats.psutil.Process",
                       side_effect=[codex_stats.psutil.NoSuchProcess(456), process]):
                codex_stats.PluginSource(folder)
            process.terminate.assert_not_called()

    def test_reader_with_a_live_owner_is_left_running(self):
        with tempfile.TemporaryDirectory() as folder:
            codex_stats.write_json(Path(folder) / "codex-stats-worker.json",
                                   {"pid": 123, "created": 10, "owner_pid": 456, "owner_created": 1})
            owner = Mock()
            owner.create_time.return_value = 1
            with patch("codex_stats.psutil.Process", return_value=owner) as process:
                codex_stats.PluginSource(folder)
            process.assert_called_once_with(456)
            owner.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()

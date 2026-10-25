"""Claude page: local snapshots only, liveness by change, waiting marks, rocker cycle."""
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import claude_status
import codex_stats
import pages

SESSION = "6f0c5c1e-1111-2222-3333-444455556666"


def fake_statusline(**summary):
    defaults = {"turns": 3, "steps": 7, "total_tokens": 1200, "last_speed": 40.0,
                "state": "tool", "turn_start": 900.0, "state_ts": 990.0, "done_ts": None,
                "last_tool": "mcp__docs__read"}
    defaults.update(summary)
    return types.SimpleNamespace(
        cached_summary=lambda path: defaults,
        remembered_limits=lambda limits: limits or {},
        compact_window=lambda model_id: 400_000,
    )


def status_input(**extra):
    data = {"session_id": SESSION, "transcript_path": "t.jsonl",
            "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
            "context_window": {"used_percentage": 10, "context_window_size": 1_000_000,
                               "current_usage": {"input_tokens": 100_000}},
            "rate_limits": {"five_hour": {"used_percentage": 23, "resets_at": 5000},
                            "seven_day": {"used_percentage": 41, "resets_at": 90000}}}
    data.update(extra)
    return data


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        patcher = patch.object(claude_status, "SNAPSHOT_DIR", Path(self.folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.folder.cleanup)

    def test_snapshot_mirrors_terminal_numbers_without_content(self):
        snap = claude_status.export(status_input(), fake_statusline(), now=1000.0)
        self.assertEqual((snap["turns"], snap["steps"], snap["tokens"], snap["tps"]), (3, 7, 1200, 40.0))
        self.assertEqual(snap["context"], 25.0)  # 100k of the 400k auto-compact window.
        self.assertEqual(snap["tool"], "read")
        self.assertEqual(snap["turn_elapsed"], 100.0)
        self.assertEqual(snap["five_hour"], {"pct": 23.0, "resets_at": 5000})
        self.assertNotIn("transcript_path", snap)
        self.assertTrue((Path(self.folder.name) / f"{SESSION}.json").exists())

    def test_prompt_or_reopen_moves_focus(self):
        snap = claude_status.export(status_input(), fake_statusline(turn_start=500.0), now=1000.0)
        self.assertEqual(snap["focus"], 1000.0)  # Just opened.
        snap = claude_status.export(status_input(), fake_statusline(turn_start=500.0), now=1001.0)
        self.assertEqual(snap["focus"], 1000.0)  # Heartbeat keeps the opening time.
        snap = claude_status.export(status_input(), fake_statusline(turn_start=1004.0), now=1005.0)
        self.assertEqual(snap["focus"], 1004.0)  # Sending a prompt moves focus here.
        snap = claude_status.export(status_input(), fake_statusline(turn_start=1004.0), now=1100.0)
        self.assertEqual(snap["focus"], 1100.0)  # Heartbeat gap: closed and reopened.

    def test_unsafe_session_id_is_not_used_as_a_file_name(self):
        self.assertIsNone(claude_status.export(status_input(session_id="../x"), fake_statusline()))

    def test_long_silent_turn_counts_as_stopped(self):
        snap = claude_status.build_snapshot(status_input(), fake_statusline(state_ts=0.0), now=5000.0)
        self.assertEqual(snap["state"], "stopped")

    def test_waiting_mark_lasts_until_transcript_moves_on(self):
        mark = Path(self.folder.name) / f"{SESSION}.waiting.json"
        claude_status._write_json(mark, {"since": 1000.0, "kind": "permission"})
        snap = claude_status.build_snapshot(status_input(), fake_statusline(state_ts=1000.5), now=1030.0)
        self.assertEqual(snap["waiting"], {"kind": "permission", "elapsed": 30.0})
        snap = claude_status.build_snapshot(status_input(), fake_statusline(state_ts=1010.0), now=1031.0)
        self.assertIsNone(snap["waiting"])
        self.assertFalse(mark.exists())


class ReaderTests(unittest.TestCase):
    def write(self, folder, session, **values):
        snap = {"version": 1, "session_id": session, "updated": 0.0, "state": "done", "activity": 0}
        snap.update(values)
        claude_status._write_json(Path(folder) / f"{session}.json", snap)

    def test_online_only_while_content_keeps_changing(self):
        clock = [100.0]
        with tempfile.TemporaryDirectory() as folder:
            reader = claude_status.ClaudeSessions(folder, clock=lambda: clock[0], wall=lambda: 1000.0)
            self.write(folder, "a", updated=999.0)
            self.assertEqual(reader.read()["count"], 1)
            clock[0] = 106.0  # No new heartbeat for six seconds.
            view = reader.read()
            self.assertIsNone(view["session"])
            self.assertEqual(view["last"]["session_id"], "a")
            self.write(folder, "a", updated=1006.0)
            self.assertEqual(reader.read()["count"], 1)

    def test_clock_drift_does_not_mark_an_old_file_live(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write(folder, "a", updated=10.0)
            reader = claude_status.ClaudeSessions(folder, clock=lambda: 0.0, wall=lambda: 1000.0)
            self.assertIsNone(reader.read()["session"])

    def test_waiting_wins_then_the_session_last_prompted(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write(folder, "busy", updated=1000.0, state="tool", focus=900)
            self.write(folder, "mine", updated=1000.0, focus=990)
            reader = claude_status.ClaudeSessions(folder, clock=lambda: 0.0, wall=lambda: 1000.0)
            self.assertEqual(reader.read()["session"]["session_id"], "mine")
            self.write(folder, "asks", updated=1000.0, focus=10, waiting={"kind": "question"})
            view = reader.read()
            self.assertEqual((view["session"]["session_id"], view["count"]), ("asks", 3))

    def test_limits_come_from_the_newest_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            self.write(folder, "old", updated=900.0, five_hour={"pct": 90})
            self.write(folder, "new", updated=999.0, five_hour={"pct": 5})
            reader = claude_status.ClaudeSessions(folder, clock=lambda: 0.0, wall=lambda: 1000.0)
            self.assertEqual(reader.read()["limits"]["five_hour"], {"pct": 5})


class PageTests(unittest.TestCase):
    def test_every_state_renders_on_the_panel(self):
        base = {"turns": 1, "steps": 2, "tps": 3.5, "tokens": 4000, "context": 50,
                "done_ts": 1000.0, "turn_elapsed": 65}
        for state in ("new", "working", "tool", "done", "interrupted", "stopped"):
            image = pages.claude_stats({"session": {**base, "state": state}, "count": 1}, now=0)
            self.assertEqual(image.size, (208, 64))
        waiting = pages.claude_stats({"session": {**base, "waiting": {"kind": "permission"}}}, now=0)
        self.assertEqual(waiting.getpixel((1, 1)), pages.L1)  # Inverted header.
        offline = pages.claude_stats({"session": None, "last": None}, now=0)
        self.assertEqual(offline.size, (208, 64))

    def test_header_texts(self):
        self.assertEqual(pages.claude_state({"state": "tool", "tool": "Bash", "turn_elapsed": 134})[0],
                         "运行 Bash 2:14")
        self.assertEqual(pages.claude_state({"waiting": {"kind": "question", "elapsed": 5}})[0],
                         "等待回答 0:05")

    def test_passed_reset_hides_the_old_percentage(self):
        self.assertEqual(pages._limit_view({"pct": 70, "resets_at": 10}, 3600, now=20), (None, None))


class RockerCycleTests(unittest.TestCase):
    def test_down_alternates_ai_pages_and_returns_from_clock(self):
        rocker = __import__("rocker_switch")
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "display-mode.json"
            codex_stats.write_json(state, {"mode": "clock"})
            pages_seen = []
            for key in (rocker.DOWN_ID, rocker.DOWN_ID, rocker.UP_ID, rocker.DOWN_ID, rocker.DOWN_ID):
                codex_stats.select_page(state, rocker.next_page(state, key))
                pages_seen.append(codex_stats.mode(state))
            self.assertEqual(pages_seen, ["codex", "claude", "clock", "claude", "codex"])


if __name__ == "__main__":
    unittest.main()

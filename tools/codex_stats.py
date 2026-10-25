"""Read the installed statistics plugin and publish only OLED-sized metrics."""
from __future__ import annotations

import importlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
import uuid

import psutil
import pages
from claude_status import ClaudeSessions

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = (Path.home() / ".codex/plugins/cache/codex-stats/"
                   "codex-native-stats/3.1.1/runtime")
PAGES = ("clock", "codex", "claude")
AI_PAGES = ("codex", "claude")
CODEX_TITLES = {
    "codex-offline": "Codex 未启动",
    "plugin-disabled": "统计插件未启用",
    "plugin-disconnected": "统计未连接",
    "no-active-chat": "无活动对话",
    "multiple-chats": "多个对话窗口",
    "stale": "统计暂停更新",
    None: "读取中",
}


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + f".{os.getpid()}.tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    pending.replace(path)


def mode(state_file):
    state = read_json(state_file, {})
    return state.get("mode") if isinstance(state, dict) and state.get("mode") in PAGES else "clock"


def select_page(state_file, selected, **extra):
    """Switch pages, remembering the last AI page so the rocker can return to it."""
    state = read_json(state_file, {})
    last_ai = state.get("last_ai") if isinstance(state, dict) else None
    last_ai = selected if selected in AI_PAGES else (last_ai if last_ai in AI_PAGES else "codex")
    write_json(state_file, {"mode": selected, "last_ai": last_ai, **extra})


def normalized_thread(value):
    try:
        return str(uuid.UUID(str(value).removeprefix("local:")))
    except (ValueError, AttributeError):
        return None


def active_threads(status):
    ids = {normalized_thread(item.get("threadId"))
           for item in status.get("ui", {}).get("composers", [])
           if item.get("active") and item.get("hasControl") and item.get("identityKind") != "new"}
    ids.discard(None)
    return ids


def active_thread(status):
    if not status.get("enabled") or not status.get("adapter", {}).get("controllerRunning"):
        return None
    ids = active_threads(status)
    return next(iter(ids)) if len(ids) == 1 else None


def inactive_reason(status):
    """Why no single chat is selected, as a key of CODEX_TITLES."""
    if not status.get("enabled"):
        return "plugin-disabled"
    if not status.get("adapter", {}).get("controllerRunning"):
        return "plugin-disconnected"
    return "multiple-chats" if len(active_threads(status)) > 1 else "no-active-chat"


def number(value, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or (integer and value != int(value)):
        return None
    return int(value) if integer else float(value)


def metrics(result, thread_id, timestamp=None):
    """Use the plugin's cumulative total and latest output-rate sample unchanged."""
    snapshot = {"available": False, "timestamp": time.time() if timestamp is None else timestamp}
    if not isinstance(result, dict) or not result.get("available") or not result.get("enabled"):
        return snapshot
    expected_thread = normalized_thread(thread_id)
    if expected_thread is None or normalized_thread(result.get("threadId")) != expected_thread:
        return snapshot
    usage = result.get("usage") or {}
    generation = result.get("generation") or {}
    snapshot.update({
        "available": True,
        "thread_id": normalized_thread(thread_id),
        "rounds": number(result.get("rounds"), integer=True),
        "steps": number(result.get("steps"), integer=True),
        "tps": number(generation.get("latest")),
        "tokens": number(usage.get("total_tokens"), integer=True),
        "speed_source": generation.get("source"),
        "speed_estimated": generation.get("estimated"),
    })
    return snapshot


class PluginSource:
    """Version-pinned bridge; it does not start, inject, or modify the Codex App."""
    def __init__(self, runtime_dir):
        self.runtime_dir = Path(runtime_dir)
        self.owner_file = self.runtime_dir / "codex-stats-worker.json"
        config = read_json(self.runtime_dir / "codex-stats-source.json", {}) or {}
        self.plugin_runtime = Path(config.get("plugin_runtime", DEFAULT_RUNTIME))
        self.node = config.get("node")
        self.adapter = None
        self.server = None
        self.worker = None
        self.cleanup_orphan()

    def cleanup_orphan(self):
        record = read_json(self.owner_file, {}) or {}
        # A second read-only probe must not terminate a live display's reader.
        # Older records without ownership information are not safe to clean.
        if not {"owner_pid", "owner_created"} <= record.keys():
            return
        try:
            owner = psutil.Process(record["owner_pid"])
            if abs(owner.create_time() - record["owner_created"]) < 0.01:
                return
        except (TypeError, ValueError, psutil.Error):
            pass
        try:
            process = psutil.Process(record["pid"])
            script = str(self.plugin_runtime / "usage-worker.cjs")
            if (abs(process.create_time() - record["created"]) < 0.01
                    and process.name().lower() == "node.exe"
                    and script in process.cmdline()):
                process.terminate()
                process.wait(timeout=3)
        except (KeyError, TypeError, ValueError, psutil.Error):
            pass

    def load(self):
        manifest = read_json(self.plugin_runtime.parent / ".codex-plugin/plugin.json", {}) or {}
        if manifest.get("name") != "codex-native-stats" or manifest.get("version") != "3.1.1":
            raise RuntimeError("The statistics bridge requires the installed native-stats 3.1.1 plugin")
        sys.path.insert(0, str(self.plugin_runtime))
        self.adapter = importlib.import_module("official_adapter")
        self.server = importlib.import_module("plugin_server")
        if self.node:
            self.adapter.NODE = self.node

    def query(self):
        if self.adapter is None:
            self.load()
        # Local process list only; a closed Codex App is never started or contacted.
        if not self.adapter.official_pids():
            self.close_worker()
            return {"available": False, "timestamp": time.time(), "reason": "codex-offline"}
        status = self.server.get_status()
        thread_id = active_thread(status)
        if thread_id is None:
            self.close_worker()
            return {"available": False, "timestamp": time.time(), "reason": inactive_reason(status)}
        if self.worker is None:
            self.worker = self.adapter.UsageWorker()
            process = psutil.Process(self.worker.process.pid)
            owner = psutil.Process()
            write_json(self.owner_file, {"pid": process.pid, "created": process.create_time(),
                                        "owner_pid": owner.pid, "owner_created": owner.create_time()})
        return metrics(self.worker.query({"threadId": thread_id}), thread_id)

    def close_worker(self):
        if self.worker is not None:
            worker, self.worker = self.worker, None
            try:
                worker.close()
            finally:
                record = read_json(self.owner_file, {}) or {}
                if record.get("pid") == worker.process.pid:
                    self.owner_file.unlink(missing_ok=True)


class ManagedDisplay:
    def __init__(self, state_file):
        self.state_file = Path(state_file)
        self.runtime_dir = self.state_file.parent
        self.snapshot_file = self.runtime_dir / "codex-stats.json"
        self.last_file = self.runtime_dir / "codex-last.json"
        self.options_file = self.runtime_dir / "display-options.json"
        self.latest = {}
        self.last_codex = read_json(self.last_file)
        self.claude = ClaudeSessions(self.runtime_dir / "claude")
        self.stop_event = threading.Event()
        self.thread = None
        self.current_mode = "clock"

    def start(self):
        self.thread = threading.Thread(target=self.poll, daemon=True, name="oled-statistics")
        self.thread.start()

    def poll(self):
        source = PluginSource(self.runtime_dir)
        previous_error = None
        try:
            while not self.stop_event.is_set():
                if mode(self.state_file) != "codex":
                    source.close_worker()
                    self.latest = {}
                    self.stop_event.wait(1)
                    continue
                try:
                    self.latest = source.query()
                    previous_error = None
                    delay = 2
                    if self.latest.get("available"):
                        self.last_codex = self.latest
                        write_json(self.last_file, self.latest)
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                    self.latest = {"available": False, "timestamp": time.time(), "reason": reason}
                    if reason != previous_error:
                        print(f"[statistics] {reason}", flush=True)
                    previous_error = reason
                    source.close_worker()
                    delay = 5
                write_json(self.snapshot_file, self.latest)
                self.stop_event.wait(delay)
        finally:
            source.close_worker()

    def autojump(self):
        options = read_json(self.options_file, {})
        return isinstance(options, dict) and options.get("claude_waiting_autojump") is True

    def frame(self):
        shown = mode(self.state_file)
        claude = None
        if shown == "claude" or self.autojump():
            claude = self.claude.read()
            # Optional: show Claude while it waits for the user, without changing the chosen page.
            if shown != "claude" and (claude["session"] or {}).get("waiting"):
                shown = "claude"
        self.current_mode = shown
        if shown == "claude":
            return pages.claude_stats(claude)
        if shown != "codex":
            return pages.clock()
        snapshot = self.latest
        if snapshot.get("available"):
            if time.time() - snapshot.get("timestamp", 0) <= 10:
                return pages.codex_stats(snapshot)
            snapshot = {"reason": "stale"}
        reason = snapshot.get("reason")
        return pages.codex_offline(CODEX_TITLES.get(reason, "统计不可用"), self.last_codex)

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=12)

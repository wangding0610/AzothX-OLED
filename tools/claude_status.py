"""Bridge the Claude Code status line to the OLED without any network access.

Claude Code side (WSL): ``claude_status.py statusline`` replaces the status-line
command. It prints the user's own ``~/.claude/statusline.py`` output unchanged,
then writes a small per-session snapshot under ``.runtime/claude/``. The status
line refreshes every second, so a snapshot that stops changing means Claude
Code is closed. ``claude_status.py waiting <kind>`` is a hook that marks a
session as waiting for the user.

Display side (Windows): ``ClaudeSessions`` only reads those files. It never
starts, queries, or contacts Claude. Only counters, state, and tool names are
exported; prompts and replies never leave the transcript.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / ".runtime" / "claude"
STATUSLINE = Path(os.environ.get("OLED_CLAUDE_STATUSLINE", "~/.claude/statusline.py")).expanduser()
ONLINE_SECONDS = 5      # The status line refreshes every second while Claude Code is open.
STALE_SECONDS = 20 * 60  # Same rule as the terminal status line: no new record -> stopped.
WAIT_CLEAR_MARGIN = 2.0  # The tool_use entry is written just before the hook fires.
REOPEN_GAP = 10         # A heartbeat gap this long means the session was closed and reopened.
KEEP_DAYS = 7
WAIT_KINDS = ("permission", "question")


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + f".{os.getpid()}.tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(pending, path)


def _session_id(data):
    value = str((data or {}).get("session_id") or "")
    return value if value and all(c.isalnum() or c in "-_" for c in value) else None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return value


# ------------------------------------------------------------ Claude Code side
def load_statusline(path=STATUSLINE):
    spec = importlib.util.spec_from_file_location("user_statusline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def context_percent(data, module=None):
    """Mirror the terminal: measure against the auto-compact window when it is smaller."""
    ctx = data.get("context_window")
    if not isinstance(ctx, dict) or _number(ctx.get("used_percentage")) is None:
        return None
    pct = float(ctx["used_percentage"])
    size = ctx.get("context_window_size") or 0
    used = sum((ctx.get("current_usage") or {}).get(k, 0) or 0 for k in (
        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")) or pct / 100 * size
    limit = module.compact_window((data.get("model") or {}).get("id")) if module else None
    if limit and (not size or limit < size):
        pct = used / limit * 100
    return round(max(0.0, pct), 1)


def _limit(info):
    if not isinstance(info, dict) or _number(info.get("used_percentage")) is None:
        return None
    return {"pct": float(info["used_percentage"]), "resets_at": _number(info.get("resets_at"))}


def _waiting(session, summary, now):
    """A waiting mark set by the hook lasts until the transcript moves on."""
    path = SNAPSHOT_DIR / f"{session}.waiting.json"
    mark = _read_json(path)
    if not isinstance(mark, dict) or _number(mark.get("since")) is None:
        return None
    latest = max(summary.get("state_ts") or 0, summary.get("done_ts") or 0)
    if latest > mark["since"] + WAIT_CLEAR_MARGIN:
        path.unlink(missing_ok=True)
        return None
    return {"kind": mark.get("kind"), "elapsed": max(0.0, now - mark["since"])}


def _prune(now):
    for entry in SNAPSHOT_DIR.iterdir():
        try:
            if now - entry.stat().st_mtime > KEEP_DAYS * 86400:
                entry.unlink()
        except OSError:
            pass


def build_snapshot(data, module=None, now=None):
    now = time.time() if now is None else now
    session = _session_id(data)
    if session is None:
        return None
    summary = module.cached_summary(data.get("transcript_path")) if module else {}
    limits = module.remembered_limits(data.get("rate_limits")) if module else data.get("rate_limits")
    limits = limits if isinstance(limits, dict) else {}
    state = summary.get("state")
    state_ts, turn_start = summary.get("state_ts"), summary.get("turn_start")
    if state in ("working", "tool") and state_ts is not None and now - state_ts > STALE_SECONDS:
        state = "stopped"
    model = data.get("model") or {}
    return {
        "version": 1,
        "session_id": session,
        "updated": now,
        "model": model.get("display_name") or "Claude",
        "state": state if summary.get("turns") else "new",
        "tool": str(summary.get("last_tool") or "").split("__")[-1][:12] or None,
        "turn_elapsed": max(0.0, now - turn_start) if turn_start and state in ("working", "tool") else None,
        "activity": max(state_ts or 0, summary.get("done_ts") or 0) or None,
        "prompted": turn_start,
        "done_ts": summary.get("done_ts"),
        "turns": summary.get("turns"),
        "steps": summary.get("steps"),
        "tps": summary.get("last_speed"),
        "tokens": summary.get("total_tokens"),
        "context": context_percent(data, module),
        "five_hour": _limit(limits.get("five_hour")),
        "seven_day": _limit(limits.get("seven_day")),
        "waiting": _waiting(session, summary, now) if summary else None,
    }


def export(data, module=None, now=None):
    snapshot = build_snapshot(data, module, now)
    if snapshot is None:
        return None
    path = SNAPSHOT_DIR / f"{snapshot['session_id']}.json"
    first = not path.exists()
    previous = None if first else _read_json(path)
    now = snapshot["updated"]
    # Opening (or resuming) a session counts as switching to it, like sending a prompt.
    opened = now
    if isinstance(previous, dict) and _number(previous.get("opened")) is not None \
            and now - (previous.get("updated") or 0) <= REOPEN_GAP:
        opened = previous["opened"]
    snapshot["opened"] = opened
    snapshot["focus"] = max(snapshot["prompted"] or 0, opened)
    _write_json(path, snapshot)
    if first:
        _prune(snapshot["updated"])
    return snapshot


def run_statusline():
    raw = sys.stdin.read()
    module = None
    try:
        module = load_statusline()
        sys.stdin = io.StringIO(raw)
        module.main()
    except Exception:
        pass
    sys.stdout.flush()
    try:
        export(json.loads(raw), module)
    except Exception:
        pass  # The OLED copy must never break the terminal status line.


def mark_waiting(kind):
    try:
        session = _session_id(json.loads(sys.stdin.read()))
        if session and kind in WAIT_KINDS:
            _write_json(SNAPSHOT_DIR / f"{session}.waiting.json", {"since": time.time(), "kind": kind})
    except Exception:
        pass  # A hook failure must not block the permission prompt.


# ---------------------------------------------------------------- display side
def _order(snapshot):
    """Waiting for the user first, then the session the user last prompted or opened."""
    return (0 if snapshot.get("waiting") else 1,
            -(snapshot.get("focus") or snapshot.get("activity") or 0))


class ClaudeSessions:
    """Judge liveness by content changes seen on this machine's clock.

    WSL and Windows clocks can drift apart after sleep, so a snapshot counts as
    live while its ``updated`` value keeps changing, not by comparing clocks.
    """
    def __init__(self, directory=SNAPSHOT_DIR, clock=time.monotonic, wall=time.time):
        self.directory = Path(directory)
        self.clock, self.wall = clock, wall
        self.cache = {}  # name -> (mtime_ns, size, snapshot)
        self.seen = {}   # name -> (updated, monotonic time the value last changed)

    def _load(self, entry):
        stat = entry.stat()
        cached = self.cache.get(entry.name)
        if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return cached[2]
        snapshot = _read_json(entry.path)
        if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
            snapshot = None
        self.cache[entry.name] = (stat.st_mtime_ns, stat.st_size, snapshot)
        return snapshot

    def read(self):
        now = self.clock()
        online, newest, limits = [], None, None
        try:
            entries = [e for e in os.scandir(self.directory)
                       if e.name.endswith(".json") and not e.name.endswith(".waiting.json")]
        except OSError:
            entries = []
        names = set()
        for entry in entries:
            try:
                snapshot = self._load(entry)
            except OSError:
                continue
            if snapshot is None or _number(snapshot.get("updated")) is None:
                continue
            names.add(entry.name)
            updated = snapshot["updated"]
            previous = self.seen.get(entry.name)
            if previous is None:
                fresh = abs(self.wall() - updated) <= ONLINE_SECONDS
                changed = now if fresh else float("-inf")
            else:
                changed = now if previous[0] != updated else previous[1]
            self.seen[entry.name] = (updated, changed)
            if now - changed <= ONLINE_SECONDS:
                online.append(snapshot)
            if newest is None or updated > newest["updated"]:
                newest = snapshot
            if (snapshot.get("five_hour") or snapshot.get("seven_day")) and (
                    limits is None or updated > limits["updated"]):
                limits = snapshot
        for name in set(self.cache) - names:
            self.cache.pop(name, None)
            self.seen.pop(name, None)
        online.sort(key=_order)
        return {
            "session": online[0] if online else None,
            "count": len(online),
            "last": newest,
            "limits": {"five_hour": limits.get("five_hour"), "seven_day": limits.get("seven_day")}
            if limits else {},
        }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["statusline"]:
        run_statusline()
    elif argv[:1] == ["waiting"] and len(argv) == 2:
        mark_waiting(argv[1])
    else:
        print("usage: claude_status.py statusline | waiting permission|question", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

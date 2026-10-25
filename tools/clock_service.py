"""Windowless clock supervisor, launched directly by Windows via pythonw.exe."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import psutil

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
SHOW = ROOT / "tools/show.py"
WORKER_PID = RUNTIME / "beijing-clock.pid"
# Written by supervisors started before the Beijing rename; still honoured so
# an already-running worker is found and replaced rather than duplicated.
LEGACY_WORKER_PID = RUNTIME / "taipei-clock.pid"
SERVICE_PID = RUNTIME / "clock-supervisor.pid"
NO_WINDOW = subprocess.CREATE_NO_WINDOW


def log(message):
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with (RUNTIME / "clock-supervisor.log").open("a", encoding="utf-8") as stream:
        stream.write(f"[{stamp}] {message}\n")


def write_pid(path, value):
    pending = path.with_suffix(".tmp")
    pending.write_text(str(value), encoding="ascii")
    pending.replace(path)


def clock_process():
    """A stale PID must never authorize stopping an unrelated application."""
    expected = os.path.normcase(str(SHOW))
    for pid_file in (WORKER_PID, LEGACY_WORKER_PID):
        try:
            process = psutil.Process(int(pid_file.read_text().strip()))
            args = process.cmdline()
            if (any(os.path.normcase(os.path.abspath(arg)) == expected for arg in args)
                    and "clock" in args and "--quiet" in args):
                return process
        except (OSError, ValueError, psutil.Error):
            pass
    return None


@contextlib.contextmanager
def runner_lock():
    stream = None
    locked = False
    try:
        stream = (RUNTIME / "clock-runner.lock").open("a+b")
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        locked = True
    except OSError:
        pass
    try:
        yield locked
    finally:
        if stream is not None:
            if locked:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            stream.close()


def spawn_clock(python_path, stdout, stderr):
    # Both supervisor and worker use the GUI executable. Explicit log handles
    # retain stdout/stderr without allocating a console or a Terminal tab.
    pythonw_path = Path(python_path).with_name("pythonw.exe")
    return subprocess.Popen(
        [str(pythonw_path), "-u", str(SHOW), "clock", "--quiet",
         "--display-state", str(RUNTIME / "display-mode.json")],
        cwd=RUNTIME, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
        creationflags=NO_WINDOW,
    )


def supervise(python_path):
    with runner_lock() as locked:
        if not locked:
            return 0
        write_pid(SERVICE_PID, os.getpid())
        log(f"Windowless supervisor started. PID={os.getpid()}")
        child = None
        rocker = None
        try:
            from codex_stats import read_json
            if (read_json(RUNTIME / "rocker-config.json", {}) or {}).get("enabled"):
                from rocker_switch import RockerSwitch
                rocker = RockerSwitch(RUNTIME / "display-mode.json", log)
                rocker.start()
            while True:
                try:
                    orphan = clock_process()
                    if orphan is not None:
                        orphan.terminate()
                        orphan.wait(timeout=5)
                    for name in ("beijing-clock.log", "beijing-clock-error.log"):
                        path = RUNTIME / name
                        if path.exists():
                            shutil.copyfile(path, str(path) + ".previous")
                    with (RUNTIME / "beijing-clock.log").open("wb") as output, \
                            (RUNTIME / "beijing-clock-error.log").open("wb") as errors:
                        child = spawn_clock(python_path, output, errors)
                        write_pid(WORKER_PID, child.pid)
                        LEGACY_WORKER_PID.unlink(missing_ok=True)
                        log(f"Clock started without console. PID={child.pid}")
                        code = child.wait()
                        log(f"Clock exited. PID={child.pid}, exit={code}; restarting in 3s.")
                        child = None
                except Exception:
                    log(f"Clock launch failed; retrying in 3s.\n{traceback.format_exc()}")
                    if child is not None and child.poll() is None:
                        child.terminate()
                        child.wait(timeout=5)
                    child = None
                time.sleep(3)
        finally:
            if rocker is not None:
                rocker.stop()
            if child is not None and child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
            if SERVICE_PID.exists() and SERVICE_PID.read_text().strip() == str(os.getpid()):
                SERVICE_PID.unlink()


def control(action):
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    with (RUNTIME / "clock-control.log").open("ab") as output:
        result = subprocess.run(
            [str(shell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(ROOT / "tools/clock_control.ps1"), "-Action", action],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
        )
    return result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "start", "codex", "claude", "stop", "status"))
    parser.add_argument("--python", default=str(Path(sys.executable).with_name("python.exe")))
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    if args.action != "run":
        if args.action in ("start", "codex", "claude"):
            from codex_stats import select_page
            select_page(RUNTIME / "display-mode.json",
                        "clock" if args.action == "start" else args.action)
            return control("start")
        return control(args.action)
    python_path = Path(args.python)
    if not python_path.is_file() or not python_path.with_name("pythonw.exe").is_file():
        raise FileNotFoundError(python_path)
    return supervise(python_path)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        RUNTIME.mkdir(exist_ok=True)
        log(f"Supervisor failed.\n{traceback.format_exc()}")
        sys.exit(1)

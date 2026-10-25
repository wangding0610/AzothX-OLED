"""Use two dedicated numpad keys from the Azoth X custom rocker as page selectors.

Up shows the clock. Down alternates between the Codex and Claude pages; coming
from the clock it returns to whichever of the two was shown last.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import threading
import time

from codex_stats import AI_PAGES, mode, read_json, select_page, write_json

WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
MOD_NOREPEAT = 0x4000
UP_ID, DOWN_ID = 0x7151, 0x7152
BINDINGS = {
    UP_ID: (0x6D, "NumpadSubtract"),
    DOWN_ID: (0x6B, "NumpadAdd"),
}


def next_page(state_file, key_id):
    if key_id == UP_ID:
        return "clock"
    current = mode(state_file)
    if current in AI_PAGES:
        return "claude" if current == "codex" else "codex"
    state = read_json(state_file, {})
    last_ai = state.get("last_ai") if isinstance(state, dict) else None
    return last_ai if last_ai in AI_PAGES else "codex"


class RockerSwitch:
    def __init__(self, state_file, logger=lambda message: None):
        self.state_file = Path(state_file)
        self.status_file = self.state_file.parent / "rocker-status.json"
        self.logger = logger
        self.ready = threading.Event()
        self.thread_id = None
        self.thread = None
        self.registered = False
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.user32.RegisterHotKey.restype = wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.UnregisterHotKey.restype = wintypes.BOOL
        self.user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.user32.GetMessageW.restype = wintypes.BOOL
        self.user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        self.user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.PostThreadMessageW.restype = wintypes.BOOL

    def status(self, **values):
        write_json(self.status_file, {"ready": self.registered, "thread_id": self.thread_id,
                                     "updated": time.time(), **values})

    def start(self):
        self.thread = threading.Thread(target=self.run, name="oled-rocker", daemon=True)
        self.thread.start()
        self.ready.wait(timeout=2)
        return self.registered

    def apply(self, key_id):
        binding = BINDINGS.get(key_id)
        if binding is None:
            return
        _, key_name = binding
        selected = next_page(self.state_file, key_id)
        select_page(self.state_file, selected, source="rocker", key=key_name, updated=time.time())
        self.logger(f"Rocker: {key_name} -> {selected}")

    def run(self):
        registered_ids = []
        try:
            self.thread_id = self.kernel32.GetCurrentThreadId()
            message = wintypes.MSG()
            self.user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
            for key_id, (vk, name) in BINDINGS.items():
                if not self.user32.RegisterHotKey(None, key_id, MOD_NOREPEAT, vk):
                    raise OSError(ctypes.get_last_error(), f"Cannot register rocker key {name}")
                registered_ids.append(key_id)
            self.registered = True
            self.status(up="NumpadSubtract -> clock", down="NumpadAdd -> codex/claude")
            self.logger("Rocker shortcuts ready: numpad minus=clock, numpad plus=codex/claude")
            self.ready.set()
            while True:
                result = self.user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == 0:
                    break
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if message.message == WM_HOTKEY:
                    self.apply(int(message.wParam))
        except Exception as exc:
            self.logger(f"Rocker listener failed: {exc}")
            self.registered = False
            self.status(error=str(exc))
        finally:
            for key_id in registered_ids:
                self.user32.UnregisterHotKey(None, key_id)
            self.registered = False
            self.ready.set()

    def stop(self):
        if self.thread_id is not None and self.thread is not None and self.thread.is_alive():
            self.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
            self.thread.join(timeout=2)

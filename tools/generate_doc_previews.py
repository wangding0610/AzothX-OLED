"""Render public documentation from fixed, fictional data without device access."""
from datetime import datetime
from pathlib import Path

from PIL import Image

import pages
from oled import render_4bpp


ROOT = Path(__file__).resolve().parents[1]


def save_preview(name, frame):
    packed = render_4bpp(frame, pages.W, pages.H)
    pixels = bytes(channel * 17 for value in packed
                   for channel in (value & 0x0F, value >> 4))
    decoded = Image.frombytes("L", (pages.W, pages.H), pixels)
    expected = frame.convert("L").point(lambda value: (value // 16) * 17)
    if decoded.tobytes() != expected.tobytes():
        raise ValueError(f"Pixel encoding mismatch: {name}")
    decoded.resize((pages.W * 5, pages.H * 5), Image.Resampling.NEAREST).save(
        ROOT / "docs" / name)


def main():
    # These values are invented for documentation, not taken from a session.
    moment = datetime(2030, 6, 15, 12, 34, 56, tzinfo=pages.BEIJING_TZ)
    now = moment.timestamp()
    codex = {"rounds": 12, "steps": 64, "tps": 42.0, "tokens": 1_200_000}
    claude = {
        "state": "working", "turn_elapsed": 83, "turns": 8, "steps": 36,
        "tps": 56.0, "tokens": 1_600_000, "context": 48,
        "five_hour": {"pct": 24, "resets_at": now + 3 * 3600},
        "seven_day": {"pct": 36, "resets_at": now + 4 * 86400},
    }
    save_preview("beijing-clock-preview.png", pages.clock(moment))
    save_preview("codex-stats-preview.png", pages.codex_stats(codex))
    save_preview("claude-stats-preview.png", pages.claude_stats(
        {"session": claude, "count": 1}, now=now))
    print("Generated 3 fictional previews; encoded pixels verified; no hardware accessed.")


if __name__ == "__main__":
    main()

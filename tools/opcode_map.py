"""Map every `array[1] = NN;` (command opcode) to its enclosing class in KBApi source."""
from pathlib import Path
import re

# Supply this file locally; vendor sources are not distributed with the repo.
SRC = Path(__file__).resolve().parents[1] / "decompiled" / "GearLink_KBApi.decompiled.cs"
lines = open(SRC, encoding="utf-8").read().splitlines()

cur = "?"
for i, line in enumerate(lines, 1):
    m = re.match(r"\s*public class (\w+)", line)
    if m:
        cur = m.group(1)
    m = re.search(r"array\[1\]\s*=\s*(\d+);", line)
    if m:
        m2 = re.search(r"array\[2\]\s*=\s*(\d+);", lines[i] if i < len(lines) else "")
        sub = m2.group(1) if m2 else "-"
        print(f"{i:6d}  {cur:38s} cmd=0x{int(m.group(1)):02X}({m.group(1)}) sub={sub}")

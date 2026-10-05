"""Dump generated P1/P2 scripts and original sb3 blocks for movement comparison."""
import re
from pathlib import Path

ROOT = Path(r"C:\Users\werop\ScratchFileConverter")
MAIN = ROOT / "build" / "dev-fg" / "main.py"
SB3 = Path.home() / "Downloads" / "Saves" / "Fighting Game.sb3"

# --- generated side ---
src = MAIN.read_text(encoding="utf-8")
lines = src.splitlines()
fns = re.findall(r"^def (\w+)\(", src, re.M)
print("=== generated functions:", len(fns))

# find functions whose body mentions key_down with movement-ish content
blocks = re.split(r"^(?=def )", src, flags=re.M)
for b in blocks:
    m = re.match(r"def (\w+)", b)
    if not m:
        continue
    if "key_down" in b and re.search(r"\.(x|y)\b|move|direction|point", b):
        print("----", m.group(1))
        print(b[:2400])
        print()

"""Real-window probe: post real KEYDOWN/KEYUP into SDL queue, log positions in-process."""
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

os.environ.pop("SDL_VIDEODRIVER", None)
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.chdir(Path(__file__).resolve().parent.parent / "build" / "dev-fg")
sys.path.insert(0, ".")

import main as gen  # noqa: E402
import pygame  # noqa: E402

spec = importlib.util.spec_from_file_location("rt_mod", "runtime.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["rt_mod"] = mod
spec.loader.exec_module(mod)

rows = []
orig_draw = mod.Runtime.draw


def draw(self):
    orig_draw(self)
    p1 = next((a for a in self.actors if a.target.name == "Player 1"), None)
    if p1 is not None:
        rows.append(
            (time.perf_counter(), round(p1.x, 1), round(p1.y, 1),
             p1.costume.name if p1.costume else None, ",".join(sorted(self.down_keys)))
        )


mod.Runtime.draw = draw


def poster():
    time.sleep(2.0)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))
    time.sleep(2.5)
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_d))
    time.sleep(0.5)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w))
    time.sleep(1.5)
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_w))


threading.Thread(target=poster, daemon=True).start()

with open("sb3_manifest.json", encoding="utf-8") as fh:
    manifest = json.load(fh)
rt = mod.Runtime(manifest, gen.SCRIPTS, manifest_path=None, smoke=240, seed=1)
rt.run()

t0 = rows[0][0] if rows else 0
prev = None
for t, x, y, c, keys in rows:
    state = (x, y, c, keys)
    if state != prev:
        print(f"t={t - t0:5.2f}s  x={x:7.1f} y={y:7.1f}  {c}  keys=[{keys}]")
        prev = state

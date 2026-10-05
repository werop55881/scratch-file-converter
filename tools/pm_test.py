"""Post WM_KEYDOWN to our own window via user32, log down_keys + x in-process."""
import ctypes
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

spec = importlib.util.spec_from_file_location("rt_mod", "runtime.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["rt_mod"] = mod
spec.loader.exec_module(mod)

u32 = ctypes.windll.user32
u32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
u32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
rows = []
orig_draw = mod.Runtime.draw


def draw(self):
    orig_draw(self)
    p1 = next((a for a in self.actors if a.target.name == "Player 1"), None)
    if p1 is not None:
        rows.append((time.perf_counter(), round(p1.x, 1), round(p1.y, 1),
                     p1.costume.name if p1.costume else None, ",".join(sorted(self.down_keys))))


mod.Runtime.draw = draw


def keyer():
    hwnd = 0
    pid = os.getpid()
    for _ in range(120):
        time.sleep(0.25)
        found = []
        EnumWindows = u32.EnumWindows

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(h, _, _found=found):
            wpid = ctypes.c_uint()
            u32.GetWindowThreadProcessId(h, ctypes.byref(wpid))
            if wpid.value == pid:
                buf = ctypes.create_unicode_buffer(256)
                u32.GetWindowTextW(h, buf, 256)
                if buf.value == "Fighting Game":
                    _found.append(h)
            return True

        EnumWindows(cb, None)
        if found:
            hwnd = found[0]
            break
    if not hwnd:
        print("PM: window not found")
        return
    print(f"PM: window {hwnd:#x} — posting d down")
    sc = u32.MapVirtualKeyW(0x44, 0)
    lp = 0x00000001 | (sc << 16)
    u32.PostMessageW(hwnd, 0x100, 0x44, lp)          # WM_KEYDOWN d
    time.sleep(2.5)
    print("PM: posting d up")
    u32.PostMessageW(hwnd, 0x101, 0x44, 0xC0000001 | (sc << 16))  # WM_KEYUP


threading.Thread(target=keyer, daemon=True).start()

with open("sb3_manifest.json", encoding="utf-8") as fh:
    manifest = json.load(fh)
rt = mod.Runtime(manifest, gen.SCRIPTS, manifest_path=None, smoke=240, seed=1)
rt.run()

t0 = rows[0][0] if rows else 0
prev = None
shown = 0
for t, x, y, c, keys in rows:
    state = (x, y, c, keys)
    if state != prev and shown < 60:
        print(f"t={t - t0:5.2f}s  x={x:7.1f} y={y:7.1f}  {c}  keys=[{keys}]")
        prev = state
        shown += 1
print(f"... {len(rows)} frames total, final x={rows[-1][1]}")

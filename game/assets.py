"""Procedural assets for the star game: PNG pictures, a 5x7 bitmap font and
WAV sound effects. Pure standard library (zlib, struct, wave) so the game can
be built without pygame installed.
"""

from __future__ import annotations

import io
import math
import random
import struct
import wave
import zlib

RGBA = tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# PNG encoding
# ---------------------------------------------------------------------------


def png_bytes(width: int, height: int, data: bytes) -> bytes:
    """Encode raw RGBA rows (width * height * 4 bytes) as a PNG."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    stride = width * 4
    raw = b"".join(b"\x00" + data[y * stride : (y + 1) * stride] for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------


class Canvas:
    """A tiny RGBA drawing surface: rectangles, circles, rings, polygons."""

    def __init__(self, width: int, height: int, bg: RGBA = (0, 0, 0, 0)) -> None:
        self.width = width
        self.height = height
        self.data = bytearray(bytes(bg) * (width * height))

    def blend(self, x: int, y: int, color: RGBA) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        r, g, b, a = color
        if a <= 0:
            return
        i = (y * self.width + x) * 4
        if a >= 255:
            self.data[i : i + 4] = bytes((r, g, b, 255))
            return
        inv = 255 - a
        sr, sg, sb, sa = self.data[i], self.data[i + 1], self.data[i + 2], self.data[i + 3]
        out_a = a + sa * inv / 255.0
        if out_a <= 0:
            return
        self.data[i] = min(255, int((r * a + sr * sa * inv / 255.0) / out_a))
        self.data[i + 1] = min(255, int((g * a + sg * sa * inv / 255.0) / out_a))
        self.data[i + 2] = min(255, int((b * a + sb * sa * inv / 255.0) / out_a))
        self.data[i + 3] = min(255, int(out_a))

    def fill(self, color: RGBA) -> None:
        self.fill_rect(0, 0, self.width, self.height, color)

    def fill_rect(self, x: int, y: int, w: int, h: int, color: RGBA) -> None:
        x0, y0 = max(0, x), max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        for py in range(y0, y1):
            for px in range(x0, x1):
                self.blend(px, py, color)

    def _span(self, y: int, x0: float, x1: float, color: RGBA) -> None:
        if y < 0 or y >= self.height:
            return
        ix0 = max(0, int(math.ceil(x0 - 0.5)))
        ix1 = min(self.width - 1, int(math.floor(x1 - 0.5)))
        for x in range(ix0, ix1 + 1):
            self.blend(x, y, color)

    def circle(self, cx: float, cy: float, r: float, color: RGBA) -> None:
        if r <= 0:
            return
        for py in range(int(cy - r - 1), int(cy + r + 2)):
            dy = py + 0.5 - cy
            inside = r * r - dy * dy
            if inside <= 0:
                continue
            dx = math.sqrt(inside)
            self._span(py, cx - dx, cx + dx, color)

    def ring(self, cx: float, cy: float, r: float, thickness: float, color: RGBA) -> None:
        outer = r + thickness / 2.0
        inner = max(0.0, r - thickness / 2.0)
        if outer <= 0:
            return
        for py in range(int(cy - outer - 1), int(cy + outer + 2)):
            dy = py + 0.5 - cy
            o = outer * outer - dy * dy
            i = inner * inner - dy * dy
            if o <= 0:
                continue
            dx = math.sqrt(o)
            if i <= 0:
                self._span(py, cx - dx, cx + dx, color)
            else:
                di = math.sqrt(i)
                self._span(py, cx - dx, cx - di, color)
                self._span(py, cx + di, cx + dx, color)

    def ellipse_ring(
        self, cx: float, cy: float, rx: float, ry: float, thickness: float, color: RGBA
    ) -> None:
        outer_x, outer_y = rx + thickness / 2.0, ry + thickness / 2.0
        inner_x, inner_y = max(0.5, rx - thickness / 2.0), max(0.5, ry - thickness / 2.0)
        steps = max(24, int((rx + ry) * 3))
        outer_pts = []
        inner_pts = []
        for step in range(steps):
            a = 2.0 * math.pi * step / steps
            outer_pts.append((cx + outer_x * math.cos(a), cy + outer_y * math.sin(a)))
            inner_pts.append((cx + inner_x * math.cos(a), cy + inner_y * math.sin(a)))
        self.polygon(outer_pts, color)
        self.polygon(list(reversed(inner_pts)), (0, 0, 0, 0))

    def polygon(self, points: list[tuple[float, float]], color: RGBA) -> None:
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        for y in range(int(min(ys)), int(max(ys)) + 1):
            yc = y + 0.5
            xs: list[float] = []
            count = len(points)
            for i in range(count):
                x1, y1 = points[i]
                x2, y2 = points[(i + 1) % count]
                if (y1 <= yc < y2) or (y2 <= yc < y1):
                    xs.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self._span(y, xs[i], xs[i + 1], color)

    def line(
        self, x0: float, y0: float, x1: float, y1: float, thickness: float, color: RGBA
    ) -> None:
        steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0))))
        r = max(0.5, thickness / 2.0)
        for step in range(steps + 1):
            t = step / steps
            self.circle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, color)

    def to_png(self) -> bytes:
        return png_bytes(self.width, self.height, bytes(self.data))


# ---------------------------------------------------------------------------
# 5x7 bitmap font
# ---------------------------------------------------------------------------

_FONT_ROWS: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    ":": ("00000", "00100", "00000", "00000", "00100", "00000", "00000"),
    "-": ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00100", "00100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "$": ("00100", "01111", "10100", "01110", "00101", "11110", "00100"),
    "'": ("00100", "00100", "00000", "00000", "00000", "00000", "00000"),
    ",": ("00000", "00000", "00000", "00000", "00100", "00100", "01000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
}


def text_width(text: str, scale: int = 1) -> int:
    return max(0, len(text) * 6 * scale - scale)


def draw_text(
    canvas: Canvas, text: str, x: int, y: int, color: RGBA, scale: int = 1
) -> None:
    cursor = x
    for ch in text.upper():
        glyph = _FONT_ROWS.get(ch, _FONT_ROWS[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    canvas.fill_rect(
                        cursor + col * scale, y + row * scale, scale, scale, color
                    )
        cursor += 6 * scale


# ---------------------------------------------------------------------------
# WAV sounds
# ---------------------------------------------------------------------------


def wav_bytes(samples: list[float], rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples
        )
        handle.writeframes(frames)
    return buf.getvalue()


def click_wav(rate: int = 22050) -> tuple[bytes, int]:
    count = int(rate * 0.07)
    out = []
    for i in range(count):
        t = i / rate
        freq = 1400 - 900 * (t / 0.07)
        env = math.exp(-t * 45)
        out.append(0.45 * env * math.sin(2 * math.pi * freq * t))
    return wav_bytes(out, rate), count


def buy_wav(rate: int = 22050) -> tuple[bytes, int]:
    count = int(rate * 0.2)
    out = []
    for i in range(count):
        t = i / rate
        if t < 0.08:
            freq, level = 700.0, 0.4
            env = (1.0 - t / 0.08) * 0.5 + 0.5
        else:
            freq, level = 1050.0, 0.4
            env = max(0.0, 1.0 - (t - 0.08) / 0.12)
        out.append(level * env * (math.sin(2 * math.pi * freq * t) * 0.8))
    return wav_bytes(out, rate), count


def nova_wav(rate: int = 22050) -> tuple[bytes, int]:
    rng = random.Random(4)
    count = int(rate * 0.8)
    lowpass = 0.0
    out = []
    for i in range(count):
        t = i / rate
        noise = rng.uniform(-1.0, 1.0)
        lowpass += 0.2 * (noise - lowpass)
        env = math.exp(-t * 5.0)
        rumble = math.sin(2 * math.pi * 55 * t) * math.exp(-t * 3.0)
        out.append(0.5 * lowpass * env + 0.4 * rumble)
    return wav_bytes(out, rate), count


# ---------------------------------------------------------------------------
# Costumes
# ---------------------------------------------------------------------------


def star_points(cx: float, cy: float, r_out: float, r_in: float, rot: float = -90.0):
    points = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 18.0)
        points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return points


def star_png() -> bytes:
    c = Canvas(100, 100)
    c.polygon(star_points(50, 50, 48, 21), (255, 150, 20, 255))
    c.polygon(star_points(50, 50, 44, 19), (255, 224, 70, 255))
    c.polygon(star_points(50, 50, 21, 9), (255, 250, 210, 255))
    c.circle(50, 50, 7, (255, 255, 255, 255))
    return c.to_png()


def star_nova_png() -> bytes:
    c = Canvas(110, 110)
    for i in range(12):
        a = math.radians(i * 30 + 8)
        r0, r1 = 30.0, 52.0 if i % 2 == 0 else 44.0
        c.line(
            55 + r0 * math.cos(a),
            55 + r0 * math.sin(a),
            55 + r1 * math.cos(a),
            55 + r1 * math.sin(a),
            4.0,
            (255, 240, 170, 220),
        )
    c.circle(55, 55, 36, (255, 255, 255, 80))
    c.circle(55, 55, 26, (255, 236, 140, 230))
    c.circle(55, 55, 16, (255, 255, 255, 255))
    return c.to_png()


def bgstar_png() -> bytes:
    c = Canvas(40, 40)
    sparkle = [(20, 1), (24, 16), (39, 20), (24, 24), (20, 39), (16, 24), (1, 20), (16, 16)]
    c.polygon(sparkle, (255, 255, 255, 235))
    c.circle(20, 20, 4.5, (255, 255, 255, 255))
    return c.to_png()


def bgstar_nova_png() -> bytes:
    c = Canvas(64, 64)
    for i in range(8):
        a = math.radians(i * 45)
        c.line(
            32 + 11 * math.cos(a),
            32 + 11 * math.sin(a),
            32 + 28 * math.cos(a),
            32 + 28 * math.sin(a),
            3.0,
            (255, 255, 255, 230),
        )
    c.ring(32, 32, 20, 2.5, (130, 225, 255, 200))
    c.circle(32, 32, 10, (255, 255, 255, 255))
    return c.to_png()


_PLANET_SKINS: tuple[tuple[RGBA, RGBA, RGBA | None, RGBA | None], ...] = (
    ((255, 196, 64, 255), (255, 236, 150, 255), None, None),
    ((186, 92, 58, 255), (226, 140, 96, 255), (140, 60, 40, 200), None),
    ((110, 196, 255, 255), (220, 246, 255, 255), None, (190, 226, 255, 220)),
    ((232, 74, 48, 255), (255, 150, 90, 255), (160, 30, 20, 170), None),
    ((154, 84, 224, 255), (210, 150, 255, 255), None, None),
)


def planet_png(index: int) -> bytes:
    base, light, stripe, ring_color = _PLANET_SKINS[index % len(_PLANET_SKINS)]
    c = Canvas(72, 72)
    cx = cy = 36.0
    r = 30.0
    if ring_color is not None:
        c.ellipse_ring(cx, cy, 42.0, 13.0, 4.0, ring_color)
    c.circle(cx, cy, r, base)
    c.circle(cx - 5, cy - 6, r - 7, light)
    if stripe is not None:
        for band in (8, -4, -16):
            half = math.sqrt(max(0.0, r * r - (band - 0.0) ** 2))
            if half > 2:
                c._span(int(cy + band), cx - half, cx - half + 6, stripe)
                c._span(int(cy + band + 4), cx + half - 8, cx + half, stripe)
    if index == 4:
        c.circle(cx, cy, 10, (240, 220, 255, 255))
        c.ring(cx, cy, 15, 3, (250, 235, 255, 200))
    c.circle(cx - 12, cy - 13, 7, (255, 255, 255, 130))
    return c.to_png()


def shop_row_png(index: int) -> bytes:
    accent = ((120, 220, 255), (255, 200, 120), (255, 140, 180))[index % 3]
    c = Canvas(180, 100, (14, 20, 44, 250))
    c.fill_rect(0, 0, 180, 2, (86, 110, 170, 255))
    c.fill_rect(0, 98, 180, 2, (86, 110, 170, 255))
    c.fill_rect(0, 0, 2, 100, (86, 110, 170, 255))
    c.fill_rect(178, 0, 2, 100, (86, 110, 170, 255))
    c.fill_rect(2, 2, 176, 1, (120, 150, 210, 255))
    c.circle(20, 50, 9, (*accent, 255))
    c.circle(20, 50, 5, (255, 255, 255, 255))
    return c.to_png()


def backdrop_png() -> bytes:
    width, height = 480, 360
    c = Canvas(width, height)
    for y in range(height):
        t = y / (height - 1)
        r = int(8 + 22 * t)
        g = int(8 + 10 * t)
        b = int(26 + 38 * t)
        c.fill_rect(0, y, width, 1, (r, g, b, 255))
    rng = random.Random(7)
    for _ in range(160):
        x = rng.randrange(width)
        y = rng.randrange(height)
        radius = 1 if rng.random() < 0.78 else 2
        alpha = rng.randrange(40, 150)
        shade = rng.randrange(180, 256)
        c.circle(x, y, radius, (shade, shade, min(255, shade + 20), alpha))
    draw_text(c, "STAR SHOP", 40, 12, (120, 225, 255, 255), scale=2)
    return c.to_png()

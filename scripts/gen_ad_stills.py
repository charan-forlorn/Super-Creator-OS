"""Generate procedural source stills for the AI Automation advertisement."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

OUT_ROOT = Path("C:/Workspace/super-creator-os/scos/work/ai-auto-ad-c1b9427f/source-assets")
OUT_ROOT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920  # Target canvas

# --- Minimal RGBA compositor (no PIL dependency) --------------------------

def _lerp(a, b, t):
    return int(a + (b - a) * max(0.0, min(1.0, t)))


def _mix(c1, c2, t):
    return tuple(_lerp(a, b, t) for a, b in zip(c1, c2))


def _hex(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rect(buf, x1, y1, x2, y2, color):
    for y in range(max(0, y1), min(H, y2)):
        for x in range(max(0, x1), min(W, x2)):
            buf[y][x] = color


def _text(buf, text, cx, cy, size=80, color=(255, 255, 255)):
    """Render simple block text (for headlines / CTA)."""
    # Use a 5x7 bitmap for uppercase ASCII + digits + symbols
    FONT = {
        "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
        "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
        "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
        "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
        "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
        "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
        "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
        "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
        "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
        "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
        "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
        "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
        "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
        "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
        "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
        "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
        "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
        "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
        "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
        "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
        "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
        "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
        "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
        "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
        "Y": ["10001", "10001", "10001", "01010", "00100", "00100", "00100"],
        "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
        "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
        "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
        "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
        "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
        "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
        "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
        "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
        "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
        "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
        "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
        " ": ["00000"] * 7,
        "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
        ":": ["00000", "00100", "00100", "00000", "00100", "00100", "00000"],
        ".": ["00000"] * 6 + ["00100"],
        ",": ["00000"] * 5 + ["00100", "01000"],
        "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
        "?": ["01110", "10001", "00001", "00010", "00100", "00000", "00100"],
        ">": ["10000", "01000", "00100", "00010", "00100", "01000", "10000"],
        "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
        "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
        ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
    }

    text = text.upper()
    glyph_w = 6
    total_w = len(text) * glyph_w * size
    start_x = cx - total_w // 2
    y0 = cy - (7 * size) // 2
    for ci, ch in enumerate(text):
        g = FONT.get(ch, FONT["?"])
        for ry, row in enumerate(g):
            for rx, bit in enumerate(row):
                if bit == "1":
                    gx = start_x + ci * glyph_w * size + rx * size
                    gy = y0 + ry * size
                    _rect(buf, gx, gy, gx + size, gy + size, color)


def _grid_nodes(buf, cx, cy, rows=3, cols=5, radius=20, gap=90, color=(0, 200, 255)):
    """Draw a grid of 'nodes' with connecting lines — orchestration pattern."""
    positions = []
    for r in range(rows):
        for c in range(cols):
            x = int(cx + (c - (cols - 1) / 2) * gap)
            y = int(cy + (r - (rows - 1) / 2) * gap)
            positions.append((x, y))
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx * dx + dy * dy <= radius * radius:
                        py, px = y + dy, x + dx
                        if 0 <= py < H and 0 <= px < W:
                            buf[py][px] = color
    # Connect horizontal + vertical
    for r in range(rows):
        for c in range(cols - 1):
            i = r * cols + c
            x1, y1 = positions[i]
            x2, y2 = positions[i + 1]
            steps = int(max(abs(x2 - x1), abs(y2 - y1)))
            for s in range(steps):
                t = s / max(1, steps)
                px = int(x1 + (x2 - x1) * t)
                py = int(y1 + (y2 - y1) * t)
                if 0 <= py < H and 0 <= px < W:
                    buf[py][px] = (0, 120, 200)
    for r in range(rows - 1):
        for c in range(cols):
            i = r * cols + c
            x1, y1 = positions[i]
            x2, y2 = positions[i + cols]
            steps = int(max(abs(x2 - x1), abs(y2 - y1)))
            for s in range(steps):
                t = s / max(1, steps)
                px = int(x1 + (x2 - x1) * t)
                py = int(y1 + (y2 - y1) * t)
                if 0 <= py < H and 0 <= px < W:
                    buf[py][px] = (0, 120, 200)
    return positions


def _ring(buf, cx, cy, r, color, thickness=8):
    for a in range(360):
        t = math.radians(a)
        for th in range(thickness):
            px = int(cx + math.cos(t) * (r + th - thickness // 2))
            py = int(cy + math.sin(t) * (r + th - thickness // 2))
            if 0 <= py < H and 0 <= px < W:
                buf[py][px] = color


def _progress_bar(buf, cx, cy, w, h, pct, fg=(0, 255, 100), bg=(40, 40, 40)):
    _rect(buf, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2, bg)
    fill = int(w * max(0, min(1, pct)))
    _rect(buf, cx - w // 2, cy - h // 2, cx - w // 2 + fill, cy + h // 2, fg)


def _pipeline(buf, cx, cy, stages, label):
    """Draw a horizontal pipeline with stages."""
    box_w, box_h = 140, 80
    total_w = len(stages) * (box_w + 60)
    x0 = cx - total_w // 2
    for i, stage in enumerate(stages):
        x = x0 + i * (box_w + 60)
        _rect(buf, x, cy - box_h // 2, x + box_w, cy + box_h // 2, (30, 30, 30))
        _rect(buf, x + 2, cy - box_h // 2 + 2, x + box_w - 2, cy + box_h // 2 - 2, (50, 50, 50))
        _text(buf, stage[:10], x + box_w // 2, cy, size=28, color=(0, 220, 255))
        if i > 0:
            _rect(buf, x - 60, cy - 4, x, cy + 4, (0, 180, 255))
    _text(buf, label, cx, cy - box_h // 2 - 60, size=32, color=(180, 180, 180))


def _bg_gradient(c1, c2):
    buf = []
    for y in range(H):
        t = y / (H - 1)
        row = [_mix(c1, c2, t)] * W
        buf.append(row)
    return buf


def save_png(buf, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal PNG writer
    import struct, zlib
    raw = bytearray()
    for row in buf:
        raw.append(0)  # filter type 0
        for px in row:
            raw.extend(px[:3])
    compressed = zlib.compress(bytes(raw), 9)
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        c += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return c
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
    path.write_bytes(png)
    sha = hashlib.sha256(png).hexdigest()
    return sha


# ==================== SCENE STILLS ====================

def scene_hook():
    """Shot 01: Visual overload — layers of clips, folders, fragments."""
    buf = _bg_gradient((5, 5, 15), (20, 10, 40))
    # "Files / clips" floating rectangles
    colors = [(0, 180, 255), (0, 255, 180), (255, 80, 160), (255, 200, 0), (0, 120, 255)]
    for i in range(25):
        import random
        random.seed(i)
        x = random.randint(50, W - 250)
        y = random.randint(100, H - 300)
        w = random.randint(120, 240)
        h = random.randint(60, 180)
        c = colors[i % len(colors)]
        _rect(buf, x, y, x + w, y + h, c)
        _rect(buf, x + 2, y + 2, x + w - 2, y + h - 2, _mix(c, (0, 0, 0), 0.5))
    # Headline
    _text(buf, "CREATIVE PRODUCTION", W // 2, H // 2 - 200, size=90, color=(255, 255, 255))
    _text(buf, "SHOULDN'T FEEL MANUAL", W // 2, H // 2 - 60, size=70, color=(0, 220, 255))
    # Decorative accent
    _rect(buf, W // 2 - 250, H // 2 + 80, W // 2 + 250, H // 2 + 88, (0, 220, 255))
    return buf


def scene_activate():
    """Shot 02: Chaos → orchestration grid + pipeline."""
    buf = _bg_gradient((8, 8, 24), (12, 20, 50))
    _grid_nodes(buf, W // 2, H // 2 + 100, rows=4, cols=5, radius=16, gap=120, color=(0, 220, 255))
    _pipeline(buf, W // 2, H // 2 - 350, ["INPUT", "ROUTE", "BUILD", "RENDER", "QA"], "ORCHESTRATION LAYER")
    _text(buf, "AUTOMATE THE LOOP", W // 2, 200, size=80, color=(255, 255, 255))
    return buf


def scene_generative():
    """Shot 03: Generative creation — data stream / transformation."""
    buf = _bg_gradient((10, 5, 30), (5, 15, 45))
    # Concentric rings representing generation
    for r in range(5):
        _ring(buf, W // 2, H // 2, 150 + r * 100, (0, 180 + r * 15, 255), thickness=6)
    _text(buf, "GENERATE", W // 2, 200, size=100, color=(0, 255, 200))
    _text(buf, "FROM BRIEF TO ASSETS", W // 2, H - 250, size=50, color=(180, 180, 200))
    return buf


def scene_editing():
    """Shot 04: Automated editing — timeline + effects."""
    buf = _bg_gradient((10, 10, 10), (30, 30, 40))
    # Timeline bar
    _rect(buf, 80, H // 2 - 40, W - 80, H // 2 + 40, (40, 40, 50))
    # Track segments
    cuts = [(80, 350), (350, 600), (600, 900), (900, 1150), (1150, W - 80)]
    colors = [(0, 180, 255), (0, 255, 140), (255, 200, 0), (255, 100, 180), (0, 120, 255)]
    for (x1, x2), c in zip(cuts, colors):
        _rect(buf, x1 + 2, H // 2 - 35, x2 - 2, H // 2 + 35, c)
    # Playhead
    _rect(buf, 400, H // 2 - 60, 408, H // 2 + 60, (255, 255, 255))
    _text(buf, "EDIT  -  TRANSITIONS  -  FX", W // 2, 250, size=60, color=(255, 255, 255))
    return buf


def scene_qa():
    """Shot 05: QA / Verification."""
    buf = _bg_gradient((5, 20, 15), (10, 40, 30))
    _text(buf, "PASS", W // 2, H // 2 - 300, size=120, color=(0, 255, 100))
    _text(buf, "VERIFIED", W // 2, H // 2 - 120, size=80, color=(0, 200, 80))
    _progress_bar(buf, W // 2, H // 2 + 100, 700, 50, 1.0, fg=(0, 255, 100))
    _text(buf, "RENDER COMPLETE", W // 2, H // 2 + 250, size=50, color=(180, 255, 180))
    _text(buf, "OUTPUT READY", W // 2, H // 2 + 350, size=50, color=(180, 255, 180))
    # Asset verified checklist
    checks = ["VISUAL", "AUDIO", "TIMING", "RESOLUTION"]
    for i, ch in enumerate(checks):
        y = H // 2 + 500 + i * 80
        _rect(buf, 250, y - 25, 290, y + 15, (0, 255, 100))
        _text(buf, f"CHECK  {ch}", W // 2 + 100, y, size=40, color=(180, 255, 180))
    return buf


def scene_platforms():
    """Shot 06: Multi-platform output."""
    buf = _bg_gradient((15, 10, 30), (30, 20, 60))
    # Three aspect ratios
    # 9:16 (center)
    _rect(buf, W // 2 - 100, 300, W // 2 + 100, H - 300, (0, 180, 255))
    _text(buf, "9:16", W // 2, H // 2, size=60, color=(255, 255, 255))
    # 1:1 (left)
    _rect(buf, 60, 500, 460, 900, (0, 255, 180))
    _text(buf, "1:1", 260, 700, size=50, color=(255, 255, 255))
    # 16:9 (right)
    _rect(buf, W - 460, 500, W - 60, 900, (255, 200, 0))
    _text(buf, "16:9", W - 260, 700, size=50, color=(255, 255, 255))
    _text(buf, "ONE SOURCE", W // 2, 200, size=70, color=(255, 255, 255))
    _text(buf, "ALL PLATFORMS", W // 2, 290, size=70, color=(0, 220, 255))
    return buf


def scene_cta():
    """Shot 07: Final CTA."""
    buf = _bg_gradient((5, 5, 20), (15, 10, 50))
    _text(buf, "AI AUTOMATION", W // 2, H // 2 - 250, size=90, color=(255, 255, 255))
    _text(buf, "FOR CREATIVE PRODUCTION", W // 2, H // 2 - 100, size=55, color=(0, 220, 255))
    _rect(buf, W // 2 - 300, H // 2 + 20, W // 2 + 300, H // 2 + 28, (0, 220, 255))
    _text(buf, "FROM BRIEF", W // 2, H // 2 + 120, size=60, color=(255, 255, 255))
    _text(buf, "BUILD  -  RENDER  -  VERIFY", W // 2, H // 2 + 250, size=50, color=(180, 200, 220))
    _text(buf, "SCOS", W // 2, H - 200, size=100, color=(0, 255, 200))
    return buf


# Generate all stills
scenes = {
    "shot_01_hook": scene_hook,
    "shot_02_activate": scene_activate,
    "shot_03_generative": scene_generative,
    "shot_04_editing": scene_editing,
    "shot_05_qa": scene_qa,
    "shot_06_platforms": scene_platforms,
    "shot_07_cta": scene_cta,
}

manifest = {}
for name, fn in scenes.items():
    path = OUT_ROOT / f"{name}.png"
    sha = save_png(fn(), path)
    manifest[name] = {"path": str(path), "sha256": sha}
    print(f"  {name}: {sha[:16]}")

# Write manifest
with open(OUT_ROOT.parent / "brief" / "stills_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)
print(f"\nGenerated {len(scenes)} stills.")

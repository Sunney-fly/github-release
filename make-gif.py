#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a terminal session GIF from REAL command output.

Not a screen recording: the command is executed for real, its stdout is
captured, and the frames are drawn with Pillow. That keeps the demo honest
(every line is actual output) while avoiding a visible window or any capture
of the user's screen.

    python make-gif.py --title "cdp-clip" \
        --command "node cdp-clip.mjs url https://nodejs.org/api/stream.html" \
        --run "D:/Users/sun/DSH/out/cdp-clip" \
        --shot "node cdp-clip.mjs clip" \
        --out D:/Users/sun/DSH/out/cdp-clip/docs/demo.gif
"""

import argparse
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 600
PAD = 22
BAR = 34
FONT_SIZE = 15
LINE_H = 23
BG = (13, 17, 23)
BAR_BG = (22, 27, 34)
FG = (201, 209, 217)
DIM = (110, 118, 129)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
YELLOW = (210, 168, 74)
CYAN = (86, 182, 194)


def load_font(size, bold=False):
    for name in (("consolab.ttf" if bold else "consola.ttf"), "consola.ttf", "cour.ttf"):
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONT = load_font(FONT_SIZE)
FONT_BOLD = load_font(FONT_SIZE, bold=True)
FONT_SMALL = load_font(12)


def load_cjk_font(size):
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"):
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return FONT


CJK = load_cjk_font(14)


def has_cjk(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def pick_font(line, bold=False):
    """Consolas has no CJK glyphs; fall back per line so nothing renders as tofu."""
    if has_cjk(line):
        return CJK
    return FONT_BOLD if bold else FONT


def color_for(line):
    low = line.lower()
    if line.startswith("$") or line.startswith(">"):
        return GREEN
    if "必须修】0" in line or "ok" in low or "pass" in low or "✓" in line:
        return GREEN
    if "必须修】" in line or "fail" in low or "error" in low or "✗" in line:
        return RED
    if "建议修" in line or "retry" in low or "warn" in low:
        return YELLOW
    if line.startswith("【") or line.startswith("#"):
        return CYAN
    return FG


def wrap_lines(lines, max_chars=96):
    out = []
    for line in lines:
        if len(line) <= max_chars:
            out.append(line)
        else:
            out.extend(textwrap.wrap(line, max_chars, subsequent_indent="    ") or [line])
    return out


def draw_frame(visible_lines, title, typing_cursor):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # title bar
    draw.rectangle([0, 0, W, BAR], fill=BAR_BG)
    for i, cx in enumerate((18, 38, 58)):
        draw.ellipse([cx - 6, BAR // 2 - 6, cx + 6, BAR // 2 + 6],
                     fill=(255, 95, 86) if i == 0 else (255, 189, 46) if i == 1 else (39, 201, 63))
    draw.text((80, BAR // 2 - 7), title, font=FONT_SMALL, fill=DIM)

    y = BAR + PAD
    for line in visible_lines:
        if y > H - PAD - LINE_H:
            break
        draw.text((PAD, y), line, font=pick_font(line, line.startswith("$")),
                  fill=color_for(line))
        y += LINE_H

    if typing_cursor and y <= H - PAD - LINE_H:
        draw.rectangle([PAD, y + 3, PAD + 9, y + FONT_SIZE + 4], fill=FG)
    return img


def frames_from(blocks, title, hold_ms=2600, per_line_ms=130):
    """blocks: list of (lines, pause_after_ms). Returns [frame, ...] with durations."""
    wrapped = []
    for lines, pause in blocks:
        wrapped.append((wrap_lines(lines), pause))

    frames, durations = [], []
    visible = []
    for lines, pause in wrapped:
        for line in lines:
            visible.append(line)
            frames.append(draw_frame(visible, title, typing_cursor=True))
            durations.append(per_line_ms)
        frames.append(draw_frame(visible, title, typing_cursor=False))
        durations.append(pause)
        visible = visible[:]  # keep accumulating across blocks
    return frames, durations


def run_command(command, cwd, timeout=180):
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    print("  running: %s" % command)
    result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True,
                            text=True, timeout=timeout, errors="replace",
                            encoding="utf-8", env=env)
    out = (result.stdout or "") + (result.stderr or "")
    lines = [line.rstrip() for line in out.splitlines() if line.strip()]
    # Do not leak the absolute workspace path into a public demo.
    root = str(Path(cwd).resolve())
    cleaned = []
    for line in lines:
        line = line.replace(root + os.sep, "./").replace(root.replace("\\", "/") + "/", "./")
        line = line.replace(root, ".")
        cleaned.append(line)
    return cleaned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--command", required=True, help="command to show and run")
    ap.add_argument("--run", required=True, help="working directory")
    ap.add_argument("--shot", nargs="*", default=[],
                    help="extra commands appended as later blocks")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-lines", type=int, default=14)
    args = ap.parse_args()

    blocks = []
    lines = run_command(args.command, args.run)[: args.max_lines]
    blocks.append((["$ " + args.command] + lines, 1400))

    for extra in args.shot:
        extra_lines = run_command(extra, args.run)[: args.max_lines]
        blocks.append((["", "$ " + extra] + extra_lines, 1400))

    frames, durations = frames_from(blocks, args.title)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out, save_all=True, append_images=frames[1:],
        duration=durations, loop=0, optimize=True,
    )
    size_kb = out.stat().st_size / 1024
    print("  wrote %s  (%d frames, %.0f KB)" % (out, len(frames), size_kb))
    return 0 if size_kb < 3000 else 1


if __name__ == "__main__":
    sys.exit(main())

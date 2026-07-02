#!/usr/bin/env python3
"""Generate cover.png for vmd-hydrate-mcp.

Adapts the house cover style (dark canvas, blurred color blobs, monospace glowing
title, film grain, rounded corners) with a teal/indigo molecular palette and a
faint hydrate-cage lattice motif behind the title. Pure PIL + numpy, no assets.

    python generate_cover.py
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 2560, 1280
CORNER_RADIUS = 80
TITLE_TEXT = "vmd-hydrate-mcp"
SUBTITLE_TEXT = "Drive VMD from any LLM -- MD trajectories & hydrate cages."
TITLE_SIZE = 190
SUBTITLE_SIZE = 66
GAP = 48

BASE = (11, 14, 18, 255)  # #0b0e12 near-black, cool
BLOBS = [
    # (rgba, cx, cy, rx, ry, blur)
    ((0, 120, 145, 235), 700, 620, 760, 560, 110),   # deep teal, center-left
    ((0, 200, 235, 210), 1980, 210, 660, 470, 95),   # bright cyan, top-right
    ((35, 30, 95, 220), 1280, 1170, 980, 380, 90),   # deep indigo, bottom
    ((25, 150, 165, 175), 1400, 660, 560, 400, 78),  # mid teal, center
]


def make_blob(rgba, cx, cy, rx, ry, blur):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=rgba)
    return layer.filter(ImageFilter.GaussianBlur(blur))


def load_font(size, bold=True):
    for path, idx in (("/System/Library/Fonts/Menlo.ttc", 1 if bold else 0),):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except OSError:
            pass
    for path in ("/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def cage_lattice(seed=42):
    """A faint constellation of nodes + near-neighbor bonds (a hydrate cage motif)."""
    rng = np.random.default_rng(seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    n = 46
    pts = rng.uniform([120, 120], [W - 120, H - 120], size=(n, 2))
    for i in range(n):
        for j in range(i + 1, n):
            dist = np.linalg.norm(pts[i] - pts[j])
            if dist < 320:
                d.line([tuple(pts[i]), tuple(pts[j])], fill=(150, 210, 230, 70), width=2)
    for p in pts:
        d.ellipse([p[0] - 7, p[1] - 7, p[0] + 7, p[1] + 7], fill=(200, 240, 252, 110))
    return layer.filter(ImageFilter.GaussianBlur(2))


def main():
    img = Image.new("RGBA", (W, H), BASE)
    for rgba, cx, cy, rx, ry, blur in BLOBS:
        img = Image.alpha_composite(img, make_blob(rgba, cx, cy, rx, ry, blur))
    img = img.filter(ImageFilter.GaussianBlur(8))
    img = Image.alpha_composite(img, cage_lattice())

    # film grain — full-range gray noise overlaid at low opacity (so it textures
    # the blobs rather than overwriting them)
    rng = np.random.default_rng(42)
    noise = (rng.random((H, W)) * 255).astype(np.uint8)
    alpha = np.full((H, W), 42, dtype=np.uint8)  # ~16% opacity
    grain = np.stack([noise, noise, noise, alpha], axis=-1)
    img = Image.alpha_composite(img, Image.fromarray(grain, "RGBA"))

    title_font = load_font(TITLE_SIZE, bold=True)
    sub_font = load_font(SUBTITLE_SIZE, bold=False)
    draw = ImageDraw.Draw(img)

    tb = draw.textbbox((0, 0), TITLE_TEXT, font=title_font)
    sb = draw.textbbox((0, 0), SUBTITLE_TEXT, font=sub_font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    sw, sh = sb[2] - sb[0], sb[3] - sb[1]
    block_h = th + GAP + sh
    block_top = (H - block_h) // 2 - 30
    tx = (W - tw) // 2 - tb[0]
    ty = block_top - tb[1]

    # title glow stack (cyan) then sharp white
    for blur, col in ((18, (120, 220, 255, 60)), (9, (150, 230, 255, 90)), (4, (190, 240, 255, 120))):
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(g).text((tx, ty), TITLE_TEXT, font=title_font, fill=col)
        img = Image.alpha_composite(img, g.filter(ImageFilter.GaussianBlur(blur)))
    draw = ImageDraw.Draw(img)
    draw.text((tx, ty), TITLE_TEXT, font=title_font, fill=(255, 255, 255, 245))

    sx = (W - sw) // 2 - sb[0]
    sy = block_top + th + GAP - sb[1]
    draw.text((sx, sy), SUBTITLE_TEXT, font=sub_font, fill=(160, 185, 192, 210))

    # rounded corners
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W, H], radius=CORNER_RADIUS, fill=255)
    img.putalpha(mask)
    img = img.filter(ImageFilter.GaussianBlur(1))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cover.png")
    img.save(out, dpi=(400, 400))
    print(f"wrote {out} ({img.size[0]}x{img.size[1]} {img.mode})")


if __name__ == "__main__":
    main()

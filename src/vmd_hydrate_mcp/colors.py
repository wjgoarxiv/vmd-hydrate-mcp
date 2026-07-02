"""Color handling for cage rendering.

Maps human/LLM color requests ("magenta", "#ff00aa") to RGB floats for VMD's
``color change rgb``, and holds the per-cage-type palette. The default palette
is a curated scientific palette.
"""

from __future__ import annotations

from typing import Dict, Tuple

RGB = Tuple[float, float, float]

# Named colors an LLM is likely to emit, as 0..1 RGB.
NAMED_COLORS: Dict[str, RGB] = {
    "red": (0.85, 0.16, 0.16),
    "green": (0.18, 0.72, 0.28),
    "blue": (0.20, 0.42, 0.92),
    "cyan": (0.12, 0.80, 0.92),
    "magenta": (0.92, 0.12, 0.80),
    "pink": (1.0, 0.55, 0.76),
    "yellow": (0.96, 0.85, 0.12),
    "orange": (0.96, 0.55, 0.12),
    "purple": (0.60, 0.30, 0.86),
    "violet": (0.56, 0.36, 0.92),
    "teal": (0.10, 0.70, 0.66),
    "lime": (0.62, 0.90, 0.22),
    "white": (0.95, 0.95, 0.95),
    "gray": (0.60, 0.60, 0.60),
    "grey": (0.60, 0.60, 0.60),
    "black": (0.05, 0.05, 0.05),
    "silver": (0.78, 0.80, 0.83),
    "gold": (0.95, 0.78, 0.25),
}

# Per-cage-type palette — a curated per-cage color map for polished renders.
CAGE_PALETTE: Dict[str, RGB] = {
    "512": (0.024, 0.714, 0.831),    # #06b6d4 cyan  — small (D) cage
    "51262": (0.545, 0.361, 0.965),  # #8b5cf6 violet — sI large (T) cage
    "51263": (0.961, 0.620, 0.043),  # #f59e0b amber
    "51264": (0.937, 0.267, 0.267),  # #ef4444 red   — sII large (H) cage
    "51265": (0.133, 0.773, 0.369),  # #22c55e green
    "51266": (0.925, 0.282, 0.600),  # #ec4899 pink
    "51268": (0.231, 0.510, 0.965),  # #3b82f6 blue  — sH large (E) cage
    "435663": (0.518, 0.800, 0.086), # #84cc16 lime  — sH medium cage
    "435664": (0.396, 0.639, 0.051), # #65a30d dark lime
    "other": (0.612, 0.639, 0.686),  # #9ca3af gray  — fallback
}


def parse_color(value) -> RGB:
    """Accept a name ('magenta'), a '#rrggbb' hex, or an (r,g,b) 0..1 tuple."""
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return tuple(float(c) for c in value)  # type: ignore[return-value]
    s = str(value).strip().lower()
    if s.startswith("#") and len(s) == 7:
        return (int(s[1:3], 16) / 255, int(s[3:5], 16) / 255, int(s[5:7], 16) / 255)
    if s in NAMED_COLORS:
        return NAMED_COLORS[s]
    raise ValueError(f"unknown color {value!r}; use a name (e.g. magenta) or #rrggbb hex")


def cage_color(cage_type: str) -> RGB:
    return CAGE_PALETTE.get(cage_type, CAGE_PALETTE["other"])

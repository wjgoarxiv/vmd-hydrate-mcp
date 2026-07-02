#!/usr/bin/env python3
"""Render the demo movie frames straight from the vmd-hydrate-mcp pipeline.

Every frame is a REAL photorealistic headless VMD (Tachyon, ambient occlusion +
shadows, orthographic) render, using the SAME cage-scene setup the MCP server's
render_cages tool uses (the built-in palette, unified per-cage colors).

Two scenes:
  A. the full sII CO2-hydrate crystal (1088 waters) rotating, cages colored by
     type (cyan 5^12, red 5^12 6^4) — identical to render_cages output;
  B. a single isolated 5^12 dodecahedron cage (20 waters, unwrapped across PBC).

Usage:  python video/build_frames.py [--quick]
Frames land in video/frames/ (gitignored; regenerable).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import numpy as np  # noqa: E402

from vmd_hydrate_mcp.config import Settings  # noqa: E402
from vmd_hydrate_mcp.tools import Tools  # noqa: E402
from vmd_hydrate_mcp.analysis.gro import read_gro_waters  # noqa: E402
from vmd_hydrate_mcp.analysis.hydrate.cage import identify_cages  # noqa: E402
from vmd_hydrate_mcp.vmd.render import render_png  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "hydrate_sII_222.gro")
FRAMES = os.path.join(HERE, "frames")
QUICK = "--quick" in sys.argv

N_SYSTEM = 12 if QUICK else 60
N_CAGE = 8 if QUICK else 48
RES = (760, 760)      # square, high quality (composited into 16:9 by Remotion)
AA = 4                # movie frames: fast AA (stills use 12)
BG = "#0f172a"        # dark theme


def save(png, name):
    with open(os.path.join(FRAMES, name), "wb") as fh:
        fh.write(png)


def write_cage_gro(path, positions_nm):
    p = np.asarray(positions_nm)
    p = p - p.mean(axis=0)
    box = float(np.abs(p).max() * 2 + 0.6)
    p = p + box / 2
    lines = ["512 cage (unwrapped)", f"{len(p):5d}"]
    for i, (x, y, z) in enumerate(p, 1):
        lines.append(f"{1:>5}{'H2O':<5}{'OW':>5}{i:>5}{x:8.3f}{y:8.3f}{z:8.3f}")
    lines.append(f"{box:10.5f}{box:10.5f}{box:10.5f}")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    os.makedirs(FRAMES, exist_ok=True)
    t = Tools(Settings(allow_dirs=[os.path.dirname(FIX), FRAMES, HERE]))
    sess = t.session
    inst = sess.install

    # ---- Scene A: full sII crystal, cage-colored, photorealistic ----
    mid = t.setup_cage_scene(FIX, background=BG, projection="orthographic")
    sess.call("recipe_resetview", mid)
    sess.call("recipe_scale", 1.15)
    sess.call("recipe_rotate", "x", 20)
    for i in range(N_SYSTEM):
        save(render_png(sess, inst, mid, *RES, aasamples=AA), f"system_{i:03d}.png")
        sess.call("recipe_rotate", "y", 360.0 / N_SYSTEM)
        print(f"  system {i + 1}/{N_SYSTEM}")

    # ---- Scene B: one isolated 5^12 dodecahedron (cyan, matching palette) ----
    w = read_gro_waters(FIX)
    res = identify_cages(w.O, w.H1, w.H2, w.cell, method="TRACE")
    dodeca = next((c for c in res.cages if c.cage_type == "512"), None)
    if dodeca is not None:
        center = dodeca.center
        pos = np.array([center + w.cell.mic(w.O[v] - center) for v in dodeca.vertices])
        cage_gro = os.path.join(FRAMES, "_cage512.gro")
        write_cage_gro(cage_gro, pos)
        sess.call("recipe_delete", mid)
        cmid = sess.load(cage_gro).molid
        sess.call("recipe_scene", "Orthographic", "0.059", "0.090", "0.165", "0.85", "0.35")
        sess.call("recipe_setcolor", 17, "0.024", "0.714", "0.831")  # 5^12 cyan (#06b6d4)
        sess.call("recipe_clearreps", cmid)
        sess.call("recipe_addrep_colorid", cmid, "DynamicBonds 3.6 0.10 20", 17, "Glossy", "all")
        sess.call("recipe_addrep_colorid", cmid, "VDW 0.34 22", 17, "Glossy", "all")
        sess.call("recipe_resetview", cmid)
        sess.call("recipe_scale", 0.82)
        sess.call("recipe_rotate", "x", 15)
        for i in range(N_CAGE):
            save(render_png(sess, inst, cmid, *RES, aasamples=AA), f"cage_{i:03d}.png")
            sess.call("recipe_rotate", "y", 360.0 / N_CAGE)
            print(f"  cage {i + 1}/{N_CAGE}")

    t.shutdown()
    print(f"done -> {FRAMES}")


if __name__ == "__main__":
    main()

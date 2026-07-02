"""Headless rendering: VMD Tachyon scene -> PNG bytes.

Pipeline:
  recipe_render_scene -> `render Tachyon scene.dat` (no display needed)
  -> standalone `tachyon scene.dat -o out.tga -format TARGA -res W H` (R1: only
     TARGA is verified; external binary gives resolution control)
  -> TGA -> PNG via sips | ImageMagick | Pillow (R2: don't assume macOS `sips`).

We never call `display resize/update` (crashes headless), and outputs live in a
server-owned temp dir, not a caller path (S5, R3).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Optional

from .discovery import VmdInstall
from .session import VmdError, VmdSession

__all__ = ["render_png", "RenderError"]


class RenderError(VmdError):
    pass


def _run(cmd) -> subprocess.CompletedProcess:
    # capture output; never let child stdout reach the server's fd1 (P3)
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)


def _tga_to_png(tga: str, png: str) -> None:
    if shutil.which("sips"):
        r = _run(["sips", "-s", "format", "png", tga, "--out", png])
        if r.returncode == 0 and os.path.exists(png):
            return
    for magick in ("magick", "convert"):
        if shutil.which(magick):
            r = _run([magick, tga, png])
            if r.returncode == 0 and os.path.exists(png):
                return
    try:
        from PIL import Image  # type: ignore

        Image.open(tga).save(png)
        return
    except Exception as e:  # noqa: BLE001
        raise RenderError(
            "no TGA->PNG converter available (need `sips`, ImageMagick, or Pillow)"
        ) from e


def render_png(
    session: VmdSession,
    install: VmdInstall,
    molid: int,
    width: int = 800,
    height: int = 600,
    max_px: int = 1280,
    aasamples: int = 12,
) -> bytes:
    """Render molecule ``molid`` from the live session and return PNG bytes.

    ``aasamples`` trades quality for speed (12 = crisp single stills; lower is
    fine for movie frames)."""
    width = max(64, min(int(width), max_px))
    height = max(64, min(int(height), max_px))

    tachyon = install.env.get("TACHYON_BIN")
    if not tachyon or not os.path.exists(tachyon):
        raise RenderError("tachyon binary not found in the VMD install")

    workdir = tempfile.mkdtemp(prefix="vmdhydrate_render_")
    os.chmod(workdir, 0o700)
    scene = os.path.join(workdir, "scene.dat")
    tga = os.path.join(workdir, "out.tga")
    png = os.path.join(workdir, "out.png")
    try:
        session.call("recipe_render_scene", molid, scene)
        if not os.path.exists(scene):
            raise RenderError("VMD did not produce a Tachyon scene file")
        # -aasamples 12 for smooth edges; ambient occlusion + shadows are baked
        # into the scene by recipe_scene, so the external render is photorealistic.
        r = _run([tachyon, scene, "-o", tga, "-format", "TARGA",
                  "-res", str(width), str(height), "-aasamples", str(aasamples)])
        if r.returncode != 0 or not os.path.exists(tga):
            out = r.stdout.decode(errors="replace")[-400:] if r.stdout else ""
            raise RenderError(f"tachyon rasterization failed: {out}")
        _tga_to_png(tga, png)
        with open(png, "rb") as fh:
            return fh.read()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

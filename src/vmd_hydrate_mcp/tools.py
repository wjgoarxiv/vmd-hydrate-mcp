"""Tool logic, independent of the MCP transport so it is unit-testable.

``server.py`` is a thin FastMCP wrapper over these functions. Numeric/hydrate
work runs through the pure-NumPy + MDAnalysis backends (no display); viz/render
runs through the persistent VMD session.
"""

from __future__ import annotations

import os
from typing import List, Optional

from .analysis import mda
from .analysis.gro import read_gro_waters
from .analysis.hydrate.cage import identify_cages as _identify_cages
from .analysis.hydrate.hbond import hbond_network as _hbond_network
from .analysis.hydrate.order_params import order_parameters
from .config import Settings
from .security import PathGuard, SecurityError, looks_like_tcl_injection
from .vmd.session import VmdSession, VmdUnavailable, VmdError

# formats that carry coordinates only (no topology/atom names)
_COORD_ONLY = {".xtc", ".trr", ".dcd", ".lammpstrj"}


class Tools:
    """Holds the shared session + path guard for a server instance."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.from_env()
        self.guard = PathGuard(self.settings.allow_dirs)
        self._session: Optional[VmdSession] = None

    # -- session --------------------------------------------------------------
    @property
    def session(self) -> VmdSession:
        if self._session is None:
            self._session = VmdSession(self.settings)
        return self._session

    def shutdown(self):
        if self._session is not None:
            self._session.shutdown()

    # -- helpers --------------------------------------------------------------
    def _safe_path(self, path: str) -> str:
        return str(self.guard.resolve(path))

    def _safe_selection(self, selection: str) -> str:
        if looks_like_tcl_injection(selection):
            raise SecurityError(
                f"selection contains forbidden characters: {selection!r}"
            )
        return selection

    # -- system ---------------------------------------------------------------
    def vmd_status(self) -> dict:
        try:
            pong = self.session.ping()
            return {
                "vmd_available": True,
                "vmd": pong,
                "display": self.settings.display,
                "loaded_molecules": [
                    {"molid": m, "path": meta.path, "numatoms": meta.numatoms, "numframes": meta.numframes}
                    for m, meta in self.session.registry.items()
                ],
            }
        except VmdUnavailable as e:
            return {"vmd_available": False, "reason": str(e)}
        except VmdError as e:
            return {"vmd_available": False, "reason": str(e)}

    # -- load / viz -----------------------------------------------------------
    def load_structure(self, path: str, filetype: str = "auto", topology: Optional[str] = None) -> dict:
        p = self._safe_path(path)
        ext = os.path.splitext(p)[1].lower()
        if ext in _COORD_ONLY and not topology:
            raise ValueError(
                f"{ext} is coordinate-only (no atom names); supply a topology via "
                f"load_trajectory(molid, topology=...) or load a .gro/.pdb/.data first"
            )
        meta = self.session.load(p, filetype)
        return {"molid": meta.molid, "path": meta.path,
                "numatoms": meta.numatoms, "numframes": meta.numframes}

    def list_molecules(self) -> dict:
        return {
            "molecules": [
                {"molid": m, "path": meta.path, "numatoms": meta.numatoms, "numframes": meta.numframes}
                for m, meta in self.session.registry.items()
            ]
        }

    def set_representation(
        self, molid: int, style: str = "VDW", color: str = "Name",
        material: str = "Opaque", selection: str = "all",
    ) -> dict:
        sel = self._safe_selection(selection)
        res = self.session.call("recipe_representation", int(molid), style, color, material, sel)
        return {"molid": int(molid), "result": res}

    def add_representation(
        self, molid: int, style: str = "VDW", color: str = "Name",
        material: str = "Opaque", selection: str = "all",
    ) -> dict:
        """Add a representation WITHOUT clearing existing ones (layer multiple
        reps, e.g. water as Points + protein as NewCartoon)."""
        sel = self._safe_selection(selection)
        res = self.session.call("recipe_addrep", int(molid), style, color, material, sel)
        return {"molid": int(molid), "result": res}

    def clear_representations(self, molid: int) -> dict:
        res = self.session.call("recipe_clearreps", int(molid))
        return {"molid": int(molid), "result": res}

    # -- live view control (visible immediately in GUI mode) ------------------
    def rotate_view(self, axis: str = "y", degrees: float = 30.0) -> dict:
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be 'x', 'y', or 'z'")
        return {"result": self.session.call("recipe_rotate", axis, float(degrees))}

    def zoom_view(self, factor: float = 1.2) -> dict:
        return {"result": self.session.call("recipe_scale", float(factor))}

    def reset_view(self, molid: int = 0) -> dict:
        return {"result": self.session.call("recipe_resetview", int(molid))}

    def render(self, molid: int, width: int = 800, height: int = 600) -> bytes:
        from .vmd.render import render_png

        return render_png(self.session, self.session.install, int(molid),
                          width, height, self.settings.max_render_px)

    # -- selection / measure (MDAnalysis) ------------------------------------
    def resolve_selection(self, path: str, selection: str, topology: Optional[str] = None) -> dict:
        p = self._safe_path(path)
        top = self._safe_path(topology) if topology else None
        n = mda.resolve_selection(p, selection, top)
        return {"selection": selection, "n_atoms": n,
                "note": "0 atoms often means a bare .gro lacks element data; try an explicit selection"}

    def measure_geometry(self, path: str, indices: List[int], topology: Optional[str] = None, frame: int = 0) -> dict:
        p = self._safe_path(path)
        top = self._safe_path(topology) if topology else None
        kind, value = mda.measure_geometry(p, indices, top, frame)
        return {"kind": kind, "value": value, "indices": indices, "frame": frame}

    def radius_of_gyration(self, path: str, selection: str = "all", topology: Optional[str] = None, frame: int = 0) -> dict:
        p = self._safe_path(path)
        top = self._safe_path(topology) if topology else None
        rg = mda.radius_of_gyration(p, selection, top, frame)
        return {"radius_of_gyration_angstrom": rg, "selection": selection, "frame": frame}

    # -- hydrate (the moat) ---------------------------------------------------
    def _load_waters(self, path: str, topology: Optional[str], frame: int):
        if os.path.splitext(path)[1].lower() == ".gro" and not topology:
            w = read_gro_waters(path, frame=frame)
            return w.O, w.H1, w.H2, w.cell
        return mda.load_waters_mda(path, topology, frame)

    def hydrate_order_params(self, path: str, cutoff: float = 0.35, frame: int = 0, topology: Optional[str] = None) -> dict:
        p = self._safe_path(path)
        top = self._safe_path(topology) if topology else None
        O, H1, H2, cell = self._load_waters(p, top, frame)
        res = order_parameters(O, H1, H2, cell, cutoff=cutoff)
        out = res.summary()
        out.update({
            "frame": frame,
            "cutoff_nm": cutoff,
            "interpretation": _interpret_f4(res.f4_overall),
        })
        return out

    def hbond_network(self, path: str, rcut: float = 0.36, theta: float = 35.0, frame: int = 0, topology: Optional[str] = None) -> dict:
        p = self._safe_path(path)
        top = self._safe_path(topology) if topology else None
        O, H1, H2, cell = self._load_waters(p, top, frame)
        res = _hbond_network(O, H1, H2, cell, rcut=rcut, theta=theta)
        out = res.summary()
        out.update({"frame": frame, "rcut_nm": rcut, "theta_deg": theta})
        return out

    # -- cages (v0.2) ---------------------------------------------------------
    def identify_cages(self, path: str, method: str = "TRACE", rcut: float = 0.36,
                       theta: float = 35.0, frame: int = 0) -> dict:
        p = self._safe_path(path)
        w = read_gro_waters(p, frame=frame)
        res = _identify_cages(w.O, w.H1, w.H2, w.cell, rcut=rcut, theta=theta, method=method)
        out = res.summary()
        out.update({"method": method, "frame": frame})
        return out

    # large cages win over small on shared vertices (for water->cage coloring)
    _CAGE_PRIORITY = {"512": 1, "51262": 2, "51263": 2, "435663": 2, "435664": 2,
                      "51264": 3, "51265": 3, "51266": 3, "51268": 3}
    _CAGE_COLORID_BASE = 17  # redefine stock ids 17+ (keeps x/y/z axis colors intact)

    def _cage_water_colors(self, path: str, frame: int, method: str, cage_types=None):
        w = read_gro_waters(path, frame=frame)
        res = _identify_cages(w.O, w.H1, w.H2, w.cell, method=method)
        show = {str(t) for t in cage_types} if cage_types else None
        best: dict = {}  # water idx -> (priority, type)
        for cage in res.cages:
            if show is not None and cage.cage_type not in show:
                continue
            pr = self._CAGE_PRIORITY.get(cage.cage_type, 0)
            for v in cage.vertices:
                if v not in best or pr > best[v][0]:
                    best[v] = (pr, cage.cage_type)
        by_type: dict = {}  # type -> sorted VMD oxygen atom indices
        for v, (_, ctype) in best.items():
            by_type.setdefault(ctype, []).append(w.o_index[v])
        for t in by_type:
            by_type[t].sort()
        return res, by_type

    def render_cages(
        self,
        path: str,
        cage_types: Optional[List[str]] = None,
        colors: Optional[dict] = None,
        highlight_color: Optional[str] = None,
        emphasis: bool = False,
        material: str = "Glossy",
        background: str = "#0f172a",
        projection: str = "orthographic",
        width: int = 1000,
        height: int = 1000,
        frame: int = 0,
        method: str = "TRACE",
    ) -> bytes:
        """Photorealistic cage render. Each cage type gets ONE unified color for
        both its O-O framework and its vertex spheres (the built-in palette by
        default). NL styling: cage_types filters which cages show (e.g. ["51264"]);
        highlight_color paints all shown cages one color (e.g. "magenta");
        colors={type: color} overrides per type; emphasis thickens edges + spheres."""
        from .vmd.render import render_png

        mid = self.setup_cage_scene(
            path, cage_types=cage_types, colors=colors, highlight_color=highlight_color,
            emphasis=emphasis, material=material, background=background,
            projection=projection, frame=frame, method=method,
        )
        return render_png(self.session, self.session.install, mid, width, height, self.settings.max_render_px)

    def setup_cage_scene(
        self, path: str, cage_types: Optional[List[str]] = None, colors: Optional[dict] = None,
        highlight_color: Optional[str] = None, emphasis: bool = False, material: str = "Glossy",
        background: str = "#0f172a", projection: str = "orthographic", frame: int = 0,
        method: str = "TRACE",
    ) -> int:
        """Load the structure, identify cages, and set up the photorealistic
        cage-colored scene (ortho + AO + shadows + unified per-cage colors).
        Returns the molid; the caller renders. Shared by render_cages and the
        demo frame builder so both look identical."""
        from .colors import parse_color, cage_color

        p = self._safe_path(path)
        res, by_type = self._cage_water_colors(p, frame, method, cage_types)
        if not by_type:
            raise ValueError(
                f"no cages of the requested types found; available cage counts: {res.counts}"
            )
        meta = self.session.load(p)
        mid = meta.molid

        proj = "Orthographic" if str(projection).lower().startswith("ortho") else "Perspective"
        br, bg, bb = parse_color(background)
        self.session.call("recipe_scene", proj, f"{br:.3f}", f"{bg:.3f}", f"{bb:.3f}", "0.85", "0.35")
        self.session.call("recipe_clearreps", mid)

        bond_r = 0.16 if emphasis else 0.09   # selected/emphasized edges ~2x thicker
        sph_r = 0.5 if emphasis else 0.33
        colors = colors or {}
        for i, (ctype, idxs) in enumerate(sorted(by_type.items())):
            if highlight_color is not None:
                rgb = parse_color(highlight_color)
            elif ctype in colors:
                rgb = parse_color(colors[ctype])
            else:
                rgb = cage_color(ctype)
            cid = self._CAGE_COLORID_BASE + i
            self.session.call("recipe_setcolor", cid, f"{rgb[0]:.3f}", f"{rgb[1]:.3f}", f"{rgb[2]:.3f}")
            sel = "index " + " ".join(str(x) for x in idxs)
            # unified color: the O-O framework AND the vertices share `cid`
            self.session.call("recipe_addrep_colorid", mid, f"DynamicBonds 3.6 {bond_r} 18", cid, material, sel)
            self.session.call("recipe_addrep_colorid", mid, f"VDW {sph_r} 20", cid, material, sel)
        return mid


def _interpret_f4(f4: float) -> str:
    if f4 != f4:  # NaN
        return "no O-O pairs found (check selection/units)"
    if f4 >= 0.85:
        return "highly ordered (crystalline hydrate / ice-like)"
    if f4 >= 0.5:
        return "hydrate-like order"
    if f4 >= -0.2:
        return "liquid-like"
    return "ice-Ih-like (strongly negative)"

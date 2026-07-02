"""FastMCP entry point for VMD-Hydrate-MCP.

Thin wrapper over ``tools.Tools``. All logging goes to stderr so the stdio
JSON-RPC channel on stdout stays clean (PLAN §13 P3). Run with:

    vmd-hydrate-mcp            # stdio (Claude Desktop / Claude Code)
"""

from __future__ import annotations

import logging
import sys
from typing import List, Optional

from mcp.server.fastmcp import FastMCP, Image

from .tools import Tools

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = FastMCP("VMD-Hydrate-MCP")
_tools = Tools()


@mcp.tool()
def vmd_status() -> dict:
    """Report whether VMD is available, its version, and the molecules currently
    loaded in the persistent session."""
    return _tools.vmd_status()


@mcp.tool()
def load_structure(path: str, filetype: str = "auto", topology: Optional[str] = None) -> dict:
    """Load a structure/trajectory into the persistent VMD session for
    visualization. Supports PDB, GROMACS (.gro/.xtc/.trr), LAMMPS (.data/dump),
    DCD. Coordinate-only formats (.xtc/.trr/.dcd) require a `topology`. Returns
    the molid used to reference this molecule in later calls."""
    return _tools.load_structure(path, filetype, topology)


@mcp.tool()
def list_molecules() -> dict:
    """List molecules currently loaded in the VMD session (molid, path, atoms, frames)."""
    return _tools.list_molecules()


@mcp.tool()
def set_representation(
    molid: int, style: str = "VDW", color: str = "Name",
    material: str = "Opaque", selection: str = "all",
) -> dict:
    """Set the visual representation of a loaded molecule (e.g. style=NewCartoon,
    Licorice, VDW, Lines; color=Name, ResType, Beta; selection is a VMD
    atom-selection string like "water" or "name CA")."""
    return _tools.set_representation(molid, style, color, material, selection)


@mcp.tool()
def render(molid: int, width: int = 800, height: int = 600) -> Image:
    """Render the current view of a loaded molecule headlessly (CPU Tachyon) and
    return a PNG image. Resolution is capped for safety."""
    png = _tools.render(molid, width, height)
    return Image(data=png, format="png")


@mcp.tool()
def resolve_selection(path: str, selection: str, topology: Optional[str] = None) -> dict:
    """Report how many atoms an MDAnalysis selection matches — use this to catch
    the common 0-atom trap on bare .gro files before running measurements."""
    return _tools.resolve_selection(path, selection, topology)


@mcp.tool()
def measure_geometry(path: str, indices: List[int], topology: Optional[str] = None, frame: int = 0) -> dict:
    """Measure a distance (2 atom indices), angle (3), or dihedral (4) at a
    frame. Distances are in Angstrom, angles in degrees."""
    return _tools.measure_geometry(path, indices, topology, frame)


@mcp.tool()
def radius_of_gyration(path: str, selection: str = "all", topology: Optional[str] = None, frame: int = 0) -> dict:
    """Radius of gyration (Angstrom) of an atom selection at a frame."""
    return _tools.radius_of_gyration(path, selection, topology, frame)


@mcp.tool()
def hydrate_order_params(path: str, cutoff: float = 0.35, frame: int = 0, topology: Optional[str] = None) -> dict:
    """Compute clathrate-hydrate water order parameters F3 (tetrahedrality) and
    F4 (<cos 3phi>) for a frame. F4 ~ 0.7-0.95 indicates hydrate/crystalline
    order, ~0 liquid, negative ice-Ih. Units are nm; for .gro the native nm
    parser is used. This is the differentiating capability no other MCP offers."""
    return _tools.hydrate_order_params(path, cutoff, frame, topology)


@mcp.tool()
def hbond_network(path: str, rcut: float = 0.36, theta: float = 35.0, frame: int = 0, topology: Optional[str] = None) -> dict:
    """Build the water-water hydrogen-bond network for a frame and report bond
    count and average coordination (the substrate for cage identification).
    rcut is the O-O cutoff (nm), theta the H-O...O angle cutoff (degrees)."""
    return _tools.hbond_network(path, rcut, theta, frame, topology)


@mcp.tool()
def identify_cages(path: str, method: str = "TRACE", rcut: float = 0.36, theta: float = 35.0, frame: int = 0) -> dict:
    """Identify clathrate-hydrate cages (5^12, 5^12 6^2, 5^12 6^4, ...) from the
    water H-bond network and classify the crystal structure (sI/sII/sH). Returns
    per-type cage counts, the structure label, and a confidence. method="TRACE"
    (all rings) or "HTR" (primitive rings). GROMACS .gro input."""
    return _tools.identify_cages(path, method, rcut, theta, frame)


@mcp.tool()
def render_cages(
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
) -> Image:
    """Render clathrate cages photorealistically (ambient occlusion + shadows,
    orthographic by default). Each cage type is drawn in ONE unified color for
    both its water-oxygen vertices and its O-O framework, using a curated
    palette (512=cyan, 51262=violet, 51264=red, 435663=lime, 51268=blue).

    Natural-language styling maps directly to the arguments:
      - "show only the sII large cages"  -> cage_types=["51264"]
      - "... in magenta"                 -> highlight_color="magenta" (name or #rrggbb)
      - "emphasize / thicker width"      -> emphasis=True (thicker edges + bigger spheres)
      - per-type colors                  -> colors={"512": "cyan", "51264": "magenta"}
    cage_types are internal codes: 512, 51262, 51263, 51264, 51268, 435663, ...
    (sI = 512+51262, sII = 512+51264, sH = 512+435663+51268). Returns a PNG."""
    png = _tools.render_cages(
        path, cage_types=cage_types, colors=colors, highlight_color=highlight_color,
        emphasis=emphasis, material=material, background=background,
        projection=projection, width=width, height=height, frame=frame, method=method,
    )
    return Image(data=png, format="png")


@mcp.tool()
def add_representation(molid: int, style: str = "VDW", color: str = "Name", material: str = "Opaque", selection: str = "all") -> dict:
    """Add a representation WITHOUT clearing existing ones — layer several reps
    (e.g. water as Points + solute as VDW). `color` is a coloring METHOD
    (Name, ResName, ResType, Chain, Beta, ...); `style` is VDW/Lines/Points/
    NewCartoon/Licorice/etc."""
    return _tools.add_representation(molid, style, color, material, selection)


@mcp.tool()
def clear_representations(molid: int) -> dict:
    """Remove all representations from a molecule (start a fresh view)."""
    return _tools.clear_representations(molid)


@mcp.tool()
def rotate_view(axis: str = "y", degrees: float = 30.0) -> dict:
    """Rotate the camera by `degrees` about an axis ('x'/'y'/'z'). In GUI/attended
    mode (VMD_HYDRATE_MCP_DISPLAY=gui) the visible window updates live."""
    return _tools.rotate_view(axis, degrees)


@mcp.tool()
def zoom_view(factor: float = 1.2) -> dict:
    """Zoom the view by a multiplicative factor (>1 zoom in, <1 zoom out)."""
    return _tools.zoom_view(factor)


@mcp.tool()
def reset_view(molid: int = 0) -> dict:
    """Reset/fit the camera to the loaded molecule."""
    return _tools.reset_view(molid)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

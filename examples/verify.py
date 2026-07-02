#!/usr/bin/env python3
"""Prove that vmd-hydrate-mcp actually drives VMD and identifies hydrate cages.

Runs the same code paths the MCP server exposes, on a bundled sII CO2-hydrate
example, and:
  1. discovers + pings the real VMD binary (proves VMD control),
  2. identifies the clathrate cages (128 x 5^12 + ~60 x 5^12 6^4, structure sII),
  3. renders a cage-colored PNG headlessly and saves it,
so you can see the expected outcome for yourself.

    python examples/verify.py

Without VMD installed, steps 1 and 3 are skipped and the analysis (steps 2)
still runs — it needs no display.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from vmd_hydrate_mcp.config import Settings  # noqa: E402
from vmd_hydrate_mcp.tools import Tools  # noqa: E402
from vmd_hydrate_mcp.vmd.discovery import discover_vmd  # noqa: E402

GRO = os.path.join(ROOT, "tests", "fixtures", "hydrate_sII_222.gro")
OUT = os.path.join(HERE, "output")


def main():
    os.makedirs(OUT, exist_ok=True)
    tools = Tools(Settings(allow_dirs=[os.path.dirname(GRO), OUT]))

    print("=" * 60)
    inst = discover_vmd()
    if inst:
        print(f"[1] VMD found : {inst.binary}")
        print(f"    ping      : {tools.session.ping()}")
    else:
        print("[1] VMD not found (set VMD_BIN) — skipping render; analysis still runs")

    print("\n[2] Identifying cages in a real sII CO2 hydrate (1088 waters)...")
    cages = tools.identify_cages(GRO)
    print(f"    cage counts : {cages['counts']}")
    print(f"    structure   : {cages['structure']}  (confidence {cages['confidence']:.2f})")

    op = tools.hydrate_order_params(GRO)
    print(f"    F4 order    : {op['f4_overall']:.3f}  ({op['interpretation']})")

    if inst:
        print("\n[3] Rendering cages headlessly (blue = 5^12, red = 5^12 6^4)...")
        png = tools.render_cages(GRO, 900, 700)
        out_png = os.path.join(OUT, "cages.png")
        with open(out_png, "wb") as fh:
            fh.write(png)
        print(f"    saved       : {out_png} ({len(png)} bytes)")

    tools.shutdown()
    print("\n" + "=" * 60)
    print("OK — vmd-hydrate-mcp drove VMD and identified the cages above.")


if __name__ == "__main__":
    main()

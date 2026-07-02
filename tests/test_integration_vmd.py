"""Integration tests that drive a real VMD install. Auto-skipped when none is
found, so CI without VMD stays green; run locally to exercise the live session,
the injection defense against a real interpreter, and the headless render path.
"""

from pathlib import Path

import pytest

from vmd_hydrate_mcp.config import Settings
from vmd_hydrate_mcp.tools import Tools
from vmd_hydrate_mcp.security import SecurityError
from vmd_hydrate_mcp.vmd.discovery import discover_vmd

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent / "fixtures"
FIX_GRO = str(FIXTURES / "hydrate_10waters.gro")

_HAVE_VMD = discover_vmd() is not None
skip_no_vmd = pytest.mark.skipif(not _HAVE_VMD, reason="no VMD install found")


@pytest.fixture
def tools():
    t = Tools(Settings(allow_dirs=[FIXTURES]))
    yield t
    t.shutdown()


@skip_no_vmd
def test_session_ping(tools):
    status = tools.vmd_status()
    assert status["vmd_available"] is True
    assert "pong" in status["vmd"]


@skip_no_vmd
def test_load_and_state_persists(tools):
    a = tools.load_structure(FIX_GRO)
    assert a["numatoms"] == 30
    # a second call sees the molecule loaded by the first (persistent session)
    mols = tools.list_molecules()["molecules"]
    assert any(m["molid"] == a["molid"] for m in mols)


@skip_no_vmd
def test_representation_and_render(tools):
    a = tools.load_structure(FIX_GRO)
    tools.set_representation(a["molid"], "VDW", "Name", "Opaque", "all")
    png = tools.render(a["molid"], 320, 240)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
    assert len(png) > 1000


@skip_no_vmd
def test_injection_is_inert_against_real_interpreter(tools):
    a = tools.load_structure(FIX_GRO)
    # our guard rejects it before it ever reaches Tcl
    with pytest.raises(SecurityError):
        tools.set_representation(a["molid"], "Lines", "Name", "Opaque", "all]; puts PWNED; [")


@skip_no_vmd
def test_render_cages_produces_png(tools):
    png = tools.render_cages(str(FIXTURES / "hydrate_sII_222.gro"), width=360, height=360)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000


@skip_no_vmd
def test_render_cages_nl_styling(tools):
    # "show only sII 5^12 6^4 cages in magenta, emphasized" -> these args
    png = tools.render_cages(
        str(FIXTURES / "hydrate_sII_222.gro"),
        cage_types=["51264"], highlight_color="magenta", emphasis=True,
        width=320, height=320,
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

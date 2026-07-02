"""Security tests — the path allowlist can't be tricked and Tcl injection is inert.

These assert the path allowlist can't be bypassed and that Tcl argument quoting /
selection filtering make injection inert. They run without VMD.
"""

import os

import pytest

from vmd_hydrate_mcp.security import PathGuard, SecurityError, looks_like_tcl_injection
from vmd_hydrate_mcp.vmd.tcl import tcl_quote, tcl_list


# --------------------------------------------------------------------------- #
# PathGuard                                                                   #
# --------------------------------------------------------------------------- #
def test_pathguard_allows_inside_root(tmp_path):
    f = tmp_path / "ok.gro"
    f.write_text("x")
    g = PathGuard([tmp_path])
    assert g.resolve(str(f)) == f.resolve()


def test_pathguard_rejects_outside_root(tmp_path):
    g = PathGuard([tmp_path])
    with pytest.raises(SecurityError):
        g.resolve("/etc/hosts")


def test_pathguard_rejects_prefix_sibling_trick(tmp_path):
    # /data must NOT permit /data-evil (component-wise, not str.startswith)
    root = tmp_path / "data"
    root.mkdir()
    evil = tmp_path / "data-evil"
    evil.mkdir()
    target = evil / "secret.gro"
    target.write_text("x")
    g = PathGuard([root])
    with pytest.raises(SecurityError):
        g.resolve(str(target))


def test_pathguard_rejects_traversal(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "outside.gro"
    outside.write_text("x")
    g = PathGuard([root])
    with pytest.raises(SecurityError):
        g.resolve(str(root / ".." / "outside.gro"))


def test_pathguard_rejects_symlink_escape(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    secret = tmp_path / "secret.gro"
    secret.write_text("x")
    link = root / "link.gro"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported")
    g = PathGuard([root])
    with pytest.raises(SecurityError):
        g.resolve(str(link))  # realpath escapes root


# --------------------------------------------------------------------------- #
# Tcl quoting / injection — the RED corpus                                     #
# --------------------------------------------------------------------------- #
def test_tcl_quote_simple_and_spaced():
    assert tcl_quote("all") == "all"
    assert tcl_quote("water and name OW") == "{water and name OW}"
    assert tcl_list(["recipe_x", 0, "name CA"]) == "recipe_x 0 {name CA}"


def test_tcl_quote_rejects_unbalanced_and_trailing_backslash():
    with pytest.raises(SecurityError):
        tcl_quote("a{b")           # unbalanced brace
    with pytest.raises(SecurityError):
        tcl_quote("x\\")           # trailing backslash escapes the close brace
    with pytest.raises(SecurityError):
        tcl_quote("a\x00b")        # NUL


@pytest.mark.parametrize(
    "payload",
    [
        "all] ; puts HACKED ; [",
        "eval [binary decode base64 ZXhlYw==]",
        "gopython -command {exec sh}",
        "] {*}[list exec sh]",
        "water;quit",
        "name $env(HOME)",
        "a`whoami`",
        "x\nquit",
    ],
)
def test_injection_selections_are_flagged(payload):
    # every one contains a Tcl metacharacter our selection filter forbids
    assert looks_like_tcl_injection(payload) is True


def test_benign_selections_pass():
    for ok in ("all", "water", "name CA", "resname SOL", "name OW and within 3 of protein"):
        assert looks_like_tcl_injection(ok) is False

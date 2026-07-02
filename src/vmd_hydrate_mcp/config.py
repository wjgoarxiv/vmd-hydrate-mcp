"""Runtime configuration, sourced from environment variables.

Env vars:
  VMD_BIN                     explicit path to the VMD executable
  VMD_HYDRATE_MCP_ALLOW_DIR   os.pathsep-separated roots that file args must live under
  VMD_HYDRATE_MCP_ENABLE_TCL  "1" to expose the raw run_tcl power tool (dev-only, OFF by default)
  VMD_HYDRATE_MCP_TIMEOUT     per-request VMD wall-clock timeout, seconds (default 120)
  VMD_HYDRATE_MCP_MAX_PX      max render edge in pixels (default 1280)
  VMD_HYDRATE_MCP_DISPLAY     "headless" (default, offscreen) or "gui" (opens a
                              visible VMD window you can watch Claude drive live)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    vmd_bin: Optional[str] = None
    allow_dirs: List[Path] = field(default_factory=list)
    enable_run_tcl: bool = False
    request_timeout_s: float = 120.0
    max_render_px: int = 1280
    display: str = "headless"  # "headless" (offscreen) or "gui" (visible window)

    @property
    def gui(self) -> bool:
        return self.display == "gui"

    @classmethod
    def from_env(cls) -> "Settings":
        allow = os.environ.get("VMD_HYDRATE_MCP_ALLOW_DIR", "")
        dirs = [Path(p).expanduser().resolve() for p in allow.split(os.pathsep) if p.strip()]
        if not dirs:
            dirs = [Path.cwd().resolve()]
        disp = os.environ.get("VMD_HYDRATE_MCP_DISPLAY", "headless").strip().lower()
        return cls(
            vmd_bin=os.environ.get("VMD_BIN") or None,
            allow_dirs=dirs,
            enable_run_tcl=_env_bool("VMD_HYDRATE_MCP_ENABLE_TCL", False),
            request_timeout_s=float(os.environ.get("VMD_HYDRATE_MCP_TIMEOUT", "120")),
            max_render_px=int(os.environ.get("VMD_HYDRATE_MCP_MAX_PX", "1280")),
            display=("gui" if disp == "gui" else "headless"),
        )

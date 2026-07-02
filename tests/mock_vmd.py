"""A stand-in VMD session that speaks the same interface as VmdSession, so the
tool layer can be exercised in CI without a real VMD install."""

from __future__ import annotations

from typing import Dict, List, Tuple

from vmd_hydrate_mcp.vmd.session import MolMeta


class MockVmdSession:
    def __init__(self):
        self.registry: Dict[int, MolMeta] = {}
        self.calls: List[Tuple] = []
        self._next = 0
        self.install = None

    def ping(self) -> str:
        return "pong MOCK 0.0"

    def load(self, path: str, ftype: str = "auto") -> MolMeta:
        molid = self._next
        self._next += 1
        meta = MolMeta(molid=molid, path=path, numatoms=3, numframes=1)
        self.registry[molid] = meta
        return meta

    def call(self, recipe: str, *args) -> str:
        self.calls.append((recipe, args))
        if recipe == "recipe_representation":
            return "reps 1 sel 3"
        return "ok"

    def shutdown(self):
        pass

"""Persistent, stateful VMD session driven over a loopback Tcl socket.

Unlike re-spawning VMD per call, a persistent session keeps molecules,
representations and camera alive across tool calls. VMD runs `-dispdev text -e
server.tcl`, serving a token-gated, length-prefixed protocol on 127.0.0.1.

Guarantees:
  * P1 — a single lock serializes every round-trip and the lazy start.
  * P3 — VMD stdout/stderr are captured (never inherit the server's fd1/2) and
    drained to stderr logging; the JSON-RPC stdout stays clean.
  * S4 — a per-request socket timeout acts as a wall-clock watchdog: a hung
    recipe kills and (on next use) restarts VMD.
  * P4 — a molid->metadata registry lets analysis tools resolve paths and lets
    crash-restart report invalidated handles.
"""

from __future__ import annotations

import logging
import os
import secrets
import socket
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ..config import Settings
from .discovery import VmdInstall, discover_vmd
from .tcl import tcl_list

log = logging.getLogger("vmd_hydrate_mcp.session")

_SERVER_TCL = os.path.join(os.path.dirname(__file__), "server.tcl")


class VmdError(RuntimeError):
    pass


class VmdUnavailable(VmdError):
    """No runnable VMD install was found."""


@dataclass
class MolMeta:
    molid: int
    path: str
    numatoms: int
    numframes: int


def _parse_kv(s: str) -> Dict[str, str]:
    toks = s.split()
    return {toks[i]: toks[i + 1] for i in range(0, len(toks) - 1, 2)}


class VmdSession:
    def __init__(self, settings: Optional[Settings] = None, install: Optional[VmdInstall] = None):
        self.settings = settings or Settings.from_env()
        self._install = install
        self._proc: Optional[subprocess.Popen] = None
        self._sock: Optional[socket.socket] = None
        self._port: Optional[int] = None
        self._token: Optional[str] = None
        self._tokenfile: Optional[str] = None
        self._lock = threading.RLock()
        self._port_event = threading.Event()
        self._drain_thread: Optional[threading.Thread] = None
        self.registry: Dict[int, MolMeta] = {}

    # -- lifecycle ------------------------------------------------------------
    @property
    def install(self) -> VmdInstall:
        if self._install is None:
            found = discover_vmd(self.settings.vmd_bin)
            if found is None:
                raise VmdUnavailable(
                    "no runnable VMD found; set VMD_BIN to the vmd executable"
                )
            self._install = found
        return self._install

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None and self._sock is not None

    def _ensure_started(self):
        with self._lock:
            if self.is_alive():
                return
            self._start_locked()

    def _start_locked(self):
        self._token = secrets.token_hex(32)
        fd, self._tokenfile = tempfile.mkstemp(prefix="vmdhydrate_tok_")
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        with os.fdopen(fd, "w") as fh:
            fh.write(self._token)

        env = dict(self.install.env)
        env["VMDHYDRATE_TOKENFILE"] = self._tokenfile
        self._port = None
        self._port_event.clear()

        # GUI mode opens a visible OpenGL window (attended mode); headless uses
        # the offscreen text device. In GUI mode VMD exits on stdin EOF, so we
        # keep stdin as an open pipe (never closed until shutdown); headless
        # takes /dev/null. Either way the same Tcl socket server drives it.
        gui = self.settings.gui
        args = [self.install.binary]
        if not gui:
            args += ["-dispdev", "text"]
        args += ["-e", _SERVER_TCL]
        self._proc = subprocess.Popen(
            args,
            stdin=(subprocess.PIPE if gui else subprocess.DEVNULL),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            bufsize=1,
        )
        self._drain_thread = threading.Thread(target=self._drain, daemon=True)
        self._drain_thread.start()

        if not self._port_event.wait(timeout=30):
            self._kill_locked()
            raise VmdError("VMD server did not report a listening port within 30s")

        self._sock = socket.create_connection(("127.0.0.1", self._port), timeout=self.settings.request_timeout_s)
        self._sock.settimeout(self.settings.request_timeout_s)

    def _drain(self):
        """Read VMD's stdout: capture the port, log the rest to stderr."""
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("SERVER_LISTENING"):
                try:
                    self._port = int(line.split()[1])
                    self._port_event.set()
                except (IndexError, ValueError):
                    pass
            elif line.startswith("SERVER_FAIL"):
                log.error("VMD server failed: %s", line)
                self._port_event.set()  # unblock; port stays None -> caller errors
            else:
                log.debug("vmd: %s", line)

    def _kill_locked(self):
        for closer in (self._sock,):
            try:
                if closer:
                    closer.close()
            except OSError:
                pass
        self._sock = None
        if self._proc is not None:
            try:
                if self._proc.stdin:  # GUI mode: closing stdin (EOF) lets VMD exit
                    try:
                        self._proc.stdin.close()
                    except OSError:
                        pass
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            except ProcessLookupError:
                pass
        if self._tokenfile and os.path.exists(self._tokenfile):
            try:
                os.unlink(self._tokenfile)
            except OSError:
                pass

    def shutdown(self):
        with self._lock:
            self._kill_locked()
            self._proc = None

    # -- protocol -------------------------------------------------------------
    def _recv_line(self) -> str:
        assert self._sock is not None
        buf = bytearray()
        while True:
            ch = self._sock.recv(1)
            if not ch:
                raise VmdError("connection closed by VMD")
            if ch == b"\n":
                return buf.decode()
            buf += ch

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise VmdError("connection closed by VMD")
            buf += chunk
        return bytes(buf)

    def request(self, recipe: str, *args) -> Tuple[int, str]:
        """Send a recipe request; return (code, result). Serialized + watchdog."""
        self._ensure_started()
        reqlist = tcl_list([recipe, *args])
        payload = (self._token + "\n" + reqlist).encode()
        header = f"{len(payload)}\n".encode()
        with self._lock:
            try:
                self._sock.sendall(header + payload)
                hdr = self._recv_line()
                n = int(hdr)
                body = self._recv_exact(n).decode()
            except (socket.timeout, VmdError, OSError) as e:
                # watchdog: hung or dead -> kill so the next call restarts fresh
                self._kill_locked()
                self._proc = None
                raise VmdError(f"VMD request '{recipe}' failed: {e}") from e
        nl = body.find("\n")
        code = int(body[:nl])
        return code, body[nl + 1:]

    def call(self, recipe: str, *args) -> str:
        code, res = self.request(recipe, *args)
        if code != 0:
            raise VmdError(f"{recipe}: {res}")
        return res

    # -- high-level ops -------------------------------------------------------
    def ping(self) -> str:
        return self.call("recipe_ping")

    def load(self, path: str, ftype: str = "auto") -> MolMeta:
        res = self.call("recipe_load", path, ftype)
        kv = _parse_kv(res)
        molid = int(kv["molid"])
        meta = MolMeta(molid=molid, path=path, numatoms=int(kv["numatoms"]), numframes=int(kv["numframes"]))
        self.registry[molid] = meta
        return meta

    def molid_for(self, molid: int) -> MolMeta:
        if molid not in self.registry:
            raise VmdError(f"unknown molid {molid}; load a structure first")
        return self.registry[molid]

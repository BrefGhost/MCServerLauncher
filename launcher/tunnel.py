"""Expose the local server to the internet through a playit.gg tunnel.

Why playit and not port forwarding: most Thai home connections sit behind
CGNAT, so there is no public port to forward. playit runs an outbound agent and
hands back a public `something.gl.joinmc.link` address instead.

The public address comes from playit's own API - `POST /agents/rundata` with an
`Authorization: Agent-Key <secret>` header returns every tunnel on the account,
including its `assigned_domain` and port. The agent binary never prints it, but
the API the agent itself talks to does.

Why version 0.17.1:
  * 1.0.x dropped the CLI entirely - its exe is a daemon that waits for a GUI
    frontend over IPC, so it cannot be driven from here at all.
  * In 0.17.1 the `tunnels prepare` / `tunnels list` subcommands answer
    `Error: NotImplemented`, but the binary still runs the tunnel, which is all
    it is needed for - the address is read from the API instead.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable

from .config import PLAYIT_EXE, PLAYIT_SECRET_FILE, PLAYIT_SHA256, PLAYIT_URL, DATA_DIR
from .installer import download

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
Log = Callable[[str], None]

API_BASE = "https://api.playit.gg"
TUNNELS_PAGE = "https://playit.gg/account/tunnels"

RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][A-Z0-9]")
RE_BOX = re.compile(r"[─-╿]+")
RE_ADDRESS = re.compile(
    r"\b([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\."
    r"(?:playit\.gg|joinmc\.link|ply\.gg)(?::\d+)?)\b")
RE_CLAIM_URL = re.compile(r"https://playit\.gg/claim/\S+")
RE_TUNNEL_COUNT = re.compile(r"tunnel running, (\d+) tunnels registered")


class PlayitError(RuntimeError):
    pass


def clean(text: str) -> str:
    """Drop TUI escape codes and box drawing, keep the actual words."""
    text = RE_ANSI.sub(" ", text)
    text = RE_BOX.sub(" ", text)
    return re.sub(r"[ \t ]+", " ", text).strip()


def ensure_agent(progress=None) -> Path:
    download(PLAYIT_URL, PLAYIT_EXE, progress, sha256=PLAYIT_SHA256)
    return PLAYIT_EXE


def has_secret() -> bool:
    return (PLAYIT_SECRET_FILE.exists()
            and len(PLAYIT_SECRET_FILE.read_text(encoding="utf-8").strip()) >= 32)


def import_existing_secret() -> bool:
    """Reuse the secret from an existing playit install if the user has one."""
    for path in (Path(os.environ.get("LOCALAPPDATA", "")) / "playit_gg" / "playit.toml",
                 Path(os.environ.get("APPDATA", "")) / "playit_gg" / "playit.toml",
                 Path(os.path.expanduser("~")) / ".config" / "playit_gg" / "playit.toml"):
        if not path.is_file():
            continue
        m = re.search(r'secret_key\s*=\s*"([^"]+)"',
                      path.read_text(encoding="utf-8", errors="replace"))
        if m:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            PLAYIT_SECRET_FILE.write_text(m.group(1), encoding="utf-8")
            return True
    return False


def forget_account() -> None:
    PLAYIT_SECRET_FILE.unlink(missing_ok=True)


# ------------------------------------------------------------------- api
def _secret() -> str:
    return PLAYIT_SECRET_FILE.read_text(encoding="utf-8").strip()


def api(path: str, body: dict | None = None, timeout: float = 30.0) -> dict:
    """Call playit's API as this agent. Every endpoint is a POST."""
    if not has_secret():
        raise PlayitError("ยังไม่ได้เชื่อมบัญชี playit.gg")
    request = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(body or {}).encode("utf-8"),
        headers={"Authorization": f"Agent-Key {_secret()}",
                 "Content-Type": "application/json",
                 "User-Agent": "MCServerLauncher/1.0"},
        method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise PlayitError(f"playit ตอบกลับว่า: {payload}")
    return payload.get("data") or {}


def tunnel_address(tunnel: dict) -> str:
    """`cynthia-gonna.tun.ply.gg:37914` - the port is dropped when it is 25565.

    Minecraft assumes 25565, so leaving it off makes for a tidier address to
    hand out; any other port has to be shown.
    """
    domain = tunnel.get("assigned_domain") or tunnel.get("custom_domain") or ""
    if not domain:
        return ""
    port = (tunnel.get("port") or {}).get("from")
    return domain if port in (None, 25565) else f"{domain}:{port}"


def find_tunnel(tunnels: list[dict], local_port: int) -> dict | None:
    """Pick the tunnel that points at our server, preferring an exact match."""
    for want_exact in (True, False):
        for t in tunnels:
            if not (t.get("assigned_domain") or t.get("custom_domain")):
                continue
            if want_exact and t.get("local_port") != local_port:
                continue
            if not want_exact and t.get("tunnel_type") != "minecraft-java":
                continue
            return t
    return None


def create_tunnel(agent_id: str, local_port: int, name: str) -> dict:
    """Make a Minecraft tunnel for this agent so the user never visits the site."""
    api("/tunnels/create", {
        "name": name[:60],
        "tunnel_type": "minecraft-java",
        "port_type": "tcp",
        "port_count": 1,
        "enabled": True,
        "origin": {"type": "agent",
                   "data": {"agent_id": agent_id,
                            "local_ip": "127.0.0.1",
                            "local_port": local_port}},
    })
    return api("/agents/rundata")


def public_address(local_port: int = 25565, name: str = "MC Server Launcher",
                   create_if_missing: bool = True,
                   log: Log | None = None) -> str:
    """The address to hand to players, creating the tunnel if there is none."""
    data = api("/agents/rundata")
    tunnels = data.get("tunnels") or []
    found = find_tunnel(tunnels, local_port)

    if found is None and create_if_missing and data.get("agent_id"):
        if log:
            log("[playit] ยังไม่มี tunnel — กำลังสร้างให้อัตโนมัติ")
        data = create_tunnel(str(data["agent_id"]), local_port, name)
        found = find_tunnel(data.get("tunnels") or [], local_port)

    return tunnel_address(found) if found else ""


def wait_for_address(local_port: int = 25565, name: str = "MC Server Launcher",
                     timeout: float = 90.0, log: Log | None = None) -> str:
    """A freshly created tunnel takes a few seconds to get its domain."""
    deadline = time.time() + timeout
    create = True
    while time.time() < deadline:
        try:
            address = public_address(local_port, name, create, log)
            if address:
                return address
            create = False          # only ever create one
        except Exception as exc:
            if log:
                log(f"[playit] ยังอ่านที่อยู่ไม่ได้: {exc}")
        time.sleep(3.0)
    return ""


class PlayitAgent:
    """The `playit start` process: links the account and carries the traffic.

    When there is no secret yet the agent prints a claim link and repeats it
    until the user approves it in a browser, then writes the secret itself -
    which is why we never have to parse the secret out of its output.
    """

    def __init__(self, on_log: Log,
                 on_claim: Callable[[str], None] | None = None,
                 on_tunnels: Callable[[int], None] | None = None):
        self.on_log = on_log
        self.on_claim = on_claim or (lambda _: None)
        self.on_tunnels = on_tunnels or (lambda _: None)
        self.proc: subprocess.Popen | None = None
        self.claim_url: str = ""
        self.tunnel_count: int = -1
        self.address: str = ""
        self._stopping = False

    @property
    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def connected(self) -> bool:
        return self.tunnel_count > 0

    def start(self, progress=None) -> None:
        if self.is_alive:
            return
        ensure_agent(progress)
        if not has_secret():
            import_existing_secret()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        self._stopping = False
        # -s keeps output as plain log lines; without it the agent paints a
        # full-screen TUI that mangles anything we try to read.
        self.proc = subprocess.Popen(
            [str(PLAYIT_EXE), "--secret_path", str(PLAYIT_SECRET_FILE), "-s", "start"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            creationflags=NO_WINDOW)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = clean(raw)
            if not line:
                continue

            m = RE_CLAIM_URL.search(line)
            if m and m.group(0) != self.claim_url:
                self.claim_url = m.group(0)
                self.on_claim(self.claim_url)
                continue

            m = RE_TUNNEL_COUNT.search(line)
            if m:
                count = int(m.group(1))
                if count != self.tunnel_count:
                    self.tunnel_count = count
                    self.on_tunnels(count)
                continue      # this line repeats every few seconds; don't log it

            m = RE_ADDRESS.search(line)
            if m:
                self.address = m.group(1)

            self.on_log(f"[playit] {line}")

        if not self._stopping:
            self.on_log("[playit] ตัวเชื่อมต่อหลุด — เพื่อนจากข้างนอกจะต่อไม่ได้แล้ว")

    def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """Block until the agent reports at least one registered tunnel."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.connected:
                return True
            if not self.is_alive:
                return False
            time.sleep(0.5)
        return self.connected

    def stop(self) -> None:
        self._stopping = True
        if self.proc and self.is_alive:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                               capture_output=True, creationflags=NO_WINDOW)
            else:
                self.proc.kill()


def open_tunnels_page() -> None:
    webbrowser.open(TUNNELS_PAGE)

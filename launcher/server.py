"""Run the Minecraft server process and expose its console."""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# Forge/NeoForge colour their console output; the escapes break every pattern
# below and the crash analysis, so strip them the moment a line arrives.
RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
RE_DONE = re.compile(r'Done \([\d.,]+s\)! For help, type "help"')
RE_JOIN = re.compile(r"\]: (\w{2,16}) joined the game")
# A player bounced off the mod handshake. The server never learns which mod is
# missing - only the client's screen shows that - so all we can do is say so.
RE_HANDSHAKE_REJECT = re.compile(
    r"mismatched mod channel list|Connection closed - mismatched"
    r"|negotiation failed|Incompatible client")
RE_LEAVE = re.compile(r"\]: (\w{2,16}) left the game")
RE_STARTING = re.compile(r"Starting minecraft server version|Loading \d+ mods")
# The server can report a fatal startup error and then never exit, because a
# mod's background thread keeps the JVM alive. Treat these lines as the end.
RE_FATAL = re.compile(
    r"Failed to start the minecraft server"
    r"|ModLoadingException: Loading errors encountered"
    r"|Loading errors have occurred")
FATAL_GRACE = 6.0          # seconds to keep reading before killing a dead start


class State(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"


class MinecraftServer:
    """One server process. All callbacks fire on the reader thread."""

    def __init__(self, server_dir: Path,
                 on_line: Callable[[str], None],
                 on_state: Callable[[State], None],
                 on_players: Callable[[set[str]], None] | None = None):
        self.server_dir = server_dir
        self.on_line = on_line
        self.on_state = on_state
        self.on_players = on_players or (lambda _: None)
        self.proc: subprocess.Popen | None = None
        self.state = State.STOPPED
        self.players: set[str] = set()
        self.exit_code: int | None = None
        self.started_at: float = 0.0
        self.recent: list[str] = []          # tail kept for crash analysis
        self._fatal = False
        self._stop_requested = False
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- state
    def _set_state(self, state: State) -> None:
        self.state = state
        self.on_state(state)

    @property
    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def uptime(self) -> float:
        return time.time() - self.started_at if self.started_at else 0.0

    # ---------------------------------------------------------------- start
    def start(self, command: list[str]) -> None:
        if self.is_alive:
            raise RuntimeError("เซิร์ฟเวอร์กำลังทำงานอยู่แล้ว")
        self.players.clear()
        self.recent.clear()
        self.exit_code = None
        self._fatal = False
        self._stop_requested = False
        self.started_at = time.time()
        self.kill_orphan()
        self._set_state(State.STARTING)

        env = dict(os.environ, JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8")
        self.proc = subprocess.Popen(
            command, cwd=str(self.server_dir), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            creationflags=NO_WINDOW, env=env)
        self._write_pid(self.proc.pid)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = RE_ANSI.sub("", raw.rstrip("\r\n"))
            self.recent.append(line)
            if len(self.recent) > 400:
                del self.recent[:100]
            self._inspect(line)
            self.on_line(line)

        self.exit_code = self.proc.wait()
        self._clear_pid()
        if self._stop_requested:
            self._set_state(State.STOPPED)
        elif self.state is State.STARTING:
            # NeoForge exits 0 after a mod-loading error, so a clean exit code
            # means nothing: dying before "Done" is always a failed start.
            self._set_state(State.CRASHED)
        elif self.exit_code == 0:
            self._set_state(State.STOPPED)
        else:
            self._set_state(State.CRASHED)

    def _inspect(self, line: str) -> None:
        if self.state is State.STARTING and RE_DONE.search(line):
            self._set_state(State.RUNNING)
            return
        if self.state is State.STARTING and not self._fatal and RE_FATAL.search(line):
            self._fatal = True
            self.on_line("[launcher] เซิร์ฟเวอร์เปิดไม่ขึ้น กำลังปิดโปรเซสเพื่อลองแก้ …")
            threading.Timer(FATAL_GRACE, self._kill_if_stuck).start()
            return
        if RE_HANDSHAKE_REJECT.search(line):
            self.on_line(
                "[launcher] มีคนเข้าไม่ได้เพราะม็อดฝั่งเซิร์ฟเวอร์กับฝั่งเกมไม่ตรงกัน — "
                "ดูชื่อม็อดที่หน้าจอเกมบอก แล้วพิมพ์ลงช่อง "
                '"ม็อดที่เซิร์ฟเวอร์ขาด" ในโปรแกรม')
            return
        m = RE_JOIN.search(line)
        if m:
            self.players.add(m.group(1))
            self.on_players(set(self.players))
            return
        m = RE_LEAVE.search(line)
        if m:
            self.players.discard(m.group(1))
            self.on_players(set(self.players))

    # ----------------------------------------------------------------- send
    def send(self, command: str) -> None:
        if not self.is_alive or self.proc is None or self.proc.stdin is None:
            raise RuntimeError("เซิร์ฟเวอร์ยังไม่ทำงาน")
        with self._lock:
            self.proc.stdin.write(command.rstrip("\n") + "\n")
            self.proc.stdin.flush()

    # ----------------------------------------------------------------- stop
    def stop(self, timeout: float = 120.0) -> None:
        """Ask the server to save and shut down; force-kill if it hangs."""
        if not self.is_alive:
            return
        self._stop_requested = True
        self._set_state(State.STOPPING)
        try:
            self.send("stop")
        except Exception:
            pass

        deadline = time.time() + timeout
        while time.time() < deadline and self.is_alive:
            time.sleep(0.4)
        if self.is_alive:
            self.on_line("[launcher] เซิร์ฟเวอร์ไม่ตอบสนอง กำลังบังคับปิด …")
            self.kill()

    def _kill_if_stuck(self) -> None:
        """A start that reported a fatal error but is still alive is hung."""
        if self.is_alive and self.state is State.STARTING:
            self.kill()

    # ------------------------------------------------------------ orphan pid
    @property
    def _pid_file(self) -> Path:
        return self.server_dir / "launcher-server.pid"

    def _write_pid(self, pid: int) -> None:
        try:
            self._pid_file.write_text(str(pid), encoding="utf-8")
        except OSError:
            pass

    def _clear_pid(self) -> None:
        self._pid_file.unlink(missing_ok=True)

    def kill_orphan(self) -> bool:
        """Kill a server left running by a previous session.

        Minecraft holds an exclusive lock on world/session.lock, so an orphan
        from a crashed run makes every later start fail with "another process
        has locked a portion of the file".
        """
        try:
            pid = int(self._pid_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return False
        if os.name != "nt":
            self._clear_pid()
            return False
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FI", "IMAGENAME eq java.exe", "/NH"],
            capture_output=True, text=True, creationflags=NO_WINDOW)
        if str(pid) in (listing.stdout or ""):
            self.on_line(f"[launcher] พบเซิร์ฟเวอร์ค้างจากรอบก่อน (PID {pid}) — ปิดให้ก่อน")
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, creationflags=NO_WINDOW)
            time.sleep(1.5)
            self._clear_pid()
            return True
        self._clear_pid()
        return False

    def kill(self) -> None:
        if self.proc is None:
            return
        pid = self.proc.pid
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, creationflags=NO_WINDOW)
        else:
            self.proc.kill()

    # -------------------------------------------------------------- helpers
    def latest_log(self) -> str:
        p = self.server_dir / "logs" / "latest.log"
        if p.exists():
            try:
                return RE_ANSI.sub("", p.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                return ""
        return ""

    def latest_crash_report(self) -> str:
        d = self.server_dir / "crash-reports"
        if not d.is_dir():
            return ""
        reports = sorted(d.glob("crash-*.txt"), key=lambda p: p.stat().st_mtime)
        if not reports:
            return ""
        # Ignore stale reports from previous runs.
        if reports[-1].stat().st_mtime < self.started_at - 5:
            return ""
        try:
            return reports[-1].read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

"""Orchestration: prepare -> launch -> auto-heal -> tunnel, on a worker thread."""
from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Callable

from . import (autoheal, installer, javafinder, serverconf, serverpack,
               sync, tunnel)
from .config import LOGS_DIR, PackSettings, SERVERS_DIR, ensure_dirs
from .instances import Instance
from .server import MinecraftServer, State

# Every restart takes the loader a minute on a heavy pack, but each one
# removes every mod the loader convicted, not just one, so this converges
# in a handful of rounds even for a 364-mod pack.
MAX_ATTEMPTS = 25


class Session:
    """Everything the UI needs to run one modpack server."""

    def __init__(self, instance: Instance, settings: PackSettings,
                 eula_accepted: bool,
                 on_log: Callable[[str], None],
                 on_status: Callable[[str], None],
                 on_state: Callable[[str], None],
                 on_address: Callable[[str], None],
                 on_players: Callable[[set[str]], None]):
        self.instance = instance
        self.settings = settings
        self.eula_accepted = eula_accepted
        # Everything the console shows is also written to a file. Without it a
        # failure that scrolled past in the window cannot be diagnosed later.
        self._log_path = LOGS_DIR / f"launcher-{instance.slug}.log"
        self._log_lock = threading.Lock()
        self._ui_log = on_log
        self.on_log = self._log
        self.on_status = on_status
        self.on_state = on_state
        self.on_address = on_address
        self.on_players = on_players

        self.server_dir: Path = SERVERS_DIR / instance.slug
        self.server: MinecraftServer | None = None
        self.agent: tunnel.PlayitAgent | None = None
        self.address: str = ""
        self._stop_requested = False
        self._state_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_state: State = State.STOPPED
        self._env_retries = 0
        self.server_pack = False    # mods came from the author's pack

    def _log(self, line: str) -> None:
        self._ui_log(line)
        try:
            with self._log_lock, self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("กำลังทำงานอยู่แล้ว")
        self._stop_requested = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        self._stop_requested = True
        self._state_event.set()
        if self.server and self.server.is_alive:
            threading.Thread(target=self.server.stop, daemon=True).start()

    def send(self, command: str) -> None:
        if not self.server:
            raise RuntimeError("เซิร์ฟเวอร์ยังไม่ทำงาน")
        self.server.send(command)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------ main
    def _run(self) -> None:
        try:
            ensure_dirs()
            self._log_path.write_text("", encoding="utf-8")
            self._prepare()
            self._launch_loop()
        except Exception as exc:                       # surfaced in the console
            self.on_log(f"[ผิดพลาด] {exc}")
            self.on_log(traceback.format_exc())
            self.on_status(f"ล้มเหลว: {exc}")
            self.on_state("error")
        finally:
            if self.agent:
                self.agent.stop()
            self.on_state("stopped")

    # --------------------------------------------------------------- prepare
    def _prepare(self) -> None:
        ensure_dirs()
        inst = self.instance
        self.on_state("preparing")

        self.on_status("กำลังหา Java ที่เหมาะกับเวอร์ชันนี้ …")
        java, major, note = javafinder.find_java(inst.mc_version)
        if java is None:
            raise RuntimeError(
                f"ไม่พบ Java บนเครื่อง — Minecraft {inst.mc_version} ต้องใช้ Java "
                f"{javafinder.required_major(inst.mc_version)}")
        self.on_log(f"ใช้ Java {major}: {java}")
        if note:
            self.on_log(f"[เตือน] {note}")
        self.java = java

        self.server_dir.mkdir(parents=True, exist_ok=True)
        if not installer.is_installed(self.server_dir, inst.loader, inst.mc_version,
                                      inst.loader_version):
            self.on_status(f"กำลังติดตั้งเซิร์ฟเวอร์ {inst.loader_label} …")
            installer.install_server(
                self.server_dir, java, inst.loader, inst.mc_version,
                inst.loader_version,
                progress=lambda msg, pct: self.on_status(msg),
                log=self.on_log)
            self.on_log("ติดตั้งเซิร์ฟเวอร์เรียบร้อย")
        else:
            self.on_log(f"เจอเซิร์ฟเวอร์ {inst.loader_label} ที่ติดตั้งไว้แล้ว")

        if self._use_server_pack():
            self.on_log("ใช้ server pack ทางการของ modpack — ไม่ต้องเดาว่าม็อด"
                        "ตัวไหนเป็นของฝั่งผู้เล่น")
        else:
            self.on_status("กำลังคัดลอกม็อดและค่าตั้งจาก modpack …")
            sync.full_sync(inst.path, self.server_dir, inst.slug,
                           force_config=False, log=self.on_log)

        if self.settings.use_tunnel:
            serverconf.relax_proxy_filters(self.server_dir, log=self.on_log)

        serverconf.write_eula(self.server_dir, self.eula_accepted)
        serverconf.write_properties(self.server_dir, self.settings, inst.name)
        serverconf.write_ops(self.server_dir, self.settings.ops)
        serverconf.write_jvm_args_file(self.server_dir, self.settings.ram_gb)

    def _use_server_pack(self) -> bool:
        """Install the author's server pack if this pack has one.

        Returns True when the server's mods come from that pack, so the caller
        knows not to derive them from the client instance. A failed download
        falls back to guessing rather than stopping the launch.
        """
        inst = self.instance
        self.server_pack = bool(serverpack.installed_file_id(inst.slug))
        if not inst.has_server_pack:
            return False
        if not serverpack.needs_install(inst):
            return True

        try:
            self.on_status("กำลังดาวน์โหลด server pack ทางการของ modpack "
                           "(ไฟล์ใหญ่ ครั้งแรกครั้งเดียว) …")
            zip_path = serverpack.fetch(
                inst, progress=lambda msg, pct: self.on_status(
                    msg + (f" {pct*100:.0f}%" if pct >= 0 else "")))
            self.on_status("กำลังแตกไฟล์ server pack …")
            serverpack.install(inst, self.server_dir, zip_path, log=self.on_log)
            serverpack.cleanup_download(zip_path)
            self.server_pack = True
            return True
        except Exception as exc:
            self.on_log(f"[เตือน] โหลด server pack ทางการไม่สำเร็จ: {exc}")
            self.on_log("จะใช้วิธีคัดม็อดเองจากโฟลเดอร์เกมแทน")
            self.server_pack = False
            return False

    # ---------------------------------------------------------- launch loop
    def _launch_loop(self) -> None:
        if not self.eula_accepted:
            raise RuntimeError("ต้องติ๊กยอมรับ Minecraft EULA ก่อนถึงจะเปิดเซิร์ฟเวอร์ได้")
        inst = self.instance
        command = installer.build_command(
            self.server_dir, self.java, inst.loader, inst.mc_version,
            inst.loader_version, serverconf.jvm_args(self.settings.ram_gb))

        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self._stop_requested:
                return
            if attempt > 1:
                self.on_log(f"— ลองเปิดใหม่ครั้งที่ {attempt} —")
            self.on_status(f"กำลังเปิดเซิร์ฟเวอร์ (ครั้งที่ {attempt}) …")
            self.on_state("starting")

            self._state_event.clear()
            self.server = MinecraftServer(
                self.server_dir, on_line=self.on_log,
                on_state=self._server_state, on_players=self.on_players)
            self.server.start(command)

            # Wait for the server to either come up or die.
            while True:
                self._state_event.wait(timeout=1.0)
                self._state_event.clear()
                if self._last_state in (State.RUNNING, State.STOPPED, State.CRASHED):
                    break
                if self._stop_requested:
                    return

            if self._last_state is State.RUNNING:
                self._on_ready()
                self._wait_until_down()
                return
            if self._last_state is State.STOPPED:
                self.on_status("เซิร์ฟเวอร์ปิดแล้ว")
                return

            if not self._heal():
                return

        self.on_status("แก้อัตโนมัติครบจำนวนครั้งแล้วแต่ยังเปิดไม่ขึ้น")
        self.on_log("ลองดูรายละเอียดใน logs/latest.log ของโฟลเดอร์เซิร์ฟเวอร์")

    def _server_state(self, state: State) -> None:
        self._last_state = state
        self._state_event.set()

    def _on_ready(self) -> None:
        self.on_state("running")
        self.on_status("เซิร์ฟเวอร์พร้อมแล้ว")
        self.on_log(f"เข้าเล่นในวงแลนได้ที่ localhost:{self.settings.port}")
        if self.settings.use_tunnel:
            self._start_tunnel()

    def _start_tunnel(self) -> None:
        try:
            self.on_status("กำลังเปิดช่องทางให้เพื่อนต่อจากข้างนอก …")
            self.agent = tunnel.PlayitAgent(
                on_log=self.on_log, on_claim=self._on_claim,
                on_tunnels=self._on_tunnels)
            self.agent.start(progress=lambda msg, pct: self.on_status(msg))

            self.agent.wait_until_ready(timeout=90)

            self.on_status("กำลังอ่านที่อยู่สาธารณะจาก playit.gg …")
            address = tunnel.wait_for_address(
                local_port=self.settings.port,
                name=f"MC {self.instance.name}",
                log=self.on_log)
            if not address:
                # A hand-entered address stays as the fallback.
                address = self.settings.tunnel_address

            if address:
                self.address = address
                self.on_address(address)
                self.on_log(f"ที่อยู่สำหรับเพื่อน: {address}")
                self.on_status("เซิร์ฟเวอร์ออนไลน์แล้ว")
            else:
                self.on_log("[playit] อ่านที่อยู่ไม่สำเร็จ — ดูได้ที่ "
                            f"{tunnel.TUNNELS_PAGE}")
                self.on_status("เซิร์ฟเวอร์พร้อมแล้ว (ยังไม่ได้ที่อยู่ภายนอก)")
        except Exception as exc:
            self.on_log(f"[playit] เปิดช่องทางภายนอกไม่สำเร็จ: {exc}")
            self.on_log("เซิร์ฟเวอร์ยังเล่นในวงแลนได้ตามปกติ")
            self.on_status("ออนไลน์ไม่ได้ แต่เล่นในวงแลนได้")

    def _on_claim(self, url: str) -> None:
        self.on_log("[playit] ยังไม่ได้เชื่อมบัญชี playit.gg — เปิดลิงก์นี้แล้วกดยืนยัน:")
        self.on_log(f"[playit]   {url}")
        self.on_status("รอยืนยันบัญชี playit.gg ในเบราว์เซอร์ …")
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    def _on_tunnels(self, count: int) -> None:
        if count > 0:
            self.on_log(f"[playit] เชื่อมต่อแล้ว ({count} tunnel)")
        else:
            self.on_log("[playit] เชื่อมบัญชีแล้วแต่ยังไม่มี tunnel — "
                        f"สร้าง tunnel แบบ Minecraft Java ที่ {tunnel.TUNNELS_PAGE} "
                        f"ให้ชี้มาที่พอร์ต {self.settings.port}")

    def _wait_until_down(self) -> None:
        while self.server and self.server.is_alive:
            self._state_event.wait(timeout=1.0)
            self._state_event.clear()
        if self.agent:
            self.agent.stop()
        if self._last_state is State.CRASHED and not self._stop_requested:
            self.on_status("เซิร์ฟเวอร์ดับกลางคัน")
            self.on_log("[launcher] เซิร์ฟเวอร์หยุดทำงานเอง ดูสาเหตุได้ในบันทึกด้านบน")
        else:
            self.on_status("ปิดเซิร์ฟเวอร์แล้ว")

    # ------------------------------------------------------------ auto-heal
    def _heal(self) -> bool:
        """Diagnose the crash and disable the culprit. False = give up."""
        assert self.server is not None
        if self.server_pack:
            self.on_status("เซิร์ฟเวอร์พังทั้งที่ใช้ server pack ทางการ")
            self.on_log("[วิเคราะห์] ม็อดชุดนี้มาจาก server pack ที่คนทำแพ็คทดสอบแล้ว "
                        "จะไม่ปิดม็อดเอง — ดูสาเหตุจริงในบันทึกด้านบน")
            return False
        self.on_status("เซิร์ฟเวอร์พัง — กำลังหาว่าม็อดตัวไหนเป็นต้นเหตุ …")
        text = "\n".join(self.server.recent[-400:])
        text += "\n" + self.server.latest_log()[-200_000:]
        text += "\n" + self.server.latest_crash_report()[:200_000]

        server_mods = self.server_dir / "mods"
        instance_mods = self.instance.path / "mods"
        index = autoheal.build_index(
            [server_mods, instance_mods, self.server_dir / "mods-disabled"],
            self.instance.slug)
        present = {j.name for j in server_mods.glob("*.jar")}
        state = sync.load_state(self.instance.slug)
        diag = autoheal.diagnose(text, index, present,
                                 protected=state.get("force_include", {}))
        self.on_log(f"[วิเคราะห์] {diag.summary}")
        for c in diag.culprits[:3]:
            self.on_log(f"[วิเคราะห์]   ผู้ต้องสงสัย {c.confidence}: {c.jar} — {c.reason}")

        if diag.environment:
            # Not the mods' fault. Retry once - the orphan check runs on every
            # start and clears the commonest case, a stale world lock - then
            # leave it to the user rather than gutting the pack.
            self.on_status(diag.environment)
            self._env_retries += 1
            return self._env_retries <= 1

        if not diag.culprits and not diag.restore:
            self.on_log("[วิเคราะห์] หาต้นเหตุอัตโนมัติไม่ได้ หยุดการแก้เองไว้ก่อน")
            return False

        disabled, restored = autoheal.apply(
            self.server_dir, self.instance.slug, diag, instance_mods)
        for jar in restored:
            self.on_log(f"[แก้ไข] เอา {jar} กลับเข้าเซิร์ฟเวอร์")
        for jar in disabled:
            reason = next((c.reason for c in diag.culprits if c.jar == jar), "")
            self.on_log(f"[แก้ไข] ปิดม็อด {jar} — {reason}")
        if not disabled and not restored:
            self.on_log("[แก้ไข] ไม่มีอะไรให้แก้เพิ่มแล้ว")
            return False
        return True

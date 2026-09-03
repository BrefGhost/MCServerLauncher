"""Headless runner - same engine as the window, for testing or a shortcut.

    python run_headless.py --list
    python run_headless.py "Contained Opolis" --ram 8 --no-tunnel
    python run_headless.py "Contained Opolis" --prepare-only
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher import instances as inst_mod
from launcher.config import PackSettings, Settings
from launcher.session import Session


for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def log(line: str) -> None:
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="เปิดเซิร์ฟเวอร์ Minecraft modpack")
    ap.add_argument("pack", nargs="?", help="ชื่อ modpack (บางส่วนก็ได้)")
    ap.add_argument("--list", action="store_true", help="ดูรายชื่อ modpack")
    ap.add_argument("--ram", type=int, default=0, help="แรม (GB)")
    ap.add_argument("--no-tunnel", action="store_true", help="ไม่เปิดให้ต่อจากข้างนอก")
    ap.add_argument("--prepare-only", action="store_true",
                    help="ติดตั้งและคัดลอกม็อดอย่างเดียว ไม่เปิดเซิร์ฟเวอร์")
    ap.add_argument("--accept-eula", action="store_true",
                    help="ยอมรับ Minecraft EULA (https://aka.ms/MinecraftEULA)")
    args = ap.parse_args()

    found = inst_mod.scan()
    if args.list or not args.pack:
        for i in found:
            print(f"{i.name}\n    Minecraft {i.mc_version} · {i.loader_label} · "
                  f"ม็อด {i.mods_count} ตัว")
        return 0

    needle = args.pack.lower()
    inst = next((i for i in found if needle in i.name.lower()), None)
    if inst is None:
        print(f"ไม่พบ modpack ที่ชื่อคล้าย '{args.pack}'")
        return 1

    settings = Settings.load()
    ps: PackSettings = settings.pack(inst.name)
    if args.ram:
        ps.ram_gb = args.ram
    if args.no_tunnel:
        ps.use_tunnel = False

    session = Session(
        instance=inst, settings=ps,
        eula_accepted=args.accept_eula or settings.eula_accepted,
        on_log=log,
        on_status=lambda s: log(f"== {s}"),
        on_state=lambda s: log(f"[state] {s}"),
        on_address=lambda a: log(f"[ที่อยู่] {a}"),
        on_players=lambda p: log(f"[ผู้เล่น] {', '.join(sorted(p)) or 'ไม่มี'}"))

    if args.prepare_only:
        session._prepare()                       # noqa: SLF001 - test entry point
        print("เตรียมเซิร์ฟเวอร์เสร็จแล้ว:", session.server_dir)
        return 0

    session.start()
    try:
        while session.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nกำลังปิดเซิร์ฟเวอร์ …")
        session.request_stop()
        while session.running:
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

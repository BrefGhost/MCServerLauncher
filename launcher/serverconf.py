"""Write eula.txt, server.properties and the JVM argument list."""
from __future__ import annotations

import json
from pathlib import Path

from .config import AIKAR_FLAGS, PackSettings, aikar_region_flags


def write_eula(server_dir: Path, accepted: bool) -> None:
    """Only ever written after the user ticks the box in the UI."""
    if not accepted:
        return
    server_dir.mkdir(parents=True, exist_ok=True)
    (server_dir / "eula.txt").write_text(
        "# ผู้ใช้ยอมรับ Minecraft EULA (https://aka.ms/MinecraftEULA) ผ่านหน้าโปรแกรม\n"
        "eula=true\n", encoding="utf-8")


def read_properties(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    if not path.exists():
        return props
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        props[k.strip()] = v.strip()
    return props


def write_properties(server_dir: Path, ps: PackSettings, pack_name: str) -> None:
    """Merge our settings into server.properties, keeping keys we don't manage."""
    path = server_dir / "server.properties"
    props = read_properties(path)
    props.update({
        "server-port": str(ps.port),
        "max-players": str(ps.max_players),
        "difficulty": ps.difficulty,
        "motd": ps.motd or f"{pack_name} - เซิร์ฟของเรา",
        "online-mode": "true" if ps.online_mode else "false",
        "pvp": "true" if ps.pvp else "false",
        "view-distance": str(ps.view_distance),
        "simulation-distance": str(ps.simulation_distance),
        "allow-flight": "true" if ps.allow_flight else "false",
        "spawn-protection": "0",
        "enable-command-block": "true",
        "sync-chunk-writes": "false",   # big win on Windows with heavy packs
    })
    if ps.level_seed:
        props["level-seed"] = ps.level_seed
    props.setdefault("level-name", "world")
    props.setdefault("allow-nether", "true")
    props.setdefault("white-list", "false")

    server_dir.mkdir(parents=True, exist_ok=True)
    lines = ["#Minecraft server properties",
             f"#เขียนโดย MC Server Launcher สำหรับ {pack_name}"]
    lines += [f"{k}={v}" for k, v in sorted(props.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_ops(server_dir: Path, names: list[str]) -> None:
    """Seed ops.json by name; the server fills in the UUIDs on first join."""
    if not names:
        return
    entries = [{"uuid": "00000000-0000-0000-0000-000000000000", "name": n,
                "level": 4, "bypassesPlayerLimit": True} for n in names if n.strip()]
    (server_dir / "ops.json").write_text(
        json.dumps(entries, indent=2), encoding="utf-8")


def relax_proxy_filters(server_dir: Path, log=None) -> list[str]:
    """Stop pack mods from treating the tunnel as an attacker.

    The Connectivity mod (shipped by most large packs) drops traffic from any
    address not in its `proxywhitelist`, which is empty by default. Behind
    playit every player arrives from a 127.x address the tunnel makes up, so
    the filter silently stalls logins until the client gives up - a player just
    sees "Logging in..." forever, and nothing is written to the server log.

    The whitelist is compared by exact string, and the made-up address differs
    per player, so listing addresses cannot work; the filter has to be off.
    Turning it off leaves the server exactly as it would be without the mod.
    """
    changed: list[str] = []
    path = server_dir / "config" / "connectivity.json"
    if not path.is_file():
        return changed
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        section = data.get("malformedtraffic")
        if isinstance(section, dict) and section.get("enabled"):
            backup = path.with_suffix(".json.bak")
            if not backup.exists():
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            section["enabled"] = False
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            changed.append("connectivity: ปิดตัวกรอง traffic ที่บล็อก IP ของ tunnel")
    except (OSError, ValueError):
        return changed

    if log and changed:
        for item in changed:
            log(f"ปรับค่าเซิร์ฟเวอร์ — {item}")
    return changed


def jvm_args(ram_gb: int) -> list[str]:
    xms = max(1, ram_gb // 2)
    return [f"-Xms{xms}G", f"-Xmx{ram_gb}G",
            *AIKAR_FLAGS, *aikar_region_flags(ram_gb),
            "-Dfile.encoding=UTF-8",
            # Plain text console: colour codes only get in the way of reading
            # the log back for crash analysis.
            "-Dterminal.jline=false", "-Dterminal.ansi=false"]


def write_jvm_args_file(server_dir: Path, ram_gb: int) -> None:
    """Keep run.bat in sync with the UI, so the folder also works standalone."""
    (server_dir / "user_jvm_args.txt").write_text(
        "# เขียนโดย MC Server Launcher\n" + "\n".join(jvm_args(ram_gb)) + "\n",
        encoding="utf-8")

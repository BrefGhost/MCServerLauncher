"""Paths, constants and persisted settings for MC Server Launcher."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

APP_NAME = "MC Server Launcher"
APP_VERSION = "1.0.1"

# Root of the launcher installation.
#
# Frozen into an exe, this module lives in a temporary folder that Windows
# deletes on exit - servers and worlds written there would vanish every run.
# Next to the exe is where the user expects their files, so that is the root.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
CACHE_DIR = APP_DIR / "cache"
SERVERS_DIR = APP_DIR / "servers"
LOGS_DIR = APP_DIR / "logs"

SETTINGS_FILE = DATA_DIR / "settings.json"
PLAYIT_SECRET_FILE = DATA_DIR / "playit_secret.txt"

# playit.gg agent, pinned to 0.17.1: the last release that can be driven from
# a script at all. The 1.0.x exe is a daemon that waits for a GUI frontend over
# IPC. See tunnel.py for what 0.17.1 can and cannot do.
PLAYIT_VERSION = "v0.17.1"
PLAYIT_URL = (
    "https://github.com/playit-cloud/playit-agent/releases/download/"
    f"{PLAYIT_VERSION}/playit-windows-x86_64-signed.exe"
)
PLAYIT_SHA256 = "9b00d6ff7d37d1052e5ae097e1348e11deae8617cd7a8ba39d1777f2006316a3"
PLAYIT_EXE = CACHE_DIR / f"playit-{PLAYIT_VERSION}.exe"

FORGE_INSTALLER_URL = (
    "https://maven.minecraftforge.net/net/minecraftforge/forge/"
    "{mc}-{ver}/forge-{mc}-{ver}-installer.jar"
)
NEOFORGE_INSTALLER_URL = (
    "https://maven.neoforged.net/releases/net/neoforged/neoforge/"
    "{ver}/neoforge-{ver}-installer.jar"
)

DEFAULT_INSTANCE_DIRS = [
    Path(os.path.expanduser("~")) / "curseforge" / "minecraft" / "Instances",
    Path(os.environ.get("APPDATA", "")) / ".minecraft" / "instances",
]

# Aikar's flags - the community standard for Minecraft server GC tuning.
# Source: https://mcflags.emc.gs
AIKAR_FLAGS = [
    "-XX:+UseG1GC",
    "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=200",
    "-XX:+UnlockExperimentalVMOptions",
    "-XX:+DisableExplicitGC",
    "-XX:+AlwaysPreTouch",
    "-XX:G1HeapWastePercent=5",
    "-XX:G1MixedGCCountTarget=4",
    "-XX:G1MixedGCLiveThresholdPercent=90",
    "-XX:G1RSetUpdatingPauseTimePercent=5",
    "-XX:SurvivorRatio=32",
    "-XX:+PerfDisableSharedMem",
    "-XX:MaxTenuringThreshold=1",
    "-Dusing.aikars.flags=https://mcflags.emc.gs",
    "-Daikars.new.flags=true",
]


def aikar_region_flags(ram_gb: int) -> list[str]:
    """Region/occupancy flags differ above and below 12GB heap (Aikar's guide)."""
    if ram_gb >= 12:
        return ["-XX:G1NewSizePercent=40", "-XX:G1MaxNewSizePercent=50",
                "-XX:G1HeapRegionSize=16M", "-XX:G1ReservePercent=15",
                "-XX:InitiatingHeapOccupancyPercent=20"]
    return ["-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40",
            "-XX:G1HeapRegionSize=8M", "-XX:G1ReservePercent=20",
            "-XX:InitiatingHeapOccupancyPercent=15"]


@dataclass
class PackSettings:
    """Per-modpack server settings."""
    ram_gb: int = 8
    max_players: int = 8
    difficulty: str = "normal"
    motd: str = ""
    online_mode: bool = True
    pvp: bool = True
    view_distance: int = 8
    simulation_distance: int = 6
    allow_flight: bool = True
    port: int = 25565
    use_tunnel: bool = True
    # playit's CLI cannot report the public address (see tunnel.py), so it is
    # copied from playit.gg once and remembered here.
    tunnel_address: str = ""
    level_seed: str = ""
    ops: list[str] = field(default_factory=list)


@dataclass
class Settings:
    eula_accepted: bool = False
    instance_dirs: list[str] = field(default_factory=list)
    last_pack: str = ""
    packs: dict = field(default_factory=dict)  # pack name -> PackSettings dict

    @classmethod
    def load(cls) -> "Settings":
        if SETTINGS_FILE.exists():
            try:
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                return cls(**{k: v for k, v in raw.items()
                              if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def pack(self, name: str) -> PackSettings:
        raw = self.packs.get(name, {})
        return PackSettings(**{k: v for k, v in raw.items()
                               if k in PackSettings.__dataclass_fields__})

    def set_pack(self, name: str, ps: PackSettings) -> None:
        self.packs[name] = asdict(ps)


def ensure_dirs() -> None:
    for d in (DATA_DIR, CACHE_DIR, SERVERS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)

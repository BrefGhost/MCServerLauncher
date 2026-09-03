"""Discover CurseForge / MultiMC style modpack instances on disk."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .config import DEFAULT_INSTANCE_DIRS


@dataclass
class Instance:
    name: str
    path: Path
    mc_version: str
    loader: str          # "forge" | "neoforge" | "fabric" | "quilt" | "vanilla"
    loader_version: str
    mods_count: int
    recommended_ram: int  # in MB, 0 if unknown
    # CurseForge ids. When the pack author published a server pack, CurseForge
    # records its file id here at install time - that pack is the authors' own
    # server build and beats anything we could derive from the client folder.
    project_id: int = 0
    server_pack_file_id: int = 0

    @property
    def has_server_pack(self) -> bool:
        return bool(self.project_id and self.server_pack_file_id)

    @property
    def slug(self) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", self.name).strip("_") or "pack"

    @property
    def loader_label(self) -> str:
        return f"{self.loader.capitalize()} {self.loader_version}"


def _parse_loader_id(loader_id: str) -> tuple[str, str]:
    """'forge-47.4.18' -> ('forge', '47.4.18'); 'neoforge-21.1.247' -> (...)"""
    if not loader_id:
        return "vanilla", ""
    for name in ("neoforge", "forge", "fabric", "quilt"):
        if loader_id.startswith(name + "-"):
            return name, loader_id[len(name) + 1:]
    if "-" in loader_id:
        a, b = loader_id.split("-", 1)
        return a.lower(), b
    return loader_id.lower(), ""


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _load_mmc(folder: Path) -> tuple[str, str, str] | None:
    """MultiMC / Prism keep the versions in mmc-pack.json instead."""
    data = _read_json(folder / "mmc-pack.json")
    if not data:
        return None
    uid_to_loader = {"net.minecraftforge": "forge", "net.neoforged": "neoforge",
                     "net.fabricmc.fabric-loader": "fabric",
                     "org.quiltmc.quilt-loader": "quilt"}
    mc_version, loader, loader_version = "", "vanilla", ""
    for component in data.get("components") or []:
        uid = component.get("uid", "")
        if uid == "net.minecraft":
            mc_version = component.get("version", "")
        elif uid in uid_to_loader:
            loader = uid_to_loader[uid]
            loader_version = component.get("version", "")
    return (mc_version, loader, loader_version) if mc_version else None


def load_instance(folder: Path) -> Instance | None:
    """Read one instance folder. Returns None if it doesn't look like a modpack."""
    manifest = _read_json(folder / "manifest.json") or {}
    mci = _read_json(folder / "minecraftinstance.json") or {}
    if not manifest and not mci:
        mmc = _load_mmc(folder)
        if not mmc:
            return None
        # Prism keeps the game files one level down.
        game_dir = next((folder / d for d in (".minecraft", "minecraft")
                         if (folder / d).is_dir()), folder)
        mods = game_dir / "mods"
        return Instance(name=folder.name, path=game_dir, mc_version=mmc[0],
                        loader=mmc[1], loader_version=mmc[2],
                        mods_count=len(list(mods.glob("*.jar"))) if mods.is_dir() else 0,
                        recommended_ram=0)

    name = manifest.get("name") or mci.get("name") or folder.name
    # CurseForge's own display name lives in minecraftinstance.json and is the
    # one the user sees in the launcher, so prefer it.
    if mci.get("name"):
        name = mci["name"]

    mc_version = ""
    loader, loader_version = "vanilla", ""

    mcblock = manifest.get("minecraft") or {}
    if mcblock:
        mc_version = mcblock.get("version", "")
        loaders = mcblock.get("modLoaders") or []
        primary = next((l for l in loaders if l.get("primary")), loaders[0] if loaders else None)
        if primary:
            loader, loader_version = _parse_loader_id(primary.get("id", ""))

    base = mci.get("baseModLoader") or {}
    if base:
        mc_version = base.get("minecraftVersion") or mc_version
        if base.get("name"):
            loader, loader_version = _parse_loader_id(base["name"])
    mc_version = mc_version or mci.get("gameVersion", "")

    mods_dir = folder / "mods"
    mods_count = len(list(mods_dir.glob("*.jar"))) if mods_dir.is_dir() else 0

    ram = mcblock.get("recommendedRam") or 0
    try:
        ram = int(ram)
    except (TypeError, ValueError):
        ram = 0

    def _int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    installed_file = (mci.get("installedModpack") or {}).get("installedFile") or {}
    return Instance(name=name, path=folder, mc_version=mc_version, loader=loader,
                    loader_version=loader_version, mods_count=mods_count,
                    recommended_ram=ram,
                    project_id=_int(mci.get("projectID")),
                    server_pack_file_id=_int(
                        installed_file.get("serverPackFileId")))


def looks_like_instance(folder: Path) -> bool:
    return ((folder / "minecraftinstance.json").is_file()
            or (folder / "manifest.json").is_file()
            or (folder / "mmc-pack.json").is_file())


def scan(extra_dirs: list[str] | None = None,
         include_defaults: bool = True) -> list[Instance]:
    """Find modpacks under every known root.

    A folder the user picked may be the modpack itself or the folder holding
    several of them, so both are accepted - guessing wrong would mean their
    pack simply never appears, with nothing on screen to explain why.
    """
    roots = [Path(d) for d in (extra_dirs or [])]
    if include_defaults:
        roots += list(DEFAULT_INSTANCE_DIRS)

    found: list[Instance] = []
    seen: set[Path] = set()

    def add(folder: Path) -> bool:
        resolved = folder.resolve()
        if resolved in seen:
            return True
        inst = load_instance(folder)
        if inst:
            seen.add(resolved)
            found.append(inst)
            return True
        return False

    for root in roots:
        if not root.is_dir():
            continue
        if looks_like_instance(root) and add(root):
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir():
                add(child)
    return found

"""Work out which mod killed the server, and take it out of the mods folder.

No metadata reliably marks a Forge mod as client-only, so the first launch of a
pack usually dies once or twice on a mod that has no business being on a server.
This reads the crash report and the log, names the culprit, moves its jar to
`mods-disabled/`, and lets the caller try again.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import modmeta
from .config import DATA_DIR
from .sync import load_state, save_state

MAX_DISABLED = 40          # refuse to gut the pack if something else is wrong
CERTAIN = 99               # confidence at which we act on every hit at once

# A jar name only accuses its mod when a "Failure message" follows it. On its
# own, "Mod File:" also appears in ordinary warnings about unrelated mods.
RE_MOD_FILE = re.compile(
    r"Mod [Ff]ile:\s*(?:.*[\\/])?(\S+\.jar)\s*\n\s*Failure message:")
RE_FAILURE = re.compile(r"Failure message:\s*(.+)")
# "Failed to create mod instance. ModID: reforgium, class link.infra..." - the
# id is followed by a comma, so \S+ would swallow it and match nothing.
RE_MOD_INSTANCE = re.compile(
    r"Failed to create mod instance\.\s*ModID:\s*([A-Za-z0-9_.-]+)")
RE_MIXIN_MOD = re.compile(r"[Mm]ixin apply for mod ([A-Za-z0-9_.-]+) failed")
RE_MIXIN_CONFIG = re.compile(r"mixins?\.([A-Za-z0-9_]+)\.json")
# Forge phrasing.
RE_MISSING_DEP = re.compile(
    r"Mod ID:\s*'([^']+)',\s*Requested by:\s*'([^']+)'")
# NeoForge phrasing: "Mod ae2 requires guideme 21.1.1 or above /
#                     Currently, guideme is not installed"
RE_MISSING_DEP_NEO = re.compile(
    r"Mod ([A-Za-z0-9_.-]+) requires ([A-Za-z0-9_.-]+)[^\n]*\n\s*"
    r"Currently, \2 is not installed")
# The dependency is present but the wrong version: "Mod continuity requires
# fabric_api / Currently, fabric_api is 0.92.2+1.11.12+1.20.1". Here the pack's
# own version is the one to keep, so the mod that refuses it is the odd one out.
RE_VERSION_MISMATCH = re.compile(
    r"Mod ([A-Za-z0-9_.-]+) requires ([A-Za-z0-9_.-]+)[^\n]*\n\s*"
    r"Currently, \2 is (?!not installed)\S+")
# "- Collapsible Groups (collapsible_groups) has failed to load correctly"
RE_FAILED_LOAD = re.compile(
    r"\(([A-Za-z0-9_.-]+)\) has failed to load correctly")
# The loader's own verdict that a mod is client-only. Nothing is more certain.
RE_INVALID_DIST = re.compile(
    r"for invalid dist DEDICATED_SERVER|Attempted to load class net/minecraft/client")
# Some mods say it themselves and then carry on half-broken instead of crashing:
# "[BetterThanLlamas/]: You are loading Better Than Llamas on a server.
#  Better Than Llamas is a client only mod!"
RE_SELF_DECLARED_CLIENT = re.compile(
    r"[^\n]*?(?:is a client[ -]only mod|is client[ -]side only"
    r"|should not be (?:installed|loaded|used) on (?:a |the )?server)[^\n]*", re.I)
RE_STACK_PKG = re.compile(r"\bat ([a-z][a-z0-9_]*(?:\.[a-z0-9_]+){1,3})\.[A-Z]")
RE_CLIENT_CLASS = re.compile(
    r"net[./]minecraft[./]client[./]|net\.minecraft\.client\.|"
    r"com[./]mojang[./]blaze3d|Cannot load class net\.minecraft\.client")

# Failures that have nothing to do with the mods - disabling one would only
# make the pack worse while the real cause stayed put.
ENVIRONMENT_FAULTS = [
    (r"another process has locked a portion of the file|DirectoryLock",
     "โลกถูกล็อกอยู่ — มีเซิร์ฟเวอร์ตัวเก่าค้างอยู่ ต้องปิดก่อน"),
    (r"java\.net\.BindException|Address already in use",
     "พอร์ตถูกใช้อยู่แล้ว — มีเซิร์ฟเวอร์อื่นเปิดพอร์ตเดียวกันอยู่"),
    (r"java\.lang\.OutOfMemoryError",
     "แรมไม่พอ — เพิ่มแรมที่ให้เซิร์ฟเวอร์แล้วลองใหม่"),
    (r"UnsupportedClassVersionError",
     "Java เวอร์ชันไม่ตรงกับที่ modpack ต้องการ"),
    (r"No space left on device|There is not enough space on the disk",
     "พื้นที่ดิสก์ไม่พอ"),
]

# Packages that belong to Minecraft/the loader, never to a mod we could remove.
IGNORED_PKGS = ("net.minecraft", "net.minecraftforge", "net.neoforged",
                "cpw.mods", "java.", "javax.", "jdk.", "sun.", "org.spongepowered",
                "com.mojang", "org.apache", "io.netty", "org.objectweb")


@dataclass
class Culprit:
    jar: str
    reason: str
    confidence: int      # higher wins


@dataclass
class Diagnosis:
    culprits: list[Culprit]
    restore: list[str]           # jars to put back (we removed a needed dep)
    client_side_evidence: bool
    summary: str
    environment: str = ""        # set when the fault is not a mod at all


# --------------------------------------------------------------------- index
def build_index(mods_dirs: list[Path], slug: str) -> dict:
    """Map mod ids and java packages to jar filenames, cached on disk.

    Indexes the instance's full mod list, not just what is on the server, so a
    missing-dependency error can name a jar the client-side filter removed.
    """
    cache_file = DATA_DIR / f"index-{slug}.json"
    INDEX_VERSION = 5          # bump when the parsing rules change
    jars: dict[str, Path] = {}
    for d in mods_dirs:
        if d.is_dir():
            for j in sorted(d.glob("*.jar")):
                jars.setdefault(j.name, j)
    signature = {name: p.stat().st_size for name, p in jars.items()}
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if (cached.get("signature") == signature
                    and cached.get("version") == INDEX_VERSION):
                return cached
        except Exception:
            pass

    by_modid: dict[str, str] = {}
    by_name: dict[str, str] = {}
    by_pkg: dict[str, str] = {}
    for jar in jars.values():
        info = modmeta.inspect(jar)
        for mid in info.mod_ids:
            by_modid.setdefault(mid.lower(), jar.name)
        if info.display_name:
            by_name.setdefault(info.display_name.strip().lower(), jar.name)
        try:
            with zipfile.ZipFile(jar) as z:
                pkgs = set()
                for entry in z.namelist():
                    if not entry.endswith(".class") or entry.startswith("META-INF"):
                        continue
                    parts = entry.split("/")
                    if len(parts) >= 3:
                        pkgs.add(".".join(parts[:3]))
                    elif len(parts) >= 2:
                        pkgs.add(".".join(parts[:2]))
                for p in pkgs:
                    if not p.startswith(IGNORED_PKGS):
                        by_pkg.setdefault(p, jar.name)
        except Exception:
            pass

    index = {"version": INDEX_VERSION, "signature": signature,
             "by_modid": by_modid, "by_name": by_name, "by_pkg": by_pkg}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index


def _jar_for_modid(index: dict, mod_id: str) -> str | None:
    return index.get("by_modid", {}).get(mod_id.lower())


def resolve_mod(index: dict, text: str) -> str | None:
    """Find a jar from whatever the game's error screen showed.

    The disconnect screen lists display names ("Wakes"), the logs list mod ids
    ("wakes"), and a user might paste the jar filename; accept all three.
    """
    low = text.strip().lower()
    if not low:
        return None
    if low.endswith(".jar"):
        for name in index.get("signature", {}):
            if name.lower() == low:
                return name
    for table in ("by_name", "by_modid"):
        hit = index.get(table, {}).get(low)
        if hit:
            return hit
    # Last resort: a name that differs only by spacing or punctuation.
    squashed = re.sub(r"[^a-z0-9]", "", low)
    if squashed:
        for table in ("by_name", "by_modid"):
            for key, jar in index.get(table, {}).items():
                if re.sub(r"[^a-z0-9]", "", key) == squashed:
                    return jar
    return None


def _jar_for_package(index: dict, pkg: str) -> str | None:
    by_pkg = index.get("by_pkg", {})
    parts = pkg.split(".")
    for n in (3, 2):
        key = ".".join(parts[:n])
        if key in by_pkg:
            return by_pkg[key]
    return None


# ----------------------------------------------------------------- diagnosis
def diagnose(text: str, index: dict, present: Iterable[str],
             protected: Iterable[str] = ()) -> Diagnosis:
    """Rank the mods that could have caused this failure.

    `present` is the set of jars currently in the server's mods folder; a mod
    named in the log that isn't present is a candidate for putting back.
    `protected` are jars we already put back once. Blaming them on a guess
    would start a disable/restore loop, so they are only accused when the
    loader itself convicts them (CERTAIN) - that verdict is never a guess.
    """
    present = set(present)
    protected = set(protected)
    for pattern, message in ENVIRONMENT_FAULTS:
        if re.search(pattern, text):
            return Diagnosis(culprits=[], restore=[], client_side_evidence=False,
                             summary=message, environment=message)

    scores: dict[str, Culprit] = {}
    restore: list[str] = []

    def add(jar: str | None, reason: str, confidence: int) -> None:
        if not jar or jar not in present:
            return
        if jar in protected and confidence < CERTAIN:
            return
        cur = scores.get(jar)
        if cur is None or confidence > cur.confidence:
            scores[jar] = Culprit(jar=jar, reason=reason, confidence=confidence)

    client_evidence = bool(RE_CLIENT_CLASS.search(text))

    # 1. Forge names the jar outright in its loading-error summary.
    for jar in RE_MOD_FILE.findall(text):
        add(jar, "Forge ชี้ว่าไฟล์นี้โหลดไม่สำเร็จ", 96)

    # 2. A dependency we disabled earlier is now missing: put it back and
    #    disable whatever asked for it instead.
    missing = RE_MISSING_DEP.findall(text) + [
        (needed, requester) for requester, needed in RE_MISSING_DEP_NEO.findall(text)]
    for needed, requester in missing:
        needed_jar = _jar_for_modid(index, needed)
        req_jar = _jar_for_modid(index, requester)
        if needed_jar and needed_jar not in present:
            # We took out something another mod genuinely needs - put it back
            # rather than pulling the dependent mod out too.
            restore.append(needed_jar)
        elif needed_jar is None and req_jar:
            add(req_jar, f"ต้องการม็อด '{needed}' ที่ไม่มีในแพ็คนี้", 70)

    for requester, needed in RE_VERSION_MISMATCH.findall(text):
        add(_jar_for_modid(index, requester),
            f"ต้องการ '{needed}' คนละเวอร์ชันกับที่แพ็คนี้ใช้", 94)

    # 3. "<Name> (<modid>) has failed to load correctly" - if the reason under
    #    it is a client class on a dedicated server, the verdict is certain and
    #    every such mod can go in one round instead of one per restart.
    for m in RE_FAILED_LOAD.finditer(text):
        mod_id = m.group(1)
        body = text[m.end():m.end() + 400]
        if RE_INVALID_DIST.search(body):
            add(_jar_for_modid(index, mod_id),
                f"'{mod_id}' เรียกโค้ดฝั่ง client บนเซิร์ฟเวอร์", CERTAIN)
        else:
            add(_jar_for_modid(index, mod_id), f"ม็อด '{mod_id}' โหลดไม่สำเร็จ", 92)

    # 3b. A mod that announced "I am client only" on its own logger. It may not
    #     have crashed anything yet, but it has no business being here.
    for line in RE_SELF_DECLARED_CLIENT.findall(text):
        for token in re.findall(r"[\[/]([A-Za-z0-9_.]{3,})[/\]]", line):
            jar = _jar_for_modid(index, token)
            if jar:
                add(jar, "ม็อดบอกเองว่าเป็นของฝั่งผู้เล่นล้วน ๆ", CERTAIN)
                break

    # 4. Explicit mod-instance and mixin failures.
    for mid in RE_MOD_INSTANCE.findall(text):
        add(_jar_for_modid(index, mid), f"สร้างอินสแตนซ์ของม็อด '{mid}' ไม่สำเร็จ", 90)
    for mid in RE_MIXIN_MOD.findall(text):
        add(_jar_for_modid(index, mid), f"mixin ของม็อด '{mid}' ล้มเหลว", 85)
    for mid in RE_MIXIN_CONFIG.findall(text):
        add(_jar_for_modid(index, mid), f"mixin config '{mid}' ล้มเหลว", 60)

    # 5. Fall back to blaming the topmost mod package in the stack trace.
    if client_evidence or not scores:
        for pkg in RE_STACK_PKG.findall(text):
            if pkg.startswith(IGNORED_PKGS):
                continue
            jar = _jar_for_package(index, pkg)
            if jar:
                add(jar, f"stack trace ชี้มาที่โค้ดของม็อดนี้ ({pkg})",
                    55 if client_evidence else 40)
                break

    restore = list(dict.fromkeys(restore))
    ranked = sorted(scores.values(), key=lambda c: -c.confidence)
    if restore:
        summary = ("มีม็อดที่ตัวอื่นต้องพึ่งถูกคัดออกไป — เอากลับเข้าไป: "
                   + ", ".join(restore))
    elif not ranked:
        summary = "วิเคราะห์ไม่ออกว่าม็อดตัวไหนทำให้พัง"
    elif client_evidence:
        summary = f"เจอโค้ดฝั่ง client ทำงานบนเซิร์ฟเวอร์ — ต้นเหตุน่าจะเป็น {ranked[0].jar}"
    else:
        summary = f"ต้นเหตุน่าจะเป็น {ranked[0].jar}"
    return Diagnosis(culprits=ranked, restore=restore,
                     client_side_evidence=client_evidence, summary=summary)


# ------------------------------------------------------------------- healing
def apply(server_dir: Path, slug: str, diagnosis: Diagnosis,
          instance_mods: Path | None = None) -> tuple[list[str], list[str]]:
    """Disable the prime suspect (and restore anything we wrongly removed).

    Returns (disabled_now, restored_now).
    """
    state = load_state(slug)
    disabled: dict = state.setdefault("disabled", {})
    force_include: dict = state.setdefault("force_include", {})
    mods_dir = server_dir / "mods"
    parked = server_dir / "mods-disabled"
    parked.mkdir(parents=True, exist_ok=True)

    # A mod the loader convicted of running client code on a server can never
    # come back, whatever depends on it - putting it back only loops.
    convicted: dict = state.setdefault("convicted", {})

    restored: list[str] = []
    for jar in diagnosis.restore:
        dst = mods_dir / jar
        if dst.exists() or jar in convicted:
            continue
        src = parked / jar
        if src.exists():
            shutil.move(str(src), str(dst))
        elif instance_mods and (instance_mods / jar).exists():
            # Filtered out as client-side, but a server mod depends on it.
            try:
                os.link(instance_mods / jar, dst)
            except OSError:
                shutil.copy2(instance_mods / jar, dst)
        else:
            continue
        disabled.pop(jar, None)
        force_include[jar] = "มีม็อดอื่นต้องพึ่งไฟล์นี้"
        restored.append(jar)

    disabled_now: list[str] = []
    # Putting a missing dependency back is a complete fix on its own; pulling a
    # mod out in the same round would blame the wrong one (AE2 for GuideME).
    if restored:
        save_state(slug, state)
        return disabled_now, restored

    # When the loader itself said "client class on a dedicated server" we can
    # take out every mod it named at once; otherwise only the prime suspect,
    # so a wrong guess costs one restart rather than half the pack.
    certain = [c for c in diagnosis.culprits if c.confidence >= CERTAIN]
    batch = certain or diagnosis.culprits[:1]

    for culprit in batch:
        if len(disabled) >= MAX_DISABLED:
            break
        src = mods_dir / culprit.jar
        if not src.exists():
            continue
        shutil.move(str(src), str(parked / culprit.jar))
        disabled[culprit.jar] = culprit.reason
        disabled_now.append(culprit.jar)
        if culprit.confidence >= CERTAIN:
            # Overrules any earlier decision to keep this jar around.
            convicted[culprit.jar] = culprit.reason
            force_include.pop(culprit.jar, None)

    save_state(slug, state)
    return disabled_now, restored


def prefix_of(jar_name: str) -> str:
    """Turn 'oculus-mc1.20.1-1.8.0.jar' into a version-agnostic prefix."""
    stem = jar_name[:-4] if jar_name.lower().endswith(".jar") else jar_name
    # Stop at the first separator that is followed by a version or loader tag,
    # keeping that separator so the prefix matches the jar exactly.
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_'\[\]. -]*?[-_])(?=v?\d|mc\d|forge|neoforge)",
                 stem, re.I)
    return m.group(1) if m else stem


def force_include(server_dir: Path, slug: str, instance_mods: Path,
                  names: Iterable[str]) -> tuple[list[str], list[str]]:
    """Put named mods back on the server for good, whatever the filters think.

    Used for the one case nothing can predict: the game says the server is
    missing a mod, and the player pastes that name in. Returns (added, unknown).
    """
    index = build_index([server_dir / "mods", instance_mods,
                         server_dir / "mods-disabled"], slug)
    state = load_state(slug)
    disabled: dict = state.setdefault("disabled", {})
    forced: dict = state.setdefault("force_include", {})
    mods_dir = server_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)

    added: list[str] = []
    unknown: list[str] = []
    for raw in names:
        jar = resolve_mod(index, raw)
        if not jar:
            unknown.append(raw.strip())
            continue
        disabled.pop(jar, None)
        forced[jar] = "ผู้ใช้สั่งให้เก็บไว้ (เกมแจ้งว่าเซิร์ฟเวอร์ขาดม็อดนี้)"
        dst = mods_dir / jar
        if not dst.exists():
            for src in (server_dir / "mods-disabled" / jar, instance_mods / jar):
                if src.exists():
                    try:
                        os.link(src, dst)
                    except OSError:
                        shutil.copy2(src, dst)
                    break
        added.append(jar)

    save_state(slug, state)
    return added, unknown


def reset_disabled(server_dir: Path, slug: str) -> int:
    """Put every auto-disabled mod back (used by the 'ลองใหม่ทั้งหมด' button)."""
    state = load_state(slug)
    disabled: dict = state.get("disabled", {})
    parked = server_dir / "mods-disabled"
    count = 0
    for jar in list(disabled):
        src = parked / jar
        if src.exists():
            shutil.move(str(src), str(server_dir / "mods" / jar))
            count += 1
    state["disabled"] = {}
    save_state(slug, state)
    return count


_prefix_of = prefix_of      # older name, still used by the tests

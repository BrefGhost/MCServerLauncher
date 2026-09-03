"""Check the crash analyser against the shapes Forge/NeoForge actually print."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from launcher.autoheal import (Diagnosis, _prefix_of, diagnose,  # noqa: E402
                               resolve_mod)

INDEX = {
    "by_modid": {
        "guideme": "guideme-21.1.17.jar",
        "ae2": "appliedenergistics2-21.1.5.jar",
        "oculus": "oculus-mc1.20.1-1.8.0.jar",
        "xaerominimap": "xaerominimap-forge-1.20.1-25.3.10.jar",
        "physicsmod": "physics-mod-3.0.18-mc-1.20.1-forge.jar",
    },
    "by_pkg": {
        "com.tr7zw.entityculling": "entityculling-forge-1.9.5-mc1.20.1.jar",
        "net.coderbot.iris": "oculus-mc1.20.1-1.8.0.jar",
    },
}
PRESENT = {"appliedenergistics2-21.1.5.jar", "oculus-mc1.20.1-1.8.0.jar",
           "entityculling-forge-1.9.5-mc1.20.1.jar",
           "physics-mod-3.0.18-mc-1.20.1-forge.jar"}

INDEX2 = {
    "by_modid": {"continuity": "continuity-3.0.0+1.20.1.forge.jar",
                 "fabric_api": "fabric-api-0.92.6+1.11.14+1.20.1.jar",
                 "curios": "curios-forge-5.14.1+1.20.1.jar"},
    "by_pkg": {},
}
PRESENT2 = {"continuity-3.0.0+1.20.1.forge.jar",
            "fabric-api-0.92.6+1.11.14+1.20.1.jar",
            "curios-forge-5.14.1+1.20.1.jar"}

FORGE_LOADING_ERROR = """
[main/ERROR] [ne.mi.fm.lo.ModLoader/LOADING]: Loading errors have occurred:
	Mod File: physics-mod-3.0.18-mc-1.20.1-forge.jar
	Failure message: Physics Mod (physicsmod) has failed to load correctly
		java.lang.NoClassDefFoundError: net/minecraft/client/Minecraft
	Mod Version: 3.0.18
"""

MISSING_DEP = """
[main/ERROR] [ne.mi.fm.lo.ModLoader/LOADING]: Missing or unsupported mandatory dependencies:
	Mod ID: 'guideme', Requested by: 'ae2', Expected range: '[21.1,)', Actual version: '[MISSING]'
"""

CLIENT_CLASS_CRASH = """
java.lang.NoSuchMethodError: 'net.minecraft.client.Minecraft net.minecraft.client.Minecraft.getInstance()'
	at com.tr7zw.entityculling.EntityCullingMod.onInitialize(EntityCullingMod.java:41)
	at net.minecraftforge.fml.javafmlmod.FMLModContainer.constructMod(FMLModContainer.java:100)
"""

# The real failure from Contained Opolis: GuideME is on the client-side list,
# but five server mods depend on it. Lower-case "Mod file:" is NeoForge's.
NEOFORGE_MISSING_DEP = """
-- Mod loading issue for: ae2 --
Details:
	Mod file: /C:/servers/Contained_Opolis/mods/appliedenergistics2-19.2.17.jar
	Failure message: Mod ae2 requires guideme 21.1.1 or above
		Currently, guideme is not installed
	Mod version: 19.2.17
net.neoforged.fml.ModLoadingException: Loading errors encountered:
	- Mod ae2 requires guideme 21.1.1 or above
	  Currently, guideme is not installed
"""

# Better MC: the only failing mod is `continuity`, which wants a different
# fabric_api than the pack ships. The dependency must not be blamed, and the
# unrelated "Mod File:" warnings elsewhere in the log must be ignored.
VERSION_MISMATCH = r"""
[main/WARN] [ne.mi.fm.ModWorkManager/]: Mod File: C:\servers\mods\curios-forge-5.14.1+1.20.1.jar
-- MOD continuity --
Details:
	Mod File: /C:/servers/mods/continuity-3.0.0+1.20.1.forge.jar
	Failure message: Mod continuity requires fabric_api
		Currently, fabric_api is 0.92.2+1.11.12+1.20.1
	Mod Version: 3.0.0+1.20.1.forge
"""

MIXIN_FAILURE = """
[main/ERROR]: Mixin apply for mod oculus failed mixins.oculus.json:MixinLevelRenderer
org.spongepowered.asm.mixin.transformer.throwables.MixinApplyError: unexpected error
"""


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {detail}" if detail else ""))
    return cond


def main() -> int:
    ok = True

    d: Diagnosis = diagnose(FORGE_LOADING_ERROR, INDEX, PRESENT)
    ok &= check("Forge 'Mod File:' names the culprit",
                d.culprits and d.culprits[0].jar == "physics-mod-3.0.18-mc-1.20.1-forge.jar",
                d.summary)
    ok &= check("client-side evidence detected", d.client_side_evidence)

    d = diagnose(MISSING_DEP, INDEX, PRESENT)
    ok &= check("missing dependency restores the filtered jar",
                d.restore == ["guideme-21.1.17.jar"], str(d.restore))
    ok &= check("dependent mod is not blamed",
                not any(c.jar == "appliedenergistics2-21.1.5.jar" for c in d.culprits))

    d = diagnose(NEOFORGE_MISSING_DEP, INDEX, PRESENT)
    ok &= check("NeoForge wording restores the dependency",
                d.restore == ["guideme-21.1.17.jar"], str(d.restore))
    ok &= check("NeoForge 'Mod file:' does not get AE2 disabled instead",
                not any(c.jar == "appliedenergistics2-21.1.5.jar" for c in d.culprits)
                or bool(d.restore), d.summary)

    d = diagnose(VERSION_MISMATCH, INDEX2, PRESENT2)
    ok &= check("version mismatch blames the mod that refuses it",
                d.culprits and d.culprits[0].jar == "continuity-3.0.0+1.20.1.forge.jar",
                d.summary)
    ok &= check("the dependency itself is never blamed",
                not any("fabric-api" in c.jar for c in d.culprits))
    ok &= check("unrelated 'Mod File:' warnings are ignored",
                not any("curios" in c.jar for c in d.culprits))

    d = diagnose(VERSION_MISMATCH, INDEX2, PRESENT2,
                 protected={"continuity-3.0.0+1.20.1.forge.jar"})
    ok &= check("a protected jar is not disabled on a guess", not d.culprits)

    # ...but the loader's own verdict outranks any earlier decision to keep it,
    # or a mod like Reforgium stays protected forever and nothing can start.
    CONVICT = """
-- MOD reforgium --
Details:
	Mod File: /C:/servers/mods/reforgium-1.0.12a.jar
	Failure message: Reforgium (reforgium) has failed to load correctly
	Exception message: java.lang.RuntimeException: Attempted to load class net/minecraft/client/renderer/RenderType for invalid dist DEDICATED_SERVER
"""
    IDX3 = {"by_modid": {"reforgium": "reforgium-1.0.12a.jar"}, "by_pkg": {},
            "by_name": {"reforgium": "reforgium-1.0.12a.jar"}}
    d = diagnose(CONVICT, IDX3, {"reforgium-1.0.12a.jar"},
                 protected={"reforgium-1.0.12a.jar"})
    ok &= check("the loader's verdict overrides protection",
                d.culprits and d.culprits[0].jar == "reforgium-1.0.12a.jar",
                d.summary)

    d = diagnose(CLIENT_CLASS_CRASH, INDEX, PRESENT)
    ok &= check("stack trace blames the right mod",
                d.culprits and d.culprits[0].jar == "entityculling-forge-1.9.5-mc1.20.1.jar",
                d.summary)

    d = diagnose(MIXIN_FAILURE, INDEX, PRESENT)
    ok &= check("mixin failure blames the named mod",
                d.culprits and d.culprits[0].jar == "oculus-mc1.20.1-1.8.0.jar", d.summary)

    d = diagnose("nothing useful here at all", INDEX, PRESENT)
    ok &= check("clean log yields no culprit", not d.culprits and not d.restore)

    for jar, want in [("oculus-mc1.20.1-1.8.0.jar", "oculus-"),
                      ("physics-mod-3.0.18-mc-1.20.1-forge.jar", "physics-mod-"),
                      ("fancymenu_forge_3.8.1_MC_1.20.1.jar", "fancymenu_"),
                      ("Essential_1-4-1-1_neoforge_1-21-1.jar", "Essential_"),
                      ("entityculling-forge-1.9.5-mc1.20.1.jar", "entityculling-")]:
        got = _prefix_of(jar)
        ok &= check(f"prefix of {jar}", got == want, f"got {got!r}")

    # The disconnect screen shows display names, the log shows mod ids, and a
    # user might paste the jar filename - all three must find the same jar.
    NAMED = {"signature": {"wakes-1.20.1-Forge-1.0.9.jar": 1},
             "by_name": {"wakes": "wakes-1.20.1-Forge-1.0.9.jar",
                         "xaero's minimap": "xaerominimap-forge-1.20.1.jar"},
             "by_modid": {"wakes": "wakes-1.20.1-Forge-1.0.9.jar"}}
    for query, want in [("Wakes", "wakes-1.20.1-Forge-1.0.9.jar"),
                        ("wakes", "wakes-1.20.1-Forge-1.0.9.jar"),
                        ("  Wakes  ", "wakes-1.20.1-Forge-1.0.9.jar"),
                        ("wakes-1.20.1-Forge-1.0.9.jar",
                         "wakes-1.20.1-Forge-1.0.9.jar"),
                        ("Xaero's Minimap", "xaerominimap-forge-1.20.1.jar"),
                        ("Xaeros Minimap", "xaerominimap-forge-1.20.1.jar"),
                        ("no such mod", None),
                        ("", None)]:
        got = resolve_mod(NAMED, query)
        ok &= check(f"resolve {query!r}", got == want, f"got {got!r}")

    print("\nทั้งหมดผ่าน" if ok else "\nมีเทสต์ไม่ผ่าน")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

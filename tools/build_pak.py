"""Cook a level from this kit into a pak PteroSim mounts, and stage it in out/<Platform>/<Level>.

usage: python tools/build_pak.py --engine <Unreal Engine 5.8 folder> --pterosim <PteroSim folder> --level <Level>
                                 --platform Win64|Linux

Copy the staged out/<Platform>/<Level> folder into <PteroSim package>/PteroSim/Mods/ and start PteroSim.
"""

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

KIT = Path(__file__).resolve().parent.parent
PROJECT = KIT / "PteroSimLevelKit.uproject"
# The engine PteroSim's releases are built with (5.8.3); its hotfixes share one package format.
ENGINE_VERSION = "5.8"
# Unreal's names for the target platforms: the one the cook and staging folders use.
COOKED_PLATFORM = {"Win64": "Windows", "Linux": "Linux"}
LEVELS_FIELD = "PteroSimLevels"
ENTRY_FIELDS = ("Map", "Name", "Planet")
# EPlanetType's names (PteroSimCore Simulation/SimulationTypes.h); make_kit.py refuses a simulator that has others.
PLANETS = ("Earth", "Mars", "Moon")
ORIGIN_FIELDS = ("Latitude", "Longitude", "Altitude")
# The poles and the antimeridian, in degrees: PteroSim refuses an Origin past them.
MAX_LATITUDE_DEG = 90.0
MAX_LONGITUDE_DEG = 180.0
ORIGIN_RULE = "a Latitude from -90 to 90, a Longitude from -180 to 180 and an Altitude in metres, all numbers"
# Characters a long package name cannot hold (INVALID_LONGPACKAGE_CHARACTERS, Engine/.../UObject/NameTypes.h). PteroSim
# refuses a map with any of them: an object path such as /Level/Maps/Map.Map opens but reads back without its suffix.
INVALID_LONGPACKAGE_CHARACTERS = "\\:*?\"<>|' ,.&!~\n\r\t@#"
# The engine's own package roots (FLongPackagePathsSingleton, CoreUObject/Private/Misc/PackageName.cpp): a level named
# as one of these, or as an engine plugin, is never mounted as its own.
# Lower case: the engine compares these names ignoring it.
RESERVED_ROOTS = ("config", "engine", "game", "memory", "script", "temp")
# The DLC cook and its container step read this one; the runtime AssetRegistry.bin is only their fallback.
REGISTRY_FILE = "Metadata/DevelopmentAssetRegistry.bin"
# The kit's Releases/<this>/ is where the cook reads the game's registry from, whichever release it is.
BASE_RELEASE = "PteroSim"
# How the staging manifest names the kit project's files (CopyBuildToStagingDirectory); the engine's are under Engine/.
KIT_FILES = f"{PROJECT.stem}/"


def fail(message: str) -> NoReturn:
    """Stop with an error message, named after the tool the user ran."""
    sys.exit(f"{Path(sys.argv[0]).stem}: {message}")


def release_arguments() -> argparse.ArgumentParser:
    """The arguments of every tool that cooks: the engine, the PteroSim the level is for and its platform."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--engine", type=Path, required=True, help="the Unreal Engine 5.8 folder (the one holding Engine/)"
    )
    parser.add_argument(
        "--pterosim",
        type=Path,
        required=True,
        help="the PteroSim the level is for, the folder holding PteroSim.exe (PteroSim.sh on Linux)",
    )
    parser.add_argument("--platform", choices=sorted(COOKED_PLATFORM), required=True)
    return parser


def origin_is_valid(origin: object) -> bool:
    """Whether PteroSim takes this Origin: three finite numbers, the latitude and longitude on the planet."""
    if not isinstance(origin, dict):
        return False
    # Floats only, as check_level reads them; both readers take NaN and an infinity as numbers.
    numbers = [n for n in (origin.get(key) for key in ORIGIN_FIELDS) if isinstance(n, float) and math.isfinite(n)]
    if len(numbers) != len(ORIGIN_FIELDS):
        return False
    latitude, longitude, _ = numbers
    return abs(latitude) <= MAX_LATITUDE_DEG and abs(longitude) <= MAX_LONGITUDE_DEG


def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A JSON object, refusing two keys PteroSim reads as one: it ignores ASCII case and keeps the last."""
    keys = [key.encode().lower() for key, _ in pairs]
    if len(set(keys)) != len(keys):
        fail(f"a .uplugin object repeats a key, ignoring case: {[key for key, _ in pairs]}")
    return dict(pairs)


def editor_cmd(engine: Path) -> Path:
    """The engine's command-line editor, which cooks and runs the kit's editor scripts."""
    binary = "Win64/UnrealEditor-Cmd.exe" if platform.system() == "Windows" else "Linux/UnrealEditor-Cmd"
    return engine / "Engine" / "Binaries" / binary


def stage_release(pterosim: Path, cooked_platform: str) -> None:
    """Put the PteroSim release's kit project and registry where the cook reads them, so the level cooks for it."""
    registry = pterosim / "LevelKit" / cooked_platform / REGISTRY_FILE
    project = pterosim / "LevelKit" / "Project"
    for source in (registry, project / PROJECT.name):
        if not source.is_file():
            fail(f"{source} does not exist: --pterosim must be PteroSim 0.6.0 or later released for {cooked_platform}")
    # A copy: UAT passes -basedonreleaseversionroot to the cooker unquoted (CookCommand.Automation.cs:254).
    target = KIT / "Releases" / BASE_RELEASE / cooked_platform / REGISTRY_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(registry, target)
    if (KIT / "Config").exists():
        shutil.rmtree(KIT / "Config")
    shutil.copytree(project, KIT, dirs_exist_ok=True)


def foreign_files(manifest: str, level: str) -> list[str]:
    """The files UAT's staging manifest of the level's pak lists from the kit, but outside the level's own plugin."""
    files = (line.split("\t")[0] for line in manifest.splitlines())
    return [path for path in files if path.startswith(KIT_FILES) and not path.startswith(f"{KIT_FILES}Mods/{level}/")]


def check_engine(engine: Path, target_platform: str, level: str) -> Path:
    """RunUAT of an Unreal Engine 5.8 that stages the platform and has no root of the level's name; refuses another."""
    build = engine / "Engine" / "Build"
    batch = build / "BatchFiles" / ("RunUAT.bat" if platform.system() == "Windows" else "RunUAT.sh")
    for tool in (batch, editor_cmd(engine), build / "Build.version"):
        if not tool.is_file():
            fail(f"{tool} does not exist: is --engine the Unreal Engine {ENGINE_VERSION} folder?")
    version = "{MajorVersion}.{MinorVersion}".format_map(json.loads((build / "Build.version").read_bytes()))
    if version != ENGINE_VERSION:
        fail(f"{engine} is Unreal Engine {version}; PteroSim loads paks cooked with {ENGINE_VERSION}")
    # An installed engine has a platform only with this file (UEBuildPlatform.cs:365, InstalledPlatformInfo.cs:382).
    target = engine / "Engine" / "Binaries" / target_platform / f"UnrealGame-{target_platform}-Shipping.target"
    if (build / "InstalledBuild.txt").is_file() and not target.is_file():
        fail(
            f"{target} does not exist: add the {target_platform} target platform to the engine in the Epic Games "
            "Launcher"
        )
    # The editor never mounts a level whose name the engine's shadows, so its map cannot even be saved.
    engine_names = {p.stem.lower() for p in (engine / "Engine" / "Plugins").rglob("*.uplugin")}
    if level.lower() in engine_names | set(RESERVED_ROOTS):
        fail(f"the engine has its own {level}: give your level another name")
    return batch


def check_level(level: str) -> None:
    """Refuse a level the simulator would not offer: each map entry as PteroSim reads it, and the map in the level."""
    levels = sorted(p.name for p in (KIT / "Mods").iterdir() if p.is_dir())
    # Exactly the folder's name: the level's package root is /<folder>/, whatever the file system's case rules.
    if level not in levels:
        fail(f"no level {level!r} in Mods/; the levels there are {levels}")
    plugin = KIT / "Mods" / level
    descriptor = plugin / f"{level}.uplugin"
    if not descriptor.is_file():
        fail(f"no level {level}: {descriptor} does not exist")
    # From bytes for the editor's UTF-16; every number a double, so a huge integer is an infinity, as in PteroSim.
    fields = json.loads(descriptor.read_bytes(), parse_int=float, object_pairs_hook=unique_keys)
    entries = fields.get(LEVELS_FIELD) if isinstance(fields, dict) else None
    if not isinstance(entries, list) or not entries:
        fail(
            f'{descriptor} lists no maps: "{LEVELS_FIELD}" must be a list of'
            ' {"Map": ..., "Name": ..., "Planet": ..., "Origin": {...}}'
        )
    seen: set[bytes] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) and entry[key] for key in ENTRY_FIELDS
        ):
            fail(f'{descriptor}: "{LEVELS_FIELD}" entry {index} needs a Map, a Name and a Planet string')
        # PteroSim compares planet names ignoring the case of ASCII letters, as bytes.lower does.
        if entry["Planet"].encode().lower() not in {planet.encode().lower() for planet in PLANETS}:
            fail(f"{descriptor}: entry {index}'s Planet {entry['Planet']!r} is not one of {', '.join(PLANETS)}")
        if not origin_is_valid(entry.get("Origin")):
            fail(f"{descriptor}: entry {index} needs an Origin of {ORIGIN_RULE}")
        map_path: str = entry["Map"]
        inside = map_path.removeprefix(f"/{level}/")
        if inside == map_path or "//" in map_path or map_path.endswith("/"):
            fail(f"{descriptor}: Map {map_path!r} is not a map of this level, such as /{level}/Maps/<Map>")
        if any(c in INVALID_LONGPACKAGE_CHARACTERS for c in map_path):
            fail(f"{descriptor}: Map {map_path!r} is not a package name: write /{level}/Maps/<Map>, no .<Map> suffix")
        if not (plugin / "Content" / f"{inside}.umap").is_file():
            fail(f"{descriptor}: Map {map_path} has no {plugin / 'Content' / inside}.umap")
        # PteroSim compares map names ignoring the case of ASCII letters only, as bytes.lower does.
        if map_path.encode().lower() in seen:
            fail(f"{descriptor}: Map {map_path} is listed twice; PteroSim offers it once")
        seen.add(map_path.encode().lower())
    if (plugin / "Config").exists():
        fail(f"{plugin / 'Config'} exists: a level pak carries no config, the simulator's settings stay its own")


def cook(command: list[str]) -> int:
    """Run the cook; an interrupt stops it with all it started, rather than leaving the cooker running."""
    # RunUAT.sh then stops every process it started when it is interrupted; on Windows UAT does that itself.
    process = subprocess.Popen(command, env={**os.environ, "UE_DesktopUnrealProcess": "1"})
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.wait()
        fail("interrupted; the cook was stopped")


def main(argv: list[str] | None = None) -> Path:
    """Cook, then copy the staged level next to the kit, where it returns it."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[release_arguments()]
    )
    parser.add_argument("--level", required=True, help="the plugin folder name under Mods/")
    args = parser.parse_args(argv)

    cooked_platform = COOKED_PLATFORM[args.platform]
    # Absolute: RunUAT changes to its own folder before UAT reads the paths it is given.
    engine = args.engine.resolve()
    batch = check_engine(engine, args.platform, args.level)
    editor = editor_cmd(engine)
    check_level(args.level)
    stage_release(args.pterosim, cooked_platform)

    command = [
        str(batch),
        "BuildCookRun",
        f"-project={PROJECT}",
        # The kit's plugins make UAT expect an editor of the kit's own otherwise, which a content-only kit never has.
        f"-unrealexe={editor}",
        f"-platform={args.platform}",
        "-clientconfig=Shipping",
        "-cook",
        "-stage",
        "-pak",
        "-iostore",
        "-compressed",
        f"-dlcname={args.level}",
        f"-basedonreleaseversion={BASE_RELEASE}",
        "-DLCIncludeEngineContent",
        "-AdditionalCookerOptions=-CookAgainstFixedBase",
        "-unattended",
        "-nop4",
        "-utf8output",
    ]
    if cook(command) != 0:
        fail("the cook failed; its log is above")

    staged = KIT / "Mods" / args.level / "Saved" / "StagedBuilds" / cooked_platform / PROJECT.stem / "Mods" / args.level
    if not (staged / "Content" / "Paks" / cooked_platform).is_dir():
        fail(f"the cook succeeded but staged no pak at {staged}")
    manifest = staged.parents[2] / f"Manifest_UFSFiles_{args.platform}.txt"
    if not manifest.is_file():
        fail(f"the cook succeeded but wrote no {manifest}, which lists what went into the pak")
    # A /Game package can stand in for PteroSim's own of that name, another pak's package for that pak's.
    foreign = foreign_files(manifest.read_text(encoding="utf-8", errors="replace"), args.level)
    if foreign:
        fail(
            f"the pak holds {len(foreign)} files from outside Mods/{args.level}, such as {foreign[0]}: a pak holds its "
            "own plugin's assets and the engine's only (make_pak.py moves those the map uses from Content)"
        )
    out: Path = KIT / "out" / args.platform / args.level
    # Copied beside it first: a copy that stops half way leaves the last good pak where it was.
    partial = out.with_name(f"{out.name}.partial")
    if partial.exists():
        shutil.rmtree(partial)
    shutil.copytree(staged, partial)
    if out.exists():
        shutil.rmtree(out)
    partial.rename(out)
    # stderr writes any character of the path; stdout piped on Windows writes only the ANSI code page's.
    print(
        f"\nLevel pak ready: {out}\nCopy that folder into <PteroSim package>/PteroSim/Mods/ and start PteroSim.",
        file=sys.stderr,
    )
    return out


if __name__ == "__main__":
    main()

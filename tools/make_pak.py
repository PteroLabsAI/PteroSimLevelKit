"""Make a level pak from a map of the kit, for the PteroSim it is given, in one command.

Checks a vehicle can stand on the map, moves it and every /Game asset it uses into Mods/<name>, cooks it into
out/<Platform>/<name> with build_pak.py and, with --install, puts that into the PteroSim's Mods folder. Close the kit in
the editor first: the move runs in an editor of its own.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import build_pak
from build_pak import fail

GAME = "/Game/"
# A pak's name is its plugin's and its package root's: letters, digits and underscores, starting with a letter.
LEVEL_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
# How many kinds of mesh no vehicle can stand on the run names: chosen, enough to see which they are.
LISTED_MESHES = 10
# The editor's settings name each map it showed (LevelEditorViewportSettings.h:665), and moving such a map asks a dialog
# -unattended cancels (AssetRenameManager.cpp:464).
FORGET_SHOWN_MAPS = "-ini:EditorPerProjectUserSettings:[/Script/UnrealEd.LevelEditorViewportSettings]:EditorViews=()"
# A mesh is built as it loads, so the check reads its collision: one still building keeps its component's old preset
# (StaticMeshComponent.cpp:2178).
BUILD_MESHES_AS_THEY_LOAD = "-asyncstaticmeshcompilation=off"
# into_plugin.py's inputs in the environment, its steps and its report.
STEP_VARIABLE, MAP_VARIABLE, PLUGIN_VARIABLE = "PTEROSIM_STEP", "PTEROSIM_MAP", "PTEROSIM_PLUGIN"
CHECK, MOVE = "check", "move"
REPORT = build_pak.KIT / "Saved" / "make_pak.json"


def in_plugin(package: str, name: str) -> str:
    """Where a package of Content lands in the pak's plugin, at the same path; a package of the plugin stays."""
    return f"/{name}/{package.removeprefix(GAME)}" if package.startswith(GAME) else package


def parse(argv: list[str]) -> argparse.Namespace:
    """The arguments, refusing a name no package root can have, a map in neither place and an origin off the planet."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[build_pak.release_arguments()],
    )
    parser.add_argument("--map", required=True, help="the map's package path: right-click it, Copy Package Path")
    parser.add_argument("--name", required=True, help="the pak's name, one no other pak uses, such as Jane_Airfield")
    parser.add_argument("--planet", choices=build_pak.PLANETS, required=True)
    parser.add_argument(
        "--origin",
        nargs=3,
        type=float,
        required=True,
        metavar=build_pak.ORIGIN_FIELDS,
        help="where the map's (0, 0, 0) is: degrees, degrees, metres above the planet's ellipsoid",
    )
    parser.add_argument("--install", action="store_true", help="put the pak into the PteroSim's Mods folder")
    args = parser.parse_args(argv)
    if not LEVEL_NAME.fullmatch(args.name):
        fail(f"{args.name!r} is no pak name: letters, digits and underscores, starting with a letter")
    if ":" in args.map:
        fail(
            f"--map {args.map!r} is no package path, such as /Game/Maps/Airfield: if Git Bash made a file path of "
            "yours, put MSYS_NO_PATHCONV=1 before python"
        )
    invalid = any(c in build_pak.INVALID_LONGPACKAGE_CHARACTERS for c in args.map)
    root = args.map.split("/")[1] if args.map.startswith("/") else ""
    # The first part of a map's path in a plugin is the plugin's name, which a pak name can be.
    other_plugin = LEVEL_NAME.fullmatch(root) and root.lower() not in (*build_pak.RESERVED_ROOTS, args.name.lower())
    if not invalid and other_plugin:
        fail(f"--map {args.map!r} is in /{root}/, not in Content: if that is a plugin of Mods/, give --name {root}")
    if invalid or not args.map.startswith((GAME, f"/{args.name}/")):
        fail(f"--map {args.map!r} is no package path in Content or in Mods/{args.name}, such as /Game/Maps/Airfield")
    args.origin = dict(zip(build_pak.ORIGIN_FIELDS, args.origin, strict=True))
    if not build_pak.origin_is_valid(args.origin):
        fail(f"--origin takes {build_pak.ORIGIN_RULE}")
    return args


def write_plugin(name: str, levels: list[dict[str, object]]) -> None:
    """Write Mods/<name>/<name>.uplugin, a content plugin listing these levels, keeping its other fields."""
    descriptor = build_pak.KIT / "Mods" / name / f"{name}.uplugin"
    (descriptor.parent / "Content").mkdir(parents=True, exist_ok=True)
    fields = (
        json.loads(descriptor.read_bytes()) if descriptor.is_file() else {"FileVersion": 3, "CanContainContent": True}
    )
    fields |= {"EnabledByDefault": True, build_pak.LEVELS_FIELD: levels}
    descriptor.write_text(json.dumps(fields, indent="\t") + "\n", encoding="utf-8")


def install(out: Path, pterosim: Path, target_platform: str, name: str) -> None:
    """Put the pak into the PteroSim's Mods folder, refusing a PteroSim of another platform or one using the old pak."""
    if not (pterosim / "PteroSim" / "Binaries" / target_platform).is_dir():
        fail(f"{pterosim} is no PteroSim for {target_platform}: copy {out} into the PteroSim it is for")
    installed = pterosim / "PteroSim" / "Mods" / name
    # Moved aside whole first: a running PteroSim holds the old pak's files, and then nothing of it is deleted.
    replaced = installed.with_name(f"{name}.replaced")
    if replaced.exists():
        shutil.rmtree(replaced)
    if installed.exists():
        try:
            installed.rename(replaced)
        except OSError:
            fail(f"{installed} is in use: close PteroSim and run make_pak.py again")
    shutil.copytree(out, installed)
    if replaced.exists():
        shutil.rmtree(replaced)
    print(f"Installed in {installed}: restart PteroSim to see it in the Level menu.", file=sys.stderr)


def run_editor(engine: Path, step: str, map_package: str, name: str) -> Any:
    """Run a step of into_plugin.py in an editor of its own and return its report."""
    REPORT.unlink(missing_ok=True)
    inputs = {STEP_VARIABLE: step, MAP_VARIABLE: map_package, PLUGIN_VARIABLE: name}
    environment = {**os.environ, **inputs, "UE_PYTHONPATH": str(Path(__file__).resolve().parent)}
    editor = [str(build_pak.editor_cmd(engine)), str(build_pak.PROJECT), "-ExecutePythonScript=into_plugin.py"]
    editor += ["-ScriptErrorsAreFatal", "-unattended", "-nullrhi", "-nosplash"]
    editor += [FORGET_SHOWN_MAPS, BUILD_MESHES_AS_THEY_LOAD]
    if subprocess.run(editor, env=environment, check=False).returncode != 0 or not REPORT.is_file():
        fail(f"the editor could not {step} {map_package}; its log is in {build_pak.KIT / 'Saved' / 'Logs'}")
    return json.loads(REPORT.read_text(encoding="utf-8"))


def main() -> None:
    """Check, move, cook and install."""
    args = parse(sys.argv[1:])
    engine = args.engine.resolve()
    build_pak.check_engine(engine, args.platform, args.name)
    target = in_plugin(args.map, args.name)
    descriptor = build_pak.KIT / "Mods" / args.name / f"{args.name}.uplugin"
    listed = json.loads(descriptor.read_bytes()).get(build_pak.LEVELS_FIELD, []) if descriptor.is_file() else []
    others = [entry.get("Map") for entry in listed if entry.get("Map") != target]
    if others:
        fail(
            f"Mods/{args.name} is the pak of {others[0]}, and a pak holds one map: give this one another --name, "
            f"moving it into Content first if it is in Mods/{args.name}"
        )
    build_pak.stage_release(args.pterosim, build_pak.COOKED_PLATFORM[args.platform])
    checked = run_editor(engine, CHECK, args.map, args.name)
    # stderr writes any character of a mesh's name; stdout piped on Windows writes only the ANSI code page's.
    for mesh, count in Counter(checked["not_ground"]).most_common(LISTED_MESHES):
        print(f"No vehicle can stand on {count} x {mesh}", file=sys.stderr)
    if checked["refused"]:
        fail(str(checked["refused"]))
    if not descriptor.is_file():
        # Listing no map yet: the editor needs the plugin's root mounted to move the map into it.
        write_plugin(args.name, [])
    moved = run_editor(engine, MOVE, args.map, args.name)["moved"]
    print(f"Moved {len(moved)} packages from Content into Mods/{args.name}.", file=sys.stderr)
    write_plugin(args.name, [{"Map": target, "Name": args.name, "Planet": args.planet, "Origin": args.origin}])
    cook = ["--engine", str(engine), "--pterosim", str(args.pterosim), "--platform", args.platform]
    out = build_pak.main([*cook, "--level", args.name])
    if args.install:
        install(out, args.pterosim, args.platform, args.name)


if __name__ == "__main__":
    main()

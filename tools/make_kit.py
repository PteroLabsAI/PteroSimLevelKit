"""Write the kit's project files from a PteroSim tree, so a level cooks as the game built from that tree loads it.

usage: python tools/make_kit.py --simulator <PteroSim tree> --engine <Unreal Engine folder> --out <folder>

PteroSim's package_game.bat runs it into a release's LevelKit/Project, which build_pak.py copies into the kit; --out
<the kit folder> writes them into the kit itself.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import NoReturn

from build_pak import ENGINE_VERSION, PLANETS, PROJECT

# Where the simulator names its planets, which build_pak.PLANETS repeats for the kit.
PLANETS_SOURCE = "Plugins/PteroSimCore/Source/PteroSimCore/Public/Simulation/SimulationTypes.h"

# Cooked shaders and collision must match the game that loads the level, so these sections are the game's own.
COPIED_ENGINE_SECTIONS = (
    "/Script/Engine.RendererSettings",
    "/Script/WindowsTargetPlatform.WindowsTargetSettings",
    "/Script/LinuxTargetPlatform.LinuxTargetSettings",
    "/Script/Engine.CollisionProfile",
)
# The game places its own georeference; a level's own would be read against a class with one more property.
PLUGINS_KEPT_OUT = ("GeoReferencing",)
# make_example_level.py and into_plugin.py run in the kit's editor through these; both are off by default.
EDITOR_PLUGINS = ("PythonScriptPlugin", "EditorScriptingUtilities")

# The engine's default map is its Open World template, which the game does not ship, so a level cooked with it as the
# kit's default carries that whole template; Entry ships with the game.
KIT_MAPS = """
[/Script/EngineSettings.GameMapsSettings]
GameDefaultMap=/Engine/Maps/Entry
EditorStartupMap=/Engine/Maps/Entry
"""
GAME_INI = """[/Script/UnrealEd.ProjectPackagingSettings]
; The cook's Zen server stops before staging reads it, as in the game's own packaging.
bUseZenStore=False
; A level's shaders travel inside its own packages, so the game needs no shader library of the level.
bShareMaterialShaderCode=False
"""
# The engine's mobile joysticks are not in the game, and a cook would pack them into every level.
INPUT_INI = """[/Script/Engine.InputSettings]
DefaultTouchInterface=None
"""


def fail(message: str) -> NoReturn:
    """Stop with an error message."""
    sys.exit(f"make_kit: {message}")


def tree_file(simulator: Path, path: str) -> bytes:
    """A file of the simulator's tree."""
    source = simulator / path
    if not source.is_file():
        fail(f"{source} does not exist")
    return source.read_bytes()


def ini_sections(ini: bytes, wanted: tuple[str, ...]) -> str:
    """The wanted sections of an ini, each with its header, in file order."""
    kept: list[str] = []
    keeping = False
    for line in ini.decode("utf-8-sig").splitlines():
        if line.startswith("["):
            keeping = line.strip("[] \t") in wanted
        if keeping:
            kept.append(line)
    missing = set(wanted) - {line.strip("[] \t") for line in kept if line.startswith("[")}
    if missing:
        fail(f"the simulator's DefaultEngine.ini has no section {sorted(missing)}")
    return "\n".join(kept) + "\n"


def main() -> None:
    """Write the project and its config into --out."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--simulator", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve() == args.simulator.resolve():
        fail("--out is the simulator's own tree, whose Config this would replace")

    stock = {path.stem for path in (args.engine / "Engine" / "Plugins").rglob("*.uplugin")}
    if not stock:
        fail(f"{args.engine} has no Engine/Plugins")
    plugins = [
        {"Name": p["Name"], "Enabled": p["Enabled"]}
        for p in json.loads(tree_file(args.simulator, "PteroSim.uproject"))["Plugins"]
        # A plugin the game builds only for some targets, such as the editor's, is not in the game a level loads into.
        if p["Name"] in stock and p["Name"] not in PLUGINS_KEPT_OUT + EDITOR_PLUGINS and "TargetAllowList" not in p
    ]
    plugins += [{"Name": name, "Enabled": False} for name in PLUGINS_KEPT_OUT]
    plugins += [{"Name": name, "Enabled": True} for name in EDITOR_PLUGINS]
    engine_ini = ini_sections(tree_file(args.simulator, "Config/DefaultEngine.ini"), COPIED_ENGINE_SECTIONS)
    header = tree_file(args.simulator, PLANETS_SOURCE).decode()
    planets = re.search(r"enum class EPlanetType\b[^{]*\{(.*?)\};", header, re.S)
    names = tuple(re.findall(r"^\s*(\w+)", planets[1], re.M)) if planets else ()
    if names != PLANETS:
        fail(f"the simulator's planets are {names} and build_pak.PLANETS {PLANETS}: make them one")

    # Everything read, now written: nothing of the last simulator's config stays.
    config = args.out / "Config"
    if config.exists():
        shutil.rmtree(config)
    config.mkdir(parents=True)
    project = {"FileVersion": 3, "EngineAssociation": ENGINE_VERSION, "Plugins": plugins}
    (args.out / PROJECT.name).write_text(json.dumps(project, indent="\t") + "\n", encoding="utf-8")
    (config / "DefaultEngine.ini").write_text(engine_ini + KIT_MAPS, encoding="utf-8")
    (config / "DefaultGame.ini").write_text(GAME_INI, encoding="utf-8")
    (config / "DefaultInput.ini").write_text(INPUT_INI, encoding="utf-8")
    print(f"kit project files written to {args.out} from {args.simulator}")


if __name__ == "__main__":
    main()

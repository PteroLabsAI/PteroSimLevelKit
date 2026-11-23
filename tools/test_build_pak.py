"""Self-check of build_pak.py's map entries and cook command and of make_pak.py: python tools/test_build_pak.py."""

import codecs
import json
import os
import sys
import tempfile
from pathlib import Path

import build_pak
import make_pak

ORIGIN = {"Latitude": -33.9321, "Longitude": 151.1723, "Altitude": 24.42}
GOOD = {"Map": "/Level/Maps/Map", "Name": "A map", "Planet": "Earth", "Origin": ORIGIN}


def write_level(kit: Path, entries: list[object], *, with_map: bool = True, utf16: bool = False) -> None:
    """A kit holding a level named Level whose .uplugin lists these entries."""
    build_pak.KIT = kit
    plugin = kit / "Mods" / "Level"
    (plugin / "Content" / "Maps").mkdir(parents=True)
    # MAP.umap: the same file as Map.umap on Windows, another one on Linux, so both reach the duplicate check.
    for umap in ("Map.umap", "MAP.umap") if with_map else ():
        (plugin / "Content" / "Maps" / umap).write_bytes(b"")
    text = json.dumps({build_pak.LEVELS_FIELD: entries})
    raw = codecs.BOM_UTF16_LE + text.encode("utf-16-le") if utf16 else text.encode()
    (plugin / "Level.uplugin").write_bytes(raw)


def refuses(entries: list[object], *, with_map: bool = True, utf16: bool = False) -> bool:
    """Whether check_level refuses a level named Level whose .uplugin lists these entries."""
    with tempfile.TemporaryDirectory() as kit:
        write_level(Path(kit), entries, with_map=with_map, utf16=utf16)
        try:
            build_pak.check_level("Level")
        except SystemExit:
            return True
        return False


def cook_commands_for_relative_engine(
    *,
    engine_has_level_plugin: bool = False,
    with_registry: bool = True,
    installed: bool = False,
    with_target: bool = False,
) -> list[list[str]]:
    """The commands main() cooks with when --engine is given relative to the current folder; none when it refuses."""
    commands: list[list[str]] = []

    def record(command: list[str]) -> int:
        commands.append(command)
        return 1

    build_pak.cook = record
    with tempfile.TemporaryDirectory() as root:
        write_level(Path(root) / "kit", [GOOD])
        registry = Path(root) / "PteroSim" / "LevelKit" / "Windows" / build_pak.REGISTRY_FILE
        registry.parent.mkdir(parents=True)
        if with_registry:
            registry.write_bytes(b"registry")
        project = Path(root) / "PteroSim" / "LevelKit" / "Project"
        (project / "Config").mkdir(parents=True)
        (project / build_pak.PROJECT.name).write_text("release project")
        (project / "Config" / "DefaultEngine.ini").write_text("release config")
        (Path(root) / "kit" / "Config").mkdir()
        (Path(root) / "kit" / "Config" / "DefaultEditor.ini").write_text("an older release's")
        build_files = Path(root) / "UE_5.8" / "Engine" / "Build"
        (build_files / "BatchFiles").mkdir(parents=True)
        (build_files / "BatchFiles" / ("RunUAT.bat" if os.name == "nt" else "RunUAT.sh")).write_bytes(b"")
        editor = Path(root) / "UE_5.8" / "Engine" / "Binaries" / ("Win64" if os.name == "nt" else "Linux")
        editor.mkdir(parents=True)
        (editor / ("UnrealEditor-Cmd.exe" if os.name == "nt" else "UnrealEditor-Cmd")).write_bytes(b"")
        (build_files / "Build.version").write_text(json.dumps({"MajorVersion": 5, "MinorVersion": 8}))
        if installed:
            (build_files / "InstalledBuild.txt").write_text("UE_5.8")
        if with_target:
            (editor.parent / "Win64").mkdir(exist_ok=True)
            (editor.parent / "Win64" / "UnrealGame-Win64-Shipping.target").write_text("{}")
        if engine_has_level_plugin:
            # Another case than the level's: the engine compares plugin names ignoring it.
            (Path(root) / "UE_5.8" / "Engine" / "Plugins" / "Runtime" / "LEVEL").mkdir(parents=True)
            (Path(root) / "UE_5.8" / "Engine" / "Plugins" / "Runtime" / "LEVEL" / "LEVEL.uplugin").write_text("{}")
        cwd = Path.cwd()
        os.chdir(root)
        sys.argv = [
            "build_pak.py",
            "--engine",
            "UE_5.8",
            "--pterosim",
            "PteroSim",
            "--level",
            "Level",
            "--platform",
            "Win64",
        ]
        try:
            build_pak.main()
        except SystemExit:
            pass
        finally:
            os.chdir(cwd)
        staged = Path(root) / "kit" / "Releases" / build_pak.BASE_RELEASE / "Windows" / build_pak.REGISTRY_FILE
        assert not commands or staged.read_bytes() == b"registry", "the cook reads the PteroSim release's own registry"
        config = Path(root) / "kit" / "Config"
        assert not commands or sorted(p.name for p in config.iterdir()) == ["DefaultEngine.ini"], "the release's config"
        assert not commands or (Path(root) / "kit" / build_pak.PROJECT.name).read_text() == "release project"
    return commands


def made_plugin_is_cooked_once_its_map_is_there() -> bool:
    """Whether check_level takes the plugin make_pak.py writes, refusing it until its map is in it."""
    with tempfile.TemporaryDirectory() as kit:
        build_pak.KIT = Path(kit)
        make_pak.write_plugin("Pak", [{**GOOD, "Map": "/Pak/Maps/Airfield"}])
        try:
            build_pak.check_level("Pak")
            return False
        except SystemExit:
            pass
        (Path(kit) / "Mods" / "Pak" / "Content" / "Maps").mkdir()
        (Path(kit) / "Mods" / "Pak" / "Content" / "Maps" / "Airfield.umap").write_bytes(b"")
        build_pak.check_level("Pak")
        return True


def installs(*, target_platform: str, holds_old: bool) -> bool:
    """Whether make_pak.install puts a new pak in a PteroSim for Win64 in place of the old one, refusing otherwise."""
    with tempfile.TemporaryDirectory() as root:
        out, pterosim = Path(root) / "out" / "Pak", Path(root) / "PteroSim"
        out.mkdir(parents=True)
        (out / "new.pak").write_bytes(b"")
        (pterosim / "PteroSim" / "Binaries" / "Win64").mkdir(parents=True)
        if holds_old:
            (pterosim / "PteroSim" / "Mods" / "Pak").mkdir(parents=True)
            (pterosim / "PteroSim" / "Mods" / "Pak" / "old.pak").write_bytes(b"")
        try:
            make_pak.install(out, pterosim, target_platform, "Pak")
        except SystemExit:
            return False
        return sorted(p.name for p in (pterosim / "PteroSim" / "Mods").rglob("*")) == ["Pak", "new.pak"]


def make_pak_refuses(*, name: str = "Pak", map_path: str = "/Game/Maps/Airfield", latitude: str = "0") -> str:
    """Why make_pak.py refuses these arguments before it touches the kit, or nothing."""
    argv = ["--engine", "UE", "--pterosim", "PteroSim", "--platform", "Win64", "--map", map_path, "--name", name]
    try:
        make_pak.parse([*argv, "--planet", "Earth", "--origin", latitude, "0", "0"])
    except SystemExit as refused:
        return str(refused)
    return ""


assert not refuses([GOOD])
assert not refuses([{**GOOD, "Name": "Aérodrome"}], utf16=True), "the editor saves non-ASCII as UTF-16"
assert refuses([]), "no maps"
assert refuses([{"Map": GOOD["Map"], "Planet": GOOD["Planet"]}]), "no Name"
assert refuses([{"Map": GOOD["Map"], "Name": GOOD["Name"]}]), "no Planet"
assert refuses([{**GOOD, "Planet": "Eath"}]), "a planet PteroSim does not have"
assert not refuses([{**GOOD, "Planet": "mars"}]), "PteroSim compares planet names ignoring ASCII case"
assert refuses([{key: value for key, value in GOOD.items() if key != "Origin"}]), "no Origin"
assert refuses([{**GOOD, "Origin": {"Latitude": 0, "Longitude": 0}}]), "an Origin without its Altitude"
assert refuses([{**GOOD, "Origin": {**ORIGIN, "Latitude": "-33.9"}}]), "a latitude as a string"
assert refuses([{**GOOD, "Origin": {**ORIGIN, "Altitude": True}}]), "true is no number in JSON"
assert refuses([{**GOOD, "Origin": {**ORIGIN, "Latitude": float("nan")}}]), "NaN is no place"
assert refuses([{**GOOD, "Origin": {**ORIGIN, "latitude": 95}}]), "PteroSim reads the later of two such keys"
assert refuses([{**GOOD, "Origin": {**ORIGIN, "Altitude": 10**400}}]), "an integer past a double is infinite"
assert refuses([{**GOOD, "Origin": {**ORIGIN, "Latitude": 90.5}}]), "past a pole"
assert refuses([{**GOOD, "Origin": {**ORIGIN, "Longitude": -180.5}}]), "past the antimeridian"
assert not refuses([{**GOOD, "Origin": {"Latitude": -90, "Longitude": 180, "Altitude": -400}}]), "the bounds are places"
assert refuses([{**GOOD, "Map": "/Level/Maps/Map.Map"}]), "an object path reads back without its suffix"
assert refuses([{**GOOD, "Map": "/Level/Maps/Map/"}]), "a trailing slash is no package name"
assert refuses([{**GOOD, "Map": "/Example/Maps/Map"}]), "a map of another plugin"
assert refuses([GOOD], with_map=False), "no .umap"
assert refuses([GOOD, GOOD]), "the same map twice"
assert refuses([GOOD, {**GOOD, "Map": "/Level/Maps/MAP"}]), "PteroSim compares map names ignoring case"
# RunUAT changes to its own folder before UAT reads its arguments.
relative = [arg for arg in cook_commands_for_relative_engine()[0][1:] if "/" in arg or "\\" in arg]
assert all(Path(arg.split("=", 1)[-1]).is_absolute() for arg in relative), f"relative paths reach UAT: {relative}"
assert not cook_commands_for_relative_engine(
    engine_has_level_plugin=True
), "a level named as an engine plugin is not cooked"
assert not cook_commands_for_relative_engine(with_registry=False), "a PteroSim without the registry cooks nothing"
assert not cook_commands_for_relative_engine(installed=True), "a launcher engine without the platform cooks nothing"
assert cook_commands_for_relative_engine(installed=True, with_target=True), "a launcher engine with it cooks"
# Lines as UAT's staging manifest lists a map, an engine function, a /Game texture and another pak's mesh.
MANIFEST = "\r\n".join(
    f"{path}\t2026-11-23T03:11:53.610Z"
    for path in (
        "PteroSimLevelKit/Mods/Level/Content/Maps/Map.umap",
        "Engine/Content/Functions/Engine_MaterialFunctions02/Utility/AppendMany.uasset",
        "PteroSimLevelKit/Content/Pack/Textures/T_Brick.uasset",
        "PteroSimLevelKit/Mods/Other/Content/SM_Hangar.uasset",
    )
)
assert build_pak.foreign_files(MANIFEST, "Level") == [
    "PteroSimLevelKit/Content/Pack/Textures/T_Brick.uasset",
    "PteroSimLevelKit/Mods/Other/Content/SM_Hangar.uasset",
], "the kit's own Content and another pak are refused, not the level's or the engine's"
assert made_plugin_is_cooked_once_its_map_is_there(), "a plugin make_pak.py writes is one build_pak.py takes"
assert not make_pak_refuses(), "a map in the kit's Content, by its package path"
assert make_pak_refuses(latitude="91"), "make_pak.py refuses an origin build_pak.py would"
assert not make_pak_refuses(latitude="-90"), "make_pak.py takes a negative latitude"
assert make_pak_refuses(name="2Fast"), "a pak name is a package root: it starts with a letter"
assert not make_pak_refuses(map_path="/Pak/Maps/Airfield"), "a map make_pak.py moved into the pak before"
assert "give --name Other" in make_pak_refuses(map_path="/Other/Maps/Airfield"), "a map of another plugin: its name"
assert "--name" not in make_pak_refuses(map_path="/Script/Engine.World'/Game/Maps/A.A'"), "no plugin of that name"
assert make_pak_refuses(map_path="Game/Maps/Airfield"), "a package path starts with /"
assert make_pak.in_plugin("/Game/Pack/Maps/Demo", "Pak") == "/Pak/Pack/Maps/Demo", "Content's path under the plugin"
assert make_pak.in_plugin("/Pak/Maps/Airfield", "Pak") == "/Pak/Maps/Airfield", "the plugin's own stays"
assert installs(target_platform="Win64", holds_old=True), "the new pak in place of the old"
assert installs(target_platform="Win64", holds_old=False), "a first install"
assert not installs(target_platform="Linux", holds_old=True), "a Linux pak is not put into a PteroSim for Windows"
assert make_pak_refuses(map_path="/Game/Maps/Airfield.Airfield"), "an object path, not a package path"
assert make_pak_refuses(map_path="C:/Program Files/Git/Game/Maps/Airfield"), "a path a shell rewrote"
print("build_pak and make_pak: ok")

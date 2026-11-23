"""Check a vehicle can stand on a map, or move the map and the /Game assets it uses into a level's plugin.

Runs in the kit's editor, which make_pak.py starts once for each step, with the step, the map and the plugin in the
environment: a map the check opened is one the editor's settings then name, which the move cannot take.
"""

import json
import os
from collections import Counter

import build_pak
import unreal
from make_pak import CHECK, GAME, MAP_VARIABLE, PLUGIN_VARIABLE, REPORT, STEP_VARIABLE, in_plugin

# PteroSim stands a vehicle on shapes it can query that block this channel (PteroSimCore CollisionWorldSubsystem.cpp).
GROUND_CHANNEL = unreal.CollisionChannel.ECC_WORLD_STATIC
# What a level stands vehicles on: meshes, foliage among them, and landscapes, their collision a component of its own.
SURFACES = (unreal.StaticMeshComponent, unreal.LandscapeHeightfieldCollisionComponent)


def uses(map_package: str, plugin: str) -> tuple[list[str], list[str]]:
    """The map's package and those it uses in Content and in the plugin, followed through each other, and the rest."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    options = unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=True, include_hard_package_references=True
    )
    seen: set[str] = set()
    others: set[str] = set()
    todo = [map_package]
    while todo:
        package = todo.pop()
        if package not in seen:
            seen.add(package)
            for used in map(str, registry.get_dependencies(package, options) or []):
                (todo.append if used.startswith((GAME, f"/{plugin}/")) else others.add)(used)
    return sorted(seen), sorted(others)


def refusal(packages: list[str], others: list[str], plugin: str) -> str:
    """Why the map cannot be moved by script, or nothing."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    for package in others:
        if (build_pak.KIT / "Mods" / package.split("/")[1]).is_dir():
            return f"the map uses {package}, an asset of another pak: duplicate it in Content and use the copy"
    for package in packages:
        assets = registry.get_assets_by_package_name(package)
        root, rest = package[1:].split("/", 1)
        if not assets:
            return f"the map uses {package}, which does not exist: open the map and save it"
        # World Partition and Use External Actors keep a map's actors here; a scripted move lost them (measured).
        if unreal.EditorAssetLibrary.does_directory_have_assets(f"/{root}/__ExternalActors__/{rest}", True):
            return f"{package} keeps its actors apart: make_pak moves a map without World Partition or External Actors"
        if any(asset.is_redirector() for asset in assets):
            return f"the map uses {package}, an asset moved: right-click its folder, Update Redirector References"
        if package.startswith(GAME) and registry.get_assets_by_package_name(in_plugin(package, plugin)):
            return f"Mods/{plugin} holds {in_plugin(package, plugin)} already: rename {package} in Content"
    return ""


def is_map(package: str) -> bool:
    """Whether the package holds a map."""
    assets = unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_package_name(package)
    return any(asset.get_class() == unreal.World.static_class() for asset in assets)


def unfit(opened: str, not_ground: Counter[str]) -> int:
    """Open a map, count its own surfaces a vehicle can stand on, and tally the others by mesh and why."""
    if not unreal.EditorLoadingAndSavingUtils.load_map(opened):
        raise RuntimeError(f"could not open {opened}")
    ground = 0
    for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        # A level it streams counts when that level is opened itself.
        if actor.get_outermost().get_name() != opened:
            continue
        for kind in SURFACES:
            for component in actor.get_components_by_class(kind):
                if not component.is_query_collision_enabled():
                    reason = "it has no query collision"
                elif (
                    component.get_collision_response_to_channel(GROUND_CHANNEL)
                    != unreal.CollisionResponseType.ECR_BLOCK
                ):
                    reason = "it does not block WorldStatic"
                else:
                    ground += 1
                    continue
                mesh = component.get_editor_property("static_mesh") if kind is unreal.StaticMeshComponent else None
                not_ground[f"{mesh.get_name() if mesh else actor.get_actor_label()}: {reason}"] += 1
    return ground


def move(map_package: str, packages: list[str], plugin: str) -> list[str]:
    """Move the map's /Game packages into the plugin in one batch, then resave the plugin's, which the move skips."""
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    moved = [package for package in packages if package.startswith(GAME)]
    renames = [
        unreal.AssetRenameData(asset.get_asset(), in_plugin(package, plugin).rsplit("/", 1)[0], str(asset.asset_name))
        for package in moved
        for asset in registry.get_assets_by_package_name(package)
    ]
    if renames and not unreal.AssetToolsHelpers.get_asset_tools().rename_assets(renames):
        raise RuntimeError(f"could not move {len(renames)} assets into /{plugin}/")
    # A user the move does not load, such as a map already in the plugin, keeps a moved asset's old path until saved.
    for package in packages:
        if not package.startswith(GAME) and not unreal.EditorAssetLibrary.save_asset(package, False):
            raise RuntimeError(f"could not save {package}")
    # Nothing in PteroSim streams a level in: a level streamed by Blueprint loads, before the map starts, only so.
    moved_map = in_plugin(map_package, plugin)
    for streaming in unreal.ObjectIterator(unreal.LevelStreamingDynamic):
        if streaming.get_outermost().get_name() == moved_map:
            for loads_with_the_map in ("initially_loaded", "initially_visible", "should_block_on_load"):
                streaming.set_editor_property(loads_with_the_map, True)
    if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
        raise RuntimeError("could not save the moved assets")
    return moved


def main() -> None:
    """Run the step make_pak.py asked for and write its report."""
    map_package, plugin = os.environ[MAP_VARIABLE], os.environ[PLUGIN_VARIABLE]
    packages, others = uses(map_package, plugin)
    if os.environ[STEP_VARIABLE] == CHECK:
        if is_map(map_package):
            refused = refusal(packages, others, plugin)
        else:
            refused = f"there is no map {map_package}: right-click your map, Copy Package Path, and give that to --map"
        not_ground: Counter[str] = Counter()
        # Each opened: a Level Instance's actors load only when the editor's world ticks, which a script never sees.
        ground = 0 if refused else sum(unfit(opened, not_ground) for opened in filter(is_map, packages))
        if not refused and not ground:
            refused = (
                f"no mesh in {map_package} or a map it holds is one a vehicle can stand on: give floors a preset such "
                "as BlockAll"
            )
        result: dict[str, object] = {"not_ground": not_ground, "refused": refused}
    else:
        result = {"moved": move(map_package, packages, plugin)}
    REPORT.write_text(json.dumps(result, indent="\t"), encoding="utf-8")


main()

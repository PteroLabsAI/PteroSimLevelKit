"""Runs in the Unreal editor on the kit project and makes the example level: a floor and a pad, each in its own colour.

usage: UnrealEditor-Cmd <kit>/PteroSimLevelKit.uproject -ExecutePythonScript=<kit>/tools/make_example_level.py
       (the project from make_kit.py --out <kit>)
       -ScriptErrorsAreFatal -unattended -nullrhi
The script path must be absolute: the editor runs from its Binaries folder. Without -ScriptErrorsAreFatal a failed run
still exits 0. It refuses a kit whose example level exists already.
"""

import unreal

LEVEL = "/Example/Maps/Example"
MATERIALS = "/Example/Materials"
CUBE = "/Engine/BasicShapes/Cube"
CUBE_SIDE_CM = 100.0  # the edge of /Engine/BasicShapes/Cube
CM_PER_M = 100.0
FLOOR_SIDE_M = 2000.0  # chosen: room to fly beside the pad
FLOOR_THICKNESS_M = 1.0  # chosen
# A vehicle over the origin lands on the pad, 3 m up, which tells the level's collision from the planet's surface.
PAD_SIDE_M = 20.0
PAD_HEIGHT_M = 3.0
# Chosen: green and red, which a camera check tells apart from the engine's grey stand-in material.
FLOOR_COLOUR = unreal.LinearColor(0.10, 0.45, 0.15, 1.0)
PAD_COLOUR = unreal.LinearColor(0.85, 0.20, 0.10, 1.0)
NODE_X = -300  # material graph pixels left of the output, chosen: only where the node sits in the editor


def solid_colour_material(name: str, colour: unreal.LinearColor) -> unreal.Material:
    """A material of one base colour."""
    tools, editing = unreal.AssetToolsHelpers.get_asset_tools(), unreal.MaterialEditingLibrary
    material = tools.create_asset(name, MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    node = editing.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, NODE_X, 0)
    node.set_editor_property("constant", colour)
    editing.connect_material_property(node, "", unreal.MaterialProperty.MP_BASE_COLOR)
    editing.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material):
        raise RuntimeError(f"could not save {MATERIALS}/{name}")
    return material


def box(*, label: str, side_m: float, height_m: float, top_m: float, material: unreal.Material) -> None:
    """A square box of /Engine/BasicShapes/Cube centred on the origin, its top at top_m."""
    cube = unreal.EditorAssetLibrary.load_asset(CUBE)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actors.spawn_actor_from_object(cube, unreal.Vector(0.0, 0.0, (top_m - height_m / 2.0) * CM_PER_M))
    scale = CM_PER_M / CUBE_SIDE_CM
    actor.set_actor_scale3d(unreal.Vector(side_m * scale, side_m * scale, height_m * scale))
    actor.set_actor_label(label)
    actor.static_mesh_component.set_material(0, material)


def main() -> None:
    """Make, fill and save the level."""
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.new_level(LEVEL):
        raise RuntimeError(f"could not create {LEVEL}")
    floor = solid_colour_material("M_Floor", FLOOR_COLOUR)
    box(label="Floor", side_m=FLOOR_SIDE_M, height_m=FLOOR_THICKNESS_M, top_m=0.0, material=floor)
    pad = solid_colour_material("M_Pad", PAD_COLOUR)
    box(label="Pad", side_m=PAD_SIDE_M, height_m=PAD_HEIGHT_M, top_m=PAD_HEIGHT_M, material=pad)
    if not levels.save_current_level():
        raise RuntimeError(f"could not save {LEVEL}")
    unreal.log(f"example level saved at {LEVEL}")


main()

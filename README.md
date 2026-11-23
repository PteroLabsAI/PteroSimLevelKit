# PteroSim Level Kit

Build your own level in Unreal Engine and fly PteroSim over it. This kit cooks the level into a level pak that you copy
into your PteroSim.

## What you need

- **PteroSim 0.6.0 or later**, unpacked. A pak loads in the release it was cooked for: cook it again for a new one.
- **Unreal Engine 5.8**: on Windows from the Epic Games Launcher, on Linux Epic's Linux build.
- **Python 3.10 or later.**
- **Git**, or the kit's ZIP from GitHub.

## 1. Get the kit

```
git clone https://github.com/PteroLabsAI/PteroSimLevelKit
cd PteroSimLevelKit
```

## 2. Try the example

```
python tools/build_pak.py --engine "C:\Program Files\Epic Games\UE_5.8" --pterosim "C:\PteroSim" --level Example --platform Win64
```

`--pterosim` is the folder holding `PteroSim.exe`. On Linux, run `python3`, give `--platform Linux` and the folder
holding `PteroSim.sh`. The cook also writes the kit's Unreal project from your PteroSim and ends with
`Level pak ready: out/Win64/Example`. Copy that folder into `PteroSim/Mods/` of your PteroSim and start it: the Level
menu shows "Example level".

## 3. Make your map

1. Open `PteroSimLevelKit.uproject` in Unreal Engine 5.8.
2. File, New Level, **Empty Level**. Save it anywhere in `Content`.
3. Build it with your own assets or packs from Fab.

- Floors need collision that blocks `WorldStatic`, such as the BlockAll preset.
- No sky, sun, sky light, fog, clouds or unbound post-process volume: PteroSim brings its own.
- No World Partition and no External Actors.
- The map's (0, 0, 0) stands on `--origin` (step 4), with X east, Y south and Z up.

## 4. Make the pak

Save everything, close the editor, and run this in PowerShell or cmd with your own values in place of each `< >`:

```
python tools/make_pak.py --engine "<Unreal Engine 5.8 folder>" --pterosim "<PteroSim folder>" --platform Win64 --map <map> --name <pak name> --planet <planet> --origin <latitude> <longitude> <altitude> --install
```

- `--map`: right-click the map in the Content Browser, Copy Package Path.
- `--name`: letters, digits and underscores, one no other pak uses, such as `Jane_Airfield`.
- `--planet`: `Earth`, `Mars` or `Moon`.
- `--origin`: latitude and longitude in degrees, and altitude in metres above the ellipsoid (WGS84 on Earth), of the
  place the map's (0, 0, 0) stands on.

The script moves the map and what it uses into `Mods/<name>`, cooks the pak and installs it. To change the map later,
open it from `Plugins > <name>` and run the script with `--map /<name>/...`. Restart PteroSim: the map is in the Level
menu, under its planet.

## When something goes wrong

- The script stops with a message that says what to fix, or where its log is.
- PteroSim places no vehicle on the map: give the floor a collision preset that blocks `WorldStatic`, such as BlockAll,
  and simple collision if its mesh is set to Use Simple Collision As Complex.
- The map is not in the Level menu: search `PteroSim/Saved/Logs/PteroSim.log` for `PteroSimLevels:`.

## For PteroSim's maintainers

A PteroSim release holds, in `LevelKit/`, its registries and the kit project `tools/make_kit.py` wrote, which
`build_pak.py` copies into the kit. `make_kit.py --out <kit folder>` writes that project from a PteroSim tree.

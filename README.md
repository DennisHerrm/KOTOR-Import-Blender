# KOTOR Import for Blender

Import characters, creatures and droids from **Star Wars: Knights of the Old Republic** straight
from your own game installation into **Blender 4.0 – 5.2**, with skeleton, skinned meshes,
textures and all their animations.

> Unofficial fan project – see the [disclaimer](#disclaimer). No game data is included; the add-on
> reads the files of your own copy of the game.

Companion of [KOTOR Import for 3ds Max](https://github.com/DennisHerrm/KOTOR-Import-3dsMax): the
same reader, ported to pure Python and checked against the Max plugin's C++ reader.

## Features

- **KOTOR panel** in the 3D View sidebar (`N` → *KOTOR*): all 506 appearances from the game's
  `appearance.2da`, sorted into *Party / NPCs / Creatures / Droids / All*, with search, body
  variant A–J (armour/clothing) and the matching head.
- **File → Import → KOTOR Character…**: import window with category, searchable character list,
  variant, head, textures and – optionally – the animations (JKA set or all) in one go.
- **File → Import → KOTOR Character (quick search)**: type a name, press Enter.
- **File → Import → KOTOR Model (.mdl)**: loose binary `.mdl` files (with their `.mdx`); textures
  and supermodels come from the game.
- **Armature** with one bone per model node, bones point towards their children; hooks (lightsaber,
  head, impact …) in a separate bone collection *Hooks*.
- **Skinned meshes** with the original weights, rigid parts (eyes, teeth, droid parts) weighted
  100 % to their bone – everything deforms through the Armature modifier.
- **Textures**: TPC (DXT1/DXT5) decoded and packed into the `.blend`, Principled BSDF materials,
  cut-out alpha where the game uses it, backface culling like in the game.
- **Animations**: every animation of the model's supermodel chain (Bastila: 268), one, several or
  all at once. Each becomes an action `<character>|<name>` (fake user, linear keys, 30 fps) with the
  game's events (`snd_footstep`, `hit` …) as pose markers. The head's own facial animations are
  merged in.
- **Jedi Academy names**: KOTOR animations with a JKA counterpart are marked (`cwalk` →
  `BOTH_WALK1`, `g0a1` → `BOTH_ATTACK1` …, stored as the action property `jka_name`); *Check JKA
  Set* selects them.

Characters face **−Y** (towards the *Front* view), 1 Blender unit = 1 m, as in the game.

## Requirements

- Blender 4.0 or newer (tested with 4.0, 4.1, 4.2 LTS, 4.3, 4.4, 4.5 LTS, 5.0, 5.1, 5.2 LTS)
- *Star Wars: Knights of the Old Republic* installed (Steam or GOG; the folder with `chitin.key`)

## Installation

**[⬇ Download kotor_import-0.2.0.zip](https://github.com/DennisHerrm/KOTOR-Import-Blender/releases/download/v0.2.0/kotor_import-0.2.0.zip)**
(all versions: [releases](../../releases)). Do not unzip it.

- **Blender 4.2 and newer**: *Edit → Preferences → Get Extensions* → menu (⌄) at the top right →
  *Install from Disk…* → pick the ZIP. (Dragging the ZIP into the Blender window works too.)
- **Blender 4.0 / 4.1**: *Edit → Preferences → Add-ons → Install…* → pick the ZIP, then tick
  *Import-Export: KOTOR Import*.

The game folder is found automatically (Steam, GOG). Otherwise set it in the add-on preferences or
in the KOTOR panel.

## Usage

**Quickest:** *File → Import → KOTOR Character…* – pick category and character (type in the search
field under the list), choose a variant and *Animations: None / JKA set / All*, press *Import*.

**Or the sidebar:**

1. 3D View → sidebar (`N`) → tab **KOTOR** → *Load Game*.
2. Pick a category and a character, a variant if there are several, then *Import Character*.
3. *KOTOR Animations* (with the character selected): highlight an animation and press *Play* – it
   is loaded on first use. Tick several and use *Load Checked*, or *Load All*. *Rest Pose* removes
   the action.
4. Switch between loaded animations in the *Action Editor* (Dope Sheet) like any other action.

Tip: some clothing parts are double-sided in the game (two layers of faces). In *Solid* view turn
on *Backface Culling* in the viewport shading popover to see them as in the game; *Material
Preview* and rendering already use the material setting.

## Development

The reader in `kotor_import/kt/` has no Blender dependency (only numpy). `tools/gegenprobe.py`
builds every character variant and loads every animation of the game with it and compares the
result line by line with `ktdump pruef` from the 3ds Max plugin. Details:
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

Build the ZIP: `python tools/baue_zip.py` → `dist/kotor_import-<version>.zip`.

## Disclaimer

Unofficial, free fan project. It is **not** made by, affiliated with, endorsed or sponsored by
Lucasfilm Ltd., The Walt Disney Company, BioWare, Electronic Arts, Aspyr or the Blender Foundation.
Star Wars is a trademark of Lucasfilm Ltd. / The Walt Disney Company; Knights of the Old Republic
belongs to its respective owners. No game data is included.

## License

GPL-3.0-or-later – see [LICENSE](LICENSE).

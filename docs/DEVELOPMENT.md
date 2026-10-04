# KOTOR Import for Blender – development notes

## Layout

| Part | Files | Blender |
|---|---|---|
| Reader | `kotor_import/kt/` – archive (KEY/BIF/ERF/Override), 2DA, MDL/MDX, TPC/TGA, character assembly | no (numpy) |
| Scene | `kotor_import/szene.py` – armature, meshes, weights, materials | yes |
| Animation | `kotor_import/animation.py` – actions, keys, pose markers | yes |
| UI | `kotor_import/ui.py`, `sitzung.py` (open game for the session), `__init__.py` (preferences) | yes |

The reader is a line-by-line port of `ktcore` from the 3ds Max plugin
([KOTOR-Import-3dsMax](https://github.com/DennisHerrm/KOTOR-Import-3dsMax), `src/kt*.cpp`); the
format notes there (`docs/DEVELOPMENT.md`) apply unchanged.

## Parity with the C++ reader

`python tools/gegenprobe.py <game> <ktdump.exe>` writes, for every appearance and every body
variant, the assembled nodes (name, parent, local pose), every mesh (vertex/triangle counts,
texture, sums over positions, UVs, triangle indices, skin bones × weights, bind data) and, for the
default variant, one line per animation (tracks, keys, sums over rotations, positions and times,
events). `ktdump pruef` (Max project, `tools/ktdump.cpp`) writes the same from C++.
Result 4.10.2026: 288 088 lines, 506 entries, 1744 characters, 111 338 animations, **0
differences** (Python ≈ 46 s, C++ ≈ 4 s).

## Bones

A KOTOR node has no length. Every node becomes a bone (except skinned meshes without children);
the bone points to the child with the most descendants, leaves continue their parent's direction.
The fixed rotation node → bone `C` is stored per bone (`kotor_c`, plus `kotor_knoten` = node name).
With `L` = rest pose of the node (local), `A` = pose in the clip:

    basis = C⁻¹ · L⁻¹ · A · C
    rotation = c⁻¹ · qL⁻¹ · q(t) · c,   location = (c⁻¹ · qL⁻¹) applied to (p(t) − pL)

Rotation and position keys keep their own times. Bones without a track get one rest key, so that
switching actions never leaves a bone in the previous clip's pose.

Skinned meshes sit at their node's rest pose under the armature object (bind pose = rest pose,
measured for every bone in the Max project). Rigid meshes get one vertex group (their node's bone,
weight 1). The armature object carries the 180° turn about Z (KOTOR faces +Y, Blender's front is −Y).

## Blender versions

* 4.0/4.1: legacy add-on (`bl_info`), `Action.fcurves`, `Material.blend_method`.
* 4.2+: extension (`blender_manifest.toml` in the same ZIP), `Material.surface_render_method`.
* 4.4+: slotted actions – F-curves go into the channelbag of a slot (`Action.fcurves` is gone in
  5.0). **Assigning an action to an armature object that has no pose yet crashes Blender**
  (measured 4.4.3, 5.0.0, 5.2.2; `foreach_action_slot_use`), so the importer updates the view layer
  after building the armature.
* 5.0: `Material.use_nodes` deprecated (materials always have nodes).

## Tests

All in `test/` (not part of the ZIP):

* `blendertest.py` – background: imports characters, loads animations and compares **every
  deformed vertex** at 7 times per clip with a computation straight from the game data (node
  poses, weights, Blender's interpolation). Bastila/Rancor/HK-47/Paaerduag/Twi'lek: ≤ 0.013 mm.
  Renders Workbench pictures.
* `installtest.py` – installs the ZIP (4.0/4.1 add-on, 4.2+ extension via
  `blender --command extension install-file`) into a separate `BLENDER_USER_RESOURCES` and drives
  every operator, saves, reopens.
* `guitest.py` – with a window: draws the panels and takes screenshots.

Passed 4.10.2026 on 4.0.2, 4.1.1, 4.2.23, 4.3.2, 4.4.3, 4.5.3, 5.0.0, 5.1.2, 5.2.2.

# ============================================================
#  KOTOR Import for Blender
#
#  Figuren, Kreaturen und Droiden aus Star Wars: Knights of the Old
#  Republic direkt aus der eigenen Spielinstallation: Skelett, gehaeutete
#  Netze, Texturen und alle Animationen der Supermodell-Kette.
#  Der Leser (kt/) ist ein Port des C++-Lesers des 3ds-Max-Plugins
#  (github.com/DennisHerrm/KOTOR-Import-3dsMax) und wird gegen ihn geprueft
#  (tools/gegenprobe.py).
# ============================================================
bl_info = {
    "name": "KOTOR Import",
    "author": "DennisHerrm",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > KOTOR, File > Import > KOTOR Character",
    "description": "Import characters, creatures and droids with animations from Star Wars: Knights of the Old Republic",
    "doc_url": "https://github.com/DennisHerrm/KOTOR-Import-Blender",
    "category": "Import-Export",
}

if "bpy" in locals():
    import importlib
    from .kt import archiv, figur, mdl, tabelle, textur
    for _m in (archiv, tabelle, mdl, textur, figur, sitzung, szene, animation, ui):
        importlib.reload(_m)
else:
    from . import animation, sitzung, szene, ui

import bpy
from bpy.props import BoolProperty, StringProperty


class KOTOR_AP_einstellungen(bpy.types.AddonPreferences):
    bl_idname = __package__

    spielordner: StringProperty(
        name="Game Folder", subtype="DIR_PATH",
        description="KOTOR installation (the folder with chitin.key). Empty = find Steam/GOG automatically")
    texturen: BoolProperty(name="Textures", default=True,
                           description="Convert the game's TPC textures and pack them into the .blend")

    def draw(self, context):
        self.layout.prop(self, "spielordner")
        self.layout.prop(self, "texturen")


def register():
    bpy.utils.register_class(KOTOR_AP_einstellungen)
    ui.register()


def unregister():
    ui.unregister()
    bpy.utils.unregister_class(KOTOR_AP_einstellungen)

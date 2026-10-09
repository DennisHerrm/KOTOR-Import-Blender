# ============================================================
#  KOTOR Import for Blender
#
#  Figuren, Kreaturen und Droiden aus Star Wars: Knights of the Old
#  Republic I und II direkt aus der eigenen Spielinstallation: Skelett, gehaeutete
#  Netze, Texturen und alle Animationen der Supermodell-Kette.
#  Der Leser (kt/) ist ein Port des C++-Lesers des 3ds-Max-Plugins
#  (github.com/DennisHerrm/KOTOR-Import-3dsMax) und wird gegen ihn geprueft
#  (tools/gegenprobe.py).
# ============================================================
bl_info = {
    "name": "KOTOR Import",
    "author": "DennisHerrm",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "File > Import > KOTOR Character..., View3D > Sidebar > KOTOR",
    "description": "Import characters, creatures and droids with animations from Star Wars: Knights of the Old Republic I and II",
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
    from .kt import archiv

import bpy
from bpy.props import BoolProperty, StringProperty


def _ordner_neu(spiel):
    """Ordner eingetragen: Spiel erkennen (swkotor.exe / swkotor2.exe), ins richtige Feld legen."""
    def update(self, context):
        feld = "spielordner2" if spiel == "2" else "spielordner"
        wert = getattr(self, feld)
        if not wert or sitzung.ordner(spiel) == wert:
            return
        erkannt = archiv.spiel_von_ordner(bpy.path.abspath(wert))
        if erkannt and erkannt != spiel:
            setattr(self, "spielordner2" if erkannt == "2" else "spielordner", wert)
            setattr(self, feld, "")
            spiel_neu = erkannt
        else:
            spiel_neu = spiel
        sitzung.schliesse(spiel_neu)
        try:
            context.window_manager.kotor_einst.spiel = spiel_neu
            ui.fuelle_figuren(context)
        except AttributeError:
            pass
    return update


class KOTOR_AP_einstellungen(bpy.types.AddonPreferences):
    bl_idname = __package__

    spielordner: StringProperty(
        name="KOTOR", subtype="DIR_PATH", update=_ordner_neu("1"),
        description="Star Wars: Knights of the Old Republic (the folder with chitin.key). Empty = find Steam/GOG "
                    "automatically. A KOTOR II folder entered here is moved to the KOTOR II field")
    spielordner2: StringProperty(
        name="KOTOR II", subtype="DIR_PATH", update=_ordner_neu("2"),
        description="Star Wars: Knights of the Old Republic II (the folder with chitin.key and swkotor2.exe). "
                    "Empty = find Steam/GOG automatically")
    texturen: BoolProperty(name="Textures", default=True,
                           description="Convert the game's TPC textures and pack them into the .blend")

    def draw(self, context):
        self.layout.label(text="Game folders (empty = found automatically; the game is recognised from the folder):")
        self.layout.prop(self, "spielordner")
        self.layout.prop(self, "spielordner2")
        self.layout.prop(self, "texturen")


def register():
    bpy.utils.register_class(KOTOR_AP_einstellungen)
    ui.register()


def unregister():
    ui.unregister()
    bpy.utils.unregister_class(KOTOR_AP_einstellungen)

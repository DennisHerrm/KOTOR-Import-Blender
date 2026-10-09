# ============================================================
#  ui.py - Panel "KOTOR" in der Seitenleiste (N) des 3D-Fensters,
#  Operatoren und Datei -> Importieren
# ============================================================
import os
import time

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from . import animation as an
from . import sitzung
from . import szene
from .kt import figur as fg
from .kt import mdl

KATEGORIEN = [("party", "Party", "Party members"), ("npc", "NPCs", "Characters"),
              ("creature", "Creatures", "Creatures and animals"), ("droid", "Droids", "Droids"),
              ("all", "All", "Every appearance")]


# ------------------------------------------------------------
#  Daten fuer die Listen (WindowManager, nicht im .blend gespeichert)
# ------------------------------------------------------------
class KOTOR_PG_figur(bpy.types.PropertyGroup):
    # name = Titel (Suche der Liste)
    index: IntProperty()           # Index in sitzung.eintraege()
    kategorie: StringProperty()
    art: StringProperty()


class KOTOR_PG_anim(bpy.types.PropertyGroup):
    # name = KOTOR-Animationsname
    jka: StringProperty()
    laenge: StringProperty()
    herkunft: StringProperty()
    gewaehlt: BoolProperty(name="Select", default=False)


def _varianten(self, context):
    wm = context.window_manager
    e = _gewaehlter_eintrag(context)
    if e is None:
        return _varianten.cache
    _varianten.cache = [(str(i), "%s  %s" % (v.buchstabe, v.modell), "Body %s, texture %s" % (v.modell, v.textur or "-"))
                        for i, v in enumerate(e.varianten)]
    return _varianten.cache


_varianten.cache = [("0", "-", "")]


def _filter_neu(self, context):
    fuelle_figuren(context)


def _spiel_neu(self, context):
    """Anderes Spiel gewaehlt: oeffnen (falls gefunden) und die Liste neu fuellen."""
    try:
        sitzung.oeffne()
    except ValueError:
        pass
    fuelle_figuren(context)


def _figur_gesucht(self, context):
    wm = context.window_manager
    for i, it in enumerate(wm.kotor_figuren):
        if it.name == wm.kotor_figur_suche:
            wm.kotor_figur_index = i
            return


def _figur_gewaehlt(self, context):
    e = _gewaehlter_eintrag(context)
    if e is not None:
        wm = context.window_manager
        it = wm.kotor_figuren[wm.kotor_figur_index]
        if wm.kotor_figur_suche != it.name:
            wm.kotor_figur_suche = it.name
        try:
            context.window_manager.kotor_variante = str(e.standard)
        except TypeError:
            pass


class KOTOR_PG_einstellungen(bpy.types.PropertyGroup):
    spiel: EnumProperty(name="Game", items=[("1", "KOTOR", "Star Wars: Knights of the Old Republic"),
                                            ("2", "KOTOR II", "Star Wars: Knights of the Old Republic II - The Sith Lords")],
                        default="1", update=_spiel_neu)
    kategorie: EnumProperty(name="Category", items=KATEGORIEN, default="party", update=_filter_neu)


def _gewaehlter_eintrag(context):
    wm = context.window_manager
    liste = wm.kotor_figuren
    if not sitzung.offen() or not (0 <= wm.kotor_figur_index < len(liste)):
        return None
    i = liste[wm.kotor_figur_index].index
    alle = sitzung.eintraege()
    return alle[i] if 0 <= i < len(alle) else None


def fuelle_figuren(context):
    wm = context.window_manager
    wm.kotor_figuren.clear()
    if not sitzung.offen():
        return
    kat = wm.kotor_einst.kategorie
    for i, e in enumerate(sitzung.eintraege()):
        if kat != "all" and e.kategorie != kat:
            continue
        it = wm.kotor_figuren.add()
        it.name = e.titel
        it.index = i
        it.kategorie = e.kategorie
        it.art = e.art
    wm.kotor_figur_index = 0 if len(wm.kotor_figuren) else -1


def kotor_rig(context):
    """Das KOTOR-Armature der Auswahl (auch wenn ein Mesh davon gewaehlt ist)."""
    o = context.active_object
    while o is not None and o.get("kotor_rig") is None:
        o = o.parent
    return o if o is not None and o.type == "ARMATURE" else None


# ------------------------------------------------------------
#  Listen
# ------------------------------------------------------------
class KOTOR_UL_figuren(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        self.use_filter_show = True                     # Suchfeld immer sichtbar
        sym = {"party": "USER", "npc": "COMMUNITY", "creature": "MONKEY", "droid": "MODIFIER"}.get(item.kategorie, "DOT")
        layout.label(text=item.name, icon=sym)


class KOTOR_UL_anims(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        rig = kotor_rig(context)
        geladen = rig is not None and bpy.data.actions.get("%s|%s" % (rig.get("kotor_titel", rig.name), item.name)) is not None
        teil = layout.split(factor=0.72, align=True)
        links = teil.row(align=True)
        links.prop(item, "gewaehlt", text="")
        links.label(text=item.name, icon="ACTION" if geladen else "BLANK1")
        teil.label(text=item.laenge)


# ------------------------------------------------------------
#  Operatoren
# ------------------------------------------------------------
class KOTOR_OT_spiel_laden(bpy.types.Operator):
    bl_idname = "kotor.spiel_laden"
    bl_label = "Load Game"
    bl_description = "Open the KOTOR installation (folder with chitin.key) and list its characters"

    def execute(self, context):
        spiel = sitzung.aktuell()
        _such_cache.pop(spiel, None)
        try:
            sitzung.schliesse(spiel)
            a, _ = sitzung.oeffne(spiel)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        fuelle_figuren(context)
        k, t, o = a.zahlen()
        self.report({"INFO"}, "%s: %d characters (%d resources, %d textures in the pack, %d in Override)"
                    % (sitzung.SPIELE[spiel], len(sitzung.eintraege()), k, t, o))
        return {"FINISHED"}


def importiere(context, koerper, kopf, textur, titel, report, spiel=None):
    t0 = time.time()
    spiel = spiel or sitzung.aktuell()
    archiv, cache = sitzung.oeffne(spiel)
    try:
        f = fg.baue_figur(cache, koerper, kopf, textur)
    except ValueError as e:
        report({"ERROR"}, "Could not build %s: %s" % (koerper, e))
        return None
    prefs = sitzung.prefs()
    arm, bericht = szene.baue_szene(context, archiv, f, titel or f.koerper,
                                    mit_texturen=prefs.texturen if prefs else True)
    arm["kotor_spiel"] = spiel
    report({"INFO"}, "%s: %s (%.1f s)" % (sitzung.SPIELE[spiel], bericht, time.time() - t0))
    print("KOTOR Import:", bericht)
    return arm


class KOTOR_OT_importieren(bpy.types.Operator):
    bl_idname = "kotor.importieren"
    bl_label = "Import Character"
    bl_description = "Import the selected character with skeleton, skinned meshes and textures"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        return {"FINISHED"} if importiere_auswahl(context, self.report) is not None else {"CANCELLED"}


def importiere_auswahl(context, report):
    """Die im Panel/Fenster gewaehlte Figur importieren; Armature oder None."""
    wm = context.window_manager
    e = _gewaehlter_eintrag(context)
    if e is None:
        report({"ERROR"}, "Pick a character first")
        return None
    try:
        v = e.varianten[int(wm.kotor_variante)]
    except (ValueError, IndexError, TypeError):
        v = e.varianten[e.standard]
    kopf = e.kopf if wm.kotor_mit_kopf else ""
    titel = e.label if len(e.varianten) == 1 else "%s_%s" % (e.label, v.buchstabe)
    try:
        arm = importiere(context, v.modell, kopf, v.textur, titel, report)
    except ValueError as ex:
        report({"ERROR"}, str(ex))
        return None
    if arm is not None:
        fuelle_anims(context, arm)
    return arm


def zeichne_auswahl(lay, context, popup=False):
    """Kategorie, Liste, Variante, Kopf, Texturen - fuer Panel und Importfenster."""
    wm = context.window_manager
    lay.prop(wm.kotor_einst, "spiel", expand=True)
    if not sitzung.offen():
        lay.label(text="%s not found - set its folder in the add-on preferences" % sitzung.SPIELE[sitzung.aktuell()],
                  icon="ERROR")
        p = sitzung.prefs()
        if p is not None:
            lay.prop(p, "spielordner2" if sitzung.aktuell() == "2" else "spielordner", text="")
            lay.operator("kotor.spiel_laden", icon="FILE_FOLDER")
        return
    lay.label(text=sitzung.ordner(), icon="FILE_FOLDER")
    lay.prop(wm.kotor_einst, "kategorie", expand=True)
    if popup and bpy.app.version < (4, 2, 0):
        # Eine UIList in einem Popup laesst Blender 4.0/4.1 abstuerzen
        # (uiTemplateList_ex, gemessen 4.0.2 und 4.1.1) - dort ein Suchfeld.
        lay.prop_search(wm, "kotor_figur_suche", wm, "kotor_figuren", text="Character")
    else:
        lay.template_list("KOTOR_UL_figuren", "", wm, "kotor_figuren", wm, "kotor_figur_index", rows=12)
    e = _gewaehlter_eintrag(context)
    if e is not None:
        if len(e.varianten) > 1:
            lay.prop(wm, "kotor_variante", text="Variant")
        if e.kopf:
            lay.prop(wm, "kotor_mit_kopf", text="Head: " + e.kopf)
    p = sitzung.prefs()
    if p is not None:
        lay.prop(p, "texturen")


class KOTOR_OT_fenster(bpy.types.Operator):
    bl_idname = "kotor.fenster"
    bl_label = "Import KOTOR Character"
    bl_description = "Pick a KOTOR character, creature or droid from your game and import it, optionally with its animations"
    bl_options = {"REGISTER", "UNDO"}

    animationen: EnumProperty(name="Animations", items=[
        ("keine", "None", "Only the character (animations can be loaded later in the KOTOR panel)"),
        ("jka", "JKA set", "The animations that have a Jedi Academy counterpart"),
        ("alle", "All", "Every animation of the character")], default="keine")

    def invoke(self, context, event):
        try:
            if not sitzung.offen():
                sitzung.oeffne()
        except ValueError:
            pass                                            # Hinweis + Ordnerfeld im Fenster
        wm = context.window_manager
        if not len(wm.kotor_figuren) or not sitzung.offen():
            fuelle_figuren(context)
        try:
            return context.window_manager.invoke_props_dialog(self, width=460, confirm_text="Import")
        except TypeError:                                   # 4.0: ohne confirm_text
            return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        lay = self.layout
        zeichne_auswahl(lay, context, popup=True)
        lay.label(text="Animations:")
        lay.prop(self, "animationen", expand=True)

    def execute(self, context):
        arm = importiere_auswahl(context, self.report)
        if arm is None:
            return {"CANCELLED"}
        if self.animationen != "keine":
            namen = [a.name for a in context.window_manager.kotor_anims if self.animationen == "alle" or a.jka]
            if namen:
                lade_namen(context, arm, namen, self.report)
        return {"FINISHED"}


_such_cache = {}


def _such_eintraege(self, context):
    spiel = sitzung.aktuell()
    if spiel not in _such_cache and sitzung.offen():
        liste = []
        for i, e in enumerate(sitzung.eintraege()):
            for j, v in enumerate(e.varianten):
                zusatz = "" if len(e.varianten) == 1 else "  [%s %s]" % (v.buchstabe, v.modell)
                liste.append(("%d:%d" % (i, j), e.titel + zusatz, e.kategorie))
        _such_cache[spiel] = liste
    return _such_cache.get(spiel) or [("-", "Game not found", "")]


class KOTOR_OT_suchen(bpy.types.Operator):
    bl_idname = "kotor.suchen"
    bl_label = "KOTOR Character"
    bl_description = "Search all characters, creatures and droids of the game chosen in the KOTOR panel and import one"
    bl_property = "auswahl"
    bl_options = {"REGISTER", "UNDO"}

    auswahl: EnumProperty(items=_such_eintraege)

    def invoke(self, context, event):
        try:
            sitzung.oeffne()
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if self.auswahl == "-":
            return {"CANCELLED"}
        i, j = (int(x) for x in self.auswahl.split(":"))
        e = sitzung.eintraege()[i]
        v = e.varianten[j]
        titel = e.label if len(e.varianten) == 1 else "%s_%s" % (e.label, v.buchstabe)
        arm = importiere(context, v.modell, e.kopf, v.textur, titel, self.report)
        if arm is None:
            return {"CANCELLED"}
        fuelle_anims(context, arm)
        return {"FINISHED"}


class KOTOR_OT_mdl(bpy.types.Operator, ImportHelper):
    bl_idname = "kotor.mdl"
    bl_label = "Import KOTOR Model"
    bl_description = "Import a loose binary .mdl (with its .mdx); supermodels and textures come from the game"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={"HIDDEN"})

    def execute(self, context):
        # KOTOR II erkennt man am Funktionszeiger im Geometriekopf (siehe kt/mdl.py).
        spiel = sitzung.aktuell()
        try:
            with open(self.filepath, "rb") as f:
                kopf = f.read(16)
            if len(kopf) == 16:
                spiel = "2" if int.from_bytes(kopf[12:16], "little") == mdl.K2_MODELL else "1"
        except OSError:
            pass
        try:
            archiv, _ = sitzung.oeffne(spiel)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        ordner, datei = os.path.split(self.filepath)
        archiv.zusatz_ordner(ordner)
        sitzung.neuer_cache(spiel)
        name = os.path.splitext(datei)[0]
        arm = importiere(context, name, "", "", name, self.report, spiel)
        if arm is None:
            return {"CANCELLED"}
        fuelle_anims(context, arm)
        return {"FINISHED"}


def lade_namen(context, rig, namen, report):
    """Animationen als Actions anlegen, die erste aufs Rig legen."""
    wm = context.window_manager
    t0 = time.time()
    try:
        _, cache = sitzung.oeffne(rig.get("kotor_spiel", "1"))
        f = fg.baue_figur(cache, rig["kotor_koerper"], rig.get("kotor_kopf", ""), rig.get("kotor_textur", ""))
    except (ValueError, KeyError) as e:
        report({"ERROR"}, str(e))
        return {"CANCELLED"}
    wm.progress_begin(0, len(namen))
    try:
        actions, fehler = an.lade(context, cache, f, rig, namen, fortschritt=wm.progress_update)
    finally:
        wm.progress_end()
    if not actions:
        report({"ERROR"}, "None of the animations could be loaded: " + "; ".join(fehler[:3]))
        return {"CANCELLED"}
    an.zeige(context, rig, actions[0])
    text = "%d animation(s) loaded as actions (%.1f s), showing %s" % (len(actions), time.time() - t0, actions[0].name)
    if fehler:
        text += "; %d failed: %s" % (len(fehler), "; ".join(fehler[:3]))
    report({"INFO"}, text)
    return {"FINISHED"}


def fuelle_anims(context, arm):
    wm = context.window_manager
    wm.kotor_anims.clear()
    wm.kotor_anims_rig = ""
    if arm is None:
        return
    try:
        _, cache = sitzung.oeffne(arm.get("kotor_spiel", "1"))
        f = fg.baue_figur(cache, arm["kotor_koerper"], arm.get("kotor_kopf", ""), arm.get("kotor_textur", ""))
    except (ValueError, KeyError):
        return
    for name in f.animationen:
        it = wm.kotor_anims.add()
        it.name = name
        it.jka = fg.jka_anim_name(name)
        for t, start in ((0, f.koerper), (1, f.kopf)):
            if not start:
                continue
            for m in cache.kette(start):
                a = m.finde_animation(name)
                if a is not None:
                    it.laenge = "%.2f s" % a.laenge
                    it.herkunft = m.name + (" (head)" if t else "")
                    break
            if it.herkunft:
                break
    wm.kotor_anims_rig = arm.name
    wm.kotor_anim_index = 0 if len(wm.kotor_anims) else -1


class KOTOR_OT_anims_auflisten(bpy.types.Operator):
    bl_idname = "kotor.anims_auflisten"
    bl_label = "List Animations"
    bl_description = "List every animation of the selected KOTOR character's model chain"

    def execute(self, context):
        rig = kotor_rig(context)
        if rig is None:
            self.report({"ERROR"}, "Select an imported KOTOR character")
            return {"CANCELLED"}
        try:
            sitzung.oeffne(rig.get("kotor_spiel", "1"))
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        fuelle_anims(context, rig)
        self.report({"INFO"}, "%d animations" % len(context.window_manager.kotor_anims))
        return {"FINISHED"}


class KOTOR_OT_anims_laden(bpy.types.Operator):
    bl_idname = "kotor.anims_laden"
    bl_label = "Load Animations"
    bl_description = "Create actions for the animations"
    bl_options = {"REGISTER", "UNDO"}

    welche: EnumProperty(items=[("aktiv", "Active", "The highlighted animation"),
                                ("gewaehlt", "Checked", "All checked animations"),
                                ("alle", "All", "Every animation of the character")], default="aktiv")

    def execute(self, context):
        wm = context.window_manager
        rig = kotor_rig(context)
        if rig is None:
            self.report({"ERROR"}, "Select an imported KOTOR character")
            return {"CANCELLED"}
        if wm.kotor_anims_rig != rig.name or not len(wm.kotor_anims):
            fuelle_anims(context, rig)
        if self.welche == "aktiv":
            namen = [wm.kotor_anims[wm.kotor_anim_index].name] if 0 <= wm.kotor_anim_index < len(wm.kotor_anims) else []
        elif self.welche == "gewaehlt":
            namen = [a.name for a in wm.kotor_anims if a.gewaehlt]
        else:
            namen = [a.name for a in wm.kotor_anims]
        if not namen:
            self.report({"ERROR"}, "No animation selected")
            return {"CANCELLED"}
        return lade_namen(context, rig, namen, self.report)


class KOTOR_OT_anim_zeigen(bpy.types.Operator):
    bl_idname = "kotor.anim_zeigen"
    bl_label = "Play"
    bl_description = "Put the highlighted animation on the character (loads it first if needed)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        wm = context.window_manager
        rig = kotor_rig(context)
        if rig is None or not (0 <= wm.kotor_anim_index < len(wm.kotor_anims)):
            self.report({"ERROR"}, "Select a KOTOR character and an animation")
            return {"CANCELLED"}
        name = wm.kotor_anims[wm.kotor_anim_index].name
        act = bpy.data.actions.get("%s|%s" % (rig.get("kotor_titel", rig.name), name))
        if act is None:
            return bpy.ops.kotor.anims_laden(welche="aktiv")
        an.zeige(context, rig, act)
        return {"FINISHED"}


class KOTOR_OT_jka_wahl(bpy.types.Operator):
    bl_idname = "kotor.jka_wahl"
    bl_label = "Check JKA Set"
    bl_description = "Check every animation that has a Jedi Academy counterpart (BOTH_...)"

    def execute(self, context):
        for a in context.window_manager.kotor_anims:
            a.gewaehlt = bool(a.jka)
        return {"FINISHED"}


class KOTOR_OT_ruhelage(bpy.types.Operator):
    bl_idname = "kotor.ruhelage"
    bl_label = "Rest Pose"
    bl_description = "Remove the action from the character and show its rest pose"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rig = kotor_rig(context)
        if rig is None:
            return {"CANCELLED"}
        an.ruhelage(context, rig)
        return {"FINISHED"}


# ------------------------------------------------------------
#  Panel
# ------------------------------------------------------------
class KOTOR_PT_figuren(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "KOTOR"
    bl_label = "KOTOR Characters"

    def draw(self, context):
        lay = self.layout
        zeichne_auswahl(lay, context)
        if sitzung.offen():
            lay.operator("kotor.importieren", icon="IMPORT")


class KOTOR_PT_anims(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "KOTOR"
    bl_label = "KOTOR Animations"

    def draw(self, context):
        wm = context.window_manager
        lay = self.layout
        rig = kotor_rig(context)
        if rig is None:
            lay.label(text="Select an imported KOTOR character", icon="INFO")
            return
        if wm.kotor_anims_rig != rig.name:
            lay.label(text=rig.name, icon="ARMATURE_DATA")
            lay.operator("kotor.anims_auflisten", icon="FILE_REFRESH")
            return
        lay.label(text="%s (%s): %d animations" % (rig.name, sitzung.SPIELE.get(rig.get("kotor_spiel", "1"), "?"),
                                                   len(wm.kotor_anims)), icon="ARMATURE_DATA")
        lay.template_list("KOTOR_UL_anims", "", wm, "kotor_anims", wm, "kotor_anim_index", rows=10)
        r = lay.row(align=True)
        r.operator("kotor.anim_zeigen", icon="PLAY")
        r.operator("kotor.ruhelage", icon="ARMATURE_DATA")
        r = lay.row(align=True)
        r.operator("kotor.anims_laden", text="Load Checked").welche = "gewaehlt"
        r.operator("kotor.anims_laden", text="Load All").welche = "alle"
        lay.operator("kotor.jka_wahl", icon="CHECKBOX_HLT")
        if 0 <= wm.kotor_anim_index < len(wm.kotor_anims):
            a = wm.kotor_anims[wm.kotor_anim_index]
            if a.jka:
                lay.label(text="JKA: " + a.jka)
            lay.label(text="from %s" % a.herkunft)


def menue_import(self, context):
    self.layout.operator(KOTOR_OT_fenster.bl_idname, text="KOTOR Character...")
    self.layout.operator(KOTOR_OT_suchen.bl_idname, text="KOTOR Character (quick search)")
    self.layout.operator(KOTOR_OT_mdl.bl_idname, text="KOTOR Model (.mdl)")


KLASSEN = (KOTOR_PG_figur, KOTOR_PG_anim, KOTOR_PG_einstellungen, KOTOR_UL_figuren, KOTOR_UL_anims,
           KOTOR_OT_spiel_laden, KOTOR_OT_importieren, KOTOR_OT_fenster, KOTOR_OT_suchen, KOTOR_OT_mdl, KOTOR_OT_anims_auflisten,
           KOTOR_OT_anims_laden, KOTOR_OT_anim_zeigen, KOTOR_OT_jka_wahl, KOTOR_OT_ruhelage,
           KOTOR_PT_figuren, KOTOR_PT_anims)


def register():
    for k in KLASSEN:
        bpy.utils.register_class(k)
    wm = bpy.types.WindowManager
    wm.kotor_figuren = CollectionProperty(type=KOTOR_PG_figur)
    wm.kotor_figur_index = IntProperty(default=-1, update=_figur_gewaehlt)
    wm.kotor_variante = EnumProperty(name="Variant", items=_varianten)
    wm.kotor_figur_suche = StringProperty(name="Character", update=_figur_gesucht)
    wm.kotor_mit_kopf = BoolProperty(name="Head", default=True, description="Attach the character's head model")
    wm.kotor_einst = bpy.props.PointerProperty(type=KOTOR_PG_einstellungen)
    wm.kotor_anims = CollectionProperty(type=KOTOR_PG_anim)
    wm.kotor_anim_index = IntProperty(default=-1)
    wm.kotor_anims_rig = StringProperty()
    bpy.types.TOPBAR_MT_file_import.append(menue_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menue_import)
    wm = bpy.types.WindowManager
    for p in ("kotor_figuren", "kotor_figur_index", "kotor_figur_suche", "kotor_variante", "kotor_mit_kopf", "kotor_einst",
              "kotor_anims", "kotor_anim_index", "kotor_anims_rig"):
        if hasattr(wm, p):
            delattr(wm, p)
    for k in reversed(KLASSEN):
        bpy.utils.unregister_class(k)
    sitzung.schliesse()

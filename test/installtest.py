"""Installiertes Add-on ueber seine Operatoren bedienen (Hintergrund):
    blender -b --python installtest.py -- <zip> <spiel> <ausgabe.txt> <lose.mdl-ordner>
Unter 4.0/4.1 installiert das Skript das ZIP selbst; ab 4.2 muss es vorher per
`blender --command extension install-file -r user_default -e <zip>` installiert sein.
"""
import os
import sys
import traceback

import addon_utils
import bpy

args = sys.argv[sys.argv.index("--") + 1:]
ZIP, SPIEL, AUS, LOSE = args
log = open(AUS, "w", encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


def modulname():
    for m in addon_utils.modules():
        if m.__name__.endswith("kotor_import"):
            return m.__name__
    return None


def ok(r, was):
    p("  %-34s %s" % (was, sorted(r)))
    if "FINISHED" not in r:
        raise RuntimeError(was + " failed")


try:
    p("Blender", bpy.app.version_string)
    if bpy.app.version < (4, 2, 0):
        bpy.ops.preferences.addon_install(filepath=ZIP, overwrite=True)
    name = modulname()
    p("Modul", name)
    addon_utils.enable(name, default_set=True)
    p("aktiv", name in bpy.context.preferences.addons)
    prefs = bpy.context.preferences.addons[name].preferences
    prefs.spielordner = SPIEL
    wm = bpy.context.window_manager

    ok(bpy.ops.kotor.spiel_laden(), "kotor.spiel_laden")
    for kat in ("party", "npc", "creature", "droid", "all"):
        wm.kotor_einst.kategorie = kat
        p("  Kategorie %-9s %3d Eintraege" % (kat, len(wm.kotor_figuren)))
    wm.kotor_einst.kategorie = "party"
    i = next(n for n, it in enumerate(wm.kotor_figuren) if it.name == "Party NPC Bastila")
    wm.kotor_figur_index = i
    p("  Variante (Standard)", wm.kotor_variante)
    ok(bpy.ops.kotor.importieren(), "kotor.importieren Bastila")
    rig = bpy.context.active_object
    p("  Rig", rig.name, rig.type, len(rig.data.bones), "Bones,", len(rig.children), "Netze")
    p("  Animationen in der Liste", len(wm.kotor_anims))
    wm.kotor_anim_index = next(n for n, a in enumerate(wm.kotor_anims) if a.name == "walk")
    ok(bpy.ops.kotor.anim_zeigen(), "kotor.anim_zeigen walk")
    p("  aktive Action", rig.animation_data.action.name, "Bilder", bpy.context.scene.frame_start, bpy.context.scene.frame_end)
    ok(bpy.ops.kotor.jka_wahl(), "kotor.jka_wahl")
    p("  JKA angehakt", sum(1 for a in wm.kotor_anims if a.gewaehlt))
    ok(bpy.ops.kotor.anims_laden(welche="gewaehlt"), "kotor.anims_laden gewaehlt")
    ok(bpy.ops.kotor.anims_laden(welche="alle"), "kotor.anims_laden alle")
    acts = [a for a in bpy.data.actions if a.get("kotor_rig") == rig.get("kotor_titel")]
    p("  Actions", len(acts), "davon mit JKA-Namen", sum(1 for a in acts if a.get("jka_name")))
    ok(bpy.ops.kotor.ruhelage(), "kotor.ruhelage")

    # Kreatur ueber die Kategorie, Mesh statt Armature gewaehlt
    wm.kotor_einst.kategorie = "creature"
    wm.kotor_figur_index = next(n for n, it in enumerate(wm.kotor_figuren) if "Rancor" in it.name)
    ok(bpy.ops.kotor.importieren(), "kotor.importieren Rancor")
    rancor = bpy.context.active_object
    bpy.context.view_layer.objects.active = rancor.children[0]
    ok(bpy.ops.kotor.anims_auflisten(), "kotor.anims_auflisten (Mesh gewaehlt)")
    ok(bpy.ops.kotor.anims_laden(welche="alle"), "kotor.anims_laden alle Rancor")

    # Importfenster (Datei > Importieren > KOTOR Character...) ohne Dialog
    wm.kotor_einst.kategorie = "droid"
    wm.kotor_figur_index = 0
    n_vor = len(bpy.data.actions)
    ok(bpy.ops.kotor.fenster("EXEC_DEFAULT", animationen="jka"), "kotor.fenster JKA-Satz " + wm.kotor_figuren[0].name)
    p("  neue Actions", len(bpy.data.actions) - n_vor, "aktiv", bpy.context.active_object.animation_data.action.name
      if bpy.context.active_object.animation_data else None)

    # KOTOR II: Ordner absichtlich ins KOTOR-Feld -> muss ins KOTOR-II-Feld wandern
    K2 = r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
    prefs.spielordner = K2
    p("  Auto-Erkennung: KOTOR-Feld", repr(prefs.spielordner), "KOTOR II-Feld", repr(prefs.spielordner2),
      "Spiel", wm.kotor_einst.spiel)
    prefs.spielordner = SPIEL
    wm.kotor_einst.spiel = "2"
    p("  KOTOR II Liste", len(wm.kotor_figuren), "Eintraege")
    wm.kotor_einst.kategorie = "party"
    wm.kotor_figur_index = next(n for n, it in enumerate(wm.kotor_figuren) if it.name == "Party NPC Atton")
    ok(bpy.ops.kotor.fenster("EXEC_DEFAULT", animationen="jka"), "kotor.fenster Atton (KOTOR II)")
    atton = bpy.context.active_object
    p("  Atton Spiel", atton.get("kotor_spiel"), "Actions", len([a for a in bpy.data.actions if a.get("kotor_rig") == atton.get("kotor_titel")]))
    wm.kotor_einst.kategorie = "all"
    wm.kotor_figur_index = next(n for n, it in enumerate(wm.kotor_figuren) if it.name == "Party NPC HK47")
    ok(bpy.ops.kotor.importieren(), "kotor.importieren HK-47 (KOTOR II, racetex)")
    hk = bpy.context.active_object
    p("  HK-47 Texturen", sorted({m.name for o in hk.children for m in o.data.materials}))
    lose2 = os.path.join(os.path.dirname(LOSE), "lose2", "n_darthnihilus.mdl")
    wm.kotor_einst.spiel = "1"
    ok(bpy.ops.kotor.mdl(filepath=lose2), "kotor.mdl Nihilus (K2 erkannt, obwohl KOTOR gewaehlt)")
    p("  Nihilus Spiel", bpy.context.active_object.get("kotor_spiel"))
    ok(bpy.ops.kotor.anims_auflisten(), "kotor.anims_auflisten Nihilus")
    p("  Nihilus Animationen", len(wm.kotor_anims))
    wm.kotor_einst.spiel = "1"

    # Suche (Datei > Importieren) ohne Popup: Auswahl direkt
    ok(bpy.ops.kotor.suchen("EXEC_DEFAULT", auswahl="0:0"), "kotor.suchen 0:0")

    # lose .mdl
    mdl = [f for f in os.listdir(LOSE) if f.lower().endswith(".mdl")]
    ok(bpy.ops.kotor.mdl(filepath=os.path.join(LOSE, mdl[0])), "kotor.mdl " + mdl[0])

    p("  Objekte", len(bpy.data.objects), "Actions", len(bpy.data.actions), "Bilder", len(bpy.data.images),
      "eingepackt", sum(1 for i in bpy.data.images if i.packed_file))
    ziel = os.path.splitext(AUS)[0] + ".blend"
    bpy.ops.wm.save_as_mainfile(filepath=ziel)
    bpy.ops.wm.open_mainfile(filepath=ziel)
    p("  wieder geoeffnet: Actions", len(bpy.data.actions), "Bilder mit Daten",
      sum(1 for i in bpy.data.images if i.has_data or i.packed_file))
    addon_utils.disable(name)
    p("  deaktiviert ohne Fehler")
    p("INSTALLTEST OK")
except Exception:
    p(traceback.format_exc())
    p("INSTALLTEST FEHLER")
log.close()

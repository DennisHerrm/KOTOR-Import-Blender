"""Selbsttest im Hintergrund:  blender -b --factory-startup --python blendertest.py -- <spiel> <ausgabe> [figuren]

Figur: KOERPER:KOPF:TEXTUR:ANIM1,ANIM2   (Kopf/Textur leer erlaubt, ANIM * = alle)
Prueft je Animation an mehreren Bildern jeden verformten Vertex gegen eine
Rechnung direkt aus den Spieldaten (Knotenlagen + Gewichte, Blender-Interpolation).
"""
import math
import os
import sys
import time
import traceback

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, ".."))

import kotor_import                                   # noqa: E402
from kotor_import import animation as an              # noqa: E402
from kotor_import import sitzung, szene, ui           # noqa: E402
from kotor_import.kt import figur as fg               # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
SPIEL, AUS = args[0], args[1]
FIGUREN = args[2:] or ["P_BastilaBB:P_BastilaH:P_BastilaBB:pause1,walk,run,g8a1,dance,talk"]
os.makedirs(AUS, exist_ok=True)
log = open(os.path.join(AUS, "blendertest_%s.txt" % bpy.app.version_string.split()[0]), "w", encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


def lerp_spur(zeiten, werte, t, quat):
    """Wie Blender: linear je Komponente zwischen den Keys, ausserhalb konstant."""
    if not zeiten:
        return None
    if t <= zeiten[0]:
        return werte[0]
    if t >= zeiten[-1]:
        return werte[-1]
    i = int(np.searchsorted(zeiten, t, side="right")) - 1
    a, b = zeiten[i], zeiten[i + 1]
    u = 0.0 if b <= a else (t - a) / (b - a)
    return tuple(x + (y - x) * u for x, y in zip(werte[i], werte[i + 1]))


def stetig(rot):
    aus, letzte = [], None
    for q in rot:
        if letzte is not None and sum(x * y for x, y in zip(q, letzte)) < 0:
            q = tuple(-x for x in q)
        aus.append(q)
        letzte = q
    return aus


def soll_lagen(f, a, t):
    """Weltlage (Armature-Raum) je Knoten zur Zeit t (Sekunden)."""
    spur = {s.knoten: s for s in a.spuren}
    welt = []
    for i, k in enumerate(f.knoten):
        pos, rot = k.pos, k.rot
        s = spur.get(i)
        if s is not None:
            if s.zeit_rot:
                q = lerp_spur(s.zeit_rot, stetig(s.rot), t, True)
                rot = tuple(Quaternion(q).normalized())
            if s.zeit_pos:
                pos = lerp_spur(s.zeit_pos, s.pos, t, False)
        lokal = szene.lage_matrix(pos, rot)
        welt.append(welt[k.eltern] @ lokal if k.eltern >= 0 else lokal)
    return welt


def pruefe_bild(f, a, arm, netz_objekte, ruhe, t):
    bpy.context.scene.frame_set(int(math.floor(t * 30)), subframe=t * 30 - math.floor(t * 30))
    dg = bpy.context.evaluated_depsgraph_get()
    welt = soll_lagen(f, a, t) if a is not None else ruhe
    arm_inv = arm.matrix_world.inverted()
    groesst = 0.0
    for n, ob in netz_objekte:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        ist = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", ist)
        ev.to_mesh_clear()
        m = np.array(arm_inv @ ob.matrix_world)
        ist = ist.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
        geo, erster = szene.schweisse(n)
        v = n.daten.pos[erster]
        wm = np.array(ruhe[n.knoten])
        v_ruhe = v @ wm[:3, :3].T + wm[:3, 3]
        if n.daten.skin:
            soll = np.zeros_like(v)
            summe = np.zeros(len(v))
            for s in range(4):
                bk = n.skin_knoten[erster, s]
                w = n.daten.gewicht[erster, s]
                for b in np.unique(bk):
                    if b < 0:
                        continue
                    sel = (bk == b) & (w > 0)
                    mm = np.array(welt[b] @ ruhe[b].inverted())
                    soll[sel] += w[sel, None] * (v_ruhe[sel] @ mm[:3, :3].T + mm[:3, 3])
                    summe[sel] += w[sel]
            ok = summe > 0
            soll[ok] /= summe[ok, None]
            soll[~ok] = v_ruhe[~ok]
        else:
            mm = np.array(welt[n.knoten])
            soll = v @ mm[:3, :3].T + mm[:3, 3]
        if len(ist) != len(soll):
            p("   VERTEXZAHL", ob.name, len(ist), len(soll))
            return 1e9
        groesst = max(groesst, float(np.abs(ist - soll).max()) if len(ist) else 0.0)
    return groesst


def foto(arm, datei, seite=False):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "TEXTURE"
    sc.display.shading.show_backface_culling = True
    sc.display.shading.show_specular_highlight = False
    sc.render.resolution_x, sc.render.resolution_y = 600, 800
    sc.render.film_transparent = False
    kam = bpy.data.objects.get("TestKamera")
    if kam is None:
        kam = bpy.data.objects.new("TestKamera", bpy.data.cameras.new("TestKamera"))
        sc.collection.objects.link(kam)
    sc.camera = kam
    # Rahmen aus den Netzen
    pts = []
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in arm.children:
        if ob.type == "MESH":
            pts += [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector((min(v.x for v in pts), min(v.y for v in pts), min(v.z for v in pts)))
    hi = Vector((max(v.x for v in pts), max(v.y for v in pts), max(v.z for v in pts)))
    mitte = (lo + hi) / 2
    h = max((hi - lo).length, 0.5)
    kam.data.type = "ORTHO"
    kam.data.ortho_scale = h * 1.05
    if seite:
        kam.location = mitte + Vector((h * 3, 0, 0))
        kam.rotation_euler = (math.pi / 2, 0, math.pi / 2)
    else:
        kam.location = mitte + Vector((0, -h * 3, 0))       # Front-Ansicht: Blick nach +Y
        kam.rotation_euler = (math.pi / 2, 0, 0)
    sc.render.filepath = datei
    bpy.ops.render.render(write_still=True)


def main():
    t0 = time.time()
    p("Blender", bpy.app.version_string, "Python", sys.version.split()[0])
    kotor_import.register()
    sitzung.oeffne(SPIEL)
    p("Spiel", sitzung.ordner(), len(sitzung.eintraege()), "Eintraege")
    archiv, cache = sitzung.oeffne(SPIEL)
    gesamt_max = 0.0
    for spec in FIGUREN:
        teile = (spec.split(":") + ["", "", "", ""])[:4]
        koerper, kopf, textur, anims = teile
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        for c in list(bpy.data.collections):
            bpy.data.collections.remove(c)
        t1 = time.time()
        f = fg.baue_figur(cache, koerper, kopf, textur)
        arm, bericht = szene.baue_szene(bpy.context, archiv, f, koerper)
        p("\n" + bericht, "(%.1f s)" % (time.time() - t1))
        ruhe = []
        for k in f.knoten:
            lokal = szene.lage_matrix(k.pos, k.rot)
            ruhe.append(ruhe[k.eltern] @ lokal if k.eltern >= 0 else lokal)
        netz_objekte = []
        for n in f.netze:
            ob = next(o for o in arm.children if o.get("kotor_knoten") == f.knoten[n.knoten].name)
            netz_objekte.append((n, ob))
        d = pruefe_bild(f, None, arm, netz_objekte, ruhe, 0.0)
        p("  Ruhelage: groesste Abweichung %.6f m" % d)
        gesamt_max = max(gesamt_max, d)
        foto(arm, os.path.join(AUS, "%s_ruhe.png" % koerper))
        namen = f.animationen if anims == "*" else [x for x in anims.split(",") if x]
        t2 = time.time()
        acts, fehler = an.lade(bpy.context, cache, f, arm, namen)
        p("  %d Actions in %.1f s, %d Fehler %s" % (len(acts), time.time() - t2, len(fehler), fehler[:3]))
        geprueft = 0
        for act in acts[:12] if anims == "*" else acts:
            a = fg.lade_animation(cache, f, act["kotor_anim"])
            an.zeige(bpy.context, arm, act)
            groesst = 0.0
            for t in np.linspace(0, a.laenge, 7):
                groesst = max(groesst, pruefe_bild(f, a, arm, netz_objekte, ruhe, float(t)))
            geprueft += 1
            gesamt_max = max(gesamt_max, groesst)
            p("  %-14s %5.2f s %3d Spuren %2d Marker  Abweichung %.6f m" % (
                a.name, a.laenge, len(a.spuren), len(act.pose_markers), groesst))
        if acts:
            an.zeige(bpy.context, arm, acts[min(1, len(acts) - 1)])
            bpy.context.scene.frame_set(int(acts[min(1, len(acts) - 1)].frame_end * 0.4))
            foto(arm, os.path.join(AUS, "%s_anim.png" % koerper))
            foto(arm, os.path.join(AUS, "%s_anim_seite.png" % koerper), seite=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(AUS, "%s.blend" % koerper))
    p("\nGESAMT groesste Abweichung %.6f m, %.1f s" % (gesamt_max, time.time() - t0))


try:
    main()
except Exception:
    p(traceback.format_exc())
log.close()

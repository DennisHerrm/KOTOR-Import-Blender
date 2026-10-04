# ============================================================
#  szene.py - aus einer kt.figur.Figur wird die Blender-Szene
#
#    1. ein Armature-Objekt, je Figurknoten ein Bone (ausser gehaeuteten
#       Netzen ohne Kinder - die bewegen sich nur ueber den Skin),
#    2. je sichtbarem Netz ein Mesh-Objekt unter dem Armature mit
#       Armature-Modifier: gehaeutete Netze mit den Gewichten aus der MDX,
#       starre Netze (Augen, Zaehne, Droidenteile) zu 100 % an ihrem Bone,
#    3. Materialien (Principled BSDF) mit den entpackten TPC-Texturen,
#       im .blend eingepackt.
#
#  ACHSEN: KOTOR ist wie Blender rechtshaendig, Z oben, Meter - nichts wird
#  umgerechnet. KOTOR-Figuren schauen nach +Y; in Blender gilt -Y als vorn
#  (die Front-Ansicht sieht das Gesicht). Das Armature-Objekt bekommt deshalb
#  180 Grad um Z, alles darunter bleibt wie in der Datei.
#
#  BONE-RICHTUNG: ein KOTOR-Knoten hat keine Laenge. Damit das Skelett lesbar
#  ist, zeigt jeder Bone zu seinem groessten Kind. Die Drehung zwischen Knoten
#  und Bone (C, je Bone fest) wird beim Setzen der Keys herausgerechnet
#  (animation.py) - Knoten, Skin und Animation bleiben exakt wie im Spiel.
# ============================================================
import math

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from .kt import archiv as ar
from .kt import figur as fg
from .kt import textur as tx

VERSION = "0.2.0"


def lage_matrix(p, q):
    return Matrix.Translation(Vector(p)) @ Quaternion(q).to_matrix().to_4x4()


# ------------------------------------------------------------
#  Welche Knoten werden Bones?
# ------------------------------------------------------------
def bone_knoten(f):
    """Liste bool je Figurknoten: True = Bone."""
    hat_kinder = [False] * len(f.knoten)
    for k in f.knoten:
        if k.eltern >= 0:
            hat_kinder[k.eltern] = True
    aus = []
    for i, k in enumerate(f.knoten):
        geh = k.netz >= 0 and f.netze[k.netz].daten.skin
        aus.append(i == 0 or not geh or hat_kinder[i])
    return aus


def skelett_knoten(f):
    """Skin-Bones, Knoten starrer Netze und ihre Vorfahren (ohne Wurzel) - der Rest sind Haken."""
    sk = [False] * len(f.knoten)

    def markiere(b):
        while b > 0 and not sk[b]:
            sk[b] = True
            b = f.knoten[b].eltern

    for n in f.netze:
        if n.daten.skin and n.skin_knoten is not None:
            for b in np.unique(n.skin_knoten):
                if b >= 0:
                    markiere(int(b))
        else:
            markiere(n.knoten)
    return sk


def bone_ausrichtung(f, welt, ist_bone):
    """Je Bone (Weltmatrix des Bones, Laenge). Y zeigt zum Kind mit den meisten Nachfahren."""
    n = len(f.knoten)
    kinder = [[] for _ in range(n)]
    for i, k in enumerate(f.knoten):
        if k.eltern >= 0 and ist_bone[i]:
            kinder[k.eltern].append(i)
    nachfahren = [0] * n
    for i in range(n - 1, -1, -1):           # Elternteil vor Kind: rueckwaerts summieren
        e = f.knoten[i].eltern
        if e >= 0 and ist_bone[i]:
            nachfahren[e] += 1 + nachfahren[i]
    groesse = 1.0
    alle = [welt[i].translation for i in range(n) if ist_bone[i]]
    if alle:
        lo = Vector((min(v.x for v in alle), min(v.y for v in alle), min(v.z for v in alle)))
        hi = Vector((max(v.x for v in alle), max(v.y for v in alle), max(v.z for v in alle)))
        groesse = max((hi - lo).length, 0.1)
    standard = groesse * 0.04
    aus = [None] * n
    for i in range(n):
        if not ist_bone[i]:
            continue
        w = welt[i]
        kopf = w.translation
        dreh = w.to_3x3().normalized()
        ziel = None
        for c in sorted(kinder[i], key=lambda c: -nachfahren[c]):
            d = welt[c].translation - kopf
            if d.length > 1e-3:
                ziel = d
                break
        if ziel is not None:
            richtung, laenge = ziel.normalized(), ziel.length
        else:
            e = f.knoten[i].eltern
            if e >= 0 and aus[e] is not None:
                richtung = aus[e][0].to_3x3().col[1].normalized()
                laenge = min(max(aus[e][1] * 0.5, standard * 0.25), standard)
            else:
                richtung, laenge = dreh.col[1].normalized(), standard
        # kleinste Drehung, die die Y-Achse des Knotens auf die Richtung legt
        r = dreh.col[1].normalized().rotation_difference(richtung).to_matrix()
        m = (r @ dreh).to_4x4()
        m.translation = kopf
        aus[i] = (m, max(laenge, 0.002))
    return aus


# ------------------------------------------------------------
#  Texturen und Materialien
# ------------------------------------------------------------
class Texturen:
    def __init__(self, archiv):
        self.archiv = archiv
        self.cache = {}
        self.fehlend = []

    def hole(self, name):
        """(bpy Image oder None, mit_alpha, txi)"""
        k = name.lower()
        if k in self.cache:
            return self.cache[k]
        bild = None
        roh = self.archiv.hole(k, ar.TYP_TPC)
        txi = ""
        try:
            if roh is not None:
                bild = tx.lies_tpc(roh)
                txi = bild.txi
            else:
                roh = self.archiv.hole(k, ar.TYP_TGA)
                if roh is not None:
                    bild = tx.lies_tga(roh)
                    t = self.archiv.hole(k, ar.TYP_TXI)
                    txi = t.decode("latin-1") if t else ""
        except ValueError as e:
            print("KOTOR Import: texture %s: %s" % (k, e))
            bild = None
        if bild is None:
            self.fehlend.append(k)
            self.cache[k] = (None, False, "")
            return self.cache[k]
        img = None
        for i in bpy.data.images:
            if i.get("kotor_textur") == k and tuple(i.size) == (bild.breite, bild.hoehe):
                img = i
                break
        if img is None:
            img = bpy.data.images.new(k, bild.breite, bild.hoehe, alpha=True)
            img.pixels.foreach_set((bild.rgba.astype(np.float32) / 255.0).ravel())
            img.update()
            try:
                img.pack()
            except RuntimeError as e:
                print("KOTOR Import: could not pack %s: %s" % (k, e))
            img["kotor_textur"] = k
        self.cache[k] = (img, bild.mit_alpha, txi)
        return self.cache[k]


def baue_material(name, img, deckkraft, diffus):
    schl = name.lower() + ("|a" if deckkraft else "")
    for m in bpy.data.materials:
        if m.get("kotor_material") == schl:
            return m
    m = bpy.data.materials.new(name)
    m["kotor_material"] = schl
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        aus = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs[0], aus.inputs[0])
    # Das Spiel zeichnet keine Rueckseiten; doppelseitige Teile (Robenlappen) sind
    # zwei deckungsgleiche Flaechenlagen - ohne Culling flackern sie ineinander.
    m.use_backface_culling = True
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.8
    if img is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        t.location = (bsdf.location.x - 320, bsdf.location.y)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        if deckkraft:
            nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
            if hasattr(m, "surface_render_method"):        # 4.2+ (EEVEE Next)
                m.surface_render_method = "DITHERED"
            else:
                m.blend_method = "CLIP"
                m.alpha_threshold = 0.5
            if hasattr(m, "shadow_method"):
                try:
                    m.shadow_method = "CLIP"
                except (AttributeError, TypeError):
                    pass
        m.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    else:
        bsdf.inputs["Base Color"].default_value = (diffus[0], diffus[1], diffus[2], 1.0)
        m.diffuse_color = (diffus[0], diffus[1], diffus[2], 1.0)
    return m


# ------------------------------------------------------------
#  Netze. Das Spiel trennt Vertices an UV-Naehten; Blender kennt UVs je
#  Ecke. Gleiche Lage + gleiche Normale + gleiche Gewichte werden deshalb zu
#  EINEM Vertex verschweisst - dann glaettet die Flaeche ueber die Naht, und
#  harte Kanten (gleiche Lage, andere Normale) bleiben getrennt.
# ------------------------------------------------------------
def schweisse(n):
    d = n.daten
    zahl = d.vertices
    teile = [np.rint(d.pos * 1e5).astype(np.int64)]
    if d.normale is not None:
        teile.append(np.rint(d.normale * 1e3).astype(np.int64))
    if d.skin and n.skin_knoten is not None:
        teile.append(n.skin_knoten.astype(np.int64))
        teile.append(np.rint(d.gewicht * 1e3).astype(np.int64))
    schl = np.concatenate(teile, axis=1)
    _, erster, geo = np.unique(schl, axis=0, return_index=True, return_inverse=True)
    # Reihenfolge wie im Spiel (erster Vorkommen), nicht nach Schluessel sortiert
    ordnung = np.argsort(erster)
    rang = np.empty_like(ordnung)
    rang[ordnung] = np.arange(len(ordnung))
    return rang[geo.ravel()], erster[ordnung]


def baue_mesh(n, name, bones, starr_bone):
    """bpy Mesh + Gewichtsliste [(vertex, bone, gewicht)]"""
    d = n.daten
    geo, erster = schweisse(n)
    verts = d.pos[erster]
    tris = geo[d.dreiecke]
    gut = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    # doppelte Dreiecke (gleiche drei Vertices) mag Blender nicht
    schl = np.sort(tris, axis=1)
    _, einmal = np.unique(schl, axis=0, return_index=True)
    doppelt = np.ones(len(tris), dtype=bool)
    doppelt[einmal] = False
    gut &= ~doppelt
    spiel_ecken = d.dreiecke[gut]
    tris = tris[gut]

    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(len(tris) * 3)
    me.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    me.polygons.add(len(tris))
    me.polygons.foreach_set("loop_start", np.arange(0, len(tris) * 3, 3, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(tris), 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(len(tris), dtype=bool))
    for nr, uv in ((0, d.uv0), (1, d.uv1)):
        if uv is None:
            continue
        lay = me.uv_layers.new(name="UVMap" if nr == 0 else "Lightmap")
        lay.data.foreach_set("uv", uv[spiel_ecken.ravel()].astype(np.float32).ravel())
    me.validate(clean_customdata=False)
    me.update()

    gewichte = []
    if d.skin and n.skin_knoten is not None:
        for g, i in enumerate(erster):
            for a in range(4):
                b = int(n.skin_knoten[i, a])
                w = float(d.gewicht[i, a])
                if b >= 0 and w > 0.0 and bones[b] is not None:
                    gewichte.append((g, bones[b], w))
    elif starr_bone is not None:
        gewichte = [(g, starr_bone, 1.0) for g in range(len(verts))]
    return me, gewichte, len(tris)


# ------------------------------------------------------------
#  Figur in die Szene
# ------------------------------------------------------------
def modus_objekt(context):
    if context.view_layer.objects.active is not None and context.view_layer.objects.active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def baue_szene(context, archiv, f, titel, mit_texturen=True):
    """Armature-Objekt; Bericht als zweiter Wert."""
    modus_objekt(context)
    welt = []
    for k in f.knoten:
        lokal = lage_matrix(k.pos, k.rot)
        welt.append(welt[k.eltern] @ lokal if k.eltern >= 0 else lokal)
    ist_bone = bone_knoten(f)
    skelett = skelett_knoten(f)
    ausr = bone_ausrichtung(f, welt, ist_bone)

    sammlung = bpy.data.collections.new("KOTOR " + titel)
    context.scene.collection.children.link(sammlung)
    arm = bpy.data.armatures.new(titel)
    arm_obj = bpy.data.objects.new(titel, arm)
    sammlung.objects.link(arm_obj)
    arm_obj.rotation_euler = (0.0, 0.0, math.pi)     # KOTOR +Y -> Blender -Y (vorn)
    arm.display_type = "STICK"
    try:
        arm_obj.show_in_front = True
    except AttributeError:
        pass

    for o in context.view_layer.objects:
        o.select_set(False)
    context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    sammel_skelett = arm.collections.new("Skeleton")
    sammel_haken = arm.collections.new("Hooks")
    namen = [None] * len(f.knoten)
    ebs = [None] * len(f.knoten)
    for i, k in enumerate(f.knoten):
        if not ist_bone[i]:
            continue
        eb = arm.edit_bones.new(k.name)
        m, laenge = ausr[i]
        eb.head = (0.0, 0.0, 0.0)
        eb.tail = (0.0, laenge, 0.0)
        eb.matrix = m
        if k.eltern >= 0 and ebs[k.eltern] is not None:
            eb.parent = ebs[k.eltern]
        (sammel_skelett if skelett[i] or i == 0 else sammel_haken).assign(eb)
        ebs[i] = eb
        namen[i] = eb.name
    bpy.ops.object.mode_set(mode="OBJECT")

    # C je Bone (Knoten -> Bone) aus der tatsaechlichen Ruhelage zurueckrechnen
    korrektur = {}
    for i, nm in enumerate(namen):
        if nm is None:
            continue
        b = arm.bones[nm]
        c = welt[i].inverted() @ b.matrix_local
        korrektur[nm] = c.to_quaternion().normalized()
        b["kotor_knoten"] = f.knoten[i].name
    arm_obj["kotor_rig"] = 1
    arm_obj["kotor_koerper"] = f.koerper
    arm_obj["kotor_kopf"] = f.kopf
    arm_obj["kotor_textur"] = f.textur_ersatz
    arm_obj["kotor_titel"] = titel
    arm_obj["kotor_version"] = VERSION
    arm_obj["kotor_blick"] = "-Y"
    for nm, q in korrektur.items():
        arm.bones[nm]["kotor_c"] = tuple(q)

    # ---- Netze ----
    texturen = Texturen(archiv)
    zahl_netze = zahl_verts = zahl_tris = zahl_skin = zahl_starr = 0
    for n in f.netze:
        i = n.knoten
        starr_bone = None if n.daten.skin else namen[i]
        me, gewichte, tris = baue_mesh(n, n.name, namen, starr_bone)
        ob = bpy.data.objects.new(n.name, me)
        sammlung.objects.link(ob)
        ob.parent = arm_obj
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.matrix_basis = welt[i]
        ob["kotor_knoten"] = f.knoten[i].name
        gruppen = {}
        for g, bone, w in gewichte:
            vg = gruppen.get(bone)
            if vg is None:
                vg = gruppen[bone] = ob.vertex_groups.new(name=bone)
            vg.add([g], w, "REPLACE")
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = arm_obj
        if n.daten.skin:
            zahl_skin += 1
        else:
            zahl_starr += 1
        zahl_netze += 1
        zahl_verts += len(me.vertices)
        zahl_tris += tris

        # Material
        img, alpha, txi = (None, False, "")
        if mit_texturen and n.textur:
            img, alpha, txi = texturen.hole(n.textur)
        deck = bool(img is not None and alpha and (n.daten.transparenz != 0 or tx.txi_wert(txi, "blending") == "punchthrough"
                                                  or tx.txi_wert(txi, "decal") == "1"))
        mat = baue_material(n.textur or ("kotor_" + n.name), img, deck, n.daten.diffus)
        me.materials.append(mat)
        if not n.daten.rendern:
            ob.hide_render = True

    context.view_layer.update()                      # Pose anlegen (noetig vor Actions ab 4.4)
    for o in context.view_layer.objects:
        o.select_set(False)
    arm_obj.select_set(True)
    context.view_layer.objects.active = arm_obj
    bericht = ("%s: %d bones, %d meshes (%d vertices, %d triangles; %d skinned, %d rigid), %d textures%s, %d animations available"
               % (titel, len(arm.bones), zahl_netze, zahl_verts, zahl_tris, zahl_skin, zahl_starr,
                  len([v for v in texturen.cache.values() if v[0] is not None]),
                  (" (%d missing: %s)" % (len(texturen.fehlend), ", ".join(texturen.fehlend[:5]))) if texturen.fehlend else "",
                  len(f.animationen)))
    return arm_obj, bericht

# ============================================================
#  animation.py - KOTOR-Animationen als Blender-Actions
#
#  Je Animation eine Action "<Figur>|<name>" (Fake-User, bleibt im .blend).
#  Keys in Bildern bei 30 fps (KOTOR rechnet in Sekunden), linear wie im Spiel.
#  Ereignisse (snd_footstep, hit ...) werden Pose-Marker der Action.
#
#  UMRECHNUNG Knoten -> Bone: L = Ruhelage des Knotens (lokal), A = Lage im
#  Clip, C = feste Drehung Knoten -> Bone (szene.py). Blender setzt
#  pose = Eltern-pose * (Ruhe relativ) * basis; daraus folgt
#      basis = C^-1 * L^-1 * A * C
#  und weil C eine reine Drehung ist, trennt sich das sauber:
#      Drehung  = c^-1 * qL^-1 * q(t) * c
#      Position = (c^-1 * qL^-1) angewandt auf (p(t) - pL)
#  Dreh- und Positionskeys behalten so ihre eigenen Zeiten.
#
#  BLENDER 4.4+: Actions haben Slots/Ebenen ("slotted actions"), ab 5.0 gibt
#  es Action.fcurves nicht mehr. Die F-Curves kommen dann in die Channelbag
#  des Slots. Vor dem Zuweisen muss das Armature eine Pose haben (sonst
#  stuerzt Blender ab - gemessen 4.4.3, 5.0.0, 5.2.2).
# ============================================================
import bpy
import numpy as np
from mathutils import Quaternion, Vector

from .kt import figur as fg

FPS = 30


def hat_slots():
    return bpy.app.version >= (4, 4, 0)


class Kurven:
    """F-Curves einer neuen Action, fuer alte und neue Blender gleich."""

    def __init__(self, action, obj):
        self.gruppen = {}
        if hat_slots():
            self.slot = action.slots.new(id_type="OBJECT", name=obj.name)
            strip = action.layers.new("Layer").strips.new(type="KEYFRAME")
            bag = strip.channelbag(self.slot, ensure=True)
            self._fc, self._gr = bag.fcurves, bag.groups
        else:
            self.slot = None
            self._fc, self._gr = action.fcurves, action.groups

    def neu(self, pfad, index, gruppe, frames, werte):
        fc = self._fc.new(pfad, index=index)
        g = self.gruppen.get(gruppe)
        if g is None:
            g = self.gruppen[gruppe] = self._gr.new(gruppe)
        fc.group = g
        n = len(frames)
        fc.keyframe_points.add(n)
        co = np.empty(n * 2, dtype=np.float32)
        co[0::2] = frames
        co[1::2] = werte
        fc.keyframe_points.foreach_set("co", co)
        fc.keyframe_points.foreach_set("interpolation", np.ones(n, dtype=np.int32))    # LINEAR
        fc.update()
        return fc


def weise_zu(obj, action):
    """Action zuweisen (mit Slot ab 4.4)."""
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = action
    if hat_slots() and obj.animation_data.action_slot is None and len(action.slots) > 0:
        obj.animation_data.action_slot = action.slots[0]


def rig_daten(arm_obj):
    """Knotenname (klein) -> (Bone-Name, c, qL, pL) aus den gespeicherten Bone-Eigenschaften."""
    aus = {}
    for b in arm_obj.data.bones:
        k = b.get("kotor_knoten")
        c = b.get("kotor_c")
        if k is None or c is None:
            continue
        aus[k.lower()] = (b.name, Quaternion(tuple(c)))
    return aus


def lade(context, cache, f, arm_obj, namen, fortschritt=None):
    """Actions anlegen; (Liste der Actions, Fehlerliste)."""
    rig = rig_daten(arm_obj)
    titel = arm_obj.get("kotor_titel", arm_obj.name)
    actions, fehler = [], []
    # Ruhelage und C je Figurknoten mit Bone
    bones = []
    for i, k in enumerate(f.knoten):
        r = rig.get(k.name.lower())
        if r is None:
            bones.append(None)
            continue
        qL = Quaternion(k.rot)
        bones.append((r[0], r[1], qL, Vector(k.pos)))
    for nr, name in enumerate(namen):
        if fortschritt:
            fortschritt(nr)
        try:
            a = fg.lade_animation(cache, f, name)
        except ValueError as e:
            fehler.append(str(e))
            continue
        alt = bpy.data.actions.get("%s|%s" % (titel, a.name))
        if alt is not None and alt.get("kotor_rig") == titel:
            bpy.data.actions.remove(alt)
        act = bpy.data.actions.new("%s|%s" % (titel, a.name))
        act.use_fake_user = True
        act["kotor_rig"] = titel
        act["kotor_anim"] = a.name
        act["kotor_herkunft"] = a.herkunft
        jka = fg.jka_anim_name(a.name)
        if jka:
            act["jka_name"] = jka
        ende = max(a.laenge * FPS, 1.0)
        act.use_frame_range = True
        act.frame_start = 0.0
        act.frame_end = ende
        kurven = Kurven(act, arm_obj)
        spur_von = {s.knoten: s for s in a.spuren}
        for i, b in enumerate(bones):
            if b is None:
                continue
            bname, c, qL, pL = b
            pfad = 'pose.bones["%s"]' % bname.replace('"', '\\"')
            s = spur_von.get(i)
            # Drehung
            if s is not None and s.zeit_rot:
                links = c.inverted() @ qL.inverted()
                werte = []
                letzte = None
                for q in s.rot:
                    r = links @ Quaternion(q) @ c
                    if letzte is not None and r.dot(letzte) < 0.0:
                        r.negate()
                    letzte = r
                    werte.append(tuple(r))
                werte = np.array(werte)
                frames = np.array(s.zeit_rot) * FPS
            else:
                werte = np.array([[1.0, 0.0, 0.0, 0.0]])
                frames = np.array([0.0])
            for ax in range(4):
                kurven.neu(pfad + ".rotation_quaternion", ax, bname, frames, werte[:, ax])
            # Position
            if s is not None and s.zeit_pos:
                m = (c.inverted() @ qL.inverted()).to_matrix()
                werte = np.array([tuple(m @ (Vector(p) - pL)) for p in s.pos])
                frames = np.array(s.zeit_pos) * FPS
            else:
                werte = np.zeros((1, 3))
                frames = np.array([0.0])
            for ax in range(3):
                kurven.neu(pfad + ".location", ax, bname, frames, werte[:, ax])
        for t, ev in a.ereignisse:
            mk = act.pose_markers.new(ev)
            mk.frame = int(round(t * FPS))
        actions.append(act)
    return actions, fehler


def zeige(context, arm_obj, action):
    """Action aufs Rig legen und die Szene auf ihren Bereich stellen."""
    context.view_layer.update()
    weise_zu(arm_obj, action)
    sc = context.scene
    if sc.render.fps != FPS or sc.render.fps_base != 1.0:
        sc.render.fps = FPS
        sc.render.fps_base = 1.0
    sc.frame_start = 0
    sc.frame_end = max(1, int(round(action.frame_end)))
    sc.frame_set(0)


def ruhelage(context, arm_obj):
    if arm_obj.animation_data is not None:
        arm_obj.animation_data.action = None
    for pb in arm_obj.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)
    context.view_layer.update()

# ============================================================
#  mdl.py - Binaere Modelle (MDL + MDX) der Odyssey-Engine, Port von ktmdl.cpp
#
#  Alle Versaetze im MDL zaehlen ab Byte 12 (nach dem Dateikopf
#  0, Groesse MDL, Groesse MDX). Vertexdaten liegen in der MDX.
#
#  Geometriekopf (80): 2 Funktionszeiger, Name[32], Wurzelknoten,
#    Knotenzahl, ..., Geometrieart (2 Modell, 5 Animation) an 76.
#  Modellkopf ab 80: Klassifikation, ..., Animationsliste (88),
#    Huelle, Radius, Animationsskala (132), Supermodell[32] (136),
#    ..., Namensliste (184).
#  Knotenkopf (80): Flags u16, Supernummer u16, Namensindex u16,
#    Eltern (12), Position (16), Drehung w x y z (28),
#    Kinder (44), Controller (56, je 16 Byte), Controllerdaten (68).
#  Meshkopf (K1: 332 Byte, K2: 340) direkt danach, Skinkopf (100) dahinter.
#
#  Am Spiel gemessen (siehe docs/DEVELOPMENT.md):
#   * Drehung: Standard-Quaternion, Welt = Eltern * T(pos) * R(q) (Spaltenvektoren).
#   * Skin: Bone-Index im Vertex -> boneMap rueckwaerts -> Knotennummer in
#     DATEIREIHENFOLGE (Tiefensuche), nicht der Namensindex.
#   * Animation: Drehungen absolut (x y z w), Positionen sind DELTAS zur Ruhelage.
# ============================================================
import math
import struct

import numpy as np

NF_HEADER, NF_LIGHT, NF_EMITTER, NF_CAMERA = 0x001, 0x002, 0x004, 0x008
NF_REFERENCE, NF_MESH, NF_SKIN, NF_ANIM = 0x010, 0x020, 0x040, 0x080
NF_DANGLY, NF_AABB, NF_SABER = 0x100, 0x200, 0x800

K1_MODELL = 4273776     # Funktionszeiger KOTOR 1, PC (gemessen)
K2_MODELL = 4285200     # KOTOR 2, PC (xoreos/MDLOps)


class Leser:
    """Little-Endian lesen. Ein Zugriff ausserhalb setzt ok=False und liefert 0."""

    def __init__(self, daten, start=0):
        self.d = daten
        self.s = start
        self.n = max(0, len(daten) - start)
        self.ok = True

    def passt(self, o, laenge):
        if o < 0 or o > self.n or laenge > self.n - o:
            self.ok = False
            return False
        return True

    def _u(self, fmt, o, groesse):
        if not self.passt(o, groesse):
            return 0
        return struct.unpack_from(fmt, self.d, self.s + o)[0]

    def u8(self, o):
        return self._u("<B", o, 1)

    def u16(self, o):
        return self._u("<H", o, 2)

    def u32(self, o):
        return self._u("<I", o, 4)

    def i32(self, o):
        return self._u("<i", o, 4)

    def f32(self, o):
        return self._u("<f", o, 4)

    def str(self, o, laenge):
        if o >= self.n:
            self.ok = False
            return ""
        b = self.d[self.s + o:self.s + o + min(laenge, self.n - o)]
        e = b.find(b"\0")
        return (b[:e] if e >= 0 else b).decode("latin-1")

    def floats(self, o, zahl):
        if not self.passt(o, zahl * 4):
            return None
        return np.frombuffer(self.d, dtype="<f4", count=zahl, offset=self.s + o).astype(np.float64)


class Netz:
    def __init__(self):
        self.pos = None            # (n, 3) im Knotenraum (Meter)
        self.normale = None        # (n, 3) oder None
        self.uv0 = None            # (n, 2) oder None
        self.uv1 = None            # (n, 2) Lightmap oder None
        self.dreiecke = None       # (m, 3) int
        self.textur0 = ""
        self.textur1 = ""
        self.diffus = (0.8, 0.8, 0.8)
        self.ambient = (0.2, 0.2, 0.2)
        self.transparenz = 0
        self.rendern = True
        self.schatten = False
        self.dangly = False
        # Skin: je Vertex 4 Knotennummern in Dateireihenfolge (-1 = leer) und 4 Gewichte.
        self.skin = False
        self.bone_knoten = None    # (n, 4) int
        self.gewicht = None        # (n, 4) float
        self.bind_q = None         # (k, 4) w x y z je Knotennummer
        self.bind_t = None         # (k, 3)

    @property
    def vertices(self):
        return 0 if self.pos is None else len(self.pos)


class Spur:
    def __init__(self):
        self.zeit_pos, self.pos = [], []     # pos: [x, y, z] je Key (in Animationen ein Delta)
        self.zeit_rot, self.rot = [], []     # rot: [w, x, y, z] je Key

    def leer(self):
        return not self.zeit_pos and not self.zeit_rot


class Knoten:
    def __init__(self):
        self.name = ""
        self.flags = 0
        self.name_index = 0
        self.eltern = -1
        self.pos = (0.0, 0.0, 0.0)
        self.rot = (1.0, 0.0, 0.0, 0.0)      # w x y z
        self.netz = -1
        self.kinder = []
        self.spur = Spur()


class Animation:
    def __init__(self):
        self.name = ""
        self.anim_root = ""
        self.laenge = 0.0
        self.uebergang = 0.0
        self.ereignisse = []                 # (zeit, name)
        self.knoten = []


class Modell:
    def __init__(self):
        self.name = ""
        self.supermodell = ""
        self.klassifikation = 0
        self.anim_skala = 1.0
        self.kotor2 = False
        self.namen = []
        self.knoten = []
        self.netze = []
        self.animationen = []

    def finde(self, name):
        n = name.lower()
        for i, k in enumerate(self.knoten):
            if k.name.lower() == n:
                return i
        return -1

    def finde_animation(self, name):
        n = name.lower()
        for a in self.animationen:
            if a.name.lower() == n:
                return a
        return None


def _ohne_null(s):
    return "" if s.lower() == "null" else s


class _Kontext:
    def __init__(self, b, x, m):
        self.b = b
        self.x = x
        self.m = m
        self.besucht = set()


def _lies_controller(k, ko, spur):
    b = k.b
    ct_off, ct_zahl = b.u32(ko + 56), b.u32(ko + 60)
    cd_off, cd_zahl = b.u32(ko + 68), b.u32(ko + 72)
    if ct_zahl == 0 or ct_zahl > 4096 or cd_zahl > (1 << 24):
        return
    if not b.passt(cd_off, cd_zahl * 4):
        return
    werte = struct.unpack_from("<%df" % cd_zahl, b.d, b.s + cd_off)
    roh = struct.unpack_from("<%dI" % cd_zahl, b.d, b.s + cd_off)
    for c in range(ct_zahl):
        co = ct_off + c * 16
        typ = b.u32(co)
        zeilen = b.u16(co + 6)
        zeit_idx = b.u16(co + 8)
        daten_idx = b.u16(co + 10)
        spalten = b.u8(co + 12)
        if zeilen == 0 or zeit_idx + zeilen > cd_zahl:
            continue
        bezier = (spalten & 0x10) != 0
        n = spalten & 0x0F
        if typ == 8:                                   # Position
            if n < 3:
                continue
            schritt = n * 3 if bezier else n
            if daten_idx + (zeilen - 1) * schritt + 3 > cd_zahl:
                continue
            for r in range(zeilen):
                d = daten_idx + r * schritt
                spur.zeit_pos.append(werte[zeit_idx + r])
                spur.pos.append((werte[d], werte[d + 1], werte[d + 2]))
        elif typ == 20:                                # Drehung
            if spalten == 2:
                # Gepackt in 32 Bit (11/11/10), wie bei xoreos.
                if daten_idx + zeilen > cd_zahl:
                    continue
                for r in range(zeilen):
                    t = roh[daten_idx + r]
                    qx = 1.0 - (t & 0x7FF) / 1023.0
                    qy = 1.0 - ((t >> 11) & 0x7FF) / 1023.0
                    qz = 1.0 - (t >> 22) / 511.0
                    q2 = qx * qx + qy * qy + qz * qz
                    if q2 < 1.0:
                        qw = -math.sqrt(1.0 - q2)
                    else:
                        l = math.sqrt(q2)
                        qx, qy, qz, qw = qx / l, qy / l, qz / l, 0.0
                    spur.zeit_rot.append(werte[zeit_idx + r])
                    spur.rot.append((qw, qx, qy, qz))
            else:
                if n < 4:
                    continue
                schritt = n * 3 if bezier else n
                if daten_idx + (zeilen - 1) * schritt + 4 > cd_zahl:
                    continue
                for r in range(zeilen):
                    d = daten_idx + r * schritt
                    spur.zeit_rot.append(werte[zeit_idx + r])
                    # Datei: x y z w  ->  bei uns w x y z
                    spur.rot.append((werte[d + 3], werte[d], werte[d + 1], werte[d + 2]))


def _lies_netz(k, m, flags, netz):
    b, x = k.b, k.x
    k2 = k.m.kotor2
    mesh_groesse = 340 if k2 else 332

    fl_off, fl_zahl = b.u32(m + 8), b.u32(m + 12)
    netz.diffus = tuple(b.f32(m + 60 + 4 * i) for i in range(3))
    netz.ambient = tuple(b.f32(m + 72 + 4 * i) for i in range(3))
    netz.transparenz = b.u32(m + 84)
    netz.textur0 = _ohne_null(b.str(m + 88, 32))
    netz.textur1 = _ohne_null(b.str(m + 120, 32))
    schritt = b.u32(m + 252)
    off = [b.i32(m + 260 + 4 * i) for i in range(11)]
    v_zahl = b.u16(m + 304)
    netz.schatten = b.u8(m + 311) != 0
    netz.rendern = b.u8(m + 313) != 0
    mdx_start = b.u32(m + (332 if k2 else 324))
    vert_off = b.u32(m + (336 if k2 else 328))
    netz.dangly = (flags & NF_DANGLY) != 0

    if 0 < fl_zahl < (1 << 20) and b.passt(fl_off, fl_zahl * 32):
        # je Flaeche 32 Byte, die drei Vertexnummern ab Byte 26
        roh = np.ndarray(shape=(fl_zahl, 3), dtype="<u2", buffer=b.d, offset=b.s + fl_off + 26, strides=(32, 2))
        d = roh.astype(np.int64)
        gut = (d < v_zahl).all(axis=1)
        netz.dreiecke = d[gut]
    else:
        netz.dreiecke = np.zeros((0, 3), dtype=np.int64)

    mit_mdx = x.n > 0 and schritt > 0 and off[0] >= 0 and x.passt(mdx_start, v_zahl * schritt)

    def feld(o, breite):
        # Vertexfeld ab Versatz o, `breite` floats je Vertex, Schritt `schritt` Byte.
        if v_zahl == 0:
            return np.zeros((0, breite))
        if o + breite * 4 > schritt and v_zahl > 0:
            return None
        return np.ndarray(shape=(v_zahl, breite), dtype="<f4", buffer=x.d,
                          offset=mdx_start + o, strides=(schritt, 4)).astype(np.float64)

    if mit_mdx:
        netz.pos = feld(off[0], 3)
        if off[1] >= 0:
            netz.normale = feld(off[1], 3)
        if off[3] >= 0:
            netz.uv0 = feld(off[3], 2)
        if off[4] >= 0:
            netz.uv1 = feld(off[4], 2)
    elif b.passt(vert_off, v_zahl * 12):
        netz.pos = b.floats(vert_off, v_zahl * 3).reshape(-1, 3)
    else:
        netz.pos = np.zeros((0, 3))
        netz.dreiecke = np.zeros((0, 3), dtype=np.int64)
    if netz.pos is None:
        netz.pos = np.zeros((0, 3))
        netz.dreiecke = np.zeros((0, 3), dtype=np.int64)

    if (flags & NF_SKIN) and mit_mdx:
        e = m + mesh_groesse
        w_off, i_off = b.u32(e + 12), b.u32(e + 16)
        bm_off, bm_zahl = b.u32(e + 20), b.u32(e + 24)
        # boneMap rueckwaerts: lokaler Bone -> Knotennummer (Dateireihenfolge).
        lokal_zu_knoten = []
        if 0 < bm_zahl < 65536 and b.passt(bm_off, bm_zahl * 4):
            bm = struct.unpack_from("<%df" % bm_zahl, b.d, b.s + bm_off)
            for i, f in enumerate(bm):
                if f < 0.0:
                    continue
                lokal = int(f + 0.5)
                if lokal >= 4096:
                    continue
                if len(lokal_zu_knoten) <= lokal:
                    lokal_zu_knoten += [-1] * (lokal + 1 - len(lokal_zu_knoten))
                lokal_zu_knoten[lokal] = i
        else:
            lokal_zu_knoten = [b.u16(e + 64 + i * 2) for i in range(16)]
        q_off, q_zahl = b.u32(e + 28), b.u32(e + 32)
        t_off, t_zahl = b.u32(e + 40), b.u32(e + 44)
        if q_zahl == t_zahl and 0 < q_zahl < 65536 and b.passt(q_off, q_zahl * 16) and b.passt(t_off, t_zahl * 12):
            netz.bind_q = b.floats(q_off, q_zahl * 4).reshape(-1, 4)
            netz.bind_t = b.floats(t_off, t_zahl * 3).reshape(-1, 3)
        if w_off < schritt and i_off < schritt and w_off + 16 <= schritt and i_off + 16 <= schritt:
            netz.skin = True
            w = feld(w_off, 4)
            bi = feld(i_off, 4)
            tab = np.array(lokal_zu_knoten + [-1], dtype=np.int64)     # letzter Eintrag: ungueltig
            lokal = np.floor(bi + 0.5).astype(np.int64)
            gueltig = (w > 0.0) & (bi >= 0.0) & (lokal < len(lokal_zu_knoten))
            lokal = np.where(gueltig, lokal, len(lokal_zu_knoten))
            kn = tab[lokal]
            gueltig &= kn >= 0
            netz.bone_knoten = np.where(gueltig, kn, -1)
            netz.gewicht = np.where(gueltig, w, 0.0)


def _lies_knoten(k, o, eltern, aus, geometrie, tiefe):
    b = k.b
    if tiefe > 256 or not b.passt(o, 80) or o in k.besucht:
        return -1
    k.besucht.add(o)
    n = Knoten()
    n.flags = b.u16(o)
    n.name_index = b.u16(o + 4)
    n.eltern = eltern
    n.name = k.m.namen[n.name_index] if n.name_index < len(k.m.namen) else "node%d" % n.name_index
    n.pos = tuple(b.f32(o + 16 + 4 * i) for i in range(3))
    n.rot = tuple(b.f32(o + 28 + 4 * i) for i in range(4))
    _lies_controller(k, o, n.spur)
    ki_off, ki_zahl = b.u32(o + 44), b.u32(o + 48)

    index = len(aus)
    if geometrie and (n.flags & NF_MESH) and not (n.flags & (NF_SABER | NF_AABB)):
        netz = Netz()
        _lies_netz(k, o + 80, n.flags, netz)
        n.netz = len(k.m.netze)
        k.m.netze.append(netz)
    aus.append(n)
    if eltern >= 0:
        aus[eltern].kinder.append(index)
    if 0 < ki_zahl < 4096 and b.passt(ki_off, ki_zahl * 4):
        for i in range(ki_zahl):
            _lies_knoten(k, b.u32(ki_off + i * 4), index, aus, geometrie, tiefe + 1)
    return index


def lies_modell(mdl, mdx, mit_animationen=True):
    """Modell; ValueError mit Grund bei kaputten Daten."""
    if len(mdl) < 12 + 200:
        raise ValueError("MDL too short")
    if struct.unpack_from("<I", mdl, 0)[0] != 0:
        raise ValueError("MDL: not a binary model (ASCII?)")
    aus = Modell()
    k = _Kontext(Leser(mdl, 12), Leser(mdx or b""), aus)
    b = k.b

    aus.kotor2 = b.u32(0) == K2_MODELL
    aus.name = b.str(8, 32)
    wurzel = b.u32(40)
    if b.u8(76) != 2:
        raise ValueError("MDL: geometry type is not 'model'")
    aus.klassifikation = b.u8(80)
    anim_off, anim_zahl = b.u32(88), b.u32(92)
    aus.anim_skala = b.f32(132)
    if not (aus.anim_skala > 0.0) or aus.anim_skala > 100.0:
        aus.anim_skala = 1.0
    aus.supermodell = _ohne_null(b.str(136, 32))
    namen_off, namen_zahl = b.u32(184), b.u32(188)
    if namen_zahl > 65536:
        raise ValueError("MDL: implausible name count")
    aus.namen = [b.str(b.u32(namen_off + i * 4), 64) for i in range(namen_zahl)]

    _lies_knoten(k, wurzel, -1, aus.knoten, True, 0)
    if not aus.knoten:
        raise ValueError("MDL: no nodes")

    if mit_animationen and anim_zahl < 4096:
        for i in range(anim_zahl):
            o = b.u32(anim_off + i * 4)
            if not b.passt(o, 136) or b.u8(o + 76) != 5:
                continue
            a = Animation()
            a.name = b.str(o + 8, 32)
            a.laenge = b.f32(o + 80)
            a.uebergang = b.f32(o + 84)
            a.anim_root = b.str(o + 88, 32)
            ev_off, ev_zahl = b.u32(o + 120), b.u32(o + 124)
            if ev_zahl < 4096:
                for e in range(ev_zahl):
                    a.ereignisse.append((b.f32(ev_off + e * 36), b.str(ev_off + e * 36 + 4, 32)))
            k.besucht = set()
            _lies_knoten(k, b.u32(o + 40), -1, a.knoten, False, 0)
            aus.animationen.append(a)
    if not b.ok and len(aus.knoten) < 2:
        raise ValueError("MDL: truncated")
    return aus

# ============================================================
#  figur.py - Figuren: Liste, Zusammenbau, Animationen (Port von ktfigur.cpp)
#
#  FIGURENLISTE: appearance.2da, eine Zeile je Erscheinungsbild.
#    modeltype B  Koerper + eigener Kopf. modela..modelj sind die
#                 Kleidungsstufen A..J (texa..texj die Texturen),
#                 normalhead zeigt in heads.2da (Spalte head).
#    F, S, L      ein Modell (modela, sonst race).
#  Texturname im Spiel: texX + "01" (Stufe 1), sonst texX.
#
#  ZUSAMMENBAU: der Kopf ist im Spiel ein eigenes Modell am Knoten
#  "headhook" des Koerpers. Seine oberen Knoten (rootdummy, torso_g,
#  torsoUpr_g) stehen alle im Ursprung - Platzhalter. Hier wird daraus
#  EIN Skelett:
#    * gleicher Name UND gleiche Weltlage wie im Koerper -> derselbe
#      Knoten (necklwr_g, neck_g),
#    * Platzhalter ohne Mesh im Ursprung -> faellt in den Elternknoten,
#    * alles andere (head_g, Gesichtsbones, Augen, Haare) -> neu, unter
#      dem passenden Elternknoten.
#
#  ANIMATIONEN: jedes Modell sucht einen Animationsnamen zuerst bei sich,
#  dann in seinem Supermodell, dessen Supermodell ... Der Kopf sucht in
#  SEINER Kette, seine Spuren gehen fuer seine Knoten vor. Positionskeys sind
#  Deltas zur Ruhelage und werden mit der Animationsskala der Modelle
#  zwischen Figur und Besitzer der Animation multipliziert (S_Female01
#  spielt die Maennerclips von S_Male02 mit 0,944).
# ============================================================
import math

import numpy as np

from . import archiv as ar
from .mdl import lies_modell
from .tabelle import lies_2da


class ModellCache:
    def __init__(self, archiv):
        self.archiv = archiv
        self._modelle = {}
        self.letzter_fehler = ""

    def hole(self, name):
        """Modell oder None (Grund in letzter_fehler)."""
        k = name.lower()
        if k in self._modelle:
            m = self._modelle[k]
            if m is None:
                self.letzter_fehler = "model %s missing or broken" % name
            return m
        m = None
        mdl = self.archiv.hole(k, ar.TYP_MDL)
        if mdl is None:
            self.letzter_fehler = "model %s not found" % name
        else:
            mdx = self.archiv.hole(k, ar.TYP_MDX) or b""
            try:
                m = lies_modell(mdl, mdx)
            except (ValueError, IndexError) as e:
                self.letzter_fehler = "%s: %s" % (name, e)
                m = None
        self._modelle[k] = m
        return m

    def kette(self, name):
        """Modell, Supermodell, dessen Supermodell ... (hoechstens 16, ohne Schleifen)."""
        aus, gesehen, n = [], set(), name
        while n and len(aus) < 16 and n.lower() not in gesehen:
            gesehen.add(n.lower())
            m = self.hole(n)
            if m is None:
                break
            aus.append(m)
            n = m.supermodell
        return aus


# ------------------------------------------------------------
#  Figurenliste
# ------------------------------------------------------------
class Variante:
    def __init__(self, buchstabe, modell, textur):
        self.buchstabe, self.modell, self.textur = buchstabe, modell, textur


class Eintrag:
    def __init__(self):
        self.zeile = -1
        self.label = ""
        self.titel = ""
        self.art = "F"
        self.kategorie = ""      # "party", "npc", "creature", "droid"
        self.varianten = []
        self.standard = 0
        self.kopf = ""


def _kategorie(label, art):
    k = label.lower()
    if k.startswith("party_") or k.startswith("p_"):
        return "party"
    if "droid" in k:
        return "droid"
    if k.startswith("creature") or art in ("S", "L"):
        return "creature"
    return "npc"


def lade_figurenliste(a):
    """Liste der Eintraege; ValueError mit Grund."""
    roh = a.hole("appearance", ar.TYP_2DA)
    if roh is None:
        raise ValueError("appearance.2da not found")
    app = lies_2da(roh)
    roh = a.hole("heads", ar.TYP_2DA)
    try:
        koepfe = lies_2da(roh) if roh else None
    except ValueError:
        koepfe = None
    aus = []
    for z in range(len(app)):
        e = Eintrag()
        e.zeile = z
        e.label = app.wert(z, "label")
        if not e.label:
            continue
        art = app.wert(z, "modeltype")
        e.art = art[0].upper() if art else "F"
        race = app.wert(z, "race")
        if e.art == "B":
            doppelt = set()
            for b in "abcdefghijklmn":                 # K1: A-J, K2 zusaetzlich K-N
                v = Variante(b.upper(), app.wert(z, "model" + b), app.wert(z, "tex" + b))
                if not v.modell or not a.gibt(v.modell, ar.TYP_MDL):
                    continue
                s = v.modell.lower() + "|" + v.textur.lower()
                if s in doppelt:
                    continue
                doppelt.add(s)
                if v.modell.lower() == race.lower():
                    e.standard = len(e.varianten)
                e.varianten.append(v)
            kz = app.wert(z, "normalhead")
            if kz[:1].isdigit() and koepfe is not None:
                ziffern = ""
                for c in kz:
                    if not c.isdigit():
                        break
                    ziffern += c
                kopf = koepfe.wert(int(ziffern), "head")
                if kopf and a.gibt(kopf, ar.TYP_MDL):
                    e.kopf = kopf
        else:
            # racetex: Farbvariante eines Ein-Modell-Eintrags (Hutt 2-4, Droidenfarben;
            # in K2 die einzige Textur von HK-47, Duros ... - dort steht im Modell NULL).
            v = Variante("A", app.wert(z, "modela"), app.wert(z, "texa") or app.wert(z, "racetex"))
            if not v.modell or not a.gibt(v.modell, ar.TYP_MDL):
                v.modell = race
            if v.modell and a.gibt(v.modell, ar.TYP_MDL):
                e.varianten.append(v)
        if not e.varianten:
            continue
        e.titel = e.label.replace("_", " ")
        e.kategorie = _kategorie(e.label, e.art)
        aus.append(e)
    if not aus:
        raise ValueError("appearance.2da: no usable rows")
    return aus


# ------------------------------------------------------------
#  Matrizen (Spaltenvektoren, Welt = Eltern * T * R), 4x4 numpy
# ------------------------------------------------------------
def normiere(q):
    w, x, y, z = q
    l = math.sqrt(w * w + x * x + y * y + z * z)
    if l < 1e-8:
        return (1.0, 0.0, 0.0, 0.0)
    return (w / l, x / l, y / l, z / l)


def aus_lage(p, q):
    w, x, y, z = normiere(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y), p[0]],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x), p[1]],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y), p[2]],
        [0.0, 0.0, 0.0, 1.0]])


def starrinvers(a):
    r = np.eye(4)
    r[:3, :3] = a[:3, :3].T
    r[:3, 3] = -r[:3, :3] @ a[:3, 3]
    return r


def zerlege(a):
    """(pos, quat w x y z) aus einer starren Matrix."""
    m = a
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w, x, y, z = (m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w, x, y, z = (m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w, x, y, z = (m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s
    return (float(m[0, 3]), float(m[1, 3]), float(m[2, 3])), normiere((w, x, y, z))


def weltlagen(m):
    w = []
    for k in m.knoten:
        lokal = aus_lage(k.pos, k.rot)
        w.append(w[k.eltern] @ lokal if k.eltern >= 0 else lokal)
    return w


def ist_sichtbares_netz(m, k):
    if k.netz < 0:
        return False
    n = m.netze[k.netz]
    return n.rendern and n.vertices > 0 and len(n.dreiecke) > 0


def _eindeutig(name, vergeben):
    n = name or "node"
    if n.lower() not in vergeben:
        vergeben.add(n.lower())
        return n
    for i in range(2, 1000):
        v = "%s_%d" % (n, i)
        if v.lower() not in vergeben:
            vergeben.add(v.lower())
            return v
    return n


def _haupt_textur(m):
    """Die haeufigste Farbtextur der sichtbaren Netze eines Modells."""
    zahl = {}
    for k in m.knoten:
        if not ist_sichtbares_netz(m, k):
            continue
        n = m.netze[k.netz]
        if n.textur0:
            zahl[n.textur0.lower()] = zahl.get(n.textur0.lower(), 0) + len(n.dreiecke) * 3
    beste, meist = "", 0
    for t in sorted(zahl):
        if zahl[t] > meist:
            beste, meist = t, zahl[t]
    return beste


# ------------------------------------------------------------
#  Zusammengebaute Figur
# ------------------------------------------------------------
class FKnoten:
    def __init__(self):
        self.name = ""             # in der Figur eindeutig
        self.eltern = -1
        self.pos = (0.0, 0.0, 0.0)
        self.rot = (1.0, 0.0, 0.0, 0.0)
        self.netz = -1             # Index in Figur.netze, -1 = Bone/Helfer
        self.teil = 1              # Bit 0 Koerper, Bit 1 Kopf
        self.quelle = ["", ""]     # Name im Koerper- bzw. Kopfmodell
        self.flags = 0


class FNetz:
    def __init__(self):
        self.name = ""
        self.knoten = -1
        self.daten = None          # mdl.Netz
        self.textur = ""
        self.skin_knoten = None    # (n, 4) FKnoten oder -1 (nur bei Skin)
        self.bind_knoten = []
        self.bind_q = []
        self.bind_t = []


class Figur:
    def __init__(self):
        self.titel = ""
        self.koerper = ""
        self.kopf = ""
        self.textur_ersatz = ""
        self.knoten = []
        self.netze = []
        self.kette = [[], []]
        self.animationen = []

    def finde(self, name):
        n = name.lower()
        for i, k in enumerate(self.knoten):
            if k.name.lower() == n:
                return i
        return -1


def baue_figur(c, koerper, kopf="", textur_ersatz=""):
    """Figur; ValueError mit Grund."""
    f = Figur()
    k = c.hole(koerper)
    if k is None:
        raise ValueError(c.letzter_fehler)
    h = c.hole(kopf) if kopf else None
    f.koerper = k.name or koerper
    f.kopf = (h.name or kopf) if h is not None else ""
    f.textur_ersatz = textur_ersatz
    f.kette[0] = [m.name for m in c.kette(koerper)]
    if h is not None:
        f.kette[1] = [m.name for m in c.kette(kopf)]

    vergeben = set()
    welt = []

    # Farbtextur des Koerpers ersetzen (appearance texX): wie im Spiel texX + "01".
    ersatz = ersetzt = ""
    if textur_ersatz:
        a = c.archiv
        for kandidat in (textur_ersatz + "01", textur_ersatz):
            if a.gibt(kandidat, ar.TYP_TPC) or a.gibt(kandidat, ar.TYP_TGA):
                ersatz = kandidat
                break
        if ersatz:
            ersetzt = _haupt_textur(k)

    def nimm_netz(m, q, fk, teil, abbild):
        if not ist_sichtbares_netz(m, q):
            return
        n = FNetz()
        n.name = f.knoten[fk].name
        n.knoten = fk
        n.daten = m.netze[q.netz]
        n.textur = n.daten.textur0
        # Ersatztextur: die Haupttextur des Koerpers und Netze ohne Textur (NULL) - viele
        # K2-Modelle (HK-47, Duros, Schmuggler) bekommen ihre Textur nur ueber appearance.2da.
        if teil == 0 and ersatz and (n.textur.lower() == ersetzt or not n.textur):
            n.textur = ersatz
        if n.daten.skin:
            # Die Skin-Tabellen zaehlen die Knoten in DATEIREIHENFOLGE (= Modell.knoten),
            # nicht ueber den Namensindex (P_BastilaBB, siehe docs/DEVELOPMENT.md).
            abb = np.array(abbild + [-1], dtype=np.int64)
            bk = n.daten.bone_knoten
            gueltig = (bk >= 0) & (bk < len(abbild))
            n.skin_knoten = np.where(gueltig, abb[np.where(gueltig, bk, len(abbild))], -1)
            bq, bt = n.daten.bind_q, n.daten.bind_t
            for qi, fk2 in zip(bk.ravel(), n.skin_knoten.ravel()):
                qi, fk2 = int(qi), int(fk2)
                if fk2 < 0 or bq is None or qi >= len(bq) or qi >= len(bt) or fk2 in n.bind_knoten:
                    continue
                n.bind_knoten.append(fk2)
                n.bind_q.append(tuple(bq[qi]))
                n.bind_t.append(tuple(bt[qi]))
        f.knoten[fk].netz = len(f.netze)
        f.netze.append(n)

    # ---- Koerper: jeder Knoten wird ein FKnoten ----
    abbild_k = []
    for q in k.knoten:
        fk = FKnoten()
        fk.name = _eindeutig(q.name, vergeben)
        fk.eltern = abbild_k[q.eltern] if q.eltern >= 0 else -1
        fk.pos = tuple(q.pos)
        fk.rot = normiere(q.rot)
        fk.teil = 1
        fk.quelle = [q.name, ""]
        fk.flags = q.flags
        lokal = aus_lage(fk.pos, fk.rot)
        welt.append(welt[fk.eltern] @ lokal if fk.eltern >= 0 else lokal)
        abbild_k.append(len(f.knoten))
        f.knoten.append(fk)
    for i, q in enumerate(k.knoten):
        nimm_netz(k, q, abbild_k[i], 0, abbild_k)

    # ---- Kopf ----
    if h is not None:
        haken = f.finde("headhook")
        if haken < 0:
            haken = 0
        welt_h = weltlagen(h)
        abbild_h = [-1] * len(h.knoten)
        koerper_name = {}
        for i, fk in enumerate(f.knoten):
            koerper_name.setdefault(fk.quelle[0].lower(), i)
        for i, q in enumerate(h.knoten):
            if i == 0 or q.eltern < 0:
                abbild_h[i] = haken
                continue
            eltern = abbild_h[q.eltern]
            ziel = welt[haken] @ welt_h[i]
            gleich = koerper_name.get(q.name.lower())
            sichtbar = ist_sichtbares_netz(h, q)
            if not sichtbar and gleich is not None:
                d = welt[gleich][:3, 3] - ziel[:3, 3]
                if math.sqrt(float(d @ d)) < 0.002 and float(np.abs(welt[gleich][:3, :3] - ziel[:3, :3]).max()) < 0.01:
                    fk = f.knoten[gleich]
                    fk.teil |= 2
                    fk.quelle[1] = q.name
                    abbild_h[i] = gleich
                    continue
            qn = normiere(q.rot)
            im_ursprung = abs(q.pos[0]) < 1e-5 and abs(q.pos[1]) < 1e-5 and abs(q.pos[2]) < 1e-5 and \
                abs(abs(qn[0]) - 1.0) < 1e-5
            if not sichtbar and im_ursprung and gleich is not None:
                abbild_h[i] = eltern                       # Platzhalter
                continue
            fk = FKnoten()
            fk.name = _eindeutig(q.name, vergeben)
            fk.eltern = eltern
            fk.pos, fk.rot = zerlege(starrinvers(welt[eltern]) @ ziel)
            fk.teil = 2
            fk.quelle = ["", q.name]
            fk.flags = q.flags
            welt.append(ziel)
            abbild_h[i] = len(f.knoten)
            f.knoten.append(fk)
        for i in range(1, len(h.knoten)):
            # Netze nur von eigenen Kopfknoten (zusammengelegte sind Bones).
            ziel = abbild_h[i]
            if ziel < 0 or f.knoten[ziel].netz >= 0 or (f.knoten[ziel].teil & 1):
                continue
            nimm_netz(h, h.knoten[i], ziel, 1, abbild_h)

    # ---- Animationsnamen: Koerperkette, dann Kopfkette ----
    gesehen = set()
    for t, start in enumerate((koerper, kopf)):
        if t == 1 and not kopf:
            break
        for m in c.kette(start):
            for a in m.animationen:
                if a.name.lower() not in gesehen:
                    gesehen.add(a.name.lower())
                    f.animationen.append(a.name)
    f.titel = f.koerper
    return f


# ------------------------------------------------------------
#  Animation fuer eine Figur
# ------------------------------------------------------------
class FSpur:
    def __init__(self, knoten):
        self.knoten = knoten
        self.zeit_pos, self.pos = [], []   # pos: absolute lokale Lage (Ruhe + Delta * Skala)
        self.zeit_rot, self.rot = [], []   # rot: w x y z (normiert)


class FAnim:
    def __init__(self):
        self.name = ""
        self.herkunft = ""
        self.laenge = 0.0
        self.skala = 1.0
        self.ereignisse = []
        self.spuren = []


def lade_animation(c, f, name):
    """FAnim; ValueError, wenn die Kette den Namen nicht kennt."""
    a_aus = FAnim()
    a_aus.name = name
    spur_von = {}
    gefunden = False
    for t, start in enumerate((f.koerper, f.kopf)):
        if not start:
            continue
        a, skala, besitzer = None, 1.0, ""
        for m in c.kette(start):
            a = m.finde_animation(name)
            if a is not None:
                besitzer = m.name
                break
            skala *= m.anim_skala
        if a is None:
            continue
        gefunden = True
        if t == 0 or a_aus.laenge < a.laenge:
            a_aus.laenge = a.laenge
        if t == 0:
            a_aus.ereignisse = list(a.ereignisse)
            a_aus.skala = skala
        a_aus.herkunft += (" + " if a_aus.herkunft else "") + besitzer

        ziel = {}
        for i, fk in enumerate(f.knoten):
            if fk.quelle[t]:
                ziel.setdefault(fk.quelle[t].lower(), i)
        for ai, an in enumerate(a.knoten):
            if an.spur.leer():
                continue
            if ai == 0:
                if t == 1:
                    continue                      # Kopfwurzel = headhook, nicht bewegen
                fk = 0
            else:
                fk = ziel.get(an.name.lower())
                if fk is None:
                    continue
            k = f.knoten[fk]
            if fk not in spur_von:
                spur_von[fk] = len(a_aus.spuren)
                a_aus.spuren.append(FSpur(fk))
            s = a_aus.spuren[spur_von[fk]]
            if an.spur.zeit_rot:                  # Kopf ueberschreibt Koerper
                s.zeit_rot = list(an.spur.zeit_rot)
                s.rot = [normiere(q) for q in an.spur.rot]
            if an.spur.zeit_pos:
                s.zeit_pos = list(an.spur.zeit_pos)
                s.pos = [tuple(k.pos[d] + p[d] * skala for d in range(3)) for p in an.spur.pos]
    if not gefunden:
        raise ValueError("animation %s not found in the model chain" % name)
    return a_aus


# ------------------------------------------------------------
#  KOTOR -> Jedi Academy (wie im Max-Plugin, siehe docs/DEVELOPMENT.md)
# ------------------------------------------------------------
_JKA = {
    "cpause1": "BOTH_STAND1", "pause1": "BOTH_STAND1", "cpause2": "BOTH_STAND2", "pause2": "BOTH_STAND2",
    "creadyr": "BOTH_GUARD_IDLE1", "cwalk": "BOTH_WALK1", "walk": "BOTH_WALK1",
    "cwalkinj": "BOTH_WALK2", "walkinj": "BOTH_WALK2", "crun": "BOTH_RUN1", "run": "BOTH_RUN1",
    "chturnl": "BOTH_TURN_LEFT1", "hturnl": "BOTH_TURN_LEFT1", "chturnr": "BOTH_TURN_RIGHT1", "hturnr": "BOTH_TURN_RIGHT1",
    "g0a1": "BOTH_ATTACK1", "g0a2": "BOTH_ATTACK2", "b0a1": "BOTH_ATTACK3", "b0a2": "BOTH_ATTACK4",
    "b0a3": "BOTH_ATTACK5", "b0a4": "BOTH_ATTACK6", "m0a1": "BOTH_MELEE1", "m0a2": "BOTH_MELEE2",
    "cdamages": "BOTH_PAIN1", "cspasm": "BOTH_PAIN2", "spasm": "BOTH_PAIN2",
    "cdie": "BOTH_DEATH1", "die": "BOTH_DEATH1", "die1": "BOTH_DEATH2",
    "cdead": "BOTH_DEAD1", "dead": "BOTH_DEAD1", "dead1": "BOTH_DEAD2",
    "ctaunt": "BOTH_GESTURE1", "taunt": "BOTH_GESTURE1", "cvictory": "BOTH_GESTURE2", "victory": "BOTH_GESTURE2",
    "ckdbck": "BOTH_KNOCKDOWN1", "cgustandb": "BOTH_GETUP1", "sleep": "BOTH_SLEEP1", "choke": "BOTH_CHOKE1",
}


def jka_anim_name(kotor_name):
    return _JKA.get(kotor_name.lower(), "")

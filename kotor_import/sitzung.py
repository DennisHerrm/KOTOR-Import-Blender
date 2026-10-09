# ============================================================
#  sitzung.py - die geoeffneten Spiele fuer die ganze Blender-Sitzung
#
#  Je Spiel ("1" = KOTOR, "2" = KOTOR II) ein Archiv, ein Modellcache und
#  die Figurenliste. Das gewaehlte Spiel steht in wm.kotor_einst.spiel;
#  eine importierte Figur merkt sich ihres (Armature-Eigenschaft kotor_spiel).
# ============================================================
import bpy

from .kt import archiv as ar
from .kt import figur as fg

SPIELE = {"1": "KOTOR", "2": "KOTOR II"}


class _Spiel:
    def __init__(self, archiv, ordner):
        self.archiv = archiv
        self.cache = fg.ModellCache(archiv)
        self.eintraege = fg.lade_figurenliste(archiv)
        self.ordner = ordner


_offen = {}


def prefs():
    a = bpy.context.preferences.addons.get(__package__)
    return a.preferences if a else None


def aktuell():
    try:
        return bpy.context.window_manager.kotor_einst.spiel
    except AttributeError:
        return "1"


def _gemerkt(spiel):
    p = prefs()
    if p is None:
        return ""
    w = p.spielordner2 if spiel == "2" else p.spielordner
    return bpy.path.abspath(w) if w else ""


def spielordner(spiel=None):
    spiel = spiel or aktuell()
    return ar.finde_spielordner(_gemerkt(spiel), spiel)


def oeffne(spiel=None, ordner=None):
    """(Archiv, ModellCache) des Spiels; ValueError mit Grund."""
    spiel = spiel or aktuell()
    if ordner is None:
        s = _offen.get(spiel)
        if s is not None:
            return s.archiv, s.cache
        ordner = spielordner(spiel)
        if not ordner:
            raise ValueError("%s game folder not found - set it in the add-on preferences or the KOTOR panel" % SPIELE[spiel])
    erkannt = ar.spiel_von_ordner(ordner)
    if erkannt and erkannt != spiel:
        raise ValueError("%s holds %s, not %s - pick the other game or another folder" % (ordner, SPIELE[erkannt], SPIELE[spiel]))
    a = ar.Archiv()
    fehler = a.oeffne(ordner)
    if fehler:
        raise ValueError("%s (%s)" % (fehler, ordner))
    _offen[spiel] = _Spiel(a, ordner)
    p = prefs()
    if p is not None:
        if spiel == "2" and p.spielordner2 != ordner:
            p.spielordner2 = ordner
        elif spiel == "1" and p.spielordner != ordner:
            p.spielordner = ordner
    return _offen[spiel].archiv, _offen[spiel].cache


def offen(spiel=None):
    return (spiel or aktuell()) in _offen


def eintraege(spiel=None):
    s = _offen.get(spiel or aktuell())
    return s.eintraege if s else []


def ordner(spiel=None):
    s = _offen.get(spiel or aktuell())
    return s.ordner if s else ""


def neuer_cache(spiel=None):
    """Frischer Modellcache (nach einem Zusatzordner fuer lose .mdl)."""
    s = _offen[spiel or aktuell()]
    s.cache = fg.ModellCache(s.archiv)
    return s.cache


def schliesse(spiel=None):
    """Ein Spiel schliessen; ohne Angabe alle."""
    if spiel is None:
        _offen.clear()
    else:
        _offen.pop(spiel, None)

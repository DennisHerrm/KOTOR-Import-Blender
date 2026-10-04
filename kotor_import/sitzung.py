# ============================================================
#  sitzung.py - ein geoeffnetes Spiel fuer die ganze Blender-Sitzung
# ============================================================
import bpy

from .kt import archiv as ar
from .kt import figur as fg

_archiv = None
_cache = None
_eintraege = []
_ordner = ""


def prefs():
    a = bpy.context.preferences.addons.get(__package__)
    return a.preferences if a else None


def spielordner():
    p = prefs()
    gemerkt = p.spielordner if p else ""
    return ar.finde_spielordner(bpy.path.abspath(gemerkt) if gemerkt else "")


def oeffne(ordner=None):
    """(Archiv, ModellCache); ValueError mit Grund."""
    global _archiv, _cache, _eintraege, _ordner
    if ordner is None:
        ordner = spielordner()
        if not ordner:
            raise ValueError("KOTOR game folder not found - set it in the add-on preferences or the KOTOR panel")
    if _archiv is not None and _ordner.lower() == ordner.lower():
        return _archiv, _cache
    a = ar.Archiv()
    fehler = a.oeffne(ordner)
    if fehler:
        raise ValueError("%s (%s)" % (fehler, ordner))
    _archiv, _cache, _ordner = a, fg.ModellCache(a), ordner
    _eintraege = fg.lade_figurenliste(a)
    p = prefs()
    if p is not None and p.spielordner != ordner:
        p.spielordner = ordner
    return _archiv, _cache


def offen():
    return _archiv is not None


def eintraege():
    return _eintraege


def ordner():
    return _ordner


def neuer_cache():
    """Frischer Modellcache (nach einem Zusatzordner fuer lose .mdl)."""
    global _cache
    _cache = fg.ModellCache(_archiv)
    return _cache


def schliesse():
    global _archiv, _cache, _eintraege, _ordner
    _archiv, _cache, _eintraege, _ordner = None, None, [], ""

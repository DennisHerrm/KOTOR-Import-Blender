# ============================================================
#  tabelle.py - 2DA-Tabellen (appearance.2da, heads.2da), Port von kt2da.cpp
#
#  Binaerform "2DA V2.b": Spaltennamen mit Tab getrennt, Zeilen-
#  beschriftungen, dann je Zelle ein u16-Versatz in einen Block mit
#  nullterminierten Zeichenketten. "****" heisst leer.
#  Die Textform "2DA V2.0" (Mods im Override) wird ebenso gelesen.
# ============================================================
import struct


class Tabelle2da:
    def __init__(self):
        self.spalten = []      # klein geschrieben
        self.zeilen = []

    def spalte(self, name):
        try:
            return self.spalten.index(name.lower())
        except ValueError:
            return -1

    def wert(self, zeile, spalte):
        """Leerer Text fuer fehlende Spalte, fehlende Zeile oder "****"."""
        s = self.spalte(spalte)
        if s < 0 or zeile >= len(self.zeilen) or s >= len(self.zeilen[zeile]):
            return ""
        w = self.zeilen[zeile][s]
        return "" if w == "****" else w

    def __len__(self):
        return len(self.zeilen)


def _zerlege(z):
    felder = []
    i = 0
    while i < len(z):
        while i < len(z) and z[i] in " \t\r":
            i += 1
        if i >= len(z):
            break
        if z[i] == '"':
            e = z.find('"', i + 1)
            e = len(z) if e < 0 else e
            felder.append(z[i + 1:e])
            i = e + 1
        else:
            a = i
            while i < len(z) and z[i] not in " \t\r":
                i += 1
            felder.append(z[a:i])
    return felder


def _lies_text(roh):
    t = Tabelle2da()
    zeilen = roh.decode("latin-1").split("\n")[1:]      # "2DA V2.0"
    kopf = False
    for z in zeilen:
        f = _zerlege(z)
        if not f:
            continue
        if not kopf:
            if f[0].lower() == "default:":
                continue
            t.spalten = [x.lower() for x in f]
            kopf = True
            continue
        r = f[1:len(t.spalten) + 1]
        r += [""] * (len(t.spalten) - len(r))
        t.zeilen.append(r)
    if not kopf:
        raise ValueError("2DA text: no header")
    return t


def lies_2da(roh):
    """Tabelle2da; ValueError bei kaputten Daten."""
    if roh[:8] == b"2DA V2.0":
        return _lies_text(roh)
    if len(roh) < 9 or roh[:8] != b"2DA V2.b":
        raise ValueError("not a 2DA file")
    t = Tabelle2da()
    ende = roh.index(b"\0", 9)
    t.spalten = [s.decode("latin-1").lower() for s in roh[9:ende].split(b"\t") if s]
    p = ende + 1
    zahl = struct.unpack_from("<I", roh, p)[0]
    p += 4
    if zahl > 100000:
        raise ValueError("2DA: implausible row count")
    for _ in range(zahl):                     # Zeilenbeschriftungen
        p = roh.index(b"\t", p) + 1
    zellen = zahl * len(t.spalten)
    versatz = struct.unpack_from("<%dH" % zellen, roh, p)
    p += zellen * 2
    groesse = struct.unpack_from("<H", roh, p)[0]
    p += 2
    daten = roh[p:p + groesse]
    if len(daten) < groesse:
        raise ValueError("2DA: truncated")
    cache = {}
    ns = len(t.spalten)
    for z in range(zahl):
        r = []
        for s in range(ns):
            o = versatz[z * ns + s]
            w = cache.get(o)
            if w is None:
                if o < groesse:
                    e = daten.find(b"\0", o)
                    w = daten[o:e if e >= 0 else groesse].decode("latin-1")
                else:
                    w = ""
                cache[o] = w
            r.append(w)
        t.zeilen.append(r)
    return t

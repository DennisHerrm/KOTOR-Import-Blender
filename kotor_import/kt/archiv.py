# ============================================================
#  archiv.py - Ressourcen aus dem Spielordner (Port von ktarchiv.cpp)
#
#  KOTOR (Odyssey-Engine, BioWare) legt seine Dateien so ab:
#    chitin.key           Verzeichnis: Name + Typ -> BIF-Datei + Index
#    data\*.bif           die eigentlichen Daten (models.bif ~ 950 MB)
#    TexturePacks\*.erf   Texturen als TPC, tpa = hoechste Stufe
#    Override\            lose Dateien, gehen allem vor (Mods)
#
#  Reihenfolge beim Suchen wie im Spiel: Override, dann bei Texturen
#  das Texturpaket, dann chitin.key. Gelesen wird immer nur der
#  Bereich der Ressource - models.bif wird nie ganz geladen.
#
#  KEY V1: 8 Zahl BIF, 12 Zahl Schluessel, 16 Versatz BIF-Tabelle (je 12:
#    Groesse, Namensversatz, Namenslaenge u16, Laufwerke u16), 20 Versatz
#    Schluessel (je 22: Name[16], Typ u16, ID u32 = BIF << 20 | Index)
#  BIFF V1: 8 Zahl variabel, 16 Versatz der Tabelle (je 16: ID, Versatz, Groesse, Typ)
#  ERF V1.0: 16 Zahl, 24 Versatz Schluessel (je 24: Name[16], ID, Typ u16, frei),
#    28 Versatz Ressourcen (je 8: Versatz, Groesse)
# ============================================================
import os
import struct

TYP_TGA = 3
TYP_MDL = 2002
TYP_2DA = 2017
TYP_TXI = 2022
TYP_TPC = 3007
TYP_MDX = 3008

_ENDUNGEN = {"tga": TYP_TGA, "mdl": TYP_MDL, "2da": TYP_2DA, "txi": TYP_TXI, "tpc": TYP_TPC, "mdx": TYP_MDX}


def typ_aus_endung(endung):
    return _ENDUNGEN.get(endung.lower(), 0)


def _cstr(b, o, laenge):
    s = b[o:o + laenge]
    n = s.find(b"\0")
    if n >= 0:
        s = s[:n]
    return s.decode("latin-1")


def _lies_bereich(pfad, versatz, laenge):
    try:
        with open(pfad, "rb") as f:
            f.seek(versatz)
            d = f.read(laenge)
        return d if len(d) == laenge else None
    except OSError:
        return None


def _finde_datei(ordner, *teile):
    """Pfad ohne Ruecksicht auf Gross/klein (K2: data/Models.bif, override) oder None."""
    pfad = ordner
    for t in teile:
        if os.path.exists(os.path.join(pfad, t)):
            pfad = os.path.join(pfad, t)
            continue
        try:
            treffer = next((e.name for e in os.scandir(pfad) if e.name.lower() == t.lower()), None)
        except OSError:
            return None
        if treffer is None:
            return None
        pfad = os.path.join(pfad, treffer)
    return pfad


def ist_spielordner(ordner):
    return bool(ordner) and _finde_datei(ordner, "chitin.key") is not None and \
        _finde_datei(ordner, "data", "models.bif") is not None


def spiel_von_ordner(ordner):
    """"1" (KOTOR), "2" (KOTOR II) oder "" (nicht erkennbar, z. B. ohne Windows-EXE)."""
    if _finde_datei(ordner, "swkotor2.exe"):
        return "2"
    if _finde_datei(ordner, "swkotor.exe"):
        return "1"
    return ""


def _dateien_in(ordner):
    try:
        return [e.name for e in os.scandir(ordner) if e.is_file()]
    except OSError:
        return []


class Archiv:
    def __init__(self):
        self.ordner = ""
        self._bifs = []
        self._erf = None
        self._key = {}         # "name|typ" -> (bif, index)
        self._erf_tab = {}     # "name|typ" -> (versatz, groesse)
        self._override = {}    # "name|typ" -> pfad
        self._bif_tab = {}     # bif -> [(versatz, groesse)]

    @staticmethod
    def _schl(name, typ):
        return "%s|%d" % (name.lower(), typ)

    def oeffne(self, spielordner, texturpaket="tpa"):
        """Liefert "" oder einen Fehlertext."""
        self.__init__()
        ordner = spielordner.rstrip("\\/")
        try:
            with open(os.path.join(ordner, "chitin.key"), "rb") as f:
                k = f.read()
        except OSError:
            return "chitin.key not found"
        if len(k) < 24 or k[:8] != b"KEY V1  ":
            return "chitin.key: not a KEY V1 file"
        zahl_bif, zahl_key, off_bif, off_key = struct.unpack_from("<4I", k, 8)
        if zahl_bif > 4096 or zahl_key > 1000000:
            return "chitin.key: implausible counts"
        try:
            for i in range(zahl_bif):
                _, n_off, n_len = struct.unpack_from("<IIH", k, off_bif + i * 12)
                name = _cstr(k, n_off, n_len).replace("/", "\\")
                teile = name.split("\\")
                self._bifs.append(_finde_datei(ordner, *teile) or os.path.join(ordner, *teile))
            for i in range(zahl_key):
                o = off_key + i * 22
                name = _cstr(k, o, 16)
                typ, rid = struct.unpack_from("<HI", k, o + 16)
                bif = rid >> 20
                if bif >= len(self._bifs):
                    continue
                self._key.setdefault(self._schl(name, typ), (bif, rid & 0x3FFF))   # erster Eintrag gewinnt
        except struct.error:
            return "chitin.key: truncated"

        # ---- Texturpaket (nur TPC) ----
        paket = _finde_datei(ordner, "TexturePacks", "swpc_tex_%s.erf" % texturpaket)
        if paket and os.path.isfile(paket):
            kopf = _lies_bereich(paket, 0, 160)
            if kopf:
                zahl = struct.unpack_from("<I", kopf, 16)[0]
                off_schl, off_res = struct.unpack_from("<II", kopf, 24)
                if zahl < 1000000:
                    schl = _lies_bereich(paket, off_schl, zahl * 24)
                    res = _lies_bereich(paket, off_res, zahl * 8)
                    if schl and res:
                        self._erf = paket
                        for i in range(zahl):
                            typ = struct.unpack_from("<H", schl, i * 24 + 20)[0]
                            self._erf_tab.setdefault(self._schl(_cstr(schl, i * 24, 16), typ),
                                                     struct.unpack_from("<II", res, i * 8))

        # ---- Override ----
        self._lade_lose(_finde_datei(ordner, "Override") or os.path.join(ordner, "Override"), ueberschreiben=False)
        self.ordner = ordner
        return ""

    def _lade_lose(self, ordner, ueberschreiben):
        for datei in _dateien_in(ordner):
            stamm, punkt, endung = datei.rpartition(".")
            if not punkt:
                continue
            typ = typ_aus_endung(endung)
            if typ == 0:
                continue
            s = self._schl(stamm, typ)
            if ueberschreiben or s not in self._override:
                self._override[s] = os.path.join(ordner, datei)

    def zusatz_ordner(self, ordner):
        """Lose Dateien eines weiteren Ordners vor allem anderen (Import einer einzelnen .mdl)."""
        self._lade_lose(ordner, ueberschreiben=True)

    @property
    def offen(self):
        return bool(self.ordner)

    def _bif_tabelle(self, bif):
        if bif in self._bif_tab:
            return self._bif_tab[bif]
        tab = []
        kopf = _lies_bereich(self._bifs[bif], 0, 20)
        if kopf and kopf[:8] == b"BIFFV1  ":
            zahl = struct.unpack_from("<I", kopf, 8)[0]
            off = struct.unpack_from("<I", kopf, 16)[0]
            if zahl <= 1000000:
                roh = _lies_bereich(self._bifs[bif], off, zahl * 16)
                if roh:
                    tab = [struct.unpack_from("<II", roh, i * 16 + 4) for i in range(zahl)]
        self._bif_tab[bif] = tab
        return tab

    def hole(self, name, typ):
        """Bytes der Ressource oder None."""
        if not name:
            return None
        s = self._schl(name, typ)
        p = self._override.get(s)
        if p:
            try:
                with open(p, "rb") as f:
                    return f.read()
            except OSError:
                return None
        if typ == TYP_TPC and self._erf:
            e = self._erf_tab.get(s)
            if e:
                return _lies_bereich(self._erf, e[0], e[1])
        k = self._key.get(s)
        if not k:
            return None
        tab = self._bif_tabelle(k[0])
        if k[1] >= len(tab):
            return None
        versatz, groesse = tab[k[1]]
        if groesse > (512 << 20):
            return None
        return _lies_bereich(self._bifs[k[0]], versatz, groesse)

    def gibt(self, name, typ):
        if not name:
            return False
        s = self._schl(name, typ)
        return s in self._override or (typ == TYP_TPC and s in self._erf_tab) or s in self._key

    def herkunft(self, name, typ):
        s = self._schl(name, typ)
        if s in self._override:
            return "Override"
        if typ == TYP_TPC and s in self._erf_tab and self._erf:
            return os.path.basename(self._erf)
        k = self._key.get(s)
        return os.path.basename(self._bifs[k[0]]) if k else ""

    def zahlen(self):
        return len(self._key), len(self._erf_tab), len(self._override)


# ------------------------------------------------------------
#  Spielordner finden (wie FindeSpielordner im Max-Plugin)
# ------------------------------------------------------------
def finde_spielordner(gemerkt="", spiel="1"):
    """Ordner von KOTOR ("1") oder KOTOR II ("2"): gemerkt, Steam (alle Bibliotheken), GOG."""
    if ist_spielordner(gemerkt) and spiel_von_ordner(gemerkt) in ("", spiel):
        return gemerkt
    steam_name = "Knights of the Old Republic II" if spiel == "2" else "swkotor"
    gog_name = "Star Wars - KotOR2" if spiel == "2" else "Star Wars - KotOR"
    kandidaten = []
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    steam = os.path.join(pf86, "Steam")
    kandidaten.append(os.path.join(steam, "steamapps", "common", steam_name))
    # Weitere Steam-Bibliotheken aus libraryfolders.vdf ("path" "D:\\SteamLibrary").
    try:
        with open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), "r", encoding="utf-8", errors="replace") as f:
            t = f.read()
        p = 0
        while True:
            p = t.find('"path"', p)
            if p < 0:
                break
            a = t.find('"', p + 6)
            e = t.find('"', a + 1) if a >= 0 else -1
            if e < 0:
                break
            kandidaten.append(os.path.join(t[a + 1:e].replace("\\\\", "\\"), "steamapps", "common", steam_name))
            p = e + 1
    except OSError:
        pass
    kandidaten += [os.path.join(r"C:\GOG Games", gog_name),
                   os.path.join(r"C:\Program Files (x86)\GOG Galaxy\Games", gog_name),
                   os.path.expanduser("~/.local/share/Steam/steamapps/common/" + steam_name),
                   os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/" + steam_name)]
    for k in kandidaten:
        if ist_spielordner(k) and spiel_von_ordner(k) in ("", spiel):
            return k
    return ""

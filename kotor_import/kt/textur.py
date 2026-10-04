# ============================================================
#  textur.py - Texturen (TPC aus den Texturpaketen), Port von kttextur.cpp
#
#  TPC: 128 Byte Kopf
#    0 u32 Groesse der obersten Stufe (0 = unkomprimiert)
#    4 f32 Alpha-Test     8 u16 Breite   10 u16 Hoehe
#    12 u8 Kodierung (1 grau, 2 RGB bzw. DXT1, 4 RGBA bzw. DXT5)
#    13 u8 Zahl der Mip-Stufen
#  danach die Stufen, am Ende ein TXI-Text (Shader-Hinweise).
#  Wuerfeltexturen: Hoehe = 6 x Breite (nur die erste Seite wird gelesen).
#
#  AUSRICHTUNG (gemessen): Zeile 0 der Daten gehoert zu v = 0, also UNTEN -
#  genau wie Blenders Image.pixels. Die UVs bleiben unveraendert.
#
#  DXT-Entpacken vektorisiert mit numpy, Rundung wie bcdec (das Max-Plugin).
# ============================================================
import struct

import numpy as np


class Bild:
    def __init__(self):
        self.breite = 0
        self.hoehe = 0
        self.rgba = None          # (hoehe, breite, 4) uint8, Zeile 0 = unten (v = 0)
        self.mit_alpha = False
        self.txi = ""
        self.format = ""


def _farben_565(c):
    r = ((c >> 11) & 0x1F).astype(np.int32)
    g = ((c >> 5) & 0x3F).astype(np.int32)
    b = (c & 0x1F).astype(np.int32)
    return r, g, b


def _farbbloecke(c0, c1, idx, nur_deckend):
    """(blöcke, 16, 4) uint8 aus den 8-Byte-Farbbloecken (bcdec__color_block)."""
    r0, g0, b0 = _farben_565(c0)
    r1, g1, b1 = _farben_565(c1)
    n = len(c0)
    tab = np.zeros((n, 4, 4), dtype=np.int32)
    tab[:, 0] = np.stack([(r0 * 527 + 23) >> 6, (g0 * 259 + 33) >> 6, (b0 * 527 + 23) >> 6, np.full(n, 255)], axis=1)
    tab[:, 1] = np.stack([(r1 * 527 + 23) >> 6, (g1 * 259 + 33) >> 6, (b1 * 527 + 23) >> 6, np.full(n, 255)], axis=1)
    vier = (c0 > c1) | nur_deckend
    f2 = np.stack([((2 * r0 + r1) * 351 + 61) >> 7, ((2 * g0 + g1) * 2763 + 1039) >> 11,
                   ((2 * b0 + b1) * 351 + 61) >> 7, np.full(n, 255)], axis=1)
    f3 = np.stack([((r0 + 2 * r1) * 351 + 61) >> 7, ((g0 + 2 * g1) * 2763 + 1039) >> 11,
                   ((b0 + 2 * b1) * 351 + 61) >> 7, np.full(n, 255)], axis=1)
    h2 = np.stack([((r0 + r1) * 1053 + 125) >> 8, ((g0 + g1) * 4145 + 1019) >> 11,
                   ((b0 + b1) * 1053 + 125) >> 8, np.full(n, 255)], axis=1)
    tab[:, 2] = np.where(vier[:, None], f2, h2)
    tab[:, 3] = np.where(vier[:, None], f3, 0)
    stellen = (idx[:, None] >> (2 * np.arange(16, dtype=np.uint32))[None, :]) & 3      # (n, 16)
    return np.take_along_axis(tab, stellen[:, :, None].astype(np.int64).repeat(4, axis=2), axis=1).astype(np.uint8)


def _alphabloecke(roh8):
    """(blöcke, 16) uint8 aus den 8-Byte-Alphabloecken von DXT5 (bcdec__smooth_alpha_block)."""
    blk = roh8.view("<u8").ravel()
    a0 = (blk & 0xFF).astype(np.int32)
    a1 = ((blk >> 8) & 0xFF).astype(np.int32)
    n = len(blk)
    tab = np.zeros((n, 8), dtype=np.int32)
    tab[:, 0], tab[:, 1] = a0, a1
    sieben = a0 > a1
    for i in range(1, 7):
        tab[:, i + 1] = np.where(sieben, ((7 - i) * a0 + i * a1) // 7, 0)
    for i in range(1, 5):
        tab[:, i + 1] = np.where(sieben, tab[:, i + 1], ((5 - i) * a0 + i * a1) // 5)
    tab[:, 6] = np.where(sieben, tab[:, 6], 0)
    tab[:, 7] = np.where(sieben, tab[:, 7], 255)
    idx = blk >> np.uint64(16)
    stellen = ((idx[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))[None, :]) & np.uint64(7)).astype(np.int64)
    return np.take_along_axis(tab, stellen, axis=1).astype(np.uint8)


def _dxt(roh, start, breite, hoehe, dxt5):
    bx, by = (breite + 3) // 4, (hoehe + 3) // 4
    block = 16 if dxt5 else 8
    d = np.frombuffer(roh, dtype=np.uint8, count=bx * by * block, offset=start).reshape(-1, block)
    farbe = d[:, 8:] if dxt5 else d
    c0 = farbe[:, 0:2].copy().view("<u2").ravel()
    c1 = farbe[:, 2:4].copy().view("<u2").ravel()
    idx = farbe[:, 4:8].copy().view("<u4").ravel()
    px = _farbbloecke(c0, c1, idx, dxt5)                   # (n, 16, 4)
    if dxt5:
        px[:, :, 3] = _alphabloecke(d[:, 0:8].copy())
    # Bloecke (by, bx, 4, 4, 4) -> Bild (by*4, bx*4, 4)
    bild = px.reshape(by, bx, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(by * 4, bx * 4, 4)
    return bild[:hoehe, :breite].copy()


def lies_tpc(roh):
    """Bild; ValueError mit Grund."""
    if len(roh) < 128:
        raise ValueError("TPC: too short")
    groesse = struct.unpack_from("<I", roh, 0)[0]
    breite, hoehe = struct.unpack_from("<HH", roh, 8)
    kodierung, mips = roh[12], roh[13]
    if breite <= 0 or hoehe <= 0 or breite > 8192 or hoehe > 8192 * 6:
        raise ValueError("TPC: bad size")
    wuerfel = hoehe == breite * 6
    if wuerfel:
        hoehe = breite
    b = Bild()
    b.breite, b.hoehe = breite, hoehe
    start = 128
    if groesse != 0:
        dxt5 = kodierung == 4
        block = 16 if dxt5 else 8
        noetig = ((breite + 3) // 4) * ((hoehe + 3) // 4) * block
        if start + noetig > len(roh):
            raise ValueError("TPC: truncated DXT data")
        b.rgba = _dxt(roh, start, breite, hoehe, dxt5)
        b.format = "DXT5" if dxt5 else "DXT1"
        summe, w, h = 0, breite, hoehe
        for _ in range(mips or 1):
            summe += ((w + 3) // 4) * ((h + 3) // 4) * block
            w, h = max(1, w // 2), max(1, h // 2)
        ende = start + summe * (6 if wuerfel else 1)
    else:
        bpp = {1: 1, 2: 3, 4: 4, 12: 4}.get(kodierung)
        if bpp is None:
            raise ValueError("TPC: unknown encoding %d" % kodierung)
        b.format = {1: "GRAY", 2: "RGB", 4: "RGBA", 12: "BGRA"}[kodierung]
        noetig = breite * hoehe * bpp
        if start + noetig > len(roh):
            raise ValueError("TPC: truncated pixel data")
        q = np.frombuffer(roh, dtype=np.uint8, count=noetig, offset=start).reshape(hoehe, breite, bpp)
        rgba = np.full((hoehe, breite, 4), 255, dtype=np.uint8)
        if bpp == 1:
            rgba[:, :, 0:3] = q
        elif bpp == 3:
            rgba[:, :, 0:3] = q
        elif kodierung == 12:
            rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2], rgba[:, :, 3] = q[:, :, 2], q[:, :, 1], q[:, :, 0], q[:, :, 3]
        else:
            rgba[:] = q
        b.rgba = rgba
        summe, w, h = 0, breite, hoehe
        for _ in range(mips or 1):
            summe += w * h * bpp
            w, h = max(1, w // 2), max(1, h // 2)
        ende = start + summe * (6 if wuerfel else 1)
    b.mit_alpha = bool((b.rgba[:, :, 3] < 255).any())
    if ende < len(roh):
        t = roh[ende:]
        n = t.find(b"\0")
        b.txi = (t[:n] if n >= 0 else t).decode("latin-1")
    return b


def lies_tga(roh):
    """Unkomprimierte und RLE-TGA (24/32 Bit, 8 Bit grau) -> Bild mit Zeile 0 = unten."""
    if len(roh) < 18:
        raise ValueError("TGA: too short")
    id_len, cmap, art = roh[0], roh[1], roh[2]
    breite, hoehe, bpp, desc = struct.unpack_from("<HHBB", roh, 12)
    if cmap != 0 or art not in (2, 3, 10, 11) or bpp not in (8, 24, 32):
        raise ValueError("TGA: unsupported type %d/%d bpp" % (art, bpp))
    p = 18 + id_len
    k = bpp // 8
    zahl = breite * hoehe
    if art in (2, 3):
        px = np.frombuffer(roh, dtype=np.uint8, count=zahl * k, offset=p).reshape(zahl, k)
    else:
        aus = bytearray()
        while len(aus) < zahl * k and p < len(roh):
            kopf = roh[p]
            p += 1
            n = (kopf & 0x7F) + 1
            if kopf & 0x80:
                aus += roh[p:p + k] * n
                p += k
            else:
                aus += roh[p:p + n * k]
                p += n * k
        px = np.frombuffer(bytes(aus[:zahl * k]).ljust(zahl * k, b"\0"), dtype=np.uint8).reshape(zahl, k)
    rgba = np.full((zahl, 4), 255, dtype=np.uint8)
    if k == 1:
        rgba[:, 0:3] = px
    else:
        rgba[:, 0], rgba[:, 1], rgba[:, 2] = px[:, 2], px[:, 1], px[:, 0]
        if k == 4:
            rgba[:, 3] = px[:, 3]
    rgba = rgba.reshape(hoehe, breite, 4)
    if desc & 0x20:            # Ursprung oben: umdrehen, damit Zeile 0 unten liegt
        rgba = rgba[::-1].copy()
    b = Bild()
    b.breite, b.hoehe, b.rgba = breite, hoehe, rgba
    b.mit_alpha = bool((rgba[:, :, 3] < 255).any())
    b.format = "TGA"
    return b


def txi_wert(txi, schluessel):
    """Einen TXI-Schluessel lesen ("blending" -> "punchthrough"), leer wenn keiner."""
    k = schluessel.lower()
    for zeile in txi.split("\n"):
        teile = zeile.strip(" \t\r").split(None, 1)
        if not teile or teile[0].lower() != k:
            continue
        if len(teile) == 1:
            return "1"
        return teile[1].rstrip("\r ").lower()
    return ""

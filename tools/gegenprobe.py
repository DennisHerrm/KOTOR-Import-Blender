"""Gegenprobe Python-Leser gegen den C++-Leser des Max-Plugins (ktdump pruef).

    python gegenprobe.py <spielordner> <ktdump.exe>

Schreibt beide Ausgaben nach test/ und vergleicht Zeile fuer Zeile (Zahlen mit Toleranz).
"""
import os
import subprocess
import sys
import time

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, "..", "kotor_import"))

from kt import archiv as ar          # noqa: E402
from kt import figur as fg           # noqa: E402


def q(v):
    s = "%.5f" % v
    return "0.00000" if s == "-0.00000" else s


def python_ausgabe(spiel):
    a = ar.Archiv()
    f = a.oeffne(spiel)
    if f:
        raise SystemExit(f)
    c = fg.ModellCache(a)
    z = []
    for x in fg.lade_figurenliste(a):
        z.append("E %d %s %s %s %s %d" % (x.zeile, x.label, x.art, x.kategorie, x.kopf or "-", x.standard) +
                 "".join(" %s:%s/%s" % (v.buchstabe, v.modell, v.textur or "-") for v in x.varianten))
        for vi, v in enumerate(x.varianten):
            try:
                fig = fg.baue_figur(c, v.modell, x.kopf, v.textur)
            except ValueError:
                z.append("FIG-FEHLER %s" % v.modell)
                continue
            z.append("F %s|%s|%s %d %d %d" % (v.modell, x.kopf, v.textur, len(fig.knoten), len(fig.netze), len(fig.animationen)))
            for i, k in enumerate(fig.knoten):
                z.append("K %d %s %d %d %d %d %s" % (i, k.name, k.eltern, k.netz, k.teil, k.flags,
                                                     " ".join(q(w) for w in tuple(k.pos) + tuple(k.rot))))
            for i, n in enumerate(fig.netze):
                d = n.daten
                sp = float(d.pos.sum())
                su = float(d.uv0.sum()) if d.uv0 is not None else 0.0
                st = int(d.dreiecke.sum())
                ss, sk = 0.0, 0
                if n.skin_knoten is not None:
                    g = n.skin_knoten >= 0
                    ss = float((n.skin_knoten[g] * d.gewicht[g]).sum())
                    sk = int(n.skin_knoten[g].sum())
                sbq = sum(sum(b) for b in n.bind_q)
                sbt = sum(sum(b) for b in n.bind_t)
                z.append("N %d %s %d %d %d %s %d %s %s %d %s %d %d %s %s" % (
                    i, n.name, n.knoten, d.vertices, len(d.dreiecke), n.textur or "-", 1 if d.skin else 0,
                    q(sp), q(su), st, q(ss), sk, len(n.bind_knoten), q(sbq), q(sbt)))
            if vi != x.standard:
                continue
            for an in fig.animationen:
                try:
                    a2 = fg.lade_animation(c, fig, an)
                except ValueError:
                    z.append("A-FEHLER %s" % an)
                    continue
                sr = sp = sz = 0.0
                kr = kp = kn = 0
                for s in a2.spuren:
                    kn += s.knoten
                    sr += sum(sum(r) for r in s.rot)
                    sp += sum(sum(p) for p in s.pos)
                    sz += sum(s.zeit_rot) + sum(s.zeit_pos)
                    kr += len(s.zeit_rot)
                    kp += len(s.zeit_pos)
                se = sum(e[0] for e in a2.ereignisse)
                z.append("A %s %s %s %s %d %d %d %d %s %s %s %d %s" % (
                    an, a2.herkunft or "-", q(a2.laenge), q(a2.skala), len(a2.spuren), kn, kr, kp,
                    q(sr), q(sp), q(sz), len(a2.ereignisse), q(se)))
    return z


def gleich(a, b):
    ta, tb = a.split(), b.split()
    if len(ta) != len(tb):
        return False
    for x, y in zip(ta, tb):
        if x == y:
            continue
        try:
            fx, fy = float(x), float(y)
        except ValueError:
            return False
        if abs(fx - fy) > 1e-3 + 1e-5 * max(abs(fx), abs(fy)):
            return False
    return True


def main():
    spiel, ktdump = sys.argv[1], sys.argv[2]
    test = os.path.join(HIER, "..", "test")
    os.makedirs(test, exist_ok=True)
    t0 = time.time()
    cpp = subprocess.run([ktdump, "pruef", spiel], capture_output=True, text=True, encoding="latin-1").stdout.splitlines()[1:]
    t1 = time.time()
    py = python_ausgabe(spiel)
    t2 = time.time()
    open(os.path.join(test, "gegenprobe_cpp.txt"), "w", encoding="latin-1").write("\n".join(cpp))
    open(os.path.join(test, "gegenprobe_py.txt"), "w", encoding="latin-1").write("\n".join(py))
    abw = 0
    for i, (x, y) in enumerate(zip(cpp, py)):
        if not gleich(x, y):
            abw += 1
            if abw <= 20:
                print("Zeile %d\n  C++: %s\n  Py:  %s" % (i + 1, x, y))
    zaehl = {}
    for z in py:
        zaehl[z[:1]] = zaehl.get(z[:1], 0) + 1
    print("C++ %d Zeilen (%.1f s), Python %d Zeilen (%.1f s), abweichend %d" % (len(cpp), t1 - t0, len(py), t2 - t1, abw +
                                                                              abs(len(cpp) - len(py))))
    print("Eintraege %d, Figuren %d, Knoten %d, Netze %d, Animationen %d" % (
        zaehl.get("E", 0), zaehl.get("F", 0), zaehl.get("K", 0), zaehl.get("N", 0), zaehl.get("A", 0)))


if __name__ == "__main__":
    main()

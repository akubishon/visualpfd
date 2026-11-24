"""log p-h-diagrammen tekenen met CoolProp.

Los script: het werkt zonder de rest van het model. Je hebt alleen CoolProp, numpy en matplotlib nodig:

    pip install CoolProp numpy matplotlib

Voorbeelden (vanuit deze map):

    python logph_diagram.py                          # beste koudemiddel voor WP-201 (40 -> 75 °C)
    python logph_diagram.py --tcond 100              # beste koudemiddel voor WP-202 (40 -> 100 °C)
    python logph_diagram.py --top 3                  # top 3 naast elkaar
    python logph_diagram.py R1233zd(E) R1234ze(Z)    # zelf koudemiddelen kiezen
    python logph_diagram.py --tcond 100 --oververhitting 5 --onderkoeling 3
    python logph_diagram.py --lijst                  # alleen de ranglijst, geen diagram

Of vanuit je eigen Python-code / notebook:

    from logph_diagram import teken_logph, beste_koudemiddelen
    teken_logph("R1233zd(E)", T_evap=40, T_cond=100)
    print(beste_koudemiddelen(40, 100)[:3])

In PowerShell of bash moet je haakjes in een naam tussen aanhalingstekens zetten: "R1233zd(E)".
"""

import argparse

import matplotlib.pyplot as plt
import numpy as np
from CoolProp.CoolProp import PropsSI

T0 = 273.15

# CoolProp-naam: (leesbare naam, GWP-100, ASHRAE-veiligheidsklasse). GWP en klasse zelf ingevuld; controleer ze.
KOUDEMIDDELEN = {
    "R1234ze(E)": ("R1234ze(E)", "<1", "A2L"), "R1234yf": ("R1234yf", "<1", "A2L"),
    "R1233zd(E)": ("R1233zd(E)", "1", "A1"), "R1234ze(Z)": ("R1234ze(Z)", "<1", "A2L"),
    "R1336mzz(Z)": ("R1336mzz(Z)", "2", "A1"), "R1224YDZ": ("R1224yd(Z)", "<1", "A1"),
    "R134a": ("R134a", "1430", "A1"), "R245fa": ("R245fa", "1030", "B1"), "R32": ("R32", "675", "A2L"),
    "R152A": ("R152a", "124", "A2"), "IsoButane": ("R600a isobutaan", "3", "A3"),
    "n-Butane": ("R600 butaan", "4", "A3"), "n-Propane": ("R290 propaan", "3", "A3"),
    "Propylene": ("R1270 propeen", "2", "A3"), "Ammonia": ("R717 ammoniak", "0", "B2L"),
    "CarbonDioxide": ("R744 CO2", "1", "A1"),
}


# ------------------------------------------------------------------------------------- cyclus
def cyclus(fluid, T_evap=40.0, T_cond=75.0, eta=0.7, oververhitting=0.0, onderkoeling=0.0):
    """Eenvoudige dampcompressiecyclus. Geeft de vier toestandspunten (p in bar, h in kJ/kg, T in °C) en de COP.

    1 = zuigzijde compressor, 2 = persdamp, 3 = na condensor, 4 = na smoorventiel.
    Werpt ValueError als het middel bij deze temperaturen niet subkritisch kan werken."""
    Tcrit = PropsSI("Tcrit", fluid) - T0
    if T_cond > Tcrit - 2:
        raise ValueError(f"{fluid}: condenseren bij {T_cond:.0f} °C kan niet, kritisch punt is {Tcrit:.0f} °C")

    pe = PropsSI("P", "T", T_evap + T0, "Q", 1, fluid)
    pc = PropsSI("P", "T", T_cond + T0, "Q", 0, fluid)

    # 1: verzadigde damp (+ eventuele oververhitting) bij verdampingsdruk
    if oververhitting > 0:
        T1 = T_evap + oververhitting
        h1 = PropsSI("H", "T", T1 + T0, "P", pe, fluid)
        s1 = PropsSI("S", "T", T1 + T0, "P", pe, fluid)
    else:
        T1 = T_evap
        h1 = PropsSI("H", "T", T_evap + T0, "Q", 1, fluid)
        s1 = PropsSI("S", "T", T_evap + T0, "Q", 1, fluid)

    # 2: compressie met isentroop rendement eta
    h2s = PropsSI("H", "P", pc, "S", s1, fluid)
    h2 = h1 + (h2s - h1) / eta
    T2 = PropsSI("T", "P", pc, "H", h2, fluid) - T0

    # 3: verzadigde vloeistof (- eventuele onderkoeling) bij condensatiedruk
    if onderkoeling > 0:
        T3 = T_cond - onderkoeling
        h3 = PropsSI("H", "T", T3 + T0, "P", pc, fluid)
    else:
        T3 = T_cond
        h3 = PropsSI("H", "T", T_cond + T0, "Q", 0, fluid)

    # 4: smoorventiel, h blijft gelijk
    h4 = h3
    x4 = PropsSI("Q", "P", pe, "H", h4, fluid)

    hv_c = PropsSI("H", "P", pc, "Q", 1, fluid)
    q_in, w, q_uit = (h1 - h4) / 1e3, (h2 - h1) / 1e3, (h2 - h3) / 1e3
    return dict(
        fluid=fluid, Tcrit=Tcrit, T_evap=T_evap, T_cond=T_cond, eta=eta,
        p=[pe / 1e5, pc / 1e5, pc / 1e5, pe / 1e5],
        h=[h1 / 1e3, h2 / 1e3, h3 / 1e3, h4 / 1e3],
        T=[T1, T2, T3, T_evap],
        h2s=h2s / 1e3, x4=x4,
        q_in=q_in, w=w, q_uit=q_uit, COP=q_uit / w,
        COP_carnot=(T_cond + T0) / (T_cond - T_evap),
        persdamp_nat=h2 < hv_c - 50,  # eindpunt compressie nog binnen de koepel
    )


def beste_koudemiddelen(T_evap=40.0, T_cond=75.0, eta=0.7, oververhitting=0.0, onderkoeling=0.0,
                        kandidaten=None, zonder_hoge_gwp=False):
    """Rekent alle kandidaten door en geeft ze terug gesorteerd op COP (hoogste eerst).
    Middelen die bij deze condities niet kunnen, vallen weg."""
    uit = []
    for f in kandidaten or KOUDEMIDDELEN:
        gwp = KOUDEMIDDELEN.get(f, (f, "?", "?"))[1]
        if zonder_hoge_gwp and gwp.isdigit() and int(gwp) > 150:
            continue
        try:
            uit.append(cyclus(f, T_evap, T_cond, eta, oververhitting, onderkoeling))
        except Exception:
            pass
    return sorted(uit, key=lambda c: c["COP"], reverse=True)


# ------------------------------------------------------------------------------------ tekenen
def _koepel(fluid, n=200):
    """Verzadigde vloeistof- en damplijn, van net boven het tripelpunt tot het kritische punt."""
    Tmin = max(PropsSI("Tmin", fluid), PropsSI("Ttriple", fluid)) + 1
    Tc = PropsSI("Tcrit", fluid)
    T = np.linspace(Tmin, Tc - 0.05, n)
    p = np.array([PropsSI("P", "T", t, "Q", 0, fluid) for t in T]) / 1e5
    hl = np.array([PropsSI("H", "T", t, "Q", 0, fluid) for t in T]) / 1e3
    hv = np.array([PropsSI("H", "T", t, "Q", 1, fluid) for t in T]) / 1e3
    return p, hl, hv, PropsSI("pcrit", fluid) / 1e5, PropsSI("H", "T", Tc, "P", PropsSI("pcrit", fluid), fluid) / 1e3


def _isotherm(fluid, T_C, p_min, p_max, n=80):
    """Isotherm in het p-h-vlak: steil in de vloeistof, horizontaal in de koepel, dalend in de damp."""
    T = T_C + T0
    Tc = PropsSI("Tcrit", fluid)
    hh, pp = [], []
    if T < Tc:
        ps = PropsSI("P", "T", T, "Q", 0, fluid)
        for p in np.geomspace(p_max * 1e5, ps * 1.001, n):          # vloeistofkant
            try:
                hh.append(PropsSI("H", "T", T, "P", p, fluid)); pp.append(p)
            except ValueError:
                pass
        hh += [PropsSI("H", "T", T, "Q", 0, fluid), PropsSI("H", "T", T, "Q", 1, fluid)]
        pp += [ps, ps]
        for p in np.geomspace(ps * 0.999, p_min * 1e5, n):          # dampkant
            try:
                hh.append(PropsSI("H", "T", T, "P", p, fluid)); pp.append(p)
            except ValueError:
                pass
    else:
        for p in np.geomspace(p_max * 1e5, p_min * 1e5, 2 * n):
            try:
                hh.append(PropsSI("H", "T", T, "P", p, fluid)); pp.append(p)
            except ValueError:
                pass
    return np.array(hh) / 1e3, np.array(pp) / 1e5


def _compressielijn(fluid, c, n=30):
    """Echte compressielijn 1 -> 2: elk tussenpunt met hetzelfde isentrope rendement."""
    p1, p2 = c["p"][0] * 1e5, c["p"][1] * 1e5
    h1 = c["h"][0] * 1e3
    s1 = PropsSI("S", "P", p1, "H", h1, fluid)
    pp = np.geomspace(p1, p2, n)
    hh = [h1 + (PropsSI("H", "P", p, "S", s1, fluid) - h1) / c["eta"] for p in pp]
    return np.array(hh) / 1e3, pp / 1e5


def teken_logph(fluid, T_evap=40.0, T_cond=75.0, eta=0.7, oververhitting=0.0, onderkoeling=0.0,
                ax=None, isothermen=True, dampfractie=True, titel=None, bestand=None, toon=True):
    """Tekent het log p-h-diagram van één koudemiddel met de cyclus erin.

    ax       : bestaande matplotlib-as (voor subplots); None maakt een nieuwe figuur.
    bestand  : bv. "logph_R1233zd.png" om op te slaan.
    toon     : plt.show() aanroepen (alleen als er geen ax is meegegeven)."""
    c = cyclus(fluid, T_evap, T_cond, eta, oververhitting, onderkoeling)
    eigen_fig = ax is None
    if eigen_fig:
        fig, ax = plt.subplots(figsize=(10, 7))

    # assen-bereik rond de cyclus
    p_koepel, hl, hv, pcrit, hcrit = _koepel(fluid)
    p_min = c["p"][0] / 4
    p_max = min(pcrit * 2.5, c["p"][1] * 4)
    h_min = PropsSI("H", "T", T_evap + T0 - 40, "Q", 0, fluid) / 1e3
    h_max = max(c["h"][1], hv.max()) + 0.35 * (hv.max() - hl.min())

    # verzadigingskoepel
    ax.plot(hl, p_koepel, color="0.15", lw=1.6)
    ax.plot(hv, p_koepel, color="0.15", lw=1.6)
    ax.plot([hl[-1], hcrit, hv[-1]], [p_koepel[-1], pcrit, p_koepel[-1]], color="0.15", lw=1.6)
    ax.plot(hcrit, pcrit, "o", color="0.15", ms=4)
    ax.annotate("kritisch punt", (hcrit, pcrit), xytext=(6, 4), textcoords="offset points", fontsize=8, color="0.3")
    ax.text(np.interp(p_min * 2, p_koepel, hl), p_min * 2, " vloeistof", fontsize=8, color="0.4", ha="right")
    ax.text(np.interp(p_min * 2, p_koepel, hv), p_min * 2, " damp", fontsize=8, color="0.4")

    # lijnen van gelijke dampfractie
    if dampfractie:
        pm = p_koepel[(p_koepel > p_min) & (p_koepel < pcrit * 0.98)]
        for x in (0.2, 0.4, 0.6, 0.8):
            hx = [PropsSI("H", "P", p * 1e5, "Q", x, fluid) / 1e3 for p in pm]
            ax.plot(hx, pm, color="0.7", lw=0.6, ls=":")
            ax.text(hx[0], pm[0], f"x={x:.1f}", fontsize=7, color="0.55", ha="center", va="top")

    # isothermen
    if isothermen:
        stap = 20
        for T_C in np.arange(np.floor((T_evap - 40) / stap) * stap, c["T"][1] + 2 * stap, stap):
            hh, pp = _isotherm(fluid, T_C, p_min, p_max)
            if len(hh) < 2:
                continue
            ax.plot(hh, pp, color="tab:green", lw=0.6, alpha=0.45)
            # label waar de isotherm de damplijn verlaat (of bovenaan als hij boven het kritische punt ligt)
            if T_C + T0 < PropsSI("Tcrit", fluid):
                ps = PropsSI("P", "T", T_C + T0, "Q", 1, fluid) / 1e5
                hl_ = PropsSI("H", "T", T_C + T0, "Q", 1, fluid) / 1e3
            else:
                ps, hl_ = p_max * 0.9, np.interp(np.log(p_max * 0.9), np.log(pp[::-1]), hh[::-1])
            if p_min < ps < p_max and hl_ < h_max:
                ax.text(hl_, ps, f" {T_C:.0f} °C", fontsize=7, color="tab:green", ha="left", va="bottom")

    # de cyclus, stap voor stap
    h, p = c["h"], c["p"]
    hc, pcomp = _compressielijn(fluid, c)
    ax.plot([h[3], h[0]], [p[3], p[0]], color="tab:blue", lw=2.6, label="4→1 verdamper (warmte opnemen)")
    ax.plot(hc, pcomp, color="tab:red", lw=2.6, label="1→2 compressor (arbeid)")
    ax.plot([h[1], h[2]], [p[1], p[2]], color="tab:orange", lw=2.6, label="2→3 condensor (warmte afgeven)")
    ax.plot([h[2], h[3]], [p[2], p[3]], color="tab:purple", lw=2.6, label="3→4 smoorventiel (h constant)")
    ax.plot([h[0], c["h2s"]], [p[0], p[1]], color="tab:red", lw=1, ls="--", label="1→2s ideale compressor")
    ax.plot(h, p, "o", color="k", ms=5, zorder=5)
    for i, (hi, pi, Ti) in enumerate(zip(h, p, c["T"])):
        dx = 8 if i in (0, 1) else -8
        ax.annotate(f"{i + 1}\n{Ti:.0f} °C, {pi:.1f} bar", (hi, pi), xytext=(dx, 6 if i in (1, 2) else -22),
                    textcoords="offset points", fontsize=8, ha="left" if dx > 0 else "right", fontweight="bold")

    # samenvatting
    naam, gwp, klasse = KOUDEMIDDELEN.get(fluid, (fluid, "?", "?"))
    tekst = (f"COP = {c['COP']:.2f}  (Carnot {c['COP_carnot']:.2f})\n"
             f"q_in = {c['q_in']:.0f} kJ/kg   w = {c['w']:.0f} kJ/kg   q_uit = {c['q_uit']:.0f} kJ/kg\n"
             f"drukverhouding = {p[1] / p[0]:.1f}   dampfractie na ventiel = {c['x4']:.2f}\n"
             f"GWP {gwp}, klasse {klasse}, kritisch punt {c['Tcrit']:.0f} °C")
    if c["persdamp_nat"]:
        tekst += "\nLet op: persdamp nog nat, geef oververhitting (--oververhitting 5)"
    ax.text(0.02, 0.98, tekst, transform=ax.transAxes, va="top", fontsize=8.5, family="monospace",
            bbox=dict(boxstyle="round", fc="white", ec="0.7", alpha=0.9))

    ax.set_yscale("log")
    ax.set_xlim(h_min, h_max)
    ax.set_ylim(p_min, p_max)
    ax.set_xlabel("specifieke enthalpie h [kJ/kg]")
    ax.set_ylabel("druk p [bar] (log)")
    ax.set_title(titel or f"log p-h  {naam}:  {T_evap:.0f} °C → {T_cond:.0f} °C, η_is = {eta}")
    ax.grid(True, which="both", lw=0.3, alpha=0.5)
    ax.legend(loc="lower right", fontsize=8)

    if eigen_fig:
        fig.tight_layout()
        if bestand:
            fig.savefig(bestand, dpi=150)
            print(f"opgeslagen: {bestand}")
        if toon:
            plt.show()
    return c


def teken_meerdere(fluids, T_evap=40.0, T_cond=75.0, eta=0.7, oververhitting=0.0, onderkoeling=0.0,
                   bestand=None, toon=True):
    """Meerdere koudemiddelen naast elkaar, elk in een eigen paneel."""
    n = len(fluids)
    kol = min(n, 3)
    rij = int(np.ceil(n / kol))
    fig, assen = plt.subplots(rij, kol, figsize=(7.5 * kol, 6 * rij), squeeze=False)
    for ax, f in zip(assen.flat, fluids):
        teken_logph(f, T_evap, T_cond, eta, oververhitting, onderkoeling, ax=ax,
                    titel=f"{KOUDEMIDDELEN.get(f, (f,))[0]}")
    for ax in list(assen.flat)[n:]:
        ax.set_visible(False)
    fig.suptitle(f"log p-h: {T_evap:.0f} °C → {T_cond:.0f} °C, η_is = {eta}", fontsize=13)
    fig.tight_layout()
    if bestand:
        fig.savefig(bestand, dpi=150)
        print(f"opgeslagen: {bestand}")
    if toon:
        plt.show()


def print_ranglijst(resultaten):
    print(f"{'#':>2}  {'koudemiddel':<18}{'COP':>6}{'p_verd':>8}{'p_cond':>8}{'T_pers':>8}  GWP   klasse  let op")
    for i, c in enumerate(resultaten, 1):
        naam, gwp, klasse = KOUDEMIDDELEN.get(c["fluid"], (c["fluid"], "?", "?"))
        let_op = "persdamp nat" if c["persdamp_nat"] else ""
        print(f"{i:>2}  {naam:<18}{c['COP']:>6.2f}{c['p'][0]:>7.1f} {c['p'][1]:>7.1f} {c['T'][1]:>6.0f}°C"
              f"  {gwp:<5} {klasse:<6}  {let_op}")


# ------------------------------------------------------------------------------- opdrachtregel
def main():
    a = argparse.ArgumentParser(description="log p-h-diagram met CoolProp voor het beste (of gekozen) koudemiddel")
    a.add_argument("koudemiddelen", nargs="*", help="CoolProp-namen, bv. R1233zd(E) Ammonia. Leeg = beste kiezen")
    a.add_argument("--tevap", type=float, default=40.0, help="verdampingstemperatuur °C (standaard 40)")
    a.add_argument("--tcond", type=float, default=75.0, help="condensatietemperatuur °C (75 = WP-201, 100 = WP-202)")
    a.add_argument("--eta", type=float, default=0.7, help="isentroop rendement compressor (standaard 0,7)")
    a.add_argument("--oververhitting", type=float, default=0.0, help="oververhitting vóór compressor, K")
    a.add_argument("--onderkoeling", type=float, default=0.0, help="onderkoeling na condensor, K")
    a.add_argument("--top", type=int, default=1, help="aantal beste koudemiddelen om te tekenen")
    a.add_argument("--zonder-hoge-gwp", action="store_true", help="middelen met GWP > 150 overslaan")
    a.add_argument("--lijst", action="store_true", help="alleen de ranglijst printen")
    a.add_argument("--opslaan", metavar="BESTAND", help="figuur opslaan, bv. logph.png")
    a.add_argument("--niet-tonen", action="store_true", help="geen venster openen (handig met --opslaan)")
    arg = a.parse_args()

    kw = dict(T_evap=arg.tevap, T_cond=arg.tcond, eta=arg.eta,
              oververhitting=arg.oververhitting, onderkoeling=arg.onderkoeling)
    rang = beste_koudemiddelen(**kw, kandidaten=arg.koudemiddelen or None, zonder_hoge_gwp=arg.zonder_hoge_gwp)
    if not rang:
        raise SystemExit("Geen enkel koudemiddel kan bij deze temperaturen.")
    print_ranglijst(rang)
    if arg.lijst:
        return

    fluids = [c["fluid"] for c in rang] if arg.koudemiddelen else [c["fluid"] for c in rang[:arg.top]]
    if len(fluids) == 1:
        teken_logph(fluids[0], **kw, bestand=arg.opslaan, toon=not arg.niet_tonen)
    else:
        teken_meerdere(fluids, **kw, bestand=arg.opslaan, toon=not arg.niet_tonen)


if __name__ == "__main__":
    main()

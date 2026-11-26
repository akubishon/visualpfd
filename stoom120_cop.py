"""COP van een warmtepomp die oververhitte stoom van 120 °C aan de industrie levert (CoolProp).

Los script, net als logph_diagram.py. Nodig: CoolProp, numpy, matplotlib.

    python stoom120_cop.py                               # standaard: 1,5 bara stoom, 120 °C, bron TW 51,5 -> 45 °C
    python stoom120_cop.py --p-stoom 1.8 --T-voeding 90  # andere stoomdruk / voedingswatertemperatuur
    python stoom120_cop.py --opslaan stoom120.png        # figuur opslaan

Bron  : koelwatercircuit TW (water, 51,5 -> 45 °C) uit het ITM-model.
Afname: voedingswater (standaard 80 °C) -> oververhitte stoom 120 °C bij p_stoom (standaard 1,5 bara,
        T_sat = 111,4 °C, dus ~8,6 K oververhitting).

Twee concepten:
  A  Gesloten warmtepomp (één trap). De stoomgenerator is de condensor: de persgassen oververhitten de stoom,
     het condenserende koudemiddel verdampt het water en de vloeistof (onderkoeling) warmt het voedingswater voor.
     De condensatietemperatuur wordt zo laag gekozen dat overal in de stoomgenerator ΔT >= pinch (T,Q-analyse).
  B  Warmtepomp + MVR (mechanische damprecompressie). De warmtepomp maakt lagedrukstoom bij T_lp; een
     stoomcompressor (water, n trappen met watersproeiing tussen de trappen) brengt die naar p_stoom en 120 °C.
     T_lp wordt gevarieerd; let op: lage T_lp geeft een hoge COP maar een groot zuigvolume (onderdruk).

COP = nuttige warmte aan de stoom / totale elektrische asarbeid (compressoren, rendementen zoals hieronder).
"""

import argparse

import matplotlib.pyplot as plt
import numpy as np
from CoolProp.CoolProp import PropsSI

T0 = 273.15
W = "Water"

KANDIDATEN = {  # CoolProp-naam: (naam, GWP, klasse)
    "R1233zd(E)": ("R1233zd(E)", "1", "A1"),
    "R1336mzz(Z)": ("R1336mzz(Z)", "2", "A1"),
    "R1224YDZ": ("R1224yd(Z)", "<1", "A1"),
    "R1234ze(Z)": ("R1234ze(Z)", "<1", "A2L"),
    "R245fa": ("R245fa", "1030", "B1"),
    "n-Butane": ("R600 butaan", "4", "A3"),
    "n-Pentane": ("R601 pentaan", "5", "A3"),
    "IsoButane": ("R600a isobutaan", "3", "A3"),
}


# --------------------------------------------------------------------------------- stoomzijde
def stoomzijde(p_stoom_bar, T_stoom, T_voeding):
    """Enthalpieën van de stoomzijde (J/kg) en de warmte per kg stoom per traject."""
    p = p_stoom_bar * 1e5
    Tsat = PropsSI("T", "P", p, "Q", 0, W) - T0
    if T_stoom <= Tsat:
        raise ValueError(f"{T_stoom} °C is niet oververhit bij {p_stoom_bar} bara (T_sat = {Tsat:.1f} °C)")
    h_fw = PropsSI("H", "T", T_voeding + T0, "P", p, W)
    h_l = PropsSI("H", "P", p, "Q", 0, W)
    h_v = PropsSI("H", "P", p, "Q", 1, W)
    h_s = PropsSI("H", "T", T_stoom + T0, "P", p, W)
    s_fw = PropsSI("S", "T", T_voeding + T0, "P", p, W)
    s_s = PropsSI("S", "T", T_stoom + T0, "P", p, W)
    return dict(p=p, Tsat=Tsat, h_fw=h_fw, h_l=h_l, h_v=h_v, h_s=h_s, q=h_s - h_fw,
                T_m=(h_s - h_fw) / (s_s - s_fw) - T0)  # entropisch gemiddelde afgiftetemperatuur


def T_stoom_van_Q(st, Q):
    """Temperatuur stoomzijde (°C) als functie van opgenomen warmte per kg stoom (J/kg vanaf voedingswater)."""
    h = st["h_fw"] + np.asarray(Q)
    return np.array([PropsSI("T", "P", st["p"], "H", hi, W) - T0 for hi in np.atleast_1d(h)])


def bron_Tm(T_in, T_uit):
    """Entropisch gemiddelde brontemperatuur (water, 1 bar ruim genoeg onder kookpunt)."""
    p = 3e5
    dh = PropsSI("H", "T", T_in + T0, "P", p, W) - PropsSI("H", "T", T_uit + T0, "P", p, W)
    ds = PropsSI("S", "T", T_in + T0, "P", p, W) - PropsSI("S", "T", T_uit + T0, "P", p, W)
    return dh / ds - T0


# ------------------------------------------------------------------------- concept A: gesloten WP
def wp_cyclus(fluid, T_evap, T_cond, T3, eta, oververhitting=5.0):
    """Eén trap: 1 zuig (verzadigd + oververhitting), 2 pers, 3 na condensor/onderkoeler (T3), 4 na smoorventiel."""
    pe = PropsSI("P", "T", T_evap + T0, "Q", 1, fluid)
    pc = PropsSI("P", "T", T_cond + T0, "Q", 0, fluid)
    T1 = T_evap + oververhitting
    h1 = PropsSI("H", "T", T1 + T0, "P", pe, fluid)
    s1 = PropsSI("S", "T", T1 + T0, "P", pe, fluid)
    h2 = h1 + (PropsSI("H", "P", pc, "S", s1, fluid) - h1) / eta
    T2 = PropsSI("T", "P", pc, "H", h2, fluid) - T0
    h3 = PropsSI("H", "T", T3 + T0, "P", pc, fluid) if T3 < T_cond - 1e-6 else PropsSI("H", "P", pc, "Q", 0, fluid)
    x4 = PropsSI("Q", "P", pe, "H", h3, fluid)
    return dict(fluid=fluid, T_evap=T_evap, T_cond=T_cond, T1=T1, T2=T2, T3=T3, pe=pe / 1e5, pc=pc / 1e5,
                h1=h1, h2=h2, h3=h3, x4=x4, COP=(h2 - h3) / (h2 - h1))


def T_koudemiddel_van_Q(c, Q_frac):
    """Temperatuur koudemiddel (°C) in de stoomgenerator, als functie van de fractie afgegeven warmte,
    gerekend vanaf de koude kant (uitlaat, punt 3) naar de warme kant (inlaat, punt 2): tegenstroom."""
    h = c["h3"] + np.asarray(Q_frac) * (c["h2"] - c["h3"])
    return np.array([PropsSI("T", "P", c["pc"] * 1e5, "H", hi, c["fluid"]) - T0 for hi in np.atleast_1d(h)])


def min_dT(c, st, n=120):
    f = np.linspace(0, 1, n)
    return float(np.min(T_koudemiddel_van_Q(c, f) - T_stoom_van_Q(st, f * st["q"])))


def bisect(f, a, b, tol=0.02):
    fa = f(a)
    for _ in range(60):
        m = 0.5 * (a + b)
        if (f(m) > 0) == (fa > 0):
            a, fa = m, f(m)
        else:
            b = m
        if b - a < tol:
            break
    return 0.5 * (a + b)


def concept_A(fluid, st, T_evap, eta, pinch, oververhitting=5.0):
    """Laagste T_cond en laagste T3 waarbij de stoomgenerator overal >= pinch haalt."""
    Tcrit = PropsSI("Tcrit", fluid) - T0
    T_hi = Tcrit - 3
    if T_hi < st["Tsat"] + pinch:
        raise ValueError(f"kritisch punt {Tcrit:.0f} °C te laag")

    def ok_Tcond(Tc):  # zonder onderkoeling
        try:
            return min_dT(wp_cyclus(fluid, T_evap, Tc, Tc, eta, oververhitting), st) - pinch
        except ValueError:
            return -1.0

    T_lo = st["Tsat"] + pinch
    if ok_Tcond(T_hi) < 0:
        raise ValueError("pinch niet te halen onder het kritisch punt (persgas te koud voor de oververhitting)")
    Tc = (T_lo if ok_Tcond(T_lo) >= 0 else bisect(ok_Tcond, T_lo, T_hi)) + 0.05

    def ok_T3(T3):
        return min_dT(wp_cyclus(fluid, T_evap, Tc, T3, eta, oververhitting), st) - pinch

    T3_min = st_T_voeding(st) + pinch
    T3 = T3_min if ok_T3(T3_min) >= 0 else bisect(ok_T3, T3_min, Tc)
    T3 = min(T3 + 0.05, Tc)
    c = wp_cyclus(fluid, T_evap, Tc, T3, eta, oververhitting)
    c["min_dT"] = min_dT(c, st)
    c["Tcrit"] = Tcrit
    return c


def st_T_voeding(st):
    return PropsSI("T", "P", st["p"], "H", st["h_fw"], W) - T0


# ------------------------------------------------------------------------- concept B: WP + MVR
def mvr(p_in, p_uit, T_uit_eind, h_inj, eta, n_trap=2, dT_tussen=5.0):
    """Stoomcompressor van verzadigde damp p_in naar p_uit in n trappen (gelijke drukverhouding).
    Tussen de trappen en na de laatste trap wordt water (h_inj) ingespoten tot T_sat+dT_tussen
    respectievelijk T_uit_eind. Geeft arbeid en eindmassa per kg zuigstoom."""
    m, h = 1.0, PropsSI("H", "P", p_in, "Q", 1, W)
    r = (p_uit / p_in) ** (1 / n_trap)
    p, w_tot, T_pers = p_in, 0.0, []
    for k in range(n_trap):
        p2 = p * r
        s = PropsSI("S", "P", p, "H", h, W)
        h2 = h + (PropsSI("H", "P", p2, "S", s, W) - h) / eta
        w_tot += m * (h2 - h)
        T_pers.append(PropsSI("T", "P", p2, "H", h2, W) - T0)
        T_doel = T_uit_eind if k == n_trap - 1 else PropsSI("T", "P", p2, "Q", 1, W) - T0 + dT_tussen
        h_doel = PropsSI("H", "T", T_doel + T0, "P", p2, W)
        if h2 > h_doel:  # inspuiten: m*h2 + dm*h_inj = (m+dm)*h_doel
            m += m * (h2 - h_doel) / (h_doel - h_inj)
            h = h_doel
        else:
            h = h2
        p = p2
    return dict(w=w_tot, m_uit=m, h_uit=h, T_pers=T_pers)


def concept_B(fluid, st, T_voeding, T_evap, T_lp, eta_wp, eta_mvr, pinch, n_trap):
    """WP verdampt water bij T_lp (condenseert bij T_lp+pinch, onderkoeling niet meegerekend),
    MVR comprimeert naar p_stoom en spuit voedingswater in tot 120 °C. Per kg geleverde stoom."""
    p_lp = PropsSI("P", "T", T_lp + T0, "Q", 1, W)
    # voedingswater komt binnen met h_fw; ligt T_voeding boven T_lp, dan flasht een deel gratis mee
    q_wp = PropsSI("H", "P", p_lp, "Q", 1, W) - st["h_fw"]          # per kg lagedrukstoom
    c = wp_cyclus(fluid, T_evap, T_lp + pinch, T_lp + pinch, eta_wp)
    m = mvr(p_lp, st["p"], T_stoom_eind(st), st["h_fw"], eta_mvr, n_trap)
    # per kg geleverde stoom
    m_lp = 1 / m["m_uit"]
    Q_wp = m_lp * q_wp
    W_wp = Q_wp / c["COP"]
    W_mvr = m_lp * m["w"]
    Q_nuttig = st["q"]
    return dict(T_lp=T_lp, p_lp=p_lp / 1e5, COP=Q_nuttig / (W_wp + W_mvr), COP_wp=c["COP"],
                w_wp=W_wp / Q_nuttig, w_mvr=W_mvr / Q_nuttig, aandeel_mvr=W_mvr / (W_wp + W_mvr), T_pers=m["T_pers"], inj=1 - m_lp, wp=c)


def T_stoom_eind(st):
    return PropsSI("T", "P", st["p"], "H", st["h_s"], W) - T0


# ------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--p-stoom", type=float, default=1.5, help="stoomdruk in bara (standaard 1,5)")
    ap.add_argument("--T-stoom", type=float, default=120.0, help="stoomtemperatuur in °C (standaard 120)")
    ap.add_argument("--T-voeding", type=float, default=80.0, help="voedingswater/condensaatretour in °C")
    ap.add_argument("--bron", type=float, nargs=2, default=[51.5, 45.0], metavar=("IN", "UIT"),
                    help="brontemperatuur in/uit °C (standaard TW 51,5 -> 45)")
    ap.add_argument("--pinch", type=float, default=5.0, help="minimaal ΔT in de warmtewisselaars (K)")
    ap.add_argument("--eta", type=float, default=0.70, help="isentroop rendement WP-compressor")
    ap.add_argument("--eta-mvr", type=float, default=0.75, help="isentroop rendement stoomcompressor")
    ap.add_argument("--trappen", type=int, default=2, help="aantal MVR-trappen")
    ap.add_argument("--Q", type=float, default=2000.0, help="gevraagd stoomvermogen in kW (voor massastroom)")
    ap.add_argument("--opslaan", help="figuur opslaan als png")
    ap.add_argument("--geen-figuur", action="store_true")
    a = ap.parse_args()

    st = stoomzijde(a.p_stoom, a.T_stoom, a.T_voeding)
    T_evap = a.bron[1] - a.pinch                     # verdampen onder de bronuitlaat
    Tm_h, Tm_c = st["T_m"], bron_Tm(*a.bron)
    COP_lorenz = (Tm_h + T0) / (Tm_h - Tm_c)
    COP_carnot = (a.T_stoom + T0) / (a.T_stoom - T_evap)
    m_stoom = a.Q / (st["q"] / 1e3)

    print(f"\nStoom: {a.p_stoom:.2f} bara, T_sat = {st['Tsat']:.1f} °C, geleverd op {a.T_stoom:.0f} °C "
          f"(oververhitting {a.T_stoom - st['Tsat']:.1f} K), voedingswater {a.T_voeding:.0f} °C")
    print(f"  warmte per kg: voorwarmen {(st['h_l'] - st['h_fw']) / 1e3:6.1f}  verdampen "
          f"{(st['h_v'] - st['h_l']) / 1e3:6.1f}  oververhitten {(st['h_s'] - st['h_v']) / 1e3:5.1f}  "
          f"totaal {st['q'] / 1e3:6.1f} kJ/kg")
    print(f"  {a.Q:.0f} kW stoom = {m_stoom:.3f} kg/s = {m_stoom * 3.6:.2f} t/h")
    print(f"Bron: {a.bron[0]} -> {a.bron[1]} °C, verdampen bij {T_evap:.1f} °C (pinch {a.pinch} K)")
    print(f"Grens: COP_Lorenz = {COP_lorenz:.2f} (T_m,afgifte {Tm_h:.1f} °C, T_m,bron {Tm_c:.1f} °C); "
          f"COP_Carnot (T_evap -> {a.T_stoom:.0f} °C) = {COP_carnot:.2f}")

    # ---------------- A
    print(f"\nA  Gesloten warmtepomp, één trap, η_is = {a.eta}  (stoomgenerator = condensor, pinch-check T,Q)")
    print(f"  {'koudemiddel':<16}{'GWP':>5}{'klasse':>7}{'T_crit':>8}{'T_cond':>8}{'T_pers':>8}{'T_3':>7}"
          f"{'p_e':>7}{'p_c':>7}{'x4':>6}{'COP':>7}{'η_Lor':>7}{'W_el kW':>9}")
    res_A = []
    for f, (naam, gwp, kl) in KANDIDATEN.items():
        try:
            c = concept_A(f, st, T_evap, a.eta, a.pinch)
        except Exception as e:
            print(f"  {naam:<16}{gwp:>5}{kl:>7}   -- {e}")
            continue
        res_A.append(c)
        print(f"  {naam:<16}{gwp:>5}{kl:>7}{c['Tcrit']:8.1f}{c['T_cond']:8.1f}{c['T2']:8.1f}{c['T3']:7.1f}"
              f"{c['pe']:7.2f}{c['pc']:7.2f}{c['x4']:6.2f}{c['COP']:7.2f}{c['COP'] / COP_lorenz:7.0%}"
              f"{a.Q / c['COP']:9.0f}")
    res_A.sort(key=lambda c: c["COP"], reverse=True)

    # ---------------- B
    fB = "R1233zd(E)"
    T_lps = np.arange(T_evap + 10, st["Tsat"] - 1, 4.0)
    res_B = [concept_B(fB, st, a.T_voeding, T_evap, t, a.eta, a.eta_mvr, a.pinch, a.trappen) for t in T_lps]
    best_B = max(res_B, key=lambda r: r["COP"])
    print(f"\nB  Warmtepomp ({fB}) + MVR ({a.trappen} trappen, η_is = {a.eta_mvr}, watersproeiing)")
    print(f"  {'T_lp':>6}{'p_lp bar':>10}{'COP_WP':>8}{'W_WP kW':>9}{'W_MVR kW':>10}{'W_MVR/W':>9}{'inspuit':>9}{'COP':>7}")
    for r in res_B:
        mark = "  <- optimum" if r is best_B else ""
        print(f"  {r['T_lp']:6.0f}{r['p_lp']:10.3f}{r['COP_wp']:8.2f}{r['w_wp'] * a.Q:9.0f}{r['w_mvr'] * a.Q:10.0f}{r['aandeel_mvr']:9.0%}"
              f"{r['inj']:9.1%}{r['COP']:7.2f}{mark}")
    print(f"  persdamptemperaturen MVR bij optimum: " + ", ".join(f"{t:.0f} °C" for t in best_B["T_pers"]))

    if res_A:
        bA = res_A[0]
        print(f"\nConclusie: beste gesloten WP {bA['fluid']}: COP = {bA['COP']:.2f} "
              f"(T_cond {bA['T_cond']:.1f} °C, {a.Q / bA['COP']:.0f} kW_el voor {a.Q:.0f} kW stoom); "
              f"WP + MVR: COP = {best_B['COP']:.2f} bij T_lp = {best_B['T_lp']:.0f} °C. "
              f"Theoretisch maximum (Lorenz) {COP_lorenz:.2f}.")

    if a.geen_figuur or not res_A:
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    c = res_A[0]
    f = np.linspace(0, 1, 200)
    Q = f * st["q"] * m_stoom / 1e3
    ax1.plot(Q, T_koudemiddel_van_Q(c, f), "r", lw=2, label=f"{c['fluid']} (pers {c['T2']:.0f} °C → {c['T3']:.0f} °C)")
    ax1.plot(Q, T_stoom_van_Q(st, f * st["q"]), "b", lw=2, label=f"water {a.T_voeding:.0f} °C → stoom {a.T_stoom:.0f} °C")
    ax1.set(xlabel="Q stoomgenerator [kW]", ylabel="T [°C]",
            title=f"A: T,Q-diagram stoomgenerator, COP = {c['COP']:.2f}, min ΔT = {c['min_dT']:.1f} K")
    ax1.grid(alpha=.3); ax1.legend()
    ax2.plot([r["T_lp"] for r in res_B], [r["COP"] for r in res_B], "o-", label="WP + MVR")
    for cc in res_A[:1]:
        ax2.axhline(cc["COP"], ls="--", lw=1, color="0.4")
        ax2.text(T_lps[0], cc["COP"], f" A: {cc['fluid']} {cc['COP']:.2f}", va="bottom", fontsize=8)
    ax2.axhline(COP_lorenz, color="k", lw=1); ax2.text(T_lps[0], COP_lorenz, " Lorenz", va="bottom", fontsize=8)
    ax2.set(xlabel="T lagedrukstoom T_lp [°C]", ylabel="COP", title="B: COP warmtepomp + MVR vs. tussen-temperatuur")
    ax2.grid(alpha=.3); ax2.legend()
    fig.suptitle(f"Oververhitte stoom {a.T_stoom:.0f} °C / {a.p_stoom} bara uit bron {a.bron[0]}→{a.bron[1]} °C")
    fig.tight_layout()
    if a.opslaan:
        fig.savefig(a.opslaan, dpi=130)
        print(f"figuur opgeslagen: {a.opslaan}")
    else:
        plt.show()


if __name__ == "__main__":
    main()

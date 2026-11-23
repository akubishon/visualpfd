"""
ITM Neptune V – procesimulator (Streamlit + CoolProp)

Starten:
    pip install -r requirements.txt
    streamlit run app.py

Elke wijziging rekent het hele PFD opnieuw door met echte CoolProp-aanroepen
(itm_model.coolprop) en, ter vergelijking, met de formules van het rekenblad (itm_model.excel).
De units worden bij- en afgeschakeld volgens de gevraagde last of een dagprofiel van de wind.
"""
import math
import random
import time
from dataclasses import asdict

import CoolProp.CoolProp as CP
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from itm_model import Invoer, excel, coolprop

st.set_page_config(page_title="ITM Neptune V procesimulator", page_icon="⚗️", layout="wide")

BASIS = Invoer()
T0 = 273.15
N_MAX = BASIS.n_units


# ------------------------------------------------------------------ hulpfuncties
def nl(v, d=1):
    """Nederlandse getalnotatie: 1.234,5"""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "–"
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(show_spinner=False, max_entries=1024)
def bereken(invoer: dict):
    i = Invoer(**invoer)
    return excel(i), coolprop(i)


# ------------------------------------------------------------------ dagprofielen wind
@st.cache_data
def windprofiel(naam: str):
    """Beschikbaar windvermogen per uur, als fractie van het windparkvermogen (illustratief)."""
    rnd = random.Random({"Wisselvallige herfstdag": 3, "Storm met afschakeling": 7, "Rustige zomerdag": 11}[naam])
    out = []
    for h in range(24):
        if naam == "Wisselvallige herfstdag":
            v = 0.55 + 0.32 * math.sin(2 * math.pi * (h - 4) / 24) + rnd.uniform(-0.12, 0.12)
        elif naam == "Storm met afschakeling":
            v = 0.95 + rnd.uniform(-0.08, 0.05)
            if 14 <= h <= 16:          # stormafschakeling windturbines
                v = 0.0
            elif h in (13, 17):
                v = 0.35
        else:
            v = 0.32 + 0.2 * math.cos(2 * math.pi * (h - 2) / 24) + rnd.uniform(-0.06, 0.06)
            if 11 <= h <= 15:
                v *= 0.25
        out.append(max(0.0, min(1.0, v)))
    return out


# ------------------------------------------------------------------ invoer
# sleutel, label, min, max, stap, eenheid, decimalen, toelichting
GROEPEN = {
    "Bedrijfsgrenzen": [
        ("m_min_pct", "Min. debiet K-101 (turndown)", 10.0, 80.0, 1.0, "%", 0, "Daaronder gaat het tekort als recycle S9 rond."),
        ("Q_ITM_EOL", "Reject heat ITM per unit (EOL)", 1200.0, 2200.0, 10.0, "kW", 0, None),
    ],
    "O₂-lijn": [
        ("T_O2_uit", "T O₂-stroom uit ITM *", 55.0, 85.0, 1.0, "°C", 0, None),
        ("P_O2_uit", "p O₂-stroom uit ITM *", 0.0, 0.5, 0.05, "barg", 2, None),
        ("w_H2O", "Water in O₂-stroom", 0.05, 0.25, 0.01, "–", 2, None),
        ("T_KO", "T na E-101 / KO-drum", 15.0, 45.0, 1.0, "°C", 0, None),
        ("P_RWZI", "Druk naar RWZI *", 0.3, 1.5, 0.05, "barg", 2, None),
        ("eta_K102", "η isentroop K-102", 0.5, 0.85, 0.01, "–", 2, None),
    ],
    "H₂-lijn": [
        ("P_V101_min", "Min. druk V-101 (zuig K-101)", 10.0, 28.0, 0.5, "barg", 1, None),
        ("P_V101_max", "Max. druk V-101", 21.0, 29.5, 0.5, "barg", 1, None),
        ("P_K101_uit", "Einddruk K-101", 67.0, 100.0, 0.5, "barg", 1, None),
        ("eta_K101", "η isentroop K-101", 0.6, 0.9, 0.01, "–", 2, None),
        ("dT_pakket", "ΔT pakketkoelers", 0.0, 60.0, 1.0, "K", 0, None),
        ("T_E102_uit", "H₂ uit E-102", 35.0, 90.0, 1.0, "°C", 0, None),
        ("T_E103_uit", "H₂ uit E-103", 15.0, 35.0, 1.0, "°C", 0, None),
        ("t_V101", "Opslagtijd V-101", 0.1, 1.0, 0.05, "h", 2, None),
        ("t_V102", "Opslagtijd V-102", 10.0, 120.0, 5.0, "s", 0, None),
    ],
    "Warmtenet en warmtepomp": [
        ("T_kc_uit", "Koelcircuit uit ITM (A) *", 50.0, 75.0, 1.0, "°C", 0, None),
        ("T_kc_retour", "Koelcircuit retour (B) *", 35.0, 65.0, 1.0, "°C", 0, None),
        ("T_net_retour", "Warmtenet retour *", 25.0, 55.0, 1.0, "°C", 0, None),
        ("T_E201_uit", "Warmtenet na E-201", 35.0, 70.0, 1.0, "°C", 0, None),
        ("T_net_aanvoer", "Warmtenet aanvoer *", 55.0, 90.0, 1.0, "°C", 0, None),
        ("dT_min", "ΔT min. wisselaar", 2.0, 10.0, 0.5, "K", 1, None),
        ("eta_K201", "η isentroop K-201 (CoolProp)", 0.5, 0.85, 0.01, "–", 2, None),
        ("eta_II", "η II warmtepomp (rekenblad)", 0.3, 0.7, 0.01, "–", 2, None),
    ],
}
KOUDEMIDDELEN = ["R1234ze(E)", "R600a", "Ammonia", "R134a", "R1233zd(E)"]
ALLE = {k[0]: k for g in GROEPEN.values() for k in g}
SNELHEID = {"Traag": 3.0, "Normaal": 1.8, "Snel": 1.0}
BEDRIJF_STANDAARD = dict(modus="Handmatig", last=100.0, strategie="Bijschakelen", min_unit=20.0,
                         profiel="Wisselvallige herfstdag", wind_ratio=1.2, spelen=False, snelheid="Normaal",
                         net_aan=True, wp_aan=True, alles=False, koudemiddel=BASIS.koudemiddel,
                         **{f"u{j}": True for j in range(1, N_MAX + 1)})


def reset():
    for k in ALLE:
        st.session_state[k] = float(getattr(BASIS, k))
    for k, v in BEDRIJF_STANDAARD.items():
        st.session_state[k] = v
    st.session_state["uur"] = 0


for k in ALLE:
    st.session_state.setdefault(k, float(getattr(BASIS, k)))
for k, v in BEDRIJF_STANDAARD.items():
    st.session_state.setdefault(k, v)
st.session_state.setdefault("uur", 0)
st.session_state.setdefault("_laatste_tik", 0.0)


def ga_naar_uur():
    st.session_state["uur"] = int(st.session_state["uur_kies"])


with st.sidebar:
    st.header("Bedrijf")
    st.radio("Modus", ["Handmatig", "Dagprofiel wind"], key="modus", horizontal=True,
             help="Handmatig: jij kiest de last. Dagprofiel: de last volgt het windvermogen uur voor uur.")
    if st.session_state["modus"] == "Handmatig":
        st.slider("Gevraagde installatielast [%]", 0.0, 100.0, step=1.0, key="last", format="%.0f",
                  help="100 % = alle 8 units op vollast.")
    else:
        st.selectbox("Windprofiel", ["Wisselvallige herfstdag", "Storm met afschakeling", "Rustige zomerdag"], key="profiel")
        st.slider("Windpark / elektrolysevermogen", 0.5, 2.0, step=0.05, key="wind_ratio",
                  help="Overdimensionering van het windpark t.o.v. de 8 ITM-units.")
        c1, c2 = st.columns(2)
        c1.toggle("▶ Afspelen", key="spelen")
        c2.selectbox("Tempo", list(SNELHEID), key="snelheid", label_visibility="collapsed")
        st.slider("Ga naar uur", 0, 23, value=int(st.session_state["uur"]), key="uur_kies", on_change=ga_naar_uur)
    with st.expander("Inzet en beschikbaarheid"):
        st.radio("Inzet units", ["Bijschakelen", "Gelijk verdelen"], key="strategie", horizontal=True,
                 help="Bijschakelen: zo weinig mogelijk units, die op hoge last. Gelijk verdelen: alle beschikbare units op dezelfde last.")
        st.slider("Minimale last per unit [%]", 5.0, 50.0, step=1.0, key="min_unit", format="%.0f")
        st.caption("Units beschikbaar (uitvinken = onderhoud)")
        ucols = st.columns(4)
        for j in range(1, N_MAX + 1):
            ucols[(j - 1) % 4].checkbox(f"#{j}", key=f"u{j}")
        st.toggle("Warmtenet neemt warmte af", key="net_aan", help="Uit: ITM-warmte gaat naar de eigen adiabatische koelers.")
        st.toggle("Warmtepomp WP-201 aan", key="wp_aan", help="Uit: alleen E-201, het net komt maximaal tot T na E-201.")
    with st.expander("Weergave"):
        weergave = st.radio("Getallen", ["Totaal", "Per unit"], horizontal=True)
        st.toggle("Alle labels in het schema tonen", key="alles",
                  help="Uit: alleen namen, status en kerngetallen; details verschijnen als je over een onderdeel beweegt.")

    st.header("Procesinvoer")
    for naam, ctls in GROEPEN.items():
        with st.expander(naam):
            for key, label, lo, hi, step, unit, dec, hlp in ctls:
                st.slider(f"{label} [{unit}]", lo, hi, step=step, key=key, help=hlp, format=f"%.{dec}f")
            if naam.startswith("Warmtenet"):
                st.selectbox("Koudemiddel WP-201", KOUDEMIDDELEN, key="koudemiddel", help="Alleen voor het CoolProp-model.")
    st.button("Terug naar basisinvoer", on_click=reset, width="stretch")
    st.caption("\\* = aanname uit het rekenblad, nog te bevestigen.")

PROCES = asdict(BASIS)
PROCES.update({k: st.session_state[k] for k in ALLE})
PROCES.update(koudemiddel=st.session_state["koudemiddel"], net_aan=st.session_state["net_aan"], wp_aan=st.session_state["wp_aan"])
BESCHIKBAAR = [st.session_state[f"u{j}"] for j in range(1, N_MAX + 1)]


def inzet(last_pct):
    """Verdeel de gevraagde last over de beschikbare units. Geeft (last per unit-lijst 0..1, aantal aan)."""
    vrij = [j for j in range(N_MAX) if BESCHIKBAAR[j]]
    P = min(last_pct / 100 * N_MAX, len(vrij))          # in unit-equivalenten
    mn = st.session_state["min_unit"] / 100
    if not vrij or P < mn - 1e-9:
        return [0.0] * N_MAX, 0
    if st.session_state["strategie"] == "Bijschakelen":
        k = math.ceil(P - 1e-9)
    else:
        k = len(vrij)
    if P / k < mn:
        k = max(1, int(P / mn))
    per = min(1.0, P / k)
    loads = [0.0] * N_MAX
    for j in vrij[:k]:
        loads[j] = per
    return loads, k


def last_voor_uur(h):
    return min(100.0, 100 * windprofiel(st.session_state["profiel"])[h % 24] * st.session_state["wind_ratio"])


def bedrijfspunt(uur=None):
    if st.session_state["modus"] == "Handmatig":
        last, wind = st.session_state["last"], None
    else:
        h = st.session_state["uur"] if uur is None else uur
        wind = windprofiel(st.session_state["profiel"])[h % 24]
        last = last_voor_uur(h)
    loads, k = inzet(last)
    d = dict(PROCES)
    if k:
        d.update(n_units=k, belasting=100 * max(loads))
    return d, loads, k, last, wind


def is_donker():
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


# ------------------------------------------------------------------ meldingen
def meldingen(r):
    i = r["i"]
    n = i.n_units
    m = []
    def chk(ok, tekst):
        m.append(("ok" if ok else "fout", tekst))
    chk(abs(i.m_O2mix - r["m_cond"] - r["m_gas"]) < 1e-6, "S13 = S15 + S17")
    chk(abs(i.m_voedwater - r["m_vers"] - r["m_cond"]) < 1e-6, "S2 = S1 + S16")
    chk(abs(i.m_H2 - r["m_backbone"]) < 1e-6, "S4 = S12 + S10")
    chk(abs(r["chk_p5"]) < 1e-3, f"Energiebalans warmte: {nl(r['chk_p5'], 3)} kW")
    m.append(("ok" if abs(r["chk_E"]) < 2 else "let op",
              f"Energiebalans installatie per unit: {nl(r['chk_E'], 2)} kW"
              + (" (reëel gas: h van H₂ bij 25 °C hangt af van de druk)" if abs(r["chk_E"]) > 0.01 else "")))
    if r["T_uit_K101"] > 180:
        m.append(("let op", f"T uit K-101 = {nl(r['T_uit_K101'], 0)} °C: waarschijnlijk 2 trappen met tussenkoeling"))
    if i.T_E103_uit > 30:
        m.append(("fout", f"H₂ naar backbone {nl(i.T_E103_uit, 0)} °C > 30 °C"))
    if "T_dauw_S18" in r and r["T_dauw_S18"] > r["T_S18"]:
        m.append(("fout", f"Dauwpunt S18 ({nl(r['T_dauw_S18'], 1)} °C) boven gastemperatuur ({nl(r['T_S18'], 1)} °C)"))
    if r["T_dauw"] > i.T_O2_uit:
        m.append(("let op", "O₂-stroom bevat al vloeibaar water bij uitlaat ITM"))
    if i.net_aan:
        if i.T_kc_uit - i.T_E201_uit < i.dT_min - 1e-9:
            m.append(("fout", f"E-201 warme kant: ΔT {nl(i.T_kc_uit - i.T_E201_uit, 1)} K < ΔT min"))
        if r["T_kc_tussen"] - i.T_net_retour < i.dT_min - 1e-9:
            m.append(("fout", f"E-201 koude kant: ΔT {nl(r['T_kc_tussen'] - i.T_net_retour, 1)} K < ΔT min"))
        if i.wp_aan and r["T_kc_tussen"] < i.T_kc_retour:
            m.append(("fout", f"Koelcircuit na E-201 ({nl(r['T_kc_tussen'], 1)} °C) al onder retour: E-201 neemt te veel warmte"))
        if not i.wp_aan:
            m.append(("let op", f"Warmtepomp uit: het net krijgt maar {nl(i.T_E201_uit, 0)} °C in plaats van {nl(i.T_net_aanvoer, 0)} °C"))
    else:
        m.append(("let op", f"Warmtenet uit: {nl(r['Q_adiabatisch'] / 1000, 2)} MW gaat via de adiabatische koelers naar buiten"))
    if i.T_kc_retour >= i.T_kc_uit:
        m.append(("fout", "Koelcircuit: retour moet lager zijn dan aanvoer"))
    if not (i.T_net_retour < i.T_E201_uit < i.T_net_aanvoer):
        m.append(("fout", "Warmtenet: T na E-201 moet tussen retour en aanvoer liggen"))
    if i.P_V101_max <= i.P_V101_min:
        m.append(("fout", "V-101: max. druk moet boven min. druk liggen"))
    if r["m_S9"] > 0:
        m.append(("let op", f"Deellast: recycle via FV-101 {nl(r['m_S9'] * n, 1)} kg/h"))
    return m


# ------------------------------------------------------------------ PFD als geanimeerde SVG
def tempkleur(T):
    if T is None or (isinstance(T, float) and not math.isfinite(T)):
        return "transparent"
    f = max(0.0, min(1.0, (T - 10) / 190))
    return f"hsl({220 - 220 * f:.0f} 70% 50%)"


def padlengte(d):
    x = y = 0.0
    L = 0.0
    tok = d.split()
    k = 0
    while k < len(tok):
        c = tok[k]
        if c == "M":
            x, y = float(tok[k + 1]), float(tok[k + 2]); k += 3
        elif c == "H":
            nx = float(tok[k + 1]); L += abs(nx - x); x = nx; k += 2
        elif c == "V":
            ny = float(tok[k + 1]); L += abs(ny - y); y = ny; k += 2
        else:
            k += 1
    return L


def kleuren(donker):
    if donker:
        return dict(bg="#0e1117", panel="#151c23", soft="#1c252e", ink="#e2e8ee", muted="#93a2b1", line="#2a3541",
                    h2="#5aa4ec", o2="#6cc25a", waste="#c98a63", kc="#b18ae6", net="#f0a64a", kw="#8fb1e0", ref="#3cc4b6",
                    heat="#f07a4f", on="#3ddc74", warn="#f5b12a", off="#56616d", err="#ff6b5e")
    return dict(bg="#ffffff", panel="#ffffff", soft="#f3f6f9", ink="#16202a", muted="#586878", line="#d3dae2",
                h2="#1d6fb8", o2="#3a8a2c", waste="#8a4b2a", kc="#7b4bb2", net="#d27a1d", kw="#5f86bd", ref="#138a80",
                heat="#e0531f", on="#1fa64a", warn="#d98a00", off="#b4bec8", err="#d0342c")


STROOMNAAM = {
    "S1": "Vers voedwater → mengpunt", "S2": "Mengpunt → ITM (voedwater)", "S3": "ITM → afvalwater",
    "S4": "ITM → V-101 (H₂)", "S5": "V-101 → K-101", "S6": "K-101 → E-102", "S7": "E-102 → E-103",
    "S8": "E-103 → kwaliteitscontrole", "S9": "Recycle via FV-101 → V-101", "S10": "Blowoff V-101",
    "S11": "Kwaliteitscontrole → V-102", "S12": "PCV-101 → H₂-backbone", "S13": "ITM → E-101 (O₂ + H₂O)",
    "S14": "E-101 → V-103", "S15": "V-103 → P-101 (condensaat)", "S16": "P-101 → mengpunt (condensaat)",
    "S17": "V-103 → K-102 (O₂ + damp)", "S18": "K-102 → RWZI", "A": "Koelcircuit uit ITM (water + Coolflow)",
    "A2": "Koelcircuit E-201 → E-202", "B": "Koelcircuit retour naar ITM", "AK": "Koelcircuit naar adiabatische koelers",
    "N1": "Warmtenet retour → E-201", "N2": "Warmtenet E-201 → E-203", "N3": "Warmtenet aanvoer",
    "R1": "Koudemiddel E-202 → K-201 (damp)", "R2": "Koudemiddel K-201 → E-203 (hete damp)",
    "R3": "Koudemiddel E-203 → TV-201 (vloeistof)", "R4": "Koudemiddel TV-201 → E-202 (natte damp)",
    "KW1": "Koelwater E-101 (20 → 30 °C)", "KW2": "Koelwater E-103 (20 → 30 °C)", "WW1": "Warmtenet-zijstroom E-102 (40 → 70 °C)",
}


def padpunt(d, frac=0.5):
    """Punt op fractie van de lengte van een M/H/V-pad (voor het stroomlabel)."""
    pts, x, y, tok, k = [], 0.0, 0.0, d.split(), 0
    while k < len(tok):
        c = tok[k]
        if c == "M":
            x, y = float(tok[k + 1]), float(tok[k + 2]); pts.append((x, y)); k += 3
        elif c == "H":
            x = float(tok[k + 1]); pts.append((x, y)); k += 2
        elif c == "V":
            y = float(tok[k + 1]); pts.append((x, y)); k += 2
        else:
            k += 1
    seg = [(a, b, abs(b[0] - a[0]) + abs(b[1] - a[1])) for a, b in zip(pts, pts[1:])]
    doel = sum(s[2] for s in seg) * frac
    for a, b, L in seg:
        if doel <= L and L > 0:
            t_ = doel / L
            return a[0] + (b[0] - a[0]) * t_, a[1] + (b[1] - a[1]) * t_
        doel -= L
    return pts[-1]


def live_html(r, loads, k, mul, donker, stil, klok, alles):
    """Statusbord + geanimeerd procesflowschema als één HTML-document, met popups bij hover."""
    import html as _h
    import json as _json
    C = kleuren(donker)
    i = r["i"]
    n = max(k, 1)
    f = mul
    eh = "totaal" if mul > 1 else "per unit"
    net_aan, wp_aan = i.net_aan, i.wp_aan and i.net_aan
    kcs = r["m_kc"] / n * 3600
    net = r["m_net_th"] * 1000
    z = 0.0 if stil else 1.0
    a2 = kcs if net_aan else 0.0
    wp = 1.0 if wp_aan else 0.0
    # id, kleur, pad, labelpositie (alles-modus), (m, T, p, soort), positie id-label op het pad (fractie)
    S = [
        ("S1", "o2", "M -56 300 H -12", (-58, 252), (r["m_vers"] * z, i.T_vers, i.P_ITM_voed, "m"), .5),
        ("S2", "o2", "M 12 300 H 120", (8, 318), (i.m_voedwater * z, r["T_mix"], i.P_ITM_voed, "m"), .5),
        ("S3", "waste", "M 160 420 V 490", (56, 440), (i.m_afvalwater * z, None, None, "m"), .6),
        ("S4", "h2", "M 250 200 H 300", (204, 122), (i.m_H2 * z, i.T_H2, i.P_H2_ITM, "m"), .5),
        ("S5", "h2", "M 344 230 H 450", (352, 248), (r["m_S5"] * z, i.T_H2, i.P_V101_min, "m"), .5),
        ("S6", "h2", "M 510 230 H 596", (516, 162), (r["m_S5"] * z, r["T_S6"], i.P_K101_uit, "m"), .5),
        ("S7", "h2", "M 644 230 H 736", (648, 162), (r["m_S5"] * z, i.T_E102_uit, i.P_K101_uit, "m"), .5),
        ("S8", "h2", "M 784 230 H 920", (784, 162), (r["m_S5"] * z, i.T_E103_uit, i.P_K101_uit, "m"), .3),
        ("S9", "h2", "M 900 230 V 100 H 334 V 140", (680, 62), (r["m_S9"] * z, i.T_E103_uit, None, "m"), .62),
        ("S10", "h2", "M 310 140 V 72", (214, 62), (0.0, None, None, "m"), .5),
        ("S11", "h2", "M 990 230 H 1030", None, (r["m_backbone"] * z, i.T_E103_uit, i.P_backbone, "m"), .5),
        ("S12", "h2", "M 1126 230 H 1190", (1104, 248), (r["m_backbone"] * z, i.T_E103_uit, i.P_backbone, "m"), .5),
        ("S13", "o2", "M 250 400 H 321", (232, 420), (i.m_O2mix * z, i.T_O2_uit, i.P_O2_uit, "m"), .5),
        ("S14", "o2", "M 369 400 H 430", (366, 318), (i.m_O2mix * z, i.T_KO, i.P_O2_uit, "m"), .5),
        ("S15", "o2", "M 450 480 V 544", (462, 488), (r["m_cond"] * z, i.T_KO, i.P_O2_uit, "m"), .5),
        ("S16", "o2", "M 434 560 H 0 V 312", (250, 566), (r["m_cond"] * z, i.T_KO, i.P_ITM_voed, "m"), .35),
        ("S17", "o2", "M 470 380 H 560", (478, 318), (r["m_gas"] * z, i.T_KO, i.P_O2_uit, "m"), .5),
        ("S18", "o2", "M 620 380 H 760", (644, 318), (r["m_gas"] * z, r["T_S18"], i.P_RWZI, "m"), .4),
        ("A", "kc", "M 205 420 V 660 H 380", (236, 612), (kcs * z, i.T_kc_uit, None, "kgs"), .85),
        ("A2", "kc", "M 460 660 H 560", None, (a2 * z, r["T_kc_tussen"], None, "kgs"), .5),
        ("B", "kc", "M 600 690 V 750 H 225 V 420", (252, 758), (a2 * z, i.T_kc_retour, None, "kgs"), .45),
        ("AK", "kc", "M 205 648 H 190", None, ((0.0 if net_aan else kcs) * z, i.T_kc_uit, None, "kgs"), .5),
        ("N1", "net", "M 420 850 V 690", (290, 800), (net * z, i.T_net_retour, None, "th"), .5),
        ("N2", "net", "M 420 630 V 604 H 900 V 630", (620, 562), (net * z, i.T_E201_uit, None, "th"), .5),
        ("N3", "net", "M 900 690 V 850", (912, 800), (net * z, r["T_aanvoer"], None, "th"), .5),
        ("R1", "ref", "M 640 646 H 722", None, (z * wp, None, None, "x"), .5),
        ("R2", "ref", "M 778 646 H 860", None, (z * wp, None, None, "x"), .5),
        ("R3", "ref", "M 860 676 H 800 V 740 H 762", None, (z * wp, None, None, "x"), .5),
        ("R4", "ref", "M 728 740 H 680 V 676 H 640", None, (z * wp, None, None, "x"), .5),
        ("KW1", "kw", "M 345 472 V 424", None, (z, None, None, "x"), .5),
        ("KW2", "kw", "M 760 300 V 254", None, (z, None, None, "x"), .5),
        ("WW1", "net", "M 620 300 V 254", None, ((z if net_aan else 0.0), None, None, "x"), .5),
    ]
    TIPS = {}
    ref = {"h2": 720, "o2": 11448, "waste": 3300, "kc": 46 * 3600, "net": 440e3}
    lijnen, deeltjes, tags, raak = [], [], [], []

    def debiet(mm, soort):
        if soort == "th":
            return f"{nl(mm / 1000, 0)} t/h"
        if soort == "kgs":
            return f"{nl(mm / 3600 * mul, 1)} kg/s"
        return f"{nl(mm * mul, 1 if mm * mul < 100 else 0)} kg/h"

    for sid, kl, d, pos, v, fr in S:
        m, T, p, soort = v
        m_tot = m * n if soort in ("m", "kgs") else m
        nul = m <= 1e-9
        if nul:
            lijnen.append(f'<path d="{d}" class="st" stroke="{C["off"]}" stroke-width="1.6" stroke-dasharray="2 5"/>')
        else:
            dash = ' stroke-dasharray="7 4"' if kl in ("kw", "ref") else ""
            lijnen.append(f'<path d="{d}" class="st" stroke="{C[kl]}" stroke-opacity=".3" stroke-width="6"{dash}/>'
                          f'<path d="{d}" class="st" stroke="{C[kl]}" stroke-width="1.6"/>')
            rel = 0.7 if soort == "x" else max(0.12, min(1.4, m_tot / ref[kl]))
            L = padlengte(d)
            dur = L / (22 + 95 * rel)
            aantal = max(1, int(L / (34 if rel > 0.4 else 48)))
            rr = 2.4 + 1.4 * min(rel, 1)
            for q in range(aantal):
                deeltjes.append(f'<circle r="{rr:.1f}" fill="{C[kl]}" stroke="{C["panel"]}" stroke-width="1" pointer-events="none">'
                                f'<animateMotion dur="{dur:.2f}s" begin="-{dur * q / aantal:.2f}s" repeatCount="indefinite" path="{d}"/></circle>')
        # popup
        rows = [["Debiet (" + eh + ")", "geen stroming" if nul else ("in bedrijf" if soort == "x" else debiet(m, soort))]]
        if T is not None and not nul and math.isfinite(T):
            rows.append(["Temperatuur", f"{nl(T, 1)} °C"])
        if p is not None:
            rows.append(["Druk", f"{nl(p, 1)} barg"])
        if sid in ("S13", "S14", "S17", "S18") and not nul:
            rows.append(["O₂ / damp / vloeibaar", f"{nl(r['m_O2'] * mul, 0)} / {nl((r['m_H2O_in'] if sid == 'S13' else r['m_v']) * mul, 0)} / "
                                                   f"{nl(r['m_cond'] * mul if sid == 'S14' else 0, 0)} kg/h"])
        TIPS[sid] = {"t": f"{sid if not sid.startswith(('A', 'B', 'N', 'R', 'K', 'W')) else ''} {STROOMNAAM.get(sid, sid)}".strip(), "r": rows}
        raak.append(f'<path d="{d}" class="raak" data-tip="{sid}"/>')
        # labels
        if stil:
            continue
        if alles and pos:
            a = debiet(m, soort)
            b = " · ".join(([f"{nl(T, 1)} °C"] if (T is not None and not nul) else []) + ([f"{nl(p, 1)} barg"] if (p is not None and mul == 1 and not nul) else [])) or "–"
            naam = {"A": "A koelcircuit", "B": "B retour", "N1": "Net retour", "N2": "Net na E-201", "N3": "Net aanvoer"}.get(sid, sid)
            w = max(len(naam) * 7 + len(a) * 6.7 + 16, len(b) * 6.7 + 28)
            tags.append(f'<g transform="translate({pos[0]},{pos[1]})" opacity="{0.5 if nul else 1}" data-tip="{sid}" class="tip">'
                        f'<rect width="{w:.0f}" height="34" rx="4" fill="{C["panel"]}" stroke="{C["line"]}"/>'
                        f'<rect x="6" y="21" width="8" height="8" rx="1.5" fill="{tempkleur(None if nul else T)}" stroke="{C["line"]}" stroke-width=".6"/>'
                        f'<text x="6" y="14" class="v"><tspan class="id">{naam}</tspan>  {a}</text>'
                        f'<text x="18" y="29" class="v">{b}</text></g>')
        elif not alles and sid.startswith("S") and sid != "S11":
            x, y = padpunt(d, fr)
            w = len(sid) * 6.6 + 8
            kleur = C["off"] if nul else C[kl]
            tags.append(f'<g data-tip="{sid}" class="tip"><rect x="{x - w / 2:.1f}" y="{y - 7.5:.1f}" width="{w:.1f}" height="15" rx="7.5" '
                        f'fill="{C["panel"]}" stroke="{kleur}" stroke-width="1.4"/>'
                        f'<text x="{x:.1f}" y="{y + 3.8:.1f}" class="badge" text-anchor="middle" style="fill:{kleur}">{sid}</text></g>')

    def t(x, y, s, cls="lbl", anchor="middle"):
        return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{s}</text>'

    def led(x, y, toestand):
        kl = C[toestand]
        puls = (f'<circle cx="{x}" cy="{y}" r="5" fill="{kl}" opacity=".5"><animate attributeName="r" values="5;10;5" dur="1.8s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values=".5;0;.5" dur="1.8s" repeatCount="indefinite"/></circle>') if toestand in ("on", "warn") else ""
        return puls + f'<circle cx="{x}" cy="{y}" r="5" fill="{kl}" stroke="{C["panel"]}" stroke-width="1.2"/>'

    def rotor(cx, cy, rad, last):
        kl = C["ink"]
        spaken = "".join(f'<line x1="{cx}" y1="{cy}" x2="{cx + rad * math.cos(a):.1f}" y2="{cy + rad * math.sin(a):.1f}" stroke="{kl}" stroke-width="1.6"/>'
                         for a in (0, 2.094, 4.189))
        anim = (f'<animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" dur="{max(0.25, 1.6 / max(last, 0.05)):.2f}s" repeatCount="indefinite"/>'
                if last > 0 else "")
        return f'<g pointer-events="none">{spaken}<circle cx="{cx}" cy="{cy}" r="2.2" fill="{kl}"/>{anim}</g>'

    def gloed(tag, attrs, q, qmax):
        if q <= 0:
            return ""
        a = 0.08 + 0.42 * max(0.0, min(1.0, q / qmax))
        return (f'<{tag} {attrs} fill="{C["heat"]}" opacity="{a:.2f}" pointer-events="none">'
                f'<animate attributeName="opacity" values="{a:.2f};{a * 0.35:.2f};{a:.2f}" dur="2.4s" repeatCount="indefinite"/></{tag}>')

    def hx(cx, cy, q, qmax):
        return (f'<circle cx="{cx}" cy="{cy}" r="24" class="eq"/>' + gloed("circle", f'cx="{cx}" cy="{cy}" r="23"', q, qmax) +
                f'<path d="M {cx - 24} {cy} l 8 -10 l 10 20 l 10 -20 l 10 20 l 10 -10" fill="none" stroke="{C["ink"]}" stroke-width="1.3" pointer-events="none"/>')

    def plaat(x, y, q, qmax):
        zig = f"M {x + 4} {y + 30}" + "".join(f" l 6 {10 if j % 2 else -10} l 6 {-10 if j % 2 else 10}" for j in range(6))
        return (f'<rect x="{x}" y="{y}" width="80" height="60" rx="3" class="eq"/>' +
                gloed("rect", f'x="{x + 1}" y="{y + 1}" width="78" height="58" rx="3"', q, qmax) +
                f'<path d="{zig}" fill="none" stroke="{C["muted"]}" pointer-events="none"/>')

    def valve(cx, cy, open_=False):
        kl = f' style="fill:{C["warn"]}"' if open_ else ""
        return f'<polygon points="{cx - 15},{cy - 10} {cx + 15},{cy + 10} {cx + 15},{cy - 10} {cx - 15},{cy + 10}" class="eq"{kl}/>'

    def vat(x, y, w, h, kl, laag, hoog, dur, uid):
        rx = w / 2
        lvl = ""
        if not stil:
            y_lo, y_hi = y + h * (1 - laag), y + h * (1 - hoog)
            lvl = (f'<clipPath id="c{uid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/></clipPath>'
                   f'<rect x="{x}" y="{y_lo:.1f}" width="{w}" height="{y + h - y_lo:.1f}" fill="{kl}" opacity=".28" clip-path="url(#c{uid})" pointer-events="none">'
                   + (f'<animate attributeName="y" values="{y_lo:.1f};{y_hi:.1f};{y_lo:.1f}" dur="{dur}s" repeatCount="indefinite"/>'
                      f'<animate attributeName="height" values="{y + h - y_lo:.1f};{y + h - y_hi:.1f};{y + h - y_lo:.1f}" dur="{dur}s" repeatCount="indefinite"/>'
                      if dur else "") + "</rect>")
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" class="eq"/>' + lvl

    def g(tip, *delen, titel=None, rows=None):
        if titel:
            TIPS[tip] = {"t": titel, "r": rows or []}
        return f'<g class="tip" data-tip="{tip}">' + "".join(delen) + "</g>"

    def sub(x, y, s, anchor="middle", altijd=False):
        """Detailtekst: alleen zichtbaar in de modus 'alles tonen' (of altijd voor kerngetallen)."""
        return t(x, y, s, "sub", anchor) if (alles or altijd) and not stil else ""

    # ITM-modules met belastingsbalk en gasbellen
    mods = []
    for j in range(N_MAX):
        y = 200 + j * 26
        ld = loads[j]
        if not BESCHIKBAAR[j]:
            st_ = "Onderhoud (niet beschikbaar)"
            inner = (f'<rect x="132" y="{y}" width="106" height="18" rx="2" fill="url(#arcering)" stroke="{C["warn"]}" stroke-width="1"/>'
                     + led(142, y + 9, "off") + t(152, y + 13, f"#{j + 1} onderhoud", "mod", "start"))
        else:
            inner = f'<rect x="132" y="{y}" width="106" height="18" rx="2" fill="{C["soft"]}" stroke="{C["line"]}" stroke-width="1"/>'
            if ld > 0:
                st_ = "Vollast" if ld > 0.999 else "Deellast"
                inner += f'<rect x="133" y="{y + 1}" width="{104 * ld:.1f}" height="16" rx="1.5" fill="{C["o2"]}" opacity=".28"/>'
                for b in range(2 + int(5 * ld)):
                    bx = 150 + (b * 37) % int(max(20, 100 * ld - 6))
                    du = 1.0 + (b % 3) * 0.35
                    inner += (f'<circle cx="{bx}" cy="{y + 16}" r="1.6" fill="{C["h2"]}" pointer-events="none"><animate attributeName="cy" values="{y + 16};{y + 2}" dur="{du:.2f}s" begin="-{b * 0.27:.2f}s" repeatCount="indefinite"/>'
                              f'<animate attributeName="opacity" values="1;0" dur="{du:.2f}s" begin="-{b * 0.27:.2f}s" repeatCount="indefinite"/></circle>')
                inner += led(142, y + 9, "on" if ld > 0.999 else "warn") + t(152, y + 13, f"#{j + 1}  {nl(ld * 100, 0)} %", "mod", "start")
            else:
                st_ = "Stand-by (wacht op vermogen)"
                inner += led(142, y + 9, "off") + t(152, y + 13, f"#{j + 1}  stand-by", "mod muted", "start")
        rows = [["Status", st_], ["Last", f"{nl(ld * 100, 0)} %"]]
        if ld > 0:
            rows += [["H₂-productie", f"{nl(i.m_H2, 1)} kg/h"], ["Stroom (EOL)", f"{nl(r['P_AC_EOL'], 0)} kW"],
                     ["Reject heat", f"{nl(i.Q_ITM_EOL, 0)} kW"], ["Voedwater", f"{nl(i.m_voedwater, 0)} kg/h"]]
        rows += [["Nominaal", "90 kg/h H₂ · 5,39 MW (EOL)"]]
        mods.append(g(f"ITM{j + 1}", inner, titel=f"ITM Neptune V #{j + 1}", rows=rows))

    lk = 0.0 if stil else r["m_S5"] / 90.0
    recyc = r["m_S9"] > 0 and not stil
    s_on = "off" if stil else "on"
    qn = 1 if stil else 0
    cy_ = r.get("cyclus") or {}
    E = [
        '<pattern id="arcering" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<rect width="6" height="6" fill="{C["soft"]}"/><line x1="0" y1="0" x2="0" y2="6" stroke="{C["warn"]}" stroke-width="1.4" opacity=".55"/></pattern>',
        '<rect x="120" y="170" width="130" height="250" rx="4" class="eq"/>', t(185, 190, f"ITM · {k}/{N_MAX} aan"),
        *mods,
        g("M1", '<circle cx="0" cy="300" r="12" class="eq"/>', titel="Mengpunt voedwater",
          rows=[["Vers water S1", f"{nl(r['m_vers'] * f, 0)} kg/h · {nl(i.T_vers, 0)} °C"], ["Condensaat S16", f"{nl(r['m_cond'] * f, 0)} kg/h · {nl(i.T_KO, 0)} °C"],
                ["Naar ITM S2", f"{nl(i.m_voedwater * f, 0)} kg/h · {nl(r['T_mix'], 1)} °C"], ["Eis ITM", "5–40 °C, 5–40 barg"]]),
        g("V101", vat(300, 140, 44, 130, C["h2"], 0.25, 0.9, 6, "v101"), t(294, 290, "V-101", anchor="end"), led(336, 132, s_on),
          sub(294, 306, f"{nl(r['V_V101'] * f, 0)} m³", "end"),
          titel="V-101 lagedrukbuffer", rows=[["Druk", f"{nl(i.P_V101_min, 1)}–{nl(i.P_V101_max, 1)} barg"], ["Opslagtijd", f"{nl(i.t_V101 * 60, 0)} min"],
                                              ["Volume (" + eh + ")", f"{nl(r['V_V101'] * f, 1)} m³"], ["Temperatuur", f"{nl(i.T_H2, 0)} °C"]]),
        g("K101", '<polygon points="450,206 510,218 510,242 450,254" class="eq"/>', rotor(480, 230, 10, lk), t(480, 198, f"K-101 ×{k}"),
          led(524, 194, "warn" if recyc else s_on),
          sub(480, 300, f"{nl(r['T_uit_K101'], 0)} → {nl(r['T_S6'], 0)} °C · E3 {nl(r['W_K101'] * f, 0)} kW"),
          titel=f"K-101 H₂-compressorpakket ({k}× in bedrijf)",
          rows=[["Druk", f"{nl(i.P_V101_min, 1)} → {nl(i.P_K101_uit, 1)} barg"], ["T in → uit compressor", f"{nl(i.T_H2, 0)} → {nl(r['T_uit_K101'], 1)} °C"],
                ["Na pakketkoeler", f"{nl(r['T_S6'], 1)} °C"], ["Vermogen E3 (" + eh + ")", f"{nl(r['W_K101'] * f, 1)} kW"],
                ["Pakketkoeler (" + eh + ")", f"{nl(r['Q_pak_K101'] * f, 1)} kW"], ["Recycle S9", f"{nl(r['m_S9'] * f, 1)} kg/h"],
                ["η isentroop", nl(i.eta_K101, 2)]]),
        g("E102", hx(620, 230, -r["Q_E102"] * (1 - qn), 60), t(642, 278, "E-102", anchor="start"),
          led(632, 274, "off" if stil or not net_aan else "on"),
          sub(642, 294, f"Q3 {nl(-r['Q_E102'] * f, 0)} kW", "start"),
          titel="E-102 warmteterugwinning", rows=[["H₂", f"{nl(r['T_S6'], 0)} → {nl(i.T_E102_uit, 0)} °C"], ["Warmte Q3 (" + eh + ")", f"{nl(-r['Q_E102'] * f, 1)} kW"],
                                                  ["Naar", "warmtenet-zijstroom" if net_aan else "koelwater (net uit)"],
                                                  ["Zijstroom (" + eh + ")", f"{nl(r['m_ww_E102'] * f, 0)} kg/h"]]),
        g("E103", hx(760, 230, -r["Q_E103"] * (1 - qn), 60), t(782, 278, "E-103", anchor="start"), led(772, 274, s_on),
          sub(782, 294, f"Q4 {nl(-r['Q_E103'] * f, 0)} kW", "start"),
          titel="E-103 eindkoeler", rows=[["H₂", f"{nl(i.T_E102_uit, 0)} → {nl(i.T_E103_uit, 0)} °C"], ["Warmte Q4 (" + eh + ")", f"{nl(-r['Q_E103'] * f, 1)} kW"],
                                          ["Koelwater (" + eh + ")", f"{nl(r['m_kw_E103'] * f, 0)} kg/h · 20 → 30 °C"]]),
        g("QC", '<rect x="920" y="212" width="70" height="36" rx="3" class="eq"/>', t(955, 235, "QC"), led(984, 206, s_on),
          titel="Kwaliteitscontrole", rows=[["Off-spec", "0 kg/h"], ["Door naar V-102", f"{nl(r['m_backbone'] * f, 1)} kg/h"]]),
        g("V102", vat(1030, 190, 40, 80, C["h2"], 0.3, 0.85, 2.5, "v102"), t(1050, 292, "V-102"), led(1064, 184, s_on),
          sub(1050, 308, f"{nl(r['V_V102'] * f, 1)} m³"),
          titel="V-102 hogedrukbuffer", rows=[["Druk", f"{nl(i.P_backbone, 1)}–{nl(i.P_K101_uit, 1)} barg"], ["Opslagtijd", f"{nl(i.t_V102, 0)} s"],
                                              ["Volume (" + eh + ")", f"{nl(r['V_V102'] * f, 2)} m³"]]),
        g("PCV", valve(1110, 230), t(1110, 208, "PCV-101"),
          titel="PCV-101 drukregelaar", rows=[["Naar backbone", f"{nl(i.P_backbone, 1)} barg (Gasunie)"], ["Debiet", f"{nl(r['m_backbone'] * f, 1)} kg/h"]]),
        g("FV101", valve(610, 100, recyc), t(610, 88, "FV-101"),
          titel="FV-101 recycleklep", rows=[["Stand", "open (deellast)" if recyc else "dicht"], ["Recycle S9", f"{nl(r['m_S9'] * f, 1)} kg/h"],
                                            ["Min. debiet K-101", f"{nl(i.m_min_pct, 0)} % van nominaal"]]),
        g("E101", hx(345, 400, -r["Q_E101"] * (1 - qn), 110), t(345, 364, "E-101"), led(372, 358, s_on),
          sub(345, 488, f"Q1 {nl(-r['Q_E101'] * f, 0)} kW"),
          titel="E-101 voorkoeler", rows=[["O₂-stroom", f"{nl(i.T_O2_uit, 0)} → {nl(i.T_KO, 0)} °C"], ["Warmte Q1 (" + eh + ")", f"{nl(-r['Q_E101'] * f, 1)} kW"],
                                          ["Koelwater (" + eh + ")", f"{nl(r['m_kw_E101'] * f, 0)} kg/h · 20 → 30 °C"],
                                          ["Condensaat (" + eh + ")", f"{nl(r['m_cond'] * f, 1)} kg/h"]]),
        g("V103", vat(430, 356, 40, 124, C["o2"], 0.18, 0.24, 3.5 if not stil else 0, "v103"), t(478, 470, "V-103", anchor="start"),
          titel="V-103 KO-drum", rows=[["Condensaat S15 (" + eh + ")", f"{nl(r['m_cond'] * f, 1)} kg/h"], ["Damp mee S17 (" + eh + ")", f"{nl(r['m_v'] * f, 1)} kg/h"],
                                       ["Damp in gas", f"{nl(r['m_v'] / r['m_gas'] * 100, 2)} %"], ["Temperatuur", f"{nl(i.T_KO, 0)} °C"]]),
        g("K102", '<polygon points="560,356 620,368 620,392 560,404" class="eq"/>', rotor(590, 380, 10, 0 if stil else r["m_gas"] / 803.6),
          t(590, 426, f"K-102 ×{k}"), led(634, 422, s_on),
          sub(590, 442, f"{nl(r['T_uit_K102'], 0)} → {nl(r['T_S18'], 0)} °C · E4 {nl(r['W_K102'] * f, 1)} kW"),
          titel=f"K-102 O₂-compressorpakket ({k}× in bedrijf)",
          rows=[["Druk", f"{nl(i.P_O2_uit, 2)} → {nl(i.P_RWZI, 2)} barg"], ["T uit compressor", f"{nl(r['T_uit_K102'], 1)} °C"],
                ["Na pakketkoeler", f"{nl(r['T_S18'], 1)} °C"], ["Vermogen E4 (" + eh + ")", f"{nl(r['W_K102'] * f, 1)} kW"],
                ["Pakketkoeler (" + eh + ")", f"{nl(r['Q_pak_K102'] * f, 1)} kW"]]
               + ([["Dauwpunt S18", f"{nl(r['T_dauw_S18'], 1)} °C"]] if "T_dauw_S18" in r else [])),
        g("P101", '<circle cx="450" cy="560" r="16" class="eq"/>', rotor(450, 560, 11, 0 if stil else r["m_cond"] / 121.2),
          t(486, 566, f"P-101 ×{k}", anchor="start"), led(476, 562, s_on),
          titel="P-101 condensaatpomp", rows=[["Debiet (" + eh + ")", f"{nl(r['m_cond'] * f, 1)} kg/h"], ["Druk", f"{nl(i.P_O2_uit, 1)} → {nl(i.P_ITM_voed, 1)} barg"],
                                              ["Vermogen E5 (" + eh + ")", f"{nl(r['W_P101'] * f, 3)} kW"]]),
        g("E201", plaat(380, 630, r["Q_E201"] * (1 - qn), 8000), t(372, 704, "E-201", anchor="end"),
          led(320, 700, "on" if net_aan and not stil else "off"), sub(372, 720, f"Q6 {nl(r['Q_E201'] / 1000, 2)} MW", "end"),
          titel="E-201 directe voorverwarming (gedeeld)", rows=[["Warmte Q6", f"{nl(r['Q_E201'], 0)} kW"],
                                                               ["Netwater", f"{nl(i.T_net_retour, 0)} → {nl(i.T_E201_uit, 0)} °C"],
                                                               ["Koelcircuit", f"{nl(i.T_kc_uit, 0)} → {nl(r['T_kc_tussen'], 1)} °C"]]),
        g("E202", plaat(560, 630, r["Q_L"] * (1 - qn), 7000), t(600, 622, "E-202"),
          titel="E-202 verdamper WP-201", rows=[["Warmte Q7", f"{nl(r['Q_L'], 0)} kW"], ["Koelcircuit", f"{nl(r['T_kc_tussen'], 1)} → {nl(i.T_kc_retour, 0)} °C"],
                                                ["Verdampen bij", f"{nl(i.T_kc_retour - i.dT_min, 1)} °C"]]),
        g("K201", '<polygon points="722,624 778,634 778,658 722,668" class="eq"/>', rotor(750, 646, 10, 0.8 if (wp_aan and not stil) else 0),
          t(750, 618, "K-201"),
          titel="K-201 warmtepompcompressor", rows=[["Vermogen E6", f"{nl(r['W_K201'], 0)} kW"], ["COP", nl(r["COP"], 2)]]
                                                  + ([["Druk", f"{nl(cy_['P_evap_bar'], 1)} → {nl(cy_['P_cond_bar'], 1)} bar"], ["Koudemiddel", cy_["fluid"]]] if cy_ and wp_aan else [])),
        g("TV201", valve(745, 740), t(745, 768, "TV-201"),
          titel="TV-201 smoorventiel", rows=[["Druk", f"{nl(cy_['P_cond_bar'], 1)} → {nl(cy_['P_evap_bar'], 1)} bar"] if cy_ else ["", ""]]),
        g("E203", plaat(860, 630, r["Q_H"] * (1 - qn), 8000), t(950, 666, "E-203", anchor="start"),
          sub(950, 682, f"Q8 {nl(r['Q_H'] / 1000, 2)} MW", "start"),
          titel="E-203 condensor WP-201", rows=[["Warmte Q8", f"{nl(r['Q_H'], 0)} kW"], ["Netwater", f"{nl(i.T_E201_uit, 0)} → {nl(i.T_net_aanvoer, 0)} °C"],
                                                ["Condenseren bij", f"{nl(i.T_net_aanvoer + i.dT_min, 1)} °C"]]),
        led(820, 790, "on" if wp_aan and not stil else "off"), t(832, 794, "WP-201" + ("" if wp_aan else " uit"), "lbl", "start"),
        g("AK", f'<rect x="30" y="622" width="160" height="52" rx="4" class="eq"/>',
          rotor(70, 648, 14, 0 if (net_aan or stil) else 1.0), rotor(112, 648, 14, 0 if (net_aan or stil) else 1.0),
          f'<circle cx="70" cy="648" r="16" fill="none" stroke="{C["muted"]}"/><circle cx="112" cy="648" r="16" fill="none" stroke="{C["muted"]}"/>',
          t(110, 612, "Adiabatische koelers"), led(170, 648, "off" if (net_aan or stil) else "warn"),
          titel="Adiabatische koelers ITM (back-up)", rows=[["Stand", "stand-by" if net_aan else "in bedrijf"],
                                                            ["Warmte naar buiten", f"{nl(r['Q_adiabatisch'], 0)} kW"]]),
        g("AC", t(185, 34, "AC · E1"), f'<path d="M 185 40 V 170" class="st" stroke="{C["on"] if not stil else C["off"]}" stroke-width="2"/>',
          titel="Elektrische aansluiting (MV, windpark)", rows=[["Stroom ITM (" + eh + ")", f"{nl(r['P_AC_EOL'] * f / 1000, 2)} MW"],
                                                              ["Units in bedrijf", f"{k} van {N_MAX}"]]),
        t(1196, 226, "H₂-backbone", anchor="start"), t(766, 376, "O₂ naar RWZI", anchor="start"),
        t(912, 830, "Warmtenet", anchor="start"),
    ]
    if not stil:
        # kerngetallen aan de grenzen van de installatie: altijd zichtbaar
        E += [
            sub(1196, 244, f"{nl(r['m_backbone'] * f, 0)} kg/h", "start", True),
            sub(766, 394, f"{nl(r['m_gas'] * f, 0)} kg/h", "start", True),
            sub(912, 846, f"{nl(r['Q_net'] / 1000, 1)} MW · {nl(r['T_aanvoer'], 0)} °C" if net_aan else "geen afname", "start", True),
            sub(192, 56, f"{nl(r['P_AC_EOL'] * f / 1000, 1)} MW", "start", True),
        ]
    else:
        E += [f'<rect x="300" y="470" width="520" height="56" rx="8" fill="{C["panel"]}" stroke="{C["err"]}" stroke-width="2"/>',
              t(560, 496, "Installatie staat stil", "groot"), t(560, 515, "onvoldoende vermogen of geen units beschikbaar", "sub")]

    # statusbord (compact; details in de popup)
    tegels = []
    for j in range(N_MAX):
        ld = loads[j]
        if not BESCHIKBAAR[j]:
            kl, lab = C["warn"], "onderh."
        elif ld > 0:
            kl, lab = (C["on"] if ld > 0.999 else C["warn"]), f"{nl(ld * 100, 0)}%"
        else:
            kl, lab = C["off"], "stand-by"
        tegels.append(f'<div class="tegel{" aan" if ld > 0 else ""}" style="--k:{kl}" data-tip="ITM{j + 1}"><div class="th"><span class="dot"></span>#{j + 1}'
                      f'<b>{lab}</b></div><div class="bar"><i style="width:{ld * 100:.0f}%"></i></div></div>')

    def chip(naam, toestand, tip):
        return f'<span class="chip{" on" if toestand == "on" else ""}" style="--k:{C[toestand]}" data-tip="{tip}"><span class="dot"></span>{naam}</span>'

    chips = "".join([
        chip(f"K-101 ×{k}", "off" if stil else ("warn" if recyc else "on"), "K101"),
        chip(f"K-102 ×{k}", "off" if stil else "on", "K102"),
        chip(f"P-101 ×{k}", "off" if stil else "on", "P101"),
        chip("FV-101 " + ("open" if recyc else "dicht"), "warn" if recyc else "off", "FV101"),
        chip("Warmtenet", "off" if (stil or not net_aan) else "on", "E201"),
        chip("WP-201", "off" if (stil or not wp_aan) else "on", "K201"),
        chip("Koelers", "warn" if (not net_aan and not stil) else "off", "AK"),
    ])
    css = f"""
    * {{ box-sizing:border-box }}
    body {{ margin:0; background:{C['bg']}; color:{C['ink']}; font-family: "Source Sans Pro", system-ui, sans-serif }}
    .bord {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px 14px; margin-bottom:4px }}
    .kop {{ font-size:14px; white-space:nowrap }} .kop b {{ font-size:16px }}
    .klok {{ font: 600 13px ui-monospace, Menlo, monospace; padding:2px 8px; border-radius:6px; background:{C['soft']}; border:1px solid {C['line']}; margin-left:auto; white-space:nowrap }}
    .tegels {{ display:grid; grid-template-columns:repeat(8, minmax(70px,1fr)); gap:5px; flex:1 1 560px }}
    .tegel {{ border:1px solid {C['line']}; border-radius:7px; padding:4px 7px; background:{C['panel']}; min-width:0; cursor:default }}
    .tegel.aan {{ border-color: var(--k) }}
    .th {{ display:flex; align-items:center; gap:5px; font-size:12px; font-weight:600 }}
    .th b {{ margin-left:auto; font: 500 11px ui-monospace, Menlo, monospace; color:{C['muted']}; white-space:nowrap }}
    .dot {{ width:8px; height:8px; border-radius:50%; background:var(--k); flex:none }}
    .tegel.aan .dot, .chip.on .dot {{ animation: puls 1.6s ease-in-out infinite }}
    @keyframes puls {{ 0%,100% {{ box-shadow:0 0 0 0 var(--k) }} 50% {{ box-shadow:0 0 0 4px transparent }} }}
    .bar {{ height:4px; background:{C['soft']}; border-radius:2px; margin-top:4px; overflow:hidden }}
    .bar i {{ display:block; height:100%; background:var(--k) }}
    .chips {{ display:flex; flex-wrap:wrap; gap:5px; width:100% }}
    .chip {{ display:inline-flex; align-items:center; gap:5px; font-size:11.5px; padding:2px 8px; border-radius:99px; border:1px solid {C['line']}; background:{C['panel']}; cursor:default }}
    .wrap {{ overflow-x:auto }}
    svg {{ width:100%; min-width:960px; height:auto; display:block }}
    .st {{ fill:none; stroke-linejoin:round; stroke-linecap:round; pointer-events:none }}
    .raak {{ fill:none; stroke:transparent; stroke-width:14; pointer-events:stroke; cursor:help }}
    .tip {{ cursor:help }}
    .tip:hover .eq {{ stroke:{C['h2']}; stroke-width:2.6 }}
    .eq {{ fill:{C['panel']}; stroke:{C['ink']}; stroke-width:1.6 }}
    text {{ fill:{C['ink']} }}
    .lbl {{ font: 600 13px "Arial Narrow", system-ui, sans-serif; letter-spacing:.02em; pointer-events:none }}
    .groot {{ font: 700 18px system-ui, sans-serif }}
    .mod {{ font: 600 10.5px ui-monospace, Menlo, monospace; pointer-events:none }}
    .badge {{ font: 700 10px ui-monospace, Menlo, monospace; pointer-events:none }}
    .muted {{ fill:{C['muted']} }}
    .sub {{ font: 11.5px ui-monospace, Menlo, monospace; fill:{C['muted']}; pointer-events:none }}
    .v {{ font: 11px ui-monospace, Menlo, monospace }}
    .id {{ font-weight:700 }}
    #popup {{ position:fixed; z-index:9; pointer-events:none; background:{C['panel']}; color:{C['ink']}; border:1px solid {C['line']};
              border-radius:8px; padding:8px 10px; font-size:12.5px; box-shadow:0 6px 20px rgba(0,0,0,.18); min-width:200px; max-width:320px; display:none }}
    #popup h4 {{ margin:0 0 6px; font-size:13px }}
    #popup table {{ border-collapse:collapse; width:100% }}
    #popup td {{ padding:2px 0; vertical-align:top }}
    #popup td+td {{ text-align:right; padding-left:12px; font-family: ui-monospace, Menlo, monospace; font-size:12px; white-space:nowrap }}
    .hint {{ font-size:11px; color:{C['muted']} }}
    @media (prefers-reduced-motion: reduce) {{ .dot {{ animation:none !important }} }}
    """
    js = """
    const TIPS = __TIPS__;
    const pop = document.getElementById('popup');
    const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    function toon(el, x, y) {
      const d = TIPS[el.dataset.tip]; if (!d) return;
      pop.innerHTML = '<h4>' + esc(d.t) + '</h4><table>' + d.r.filter(r => r[0]).map(r => '<tr><td>' + esc(r[0]) + '</td><td>' + esc(r[1]) + '</td></tr>').join('') + '</table>';
      pop.style.display = 'block'; plaats(x, y);
    }
    function plaats(x, y) {
      const w = pop.offsetWidth, h = pop.offsetHeight;
      pop.style.left = Math.min(x + 14, innerWidth - w - 6) + 'px';
      pop.style.top = (y + h + 20 > innerHeight ? y - h - 12 : y + 14) + 'px';
    }
    document.querySelectorAll('[data-tip]').forEach(el => {
      el.addEventListener('mouseenter', e => toon(el, e.clientX, e.clientY));
      el.addEventListener('mousemove', e => plaats(e.clientX, e.clientY));
      el.addEventListener('mouseleave', () => pop.style.display = 'none');
      el.addEventListener('click', e => toon(el, e.clientX, e.clientY));
    });
    """.replace("__TIPS__", _json.dumps(TIPS, ensure_ascii=False).replace("</", "<\\/"))
    kop = f'<span class="kop"><b>{k}/{N_MAX} units in bedrijf</b></span>'
    bord = (f'<div class="bord">{kop}<div class="tegels">{"".join(tegels)}</div><span class="klok">{_h.escape(klok)}</span>'
            f'<div class="chips">{chips}<span class="hint">· beweeg over een apparaat, stroom of tegel voor details</span></div></div>')
    svg = (f'<div class="wrap"><svg viewBox="-62 0 1362 860" role="img" aria-label="Geanimeerd procesflowschema">'
           + "".join(lijnen) + "".join(raak) + "".join(E) + "".join(deeltjes) + "".join(tags) + "</svg></div>")
    return f"<style>{css}</style>{bord}{svg}<div id=\"popup\"></div><script>{js}</script>"


# ------------------------------------------------------------------ kop
st.title("8 × ITM Neptune V · procesimulator")
st.caption(f"Live massa- en energiebalans van het PFD met CoolProp {CP.get_global_param_string('version')}. "
           "Lampje groen = in bedrijf, oranje = deellast of back-up, grijs = uit.")

spelen = st.session_state["modus"] == "Dagprofiel wind" and st.session_state["spelen"]
interval = SNELHEID[st.session_state["snelheid"]] if spelen else None


def kpis(r, k):
    wc = (r["W_K101"] + r["W_K102"] + r["W_P101"]) * k
    return {
        "H₂ naar backbone": (r["m_backbone"] * k, "kg/h", 0),
        "Stroom ITM": (r["P_AC_EOL"] * k / 1000, "MW", 2),
        "Compressoren + pomp": (wc, "kW", 0),
        "Naar warmtenet": (r["Q_net"] / 1000, "MW", 2),
        "COP WP-201": (r["COP"], "", 2),
        "Rendement HHV": (100 * r["i"].m_H2 * 141800 / 3600 * k / (r["P_AC_EOL"] * k + wc), "%", 1),
    }


@st.fragment(run_every=interval)
def live():
    # klok verder zetten als de timer deze run startte
    if spelen and time.time() - st.session_state["_laatste_tik"] >= interval * 0.9:
        if st.session_state["_laatste_tik"] > 0:
            st.session_state["uur"] = (st.session_state["uur"] + 1) % 24
        st.session_state["_laatste_tik"] = time.time()
    d, loads, k, last, wind = bedrijfspunt()
    stil = k == 0
    if stil:
        d = dict(PROCES, n_units=1, belasting=st.session_state["min_unit"])
    try:
        rx, rc = bereken(d)
    except Exception as exc:
        st.error(f"CoolProp kan dit punt niet doorrekenen: {exc}. Zet de laatste wijziging terug of kies een ander koudemiddel.")
        return
    mul = (k if k else 1) if weergave == "Totaal" else 1

    if st.session_state["modus"] == "Dagprofiel wind":
        h = st.session_state["uur"]
        klok = f"{h:02d}:00 · wind {nl(wind * 100, 0)} % · last {nl(last, 0)} %"
    else:
        klok = f"handmatig · last {nl(last, 0)} %"

    cols = st.columns(6)
    if stil:
        for col, naam in zip(cols, ["H₂ naar backbone", "Stroom ITM", "Compressoren + pomp", "Naar warmtenet", "COP WP-201", "Rendement HHV"]):
            col.metric(naam, "0")
    else:
        kc, kx = kpis(rc, k), kpis(rx, k)
        for col, (naam, (v, u, dd)) in zip(cols, kc.items()):
            col.metric(naam, f"{nl(v, dd)} {u}", help=f"Rekenblad (Çengel, ideaal gas): {nl(kx[naam][0], dd)} {u}")

    html = live_html(rc, loads, k, mul, is_donker(), stil, klok, st.session_state["alles"])
    if hasattr(st, "iframe"):
        st.iframe(html, height=820)
    else:  # oudere Streamlit-versies
        import streamlit.components.v1 as components
        components.html(html, height=820)

    if st.session_state["modus"] == "Dagprofiel wind":
        uren = list(range(24))
        lasten = [last_voor_uur(h) for h in uren]
        aan = [inzet(L)[1] for L in lasten]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=uren, y=aan, name="units aan", marker_color=["#1fa64a" if h == st.session_state["uur"] else "rgba(31,166,74,.35)" for h in uren],
                             yaxis="y2", hovertemplate="%{x}:00 · %{y} units<extra></extra>"))
        fig.add_trace(go.Scatter(x=uren, y=[100 * w for w in windprofiel(st.session_state["profiel"])], name="wind beschikbaar [%]",
                                 line=dict(color="#5f86bd", width=2, dash="dot")))
        fig.add_trace(go.Scatter(x=uren, y=lasten, name="ITM-last [%]", line=dict(color="#d27a1d", width=3), line_shape="hv"))
        fig.add_vline(x=st.session_state["uur"], line_color="#c8461b", line_width=2)
        fig.update_layout(height=230, margin=dict(l=10, r=10, t=10, b=30), legend=dict(orientation="h", y=1.15),
                          yaxis=dict(title="%", range=[0, 105]), xaxis=dict(dtick=2, title="uur"),
                          yaxis2=dict(overlaying="y", side="right", range=[0, N_MAX * 2.2], dtick=2, showgrid=False, title="units"))
        st.plotly_chart(fig, width="stretch", key="dagprofiel")

    with st.expander("Controles en waarschuwingen", expanded=False):
        if stil:
            st.info("Geen units in bedrijf.")
        else:
            for soort, tekst in meldingen(rc):
                {"ok": st.success, "let op": st.warning, "fout": st.error}[soort](tekst, icon={"ok": "✅", "let op": "⚠️", "fout": "⛔"}[soort])


live()

# ------------------------------------------------------------------ analyses (bij het huidige bedrijfspunt)
invoer, LOADS, K, LAST, _ = bedrijfspunt()
if K == 0:
    st.info("De installatie staat stil op dit moment. Kies een hogere last of een ander uur om de analyses te zien.")
    st.stop()
try:
    RX, RC = bereken(invoer)
except Exception:
    st.stop()
R = RC
i = R["i"]
n = i.n_units
mul = n if weergave == "Totaal" else 1
eenheid = f"{n} units" if mul > 1 else "per unit"
st.divider()
if spelen:
    st.caption("Tijdens het afspelen tonen de analyses hieronder het uur waarop je het laatst iets aanpaste. Pauzeer om ze bij te werken.")


# ------------------------------------------------------------------ apparaatdetails
def details(r, naam, f):
    i = r["i"]
    u = f" ({eenheid})"
    cy = r.get("cyclus") or {}
    D = {
        "ITM-units": [("Units in bedrijf", f"{n} van {N_MAX}"), ("Last per unit", f"{nl(max(LOADS) * 100, 0)} %"),
                      ("H₂-productie" + u, f"{nl(i.m_H2 * f, 0)} kg/h"),
                      ("Stroom EOL" + u, f"{nl(r['P_AC_EOL'] * f, 0)} kW"), ("Stroom BOL" + u, f"{nl(r['P_AC_BOL'] * f, 0)} kW"),
                      ("Reject heat EOL" + u, f"{nl(i.Q_ITM_EOL * f, 0)} kW"), ("Dauwpunt O₂-stroom", f"{nl(r['T_dauw'], 1)} °C")],
        "V-101 lagedrukbuffer": [("Druk", f"{nl(i.P_V101_min, 1)}–{nl(i.P_V101_max, 1)} barg"), ("Opslagtijd", f"{nl(i.t_V101 * 60, 0)} min"),
                                 ("Volume" + u, f"{nl(r['V_V101'] * f, 1)} m³")],
        "K-101 H₂-compressor": [("Drukverhouding", nl((i.P_K101_uit + 1.01325) / (i.P_V101_min + 1.01325), 2)),
                                ("T uit compressor", f"{nl(r['T_uit_K101'], 1)} °C"), ("Vermogen E3" + u, f"{nl(r['W_K101'] * f, 1)} kW"),
                                ("Isentroop minimum" + u, f"{nl(r['W_K101_s'] * f, 1)} kW"), ("Pakketkoeler" + u, f"{nl(r['Q_pak_K101'] * f, 1)} kW"),
                                ("Debiet S5" + u, f"{nl(r['m_S5'] * f, 1)} kg/h"), ("waarvan recycle S9", f"{nl(r['m_S9'] * f, 1)} kg/h")],
        "E-102 warmteterugwinning": [("H₂", f"{nl(r['T_S6'], 0)} → {nl(i.T_E102_uit, 0)} °C"), ("Warmte" + u, f"{nl(-r['Q_E102'] * f, 1)} kW"),
                                     ("Warmtenet-zijstroom" + u, f"{nl(r['m_ww_E102'] * f, 0)} kg/h")],
        "E-103 eindkoeler": [("H₂", f"{nl(i.T_E102_uit, 0)} → {nl(i.T_E103_uit, 0)} °C"), ("Warmte" + u, f"{nl(-r['Q_E103'] * f, 1)} kW"),
                             ("Koelwater" + u, f"{nl(r['m_kw_E103'] * f, 0)} kg/h")],
        "V-102 hogedrukbuffer": [("Druk", f"{nl(i.P_backbone, 1)}–{nl(i.P_K101_uit, 1)} barg"), ("Opslagtijd", f"{nl(i.t_V102, 0)} s"),
                                 ("Volume" + u, f"{nl(r['V_V102'] * f, 2)} m³")] + ([("Z bij max. druk", nl(r["Z_V102_max"], 3))] if "Z_V102_max" in r else []),
        "E-101 voorkoeler": [("O₂-stroom", f"{nl(i.T_O2_uit, 0)} → {nl(i.T_KO, 0)} °C"), ("Warmte" + u, f"{nl(-r['Q_E101'] * f, 1)} kW"),
                             ("Koelwater" + u, f"{nl(r['m_kw_E101'] * f, 0)} kg/h"), ("Condensaat" + u, f"{nl(r['m_cond'] * f, 1)} kg/h")],
        "V-103 KO-drum": [("Condensaat S15" + u, f"{nl(r['m_cond'] * f, 1)} kg/h"), ("Damp mee S17" + u, f"{nl(r['m_v'] * f, 1)} kg/h"),
                          ("Damp in gas", f"{nl(r['m_v'] / r['m_gas'] * 100, 2)} %")],
        "K-102 O₂-compressor": [("Drukverhouding", nl((i.P_RWZI + 1.01325) / (i.P_O2_uit + 1.01325), 2)), ("T uit compressor", f"{nl(r['T_uit_K102'], 1)} °C"),
                                ("Vermogen E4" + u, f"{nl(r['W_K102'] * f, 1)} kW"), ("Pakketkoeler" + u, f"{nl(r['Q_pak_K102'] * f, 1)} kW"),
                                ("Warmte mee naar RWZI" + u, f"{nl(r['Q_O2_RWZI'] * f, 1)} kW")]
                               + ([("Dauwpunt S18", f"{nl(r['T_dauw_S18'], 1)} °C")] if "T_dauw_S18" in r else []),
        "P-101 condensaatpomp": [("Debiet" + u, f"{nl(r['m_cond'] * f, 1)} kg/h"), ("Vermogen E5" + u, f"{nl(r['W_P101'] * f, 3)} kW"),
                                 ("Mengtemperatuur S2", f"{nl(r['T_mix'], 2)} °C")],
        "E-201 directe voorverwarming": [("Warmte Q6", f"{nl(r['Q_E201'], 0)} kW"), ("Netwater", f"{nl(i.T_net_retour, 0)} → {nl(i.T_E201_uit, 0)} °C"),
                                         ("Koelcircuit", f"{nl(i.T_kc_uit, 0)} → {nl(r['T_kc_tussen'], 1)} °C"),
                                         ("ΔT warme kant", f"{nl(i.T_kc_uit - i.T_E201_uit, 1)} K"), ("ΔT koude kant", f"{nl(r['T_kc_tussen'] - i.T_net_retour, 1)} K")],
        "WP-201 warmtepomp": [("In bedrijf", "ja" if (i.wp_aan and i.net_aan) else "nee"), ("Verdamper Q7", f"{nl(r['Q_L'], 0)} kW"),
                              ("Condensor Q8", f"{nl(r['Q_H'], 0)} kW"), ("K-201 E6", f"{nl(r['W_K201'], 0)} kW"), ("COP", nl(r["COP"], 2)),
                              ("COP Carnot", nl(r["COP_carnot"], 2))]
                             + ([("Druk", f"{nl(cy['P_evap_bar'], 1)} → {nl(cy['P_cond_bar'], 1)} bar"), ("Perstemperatuur", f"{nl(cy['T_pers'], 1)} °C")] if cy else []),
    }
    return D[naam]


# ------------------------------------------------------------------ tabs
tab_app, tab_bal, tab_wp, tab_h2, tab_gev, tab_cmp, tab_str = st.tabs(
    ["Apparaten", "Balansen", "Warmtepomp", "H₂-compressie", "Gevoeligheid", "Rekenblad ↔ CoolProp", "Stroomtabel"])

with tab_app:
    c1, c2 = st.columns([1, 2])
    with c1:
        app = st.selectbox("Apparaat", ["K-101 H₂-compressor", "ITM-units", "V-101 lagedrukbuffer", "E-102 warmteterugwinning",
                                        "E-103 eindkoeler", "V-102 hogedrukbuffer", "E-101 voorkoeler", "V-103 KO-drum",
                                        "K-102 O₂-compressor", "P-101 condensaatpomp", "E-201 directe voorverwarming", "WP-201 warmtepomp"])
    with c2:
        st.dataframe(pd.DataFrame(details(R, app, mul), columns=["Grootheid", "CoolProp"]), hide_index=True, width="stretch")


with tab_bal:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader(f"Warmteoverzicht ({n} units in bedrijf)")
        items = [("Reject heat ITM", i.Q_ITM_EOL * n, "#7b4bb2"), ("E-101 voorkoeler", -R["Q_E101"] * n, "#5f86bd"),
                 ("E-102 terugwinning", -R["Q_E102"] * n, "#d27a1d"), ("K-101 pakketkoeler", R["Q_pak_K101"] * n, "#1d6fb8"),
                 ("E-103 eindkoeler", -R["Q_E103"] * n, "#5f86bd"), ("K-102 pakketkoeler", R["Q_pak_K102"] * n, "#3a8a2c"),
                 ("Warmte in O₂-gas", R["Q_O2_RWZI"] * n, "#3a8a2c")]
        fig = go.Figure(go.Bar(y=[x[0] for x in items][::-1], x=[x[1] for x in items][::-1], orientation="h",
                               marker_color=[x[2] for x in items][::-1], text=[f"{nl(x[1], 0)} kW" for x in items][::-1],
                               textposition="outside", cliponaxis=False))
        fig.update_layout(xaxis_type="log", xaxis_title="kW (logaritmisch)", height=340, margin=dict(l=10, r=60, t=10, b=40))
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Waar komt de warmte voor het net vandaan?")
        parts = [("E-201 direct uit ITM", R["Q_E201"], "#7b4bb2"), ("ITM via verdamper E-202", R["Q_L"], "#b49ad6"),
                 ("Stroom K-201", R["W_K201"], "#16202a"), ("Zijstroom E-102", R["Q_E102_tot"], "#d27a1d")]
        fig = go.Figure(go.Pie(labels=[p[0] for p in parts], values=[max(p[1], 0) for p in parts], hole=.55,
                               marker_colors=[p[2] for p in parts], sort=False, textinfo="percent"))
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10),
                          annotations=[dict(text=f"{nl(R['Q_net'] / 1000, 2)} MW", showarrow=False, font_size=18)])
        st.plotly_chart(fig, width="stretch")

    st.subheader(f"Energiebalans per unit (EOL) · CoolProp")
    rows = [("In", "AC naar ITM (E1)", R["P_AC_EOL"]), ("In", "K-101 (E3)", R["W_K101"]), ("In", "K-102 (E4)", R["W_K102"]),
            ("Uit", "Chemische energie H₂ (HHV)", i.m_H2 * 141800 / 3600), ("Uit", "Reject heat ITM", i.Q_ITM_EOL),
            ("Uit", "Voorkoeler E-101", -R["Q_E101"]), ("Uit", "Pakketkoeler K-101", R["Q_pak_K101"]),
            ("Uit", "Terugwinning E-102", -R["Q_E102"]), ("Uit", "Eindkoeler E-103", -R["Q_E103"]),
            ("Uit", "Pakketkoeler K-102", R["Q_pak_K102"]), ("Uit", "Warmte in O₂ naar RWZI", R["Q_O2_RWZI"]),
            ("", "In − uit", R["chk_E"])]
    st.dataframe(pd.DataFrame(rows, columns=["", "Post", "kW"]).style.format({"kW": lambda v: nl(v, 2)}),
                 hide_index=True, width="stretch")

with tab_wp:
    cy = RC["cyclus"]
    f = cy["fluid"]
    c1, c2 = st.columns([3, 2])
    with c1:
        Tc = CP.PropsSI("Tcrit", f)
        Tmin = max(CP.PropsSI("Tmin", f), 230)
        Ts = [Tmin + (Tc - 0.3 - Tmin) * k / 120 for k in range(121)]
        pl = [CP.PropsSI("P", "T", T, "Q", 0, f) / 1e5 for T in Ts]
        hl = [CP.PropsSI("H", "T", T, "Q", 0, f) / 1e3 for T in Ts]
        hv = [CP.PropsSI("H", "T", T, "Q", 1, f) / 1e3 for T in Ts]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hl + hv[::-1], y=pl + pl[::-1], mode="lines", line=dict(color="#8896a5", width=1.5), name="verzadigingslijn"))
        Pe, Pc = cy["P_evap_bar"], cy["P_cond_bar"]
        h2s = CP.PropsSI("H", "P", Pc * 1e5, "S", CP.PropsSI("S", "T", cy["T_evap"] + T0, "Q", 1, f), f) / 1e3
        px = [cy["h1"], cy["h2"], cy["h3"], cy["h3"], cy["h1"]]
        py = [Pe, Pc, Pc, Pe, Pe]
        fig.add_trace(go.Scatter(x=px, y=py, mode="lines+markers+text", fill="toself", fillcolor="rgba(19,138,128,.12)",
                                 line=dict(color="#138a80", width=3), text=["1", "2", "3", "4", ""], textposition="top center", name="cyclus"))
        fig.add_trace(go.Scatter(x=[cy["h1"], h2s], y=[Pe, Pc], mode="lines", line=dict(color="#138a80", dash="dot"), name="isentroop"))
        fig.update_layout(yaxis_type="log", xaxis_title="h (kJ/kg)", yaxis_title="p (bar)", height=440,
                          margin=dict(l=10, r=10, t=30, b=40), title=f"log p–h · {f}", legend=dict(orientation="h", y=-0.2))
        fig.update_yaxes(range=[math.log10(max(Pe / 4, min(pl))), math.log10(max(pl) * 1.2)])
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader("Toestanden")
        st.dataframe(pd.DataFrame([
            ("1 uit verdamper", nl(cy["T_evap"], 1), nl(Pe, 2), nl(cy["h1"], 1)),
            ("2 uit K-201", nl(cy["T_pers"], 1), nl(Pc, 2), nl(cy["h2"], 1)),
            ("3 uit condensor", nl(cy["T_cond"], 1), nl(Pc, 2), nl(cy["h3"], 1)),
            ("4 na TV-201", nl(cy["T_evap"], 1), nl(Pe, 2), nl(cy["h3"], 1)),
        ], columns=["Punt", "T °C", "p bar", "h kJ/kg"]), hide_index=True, width="stretch")
        st.metric("COP cyclus (CoolProp)", nl(cy["COP"], 2))
        st.metric("COP rekenblad (η_II · Carnot)", nl(RX["COP"], 2))
        st.metric("COP Carnot", nl(cy["COP_carnot"], 2))
        st.caption(f"Dampfractie na smoorventiel: {nl(cy['x4'], 3)}. Cyclus zonder oververhitting of onderkoeling.")

with tab_h2:
    H = "Hydrogen"
    P1 = (i.P_V101_min * 100 + 101.325) * 1e3
    P2 = (i.P_K101_uit * 100 + 101.325) * 1e3
    Tr = [270 + k * 2.5 for k in range(int((max(RC["T_uit_K101"] + T0 + 30, 480) - 270) / 2.5))]
    fig = go.Figure()
    for P, naam, kl in ((P1, f"{nl(i.P_V101_min, 1)} barg (zuig)", "#5f86bd"), (P2, f"{nl(i.P_K101_uit, 1)} barg (pers)", "#1d6fb8")):
        fig.add_trace(go.Scatter(x=[CP.PropsSI("S", "T", T, "P", P, H) / 1e3 for T in Tr], y=[T - T0 for T in Tr],
                                 mode="lines", line=dict(color=kl, width=1.5), name=f"isobaar {naam}"))
    s1 = CP.PropsSI("S", "T", i.T_H2 + T0, "P", P1, H) / 1e3
    T2s = CP.PropsSI("T", "S", s1 * 1e3, "P", P2, H) - T0
    s2 = CP.PropsSI("S", "T", RC["T_uit_K101"] + T0, "P", P2, H) / 1e3
    s6 = CP.PropsSI("S", "T", RC["T_S6"] + T0, "P", P2, H) / 1e3
    s7 = CP.PropsSI("S", "T", i.T_E102_uit + T0, "P", P2, H) / 1e3
    s8 = CP.PropsSI("S", "T", i.T_E103_uit + T0, "P", P2, H) / 1e3
    fig.add_trace(go.Scatter(x=[s1, s1], y=[i.T_H2, T2s], mode="lines", line=dict(color="#8896a5", dash="dot"), name="isentroop"))
    fig.add_trace(go.Scatter(x=[s1, s2, s6, s7, s8], y=[i.T_H2, RC["T_uit_K101"], RC["T_S6"], i.T_E102_uit, i.T_E103_uit],
                             mode="lines+markers+text", text=["S5", "uit K-101", "S6", "S7", "S8"], textposition="middle right",
                             line=dict(color="#c8461b", width=3), name="werkelijk"))
    fig.update_layout(xaxis_title="s (kJ/kg·K)", yaxis_title="T (°C)", height=460, margin=dict(l=10, r=10, t=30, b=40),
                      title="T–s van de H₂-lijn: compressie K-101 en koeling via pakketkoeler, E-102 en E-103",
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch")
    c = st.columns(4)
    c[0].metric("T isentroop", f"{nl(T2s, 1)} °C")
    c[1].metric("T werkelijk", f"{nl(RC['T_uit_K101'], 1)} °C")
    c[2].metric(f"Vermogen E3 ({eenheid})", f"{nl(RC['W_K101'] * mul, 1)} kW")
    c[3].metric("Z bij persdruk", nl(CP.PropsSI("Z", "T", i.T_H2 + T0, "P", P2, H), 4))

with tab_gev:
    st.write(f"Varieer één invoergrootheid over het hele schuifbereik; alle andere invoer blijft zoals nu ({n} units in bedrijf).")
    c1, c2, c3 = st.columns(3)
    SWEEP = {"belasting": ("belasting", "Last per unit in bedrijf", 10.0, 100.0, 1.0, "%", 0, None)} | ALLE
    par = c1.selectbox("Invoer", list(SWEEP), format_func=lambda k: f"{SWEEP[k][1]} [{SWEEP[k][5]}]", index=0)
    UIT = {"Ẇ K-101 [kW]": lambda r: r["W_K101"] * n, "T uit K-101 [°C]": lambda r: r["T_uit_K101"],
           "Ẇ K-102 [kW]": lambda r: r["W_K102"] * n, "Q E-101 [kW]": lambda r: -r["Q_E101"] * n,
           "Condensaat S15 [kg/h]": lambda r: r["m_cond"] * n, "COP WP-201 [–]": lambda r: r["COP"],
           "Ẇ K-201 [kW]": lambda r: r["W_K201"], "Naar warmtenet [kW]": lambda r: r["Q_net"],
           "Volume V-101 [m³]": lambda r: r["V_V101"] * n, "H₂ naar backbone [kg/h]": lambda r: r["m_backbone"] * n}
    uit = c2.selectbox("Uitkomst", list(UIT), index=0)
    npt = c3.slider("Aantal punten", 5, 40, 15)
    _, label, lo, hi, *_ = SWEEP[par]
    xs = [lo + (hi - lo) * k / (npt - 1) for k in range(npt)]
    yc, yx = [], []
    for x in xs:
        d = dict(invoer); d[par] = x
        try:
            ex, cp_ = bereken(d)
            yc.append(UIT[uit](cp_)); yx.append(UIT[uit](ex))
        except Exception:
            yc.append(None); yx.append(None)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=yc, mode="lines+markers", name="CoolProp", line=dict(color="#c8461b", width=3)))
    fig.add_trace(go.Scatter(x=xs, y=yx, mode="lines", name="Rekenblad", line=dict(color="#5f86bd", dash="dash")))
    fig.add_vline(x=invoer[par], line_dash="dot", line_color="#8896a5", annotation_text="huidig")
    fig.update_layout(xaxis_title=f"{label} [{SWEEP[par][5]}]", yaxis_title=uit, height=440, margin=dict(l=10, r=10, t=20, b=40))
    st.plotly_chart(fig, width="stretch")

with tab_cmp:
    def delta_kleur(v):
        a = min(abs(v) / 15, 1) * 0.55
        return f"background-color: rgba({'200,70,27' if v > 0 else '29,111,184'},{a:.2f})" if abs(v) >= 0.5 else ""

    CMP = [("T_dauw", "Dauwpunt O₂-stroom", "°C"), ("m_cond", "Condensaat S15", "kg/h"), ("Q_E101", "Q E-101", "kW"),
           ("T_uit_K102", "T uit K-102", "°C"), ("W_K102", "Ẇ K-102", "kW"), ("T_uit_K101", "T uit K-101", "°C"),
           ("W_K101", "Ẇ K-101", "kW"), ("Q_pak_K101", "Pakketkoeler K-101", "kW"), ("Q_E102", "Q E-102", "kW"),
           ("Q_E103", "Q E-103", "kW"), ("V_V101", "Volume V-101", "m³"), ("V_V102", "Volume V-102", "m³"),
           ("T_mix", "Mengtemperatuur S2", "°C"), ("P_AC_EOL", "Stroom ITM EOL", "kW"), ("COP", "COP warmtepomp", "–"),
           ("Q_E201", "E-201 (alle units)", "kW"), ("Q_H", "Condensor E-203 (alle units)", "kW"), ("W_K201", "Ẇ K-201", "kW"),
           ("Q_net", "Naar warmtenet (alle units)", "kW")]
    df = pd.DataFrame([(l, u, RX[k], RC[k], (RC[k] - RX[k]) / abs(RX[k]) * 100 if (RX[k] and math.isfinite(RX[k]) and math.isfinite(RC[k])) else 0.0) for k, l, u in CMP],
                      columns=["Grootheid (per unit tenzij vermeld)", "Eenheid", "Rekenblad", "CoolProp", "Δ %"])
    st.dataframe(df.style.format({"Rekenblad": lambda v: nl(v, 2), "CoolProp": lambda v: nl(v, 2), "Δ %": lambda v: f"{'+' if v >= 0 else ''}{nl(v, 1)}"})
                 .map(delta_kleur, subset=["Δ %"]),
                 hide_index=True, width="stretch", height=720)

with tab_str:
    model = st.radio("Model", ["CoolProp", "Rekenblad"], horizontal=True, key="str_model")
    r = RC if model == "CoolProp" else RX
    ii = r["i"]
    rows = [
        ("S1", "vers water → mengpunt", 0, 0, 0, r["m_vers"], ii.T_vers, ii.P_ITM_voed),
        ("S2", "mengpunt → ITM", 0, 0, 0, ii.m_voedwater, r["T_mix"], ii.P_ITM_voed),
        ("S3", "ITM → afvalwater", 0, 0, 0, ii.m_afvalwater, None, None),
        ("S4", "ITM → V-101", ii.m_H2, 0, 0, 0, ii.T_H2, ii.P_H2_ITM),
        ("S5", "V-101 → K-101", r["m_S5"], 0, 0, 0, ii.T_H2, ii.P_V101_min),
        ("S6", "K-101 → E-102", r["m_S5"], 0, 0, 0, r["T_S6"], ii.P_K101_uit),
        ("S7", "E-102 → E-103", r["m_S5"], 0, 0, 0, ii.T_E102_uit, ii.P_K101_uit),
        ("S8", "E-103 → kwaliteitscontrole", r["m_S5"], 0, 0, 0, ii.T_E103_uit, ii.P_K101_uit),
        ("S9", "recycle FV-101", r["m_S9"], 0, 0, 0, ii.T_E103_uit, None),
        ("S10", "blowoff", 0, 0, 0, 0, None, None),
        ("S11", "kwaliteitscontrole → V-102", r["m_backbone"], 0, 0, 0, ii.T_E103_uit, ii.P_backbone),
        ("S12", "PCV-101 → backbone", r["m_backbone"], 0, 0, 0, ii.T_E103_uit, ii.P_backbone),
        ("S13", "ITM → E-101", 0, r["m_O2"], r["m_H2O_in"], 0, ii.T_O2_uit, ii.P_O2_uit),
        ("S14", "E-101 → V-103", 0, r["m_O2"], r["m_v"], r["m_cond"], ii.T_KO, ii.P_O2_uit),
        ("S15", "V-103 → P-101", 0, 0, 0, r["m_cond"], ii.T_KO, ii.P_O2_uit),
        ("S16", "P-101 → mengpunt", 0, 0, 0, r["m_cond"], ii.T_KO, ii.P_ITM_voed),
        ("S17", "V-103 → K-102", 0, r["m_O2"], r["m_v"], 0, ii.T_KO, ii.P_O2_uit),
        ("S18", "K-102 → RWZI", 0, r["m_O2"], r["m_v"], 0, r["T_S18"], ii.P_RWZI),
    ]
    df = pd.DataFrame(rows, columns=["Nr", "Van → naar", "H₂", "O₂", "H₂O damp", "H₂O vl.", "T °C", "p barg"])
    for c in ["H₂", "O₂", "H₂O damp", "H₂O vl."]:
        df[c] = df[c] * mul
    df.insert(6, "Totaal kg/h", df[["H₂", "O₂", "H₂O damp", "H₂O vl."]].sum(axis=1))
    st.dataframe(df.style.format({c: (lambda v: nl(v, 1) if v else "") for c in ["H₂", "O₂", "H₂O damp", "H₂O vl."]}
                                 | {"Totaal kg/h": lambda v: nl(v, 1), "T °C": lambda v: "n.b." if pd.isna(v) else nl(v, 1),
                                    "p barg": lambda v: "–" if pd.isna(v) else nl(v, 1)}),
                 hide_index=True, width="stretch", height=680)
    st.caption(f"{model} · {eenheid} · {n} units op {nl(max(LOADS) * 100, 0)} %")
    st.download_button("Stroomtabel als CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name=f"stroomtabel_{model.lower()}.csv", mime="text/csv")

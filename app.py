"""Lokale Streamlit-app voor het interactieve ITM Neptune V-processchema."""

import math
from pathlib import Path
import random
import time
from dataclasses import asdict

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from itm_model import Invoer, KOUDEMIDDEL_INFO
from pfd import analyses
from pfd.bedrijfspunt import momentopname
from pfd.rekenstappen import TEMPERATUURINVOER
from pfd.schema import OPSTELLINGEN, schema

st.set_page_config(page_title="VisualPFD · ITM Neptune V", layout="wide")

BASIS = Invoer()
N_MAX = BASIS.n_units
PFD = components.declare_component("visualpfd", path=str(Path(__file__).parent / "pfd" / "frontend"))


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
        ("T_H2", "H₂ uit ITM", 5.0, 80.0, 0.5, "°C", 1, None),
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
    "Voedwater en koelwater": [
        ("T_vers", "Vers UPW", 5.0, 40.0, 0.5, "°C", 1, None),
        ("T_afvalwater", "Afvalwater", 5.0, 80.0, 1.0, "°C", 1, None),
        ("T_kw_in", "Koelwater aanvoer", 5.0, 40.0, 0.5, "°C", 1, None),
        ("T_kw_uit", "Koelwater retour", 10.0, 60.0, 0.5, "°C", 1, None),
    ],
    "ITM-circuit en warmteterugwinning": [
        ("T_kc_uit", "ITM-circuit uit ITM (datasheet)", 50.0, 60.0, 0.5, "°C", 1, "Gesloten circuit per unit, 62/38 water/CoolFlow DTX, 278.814 kg/h, 4,4 barg (EOL)."),
        ("T_kc_retour", "ITM-circuit terug naar ITM (datasheet)", 40.0, 52.0, 0.5, "°C", 1, None),
        ("dT_E201", "ΔT platenwisselaar E-201", 1.0, 6.0, 0.5, "K", 1, "Temperatuurverlies ITM-circuit → koelwatercircuit."),
        ("T_net_retour", "Warmtenet retour *", 25.0, 50.0, 1.0, "°C", 0, None),
        ("T_E204_uit", "Warmtenet na E-204 (direct)", 30.0, 55.0, 0.5, "°C", 1, None),
        ("T_net_aanvoer", "Warmtenet aanvoer *", 55.0, 90.0, 1.0, "°C", 0, None),
        ("dT_min", "ΔT min. wisselaar", 2.0, 10.0, 0.5, "K", 1, None),
        ("eta_K201", "η isentroop K-201 (CoolProp)", 0.5, 0.85, 0.01, "–", 2, None),
        ("eta_II", "η II warmtepompen (rekenblad)", 0.3, 0.7, 0.01, "–", 2, None),
    ],
    "Industrie (WP-202)": [
        ("Q_ind", "Warmtevraag industrie", 0.0, 30000.0, 100.0, "kW", 0, "Bij 0 kW staat WP-202 uit."),
        ("T_ind_aanvoer", "Aanvoer industrie", 70.0, 135.0, 1.0, "°C", 0, None),
        ("T_ind_retour", "Retour industrie", 50.0, 120.0, 1.0, "°C", 0, None),
        ("eta_K202", "η isentroop K-202 (CoolProp)", 0.5, 0.85, 0.01, "–", 2, None),
    ],
}


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

ALLE = {veld[0]: veld for groep in GROEPEN.values() for veld in groep}
VELDEN_WARMTE = {"T_net_retour", "T_E204_uit", "T_net_aanvoer", "eta_K201"}
KOUDEMIDDELEN = [k for k in KOUDEMIDDEL_INFO if k != "CarbonDioxide"]
SNELHEID = {"Traag": 3.0, "Normaal": 1.8, "Snel": 1.0}
BEDRIJF_STANDAARD = dict(
    modus="Handmatig", last=100.0, strategie="Bijschakelen", min_unit=20.0,
    profiel="Wisselvallige herfstdag", wind_ratio=1.2, spelen=False, snelheid="Normaal",
    **{f"u{j}": True for j in range(1, N_MAX + 1)},
)

S = st.session_state
S.setdefault("opstelling", "industrie")
S.setdefault("proces", asdict(BASIS))
S.setdefault("bedrijf", dict(maximale_afname=True, industrie_vraag=BASIS.Q_ind, warmtenet_vraag=BASIS.Q_ind))
S.setdefault("uur", 0)
S.setdefault("_laatste_tik", 0.0)
S.setdefault("geldige_pfd", {})
for sleutel, waarde in BEDRIJF_STANDAARD.items():
    S.setdefault(sleutel, waarde)


def reset():
    S.proces = asdict(BASIS)
    S.bedrijf = dict(maximale_afname=True, industrie_vraag=BASIS.Q_ind, warmtenet_vraag=BASIS.Q_ind)
    for k, v in BEDRIJF_STANDAARD.items():
        S[k] = v
    S.uur = 0
    S._laatste_tik = 0.0
    S.pop("temperatuurmelding", None)


def inzet(last_pct):
    vrij = [j for j in range(N_MAX) if S[f"u{j + 1}"]]
    gevraagde_units = min(last_pct / 100 * N_MAX, len(vrij))
    minimum = S.min_unit / 100
    loads = [0.0] * N_MAX
    if not vrij or gevraagde_units < minimum - 1e-9:
        return tuple(loads)
    k = math.ceil(gevraagde_units - 1e-9) if S.strategie == "Bijschakelen" else len(vrij)
    if gevraagde_units / k < minimum:
        k = max(1, int(gevraagde_units / minimum))
    for j in vrij[:k]:
        loads[j] = min(1.0, gevraagde_units / k)
    return tuple(loads)


def last_voor_uur(uur):
    return min(100.0, 100 * windprofiel(S.profiel)[uur % 24] * S.wind_ratio)


def bedrijfspunt(wijzigingen=None):
    opstelling = S.opstelling
    d = dict(S.proces)
    if wijzigingen:
        d.update(wijzigingen)
    if opstelling == "industrie":
        d.update(net_aan=False, wp_aan=False, h2_warmteterugwinning=False,
                 Q_ind=math.inf if S.bedrijf["maximale_afname"] else S.bedrijf["industrie_vraag"])
    else:
        d.update(h2_warmteterugwinning=True, Q_ind=S.bedrijf["warmtenet_vraag"])
    loads = inzet(S.last if S.modus == "Handmatig" else last_voor_uur(S.uur))
    d.update(n_units=sum(bool(load) for load in loads), belasting=max(loads) * 100)
    return d, loads


@st.cache_data(show_spinner=False, max_entries=128)
def doorrekening(invoer, opstelling, loads):
    return momentopname(Invoer(**invoer), opstelling, loads)


def wijzig_temperaturen(verzoek):
    """Valideer alle bewerkingen vóór de eerstvolgende weergave van de widgets."""
    velden = verzoek.get("waarden")
    veld = None
    try:
        if verzoek.get("opstelling") != S.opstelling or not isinstance(velden, dict) or not velden:
            raise ValueError("Open het apparaat in de actieve opstelling en pas de instellingen daar toe.")
        toegepast = {}
        for veld, invoer in velden.items():
            if veld not in TEMPERATUURINVOER or (veld in VELDEN_WARMTE and S.opstelling == "industrie"):
                raise ValueError("Die temperatuur is hier geen modelinstelling.")
            waarde = float(str(invoer).strip().replace(",", "."))
            _, naam, laag, hoog, *_ = ALLE[veld]
            if not math.isfinite(waarde) or not laag <= waarde <= hoog:
                raise ValueError(f"{naam} moet tussen {laag:g} en {hoog:g} °C liggen.")
            toegepast[veld] = waarde
        d, loads = bedrijfspunt(toegepast)
        doorrekening(d, S.opstelling, loads)
    except (TypeError, ValueError, ArithmeticError, RuntimeError) as exc:
        uitleg = str(exc)
        if uitleg.startswith("could not convert string"):
            uitleg = "Vul een temperatuur in °C in."
        S.temperatuurmelding = dict(id=verzoek["id"], ok=False, veld=veld, tekst=uitleg)
        return
    S.proces.update(toegepast)
    S.temperatuurmelding = dict(id=verzoek["id"], ok=True, tekst="Temperatuurinstellingen toegepast.")


verzoek = S.pop("_pfd_verzoek", None)
if verzoek:
    wijzig_temperaturen(verzoek)


def kopieer_naar(opslag, veld, widget):
    S[opslag][veld] = S[widget]


def bind(opslag, veld):
    sleutel = f"{opslag}.{veld}"
    if S.get(sleutel) != S[opslag][veld]:
        S[sleutel] = S[opslag][veld]
    return dict(key=sleutel, on_change=kopieer_naar, args=(opslag, veld, sleutel))


st.title("VisualPFD · ITM Neptune V")
st.radio("Opstelling", list(OPSTELLINGEN), format_func=OPSTELLINGEN.__getitem__, key="opstelling", horizontal=True)

with st.sidebar:
    st.header("Bedrijf")
    st.radio("Modus", ["Handmatig", "Dagprofiel wind"], key="modus", horizontal=True)
    if S.modus == "Handmatig":
        st.slider("Gevraagde installatielast [%]", 0.0, 100.0, step=1.0, key="last", format="%.0f",
                  help="100% betekent dat alle acht ITM-units op vollast kunnen draaien.")
    else:
        st.selectbox("Windprofiel", ["Wisselvallige herfstdag", "Storm met afschakeling", "Rustige zomerdag"], key="profiel")
        st.slider("Windpark / elektrolysevermogen", 0.5, 2.0, step=0.05, key="wind_ratio")
        c1, c2 = st.columns(2)
        c1.toggle("Afspelen", key="spelen")
        c2.selectbox("Tempo", list(SNELHEID), key="snelheid")
        st.slider("Ga naar uur", 0, 23, value=S.uur, key="uur_kies",
                  on_change=lambda: S.update(uur=int(S.uur_kies), _laatste_tik=time.time()))
    with st.expander("Inzet en beschikbaarheid"):
        st.radio("Inzet units", ["Bijschakelen", "Gelijk verdelen"], key="strategie", horizontal=True)
        st.slider("Minimale last per unit [%]", 5.0, 50.0, step=1.0, key="min_unit", format="%.0f")
        st.caption("Units beschikbaar voor productie")
        ucols = st.columns(4)
        for j in range(1, N_MAX + 1):
            ucols[(j - 1) % 4].checkbox(f"#{j}", key=f"u{j}")
        if S.opstelling == "warmtenet":
            st.toggle("Warmtenet neemt warmte af", **bind("proces", "net_aan"))
            st.toggle("WP-201 in bedrijf", **bind("proces", "wp_aan"))

    st.header("Procesinvoer")
    for naam, ctls in GROEPEN.items():
        with st.expander(naam, expanded=naam == "Industrie (WP-202)"):
            if naam == "Industrie (WP-202)":
                bedrijf = S.bedrijf
                industrie = S.opstelling == "industrie"
                if industrie:
                    st.toggle("Maximale afname", **bind("bedrijf", "maximale_afname"))
                if not industrie or not bedrijf["maximale_afname"]:
                    veld = "industrie_vraag" if industrie else "warmtenet_vraag"
                    st.number_input("Warmtevraag industrie [kW]", min_value=0.0, step=100.0, **bind("bedrijf", veld))
            for veld, label, lo, hi, step, unit, dec, hlp in ctls:
                if veld == "Q_ind" or (veld in VELDEN_WARMTE and S.opstelling == "industrie"):
                    continue
                st.slider(f"{label} [{unit}]", lo, hi, step=step, help=hlp, format=f"%.{dec}f", **bind("proces", veld))
            if naam.startswith("ITM-circuit") and S.opstelling == "warmtenet":
                st.selectbox("Koudemiddel WP-201", KOUDEMIDDELEN, format_func=lambda k: KOUDEMIDDEL_INFO[k][0],
                             **bind("proces", "koudemiddel"))
            if naam.startswith("Industrie"):
                st.selectbox("Koudemiddel WP-202", KOUDEMIDDELEN, format_func=lambda k: KOUDEMIDDEL_INFO[k][0],
                             **bind("proces", "koudemiddel2"))
    st.button("Terug naar basisinvoer", on_click=reset, width="stretch")


def basispunt(opstelling):
    i = asdict(BASIS)
    if opstelling == "industrie":
        i.update(net_aan=False, wp_aan=False, h2_warmteterugwinning=False, Q_ind=math.inf)
    loads = (1.0,) * N_MAX
    r, data = doorrekening(i, opstelling, loads)
    return i, loads, r, data


def toon_controles(r, invoer):
    if r is None:
        return
    i = r["i"]
    meldingen = []
    if abs(r["chk_p5"]) > 1e-3:
        meldingen.append("De warmteketen sluit niet op dit bedrijfspunt.")
    if i.T_KO > 40:
        meldingen.append("Condensaat naar ITM is warmer dan de datasheetgrens van 40 °C.")
    if i.T_E103_uit > 30:
        meldingen.append("H₂ naar backbone is warmer dan 30 °C.")
    if r["T_dauw_S18"] > r["T_S18"]:
        meldingen.append("De gastemperatuur naar RWZI ligt onder het dauwpunt van het mengsel.")
    if i.h2_warmteterugwinning and i.T_E102_uit < r["T_tw_r"] + i.dT_min - 1e-9:
        meldingen.append("Het temperatuurverschil voor H₂-warmteterugwinning is kleiner dan de ingestelde minimumwaarde.")
    if r["Q_E204"] > 0 and (r["T_tw_a"] - i.T_net_retour < i.dT_min or r["T_tw_tussen"] - r["T_E204"] < i.dT_min):
        meldingen.append("Bij E-204 is het temperatuurverschil kleiner dan de ingestelde minimumwaarde.")
    if math.isfinite(invoer["Q_ind"]) and r["ind_begrensd"]:
        meldingen.append(f"Beschikbaar bronvermogen begrenst de industrieafname op {analyses.nl(r['Q_ind'], 0)} kW.")
    for bericht in meldingen:
        st.warning(bericht)


def toon_windprofiel():
    uren = list(range(24))
    units = [sum(bool(load) for load in inzet(last_voor_uur(h))) for h in uren]
    fig = go.Figure()
    fig.add_bar(x=uren, y=units, name="Actieve units", yaxis="y2", marker_color="#48826d")
    fig.add_scatter(x=uren, y=[100 * w for w in windprofiel(S.profiel)], name="Wind beschikbaar [%]", mode="lines")
    fig.add_vline(x=S.uur, line_color="#a84c2c")
    fig.update_layout(height=230, margin=dict(l=10, r=10, t=10, b=30), legend=dict(orientation="h", y=1.15),
                      yaxis=dict(title="%", range=[0, 105]), yaxis2=dict(title="units", overlaying="y", side="right"),
                      xaxis=dict(dtick=2, title="Uur"))
    st.plotly_chart(fig, width="stretch", key="dagprofiel")


def toon_analyses(invoer, r, opstelling):
    with st.expander("Analyses"):
        keuze = st.selectbox("Analyse", ["Warmtepomp", "H₂-compressie", "Gevoeligheid", "Rekenblad ↔ CoolProp",
                                       "Stroomtabel rekenblad", "Leidingdimensionering"], index=None)
        if keuze is None:
            return
        if keuze == "Leidingdimensionering":
            analyses.leidingdimensionering(invoer, opstelling)
            return
        if r is None:
            st.info("Kies een bedrijfspunt met actieve units om deze analyse te bekijken.")
            return
        n = invoer["n_units"]
        schaal = st.radio("Getallen", ["Totaal", "Per unit"], horizontal=True) if keuze in ("H₂-compressie", "Stroomtabel rekenblad") else "Totaal"
        mul, eenheid = (n, f"{n} actieve units") if schaal == "Totaal" else (1, "per unit")
        if keuze == "Warmtepomp":
            analyses.warmtepomp(r, opstelling)
        elif keuze == "H₂-compressie":
            analyses.h2_compressie(r, mul, eenheid)
        elif keuze == "Gevoeligheid":
            analyses.gevoeligheid(invoer, n, ALLE)
        elif keuze == "Rekenblad ↔ CoolProp":
            analyses.vergelijking(invoer, r)
        else:
            analyses.stroomtabel_rekenblad(invoer, mul, eenheid)


interval = SNELHEID[S.snelheid] if S.modus == "Dagprofiel wind" and S.spelen else None


@st.fragment(run_every=interval)
def live():
    opstelling = S.opstelling
    if interval and time.time() - S._laatste_tik >= interval * 0.9:
        if S._laatste_tik:
            S.uur = (S.uur + 1) % 24
        S._laatste_tik = time.time()
    invoer, loads = bedrijfspunt()
    melding = ""
    try:
        r, data = doorrekening(invoer, opstelling, loads)
        S.geldige_pfd[opstelling] = (invoer, loads, r, data)
    except (ValueError, ArithmeticError, RuntimeError) as exc:
        geldig = S.geldige_pfd.get(opstelling)
        invoer, loads, r, data = geldig if geldig else basispunt(opstelling)
        melding = f"{'Laatste geldige bedrijfspunt' if geldig else 'Basisinvoer'} zichtbaar. {exc}"

    velden = {
        veld: {"naam": naam, "laag": ALLE[veld][2], "hoog": ALLE[veld][3], "waarde": invoer[veld]}
        for veld, naam in TEMPERATUURINVOER.items()
        if veld not in VELDEN_WARMTE or opstelling == "warmtenet"
    }
    uur = f"{S.uur:02d}:00" if S.modus == "Dagprofiel wind" else None
    status = ["In bedrijf" if last else ("Stand-by" if S[f"u{j}"] else "Onderhoud") for j, last in enumerate(loads, 1)]
    actie = PFD(
        opstelling=opstelling, blad=schema(opstelling), data=data, velden=velden, status=status, uur=uur,
        melding=melding, temperatuurmelding=S.get("temperatuurmelding"), key="visualpfd", default=None,
    )
    if isinstance(actie, dict) and isinstance(actie.get("id"), str) and actie["id"] != S.get("_pfd_afgehandeld"):
        S._pfd_afgehandeld = actie["id"]
        S._pfd_verzoek = actie
        st.rerun()

    if S.modus == "Dagprofiel wind":
        toon_windprofiel()
    toon_controles(r, invoer)
    toon_analyses(invoer, r, opstelling)


live()

"""Analyseweergaven naast het interactieve processchema."""

import math

import CoolProp.CoolProp as CP
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from itm_model import Invoer, coolprop, excel, leidingen, ts_cyclus, vergelijk_koudemiddelen

BASIS = Invoer()
T0 = 273.15


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


@st.cache_data(show_spinner=False, max_entries=64)
def ts_data(fluid, T_evap, T_cond, eta):
    return ts_cyclus(fluid, T_evap, T_cond, eta)


@st.cache_data(show_spinner=False, max_entries=64)
def km_tabel(T_evap, T_cond, eta, Q):
    return vergelijk_koudemiddelen(T_evap, T_cond, eta, Q)


@st.cache_data(show_spinner=False, max_entries=256)
def leidingtabel(invoer: dict, industrie: bool):
    return leidingen(Invoer(**invoer), gekozen_configuratie=industrie)


def warmtepomp(RC, opstelling):
    i = RC["i"]
    keuzes = ["WP-202 · industrie"]
    if opstelling == "warmtenet":
        keuzes.insert(0, "WP-201 · warmtenet")
    wp_keuze = st.radio("Warmtepomp", keuzes, horizontal=True, key="wp_keuze")
    is2 = wp_keuze.startswith("WP-202")
    cy = RC["cyclus2"] if is2 else RC["cyclus"]
    if not cy:
        st.info(f"{wp_keuze.split()[0]} levert geen warmte bij dit bedrijfspunt.")
    else:
        f = cy["fluid"]
        eta_k = i.eta_K202 if is2 else i.eta_K201
        try:
            D = ts_data(f, cy["T_evap"], cy["T_cond"], eta_k)
        except Exception as exc:
            st.error(f"T–s-diagram niet te maken voor {f}: {exc}")
            D = None
        if D:
            Q_c = RC["Q_ind"] if is2 else RC["Q_H"]
            Q_v = RC["Q_L2"] if is2 else RC["Q_L"]
            W_c = RC["W_K202"] if is2 else RC["W_K201"]
            m_ref = Q_c / D["q_uit"]                       # kg/s koudemiddel
            nm = dict(V="E-206" if is2 else "E-202", K="K-202" if is2 else "K-201", C="E-205" if is2 else "E-203",
                      TV="TV-202" if is2 else "TV-201", af="industriewater" if is2 else "warmtenet")
            bron = (RC["T_tw_naE202"], RC["T_tw_r"]) if is2 else (RC["T_tw_tussen"], RC["T_tw_naE202"])
            put = (i.T_ind_retour, i.T_ind_aanvoer) if is2 else (RC["T_E204"], i.T_net_aanvoer)
            P = D["punten"]
            c1, c2 = st.columns([3, 2])
            with c1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=D["koepel"]["s"], y=D["koepel"]["T"], mode="lines", line=dict(color="#8896a5", width=1.5),
                                         name="verzadigingslijn", hoverinfo="skip"))
                stappen = [("1→2 compressie", D["compressie"], "#c8461b"), ("2→3 condensor", D["condensor"], "#d27a1d"),
                           ("3→4 smoorventiel", D["smoren"], "#7b4bb2"), ("4→1 verdamper", D["verdamper"], "#1d6fb8")]
                for naam, pts_, kl in stappen:
                    fig.add_trace(go.Scatter(x=[p_[0] for p_ in pts_], y=[p_[1] for p_ in pts_], mode="lines",
                                             line=dict(color=kl, width=4), name=naam))
                fig.add_trace(go.Scatter(x=[P[1][0], P["2s"][0]], y=[P[1][1], P["2s"][1]], mode="lines",
                                         line=dict(color="#c8461b", dash="dot", width=1.5), name="isentroop (ideaal)"))
                fig.add_trace(go.Scatter(x=[P[k][0] for k in (1, 2, 3, 4)], y=[P[k][1] for k in (1, 2, 3, 4)], mode="markers+text",
                                         text=["1", "2", "3", "4"], textposition=["bottom right", "top right", "top left", "bottom left"],
                                         marker=dict(size=10, color="#16202a"), textfont=dict(size=15), showlegend=False))
                # bron (koelwater) en afnemer (warmtenet / industrie) als temperatuurlijn naast de cyclus
                fig.add_trace(go.Scatter(x=[P[1][0], P[4][0]], y=[bron[0], bron[1]], mode="lines",
                                         line=dict(color="#b8457e", width=3),
                                         name=f"koelwatercircuit {nl(bron[0], 1)} → {nl(bron[1], 1)} °C"))
                fig.add_trace(go.Scatter(x=[P[3][0], P[2][0]], y=[put[0], put[1]], mode="lines",
                                         line=dict(color="#e0531f" if is2 else "#d27a1d", width=3, dash="dash"),
                                         name=f"{nm['af']} {nl(put[0], 0)} → {nl(put[1], 0)} °C"))
                smin = min(D["koepel"]["s"]); smax = max(D["koepel"]["s"])
                fig.update_layout(height=520, margin=dict(l=10, r=10, t=40, b=40), title=f"T–s-diagram {wp_keuze.split(' ·')[0]} · {f}",
                                  xaxis_title="entropie s (kJ/kg·K)", yaxis_title="temperatuur T (°C)",
                                  legend=dict(orientation="h", y=-0.18))
                fig.update_xaxes(range=[smin + (smax - smin) * 0.25, max(smax, P[2][0]) + (smax - smin) * 0.08])
                fig.update_yaxes(range=[min(0, cy["T_evap"] - 30), max(D["Tcrit"] + 8, P[2][1] + 10)])
                st.plotly_chart(fig, width="stretch")
            with c2:
                st.subheader("Toestanden")
                st.dataframe(pd.DataFrame([
                    ("1 in compressor", nl(P[1][1], 1), nl(cy["P_evap_bar"], 2), nl(cy["h1"], 1), nl(P[1][0], 3), "verzadigde damp"),
                    ("2 uit compressor", nl(P[2][1], 1), nl(cy["P_cond_bar"], 2), nl(cy["h2"], 1), nl(P[2][0], 3), "oververhitte damp"),
                    ("3 uit condensor", nl(P[3][1], 1), nl(cy["P_cond_bar"], 2), nl(cy["h3"], 1), nl(P[3][0], 3), "verzadigde vloeistof"),
                    ("4 na smoorventiel", nl(P[4][1], 1), nl(cy["P_evap_bar"], 2), nl(cy["h3"], 1), nl(P[4][0], 3),
                     f"nat: {nl(cy['x4'] * 100, 0)} % damp"),
                ], columns=["Punt", "T °C", "p bar", "h kJ/kg", "s kJ/kg·K", "Toestand"]), hide_index=True, width="stretch")
                m1, m2, m3 = st.columns(3)
                m1.metric("COP", nl(cy["COP"], 2))
                m2.metric("COP Carnot", nl(cy["COP_carnot"], 2))
                m3.metric("ṁ koudemiddel", f"{nl(m_ref, 0)} kg/s")
                st.caption(f"Per kg koudemiddel: opnemen {nl(D['q_in'], 1)} kJ, compressor {nl(D['w'], 1)} kJ, "
                           f"afgeven {nl(D['q_uit'], 1)} kJ → COP = {nl(D['q_uit'], 1)} / {nl(D['w'], 1)} = {nl(cy['COP'], 2)}.")
            st.markdown(f"""
**Wat er gebeurt, stap voor stap** (koudemiddel {f}, verdampen bij {nl(cy['T_evap'], 0)} °C, condenseren bij {nl(cy['T_cond'], 0)} °C)

- **4 → 1 · verdamper {nm['V']} (warmte opnemen).** Het koudemiddel staat op lage druk ({nl(cy['P_evap_bar'], 1)} bar) en kookt daardoor al bij {nl(cy['T_evap'], 0)} °C.
  Het koelwater ({nl(bron[0], 1)} → {nl(bron[1], 1)} °C) is warmer, dus warmte stroomt naar het koudemiddel en dat verdampt helemaal.
  De temperatuur blijft gelijk (horizontale lijn), de entropie neemt toe. Opgenomen: {nl(D['q_in'], 0)} kJ/kg, samen **{nl(Q_v / 1000, 2)} MW**.
- **1 → 2 · compressor {nm['K']} (persen, kost stroom).** De damp wordt samengeperst van {nl(cy['P_evap_bar'], 1)} naar {nl(cy['P_cond_bar'], 1)} bar en wordt
  daardoor heet: {nl(P[2][1], 0)} °C. Een ideale compressor zou recht omhoog gaan (stippellijn, s gelijk); door wrijving (η = {nl(eta_k, 2)})
  schuift het punt iets naar rechts. Arbeid: {nl(D['w'], 0)} kJ/kg, samen **{nl(W_c / 1000, 2)} MW stroom**.
- **2 → 3 · condensor {nm['C']} (warmte afgeven).** Eerst koelt de hete damp af tot {nl(cy['T_cond'], 0)} °C, daarna condenseert hij bij die
  vaste temperatuur tot vloeistof (horizontale lijn). Het {nm['af']} ({nl(put[0], 0)} → {nl(put[1], 0)} °C) is kouder en neemt de warmte op:
  {nl(D['q_uit'], 0)} kJ/kg, samen **{nl(Q_c / 1000, 2)} MW** = opgenomen warmte + compressorstroom.
- **3 → 4 · smoorventiel {nm['TV']} (druk eraf).** De vloeistof gaat door een vernauwing terug naar {nl(cy['P_evap_bar'], 1)} bar. De enthalpie blijft gelijk,
  maar door de lagere druk kookt een deel meteen ({nl(cy['x4'] * 100, 0)} % damp) en koelt alles af tot {nl(cy['T_evap'], 0)} °C. Dit kost geen energie,
  maar het is een verlies (s neemt toe): daarom haalt de echte cyclus de Carnot-COP ({nl(cy['COP_carnot'], 2)}) niet.

**Lezen in het T–s-diagram:** de oppervlakte onder de verdamperlijn is de opgenomen warmte per kg, de oppervlakte onder de condensorlijn de
afgegeven warmte. Het verschil (de ingesloten lus) is ongeveer de compressorarbeid. Hoe dichter de koelwaterlijn boven de verdamper ligt en hoe
dichter de {nm['af']}lijn onder de condensor, hoe kleiner de lus en hoe hoger de COP; daarom willen we kleine ΔT's in de wisselaars.
""")

    st.divider()
    st.subheader("Koudemiddelen vergelijken")
    st.write("Dezelfde eenvoudige cyclus (verzadigde damp in de compressor, verzadigde vloeistof uit de condensor) doorgerekend met CoolProp "
             "voor elk koudemiddel, bij de huidige verdamp- en condensatietemperatuur en hetzelfde compressorrendement.")
    Te_ = i.T_kc_retour - i.dT_E201 - i.dT_min
    ranglijsten = [("WP-202 · industrie", i.T_ind_aanvoer + i.dT_min, i.eta_K202, max(RC["Q_ind"], 1.0), i.koudemiddel2)]
    if opstelling == "warmtenet":
        ranglijsten.insert(0, ("WP-201 · warmtenet", i.T_net_aanvoer + i.dT_min, i.eta_K201, RC["Q_H"], i.koudemiddel))
    for titel, Tc_, eta_, Q_, huidig in ranglijsten:
        rows = km_tabel(Te_, Tc_, eta_, Q_)
        df = pd.DataFrame([(("▶ " if r_["fluid"] == huidig else "") + r_["naam"], r_["gwp"], r_["klasse"], r_["Tcrit"],
                            r_.get("COP"), r_.get("Pe"), r_.get("Pc"), r_.get("T_pers"), (r_.get("x4") or 0) * 100 if r_["ok"] else None,
                            r_.get("V_comp"), r_["opmerking"]) for r_ in sorted(rows, key=lambda r_: -(r_.get("COP") or 0))],
                          columns=["Koudemiddel", "GWP", "Veiligheid", "T krit °C", "COP", "p verd. bar", "p cond. bar", "T pers °C",
                                   "damp na TV %", "Slagvolume m³/h", "Opmerking"])
        st.markdown(f"**{titel}** — verdampen {nl(Te_, 0)} °C, condenseren {nl(Tc_, 0)} °C, η {nl(eta_, 2)}, "
                    f"condensorvermogen {nl(Q_ / 1000, 2)} MW · ▶ = huidige keuze")
        fmt = lambda d: (lambda v: "–" if v is None or (isinstance(v, float) and not math.isfinite(v)) else nl(v, d))
        st.dataframe(df.style.format({"T krit °C": fmt(0), "COP": fmt(2), "p verd. bar": fmt(1), "p cond. bar": fmt(1),
                                      "T pers °C": fmt(0), "damp na TV %": fmt(0), "Slagvolume m³/h": fmt(0)}, na_rep="–"),
                     hide_index=True, width="stretch", height=36 * (len(df) + 1) + 4)
    st.caption("Veiligheidsklasse (ASHRAE 34): A = niet giftig, B = giftig; 1 = niet brandbaar, 2L = licht brandbaar, 2 = brandbaar, "
               "3 = zeer brandbaar. GWP = broeikaseffect t.o.v. CO₂ over 100 jaar. Slagvolume = zuigvolume dat de compressor moet "
               "verpompen voor het condensorvermogen: hoe groter, hoe groter de compressor en de zuigleiding. 'Persdamp nog nat' betekent "
               "dat in dit eenvoudige model de damp na de compressor nog druppels bevat; in de praktijk geef je dan 5–10 K oververhitting.")
    with st.expander("Hoe kies je een koudemiddel?"):
        st.markdown("""
1. **Kritische temperatuur ruim boven de condensatietemperatuur** (vuistregel 30–50 K). Vlak onder het kritische punt is er weinig
   condensatiewarmte, veel damp na het smoorventiel en een lage COP. Erboven kan het in deze opzet helemaal niet (transkritisch, zoals CO₂).
2. **Hoge COP**: minder stroom voor dezelfde warmte.
3. **Klein slagvolume**: compacte en goedkopere compressor en leidingen. Koudemiddelen met een lage druk (zoals R1233zd(E)) hebben een
   ijle damp en dus een groot slagvolume.
4. **Drukken binnen bereik**: geen onderdruk in de verdamper (lucht lekt naar binnen) en liever niet boven ±40 bar.
5. **Milieu en veiligheid**: lage GWP (F-gassenverordening) en een veiligheidsklasse die past bij de opstelling (ventilatie, gasdetectie).
""")


def h2_compressie(RC, mul, eenheid):
    i = RC["i"]
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


def gevoeligheid(invoer, n, alle):
    st.write(f"Varieer één invoergrootheid over het hele schuifbereik; alle andere invoer blijft zoals nu ({n} units in bedrijf).")
    c1, c2, c3 = st.columns(3)
    SWEEP = {"belasting": ("belasting", "Last per unit in bedrijf", 10.0, 100.0, 1.0, "%", 0, None)} | alle
    par = c1.selectbox("Invoer", list(SWEEP), format_func=lambda k: f"{SWEEP[k][1]} [{SWEEP[k][5]}]", index=0)
    UIT = {"Ẇ K-101 [kW]": lambda r: r["W_K101"] * n, "T uit K-101 [°C]": lambda r: r["T_uit_K101"],
           "Ẇ K-102 [kW]": lambda r: r["W_K102"] * n, "Q E-101 [kW]": lambda r: -r["Q_E101"] * n,
           "Condensaat S15 [kg/h]": lambda r: r["m_cond"] * n, "COP WP-201 [–]": lambda r: r["COP"],
           "Ẇ K-201 [kW]": lambda r: r["W_K201"], "Naar warmtenet [kW]": lambda r: r["Q_net"],
           "Warmte naar industrie [kW]": lambda r: r["Q_ind"], "COP WP-202 [–]": lambda r: r["COP2"],
           "Ẇ K-202 [kW]": lambda r: r["W_K202"], "H₂-warmte naar koelwatercircuit [kW]": lambda r: r["Q_H2_TW"], "Luchtkoelers naar buiten [kW]": lambda r: r["Q_AK"],
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
    if math.isfinite(invoer[par]):
        fig.add_vline(x=invoer[par], line_dash="dot", line_color="#8896a5", annotation_text="huidig")
    fig.update_layout(xaxis_title=f"{label} [{SWEEP[par][5]}]", yaxis_title=uit, height=440, margin=dict(l=10, r=10, t=20, b=40))
    st.plotly_chart(fig, width="stretch")


def vergelijking(invoer, RC):
    RX = excel(Invoer(**invoer))
    def delta_kleur(v):
        a = min(abs(v) / 15, 1) * 0.55
        return f"background-color: rgba({'200,70,27' if v > 0 else '29,111,184'},{a:.2f})" if abs(v) >= 0.5 else ""

    CMP = [("T_dauw", "Dauwpunt O₂-stroom", "°C"), ("m_cond", "Condensaat S15", "kg/h"), ("Q_E101", "Q E-101", "kW"),
           ("T_uit_K102", "T uit K-102", "°C"), ("W_K102", "Ẇ K-102", "kW"), ("T_uit_K101", "T uit K-101", "°C"),
           ("W_K101", "Ẇ K-101", "kW"), ("Q_pak_K101", "Pakketkoeler K-101", "kW"), ("Q_E102", "Q E-102", "kW"),
           ("Q_E103", "Q E-103", "kW"), ("V_V101", "Volume V-101", "m³"), ("V_V102", "Volume V-102", "m³"),
           ("P_AC_EOL", "Stroom ITM EOL", "kW"), ("COP", "COP WP-201", "–"),
           ("Q_E201", "E-201 (alle units)", "kW"), ("Q_E204", "E-204 direct", "kW"), ("Q_H", "Condensor E-203 (alle units)", "kW"), ("W_K201", "Ẇ K-201", "kW"),
           ("Q_net", "Naar warmtenet (alle units)", "kW"), ("COP2", "COP WP-202", "–"), ("W_K202", "Ẇ K-202", "kW")]
    df = pd.DataFrame([(l, u, RX[k], RC[k], (RC[k] - RX[k]) / abs(RX[k]) * 100 if (RX[k] and math.isfinite(RX[k]) and math.isfinite(RC[k])) else 0.0) for k, l, u in CMP],
                      columns=["Grootheid (per unit tenzij vermeld)", "Eenheid", "Rekenblad", "CoolProp", "Δ %"])
    st.dataframe(df.style.format({"Rekenblad": lambda v: nl(v, 2), "CoolProp": lambda v: nl(v, 2), "Δ %": lambda v: f"{'+' if v >= 0 else ''}{nl(v, 1)}"})
                 .map(delta_kleur, subset=["Δ %"]),
                 hide_index=True, width="stretch", height=720)


def stroomtabel_rekenblad(invoer, mul, eenheid):
    r = excel(Invoer(**invoer))
    ii = r["i"]
    rows = [
        ("S1", "vers UPW-suppletie → ITM", 0, 0, 0, r["m_vers"], ii.T_vers, ii.P_ITM_voed),
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
        ("S16", "P-101 → ITM (condensaat direct)", 0, 0, 0, r["m_cond"], ii.T_KO, ii.P_ITM_voed),
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
    st.caption(f"Rekenblad · {eenheid} · {ii.n_units} actieve units")
    st.download_button("Stroomtabel als CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="stroomtabel_rekenblad.csv", mime="text/csv")


def leidingdimensionering(invoer, opstelling):
    industrie = opstelling == "industrie"
    ontwerppunt = "vollast in de industriewarmte-opstelling" if industrie else "vollast met warmtenet en WP-201 in bedrijf"
    st.write("De minimale binnendiameter per leiding volgt uit **d_min = √(4·V̇ / (π·v_max))**, met V̇ = ṁ/ρ. "
             f"De tabel gebruikt {ontwerppunt} en maximale recycle voor S9. "
             "Dichtheden uit CoolProp (O₂ + damp als ideaal mengsel, S14 homogeen met druppels). "
             "Daarna de kleinste RVS-pijp ASME B36.19 sch. 40S met d_i ≥ d_min.")
    VMAX = [("v_max_H2", "H₂-gas", 5.0, 40.0, 1.0), ("v_max_O2", "O₂-gas (droog/verzadigd)", 5.0, 30.0, 1.0),
            ("v_max_nat", "O₂-gas met druppels (S14)", 3.0, 20.0, 1.0), ("v_max_pers", "Vloeistof pers/circuit", 0.5, 4.0, 0.1),
            ("v_max_zuig", "Vloeistof zuig/vrij verval", 0.3, 2.0, 0.1), ("v_max_ref_damp", "Koudemiddeldamp", 5.0, 25.0, 1.0),
            ("v_max_ref_vl", "Koudemiddelvloeistof", 0.3, 2.0, 0.1), ("v_max_ref_2f", "Koudemiddel tweefase", 2.0, 15.0, 0.5)]
    d = dict(invoer)
    with st.expander("Maximale snelheden (m/s) en aannames", expanded=False):
        cols = st.columns(4)
        for k_, (key, lab, lo, hi, stap) in enumerate(VMAX):
            d[key] = cols[k_ % 4].number_input(lab, lo, hi, float(getattr(BASIS, key)), stap, key=f"lei_{key}")
        c1, c2 = st.columns(2)
        d["rho_kc"] = c1.number_input("ρ koelcircuit water + Coolflow [kg/m³]", 950.0, 1150.0, float(BASIS.rho_kc), 5.0, key="lei_rho_kc")
        d["T_afvalwater"] = c2.number_input("T afvalwater S3 [°C]", 5.0, 80.0, float(BASIS.T_afvalwater), 1.0, key="lei_T_aw")
    d["n_units"] = BASIS.n_units
    try:
        L = leidingtabel(d, industrie)
    except Exception as exc:
        st.error(f"Leidingen niet door te rekenen: {exc}")
        L = []
    if L:
        df = pd.DataFrame([(l["id"], l["naam"], l["schaal"], l["medium"], l["m"], l["rho"], l["V"], l["v_max"], l["d_min"],
                            f"DN {l['DN']}" if l["DN"] else "> DN 800", l["d_i"], l["v"]) for l in L],
                          columns=["Nr", "Leiding", "Geldt", "Medium", "ṁ kg/h", "ρ kg/m³", "V̇ m³/h", "v_max m/s",
                                   "d_min mm", "DN (40S)", "d_i mm", "v m/s"])
        st.dataframe(df.style.format({"ṁ kg/h": lambda v: nl(v, 1 if v < 100 else 0), "ρ kg/m³": lambda v: nl(v, 3 if v < 10 else 1),
                                      "V̇ m³/h": lambda v: nl(v, 2 if v < 100 else 0), "v_max m/s": lambda v: nl(v, 1),
                                      "d_min mm": lambda v: nl(v, 1), "d_i mm": lambda v: nl(v, 1), "v m/s": lambda v: nl(v, 2)}),
                     hide_index=True, width="stretch", height=1130)
        st.caption(f"{BASIS.n_units} units · 'per unit' = leiding die elke unit zelf heeft, 'installatie' = gedeelde leiding. "
                   "S10 (blowoff) dimensioneren op het afblaasgeval, niet op het procesdebiet.")
        st.download_button("Leidingtabel als CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           file_name="leidingdimensionering.csv", mime="text/csv")

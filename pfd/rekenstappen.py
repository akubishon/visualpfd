"""Herkomst van de getallen in het live PFD, opgebouwd uit dezelfde doorrekening."""

from math import isfinite

from itm_model import CENGEL, PATM, R_UNIVERSEEL, T0, WATERDRUK_PA, druk_pa


class Rekenboek:
    def __init__(self):
        self.waarden = {}

    def getal(self, sleutel):
        return self.waarden[sleutel]["getal"]

    def _voeg_toe(self, sleutel, getal, naam, symbool, eenheid, soort, uitleg, formule="", argumenten=None):
        self.waarden[sleutel] = {
            "getal": getal if getal is not None and isfinite(getal) else None,
            "naam": naam, "symbool": symbool, "eenheid": eenheid, "soort": soort,
            "uitleg": uitleg, "formule": formule, "argumenten": argumenten or {},
        }
        return sleutel

    def gegeven(self, sleutel, getal, naam, symbool, eenheid, uitleg, *, soort="Invoer"):
        return self._voeg_toe(sleutel, getal, naam, symbool, eenheid, soort, uitleg)

    def formule(self, sleutel, getal, naam, symbool, eenheid, formule, uitleg, *, soort="Berekening", **argumenten):
        return self._voeg_toe(sleutel, getal, naam, symbool, eenheid, soort, uitleg, formule, argumenten)

    def opzoeking(self, sleutel, getal, naam, symbool, eenheid, medium, uitleg, **argumenten):
        volgorde = ", ".join("@" + arg for arg in argumenten)
        return self._voeg_toe(sleutel, getal, naam, symbool, eenheid, "CoolProp",
                              f"{medium}. {uitleg}",
                              rf"\operatorname{{CoolProp}}\!\left({volgorde}\right)" if volgorde else "",
                              argumenten)

    def afgeleid(self, sleutel, naam, symbool, eenheid, functie, formule, uitleg, **argumenten):
        getallen = {arg: self.getal(ref) for arg, ref in argumenten.items()}
        getal = functie(**getallen) if all(v is not None for v in getallen.values()) else None
        return self.formule(sleutel, getal, naam, symbool, eenheid, formule, uitleg, **argumenten)

    def stilstand(self, sleutel, naam, symbool, eenheid, *, getal=0.0, uitleg="Er is geen stroming bij dit bedrijfspunt."):
        return self.gegeven(sleutel, getal, naam, symbool, eenheid, uitleg, soort="Uit")

    def kelvin(self, temperatuur):
        sleutel = temperatuur + ".K"
        if sleutel not in self.waarden:
            self.afgeleid(sleutel, self.waarden[temperatuur]["naam"] + " in kelvin", "T_K", "K",
                          lambda t, n: t + n, "@t+@n", "CoolProp gebruikt de absolute temperatuur.",
                          t=temperatuur, n="T0")
        return sleutel

    def absoluut(self, druk):
        sleutel = druk + ".Pa"
        if sleutel not in self.waarden:
            barg = self.getal(druk)
            self.formule(sleutel, None if barg is None else druk_pa(barg),
                         "Absolute druk", "p_{abs}", "Pa", r"@p\cdot 10^5+@atm",
                         "Tel de atmosferische druk op bij de druk boven de atmosfeer.",
                         p=druk, atm="p_atm")
        return sleutel


TEMPERATUURINVOER = {
    "T_H2": "H₂ uit ITM", "T_O2_uit": "O₂-stroom uit ITM", "T_KO": "Na E-101 / KO-drum",
    "T_E102_uit": "H₂ uit E-102", "T_E103_uit": "H₂ uit E-103", "T_vers": "Vers UPW",
    "T_afvalwater": "Afvalwater", "T_kw_in": "Koelwater aanvoer", "T_kw_uit": "Koelwater retour",
    "T_kc_uit": "ITM-koelmiddel uit ITM", "T_kc_retour": "ITM-koelmiddel retour",
    "T_net_aanvoer": "Warmtenet aanvoer", "T_net_retour": "Warmtenet retour",
    "T_E204_uit": "Warmtenet na E-204", "T_ind_aanvoer": "Industrieaanvoer",
    "T_ind_retour": "Industrieretour",
}


def invoerstappen(boek, i, n):
    g = boek.gegeven
    nominaal = {
        "m_H2": "Nominaal H₂-debiet per ITM-unit",
        "m_O2mix": "Nominaal O₂-mengseldebiet per ITM-unit",
        "m_voedwater": "Nominaal voedingswater per ITM-unit",
        "m_afvalwater": "Nominaal afvalwater per ITM-unit",
        "m_kc_ds": "Nominaal ITM-koelmiddeldebiet per unit",
    }
    for veld, naam in nominaal.items():
        g("i." + veld, getattr(i, veld), naam, r"\dot m_{nom}", "kg/h", "Nominaal bedrijfspunt uit de ITM-gegevens van het model.")
    for veld, naam in TEMPERATUURINVOER.items():
        g("i." + veld, getattr(i, veld), naam, "T", "°C", "Temperatuurinstelling van het huidige bedrijfspunt.")
    for veld, naam in (
        ("P_H2_ITM", "Uitlaatdruk H₂ uit ITM"), ("P_V101_min", "Minimale druk V-101"),
        ("P_V101_max", "Maximale druk V-101"), ("P_K101_uit", "Persdruk K-101"),
        ("P_backbone", "Backbone-druk"), ("P_O2_uit", "Uitlaatdruk O₂ uit ITM"),
        ("P_RWZI", "Druk naar RWZI"), ("P_ITM_voed", "Voedwaterdruk ITM"), ("P_kc", "Druk ITM-koelcircuit"),
    ):
        g("i." + veld, getattr(i, veld), naam, "p_g", "barg", "Druk volgens de invoer van het model.")
    for veld, naam in (("dT_E201", "Temperatuurverschil E-201"), ("dT_min", "Minimaal wisselaarverschil"),
                        ("dT_pakket", "Temperatuurdaling pakketkoelers")):
        g("i." + veld, getattr(i, veld), naam, r"\Delta T", "K", "Instelling van het huidige bedrijfspunt.")
    for veld in ("K101", "K102", "K201", "K202", "P101"):
        g(f"i.eta_{veld}", getattr(i, f"eta_{veld}"), f"Rendement {veld[0]}-{veld[1:]}",
          r"\eta", "", "Isentroop compressorrendement of pomprendement uit de modelinvoer.")
    g("i.w_H2O", i.w_H2O, "Waterfractie in O₂-uitlaat", "w_{water}", "", "Massafractie uit de modelinvoer.")
    g("i.t_V101", i.t_V101, "Opslagtijd V-101", "t", "h", "Ingestelde buffertijd.")
    g("i.t_V102", i.t_V102, "Opslagtijd V-102", "t", "s", "Ingestelde buffertijd.")
    g("i.n_V101", i.n_V101, "Volumefactor V-101", "f", "", "Veiligheidsfactor uit het model.", soort="Modelaanname")
    g("i.Q_ITM_EOL", i.Q_ITM_EOL, "Nominaal koelvermogen per ITM-unit", "Q_{nom}", "kW", "Modelinvoer voor einde levensduur (EOL).")
    g("i.Q_ind", i.Q_ind, "Gevraagde industriewarmte", "Q_{vraag}", "kW",
      "De afnemer vraagt alle beschikbare warmte." if not isfinite(i.Q_ind) else "Warmtevraag van de afnemer.")
    g("i.m_min_pct", i.m_min_pct, "Minimumdebiet K-101", "f_{min}", "%", "Onder deze last recirculeert H₂ om het minimumdebiet te halen.")
    g("n", n, "Aantal actieve ITM-units", "n", "", "Volgt uit de installatielast, beschikbare units en gekozen inzetstrategie.")
    g("i.belasting", i.belasting if n else 0.0, "Last per actieve ITM-unit", "L", "%", "De gevraagde last wordt over de actieve units verdeeld.")
    g("T0", T0, "Nulpunt van de Celsiusschaal", "T_0", "K", "Een temperatuur van 0 °C komt overeen met 273,15 K.", soort="Constante")
    g("p_atm", PATM * 1000, "Standaard atmosferische druk", "p_{atm}", "Pa", "Een standaardatmosfeer.", soort="Constante")
    g("R", R_UNIVERSEEL, "Universele gasconstante", "R", "J/(mol·K)", "Constante in de idealegaswet.", soort="Constante")
    g("HHV", CENGEL["HHV_H2"], "Bovenste verbrandingswaarde H₂", "HHV_{H_2}", "kJ/kg",
      "Referentiewaarde uit het rekenblad, inclusief condensatiewarmte.", soort="Modelaanname")
    g("p_damp_ideaal", 500.0, "Referentiedruk waterdamp", "p_{ref}", "Pa",
      "Het model gebruikt enthalpie bij zeer lage druk als benadering voor ideale waterdamp.", soort="Modelaanname")
    g("x_damp", 1, "Verzadigde damp", "x_v", "", "De massafractie damp is één.", soort="Toestand")
    g("x_vloeistof", 0, "Verzadigde vloeistof", "x_l", "", "De massafractie damp is nul.", soort="Toestand")
    g("i.rho_kc", i.rho_kc, "Dichtheid water/CoolFlow DTX (62/38)", r"\rho_{kc}", "kg/m³",
      "Vaste dichtheid voor het ITM-koelmiddelmengsel rond 50 °C.", soort="Modelaanname")
    for circuit, druk in WATERDRUK_PA.items():
        g("p." + circuit, druk, f"Aangenomen absolute druk · {circuit}", "p_{abs}", "Pa",
          "Vaste druk gebruikt voor de stofeigenschappen van deze waterkring.", soort="Modelaanname")


def processtappen(boek, r, tussen):
    """Formules volgen de rekenvolgorde van itm_model.coolprop."""
    i = r["i"]
    f = boek.formule
    op = boek.opzoeking
    tk = boek.kelvin
    pa = boek.absoluut

    f("lastfactor", r["_f_last"], "Lastfactor van een actieve unit", "f_L", "", "@last/100",
      "Zet het ingestelde lastpercentage om naar een fractie.", last="i.belasting")
    for veld, naam, waarde in (
        ("m_H2", "Productie H₂", i.m_H2), ("m_O2mix", "O₂-stroom uit ITM", i.m_O2mix),
        ("m_voedwater", "Totaal voedingswater", i.m_voedwater), ("m_afvalwater", "Afvalwater uit ITM", i.m_afvalwater),
        ("m_kc_ds", "ITM-koelmiddel per unit", r["m_kc_unit"]),
    ):
        f(veld, waarde, naam + " per actieve unit", r"\dot m", "kg/h", r"@nom\cdot @f",
          "Het model schaalt het nominale debiet lineair met de last.", nom="i." + veld, f="lastfactor")
    f("Q_ITM_EOL", i.Q_ITM_EOL, "Restwarmte per actieve ITM-unit", "Q_{ITM,u}", "kW",
      r"@nom\cdot @f", "Schaal de nominale ITM-restwarmte met de last.", nom="i.Q_ITM_EOL", f="lastfactor")
    f("m_S9", r["m_S9"], "Recycle S9 per actieve unit", r"\dot m_{S9}", "kg/h",
      r"\max\!\left(0, @nom \cdot @min/100 - @prod\right)",
      "Recycle vult het verschil met het minimumdebiet van K-101 aan. Bij voldoende productiedebiet is recycle nul.",
      nom="i.m_H2", min="i.m_min_pct", prod="m_H2")
    f("m_S5", r["m_S5"], "Debiet door K-101 per actieve unit", r"\dot m_{S5}", "kg/h", "@prod+@rec",
      "Bij de productie komt het waterstofdebiet dat terugkeert via de recycle.", prod="m_H2", rec="m_S9")

    op("M_O2", r["M_O2"], "Molaire massa zuurstof", "M_{O_2}", "kg/kmol", "Zuurstof", "Molaire massa uit de stoffendatabase.")
    op("M_H2O", r["M_H2O"], "Molaire massa water", "M_{H_2O}", "kg/kmol", "Water", "Molaire massa uit de stoffendatabase.")
    f("m_H2O_in", r["m_H2O_in"], "Water in O₂-mengsel per unit", r"\dot m_{H_2O,in}", "kg/h", r"@mix\cdot @w",
      "Splits de waterfractie af van het totale mengseldebiet.", mix="m_O2mix", w="i.w_H2O")
    f("m_O2", r["m_O2"], "Droge zuurstof per unit", r"\dot m_{O_2}", "kg/h", "@mix-@wat",
      "Het resterende massadebiet is zuurstof.", mix="m_O2mix", wat="m_H2O_in")
    f("N_O2", r["N_O2"], "Hoeveelheid zuurstof per uur", r"\dot n_{O_2}", "kmol/h", "@m/@M",
      "Deel het massadebiet door de molaire massa.", m="m_O2", M="M_O2")
    f("N_H2O", r["N_H2O"], "Hoeveelheid ingaande waterdamp per uur", r"\dot n_{H_2O}", "kmol/h", "@m/@M",
      "Zet de watermassa om naar hoeveelheid stof.", m="m_H2O_in", M="M_H2O")
    f("y_v", r["y_v"], "Molfractie waterdamp vóór E-101", "y_{v,in}", "", r"\frac{@nv}{@nv+@no}",
      "Partiële druk volgt uit de molfractie bij een ideaal mengsel.", nv="N_H2O", no="N_O2")
    op("Psat_KO", r["Psat_KO"], "Verzadigingsdruk water bij KO-temperatuur", "p_{sat}", "Pa",
       "Water", "Zoek de druk van verzadigd water op bij de temperatuur van de KO-drum.",
       T=tk("i.T_KO"), x="x_vloeistof")
    po = pa("i.P_O2_uit")
    f("y_v_max", r["y_v_max"], "Molfractie waterdamp na E-101", "y_{v,KO}", "", "@sat/@p",
      "Na afkoelen is de uitgaande gasfase in dit model verzadigd.", sat="Psat_KO", p=po)
    f("m_v", r["m_v"], "Waterdamp die meegaat met O₂ per unit", r"\dot m_v", "kg/h",
      r"\frac{@y}{1-@y}\cdot @no\cdot @M", "Zet de verhouding waterdamp/zuurstof om naar een massadebiet.",
      y="y_v_max", no="N_O2", M="M_H2O")
    f("m_cond", r["m_cond"], "Condensaat per actieve unit", r"\dot m_{cond}", "kg/h", "@water-@damp",
      "De KO-drum scheidt het gecondenseerde water af.", water="m_H2O_in", damp="m_v")
    f("m_gas", r["m_gas"], "Vochtig gas na de KO-drum per unit", r"\dot m_{gas}", "kg/h", "@o+@v",
      "Zuurstof en resterende waterdamp gaan samen naar K-102.", o="m_O2", v="m_v")
    f("m_vers", r["m_vers"], "Vers UPW per actieve unit", r"\dot m_{vers}", "kg/h", "@voed-@cond",
      "Condensaat keert via P-101 terug naar ITM. Vers UPW vult het voedingswater aan.",
      voed="m_voedwater", cond="m_cond")

    for sleutel, druk, y in (("pO2_in", po, "y_v"), ("pO2_ko", po, "y_v_max"),
                              ("pO2_2", pa("i.P_RWZI"), "y_v_max")):
        f(sleutel, r[sleutel], "Partiële zuurstofdruk", "p_{O_2}", "Pa", r"(1-@y)\cdot @p",
          "Zuurstof draagt het zuurstofdeel van de totale mengseldruk.", y=y, p=druk)
    for toestand, t, p in (("in", "i.T_O2_uit", "pO2_in"), ("ko", "i.T_KO", "pO2_ko")):
        op(f"h_O2_{toestand}", r[f"h_O2_{toestand}"], "Enthalpie zuurstof", "h_{O_2}", "J/kg", "Zuurstof",
           "Gebruik temperatuur en partiële zuurstofdruk.", T=tk(t), p=p)
        op(f"h_v_{toestand}", r[f"h_v_{toestand}"], "Enthalpie waterdamp", "h_v", "J/kg", "Waterdamp",
           "De lage referentiedruk benadert de enthalpie van ideale waterdamp.", T=tk(t), p="p_damp_ideaal")
    op("h_f_KO", r["h_f_KO"], "Enthalpie condensaat", "h_l", "J/kg", "Water",
       "Gebruik verzadigde vloeistof bij de KO-temperatuur.", T=tk("i.T_KO"), x="x_vloeistof")
    f("Q_c_O2", r["Q_c_O2"], "Enthalpieverandering van zuurstof", "Q_{O_2}", "kW",
      r"\frac{@m}{3600}\frac{@uit-@in_}{1000}", "Zuurstof koelt af en verliest enthalpie.",
      m="m_O2", in_="h_O2_in", uit="h_O2_ko")
    f("Q_c_w", r["Q_c_w"], "Enthalpieverandering van water in E-101", "Q_{water}", "kW",
      r"\frac{@mv @hv+@ml @hl-@mi @hi}{3600\cdot 1000}",
      "Vergelijk de enthalpie van waterdamp en condensaat na E-101 met die van de inkomende damp.",
      mv="m_v", hv="h_v_ko", ml="m_cond", hl="h_f_KO", mi="m_H2O_in", hi="h_v_in")
    f("Q_E101", r["Q_E101"], "Warmteverandering O₂-stroom in E-101", "Q_{E101}", "kW", "@gas+@water",
      "Tel het afkoelen van zuurstof en het afkoelen en condenseren van water op.", gas="Q_c_O2", water="Q_c_w")

    f("T_S6", r["T_S6"], "H₂ na de pakketkoeler van K-101", "T_{S6}", "°C", "@pers-@dt",
      "De pakketkoeler verlaagt de perstemperatuur met het ingestelde temperatuurverschil.", pers="T_uit_K101", dt="i.dT_pakket")
    f("T_S18", r["T_S18"], "O₂-mengsel na de pakketkoeler", "T_{S18}", "°C", "@pers-@dt",
      "De pakketkoeler verlaagt de temperatuur vóór levering aan RWZI.", pers="T_uit_K102", dt="i.dT_pakket")
    compressorstappen(boek, r, tussen)
    waterstappen(boek, r)
    bufferstappen(boek, r)
    f("P_AC_EOL", r["P_AC_EOL"], "Elektrisch ITM-vermogen per actieve unit", "P_{ITM,u}", "kW",
      r"\frac{@m\cdot @HHV}{3600} + @warmte-@koeling", "De balans omvat de chemische energie van H₂ en het warmteverlies.",
      m="m_H2", HHV="HHV", warmte="Q_ITM_EOL", koeling="Q_E101")


def compressorstappen(boek, r, tussen):
    f, op = boek.formule, boek.opzoeking
    tk, pa = boek.kelvin, boek.absoluut
    T1, P1, P2 = tk("i.T_H2"), pa("i.P_V101_min"), pa("i.P_K101_uit")
    op("h1h", r["h1h"], "Enthalpie H₂ aan de zuigzijde", "h_1", "J/kg", "Waterstof",
       "Gebruik zuigtemperatuur en zuigdruk.", T=T1, p=P1)
    op("s1h", r["s1h"], "Entropie H₂ aan de zuigzijde", "s_1", "J/(kg·K)", "Waterstof",
       "De entropie bepaalt het ideale compressiepad.", T=T1, p=P1)
    op("h2sh", r["h2sh"], "Enthalpie H₂ na ideale compressie", "h_{2s}", "J/kg", "Waterstof",
       "Zoek de enthalpie bij de persdruk en de entropie aan de zuigzijde.", p=P2, s="s1h")
    for doel, h_in, h_is, eta, label in (
        ("h2h", "h1h", "h2sh", "i.eta_K101", "H₂"), ("h2", "h1", "h2s", "i.eta_K102", "O₂-mengsel"),
    ):
        f(doel, r[doel], f"Enthalpie na compressie · {label}", "h_2", "J/kg",
          r"@h1+\frac{@hs-@h1}{@eta}", "Het werkelijke enthalpieverschil is groter door het compressorrendement.",
          h1=h_in, hs=h_is, eta=eta)
    op("T_uit_K101", r["T_uit_K101"], "Perstemperatuur K-101", "T_{2}", "°C", "Waterstof",
       "Zoek de temperatuur bij de persdruk en werkelijke enthalpie. CoolProp geeft K, weergegeven in °C.", p=P2, h="h2h")

    # Numerieke oplossingen volgen uit de mengseleigenschappen bij dezelfde partiële drukken.
    f("T2s", r["T2s"], "Isentrope perstemperatuur K-102", "T_{2s}", "°C", r"s_{\mathrm{mix}}(T_{2s},@p)=@s",
      "Halveer het temperatuurinterval van de KO-temperatuur tot 400 °C tot de mengselentropie gelijk is aan die bij de zuigzijde.",
      soort="Bisectie", p=pa("i.P_RWZI"), s="s1")
    f("T_uit_K102", r["T_uit_K102"], "Perstemperatuur K-102", "T_{2}", "°C", r"h_{\mathrm{mix}}(T_2,@p)=@h",
      "Halveer het temperatuurinterval van de KO-temperatuur tot 500 °C tot de mengselenthalpie het berekende h₂ bereikt.",
      soort="Bisectie", p="pO2_2", h="h2")
    f("pv_1", r["pv_1"], "Partiële waterdampdruk aan de zuigzijde", "p_v", "Pa", r"@y\cdot @p",
      "Vermenigvuldig de totale druk met de molfractie waterdamp.", y="y_v_max", p=pa("i.P_O2_uit"))
    op("s1_o2", tussen["s1_o2"], "Entropie zuurstof aan de zuigzijde", "s_{O_2}", "J/(kg·K)", "Zuurstof",
       "Gebruik de partiële zuurstofdruk en de temperatuur in de KO-drum.", T=tk("i.T_KO"), p="pO2_ko")
    op("s1_damp_ref", tussen["s1_damp_ref"], "Waterdampentropie bij referentiedruk", "s_{ref}", "J/(kg·K)", "Waterdamp",
       "De berekening start bij de entropie van waterdamp bij zeer lage druk.", T=tk("i.T_KO"), p="p_damp_ideaal")
    f("s1_damp", tussen["s1_damp"], "Entropie waterdamp bij partiële druk", "s_v", "J/(kg·K)",
      r"@s-\frac{@R}{@M/1000}\ln\!\left(\frac{@p}{@pref}\right)",
      "Corrigeer de referentie-entropie met de drukverhouding van een ideaal gas.",
      s="s1_damp_ref", R="R", M="M_H2O", p="pv_1", pref="p_damp_ideaal")
    f("s1", r["s1"], "Entropie mengsel aan de zuigzijde", "s_1", "J/(kg·K)", r"\frac{@mo @so+@mv @sv}{@m}",
      "Weeg de entropie van zuurstof en waterdamp met hun eigen debiet.", mo="m_O2", so="s1_o2", mv="m_v", sv="s1_damp", m="m_gas")
    for punt, t, p, suffix in (
        ("h1", "i.T_KO", "pO2_ko", "zuigzijde"), ("h2s", "T2s", "pO2_2", "isentrope perszijde"),
        ("h_S18", "T_S18", "pO2_2", "na de pakketkoeler"),
    ):
        op(punt + "_o2", tussen[punt + "_o2"], f"Enthalpie O₂ · {suffix}", "h_{O_2}", "J/kg",
           "Zuurstof", "Toestand bij de partiële zuurstofdruk.", T=tk(t), p=p)
        op(punt + "_damp", tussen[punt + "_damp"], f"Enthalpie waterdamp · {suffix}", "h_v", "J/kg",
           "Waterdamp", "Benadering voor ideale waterdamp.", T=tk(t), p="p_damp_ideaal")
        f(punt, r[punt], f"Mengselenthalpie · {suffix}", "h_{mix}", "J/kg",
          r"\frac{@mo @ho+@mv @hv}{@m}", "Weeg de enthalpie van iedere stof met haar massadebiet.",
          mo="m_O2", ho=punt + "_o2", mv="m_v", hv=punt + "_damp", m="m_gas")

    for sleutel, t in (("h_S6", "T_S6"), ("h_S7", "i.T_E102_uit"), ("h_S8", "i.T_E103_uit")):
        op(sleutel, r[sleutel], f"H₂-enthalpie op {sleutel[2:]}", "h_{H_2}", "J/kg", "Waterstof",
           "Zoek de enthalpie op aan de hand van temperatuur en persdruk.", T=tk(t), p=P2)

    for sleutel, debiet, eerst, laatst, naam in (
        ("W_K101", "m_S5", "h1h", "h2h", "Compressorvermogen K-101"),
        ("W_K102", "m_gas", "h1", "h2", "Compressorvermogen K-102"),
        ("Q_pak_K101", "m_S5", "h_S6", "h2h", "Afgevoerde warmte pakketkoeler K-101"),
        ("Q_pak_K102", "m_gas", "h_S18", "h2", "Afgevoerde warmte pakketkoeler K-102"),
        ("Q_E102", "m_S5", "h_S6", "h_S7", "Warmteverandering H₂ in E-102"),
        ("Q_E103", "m_S5", "h_S7", "h_S8", "Warmteverandering H₂ in E-103"),
    ):
        f(sleutel, r[sleutel], naam + " per unit", "W" if sleutel.startswith("W") else "Q", "kW",
          r"\frac{@m}{3600}\frac{@b-@a}{1000}",
          "Vermenigvuldig de enthalpieverandering in J/kg met het debiet in kg/s en druk het resultaat uit in kW.",
          m=debiet, a=eerst, b=laatst)


def waterstappen(boek, r):
    f, op = boek.formule, boek.opzoeking
    op("rho_f_KO", r["rho_f_KO"], "Dichtheid verzadigd condensaat", r"\rho_f", "kg/m³", "Water",
       "De pompberekening gebruikt verzadigde vloeistof bij de KO-temperatuur.", T=boek.kelvin("i.T_KO"), x="x_vloeistof")
    f("W_P101", r["W_P101"], "Vermogen condensaatpomp per unit", "W_{P101}", "kW",
      r"\frac{@m}{3600} \frac{@p2-@p1}{1000 @rho @eta}",
      "De pomp verhoogt de druk van het condensaat. Het rendement bepaalt het benodigde elektrische vermogen.",
      m="m_cond", p2=boek.absoluut("i.P_ITM_voed"), p1=boek.absoluut("i.P_O2_uit"),
      rho="rho_f_KO", eta="i.eta_P101")
    for kant in ("in", "uit"):
        op(f"h_kw_{kant}", r[f"h_kw_{kant}"], f"Enthalpie koelwater · {kant}", "h", "J/kg", "Water",
           "Toestand bij de temperatuur van deze aansluiting en de aangenomen koelwaterdruk.",
           T=boek.kelvin("i.T_kw_" + kant), p="p.koelwater")
    f("dh_kw", r["cp_w"], "Enthalpiestijging koelwater", r"\Delta h_{kw}", "kJ/kg", "(@uit-@in_)/1000",
      "Iedere kilogram koelwater neemt dit verschil aan warmte op.", uit="h_kw_uit", in_="h_kw_in")
    for onderdeel in ("E101", "E103"):
        sleutel = "m_kw_" + onderdeel
        f(sleutel, r[sleutel], f"Koelwaterdebiet {onderdeel} per unit", r"\dot m_{kw}", "kg/h",
          r"\frac{-@Q}{@dh}\cdot 3600", "De koelwaterstroom voert precies de berekende koellast af.",
          Q="Q_" + onderdeel, dh="dh_kw")


def bufferstappen(boek, r):
    nummer_vaten = {
        "V101": ("P_V101_min", "P_V101_max", "i.n_V101"), "V102": ("P_backbone", "P_K101_uit", "k_H2"),
    }
    for sleutel, naam, symbool in (("cp_H2", "constante druk", "c_p"), ("cv_H2", "constant volume", "c_v")):
        boek.opzoeking(sleutel, r[sleutel], f"Warmtecapaciteit H₂ bij {naam}", symbool, "J/(kg·K)", "Waterstof",
                       "Stofeigenschap bij de H₂-temperatuur en de standaard atmosferische druk.",
                       T=boek.kelvin("i.T_H2"), p="p_atm")
    boek.formule("k_H2", r["k_H2"], "Soortelijke-warmteverhouding van H₂", r"\kappa", "", r"\frac{@cp}{@cv}",
                 "De verhouding benadert de volumecorrectie voor snelle expansie uit V-102.", cp="cp_H2", cv="cv_H2")
    for vat, (p_min, p_max, factor) in nummer_vaten.items():
        cid = vat.lower()
        for grens, p in (("min", p_min), ("max", p_max)):
            sleutel = f"rho_{cid}_{grens}"
            boek.opzoeking(sleutel, r[sleutel], f"Dichtheid bij {grens}imale bufferdruk", r"\rho_" + grens,
                           "kg/m³", "Waterstof", "Het vatmodel neemt een constante temperatuur aan.",
                           T=boek.kelvin("i.T_H2"), p=boek.absoluut("i." + p))
        dat = "V_" + vat
        uren = vat == "V101"
        term = "@t" if uren else "@t/3600"
        boek.formule(dat + "_iso", r[dat + "_iso"], f"Isotherm buffervolume {vat}", "V_{iso}", "m³",
                     rf"\frac{{@m\cdot {term}}}{{@hoog-@laag}}",
                     "Het drukbereik bepaalt hoeveel massa per kubieke meter beschikbaar is.",
                     m="m_H2", t="i.t_" + vat, hoog=f"rho_{cid}_max", laag=f"rho_{cid}_min")
        boek.formule(dat, r[dat], f"Buffervolume {vat} per unit", "V", "m³", r"@V\cdot @f",
                     "Pas de volumecorrectie van het betreffende vat toe.", V=dat + "_iso", f=factor)


def cyclusstappen(boek, cy, nr):
    """Stofeigenschappen en energiebalans per kg koudemiddel."""
    voor = f"wp{nr}."
    f, op = boek.formule, boek.opzoeking
    medium = cy["fluid"]
    kant = "net" if nr == 201 else "ind"
    t_cond = f"i.T_{kant}_aanvoer"
    f(voor + "Te", cy["T_evap"], "Verdampingstemperatuur", "T_e", "°C", "@ret-@dt1-@dt2",
      "Het koudemiddel moet kouder zijn dan de retour van het koelwatercircuit.",
      ret="i.T_kc_retour", dt1="i.dT_E201", dt2="i.dT_min")
    f(voor + "Tc", cy["T_cond"], "Condensatietemperatuur", "T_c", "°C", "@aan+@dt",
      "Voor warmteafgifte is het koudemiddel warmer dan het water dat de condensor verlaat.", aan=t_cond, dt="i.dT_min")
    Te, Tc = boek.kelvin(voor + "Te"), boek.kelvin(voor + "Tc")
    Pe, Pc = voor + "Pe", voor + "Pc"
    op(Pe, cy["P_evap_bar"] * 1e5, "Verdampingsdruk", "p_e", "Pa", medium,
       "Verzadigingsdruk aan de zuigzijde bij de verdampingstemperatuur.", T=Te, x="x_damp")
    op(Pc, cy["P_cond_bar"] * 1e5, "Condensatiedruk", "p_c", "Pa", medium,
       "Verzadigingsdruk aan de perszijde bij de condensatietemperatuur.", T=Tc, x="x_vloeistof")
    op(voor + "h1", cy["h1"], "Enthalpie naar compressor", "h_1", "kJ/kg", medium,
       "Verzadigde damp uit de verdamper. De enthalpie is omgezet van J/kg naar kJ/kg.", T=Te, x="x_damp")
    op(voor + "s1", cy["s1"], "Entropie naar compressor", "s_1", "kJ/(kg·K)", medium,
       "Verzadigde damp uit de verdamper. CoolProp geeft J/(kg·K).", T=Te, x="x_damp")
    op(voor + "h2s", cy["h2s"], "Enthalpie na ideale compressie", "h_{2s}", "kJ/kg", medium,
       "Gebruik de condensatiedruk en dezelfde entropie als aan de zuigzijde, omgerekend naar J/(kg·K).", p=Pc, s=voor + "s1")
    f(voor + "h2", cy["h2"], "Enthalpie na werkelijke compressie", "h_2", "kJ/kg",
      r"@h+\frac{@hs-@h}{@eta}", "Het rendement geeft de extra energie aan die nodig is voor de werkelijke compressie.",
      h=voor + "h1", hs=voor + "h2s", eta=f"i.eta_K{nr}")
    op(voor + "h3", cy["h3"], "Enthalpie uit de condensor", "h_3", "kJ/kg", medium,
       "De condensor levert verzadigde vloeistof op bij de condensatietemperatuur.", T=Tc, x="x_vloeistof")
    op(voor + "Tpers", cy["T_pers"], "Perstemperatuur koudemiddel", "T_2", "°C", medium,
       "Gebruik persdruk en enthalpie. CoolProp geeft K, weergegeven in °C.", p=Pc, h=voor + "h2")
    for sleutel, naam, sym, ingang, uit in (
        ("q", "Afgegeven warmte per kg koudemiddel", "q_H", "h3", "h2"),
        ("w", "Compressorarbeid per kg koudemiddel", "w", "h1", "h2"),
    ):
        boek.afgeleid(voor + sleutel, naam, sym, "kJ/kg", lambda a, b: b - a, "@b-@a",
                      "Neem het enthalpieverschil per kilogram koudemiddel.", a=voor + ingang, b=voor + uit)
    cop = "COP" if nr == 201 else "COP2"
    f(cop, cy["COP"], f"COP WP-{nr}", r"\mathrm{COP}", "", r"\frac{@q}{@w}",
      "De verwarmings-COP geeft aan hoeveel warmte de condensor levert per eenheid compressorarbeid.",
      q=voor + "q", w=voor + "w")


WARMTEMETRIEKEN = {
    "Q_ITM_tot": "ITM-restwarmte",
    "Q_E201": "Warmte naar koelwatercircuit",
    "Q_AK": "Afvoer via luchtkoelers",
    "Q_E204": "Directe warmte warmtenet",
    "Q_H": "Afgegeven warmte WP-201",
    "Q_L": "Opgenomen warmte WP-201",
    "W_K201": "Compressorvermogen WP-201",
    "Q_net": "Geleverde warmte warmtenet",
    "Q_ind": "Geleverde industriewarmte",
    "Q_L2": "Opgenomen warmte WP-202",
    "W_K202": "Compressorvermogen WP-202",
    "Q_H2_TW": "Teruggewonnen warmte H₂-koelers",
    "chk_p5": "Restverschil warmteketen",
}


def warmtestappen(boek, r, tussen):
    f = boek.formule
    i = r["i"]
    for nr, cy, actief in ((201, r["cyclus"], r["Q_H"] > 0), (202, r["cyclus2"], r["Q_ind"] > 0)):
        if actief:
            cyclusstappen(boek, cy, nr)
        else:
            boek.stilstand("COP" if nr == 201 else "COP2", f"COP WP-{nr}", r"\mathrm{COP}", "", getal=None,
                          uitleg="De warmtepomp levert bij dit bedrijfspunt geen warmte. Er is geen verhouding van warmte tot compressorarbeid.")

    f("Q_ITM_tot", r["Q_ITM_tot"], WARMTEMETRIEKEN["Q_ITM_tot"], "Q_{ITM}", "kW", r"@n\cdot @q",
      "Tel de restwarmte van de actieve ITM-units op.", n="n", q="Q_ITM_EOL")
    f("Q_H2_tot", r["Q_H2_tot"], "Beschikbare warmte uit H₂-koelers", "Q_{H_2}", "kW", r"@n\cdot(@pak-@e102)",
      "Som van de koelvermogens van de pakketkoeler en E-102.", n="n", pak="Q_pak_K101", e102="Q_E102")
    if i.h2_warmteterugwinning:
        f("Q_bron", tussen["Q_bron"], "Beschikbaar bronvermogen", "Q_{bron}", "kW", "@itm+@h2",
          "Dit scenario gebruikt zowel de ITM-restwarmte als de warmte van de H₂-koelers.", itm="Q_ITM_tot", h2="Q_H2_tot")
    else:
        f("Q_bron", tussen["Q_bron"], "Beschikbaar bronvermogen", "Q_{bron}", "kW", "@itm",
          "De industriewarmte-opstelling wint warmte uit het ITM-koelcircuit. De H₂-koelers hebben externe koeling.", itm="Q_ITM_tot")

    for veld, temperatuur, toelichting in (
        ("T_tw_a", "T_kc_uit", "De warme aanvoer neemt via E-201 warmte uit ITM op."),
        ("T_tw_r", "T_kc_retour", "Het koelwater keert na de warmteafnemers terug naar E-201."),
    ):
        f(veld, r[veld], "Koelwatercircuit " + ("aanvoer" if veld.endswith("_a") else "retour"), "T_{TW}", "°C",
          "@kc-@dt", toelichting + " Het model gebruikt het wisselaarverschil van E-201.", kc="i." + temperatuur, dt="i.dT_E201")
    f("T_E204", r["T_E204"], "Temperatuur netwater na E-204", "T_{E204}", "°C", r"\max\!\left(@set,@ret\right)",
      "Bij een instelling onder de retour blijft de voorverwarmer buiten bedrijf.", set="i.T_E204_uit", ret="i.T_net_retour")
    for sleutel, t in (
        ("h_tw_aan", "T_tw_a"), ("h_tw_ret", "T_tw_r"), ("h_ind_aan", "i.T_ind_aanvoer"),
        ("h_ind_ret", "i.T_ind_retour"), ("h_net_aan", "i.T_net_aanvoer"),
        ("h_net_ret", "i.T_net_retour"), ("h_E204", "T_E204"),
    ):
        boek.opzoeking(sleutel, tussen[sleutel], "Waterenthalpie · " + boek.waarden[t]["naam"], "h_w", "kJ/kg",
                       "Water", "Het warmteketenmodel gebruikt 1 MPa voor de waterenthalpieën. Uitkomst in kJ/kg.",
                       T=boek.kelvin(t), p="p.industrie")
    f("cpw", tussen["cpw"], "Gemiddelde warmtecapaciteit van het TW-water", "c_{p,TW}", "kJ/(kg·K)",
      r"\frac{@ha-@hr}{@ta-@tr}", "Deel de enthalpieverandering door het temperatuurverschil over het TW-circuit.",
      ha="h_tw_aan", hr="h_tw_ret", ta="T_tw_a", tr="T_tw_r")

    if r["Q_ind"] > 0:
        f("f_L2", tussen["f_L2"], "Aandeel bronwarmte in industriewarmte", "f_L", "", "1-1/@cop",
          "Het overige aandeel van de geleverde warmte komt van de compressor.", cop="COP2")
        boek.afgeleid("Q_ind_max", "Maximale levering industrie", "Q_{max}", "kW",
                      lambda q, bron: q / bron, "@q/@bron", "Om elke kW aan de condensor te leveren is dit aandeel bronwarmte nodig.",
                      q="Q_bron", bron="f_L2")
        if not isfinite(i.Q_ind):
            f("Q_ind", r["Q_ind"], WARMTEMETRIEKEN["Q_ind"], "Q_{ind}", "kW", "@max",
              "Bij maximale afname gebruikt WP-202 alle beschikbare bronwarmte.", max="Q_ind_max")
        else:
            f("Q_ind", r["Q_ind"], WARMTEMETRIEKEN["Q_ind"], "Q_{ind}", "kW", r"\min\!\left(@vraag,@max\right)",
              "Lever de ingestelde warmtevraag tot de grens van de beschikbare bronwarmte.", vraag="i.Q_ind", max="Q_ind_max")
        f("Q_L2", r["Q_L2"], WARMTEMETRIEKEN["Q_L2"], "Q_{L,202}", "kW", r"@ind\cdot @f",
          "E-206 haalt dit deel van het vermogen uit het koelwatercircuit.", ind="Q_ind", f="f_L2")
        f("W_K202", r["W_K202"], WARMTEMETRIEKEN["W_K202"], "W_{202}", "kW", "@ind-@bron",
          "Het elektrische compressorvermogen vult de bronwarmte aan tot het condensorvermogen.",
          ind="Q_ind", bron="Q_L2")
        f("m_ind_th", r["m_ind_th"], "Industriewaterdebiet", r"\dot m_{ind}", "t/h",
          r"\frac{@ind}{@ha-@hr}\cdot 3{,}6",
          "Deel het vermogen door de enthalpiestijging per kilogram industriewater. Zet kg/s om naar ton per uur.",
          ind="Q_ind", ha="h_ind_aan", hr="h_ind_ret")
    else:
        for sleutel in ("Q_ind", "Q_L2", "W_K202", "m_ind_th"):
            boek.stilstand(sleutel, WARMTEMETRIEKEN.get(sleutel, "Industriewaterdebiet"), r"\dot m" if sleutel == "m_ind_th" else "Q",
                           "t/h" if sleutel == "m_ind_th" else "kW", uitleg="De industrie neemt bij dit bedrijfspunt geen warmte af.")

    f("Qb", tussen["Qb"], "Beschikbare warmte na WP-202", "Q_b", "kW", "@bron-@industrie",
      "De warmtenetketen krijgt de warmte die overblijft na opname door E-206.", bron="Q_bron", industrie="Q_L2")
    warmtenetstappen(boek, r)
    f("Q_TW", r["Q_TW"], "Afgenomen vermogen uit het TW-circuit", "Q_{TW}", "kW", "@direct+@wp1+@wp2",
      "Tel de onttrekkingen van de voorverwarmer en beide verdampers op.", direct="Q_E204", wp1="Q_L", wp2="Q_L2")
    if i.h2_warmteterugwinning:
        f("Q_H2_TW", r["Q_H2_TW"], WARMTEMETRIEKEN["Q_H2_TW"], "Q_{H_2,TW}", "kW", r"\min\!\left(@beschikbaar,@afname\right)",
          "De H₂-koelers leveren eerst aan de TW-vraag, tot hun beschikbare koelvermogen.",
          beschikbaar="Q_H2_tot", afname="Q_TW")
    else:
        boek.stilstand("Q_H2_TW", WARMTEMETRIEKEN["Q_H2_TW"], "Q_{H_2,TW}", "kW",
                       uitleg="In de industriewarmte-opstelling gaat H₂-koelwarmte naar de externe koeling.")
    f("Q_E201", r["Q_E201"], WARMTEMETRIEKEN["Q_E201"], "Q_{E201}", "kW", "@afname-@h2",
      "E-201 levert uit ITM het deel van de TW-vraag dat overblijft na bijdrage van de H₂-koelers.", afname="Q_TW", h2="Q_H2_TW")
    f("Q_AK", r["Q_AK"], WARMTEMETRIEKEN["Q_AK"], "Q_{AK}", "kW", "@itm-@e201",
      "De luchtkoelers voeren de restwarmte af die E-201 overlaat.", itm="Q_ITM_tot", e201="Q_E201")
    f("m_tw", r["m_tw"], "Debiet hoofdkring TW", r"\dot m_{TW}", "kg/s", r"\frac{@q}{@cp(@ta-@tr)}",
      "Voor een groter afgenomen vermogen is bij dit temperatuurverschil meer circulatiedebiet nodig.",
      q="Q_TW", cp="cpw", ta="T_tw_a", tr="T_tw_r")
    if r["m_tw"] > 0:
        for veld, invoer, q, naam in (
            ("T_tw_tussen", "T_tw_a", "Q_E204", "TW na E-204"), ("T_tw_naE202", "T_tw_tussen", "Q_L", "TW na E-202"),
        ):
            f(veld, r[veld], naam, "T_{uit}", "°C", r"@tin-\frac{@q}{@m\cdot @cp}",
              "Door warmteafgifte daalt de temperatuur van het water.", tin=invoer, q=q, m="m_tw", cp="cpw")
    else:
        for veld in ("T_tw_tussen", "T_tw_naE202"):
            boek.stilstand(veld, "Temperatuur stilstaande TW-kring", "T", "°C", getal=None)
    f("m_tw_H2_unit", r["m_tw_H2_unit"], "TW-debiet H₂-koeltak per unit", r"\dot m_{TW,H_2,u}", "kg/h",
      r"\frac{@q/@n}{@cp(@ta-@tr)}\cdot 3600",
      "Deel de teruggewonnen H₂-warmte over de actieve units en bepaal het bijbehorende koeldebiet.",
      q="Q_H2_TW", n="n", cp="cpw", ta="T_tw_a", tr="T_tw_r")
    f("cp_kc", r["cp_kc"], "Warmtecapaciteit ITM-koelmiddel", "c_{p,kc}", "kJ/(kg·K)",
      r"\frac{@q}{(@m/3600)(@uit-@ret)}", "Het model leidt de warmtecapaciteit af uit de nominale warmte en het ITM-debiet.",
      q="Q_ITM_EOL", m="m_kc_ds", uit="i.T_kc_uit", ret="i.T_kc_retour")
    f("T_kc_naE201", r["T_kc_naE201"], "Temperatuur ITM-koelmiddel na E-201", "T_{A2}", "°C",
      r"@t-\frac{@Q/@n}{(@m/3600)@cp}", "E-201 onttrekt per actieve unit dit deel van de ITM-restwarmte.",
      t="i.T_kc_uit", Q="Q_E201", n="n", m="m_kc_ds", cp="cp_kc")
    f("chk_p5", r["chk_p5"], WARMTEMETRIEKEN["chk_p5"], r"\Delta Q", "kW",
      "@itm+@h2+@w1+@w2-@net-@ind-@ak",
      "Vergelijk de toevoer van warmte en compressorvermogen met de levering en de warmteafvoer.",
      itm="Q_ITM_tot", h2="Q_H2_TW", w1="W_K201", w2="W_K202", net="Q_net", ind="Q_ind", ak="Q_AK")


def warmtenetstappen(boek, r):
    f = boek.formule
    if r["Q_net"] > 0 and r["Q_H"] > 0:
        boek.afgeleid("f_L", "Aandeel bronwarmte in WP-201", "f_L", "", lambda cop: 1 - 1 / cop, "1-1/@cop",
                      "Het overige aandeel van de geleverde warmte komt van de compressor.", cop="COP")
        f("r_E204", r["r_E204"], "Verhouding voorverwarming tot condensorwarmte", "r_{E204}", "",
          r"\frac{@h2-@h1}{@h3-@h2}", "De verhouding volgt uit de twee enthalpiestijgingen van hetzelfde netwater.",
          h1="h_net_ret", h2="h_E204", h3="h_net_aan")
        f("Q_H", r["Q_H"], WARMTEMETRIEKEN["Q_H"], "Q_{H,201}", "kW", r"\frac{@bron}{@r+@f}",
          "De beschikbare TW-warmte verdeelt zich over directe voorverwarming en de verdamper.",
          bron="Qb", r="r_E204", f="f_L")
        f("Q_E204", r["Q_E204"], WARMTEMETRIEKEN["Q_E204"], "Q_{E204}", "kW", r"@r\cdot @q",
          "Bereken uit de verhouding de rechtstreekse levering aan het netwater.", r="r_E204", q="Q_H")
        f("Q_L", r["Q_L"], WARMTEMETRIEKEN["Q_L"], "Q_{L,201}", "kW", r"@f\cdot @q",
          "E-202 haalt dit aandeel van het condensorvermogen uit het TW-water.", f="f_L", q="Q_H")
        f("W_K201", r["W_K201"], WARMTEMETRIEKEN["W_K201"], "W_{201}", "kW", "@cond-@verd",
          "Vul het verdampervermogen aan tot het condensorvermogen.", cond="Q_H", verd="Q_L")
        term, laag, hoog = "Q_H", "h_E204", "h_net_aan"
        aanvoer = "i.T_net_aanvoer"
    else:
        for veld in ("Q_H", "Q_L", "W_K201"):
            boek.stilstand(veld, WARMTEMETRIEKEN[veld], "Q", "kW", uitleg="WP-201 levert bij dit bedrijfspunt geen warmte.")
        if r["Q_E204"] > 0:
            f("Q_E204", r["Q_E204"], WARMTEMETRIEKEN["Q_E204"], "Q_{E204}", "kW", "@bron",
              "De beschikbare warmte gaat rechtstreeks via E-204 naar het netwater.", bron="Qb")
        else:
            boek.stilstand("Q_E204", WARMTEMETRIEKEN["Q_E204"], "Q_{E204}", "kW", uitleg="E-204 levert bij dit bedrijfspunt geen warmte.")
        term, laag, hoog = "Q_E204", "h_net_ret", "h_E204"
        aanvoer = "T_E204"
    f("Q_net", r["Q_net"], WARMTEMETRIEKEN["Q_net"], "Q_{net}", "kW", "@direct+@cond",
      "Het netwater krijgt warmte via E-204 en de warmtepompcondensor.", direct="Q_E204", cond="Q_H")
    if r["Q_net"] > 0:
        f("m_net_th", r["m_net_th"], "Warmtenetdebiet", r"\dot m_{net}", "t/h", r"\frac{@q}{@h2-@h1}\cdot 3{,}6",
          "Uit het vermogen en de enthalpiestijging volgt het debiet in kg/s. Vermenigvuldig met 3,6 voor ton per uur.",
          q=term, h2=hoog, h1=laag)
        f("T_aanvoer", r["T_aanvoer"], "Werkelijke warmtenetaanvoer", "T_{aan}", "°C", "@t",
          "De laatste actieve verwarmingsstap bepaalt de aanvoertemperatuur.", t=aanvoer)
    else:
        boek.stilstand("m_net_th", "Warmtenetdebiet", r"\dot m_{net}", "t/h")
        boek.stilstand("T_aanvoer", "Warmtenetaanvoer bij stilstand", "T_{aan}", "°C", getal=None)

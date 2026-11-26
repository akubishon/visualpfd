"""Actuele toestanden per getekende stroom en de bijbehorende rekenstappen."""

from math import isfinite

from itm_model import PS, coolprop, gasmengsel_dichtheid, koudemiddel_toestanden
from pfd.rekenstappen import Rekenboek, WARMTEMETRIEKEN, invoerstappen, processtappen, warmtestappen
from pfd.schema import schema

DEBIETEENHEDEN = (("kg_h", "kg/h"), ("kg_s", "kg/s"), ("m3_h", "m³/h"), ("m3_s", "m³/s"))

PARALLEL_VERMOGEN = {
    "P_AC_EOL": ("P_AC_tot", "Elektrisch vermogen ITM", 1),
    "W_K101": ("W_K101_tot", "Compressorvermogen K-101", 1),
    "W_K102": ("W_K102_tot", "Compressorvermogen K-102", 1),
    "W_P101": ("W_P101_tot", "Vermogen condensaatpomp P-101", 1),
    "Q_pak_K101": ("Q_pak_K101_tot", "Afgevoerde pakketwarmte K-101", 1),
    "Q_pak_K102": ("Q_pak_K102_tot", "Afgevoerde pakketwarmte K-102", 1),
    "Q_E101": ("Q_E101_tot", "Koellast E-101", -1),
    "Q_E102": ("Q_E102_tot", "Koellast E-102", -1),
    "Q_E103": ("Q_E103_tot", "Koellast E-103", -1),
}


def valideer_invoer(i):
    regels = (
        (i.T_kc_retour < i.T_kc_uit, "De ITM-koelmiddelretour moet kouder zijn dan de aanvoer."),
        (i.T_kw_in < i.T_kw_uit, "De koelwaterretour moet warmer zijn dan de aanvoer."),
        (i.T_E103_uit <= i.T_E102_uit, "H₂ uit E-103 mag niet warmer zijn dan H₂ uit E-102."),
        (i.T_KO < i.T_O2_uit, "De temperatuur in de KO-drum moet lager zijn dan die van de O₂-uitlaat."),
        (i.P_V101_min < i.P_V101_max, "De minimale druk van V-101 moet onder de maximale druk liggen."),
        (i.P_O2_uit <= i.P_RWZI, "De persdruk van K-102 moet minstens gelijk zijn aan de zuigdruk."),
        (i.Q_ind <= 0 or i.T_ind_retour < i.T_ind_aanvoer, "De industrieretour moet kouder zijn dan de industrieaanvoer."),
        (
            not (i.net_aan and i.wp_aan) or max(i.T_E204_uit, i.T_net_retour) < i.T_net_aanvoer,
            "De warmtenetaanvoer moet warmer zijn dan de retour en de voorverwarming na E-204.",
        ),
    )
    for geldig, bericht in regels:
        if not geldig:
            raise ValueError(bericht)
    for actief, nr, medium, t_cond in (
        (i.net_aan and i.wp_aan, "WP-201", i.koudemiddel, i.T_net_aanvoer + i.dT_min),
        (i.Q_ind > 0, "WP-202", i.koudemiddel2, i.T_ind_aanvoer + i.dT_min),
    ):
        if actief:
            kritisch = PS("Tcrit", medium) - 273.15
            verdamping = i.T_kc_retour - i.dT_E201 - i.dT_min
            if not verdamping < t_cond < kritisch:
                raise ValueError(
                    f"{nr} condenseert met {medium} tussen de verdampingstemperatuur "
                    f"en {kritisch:.1f} °C. Pas de temperatuur of het koudemiddel aan."
                )


def valideer_resultaat(r):
    if r["m_cond"] < 0:
        raise ValueError("Met deze invoer overstijgt de berekende waterdamp het beschikbare water in de O₂-stroom.")
    if r["Q_E102"] > 0 or r["Q_E103"] > 0:
        raise ValueError("De H₂-koelers vragen een uitlaattemperatuur onder hun inlaattemperatuur.")
    for condensor, werk, cop in (("Q_H", "W_K201", "COP"), ("Q_ind", "W_K202", "COP2")):
        if r[condensor] > 0 and (not isfinite(r[cop]) or r[cop] <= 1 or r[werk] <= 0):
            raise ValueError("De actieve warmtepompcyclus levert geen geldige verwarmings-COP.")


class Stromen:
    def __init__(self, boek, actief):
        self.boek = boek
        self.actief = actief
        self.rijen = {}

    def voeg_toe(self, id_, medium, m, t, p, *, parallel=False, dichtheid=None, stof=None,
                druk_aanname=False, toestand_uitleg=None):
        boek = self.boek
        naam = f"Stroom {id_}"
        uitleg = toestand_uitleg or "Deze toestand vraagt temperatuur en druk op de betreffende aansluiting."
        velden = {}
        if not self.actief or m is None:
            nul_uitleg = "De installatie staat stil." if not self.actief else uitleg
            m = boek.stilstand(f"{id_}.bron", f"Massadebiet {id_}", r"\dot m", "kg/h", uitleg=nul_uitleg)
            t, p, dichtheid = None, None, None
        if t is None:
            t = boek.gegeven(f"{id_}.T", None, f"Temperatuur {id_}", "T", "°C", uitleg, soort="Toestand")
        if p is None:
            p = boek.gegeven(f"{id_}.p", None, f"Druk {id_}", "p_g", "barg", uitleg, soort="Toestand")
        if p.startswith("p.") and p.count(".") == 1:
            p_abs = p
            p = p + ".barg"
            if p not in boek.waarden:
                boek.afgeleid(p, boek.waarden[p_abs]["naam"], "p_g", "barg", lambda p, atm: (p - atm) / 1e5,
                              r"\frac{@p-@atm}{10^5}", "Druk gemeten boven de standaardatmosfeer.", p=p_abs, atm="p_atm")
        else:
            p_abs = boek.absoluut(p)
        if dichtheid is None:
            rho = None
            if stof and boek.getal(t) is not None and boek.getal(p_abs) is not None:
                T = boek.kelvin(t)
                rho = PS("D", "T", boek.getal(T), "P", boek.getal(p_abs), stof)
                dichtheid = boek.opzoeking(f"{id_}.rho", rho, f"Dichtheid {id_}", r"\rho", "kg/m³", medium,
                                          "Zoek de dichtheid op bij deze temperatuur en absolute druk.", T=T, p=p_abs)
            else:
                dichtheid = boek.gegeven(f"{id_}.rho", rho, f"Dichtheid {id_}", r"\rho", "kg/m³",
                                         uitleg, soort="Toestand")
        massah = f"{id_}.kg_h"
        if parallel:
            boek.afgeleid(massah, f"Massadebiet {id_} · installatie", r"\dot m", "kg/h", lambda m, n: m * n,
                          r"@m\cdot @n", "Tel dezelfde stroom over de actieve ITM-units op.", m=m, n="n")
        else:
            boek.afgeleid(massah, f"Massadebiet {id_}", r"\dot m", "kg/h", lambda m: m, "@m",
                          "Dit is het debiet op deze aansluiting.", m=m)
        velden.update(temperatuur=t, druk=p, dichtheid=dichtheid, **self.debieten(id_, massah, dichtheid))
        per_unit = self.debieten(id_ + ".unit", m, dichtheid) if parallel else None
        self.rijen[id_] = dict(naam=naam, medium=medium, waarden=velden, per_unit=per_unit, druk_aanname=druk_aanname)
        return velden

    def debieten(self, id_, m, rho):
        b = self.boek
        kg_s = b.afgeleid(id_ + ".kg_s", f"Massadebiet {id_} in kg/s", r"\dot m", "kg/s", lambda m: m / 3600,
                          r"\frac{@m}{3600}", "Een uur telt 3.600 seconden.", m=m)
        m3h = id_ + ".m3_h"
        if b.getal(m) == 0 and b.getal(rho) is None:
            b.stilstand(m3h, f"Volumedebiet {id_}", r"\dot V", "m³/h", uitleg="Bij stilstand passeert er geen volume.")
        else:
            b.afgeleid(m3h, f"Volumedebiet {id_} in m³/h", r"\dot V", "m³/h", lambda m, rho: m / rho,
                       r"\frac{@m}{@rho}", "Deel het massadebiet door de dichtheid op deze aansluiting.", m=m, rho=rho)
        m3s = b.afgeleid(id_ + ".m3_s", f"Volumedebiet {id_} in m³/s", r"\dot V", "m³/s", lambda v: v / 3600,
                         r"\frac{@v}{3600}", "Zet het volume per uur om naar volume per seconde.", v=m3h)
        return dict(kg_h=m, kg_s=kg_s, m3_h=m3h, m3_s=m3s)

    def water(self, id_, m, t, p, *, medium="Water", parallel=False):
        return self.voeg_toe(id_, medium, m, t, p, parallel=parallel, stof="Water", druk_aanname=p.startswith("p."))

    def gasdichtheid(self, id_, t, p, waterdamp):
        if not self.actief:
            return None
        b = self.boek
        M = b.afgeleid(f"{id_}.M", "Molaire massa vochtig zuurstofmengsel", "M_{mix}", "kg/mol",
                       lambda mo, mv, Mo, Mv: (mo + mv) / (mo / Mo + mv / Mv) / 1000,
                       r"\frac{@mo+@mv}{@mo/@Mo+@mv/@Mv}\cdot 10^{-3}",
                       "Deel het totale massadebiet door de som van de molaire debieten.",
                       mo="m_O2", mv=waterdamp, Mo="M_O2", Mv="M_H2O")
        T, P = b.kelvin(t), b.absoluut(p)
        return b.formule(f"{id_}.rho", gasmengsel_dichtheid(b.getal(T), b.getal(P), b.getal(M)),
                         f"Dichtheid vochtig gas · {id_}", r"\rho_{mix}", "kg/m³", r"\frac{@p @M}{@R @T}",
                         "Pas de idealegaswet toe op het zuurstof-waterdampmengsel.", p=P, M=M, R="R", T=T)


def processtromen(stromen):
    b = stromen.boek
    stromen.water("S1", "m_vers", "i.T_vers", "i.P_ITM_voed", medium="Ultrapuur water (UPW)", parallel=True)
    stromen.water("S3", "m_afvalwater", "i.T_afvalwater", "p.afvoer", medium="Afvalwater", parallel=True)
    for id_, m, t, p in (
        ("S4", "m_H2", "i.T_H2", "P_H2_ITM"), ("S5", "m_S5", "i.T_H2", "P_V101_min"),
        ("K101-uit", "m_S5", "T_uit_K101", "P_K101_uit"), ("S6", "m_S5", "T_S6", "P_K101_uit"),
        ("S7", "m_S5", "i.T_E102_uit", "P_K101_uit"), ("S8", "m_S5", "i.T_E103_uit", "P_K101_uit"),
        ("S9-in", "m_S9", "i.T_E103_uit", "P_K101_uit"), ("S9", "m_S9", "i.T_E103_uit", "P_V101_min"),
        ("S11-in", "m_H2", "i.T_E103_uit", "P_K101_uit"), ("S11", "m_H2", "i.T_E103_uit", "P_backbone"),
        ("S12", "m_H2", "i.T_E103_uit", "P_backbone"),
    ):
        stromen.voeg_toe(id_, "H₂", m, t, "i." + p, parallel=True, stof="Hydrogen")
    stromen.voeg_toe("V102-uit", "H₂", "m_H2", "i.T_E103_uit", None, parallel=True,
                    toestand_uitleg="De druk in V-102 varieert tussen de minimale en maximale bufferdruk.")
    stromen.voeg_toe("S10", "H₂", None, None, None,
                    toestand_uitleg="De afblaasleiding is gesloten tijdens de stationaire procesberekening.")
    for id_, m, t, p, damp in (
        ("S13", "m_O2mix", "i.T_O2_uit", "i.P_O2_uit", "m_H2O_in"),
        ("S17", "m_gas", "i.T_KO", "i.P_O2_uit", "m_v"),
        ("K102-uit", "m_gas", "T_uit_K102", "i.P_RWZI", "m_v"),
        ("S18", "m_gas", "T_S18", "i.P_RWZI", "m_v"),
    ):
        stromen.voeg_toe(id_, "O₂ + waterdamp", m, t, p, parallel=True, dichtheid=stromen.gasdichtheid(id_, t, p, damp))
    cond = stromen.water("S15", "m_cond", "i.T_KO", "i.P_O2_uit", medium="Condensaat (UPW)", parallel=True)
    stromen.water("S16", "m_cond", "i.T_KO", "i.P_ITM_voed", medium="Condensaat (UPW)", parallel=True)
    rho = None
    if stromen.actief:
        rho = b.afgeleid("S14.rho", "Dichtheid nat O₂-mengsel · S14", r"\rho_{S14}", "kg/m³",
                         lambda m, mg, rg, ml, rl: m / (mg / rg + ml / rl),
                         r"\frac{@m}{@mg/@rg+@ml/@rl}",
                         "Tel het volume van het vochtige gas en de waterdruppels op. Het model veronderstelt een homogeen mengsel.",
                         m="m_O2mix", mg="m_gas", rg="S17.rho", ml="m_cond", rl=cond["dichtheid"])
    stromen.voeg_toe("S14", "O₂ + waterdamp + vloeibaar water", "m_O2mix", "i.T_KO", "i.P_O2_uit",
                    parallel=True, dichtheid=rho)

    for id_, t in (("A", "i.T_kc_uit"), ("A2", "T_kc_naE201"), ("B", "i.T_kc_retour")):
        stromen.voeg_toe(id_, "Water/CoolFlow DTX (62/38)", "m_kc_ds", t, "i.P_kc", parallel=True, dichtheid="i.rho_kc")
    for nr, onderdeel in ((1, "E101"), (2, "E103")):
        for kant in ("in", "uit"):
            stromen.water(f"KW{nr}-{kant}", f"m_kw_{onderdeel}", "i.T_kw_" + kant, "p.koelwater",
                          medium="Koelwater", parallel=True)


def warmte_stromen(stromen, i, r, opstelling):
    b = stromen.boek
    warmtenet = opstelling == "warmtenet"
    if stromen.actief:
        for naar, bron, naam, factor in (
            ("m_tw_h", "m_tw", "Hoofddebiet TW", 3600),
            ("m_ind_h", "m_ind_th", "Industriewaterdebiet", 1000),
            ("m_net_h", "m_net_th", "Warmtenetdebiet", 1000),
        ):
            b.afgeleid(naar, naam, r"\dot m", "kg/h", lambda m: m * factor, rf"@m\cdot {factor}",
                       "Druk het debiet uit in kg per uur.", m=bron)
        if warmtenet:
            b.afgeleid("m_twh", "TW-debiet van de H₂-koeltak", r"\dot m_{TW,H_2}", "kg/h", lambda m, n: m * n,
                       r"@m\cdot @n", "Tel het koelwaterdebiet van de H₂-tak over de actieve units op.", m="m_tw_H2_unit", n="n")
            b.afgeleid("m_twe201", "TW-debiet van de E-201-tak", r"\dot m_{TW,E201}", "kg/h", lambda m, h: m - h,
                       "@m-@h", "Bij het retourverzamelpunt splitst het hoofddebiet naar de H₂-koelers en E-201.", m="m_tw_h", h="m_twh")
            if b.getal("m_twh") > 0:
                b.afgeleid("fractie_H2_TW", "Teruggewonnen fractie H₂-koelwarmte", "f", "", lambda q, qtot: q / qtot,
                           "@q/@qtot", "Bij gedeeltelijke afname verdeelt de app het teruggewonnen aandeel naar verhouding over de twee koelers.",
                           q="Q_H2_TW", qtot="Q_H2_tot")
                b.afgeleid("T_twh_tussen", "TW tussen de H₂-koelers", "T_{TW,H_2}", "°C",
                           lambda t, q, f, m, cp: t + q * f * 3600 / (m * cp),
                           r"@t+\frac{@q @f}{(@m/3600)@cp}", "Na E-102 is het TW-water warmer. Daarna stroomt het door de pakketkoeler.",
                           t="T_tw_r", q="Q_E102_tot", f="fractie_H2_TW", m="m_twh", cp="cpw")
    stromen.water("TW1", "m_tw_h", "T_tw_a", "p.TW", medium="TW-water")
    stromen.water("TW3", "m_twe201" if warmtenet else "m_tw_h", "T_tw_r", "p.TW", medium="TW-water")
    for id_, t in (("I1", "i.T_ind_aanvoer"), ("I2", "i.T_ind_retour")):
        stromen.water(id_, "m_ind_h", t, "p.industrie", medium="Industriewater")
    if warmtenet:
        for id_, m, t in (
            ("TW", "m_twe201", "T_tw_a"), ("TW2", "m_tw_h", "T_tw_tussen"), ("TW4", "m_tw_h", "T_tw_naE202"),
            ("TW5", "m_tw_h", "T_tw_r"), ("TWH1", "m_twh", "T_tw_r"),
            ("TWH-tussen", "m_twh", "T_twh_tussen" if "T_twh_tussen" in b.waarden else None), ("TWH2", "m_twh", "T_tw_a"),
        ):
            stromen.water(id_, m, t, "p.TW", medium="TW-water")
        for id_, t in (("N1", "i.T_net_retour"), ("N2", "T_E204"), ("N3", "T_aanvoer")):
            stromen.water(id_, "m_net_h", t, "p.net", medium="Netwater")
        koudemiddelstromen(stromen, r, 201, i.koudemiddel)
    koudemiddelstromen(stromen, r, 202, i.koudemiddel2)


def koudemiddelstromen(stromen, r, nr, medium):
    b = stromen.boek
    ref = f"wp{nr}."
    cond = "Q_H" if nr == 201 else "Q_ind"
    actief = stromen.actief and r[cond] > 0
    eerste = 1 if nr == 201 else 5
    fasen = ("verzadigde damp", "persdamp", "verzadigde vloeistof", "vloeistof + damp")
    if not actief:
        for volgnummer, fase in enumerate(fasen, eerste):
            stromen.voeg_toe(f"R{volgnummer}", f"{medium} · {fase}", None, None, None,
                            toestand_uitleg=f"WP-{nr} staat stil. Het koudemiddel circuleert niet.")
        return

    cy = r["cyclus" if nr == 201 else "cyclus2"]
    m = b.afgeleid(ref + "kg_h", f"Koudemiddeldebiet WP-{nr}", r"\dot m_{ref}", "kg/h",
                  lambda q, dh: q / dh * 3600, r"\frac{@q}{@dh}\cdot 3600",
                  "Het condensorvermogen bepaalt hoeveel kilogram koudemiddel per uur door de cyclus gaat.", q=cond, dh=ref + "q")
    for druk in ("Pe", "Pc"):
        b.afgeleid(ref + druk + ".barg", f"{b.waarden[ref + druk]['naam']} in barg", "p_g", "barg",
                   lambda p, atm: (p - atm) / 1e5, r"\frac{@p-@atm}{10^5}",
                   "Trek voor de overdruk de atmosferische druk af.", p=ref + druk, atm="p_atm")
    toestanden = koudemiddel_toestanden(cy)
    toestand_refs = (
        dict(T=b.kelvin(ref + "Te"), x="x_damp"),
        dict(p=ref + "Pc", h=ref + "h2"),
        dict(T=b.kelvin(ref + "Tc"), x="x_vloeistof"),
        dict(p=ref + "Pe", h=ref + "h3"),
    )
    for j, (fase, t, druk, toestand, args) in enumerate(zip(
        fasen, ("Te", "Tpers", "Tc", "Te"), ("Pe", "Pc", "Pc", "Pe"), toestanden, toestand_refs
    ), eerste):
        id_ = f"R{j}"
        rho = b.opzoeking(f"{id_}.rho", PS("D", *toestand, medium), f"Dichtheid {id_}", r"\rho", "kg/m³", medium,
                         f"Stofeigenschap voor {fase}. CoolProp gebruikt absolute SI-eenheden.",
                         **args)
        stromen.voeg_toe(id_, f"{medium} · {fase}", m, ref + t, ref + druk + ".barg", dichtheid=rho)


def installatiecijfers(boek, r, loads):
    for bron, (sleutel, naam, teken) in PARALLEL_VERMOGEN.items():
        if r is not None:
            boek.afgeleid(sleutel, naam, "P" if sleutel.startswith(("P", "W")) else "Q", "kW",
                          lambda q, n: teken * q * n, (r"-@q\cdot @n" if teken < 0 else r"@q\cdot @n"),
                          "Tel de bijdrage van de actieve units op. Afgevoerde warmte wordt als positief koelvermogen weergegeven.",
                          q=bron, n="n")
        else:
            boek.stilstand(sleutel, naam, "Q", "kW", uitleg="De installatie staat stil.")
    if r is None:
        for sleutel, naam in WARMTEMETRIEKEN.items():
            boek.stilstand(sleutel, naam, "Q", "kW", uitleg="De installatie staat stil.")
        for sleutel in ("V_V101", "V_V102"):
            boek.stilstand(sleutel, "Benodigd buffervolume per unit", "V", "m³", uitleg="Er is geen actieve productie om te bufferen.")
        for cop, nr in (("COP", 201), ("COP2", 202)):
            boek.stilstand(cop, f"COP WP-{nr}", r"\mathrm{COP}", "", getal=None, uitleg="De installatie staat stil.")
    for j, last in enumerate(loads, 1):
        voor = f"unit{j}."
        if last:
            for sleutel, naam, sym, eenheid, bron in (
                ("last", "Last ITM-unit", "L", "%", "i.belasting"),
                ("warmte", "Restwarmte ITM-unit", "Q", "kW", "Q_ITM_EOL"),
                ("AC", "Elektrisch vermogen ITM-unit", "P", "kW", "P_AC_EOL"),
            ):
                boek.afgeleid(voor + sleutel, f"{naam} {j}", sym, eenheid, lambda v: v, "@v",
                              "De actieve ITM-units draaien op dezelfde verdeelde last.", v=bron)
        else:
            for sleutel, naam, sym, eenheid in (("last", "Last", "L", "%"), ("warmte", "Restwarmte", "Q", "kW"),
                                                ("AC", "Elektrisch vermogen", "P", "kW")):
                boek.stilstand(voor + sleutel, f"{naam} ITM-unit {j}", sym, eenheid, uitleg="Deze ITM-unit staat stil.")
    for sleutel, eenheid in DEBIETEENHEDEN:
        boek.stilstand("unit.uit." + sleutel, "Debiet van een stilstaande ITM-unit", r"\dot m" if sleutel.startswith("kg") else r"\dot V",
                       eenheid, uitleg="Deze ITM-unit staat stil.")


def balansen(boek, rijen, opstelling):
    ingaan, afvoer, backbone, rwzi = (rijen[id_]["waarden"]["kg_h"] for id_ in ("S1", "S3", "S12", "S18"))
    boek.afgeleid("massa.uit", "Uitstroom procesmassa", r"\sum \dot m_{uit}", "kg/h",
                  lambda afval, h2, o2: afval + h2 + o2, "@afval+@h2+@o2",
                  "De procesmassa verlaat de installatie via afvalwater, H₂-backbone en O₂ naar RWZI.",
                  afval=afvoer, h2=backbone, o2=rwzi)
    boek.afgeleid("massa.verschil", "Restverschil massabalans", r"\Delta\dot m", "kg/h",
                  lambda in_, uit: in_ - uit, "@in_-@uit",
                  "Vers UPW is de externe instroom. Condensaat, koelkring en recycle lopen intern. "
                  "Door afronding in de nominale ITM-invoergegevens blijft een klein verschil over.",
                  in_=ingaan, uit="massa.uit")
    return {
        "massa": [("Vers UPW in", ingaan), ("Processtromen uit", "massa.uit"), ("Verschil in − uit", "massa.verschil")],
        "warmte": ["Q_ITM_tot", "Q_E201", "Q_ind"]
        + (["Q_net", "Q_H2_TW", "W_K201", "COP"] if opstelling == "warmtenet" else [])
        + ["W_K202", "COP2", "Q_AK", "chk_p5"],
    }


def momentopname(i, opstelling, loads):
    """Één CoolProp-doorrekening en de passende toestanden voor het actieve blad."""
    valideer_invoer(i)
    n = sum(bool(load) for load in loads)
    boek = Rekenboek()
    invoerstappen(boek, i, n)
    r = None
    if n:
        tussen = {}
        r = coolprop(i, tussenstappen=tussen, alleen_actieve_cycli=True)
        valideer_resultaat(r)
        processtappen(boek, r, tussen)
        warmtestappen(boek, r, tussen)
    installatiecijfers(boek, r, loads)
    stromen = Stromen(boek, actief=n > 0)
    processtromen(stromen)
    warmte_stromen(stromen, i, r, opstelling)
    balans = balansen(boek, stromen.rijen, opstelling)
    blad = schema(opstelling)
    for apparaat in blad["apparaten"].values():
        for getal in apparaat["getallen"]:
            boek.getal(getal)
    for leiding in blad["leidingen"].values():
        if leiding["stroom"]:
            stromen.rijen[leiding["stroom"]]
    return r, dict(stromen=stromen.rijen, waarden=boek.waarden, balans=balans)

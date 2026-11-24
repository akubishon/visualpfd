"""
Massa- en energiebalans 8 x ITM Neptune V – naberekening met CoolProp.

Twee modellen naast elkaar:
  * excel()     : exact dezelfde formules als het rekenblad (Cengel, ideaal gas, constante cp)
  * coolprop()  : zelfde processchema, maar met echte stofeigenschappen uit CoolProp
                  (reëel H2/O2, stoomtabel via IAPWS, echte warmtepompcyclus met koudemiddel)

Gebruik:
    python itm_model.py                # vergelijkt beide modellen voor de basisinvoer
    python itm_model.py --tables out.json   # schrijft eigenschapstabellen voor de HTML-simulatie
"""
import json
import sys
from dataclasses import dataclass, asdict, field, replace

import CoolProp.CoolProp as CP

PS = CP.PropsSI
T0 = 273.15
PATM = 101.325  # kPa


@dataclass
class Invoer:
    # ITM (per unit)
    m_H2: float = 90.0          # kg/h
    P_H2_ITM: float = 30.0      # barg
    T_H2: float = 25.0          # °C
    m_O2mix: float = 925.0      # kg/h
    w_H2O: float = 0.15
    m_voedwater: float = 1431.0
    m_afvalwater: float = 412.0
    SEC_BOL: float = 55.9       # kWh/kg
    Q_ITM_EOL: float = 1750.0   # kW
    n_units: int = 8
    # bedrijfspunt
    belasting: float = 100.0    # % van nominaal
    m_min_pct: float = 40.0     # min. debiet K-101 in % van nominaal (turndown)
    m_recycle: float = 0.0      # wordt berekend door schaal()
    net_aan: bool = True        # warmtenet neemt warmte af
    wp_aan: bool = True         # warmtepomp WP-201 in bedrijf
    # O2-lijn
    T_O2_uit: float = 70.0
    P_O2_uit: float = 0.1
    T_KO: float = 30.0
    P_RWZI: float = 0.7
    eta_K102: float = 0.70
    # H2-lijn
    P_K101_uit: float = 70.0
    P_backbone: float = 66.2
    eta_K101: float = 0.75
    dT_pakket: float = 30.0
    T_E102_uit: float = 50.0
    T_E103_uit: float = 25.0
    # buffers
    P_V101_max: float = 29.0
    P_V101_min: float = 20.0
    t_V101: float = 0.5         # h
    t_V102: float = 30.0        # s
    n_V101: float = 1.2
    # water
    T_vers: float = 15.0
    P_ITM_voed: float = 5.0
    eta_P101: float = 0.5
    T_kw_in: float = 20.0
    T_kw_uit: float = 30.0
    # warmtenet
    T_kc_uit: float = 60.0
    T_kc_retour: float = 50.0
    cp_kc: float = 3.8
    T_net_aanvoer: float = 70.0
    T_net_retour: float = 40.0
    T_E201_uit: float = 55.0
    dT_min: float = 5.0
    eta_II: float = 0.5
    # alleen CoolProp-model
    koudemiddel: str = "R1234ze(E)"
    eta_K201: float = 0.70      # isentropisch rendement warmtepompcompressor
    # leidingdimensionering: maximale snelheden (m/s) en aannames
    v_max_H2: float = 20.0      # H2-gas (richtwaarde, EIGA Doc 121)
    v_max_O2: float = 15.0      # O2-rijk gas, droog/verzadigd (EIGA Doc 13, conservatief)
    v_max_nat: float = 10.0     # O2-gas met druppels (E-101 → V-103)
    v_max_pers: float = 2.0     # vloeistof, persleiding / gepompt circuit
    v_max_zuig: float = 1.0     # vloeistof, zuigleiding / vrij verval / afvoer
    v_max_ref_damp: float = 15.0  # koudemiddeldamp (zuig- en persleiding)
    v_max_ref_vl: float = 1.0   # koudemiddelvloeistof
    v_max_ref_2f: float = 8.0   # tweefase na smoorventiel
    rho_kc: float = 1040.0      # kg/m3, koelcircuit water + Coolflow (aanname)
    T_afvalwater: float = 30.0  # °C, aanname voor dichtheid S3



def schaal(i: Invoer) -> Invoer:
    """Deellast: ITM-stromen en restwarmte schalen lineair; onder het minimale
    compressordebiet gaat het tekort als recycle S9 rond via FV-101."""
    f = i.belasting / 100
    return replace(i, m_H2=i.m_H2 * f, m_O2mix=i.m_O2mix * f, m_voedwater=i.m_voedwater * f,
                   m_afvalwater=i.m_afvalwater * f, Q_ITM_EOL=i.Q_ITM_EOL * f,
                   m_recycle=max(0.0, i.m_H2 * i.m_min_pct / 100 - i.m_H2 * f), belasting=100.0)


def nabewerking(i: Invoer, r: dict) -> dict:
    """Grootheden die voor beide modellen hetzelfde worden afgeleid."""
    n = i.n_units
    r["Q_ITM_tot"] = n * i.Q_ITM_EOL
    r["Q_E102_tot"] = -r["Q_E102"] * n
    r["Q_adiabatisch"] = 0.0
    r["T_aanvoer"] = i.T_net_aanvoer
    if not i.net_aan:
        # geen afname: ITM-warmte via de eigen adiabatische koelers, E-102 via koelwater
        r.update(Q_E201=0.0, Q_L=0.0, Q_H=0.0, W_K201=0.0, Q_net=0.0, m_net_th=0.0,
                 Q_adiabatisch=r["Q_ITM_tot"], COP=float("nan"), T_aanvoer=float("nan"))
        r["Q_E102_tot"] = 0.0
    elif not i.wp_aan:
        # variant A (stap p7): alleen E-201, net maximaal tot T na E-201
        r.update(Q_E201=r["Q_ITM_tot"], Q_L=0.0, Q_H=0.0, W_K201=0.0, COP=float("nan"),
                 T_aanvoer=i.T_E201_uit)
        r["Q_net"] = r["Q_E201"] + r["Q_E102_tot"]
        r["m_net_th"] = r["Q_E201"] / (CENGEL["cp_w"] * (i.T_E201_uit - i.T_net_retour)) * 3.6
    r["m_kc"] = r["Q_ITM_tot"] / (i.cp_kc * (i.T_kc_uit - i.T_kc_retour))
    r["T_kc_tussen"] = i.T_kc_uit - r["Q_E201"] / (r["m_kc"] * i.cp_kc) if i.net_aan else i.T_kc_uit
    r["m_verschil"] = r["m_vers"] - (i.m_afvalwater + r["m_backbone"] + r["m_gas"])
    r["E_in"] = r["P_AC_EOL"] + r["W_K101"] + r["W_K102"]
    r["E_uit"] = (i.m_H2 * CENGEL["HHV_H2"] / 3600 + i.Q_ITM_EOL - r["Q_E101"] + r["Q_pak_K101"]
                  - r["Q_E102"] - r["Q_E103"] + r["Q_pak_K102"] + r["Q_O2_RWZI"])
    r["chk_E"] = r["E_in"] - r["E_uit"]
    r["chk_p5"] = r["Q_ITM_tot"] + r["Q_E102_tot"] + r["W_K201"] - r["Q_net"] - r["Q_adiabatisch"]
    r["i"] = i
    return r

# ---------------------------------------------------------------- Excel-model
CENGEL = dict(Mol_O2=31.999, Mol_H2O=18.015, cp_O2=0.918, cp_damp=1.8723, cp_H2=14.307,
              k_O2=1.395, k_H2=1.405, Psat_30=4.2469, Psat_65=25.043, Psat_70=31.202,
              hg_70=2626.1, hg_30=2555.6, hf_30=125.74, R_H2=4.124, B_H2=14.8,
              vf_30=0.001004, cp_w=4.18, HHV_H2=141800.0)


def excel(i: Invoer) -> dict:
    i = schaal(i)
    c = CENGEL
    r = {}
    m_S9 = i.m_recycle
    m_S5 = i.m_H2 + m_S9
    m_backbone = i.m_H2
    # a
    m_H2O_in = i.w_H2O * i.m_O2mix
    m_O2 = i.m_O2mix - m_H2O_in
    N_O2, N_H2O = m_O2 / c["Mol_O2"], m_H2O_in / c["Mol_H2O"]
    y_v = N_H2O / (N_O2 + N_H2O)
    P_O2_abs = i.P_O2_uit * 100 + PATM
    P_v = y_v * P_O2_abs
    T_dauw = 65 + (P_v - c["Psat_65"]) / (c["Psat_70"] - c["Psat_65"]) * 5
    # b
    y_v_max = c["Psat_30"] / P_O2_abs
    m_v = y_v_max / (1 - y_v_max) * N_O2 * c["Mol_H2O"]
    m_cond = m_H2O_in - m_v
    m_gas = m_O2 + m_v
    # c
    Q_E101 = m_O2 / 3600 * c["cp_O2"] * (i.T_KO - i.T_O2_uit) + \
        (m_v * c["hg_30"] + m_cond * c["hf_30"] - m_H2O_in * c["hg_70"]) / 3600
    # d
    cp_m = (m_O2 * c["cp_O2"] + m_v * c["cp_damp"]) / m_gas
    P_uit_K102 = i.P_RWZI * 100 + PATM
    T1 = i.T_KO + T0
    T2s = T1 * (P_uit_K102 / P_O2_abs) ** ((c["k_O2"] - 1) / c["k_O2"])
    T2 = T1 + (T2s - T1) / i.eta_K102
    mcp_O2 = m_gas / 3600 * cp_m
    W_K102 = mcp_O2 * (T2 - T1)
    T_S18 = T2 - T0 - i.dT_pakket
    Q_pak_K102 = mcp_O2 * i.dT_pakket
    Q_O2_RWZI = mcp_O2 * (T_S18 - i.T_KO)
    # e
    P_in_K101 = i.P_V101_min * 100 + PATM
    P_uit_K101 = i.P_K101_uit * 100 + PATM
    T1h = i.T_H2 + T0
    ex = (c["k_H2"] - 1) / c["k_H2"]
    T2sh = T1h * (P_uit_K101 / P_in_K101) ** ex
    T2h = T1h + (T2sh - T1h) / i.eta_K101
    mcp_H2 = m_S5 / 3600 * c["cp_H2"]
    W_K101 = mcp_H2 * (T2h - T1h)
    T_S6 = T2h - T0 - i.dT_pakket
    Q_pak_K101 = mcp_H2 * i.dT_pakket
    # g
    Q_E102 = mcp_H2 * (i.T_E102_uit - T_S6)
    Q_E103 = mcp_H2 * (i.T_E103_uit - i.T_E102_uit)
    # h (alleen eindvolumes)
    RT = c["R_H2"] * T1h
    RuT = 8.314 * T1h
    def vol(m, pmax, pmin, n):
        iso = m / (pmax / RT - pmin / RT)
        zmax, zmin = 1 + c["B_H2"] * 1e-6 * pmax * 1000 / RuT, 1 + c["B_H2"] * 1e-6 * pmin * 1000 / RuT
        fz = (m / (pmax / RT / zmax - pmin / RT / zmin)) / iso
        return m * n * RT / (pmax - pmin) * fz
    V_V101 = vol(i.m_H2 * i.t_V101, i.P_V101_max * 100 + PATM, P_in_K101, i.n_V101)
    V_V102 = vol(i.m_H2 * i.t_V102 / 3600, P_uit_K101, i.P_backbone * 100 + PATM, c["k_H2"])
    # i
    W_P101 = m_cond / 3600 * c["vf_30"] * (i.P_ITM_voed * 100 + PATM - P_O2_abs) / i.eta_P101
    # condensaat (UPW) gaat via P-101 direct terug de eigen unit in (S16); S1 vult alleen aan
    m_vers = i.m_voedwater - m_cond
    # j
    m_kw_E101 = -Q_E101 / (c["cp_w"] * (i.T_kw_uit - i.T_kw_in)) * 3600
    m_kw_E103 = -Q_E103 / (c["cp_w"] * (i.T_kw_uit - i.T_kw_in)) * 3600
    m_ww_E102 = -Q_E102 / (c["cp_w"] * (i.T_net_aanvoer - i.T_net_retour)) * 3600
    # l
    E_H2 = i.m_H2 * c["HHV_H2"] / 3600
    P_AC_BOL = i.SEC_BOL * i.m_H2
    Q_ITM_BOL = P_AC_BOL - E_H2 + Q_E101
    P_AC_EOL = E_H2 + i.Q_ITM_EOL - Q_E101
    # p warmtenet
    Q_ITM_tot = i.n_units * i.Q_ITM_EOL
    T_H = i.T_net_aanvoer + i.dT_min + T0
    T_L = i.T_kc_retour - i.dT_min + T0
    COP = i.eta_II * T_H / (T_H - T_L)
    f_L = 1 - 1 / COP
    r_E201 = (i.T_E201_uit - i.T_net_retour) / (i.T_net_aanvoer - i.T_E201_uit)
    Q_H = Q_ITM_tot / (r_E201 + f_L)
    Q_E201 = r_E201 * Q_H
    Q_L = f_L * Q_H
    W_K201 = Q_H - Q_L
    Q_net = Q_E201 + Q_H - Q_E102 * i.n_units
    m_net_th = Q_H / (c["cp_w"] * (i.T_net_aanvoer - i.T_E201_uit)) * 3.6
    T_uit_K102 = T2 - T0
    T_uit_K101 = T2h - T0
    r.update(locals())
    W_K101_s = mcp_H2 * (T2sh - T1h)
    COP_carnot = T_H / (T_H - T_L)
    r.update(locals())
    out = {k: v for k, v in r.items() if isinstance(v, (int, float)) and k not in ("c", "r", "i")}
    return nabewerking(i, out)


# ---------------------------------------------------------------- CoolProp-model
def coolprop(i: Invoer) -> dict:
    i = schaal(i)
    m_S9 = i.m_recycle
    m_S5 = i.m_H2 + m_S9
    m_backbone = i.m_H2
    M_O2 = PS("M", "Oxygen") * 1000
    M_H2O = PS("M", "Water") * 1000
    M_H2 = PS("M", "Hydrogen") * 1000
    P_O2_abs = (i.P_O2_uit * 100 + PATM) * 1e3     # Pa
    # a – samenstelling / dauwpunt
    m_H2O_in = i.w_H2O * i.m_O2mix
    m_O2 = i.m_O2mix - m_H2O_in
    N_O2, N_H2O = m_O2 / M_O2, m_H2O_in / M_H2O
    y_v = N_H2O / (N_O2 + N_H2O)
    P_v = y_v * P_O2_abs
    T_dauw = PS("T", "P", P_v, "Q", 1, "Water") - T0
    # b – KO-drum
    Psat_KO = PS("P", "T", i.T_KO + T0, "Q", 0, "Water")
    y_v_max = Psat_KO / P_O2_abs
    m_v = y_v_max / (1 - y_v_max) * N_O2 * M_H2O
    m_cond = m_H2O_in - m_v
    m_gas = m_O2 + m_v

    # damp als ideaal gas: enthalpie bij zeer lage druk (≈ ideaal-gasdeel)
    def h_vap(T):  # J/kg, superheated vapour at 0.5 kPa
        return PS("H", "T", T + T0, "P", 500.0, "Water")

    def s_vap(T, p):  # entropie ideaal-gas-damp bij partiële druk p
        R = 8.314462618 / (M_H2O / 1000)
        return PS("S", "T", T + T0, "P", 500.0, "Water") - R * __import__("math").log(p / 500.0)

    # c – voorkoeler E-101 (O2 reëel bij partiële druk; water: damp → damp + vloeistof)
    pO2_in = (1 - y_v) * P_O2_abs
    pO2_ko = (1 - y_v_max) * P_O2_abs
    Q_c_O2 = m_O2 / 3600 * (PS("H", "T", i.T_KO + T0, "P", pO2_ko, "Oxygen") -
                            PS("H", "T", i.T_O2_uit + T0, "P", pO2_in, "Oxygen")) / 1e3
    h_f_KO = PS("H", "T", i.T_KO + T0, "Q", 0, "Water")
    Q_c_w = (m_v * h_vap(i.T_KO) + m_cond * h_f_KO - m_H2O_in * h_vap(i.T_O2_uit)) / 3600 / 1e3
    Q_E101 = Q_c_O2 + Q_c_w

    # d – K-102: ideaal mengsel O2 + damp, isentroop via entropie bij partiële drukken
    P_uit_K102 = (i.P_RWZI * 100 + PATM) * 1e3
    pO2_2, pv_2 = (1 - y_v_max) * P_uit_K102, y_v_max * P_uit_K102
    pv_1 = y_v_max * P_O2_abs

    def h_mix(T, pO2):
        return (m_O2 * PS("H", "T", T + T0, "P", pO2, "Oxygen") + m_v * h_vap(T)) / m_gas

    def s_mix(T, pO2, pv):
        return (m_O2 * PS("S", "T", T + T0, "P", pO2, "Oxygen") + m_v * s_vap(T, pv)) / m_gas

    s1 = s_mix(i.T_KO, pO2_ko, pv_1)
    h1 = h_mix(i.T_KO, pO2_ko)
    T2s = bisect(lambda T: s_mix(T, pO2_2, pv_2) - s1, i.T_KO, 400)
    h2s = h_mix(T2s, pO2_2)
    h2 = h1 + (h2s - h1) / i.eta_K102
    T_uit_K102 = bisect(lambda T: h_mix(T, pO2_2) - h2, i.T_KO, 500)
    W_K102 = m_gas / 3600 * (h2 - h1) / 1e3
    T_S18 = T_uit_K102 - i.dT_pakket
    Q_pak_K102 = m_gas / 3600 * (h2 - h_mix(T_S18, pO2_2)) / 1e3
    Q_O2_RWZI = W_K102 - Q_pak_K102
    T_dauw_S18 = PS("T", "P", pv_2, "Q", 1, "Water") - T0

    # e – K-101 H2 reëel
    H2 = "Hydrogen"
    P_in_K101 = (i.P_V101_min * 100 + PATM) * 1e3
    P_uit_K101 = (i.P_K101_uit * 100 + PATM) * 1e3
    T1 = i.T_H2 + T0
    h1h = PS("H", "T", T1, "P", P_in_K101, H2)
    s1h = PS("S", "T", T1, "P", P_in_K101, H2)
    h2sh = PS("H", "S", s1h, "P", P_uit_K101, H2)
    T2sh = PS("T", "S", s1h, "P", P_uit_K101, H2)
    h2h = h1h + (h2sh - h1h) / i.eta_K101
    T_uit_K101 = PS("T", "H", h2h, "P", P_uit_K101, H2) - T0
    W_K101 = m_S5 / 3600 * (h2h - h1h) / 1e3
    W_K101_s = m_S5 / 3600 * (h2sh - h1h) / 1e3
    T_S6 = T_uit_K101 - i.dT_pakket
    hH = lambda T: PS("H", "T", T + T0, "P", P_uit_K101, H2)
    Q_pak_K101 = m_S5 / 3600 * (h2h - hH(T_S6)) / 1e3
    Q_E102 = m_S5 / 3600 * (hH(i.T_E102_uit) - hH(T_S6)) / 1e3
    Q_E103 = m_S5 / 3600 * (hH(i.T_E103_uit) - hH(i.T_E102_uit)) / 1e3

    # h – buffervolumes met echte dichtheid (isotherm × n, zoals h4c)
    def rho(P):
        return PS("D", "T", T1, "P", P, H2)
    P_V101_max = (i.P_V101_max * 100 + PATM) * 1e3
    P_V102_min = (i.P_backbone * 100 + PATM) * 1e3
    V_V101_iso = i.m_H2 * i.t_V101 / (rho(P_V101_max) - rho(P_in_K101))
    V_V102_iso = i.m_H2 * i.t_V102 / 3600 / (rho(P_uit_K101) - rho(P_V102_min))
    k_H2 = PS("CPMASS", "T", T1, "P", 101325, H2) / PS("CVMASS", "T", T1, "P", 101325, H2)
    V_V101 = V_V101_iso * i.n_V101
    V_V102 = V_V102_iso * k_H2
    Z_V102_max = PS("Z", "T", T1, "P", P_uit_K101, H2)

    # i – condensaatpomp
    v_f = 1 / PS("D", "T", i.T_KO + T0, "Q", 0, "Water")
    W_P101 = m_cond / 3600 * v_f * ((i.P_ITM_voed * 100 + PATM) * 1e3 - P_O2_abs) / 1e3 / i.eta_P101
    # condensaat (UPW) gaat via P-101 direct terug de eigen unit in (S16); S1 vult alleen aan
    m_vers = i.m_voedwater - m_cond

    # j – koelwater (cp water uit CoolProp)
    cp_w = (PS("H", "T", i.T_kw_uit + T0, "P", 3e5, "Water") - PS("H", "T", i.T_kw_in + T0, "P", 3e5, "Water")) / 1e3
    m_kw_E101 = -Q_E101 / cp_w * 3600
    m_kw_E103 = -Q_E103 / cp_w * 3600
    dh_net = (PS("H", "T", i.T_net_aanvoer + T0, "P", 6e5, "Water") - PS("H", "T", i.T_net_retour + T0, "P", 6e5, "Water")) / 1e3
    m_ww_E102 = -Q_E102 / dh_net * 3600

    # l – energiebalans ITM (HHV uit Cengel; CoolProp heeft geen verbrandingswaarde)
    E_H2 = i.m_H2 * CENGEL["HHV_H2"] / 3600
    P_AC_BOL = i.SEC_BOL * i.m_H2
    Q_ITM_BOL = P_AC_BOL - E_H2 + Q_E101
    P_AC_EOL = E_H2 + i.Q_ITM_EOL - Q_E101

    # p – warmtepomp als echte dampcompressiecyclus
    hp = warmtepomp(i.koudemiddel, i.T_kc_retour - i.dT_min, i.T_net_aanvoer + i.dT_min, i.eta_K201)
    COP = hp["COP"]
    f_L = 1 - 1 / COP
    Q_ITM_tot = i.n_units * i.Q_ITM_EOL
    hw = lambda T: PS("H", "T", T + T0, "P", 6e5, "Water")
    r_E201 = (hw(i.T_E201_uit) - hw(i.T_net_retour)) / (hw(i.T_net_aanvoer) - hw(i.T_E201_uit))
    Q_H = Q_ITM_tot / (r_E201 + f_L)
    Q_E201 = r_E201 * Q_H
    Q_L = f_L * Q_H
    W_K201 = Q_H - Q_L
    Q_net = Q_E201 + Q_H - Q_E102 * i.n_units
    m_net_th = Q_H / ((hw(i.T_net_aanvoer) - hw(i.T_E201_uit)) / 1e3) * 3.6

    out = {k: v for k, v in locals().items() if isinstance(v, (int, float))}
    out["cyclus"] = hp
    out["COP_carnot"] = hp["COP_carnot"]
    return nabewerking(i, out)


def warmtepomp(fluid, T_evap, T_cond, eta):
    """Eenvoudige cyclus: verzadigde damp in compressor, verzadigde vloeistof uit condensor."""
    Te, Tc = T_evap + T0, T_cond + T0
    Pe, Pc = PS("P", "T", Te, "Q", 1, fluid), PS("P", "T", Tc, "Q", 0, fluid)
    h1, s1 = PS("H", "T", Te, "Q", 1, fluid), PS("S", "T", Te, "Q", 1, fluid)
    h2s = PS("H", "P", Pc, "S", s1, fluid)
    h2 = h1 + (h2s - h1) / eta
    T2 = PS("T", "P", Pc, "H", h2, fluid) - T0
    h3 = PS("H", "T", Tc, "Q", 0, fluid)
    h4 = h3
    x4 = PS("Q", "P", Pe, "H", h4, fluid)
    COP = (h2 - h3) / (h2 - h1)
    return dict(fluid=fluid, T_evap=T_evap, T_cond=T_cond, P_evap_bar=Pe / 1e5, P_cond_bar=Pc / 1e5,
                T_pers=T2, h1=h1 / 1e3, h2=h2 / 1e3, h3=h3 / 1e3, x4=x4, COP=COP,
                COP_carnot=Tc / (Tc - Te))


def bisect(f, a, b, tol=1e-6):
    fa = f(a)
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = f(m)
        if fa * fm <= 0:
            b = m
        else:
            a, fa = m, fm
        if b - a < tol:
            break
    return 0.5 * (a + b)


# ---------------------------------------------------------------- leidingdimensionering
# Roestvaststalen pijp ASME B36.19 schedule 40S: (DN, buitendiameter mm, wanddikte mm)
DN_40S = [(15, 21.3, 2.77), (20, 26.7, 2.87), (25, 33.4, 3.38), (32, 42.2, 3.56), (40, 48.3, 3.68),
          (50, 60.3, 3.91), (65, 73.0, 5.16), (80, 88.9, 5.49), (100, 114.3, 6.02), (125, 141.3, 6.55),
          (150, 168.3, 7.11), (200, 219.1, 8.18), (250, 273.0, 9.27), (300, 323.8, 9.53), (350, 355.6, 9.53),
          (400, 406.4, 9.53), (450, 457.0, 9.53), (500, 508.0, 9.53), (600, 610.0, 9.53), (700, 711.0, 9.53),
          (800, 813.0, 9.53)]


def kies_dn(d_min_mm):
    """Kleinste standaardmaat (40S) met binnendiameter ≥ d_min."""
    for dn, od, wd in DN_40S:
        if od - 2 * wd >= d_min_mm:
            return dn, od - 2 * wd
    return None, float("nan")


def ontwerppunt(i: Invoer) -> Invoer:
    """Dimensioneren op vollast met warmtenet en warmtepomp in bedrijf."""
    return replace(i, belasting=100.0, net_aan=True, wp_aan=True)


def leidingen(i: Invoer = None) -> list:
    """Minimale binnendiameter per leiding: d_min = √(4·V̇ / (π·v_max)), V̇ = ṁ/ρ.
    Ontwerppunt = vollast (S9: maximale recycle), stofeigenschappen uit CoolProp."""
    import math
    i = i or Invoer()
    d = ontwerppunt(i)
    r = coolprop(d)
    n = d.n_units
    bar = lambda barg: (barg * 100 + PATM) * 1e3          # barg → Pa abs
    w = lambda T, p=6e5: PS("D", "T", T + T0, "P", p, "Water")
    h2 = lambda T, barg: PS("D", "T", T + T0, "P", bar(barg), "Hydrogen")
    Ru = 8.314462618
    M_O2, M_W = PS("M", "Oxygen"), PS("M", "Water")

    def gas_o2(T, barg, m_O2, m_v):                     # ideaal mengsel O2 + damp
        N = m_O2 / M_O2 + m_v / M_W
        return bar(barg) * (m_O2 + m_v) / N / (Ru * (T + T0))

    # koudemiddel WP-201
    cy = r["cyclus"]
    f = cy["fluid"]
    Te, Tc = cy["T_evap"] + T0, cy["T_cond"] + T0
    m_ref = r["Q_H"] / (cy["h2"] - cy["h3"]) * 3600       # kg/h
    rho_R1 = PS("D", "T", Te, "Q", 1, f)
    rho_R2 = PS("D", "P", cy["P_cond_bar"] * 1e5, "H", cy["h2"] * 1e3, f)
    rho_R3 = PS("D", "T", Tc, "Q", 0, f)
    rho_R4 = PS("D", "P", cy["P_evap_bar"] * 1e5, "H", cy["h3"] * 1e3, f)

    kc = r["m_kc"] * 3600                                 # kg/h, alle units
    net = r["m_net_th"] * 1000                            # kg/h
    m_S9_max = d.m_H2 * d.m_min_pct / 100
    v = dict(H2=d.v_max_H2, O2=d.v_max_O2, nat=d.v_max_nat, pers=d.v_max_pers, zuig=d.v_max_zuig,
             rd=d.v_max_ref_damp, rv=d.v_max_ref_vl, r2=d.v_max_ref_2f)
    U, A = "per unit", "installatie"
    # id, omschrijving, medium, schaal, ṁ kg/h, ρ kg/m³, v_max-categorie, T °C, p barg
    L = [
        ("S1", "Vers UPW-suppletie → ITM", "water", U, r["m_vers"], w(d.T_vers), "pers", d.T_vers, d.P_ITM_voed),
        ("S3", "ITM → afvalwater", "water", U, d.m_afvalwater, w(d.T_afvalwater, 2e5), "zuig", d.T_afvalwater, None),
        ("S4", "ITM → V-101", "H₂", U, d.m_H2, h2(d.T_H2, d.P_H2_ITM), "H2", d.T_H2, d.P_H2_ITM),
        ("S5", "V-101 → K-101 (zuig)", "H₂", U, r["m_S5"], h2(d.T_H2, d.P_V101_min), "H2", d.T_H2, d.P_V101_min),
        ("S6", "K-101 → E-102", "H₂", U, r["m_S5"], h2(r["T_S6"], d.P_K101_uit), "H2", r["T_S6"], d.P_K101_uit),
        ("S7", "E-102 → E-103", "H₂", U, r["m_S5"], h2(d.T_E102_uit, d.P_K101_uit), "H2", d.T_E102_uit, d.P_K101_uit),
        ("S8", "E-103 → kwaliteitscontrole", "H₂", U, r["m_S5"], h2(d.T_E103_uit, d.P_K101_uit), "H2", d.T_E103_uit, d.P_K101_uit),
        ("S9", "Recycle FV-101 → V-101 (max.)", "H₂", U, m_S9_max, h2(d.T_E103_uit, d.P_V101_min), "H2", d.T_E103_uit, d.P_V101_min),
        ("S11", "Kwaliteitscontrole → V-102", "H₂", U, r["m_backbone"], h2(d.T_E103_uit, d.P_backbone), "H2", d.T_E103_uit, d.P_backbone),
        ("S12", "PCV-101 → H₂-backbone", "H₂", U, r["m_backbone"], h2(d.T_E103_uit, d.P_backbone), "H2", d.T_E103_uit, d.P_backbone),
        ("S13", "ITM → E-101", "O₂ + damp", U, d.m_O2mix, gas_o2(d.T_O2_uit, d.P_O2_uit, r["m_O2"], r["m_H2O_in"]), "O2", d.T_O2_uit, d.P_O2_uit),
        ("S14", "E-101 → V-103 (met druppels)", "O₂ + damp + water", U, d.m_O2mix,
         d.m_O2mix / ((r["m_O2"] + r["m_v"]) / gas_o2(d.T_KO, d.P_O2_uit, r["m_O2"], r["m_v"]) + r["m_cond"] / w(d.T_KO, 2e5)),
         "nat", d.T_KO, d.P_O2_uit),
        ("S15", "V-103 → P-101 (zuig)", "condensaat (UPW)", U, r["m_cond"], w(d.T_KO, 2e5), "zuig", d.T_KO, d.P_O2_uit),
        ("S16", "P-101 → ITM (condensaat direct)", "condensaat (UPW)", U, r["m_cond"], w(d.T_KO), "pers", d.T_KO, d.P_ITM_voed),
        ("S17", "V-103 → K-102", "O₂ + damp", U, r["m_gas"], gas_o2(d.T_KO, d.P_O2_uit, r["m_O2"], r["m_v"]), "O2", d.T_KO, d.P_O2_uit),
        ("S18", "K-102 → RWZI", "O₂ + damp", U, r["m_gas"], gas_o2(r["T_S18"], d.P_RWZI, r["m_O2"], r["m_v"]), "O2", r["T_S18"], d.P_RWZI),
        ("A", "Koelcircuit uit ITM (aftakking)", "water + Coolflow", U, kc / n, d.rho_kc, "pers", d.T_kc_uit, None),
        ("A-h", "Koelcircuit verzamelleiding → E-201", "water + Coolflow", A, kc, d.rho_kc, "pers", d.T_kc_uit, None),
        ("A2", "Koelcircuit E-201 → E-202", "water + Coolflow", A, kc, d.rho_kc, "pers", r["T_kc_tussen"], None),
        ("B-h", "Koelcircuit retour verzamelleiding", "water + Coolflow", A, kc, d.rho_kc, "pers", d.T_kc_retour, None),
        ("B", "Koelcircuit retour naar ITM (aftakking)", "water + Coolflow", U, kc / n, d.rho_kc, "pers", d.T_kc_retour, None),
        ("KW1", "Koelwater E-101", "koelwater", U, r["m_kw_E101"], w((d.T_kw_in + d.T_kw_uit) / 2, 3e5), "pers", d.T_kw_in, None),
        ("KW2", "Koelwater E-103", "koelwater", U, r["m_kw_E103"], w((d.T_kw_in + d.T_kw_uit) / 2, 3e5), "pers", d.T_kw_in, None),
        ("WW1", "Warmtenet-zijstroom E-102", "netwater", U, r["m_ww_E102"], w((d.T_net_retour + d.T_net_aanvoer) / 2), "pers", d.T_net_retour, None),
        ("N1", "Warmtenet retour → E-201", "netwater", A, net, w(d.T_net_retour), "pers", d.T_net_retour, None),
        ("N2", "Warmtenet E-201 → E-203", "netwater", A, net, w(d.T_E201_uit), "pers", d.T_E201_uit, None),
        ("N3", "Warmtenet aanvoer (incl. zijstroom E-102)", "netwater", A, net + n * r["m_ww_E102"], w(d.T_net_aanvoer), "pers", d.T_net_aanvoer, None),
        ("R1", "E-202 → K-201 (zuigdamp)", f, A, m_ref, rho_R1, "rd", cy["T_evap"], cy["P_evap_bar"] - 1.01325),
        ("R2", "K-201 → E-203 (persdamp)", f, A, m_ref, rho_R2, "rd", cy["T_pers"], cy["P_cond_bar"] - 1.01325),
        ("R3", "E-203 → TV-201 (vloeistof)", f, A, m_ref, rho_R3, "rv", cy["T_cond"], cy["P_cond_bar"] - 1.01325),
        ("R4", "TV-201 → E-202 (tweefase)", f, A, m_ref, rho_R4, "r2", cy["T_evap"], cy["P_evap_bar"] - 1.01325),
    ]
    uit = []
    for sid, naam, med, sch, m, rho, cat, T, p in L:
        V = m / rho / 3600                                # m³/s
        dmin = math.sqrt(4 * V / (math.pi * v[cat])) * 1000 if V > 0 else 0.0
        dn, di = kies_dn(dmin)
        vw = V / (math.pi / 4 * (di / 1000) ** 2) if dn else float("nan")
        uit.append(dict(id=sid, naam=naam, medium=med, schaal=sch, m=m, rho=rho, V=V * 3600, v_max=v[cat], cat=cat,
                        d_min=dmin, DN=dn, d_i=di, v=vw, T=T, p=p))
    return uit


# ---------------------------------------------------------------- vergelijking
VERGELIJK = [
    ("T_dauw", "Dauwpunt O₂-stroom", "°C"),
    ("m_v", "Damp mee met O₂ (S17)", "kg/h"),
    ("m_cond", "Condensaat (S15)", "kg/h"),
    ("Q_E101", "Voorkoeler E-101", "kW"),
    ("T_uit_K102", "T uit K-102", "°C"),
    ("W_K102", "Vermogen K-102 (E4)", "kW"),
    ("T_uit_K101", "T uit K-101", "°C"),
    ("W_K101", "Vermogen K-101 (E3)", "kW"),
    ("Q_pak_K101", "Pakketkoeler K-101", "kW"),
    ("Q_E102", "E-102 terugwinning", "kW"),
    ("Q_E103", "E-103 eindkoeler", "kW"),
    ("V_V101", "Volume V-101", "m³"),
    ("V_V102", "Volume V-102", "m³"),
    ("W_P101", "Pomp P-101 (E5)", "kW"),
    ("P_AC_EOL", "Stroom ITM EOL", "kW"),
    ("COP", "COP warmtepomp", "–"),
    ("Q_E201", "E-201 (8 units)", "kW"),
    ("Q_H", "Condensor E-203", "kW"),
    ("W_K201", "K-201 (E6)", "kW"),
    ("Q_net", "Totaal naar warmtenet", "kW"),
]


def vergelijk(i: Invoer = None):
    i = i or Invoer()
    e, c = excel(i), coolprop(i)
    print(f"{'Grootheid':32s}{'Excel':>11s}{'CoolProp':>11s}{'Δ %':>8s}  eenheid")
    for k, naam, u in VERGELIJK:
        a, b = e[k], c[k]
        d = (b - a) / abs(a) * 100 if a else 0
        print(f"{naam:32s}{a:11.2f}{b:11.2f}{d:8.1f}  {u}")
    hp = c["cyclus"]
    print(f"\nWarmtepomp {hp['fluid']}: {hp['P_evap_bar']:.1f} → {hp['P_cond_bar']:.1f} bar, "
          f"perstemperatuur {hp['T_pers']:.1f} °C, COP {hp['COP']:.2f} (Carnot {hp['COP_carnot']:.2f})")
    return e, c


# ---------------------------------------------------------------- tabellen voor de browser
def tabellen():
    """Eigenschapstabellen (CoolProp) voor interpolatie in de HTML-simulatie."""
    import numpy as np
    t = {}
    # H2: h, s, rho op (T, P)-raster
    Ts = list(np.arange(250, 720.1, 5.0))
    Ps = [float(p) for p in np.concatenate([np.arange(1, 10, 1), np.arange(10, 120.1, 2.5)])]
    for prop in ("H", "S", "D"):
        t["H2_" + prop] = [[float(f"{PS(prop, 'T', T, 'P', P * 1e5, 'Hydrogen'):.7g}") for P in Ps] for T in Ts]
    t["H2_T"], t["H2_P"] = Ts, Ps
    # O2: h, s op (T, P) bij lage druk
    To = list(np.arange(260, 480.1, 5.0))
    Po = [float(p) for p in np.arange(0.4, 2.61, 0.2)]
    for prop in ("H", "S"):
        t["O2_" + prop] = [[float(f"{PS(prop, 'T', T, 'P', P * 1e5, 'Oxygen'):.7g}") for P in Po] for T in To]
    t["O2_T"], t["O2_P"] = To, Po
    # Water: verzadiging en damp (ideaal-gas-deel)
    Tw = list(np.arange(1, 150.1, 1.0))
    t["W_T"] = Tw
    t["W_Psat"] = [PS("P", "T", T + T0, "Q", 0, "Water") for T in Tw]
    t["W_hf"] = [PS("H", "T", T + T0, "Q", 0, "Water") for T in Tw]
    t["W_hv"] = [PS("H", "T", T + T0, "P", 500.0, "Water") for T in Tw]
    t["W_sv"] = [PS("S", "T", T + T0, "P", 500.0, "Water") for T in Tw]
    t["W_vf"] = [1 / PS("D", "T", T + T0, "Q", 0, "Water") for T in Tw]
    t["W_hl"] = [PS("H", "T", T + T0, "P", 6e5, "Water") for T in Tw]  # vloeistof 5 barg
    # Warmtepompcycli: per koudemiddel op raster (T_evap, T_cond)
    Te = list(np.arange(20, 60.1, 1.0))
    Tc = list(np.arange(50, 95.1, 1.0))
    t["HP_Te"], t["HP_Tc"] = Te, Tc
    t["HP"] = {}
    for f in ("R1234ze(E)", "R600a", "Ammonia"):
        rows = {"h1": [], "h2s": [], "h3": [], "Pe": [], "Pc": [],
                "hl_e": [], "Dv_e": [], "Dl_e": [], "Dl_c": [], "D2s": [], "T2s": [], "cp2s": []}
        for te in Te:
            h1 = PS("H", "T", te + T0, "Q", 1, f)
            s1 = PS("S", "T", te + T0, "Q", 1, f)
            rows["h1"].append(h1 / 1e3)
            rows["Pe"].append(PS("P", "T", te + T0, "Q", 1, f) / 1e5)
            rows["hl_e"].append(round(PS("H", "T", te + T0, "Q", 0, f) / 1e3, 3))
            rows["Dv_e"].append(round(PS("D", "T", te + T0, "Q", 1, f), 4))
            rows["Dl_e"].append(round(PS("D", "T", te + T0, "Q", 0, f), 3))
            r2, d2, t2, c2 = [], [], [], []
            for tc in Tc:
                Pc = PS("P", "T", tc + T0, "Q", 0, f)
                r2.append(PS("H", "P", Pc, "S", s1, f) / 1e3)
                d2.append(round(PS("D", "P", Pc, "S", s1, f), 4))
                t2.append(round(PS("T", "P", Pc, "S", s1, f) - T0, 3))
                c2.append(round(PS("CPMASS", "P", Pc, "S", s1, f) / 1e3, 5))
            rows["h2s"].append(r2)
            rows["D2s"].append(d2)
            rows["T2s"].append(t2)
            rows["cp2s"].append(c2)
        for tc in Tc:
            rows["h3"].append(PS("H", "T", tc + T0, "Q", 0, f) / 1e3)
            rows["Pc"].append(PS("P", "T", tc + T0, "Q", 0, f) / 1e5)
            rows["Dl_c"].append(round(PS("D", "T", tc + T0, "Q", 0, f), 3))
        dome = []
        Tcrit = PS("Tcrit", f)
        for T in np.linspace(250, Tcrit - 0.5, 60):
            dome.append([round(PS("P", "T", T, "Q", 0, f) / 1e5, 4),
                         round(PS("H", "T", T, "Q", 0, f) / 1e3, 2),
                         round(PS("H", "T", T, "Q", 1, f) / 1e3, 2)])
        rows["dome"] = dome
        t["HP"][f] = rows
    t["M"] = {"O2": PS("M", "Oxygen") * 1000, "H2O": PS("M", "Water") * 1000, "H2": PS("M", "Hydrogen") * 1000}
    t["k_H2"] = PS("CPMASS", "T", 298.15, "P", 101325, "Hydrogen") / PS("CVMASS", "T", 298.15, "P", 101325, "Hydrogen")
    for k in list(t):
        if k.startswith("W_"):
            t[k] = [float(f"{v:.7g}") for v in t[k]]
    t["bron"] = "CoolProp " + CP.get_global_param_string("version")
    return t


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--tables":
        with open(sys.argv[2], "w") as fh:
            json.dump(tabellen(), fh, separators=(",", ":"))
        print("geschreven:", sys.argv[2])
    else:
        e, c = vergelijk()
        if len(sys.argv) > 1 and sys.argv[1] == "--json":
            print(json.dumps({"excel": e, "coolprop": {k: v for k, v in c.items()}}, default=str))

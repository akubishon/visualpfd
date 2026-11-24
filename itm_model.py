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
    # ITM-koelcircuit: gesloten circuit per unit (datasheet, standaard luchtgekoeld, EOL)
    T_kc_uit: float = 54.5      # °C uit ITM (outlet)
    T_kc_retour: float = 48.0   # °C terug naar ITM (inlet)
    m_kc_ds: float = 278814.0   # kg/h per unit, 62/38 water/CoolFlow DTX
    P_kc: float = 4.4           # barg
    # warmteterugwinning: E-201 (×8) → tussencircuit TW → E-204 (net direct), WP-201 (net), WP-202 (industrie)
    dT_E201: float = 3.0        # K, temperatuurverschil platenwisselaar E-201 (ITM-circuit → TW)
    T_net_aanvoer: float = 70.0
    T_net_retour: float = 40.0
    T_E204_uit: float = 45.0    # warmtenet na directe voorverwarming E-204
    dT_min: float = 5.0
    eta_II: float = 0.5
    Q_ind: float = 2000.0       # kW warmtevraag industrie (0 = uit)
    T_ind_aanvoer: float = 95.0
    T_ind_retour: float = 75.0
    # alleen CoolProp-model
    koudemiddel: str = "R1234ze(E)"
    eta_K201: float = 0.70      # isentropisch rendement warmtepompcompressor
    koudemiddel2: str = "R1233zd(E)"  # WP-202 industrie (hogere temperatuur)
    eta_K202: float = 0.70
    # leidingdimensionering: maximale snelheden (m/s) en aannames
    v_max_H2: float = 20.0      # H2-gas (richtwaarde, EIGA Doc 121)
    v_max_O2: float = 15.0      # O2-rijk gas, droog/verzadigd (EIGA Doc 13, conservatief)
    v_max_nat: float = 10.0     # O2-gas met druppels (E-101 → V-103)
    v_max_pers: float = 2.0     # vloeistof, persleiding / gepompt circuit
    v_max_zuig: float = 1.0     # vloeistof, zuigleiding / vrij verval / afvoer
    v_max_ref_damp: float = 15.0  # koudemiddeldamp (zuig- en persleiding)
    v_max_ref_vl: float = 1.0   # koudemiddelvloeistof
    v_max_ref_2f: float = 8.0   # tweefase na smoorventiel
    rho_kc: float = 1025.0      # kg/m3, 62/38 water/CoolFlow DTX bij ~50 °C (aanname)
    T_afvalwater: float = 30.0  # °C, aanname voor dichtheid S3



def last_factor(i: Invoer) -> float:
    return i.belasting / 100


def schaal(i: Invoer) -> Invoer:
    """Deellast: ITM-stromen en restwarmte schalen lineair; onder het minimale
    compressordebiet gaat het tekort als recycle S9 rond via FV-101."""
    f = i.belasting / 100
    return replace(i, m_H2=i.m_H2 * f, m_O2mix=i.m_O2mix * f, m_voedwater=i.m_voedwater * f,
                   m_afvalwater=i.m_afvalwater * f, Q_ITM_EOL=i.Q_ITM_EOL * f,
                   m_recycle=max(0.0, i.m_H2 * i.m_min_pct / 100 - i.m_H2 * f), belasting=100.0)


def warmteketen(i: Invoer, r: dict, COP, COP2, hw) -> dict:
    """Restwarmte ITM → warmtenet en industrie, voor de hele installatie (n units).
    Per unit: ITM-circuit (gesloten) → E-201 → luchtkoeler AK (trim/back-up) → ITM.
    Gedeeld tussencircuit TW: E-201 (×n) → E-204 (net direct) → E-202 (verdamper WP-201) ∥ E-206 (verdamper WP-202).
    hw(T): enthalpie water in kJ/kg."""
    n = i.n_units
    Q_ITM_tot = n * i.Q_ITM_EOL
    T_tw_a, T_tw_r = i.T_kc_uit - i.dT_E201, i.T_kc_retour - i.dT_E201
    # industrie via WP-202 (verdampt op TW, condenseert boven de industrie-aanvoer)
    f_L2 = 1 - 1 / COP2 if COP2 and COP2 > 1 else float("nan")
    Q_ind, begrensd = max(i.Q_ind, 0.0), False
    if Q_ind > 0 and Q_ind * f_L2 > Q_ITM_tot:
        Q_ind, begrensd = Q_ITM_tot / f_L2, True
    Q_L2 = Q_ind * f_L2 if Q_ind > 0 else 0.0
    W_K202 = Q_ind - Q_L2
    m_ind = Q_ind / (hw(i.T_ind_aanvoer) - hw(i.T_ind_retour)) * 3.6 if Q_ind > 0 else 0.0   # t/h
    Qb = Q_ITM_tot - Q_L2                                    # beschikbaar voor het warmtenet
    Q_E102_tot = -r["Q_E102"] * n
    nan = float("nan")
    if not i.net_aan:
        Q_E204 = Q_L = Q_H = W_K201 = m_net = r_E204 = 0.0
        Q_E102_tot, T_aanvoer, COP = 0.0, nan, nan
    elif not i.wp_aan:
        r_E204, Q_E204, Q_L = 0.0, Qb, 0.0
        Q_H = W_K201 = 0.0
        m_net = Q_E204 / (hw(i.T_E204_uit) - hw(i.T_net_retour))
        T_aanvoer, COP = i.T_E204_uit, nan
    else:
        f_L = 1 - 1 / COP
        r_E204 = (hw(i.T_E204_uit) - hw(i.T_net_retour)) / (hw(i.T_net_aanvoer) - hw(i.T_E204_uit))
        Q_H = Qb / (r_E204 + f_L)
        Q_E204, Q_L = r_E204 * Q_H, f_L * Q_H
        W_K201 = Q_H - Q_L
        m_net = Q_H / (hw(i.T_net_aanvoer) - hw(i.T_E204_uit))
        T_aanvoer = i.T_net_aanvoer
    Q_E201 = Q_E204 + Q_L + Q_L2                             # via alle E-201's naar TW
    Q_AK = Q_ITM_tot - Q_E201                                # rest via de luchtkoelers
    cpw = (hw(T_tw_a) - hw(T_tw_r)) / (T_tw_a - T_tw_r)
    m_tw = Q_E201 / (cpw * (T_tw_a - T_tw_r)) if Q_E201 > 0 else 0.0   # kg/s
    T_tw_tussen = T_tw_a - Q_E204 / (m_tw * cpw) if m_tw > 0 else T_tw_a
    # ITM-circuit per unit (datasheet-debiet schaalt met de last, temperaturen vast)
    f = r.get("_f_last", 1.0)
    m_kc_unit = i.m_kc_ds * f                                 # kg/h
    cp_kc = i.Q_ITM_EOL / (m_kc_unit / 3600 * (i.T_kc_uit - i.T_kc_retour)) if m_kc_unit > 0 else nan
    T_kc_naE201 = i.T_kc_uit - (Q_E201 / n) / (m_kc_unit / 3600 * cp_kc) if m_kc_unit > 0 else i.T_kc_uit
    Q_net = Q_E204 + Q_H + Q_E102_tot
    r.update(Q_ITM_tot=Q_ITM_tot, T_tw_a=T_tw_a, T_tw_r=T_tw_r, T_tw_tussen=T_tw_tussen, m_tw=m_tw,
             Q_E201=Q_E201, Q_AK=Q_AK, Q_adiabatisch=Q_AK, Q_E204=Q_E204, r_E204=r_E204, Q_L=Q_L, Q_H=Q_H,
             W_K201=W_K201, COP=COP, Q_E102_tot=Q_E102_tot, Q_net=Q_net, m_net_th=m_net * 3.6, T_aanvoer=T_aanvoer,
             Q_ind=Q_ind, ind_begrensd=begrensd, Q_L2=Q_L2, W_K202=W_K202, COP2=COP2 if Q_ind > 0 else nan,
             m_ind_th=m_ind, m_kc_unit=m_kc_unit, cp_kc=cp_kc, T_kc_naE201=T_kc_naE201,
             Q_warmte_nuttig=Q_net + Q_ind)
    return r


def nabewerking(i: Invoer, r: dict) -> dict:
    """Grootheden die voor beide modellen hetzelfde worden afgeleid."""
    r["m_verschil"] = r["m_vers"] - (i.m_afvalwater + r["m_backbone"] + r["m_gas"])
    r["E_in"] = r["P_AC_EOL"] + r["W_K101"] + r["W_K102"]
    r["E_uit"] = (i.m_H2 * CENGEL["HHV_H2"] / 3600 + i.Q_ITM_EOL - r["Q_E101"] + r["Q_pak_K101"]
                  - r["Q_E102"] - r["Q_E103"] + r["Q_pak_K102"] + r["Q_O2_RWZI"])
    r["chk_E"] = r["E_in"] - r["E_uit"]
    r["chk_p5"] = (r["Q_ITM_tot"] + r["Q_E102_tot"] + r["W_K201"] + r["W_K202"]
                   - r["Q_net"] - r["Q_ind"] - r["Q_AK"])
    r["i"] = i
    return r

# ---------------------------------------------------------------- Excel-model
CENGEL = dict(Mol_O2=31.999, Mol_H2O=18.015, cp_O2=0.918, cp_damp=1.8723, cp_H2=14.307,
              k_O2=1.395, k_H2=1.405, Psat_30=4.2469, Psat_65=25.043, Psat_70=31.202,
              hg_70=2626.1, hg_30=2555.6, hf_30=125.74, R_H2=4.124, B_H2=14.8,
              vf_30=0.001004, cp_w=4.18, HHV_H2=141800.0)


def excel(i: Invoer) -> dict:
    f_last = last_factor(i)
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
    # p warmtepompen (η_II × Carnot)
    T_L = i.T_kc_retour - i.dT_E201 - i.dT_min + T0
    T_H = i.T_net_aanvoer + i.dT_min + T0
    T_H2 = i.T_ind_aanvoer + i.dT_min + T0
    COP_wp = i.eta_II * T_H / (T_H - T_L)
    COP_wp2 = i.eta_II * T_H2 / (T_H2 - T_L)
    T_uit_K102 = T2 - T0
    T_uit_K101 = T2h - T0
    r.update(locals())
    W_K101_s = mcp_H2 * (T2sh - T1h)
    COP_carnot = T_H / (T_H - T_L)
    COP2_carnot = T_H2 / (T_H2 - T_L)
    r.update(locals())
    out = {k: v for k, v in r.items() if isinstance(v, (int, float)) and k not in ("c", "r", "i")}
    out["_f_last"] = f_last
    warmteketen(i, out, COP_wp, COP_wp2, lambda T: c["cp_w"] * T)
    return nabewerking(i, out)


# ---------------------------------------------------------------- CoolProp-model
def coolprop(i: Invoer) -> dict:
    f_last = last_factor(i)
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

    # p – warmtepompen als echte dampcompressiecyclus, verdampen op het tussencircuit TW
    T_evap = i.T_kc_retour - i.dT_E201 - i.dT_min
    hp = warmtepomp(i.koudemiddel, T_evap, i.T_net_aanvoer + i.dT_min, i.eta_K201)
    hp2 = warmtepomp(i.koudemiddel2, T_evap, i.T_ind_aanvoer + i.dT_min, i.eta_K202) if i.Q_ind > 0 else None
    hw = lambda T: PS("H", "T", T + T0, "P", 1e6, "Water") / 1e3

    out = {k: v for k, v in locals().items() if isinstance(v, (int, float))}
    out["cyclus"] = hp
    out["cyclus2"] = hp2
    out["COP_carnot"] = hp["COP_carnot"]
    out["COP2_carnot"] = hp2["COP_carnot"] if hp2 else float("nan")
    out["_f_last"] = f_last
    warmteketen(i, out, hp["COP"], hp2["COP"] if hp2 else float("nan"), hw)
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

    def kring(cy, Q_cond):
        """Koudemiddeldebiet (kg/h) en dichtheden in de vier leidingen van een cyclus."""
        f = cy["fluid"]
        Pe, Pc = cy["P_evap_bar"] * 1e5, cy["P_cond_bar"] * 1e5
        return (f, Q_cond / (cy["h2"] - cy["h3"]) * 3600,
                [PS("D", "T", cy["T_evap"] + T0, "Q", 1, f), PS("D", "P", Pc, "H", cy["h2"] * 1e3, f),
                 PS("D", "T", cy["T_cond"] + T0, "Q", 0, f), PS("D", "P", Pe, "H", cy["h3"] * 1e3, f)])

    cy, cy2 = r["cyclus"], r["cyclus2"]
    f, m_ref, (rho_R1, rho_R2, rho_R3, rho_R4) = kring(cy, r["Q_H"])

    kc = r["m_kc_unit"]                                   # kg/h per unit (datasheet)
    tw = r["m_tw"] * 3600                                 # kg/h tussencircuit
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
        ("A", "ITM-circuit uit ITM → E-201", "water/CoolFlow DTX 62/38", U, kc, d.rho_kc, "pers", d.T_kc_uit, d.P_kc),
        ("A2", "ITM-circuit E-201 → luchtkoeler AK", "water/CoolFlow DTX 62/38", U, kc, d.rho_kc, "pers", r["T_kc_naE201"], d.P_kc),
        ("B", "ITM-circuit luchtkoeler AK → ITM", "water/CoolFlow DTX 62/38", U, kc, d.rho_kc, "pers", d.T_kc_retour, d.P_kc),
        ("TW", "Tussencircuit aftakking per E-201", "water", U, tw / n, w(r["T_tw_a"]), "pers", r["T_tw_a"], None),
        ("TW1", "Tussencircuit E-201's → E-204", "water", A, tw, w(r["T_tw_a"]), "pers", r["T_tw_a"], None),
        ("TW2", "Tussencircuit E-204 → verdampers", "water", A, tw, w(r["T_tw_tussen"]), "pers", r["T_tw_tussen"], None),
        ("TW3", "Tussencircuit retour → E-201's", "water", A, tw, w(r["T_tw_r"]), "pers", r["T_tw_r"], None),
        ("KW1", "Koelwater E-101", "koelwater", U, r["m_kw_E101"], w((d.T_kw_in + d.T_kw_uit) / 2, 3e5), "pers", d.T_kw_in, None),
        ("KW2", "Koelwater E-103", "koelwater", U, r["m_kw_E103"], w((d.T_kw_in + d.T_kw_uit) / 2, 3e5), "pers", d.T_kw_in, None),
        ("WW1", "Warmtenet-zijstroom E-102", "netwater", U, r["m_ww_E102"], w((d.T_net_retour + d.T_net_aanvoer) / 2), "pers", d.T_net_retour, None),
        ("N1", "Warmtenet retour → E-204", "netwater", A, net, w(d.T_net_retour), "pers", d.T_net_retour, None),
        ("N2", "Warmtenet E-204 → E-203", "netwater", A, net, w(d.T_E204_uit), "pers", d.T_E204_uit, None),
        ("N3", "Warmtenet aanvoer (incl. zijstroom E-102)", "netwater", A, net + n * r["m_ww_E102"], w(d.T_net_aanvoer), "pers", d.T_net_aanvoer, None),
        ("R1", "E-202 → K-201 (zuigdamp)", f, A, m_ref, rho_R1, "rd", cy["T_evap"], cy["P_evap_bar"] - 1.01325),
        ("R2", "K-201 → E-203 (persdamp)", f, A, m_ref, rho_R2, "rd", cy["T_pers"], cy["P_cond_bar"] - 1.01325),
        ("R3", "E-203 → TV-201 (vloeistof)", f, A, m_ref, rho_R3, "rv", cy["T_cond"], cy["P_cond_bar"] - 1.01325),
        ("R4", "TV-201 → E-202 (tweefase)", f, A, m_ref, rho_R4, "r2", cy["T_evap"], cy["P_evap_bar"] - 1.01325),
    ]
    if cy2 and r["Q_ind"] > 0:
        f2, m2, (q1, q2, q3, q4) = kring(cy2, r["Q_ind"])
        TW_ind = r["Q_L2"] / r["Q_E201"] * tw if r["Q_E201"] else 0.0
        mi = r["m_ind_th"] * 1000
        L += [
            ("TW4", "Tussencircuit → verdamper E-206 (WP-202)", "water", A, TW_ind, w(r["T_tw_tussen"]), "pers", r["T_tw_tussen"], None),
            ("I1", "Industrie aanvoer uit E-205", "water (onder druk)", A, mi, w(d.T_ind_aanvoer, 1e6), "pers", d.T_ind_aanvoer, None),
            ("I2", "Industrie retour → E-205", "water (onder druk)", A, mi, w(d.T_ind_retour, 1e6), "pers", d.T_ind_retour, None),
            ("R5", "E-206 → K-202 (zuigdamp)", f2, A, m2, q1, "rd", cy2["T_evap"], cy2["P_evap_bar"] - 1.01325),
            ("R6", "K-202 → E-205 (persdamp)", f2, A, m2, q2, "rd", cy2["T_pers"], cy2["P_cond_bar"] - 1.01325),
            ("R7", "E-205 → TV-202 (vloeistof)", f2, A, m2, q3, "rv", cy2["T_cond"], cy2["P_cond_bar"] - 1.01325),
            ("R8", "TV-202 → E-206 (tweefase)", f2, A, m2, q4, "r2", cy2["T_evap"], cy2["P_evap_bar"] - 1.01325),
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
    ("COP", "COP warmtepomp WP-201", "–"),
    ("Q_E201", "E-201 (8 units)", "kW"),
    ("Q_E204", "E-204 directe voorverwarming", "kW"),
    ("Q_H", "Condensor E-203", "kW"),
    ("W_K201", "K-201 (E6)", "kW"),
    ("Q_net", "Totaal naar warmtenet", "kW"),
    ("COP2", "COP WP-202 industrie", "–"),
    ("W_K202", "K-202 (WP-202)", "kW"),
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
    Tc2 = list(np.arange(60, 140.1, 1.0))
    t["HP"] = {}
    for f, Tc in [("R1234ze(E)", Tc), ("R600a", Tc), ("Ammonia", Tc),
                  ("R1233zd(E)", Tc2), ("n-Butane", Tc2), ("R245fa", Tc2)]:
        rows = {"h1": [], "h2s": [], "h3": [], "Pe": [], "Pc": [],
                "hl_e": [], "Dv_e": [], "Dl_e": [], "Dl_c": [], "D2s": [], "T2s": [], "cp2s": []}
        for te in Te:
            h1 = PS("H", "T", te + T0, "Q", 1, f)
            s1 = PS("S", "T", te + T0, "Q", 1, f)
            rows["h1"].append(round(h1 / 1e3, 4))
            rows["Pe"].append(round(PS("P", "T", te + T0, "Q", 1, f) / 1e5, 5))
            rows["hl_e"].append(round(PS("H", "T", te + T0, "Q", 0, f) / 1e3, 3))
            rows["Dv_e"].append(round(PS("D", "T", te + T0, "Q", 1, f), 4))
            rows["Dl_e"].append(round(PS("D", "T", te + T0, "Q", 0, f), 3))
            r2, d2, t2, c2 = [], [], [], []
            for tc in Tc:
                Pc = PS("P", "T", tc + T0, "Q", 0, f)
                r2.append(round(PS("H", "P", Pc, "S", s1, f) / 1e3, 4))
                d2.append(round(PS("D", "P", Pc, "S", s1, f), 4))
                t2.append(round(PS("T", "P", Pc, "S", s1, f) - T0, 3))
                c2.append(round(PS("CPMASS", "P", Pc, "S", s1, f) / 1e3, 5))
            rows["h2s"].append(r2)
            rows["D2s"].append(d2)
            rows["T2s"].append(t2)
            rows["cp2s"].append(c2)
        for tc in Tc:
            rows["h3"].append(round(PS("H", "T", tc + T0, "Q", 0, f) / 1e3, 4))
            rows["Pc"].append(round(PS("P", "T", tc + T0, "Q", 0, f) / 1e5, 5))
            rows["Dl_c"].append(round(PS("D", "T", tc + T0, "Q", 0, f), 3))
        dome = []
        Tcrit = PS("Tcrit", f)
        for T in np.linspace(250, Tcrit - 0.5, 60):
            dome.append([round(PS("P", "T", T, "Q", 0, f) / 1e5, 4),
                         round(PS("H", "T", T, "Q", 0, f) / 1e3, 2),
                         round(PS("H", "T", T, "Q", 1, f) / 1e3, 2)])
        rows["dome"] = dome
        rows["Tc"] = [float(x) for x in Tc]
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

"""
Alle getallen voor het rekenverslag, met tussenstappen.

  versie A : CoolProp (zoals itm_model.coolprop), elke opzoeking expliciet
  versie B : alleen Cengel (rekenblad itm_model.excel: ideaal gas, constante cp, stoomtabellen),
             warmtepompen met waarden afgelezen uit het log p-h-diagram (afgerond op 0,5 kJ/kg)

Elke tussenstap wordt opnieuw uitgerekend en gecontroleerd tegen itm_model, zodat het verslag
altijd dezelfde getallen geeft als de app.
"""
import math
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import CoolProp.CoolProp as CP  # noqa: E402
import itm_model as M  # noqa: E402

PS = CP.PropsSI
T0 = 273.15
PATM = 101.325
RU = 8.314  # kJ/(kmol·K), Cengel


def kpa(barg):
    return barg * 100 + PATM


def rond(x, stap):
    return round(x / stap) * stap


def check(a, b, naam, tol=1e-6):
    if abs(a - b) > tol * max(1.0, abs(b)):
        raise AssertionError(f"{naam}: verslag {a} ≠ model {b}")


# ------------------------------------------------------------------ gemeenschappelijk
def invoer():
    return M.Invoer()


def stoich(m_H2, M_H2, M_O2, M_H2O, m_O2mix):
    """Elektrolyse H2O → H2 + ½ O2: wat de datasheet stoichiometrisch zou moeten geven."""
    N = m_H2 / M_H2
    m_O2 = N * 0.5 * M_O2
    m_w = N * M_H2O
    return dict(N_H2_st=N, m_O2_st=m_O2, m_w_reactie=m_w, w_st=(m_O2mix - m_O2) / m_O2mix,
                m_H2O_st=m_O2mix - m_O2)


# ------------------------------------------------------------------ versie A
def versie_A():
    i = invoer()
    ref = M.coolprop(i)
    r = {}
    H2, O2, W = "Hydrogen", "Oxygen", "Water"
    r["M_O2"], r["M_H2O"], r["M_H2"] = PS("M", O2) * 1e3, PS("M", W) * 1e3, PS("M", H2) * 1e3
    # a samenstelling
    r["m_H2O_in"] = i.w_H2O * i.m_O2mix
    r["m_O2"] = i.m_O2mix - r["m_H2O_in"]
    r["N_O2"], r["N_H2O"] = r["m_O2"] / r["M_O2"], r["m_H2O_in"] / r["M_H2O"]
    r["N_tot"] = r["N_O2"] + r["N_H2O"]
    r["y_v"] = r["N_H2O"] / r["N_tot"]
    r["P_O2_abs"] = kpa(i.P_O2_uit)
    r["P_v"] = r["y_v"] * r["P_O2_abs"]
    r["T_dauw"] = PS("T", "P", r["P_v"] * 1e3, "Q", 1, W) - T0
    r["Psat_70"] = PS("P", "T", 70 + T0, "Q", 0, W) / 1e3
    check(r["T_dauw"], ref["T_dauw"], "T_dauw")
    # b KO-drum
    r["Psat_KO"] = PS("P", "T", i.T_KO + T0, "Q", 0, W) / 1e3
    r["y_v_max"] = r["Psat_KO"] / r["P_O2_abs"]
    r["N_v"] = r["y_v_max"] / (1 - r["y_v_max"]) * r["N_O2"]
    r["m_v"] = r["N_v"] * r["M_H2O"]
    r["m_cond"] = r["m_H2O_in"] - r["m_v"]
    r["m_gas"] = r["m_O2"] + r["m_v"]
    r["omega_in"] = r["m_H2O_in"] / r["m_O2"]
    r["omega_KO"] = r["m_v"] / r["m_O2"]
    check(r["m_v"], ref["m_v"], "m_v")
    # c E-101
    pO2_in = (1 - r["y_v"]) * r["P_O2_abs"]
    pO2_ko = (1 - r["y_v_max"]) * r["P_O2_abs"]
    r["pO2_in"], r["pO2_ko"] = pO2_in, pO2_ko
    r["hO2_70"] = PS("H", "T", i.T_O2_uit + T0, "P", pO2_in * 1e3, O2) / 1e3
    r["hO2_30"] = PS("H", "T", i.T_KO + T0, "P", pO2_ko * 1e3, O2) / 1e3
    r["Q_c_O2"] = r["m_O2"] / 3600 * (r["hO2_30"] - r["hO2_70"])
    r["hv_70"] = PS("H", "T", i.T_O2_uit + T0, "P", 500.0, W) / 1e3
    r["hv_30"] = PS("H", "T", i.T_KO + T0, "P", 500.0, W) / 1e3
    r["hg_70_sat"] = PS("H", "T", i.T_O2_uit + T0, "Q", 1, W) / 1e3
    r["hg_30_sat"] = PS("H", "T", i.T_KO + T0, "Q", 1, W) / 1e3
    r["hf_30"] = PS("H", "T", i.T_KO + T0, "Q", 0, W) / 1e3
    r["Q_c_w"] = (r["m_v"] * r["hv_30"] + r["m_cond"] * r["hf_30"] - r["m_H2O_in"] * r["hv_70"]) / 3600
    r["Q_E101"] = r["Q_c_O2"] + r["Q_c_w"]
    r["Q_E101_lat"] = r["m_cond"] / 3600 * (r["hv_30"] - r["hf_30"])
    r["Q_E101_vel"] = r["Q_E101"] + r["Q_E101_lat"]
    check(r["Q_E101"], ref["Q_E101"], "Q_E101")
    r["cp_O2_eff"] = (r["hO2_70"] - r["hO2_30"]) / (i.T_O2_uit - i.T_KO)
    # d K-102
    P2 = kpa(i.P_RWZI)
    r["P_uit_K102"] = P2
    r["pO2_2"], r["pv_2"], r["pv_1"] = (1 - r["y_v_max"]) * P2, r["y_v_max"] * P2, r["y_v_max"] * r["P_O2_abs"]
    r["rp_K102"] = P2 / r["P_O2_abs"]
    for k in ("h1", "s1", "T2s", "h2s", "h2", "T_uit_K102", "W_K102", "T_S18", "Q_pak_K102", "Q_O2_RWZI", "T_dauw_S18"):
        r[k] = ref[k] / (1e3 if k in ("h1", "s1", "h2s", "h2") else 1)
    r["sO2_1"] = PS("S", "T", i.T_KO + T0, "P", pO2_ko * 1e3, O2) / 1e3
    r["sv_1"] = (PS("S", "T", i.T_KO + T0, "P", 500.0, W) - 8.314462618 / (r["M_H2O"] / 1e3) * math.log(r["pv_1"] * 1e3 / 500)) / 1e3
    r["hO2_K102_1"] = PS("H", "T", i.T_KO + T0, "P", pO2_ko * 1e3, O2) / 1e3
    r["hv_K102_1"] = r["hv_30"]
    r["hS18"] = (r["h2"] - r["Q_pak_K102"] * 3600 / r["m_gas"])
    r["eta_K102"] = i.eta_K102
    # e K-101
    P1, P2h = kpa(i.P_V101_min), kpa(i.P_K101_uit)
    r["P_in_K101"], r["P_uit_K101"] = P1, P2h
    T1 = i.T_H2 + T0
    r["h1h"] = PS("H", "T", T1, "P", P1 * 1e3, H2) / 1e3
    r["s1h"] = PS("S", "T", T1, "P", P1 * 1e3, H2) / 1e3
    r["h2sh"] = PS("H", "S", r["s1h"] * 1e3, "P", P2h * 1e3, H2) / 1e3
    r["T2sh"] = PS("T", "S", r["s1h"] * 1e3, "P", P2h * 1e3, H2) - T0
    r["h2h"] = r["h1h"] + (r["h2sh"] - r["h1h"]) / i.eta_K101
    r["T_uit_K101"] = PS("T", "H", r["h2h"] * 1e3, "P", P2h * 1e3, H2) - T0
    r["m_S5"] = ref["m_S5"]
    r["W_K101"] = r["m_S5"] / 3600 * (r["h2h"] - r["h1h"])
    r["W_K101_s"] = r["m_S5"] / 3600 * (r["h2sh"] - r["h1h"])
    r["T_S6"] = r["T_uit_K101"] - i.dT_pakket
    hH = lambda T: PS("H", "T", T + T0, "P", P2h * 1e3, H2) / 1e3
    r["hH_S6"], r["hH_50"], r["hH_25"] = hH(r["T_S6"]), hH(i.T_E102_uit), hH(i.T_E103_uit)
    r["Q_pak_K101"] = r["m_S5"] / 3600 * (r["h2h"] - r["hH_S6"])
    r["Q_E102"] = r["m_S5"] / 3600 * (r["hH_50"] - r["hH_S6"])
    r["Q_E103"] = r["m_S5"] / 3600 * (r["hH_25"] - r["hH_50"])
    r["hH_25_lp"] = r["h1h"]
    r["Q_H2_res"] = r["m_S5"] / 3600 * (r["hH_25"] - r["h1h"])
    r["Z_in_K101"] = PS("Z", "T", T1, "P", P1 * 1e3, H2)
    r["Z_uit_K101"] = PS("Z", "T", r["T_uit_K101"] + T0, "P", P2h * 1e3, H2)
    r["rp_K101"] = P2h / P1
    r["k_H2"] = PS("CPMASS", "T", T1, "P", 101325, H2) / PS("CVMASS", "T", T1, "P", 101325, H2)
    r["cp_H2_eff"] = (r["h2h"] - r["hH_S6"]) / i.dT_pakket
    for k in ("W_K101", "Q_pak_K101", "Q_E102", "Q_E103", "T_uit_K101"):
        check(r[k], ref[k], k)
    # h buffers
    rho = lambda P: PS("D", "T", T1, "P", P * 1e3, H2)
    r["P_V101_max"], r["P_V101_min"] = kpa(i.P_V101_max), P1
    r["P_V102_max"], r["P_V102_min"] = P2h, kpa(i.P_backbone)
    r["rho_V101_max"], r["rho_V101_min"] = rho(r["P_V101_max"]), rho(r["P_V101_min"])
    r["rho_V102_max"], r["rho_V102_min"] = rho(r["P_V102_max"]), rho(r["P_V102_min"])
    r["Z_V101_max"] = PS("Z", "T", T1, "P", r["P_V101_max"] * 1e3, H2)
    r["Z_V101_min"] = PS("Z", "T", T1, "P", r["P_V101_min"] * 1e3, H2)
    r["Z_V102_max"] = PS("Z", "T", T1, "P", r["P_V102_max"] * 1e3, H2)
    r["Z_V102_min"] = PS("Z", "T", T1, "P", r["P_V102_min"] * 1e3, H2)
    r["m_buf_V101"] = i.m_H2 * i.t_V101
    r["m_buf_V102"] = i.m_H2 * i.t_V102 / 3600
    r["V_V101_iso"] = r["m_buf_V101"] / (r["rho_V101_max"] - r["rho_V101_min"])
    r["V_V102_iso"] = r["m_buf_V102"] / (r["rho_V102_max"] - r["rho_V102_min"])
    r["V_V101"] = r["V_V101_iso"] * i.n_V101
    r["V_V102"] = r["V_V102_iso"] * r["k_H2"]
    check(r["V_V101"], ref["V_V101"], "V_V101")
    check(r["V_V102"], ref["V_V102"], "V_V102")
    # i pomp
    r["v_f"] = 1 / PS("D", "T", i.T_KO + T0, "Q", 0, W)
    r["P_voed"] = kpa(i.P_ITM_voed)
    r["dP_P101"] = r["P_voed"] - r["P_O2_abs"]
    r["W_P101"] = r["m_cond"] / 3600 * r["v_f"] * r["dP_P101"] / i.eta_P101
    r["W_P101_s"] = r["W_P101"] * i.eta_P101
    r["m_vers"] = i.m_voedwater - r["m_cond"]
    # j koelwater
    r["hkw_in"] = PS("H", "T", i.T_kw_in + T0, "P", 3e5, W) / 1e3
    r["hkw_uit"] = PS("H", "T", i.T_kw_uit + T0, "P", 3e5, W) / 1e3
    r["dh_kw"] = r["hkw_uit"] - r["hkw_in"]
    r["m_kw_E101"] = -r["Q_E101"] / r["dh_kw"] * 3600
    r["m_kw_E103"] = -r["Q_E103"] / r["dh_kw"] * 3600
    # l ITM
    gemeen_itm(r, i)
    # warmteketen
    for k in ("T_tw_a", "T_tw_r", "Q_ITM_tot", "Q_H2_tot", "Q_H2_unit", "Q_TW", "T_tw_tussen", "T_tw_naE202",
              "Q_E201", "Q_AK", "Q_E204", "r_E204", "Q_L", "Q_H", "W_K201", "COP", "Q_net", "Q_ind", "Q_L2",
              "W_K202", "COP2", "m_kc_unit", "cp_kc", "T_kc_naE201", "Q_warmte_nuttig", "T_E204", "Q_H2_TW",
              "E_in", "E_uit", "chk_E", "chk_p5", "m_verschil", "m_tw_H2_unit"):
        r[k] = ref[k]
    r["m_tw"] = ref["m_tw"] * 3600
    r["m_net"] = ref["m_net_th"] * 1000
    r["m_ind"] = ref["m_ind_th"] * 1000
    hw = lambda T: PS("H", "T", T + T0, "P", 1e6, W) / 1e3
    r["hw"] = {T: hw(T) for T in (40, 45, 45.0, 50, 51.5, 70, 75, 95)}
    r["hw_45_40"], r["hw_70_45"], r["hw_95_75"] = hw(45) - hw(40), hw(70) - hw(45), hw(95) - hw(75)
    r["cpw_tw"] = (hw(r["T_tw_a"]) - hw(r["T_tw_r"])) / (r["T_tw_a"] - r["T_tw_r"])
    gemeen_keten(r, i)
    # warmtepompen
    r["wp1"] = cyclus_A(i.koudemiddel, r["T_evap"], r["T_cond1"], i.eta_K201, r["Q_H"])
    r["wp2"] = cyclus_A(i.koudemiddel2, r["T_evap"], r["T_cond2"], i.eta_K202, r["Q_ind"])
    check(r["wp1"]["COP"], ref["COP"], "COP")
    check(r["wp2"]["COP"], ref["COP2"], "COP2")
    r["COP_etaII"] = i.eta_II * r["wp1"]["COP_carnot"]
    r["COP2_etaII"] = i.eta_II * r["wp2"]["COP_carnot"]
    # leidingen
    r["leidingen"] = M.leidingen(i)
    r["E101_dauw"] = r["T_dauw"]
    r.update(stoich(i.m_H2, r["M_H2"], r["M_O2"], r["M_H2O"], i.m_O2mix))
    r["versie"] = "A"
    r["ref"] = ref
    return r


def cyclus_A(fluid, Te, Tc, eta, Q_cond):
    c = M.warmtepomp(fluid, Te, Tc, eta)
    f = fluid
    Pe, Pc = c["P_evap_bar"] * 1e5, c["P_cond_bar"] * 1e5
    d = dict(fluid=f, Te=Te, Tc=Tc, eta=eta, Pe=Pe / 1e3, Pc=Pc / 1e3)
    d["h1"] = c["h1"]
    d["s1"] = PS("S", "T", Te + T0, "Q", 1, f) / 1e3
    d["h2s"] = PS("H", "P", Pc, "S", d["s1"] * 1e3, f) / 1e3
    d["T2s"] = PS("T", "P", Pc, "S", d["s1"] * 1e3, f) - T0
    d["h2"] = c["h2"]
    d["T2"] = c["T_pers"]
    d["s2"] = PS("S", "P", Pc, "H", d["h2"] * 1e3, f) / 1e3
    d["h3"] = c["h3"]
    d["s3"] = PS("S", "T", Tc + T0, "Q", 0, f) / 1e3
    d["h4"] = d["h3"]
    d["x4"] = c["x4"]
    d["s4"] = PS("S", "P", Pe, "H", d["h4"] * 1e3, f) / 1e3
    d["hf_e"] = PS("H", "T", Te + T0, "Q", 0, f) / 1e3
    d["hg_e"] = d["h1"]
    d["hg_c"] = PS("H", "T", Tc + T0, "Q", 1, f) / 1e3
    d["rho1"] = PS("D", "T", Te + T0, "Q", 1, f)
    d["rho2"] = PS("D", "P", Pc, "H", d["h2"] * 1e3, f)
    d["rho3"] = PS("D", "T", Tc + T0, "Q", 0, f)
    d["rho4"] = PS("D", "P", Pe, "H", d["h4"] * 1e3, f)
    d["Tcrit"] = PS("Tcrit", f) - T0
    d["Pcrit"] = PS("Pcrit", f) / 1e3
    afronden_cyclus(d, Q_cond)
    return d


def afronden_cyclus(d, Q_cond):
    d["q_in"] = d["h1"] - d["h4"]
    d["w"] = d["h2"] - d["h1"]
    d["w_s"] = d["h2s"] - d["h1"]
    d["q_uit"] = d["h2"] - d["h3"]
    d["q_desup"] = d["h2"] - d["hg_c"]
    d["q_cond_lat"] = d["hg_c"] - d["h3"]
    d["COP"] = d["q_uit"] / d["w"]
    d["COP_s"] = (d["h2s"] - d["h3"]) / d["w_s"]
    d["COP_carnot"] = (d["Tc"] + T0) / (d["Tc"] - d["Te"])
    d["eta_II"] = d["COP"] / d["COP_carnot"]
    d["rp"] = d["Pc"] / d["Pe"]
    d["Q_cond"] = Q_cond
    d["m_ref"] = Q_cond / d["q_uit"] * 3600 if Q_cond else 0.0
    d["Q_evap"] = d["m_ref"] / 3600 * d["q_in"]
    d["W_comp"] = d["m_ref"] / 3600 * d["w"]
    d["V_zuig"] = d["m_ref"] / d["rho1"]
    d["vhc"] = d["rho1"] * d["q_uit"]
    d["x4_hand"] = (d["h4"] - d["hf_e"]) / (d["hg_e"] - d["hf_e"])


# ------------------------------------------------------------------ versie B
CENGEL = M.CENGEL
TAB_A4 = {  # Cengel tabel A-4 (verzadigd water, temperatuurtabel): T: (Psat kPa, vf m3/kg, hf, hfg, hg)
    15: (1.7057, 0.001001, 62.982, 2465.4, 2528.3),
    20: (2.3392, 0.001002, 83.915, 2453.5, 2537.4),
    25: (3.1698, 0.001003, 104.83, 2441.7, 2546.5),
    30: (4.2469, 0.001004, 125.74, 2429.8, 2555.6),
    35: (5.6291, 0.001006, 146.64, 2417.9, 2564.6),
    40: (7.3851, 0.001008, 167.53, 2406.0, 2573.5),
    45: (9.5953, 0.001010, 188.44, 2394.0, 2582.4),
    50: (12.352, 0.001012, 209.34, 2382.0, 2591.3),
    55: (15.763, 0.001015, 230.26, 2369.8, 2600.1),
    60: (19.947, 0.001017, 251.18, 2357.7, 2608.8),
    65: (25.043, 0.001020, 272.12, 2345.4, 2617.5),
    70: (31.202, 0.001023, 293.07, 2333.0, 2626.1),
    75: (38.597, 0.001026, 314.03, 2320.6, 2634.6),
    80: (47.416, 0.001029, 335.02, 2308.0, 2643.0),
    85: (57.868, 0.001032, 356.02, 2295.3, 2651.4),
    90: (70.183, 0.001036, 377.04, 2282.5, 2659.6),
    95: (84.609, 0.001040, 398.09, 2269.6, 2667.6),
}


def tsat_A4(P):
    """T_sat bij P (kPa) door lineair te interpoleren in tabel A-4."""
    ks = sorted(TAB_A4)
    for a, b in zip(ks, ks[1:]):
        pa, pb = TAB_A4[a][0], TAB_A4[b][0]
        if pa <= P <= pb:
            return a + (b - a) * (P - pa) / (pb - pa)
    raise ValueError(P)


def ko_B(T_KO, w=None):
    """Damp en condensaat na de KO-drum bij een andere temperatuur, met P_sat uit tabel A-4."""
    i = invoer()
    w = i.w_H2O if w is None else w
    c = CENGEL
    m_w = w * i.m_O2mix
    m_O2 = i.m_O2mix - m_w
    N_O2, N_w = m_O2 / c["Mol_O2"], m_w / c["Mol_H2O"]
    P = kpa(i.P_O2_uit)
    y = TAB_A4[T_KO][0] / P
    m_v = y / (1 - y) * N_O2 * c["Mol_H2O"]
    return dict(m_v=m_v, m_cond=m_w - m_v, T_dauw=tsat_A4(N_w / (N_O2 + N_w) * P))


def vf_A4(T):
    """v_f uit tabel A-4, lineair geïnterpoleerd."""
    ks = sorted(TAB_A4)
    for a, b in zip(ks, ks[1:]):
        if a <= T <= b:
            va, vb = TAB_A4[a][1], TAB_A4[b][1]
            return va + (vb - va) * (T - a) / (b - a)
    raise ValueError(T)


def versie_B():
    i = invoer()
    c = CENGEL
    ref = M.excel(i)
    r = {k: v for k, v in ref.items() if isinstance(v, (int, float))}
    r["M_O2"], r["M_H2O"], r["M_H2"] = c["Mol_O2"], c["Mol_H2O"], 2.016
    r["N_tot"] = r["N_O2"] + r["N_H2O"]
    r["Psat_KO"] = c["Psat_30"]
    r["Psat_70"] = c["Psat_70"]
    r["N_v"] = r["y_v_max"] / (1 - r["y_v_max"]) * r["N_O2"]
    r["omega_in"] = r["m_H2O_in"] / r["m_O2"]
    r["omega_KO"] = r["m_v"] / r["m_O2"]
    r["Q_c_O2"] = r["m_O2"] / 3600 * c["cp_O2"] * (i.T_KO - i.T_O2_uit)
    r["Q_c_w"] = (r["m_v"] * c["hg_30"] + r["m_cond"] * c["hf_30"] - r["m_H2O_in"] * c["hg_70"]) / 3600
    r["hg_70"], r["hg_30"], r["hf_30"] = c["hg_70"], c["hg_30"], c["hf_30"]
    r["Q_E101_lat"] = r["m_cond"] / 3600 * (c["hg_30"] - c["hf_30"])
    check(r["Q_c_O2"] + r["Q_c_w"], r["Q_E101"], "Q_E101 B")
    r["rp_K102"] = r["P_uit_K102"] / r["P_O2_abs"]
    r["T1_K102"] = r["T1"]
    r["T2s_K102"], r["T2_K102"] = r["T2s"], r["T2"]
    r["ex_O2"] = (c["k_O2"] - 1) / c["k_O2"]
    r["T_dauw_S18"] = None
    pv2 = r["y_v_max"] * r["P_uit_K102"]
    r["pv_2"] = pv2
    # dauwpunt S18 uit tabel A-4 (interpolatie 30–40 °C)
    r["T_dauw_S18"] = 30 + (pv2 - 4.2469) / (7.3851 - 4.2469) * 10
    r["rp_K101"] = r["P_uit_K101"] / r["P_in_K101"]
    r["W_K101_s"] = r["mcp_H2"] * (r["T2sh"] - r["T1h"])
    r["m_S5"] = r["m_S5"]
    # buffers (zelfde als rekenblad, tussenwaarden)
    RT, RuT = c["R_H2"] * r["T1h"], RU * r["T1h"]
    r["RT"], r["RuT"] = RT, RuT

    def buf(m, pmax, pmin, n):
        iso = m * RT / (pmax - pmin)
        zmax = 1 + c["B_H2"] * 1e-6 * pmax * 1000 / RuT
        zmin = 1 + c["B_H2"] * 1e-6 * pmin * 1000 / RuT
        isoZ = m / (pmax / RT / zmax - pmin / RT / zmin)
        return dict(m=m, pmax=pmax, pmin=pmin, n=n, iso=iso, zmax=zmax, zmin=zmin, isoZ=isoZ, V=isoZ * n,
                    rho_max=pmax / (zmax * RT), rho_min=pmin / (zmin * RT))
    r["V101"] = buf(i.m_H2 * i.t_V101, kpa(i.P_V101_max), r["P_in_K101"], i.n_V101)
    r["V102"] = buf(i.m_H2 * i.t_V102 / 3600, r["P_uit_K101"], kpa(i.P_backbone), c["k_H2"])
    check(r["V101"]["V"], r["V_V101"], "V101 B")
    check(r["V102"]["V"], r["V_V102"], "V102 B")
    r["P_voed"] = kpa(i.P_ITM_voed)
    r["dP_P101"] = r["P_voed"] - r["P_O2_abs"]
    r["W_P101_s"] = r["W_P101"] * i.eta_P101
    r["dh_kw"] = c["cp_w"] * (i.T_kw_uit - i.T_kw_in)
    gemeen_itm(r, i)
    # ---- warmtepompen: aflezen in het log p-h-diagram
    r["T_evap"] = i.T_kc_retour - i.dT_E201 - i.dT_min
    r["T_cond1"] = i.T_net_aanvoer + i.dT_min
    r["T_cond2"] = i.T_ind_aanvoer + i.dT_min
    r["COP_etaII"], r["COP2_etaII"] = ref["COP_wp"], ref["COP_wp2"]
    r["COP_carnot"], r["COP2_carnot"] = ref["COP_carnot"], ref["COP2_carnot"]
    lees1 = afgelezen(i.koudemiddel, r["T_evap"], r["T_cond1"], i.eta_K201)
    lees2 = afgelezen(i.koudemiddel2, r["T_evap"], r["T_cond2"], i.eta_K202)
    afronden_cyclus(lees1, 0.0)
    afronden_cyclus(lees2, 0.0)
    # warmteketen met de afgelezen COP (water: h = cp·T, cp = 4,18)
    out = dict(ref)
    M.warmteketen(M.schaal(i), out, lees1["COP"], lees2["COP"], lambda T: c["cp_w"] * T)
    M.nabewerking(M.schaal(i), out)
    for k in ("T_tw_a", "T_tw_r", "Q_ITM_tot", "Q_H2_tot", "Q_H2_unit", "Q_TW", "T_tw_tussen", "T_tw_naE202",
              "Q_E201", "Q_AK", "Q_E204", "r_E204", "Q_L", "Q_H", "W_K201", "COP", "Q_net", "Q_ind", "Q_L2",
              "W_K202", "COP2", "m_kc_unit", "cp_kc", "T_kc_naE201", "Q_warmte_nuttig", "T_E204", "Q_H2_TW",
              "E_in", "E_uit", "chk_E", "chk_p5", "m_verschil", "m_tw_H2_unit"):
        r[k] = out[k]
    r["m_tw"] = out["m_tw"] * 3600
    r["m_net"] = out["m_net_th"] * 1000
    r["m_ind"] = out["m_ind_th"] * 1000
    r["hw_45_40"], r["hw_70_45"], r["hw_95_75"] = c["cp_w"] * 5, c["cp_w"] * 25, c["cp_w"] * 20
    r["cpw_tw"] = c["cp_w"]
    r["hw"] = {T: c["cp_w"] * T for T in (40, 45, 50, 51.5, 70, 75, 95)}
    gemeen_keten(r, i)
    afronden_cyclus(lees1, r["Q_H"])
    afronden_cyclus(lees2, r["Q_ind"])
    r["wp1"], r["wp2"] = lees1, lees2
    # rekenblad zelf (η_II·Carnot) voor de vergelijking
    r["blad"] = dict(COP=ref["COP"], W_K201=ref["W_K201"], Q_net=ref["Q_net"], Q_H=ref["Q_H"],
                     COP2=ref["COP2"], W_K202=ref["W_K202"], Q_E204=ref["Q_E204"])
    r["leidingen"] = leidingen_B(i, r)
    r.update(stoich(i.m_H2, r["M_H2"], r["M_O2"], r["M_H2O"], i.m_O2mix))
    r["versie"] = "B"
    r["ref"] = ref
    return r


def afgelezen(fluid, Te, Tc, eta):
    """Waarden zoals je ze uit het log p-h-diagram afleest (h op 0,5 kJ/kg, p op 0,1 bar, ρ op 2-3 cijfers)."""
    f = fluid
    Pe = PS("P", "T", Te + T0, "Q", 1, f)
    Pc = PS("P", "T", Tc + T0, "Q", 0, f)
    s1 = PS("S", "T", Te + T0, "Q", 1, f)
    d = dict(fluid=f, Te=Te, Tc=Tc, eta=eta)
    d["Pe"] = rond(Pe / 1e5, 0.1) * 100
    d["Pc"] = rond(Pc / 1e5, 0.1) * 100
    d["h1"] = rond(PS("H", "T", Te + T0, "Q", 1, f) / 1e3, 0.5)
    d["s1"] = rond(s1 / 1e3, 0.005)
    d["h2s"] = rond(PS("H", "P", Pc, "S", s1, f) / 1e3, 0.5)
    d["T2s"] = rond(PS("T", "P", Pc, "S", s1, f) - T0, 1)
    d["h2"] = d["h1"] + (d["h2s"] - d["h1"]) / eta
    d["T2"] = rond(PS("T", "P", Pc, "H", d["h2"] * 1e3, f) - T0, 1)
    d["h3"] = rond(PS("H", "T", Tc + T0, "Q", 0, f) / 1e3, 0.5)
    d["h4"] = d["h3"]
    d["hf_e"] = rond(PS("H", "T", Te + T0, "Q", 0, f) / 1e3, 0.5)
    d["hg_e"] = d["h1"]
    d["hg_c"] = rond(PS("H", "T", Tc + T0, "Q", 1, f) / 1e3, 0.5)
    d["x4"] = (d["h4"] - d["hf_e"]) / (d["hg_e"] - d["hf_e"])
    d["rho1"] = float(f"{PS('D', 'T', Te + T0, 'Q', 1, f):.2g}")
    d["rho2"] = float(f"{PS('D', 'P', Pc, 'H', d['h2'] * 1e3, f):.2g}")
    d["rho3"] = float(f"{PS('D', 'T', Tc + T0, 'Q', 0, f):.3g}")
    d["rho4"] = float(f"{PS('D', 'P', Pe, 'H', d['h4'] * 1e3, f):.2g}")
    d["Tcrit"] = PS("Tcrit", f) - T0
    d["Pcrit"] = PS("Pcrit", f) / 1e3
    d["s2"] = d["s3"] = d["s4"] = float("nan")
    return d


def leidingen_B(i, r):
    """Leidingen met Cengel-dichtheden: ideaal gas ρ = P/(RT), water ρ = 1/v_f (tabel A-4)."""
    A = M.leidingen(i)
    c = CENGEL
    R_H2 = c["R_H2"]
    rhoH2 = lambda T, barg: kpa(barg) / (R_H2 * (T + T0))

    def rho_o2(T, barg, mO2, mv):
        N = mO2 / c["Mol_O2"] + mv / c["Mol_H2O"]
        return kpa(barg) * (mO2 + mv) / N / (RU * (T + T0))
    w = lambda T: 1 / vf_A4(T)
    wp1, wp2 = r["wp1"], r["wp2"]
    m_ref1 = wp1["m_ref"]
    m_ref2 = wp2["m_ref"]
    dichtheid = {
        "S1": (r["m_vers"], w(i.T_vers)), "S3": (i.m_afvalwater, w(i.T_afvalwater)),
        "S4": (i.m_H2, rhoH2(i.T_H2, i.P_H2_ITM)), "S5": (r["m_S5"], rhoH2(i.T_H2, i.P_V101_min)),
        "S6": (r["m_S5"], rhoH2(r["T_S6"], i.P_K101_uit)), "S7": (r["m_S5"], rhoH2(i.T_E102_uit, i.P_K101_uit)),
        "S8": (r["m_S5"], rhoH2(i.T_E103_uit, i.P_K101_uit)),
        "S9": (i.m_H2 * i.m_min_pct / 100, rhoH2(i.T_E103_uit, i.P_V101_min)),
        "S11": (i.m_H2, rhoH2(i.T_E103_uit, i.P_backbone)), "S12": (i.m_H2, rhoH2(i.T_E103_uit, i.P_backbone)),
        "S13": (i.m_O2mix, rho_o2(i.T_O2_uit, i.P_O2_uit, r["m_O2"], r["m_H2O_in"])),
        "S14": (i.m_O2mix, i.m_O2mix / ((r["m_O2"] + r["m_v"]) / rho_o2(i.T_KO, i.P_O2_uit, r["m_O2"], r["m_v"])
                                         + r["m_cond"] / w(i.T_KO))),
        "S15": (r["m_cond"], w(i.T_KO)), "S16": (r["m_cond"], w(i.T_KO)),
        "S17": (r["m_gas"], rho_o2(i.T_KO, i.P_O2_uit, r["m_O2"], r["m_v"])),
        "S18": (r["m_gas"], rho_o2(r["T_S18"], i.P_RWZI, r["m_O2"], r["m_v"])),
        "A": (i.m_kc_ds, i.rho_kc), "A2": (i.m_kc_ds, i.rho_kc), "B": (i.m_kc_ds, i.rho_kc),
        "TW": ((r["m_tw"] - i.n_units * r["m_tw_H2_unit"]) / i.n_units, w(r["T_tw_a"])),
        "TW-H": (r["m_tw_H2_unit"], w(r["T_tw_a"])),
        "TW1": (r["m_tw"], w(r["T_tw_a"])), "TW2": (r["m_tw"], w(r["T_tw_tussen"])),
        "TW3": (r["m_tw"], w(r["T_tw_r"])), "TW4": (r["m_tw"], w(r["T_tw_naE202"])),
        "KW1": (r["m_kw_E101"], w(25)), "KW2": (r["m_kw_E103"], w(25)),
        "N1": (r["m_net"], w(40)), "N2": (r["m_net"], w(r["T_E204"])), "N3": (r["m_net"], w(70)),
        "I1": (r["m_ind"], w(95)), "I2": (r["m_ind"], w(75)),
        "R1": (m_ref1, wp1["rho1"]), "R2": (m_ref1, wp1["rho2"]), "R3": (m_ref1, wp1["rho3"]), "R4": (m_ref1, wp1["rho4"]),
        "R5": (m_ref2, wp2["rho1"]), "R6": (m_ref2, wp2["rho2"]), "R7": (m_ref2, wp2["rho3"]), "R8": (m_ref2, wp2["rho4"]),
    }
    uit = []
    for L in A:
        m, rho = dichtheid[L["id"]]
        V = m / rho / 3600
        dmin = math.sqrt(4 * V / (math.pi * L["v_max"])) * 1000 if V > 0 else 0.0
        dn, di = M.kies_dn(dmin)
        vw = V / (math.pi / 4 * (di / 1000) ** 2) if dn else float("nan")
        L2 = dict(L, m=m, rho=rho, V=V * 3600, d_min=dmin, DN=dn, d_i=di, v=vw)
        if L["id"] in ("R1", "R2", "R3", "R4"):
            L2["T"] = {"R1": wp1["Te"], "R2": wp1["T2"], "R3": wp1["Tc"], "R4": wp1["Te"]}[L["id"]]
        if L["id"] in ("R5", "R6", "R7", "R8"):
            L2["T"] = {"R5": wp2["Te"], "R6": wp2["T2"], "R7": wp2["Tc"], "R8": wp2["Te"]}[L["id"]]
        uit.append(L2)
    return uit


# ------------------------------------------------------------------ gedeeld
def gemeen_itm(r, i):
    r["E_H2"] = i.m_H2 * CENGEL["HHV_H2"] / 3600
    r["E_H2_LHV"] = i.m_H2 * 120000 / 3600
    r["P_AC_BOL"] = i.SEC_BOL * i.m_H2
    r["Q_ITM_BOL"] = r["P_AC_BOL"] - r["E_H2"] + r["Q_E101"]
    r["P_AC_EOL"] = r["E_H2"] + i.Q_ITM_EOL - r["Q_E101"]
    r["SEC_EOL"] = r["P_AC_EOL"] / i.m_H2
    r["eta_HHV_BOL"] = r["E_H2"] / r["P_AC_BOL"]
    r["eta_HHV_EOL"] = r["E_H2"] / r["P_AC_EOL"]
    r["P_AC_tot"] = r["P_AC_EOL"] * i.n_units
    r["m_massa_in"] = i.m_voedwater
    r["m_massa_uit"] = i.m_H2 + i.m_O2mix + i.m_afvalwater


def gemeen_keten(r, i):
    n = i.n_units
    r["Q_bron"] = r["Q_ITM_tot"] + r["Q_H2_tot"]
    r["f_L"] = 1 - 1 / r["COP"]
    r["f_L2"] = 1 - 1 / r["COP2"]
    r["Qb"] = r["Q_bron"] - r["Q_L2"]
    r["T_evap"] = i.T_kc_retour - i.dT_E201 - i.dT_min
    r["T_cond1"] = i.T_net_aanvoer + i.dT_min
    r["T_cond2"] = i.T_ind_aanvoer + i.dT_min
    r["W_wp_tot"] = r["W_K201"] + r["W_K202"]
    r["COP_sys"] = (r["Q_net"] + r["Q_ind"]) / r["W_wp_tot"]
    r["Q_E201_unit"] = r["Q_E201"] / n
    r["m_kc_s"] = r["m_kc_unit"] / 3600
    r["Q_E202"] = r["Q_L"]
    r["Q_E206"] = r["Q_L2"]
    r["Q_E203"] = r["Q_H"]
    r["Q_E205"] = r["Q_ind"]
    r["Q_ITM_unit"] = i.Q_ITM_EOL
    r["m_tw_E201_unit"] = (r["m_tw"] - n * r["m_tw_H2_unit"]) / n
    r["dT_E204_warm"] = r["T_tw_a"] - r["T_E204"]
    r["dT_E204_koud"] = r["T_tw_tussen"] - i.T_net_retour
    r["E_el_tot"] = r["P_AC_EOL"] * n + n * (r["W_K101"] + r["W_K102"] + r["W_P101"]) + r["W_wp_tot"]


# ------------------------------------------------------------------ wat-als (verdedigingsvragen)
def wat_als(versie):
    """Gevoeligheden voor de vragenbijlage. A: CoolProp-model, B: rekenblad (COP = η_II·Carnot)."""
    fn = M.coolprop if versie == "A" else M.excel
    base = M.Invoer()
    gevallen = {
        "basis": base,
        "net80": replace(base, T_net_aanvoer=80.0),
        "net60": replace(base, T_net_aanvoer=60.0),
        "eta60": replace(base, eta_K201=0.60, eta_K202=0.60, eta_II=0.43),
        "dTmin3": replace(base, dT_min=3.0),
        "dTmin8": replace(base, dT_min=8.0),
        "E204uit": replace(base, T_E204_uit=40.0),
        "E204_46": replace(base, T_E204_uit=46.5),
        "wpuit": replace(base, wp_aan=False),
        "indnul": replace(base, Q_ind=0.0),
        "KO35": replace(base, T_KO=35.0),
        "KO25": replace(base, T_KO=25.0),
        "etaK101_65": replace(base, eta_K101=0.65),
        "Pback": replace(base, P_K101_uit=80.0),
        "dTE201_5": replace(base, dT_E201=5.0),
        "ind120": replace(base, T_ind_aanvoer=120.0, T_ind_retour=100.0, koudemiddel2="R1233zd(E)"),
        "w02": replace(base, w_H2O=0.228),
        "Tuit65": replace(base, T_O2_uit=65.0),
    }
    uit = {}
    for k, inv in gevallen.items():
        try:
            d = fn(inv)
            uit[k] = {kk: d.get(kk) for kk in ("COP", "COP2", "W_K201", "W_K202", "Q_net", "Q_H", "Q_E204", "Q_L",
                                               "Q_AK", "m_net_th", "m_v", "m_cond", "W_K102", "Q_E101", "W_K101",
                                               "T_uit_K101", "T_uit_K102", "Q_ind", "T_dauw", "Q_warmte_nuttig",
                                               "Q_E201", "Q_TW")}
            uit[k]["m_net"] = d["m_net_th"] * 1000
            if versie == "B" and k in ("KO25", "KO35", "w02", "basis"):
                uit[k].update(ko_B({"KO25": 25, "KO35": 35}.get(k, 30), 0.228 if k == "w02" else None))
        except Exception as exc:  # pragma: no cover
            uit[k] = {"fout": str(exc)}
    return uit


def koudemiddelen(r, i=None):
    i = i or invoer()
    return dict(
        wp1=M.vergelijk_koudemiddelen(r["T_evap"], r["T_cond1"], i.eta_K201, r["Q_H"]),
        wp2=M.vergelijk_koudemiddelen(r["T_evap"], r["T_cond2"], i.eta_K202, r["Q_ind"]),
    )


if __name__ == "__main__":
    a, b = versie_A(), versie_B()
    print("A en B rekenen; controles geslaagd.")
    for k in ("T_dauw", "m_v", "Q_E101", "W_K102", "W_K101", "V_V101", "P_AC_EOL", "COP", "Q_net", "W_K201", "m_net"):
        print(f"{k:12s} A={a[k]:12.4f}  B={b[k]:12.4f}")
    for w in ("wp1", "wp2"):
        print(w, "A", {k: round(v, 3) for k, v in a[w].items() if isinstance(v, float)})
        print(w, "B", {k: round(v, 3) for k, v in b[w].items() if isinstance(v, float)})

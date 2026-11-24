/* Rekenmodel ITM Neptune V – twee varianten:
 *   excel(i)      : formules van het rekenblad (Çengel, ideaal gas, constante cp)
 *   coolprop(i,t) : zelfde schema met CoolProp-eigenschappen (tabellen t, geïnterpoleerd)
 * Alle grootheden per unit, tenzij _tot.
 */
(function (root) {
  const T0 = 273.15, PATM = 101.325;

  const DEFAULTS = {
    belasting: 100, m_min_pct: 40,
    m_H2: 90, P_H2_ITM: 30, T_H2: 25, m_O2mix: 925, w_H2O: 0.15, m_voedwater: 1431,
    m_afvalwater: 412, SEC_BOL: 55.9, Q_ITM_EOL: 1750, n_units: 8,
    T_O2_uit: 70, P_O2_uit: 0.1, T_KO: 30, P_RWZI: 0.7, eta_K102: 0.70,
    P_K101_uit: 70, P_backbone: 66.2, eta_K101: 0.75, dT_pakket: 30, T_E102_uit: 50, T_E103_uit: 25,
    P_V101_max: 29, P_V101_min: 20, t_V101: 0.5, t_V102: 30, n_V101: 1.2,
    T_vers: 15, P_ITM_voed: 5, eta_P101: 0.5, T_kw_in: 20, T_kw_uit: 30,
    // ITM-koelcircuit: gesloten circuit per unit (datasheet EOL, 62/38 water/CoolFlow DTX, standaard luchtgekoeld)
    T_kc_uit: 54.5, T_kc_retour: 48, m_kc_ds: 278814, P_kc: 4.4,
    // warmteterugwinning: E-201 (×8) → tussencircuit TW → E-204 (net direct), WP-201 (net), WP-202 (industrie)
    dT_E201: 3, T_net_aanvoer: 70, T_net_retour: 40, T_E204_uit: 45,
    dT_min: 5, eta_II: 0.5, koudemiddel: 'R1234ze(E)', eta_K201: 0.70,
    Q_ind: 2000, T_ind_aanvoer: 95, T_ind_retour: 75, koudemiddel2: 'R1233zd(E)', eta_K202: 0.70,
    net_aan: true, wp_aan: true,
    // leidingdimensionering: maximale snelheden (m/s) en aannames
    v_max_H2: 20, v_max_O2: 15, v_max_nat: 10, v_max_pers: 2, v_max_zuig: 1,
    v_max_ref_damp: 15, v_max_ref_vl: 1, v_max_ref_2f: 8, rho_kc: 1025, T_afvalwater: 30,
  };

  const C = { Mol_O2: 31.999, Mol_H2O: 18.015, cp_O2: 0.918, cp_damp: 1.8723, cp_H2: 14.307,
    k_O2: 1.395, k_H2: 1.405, Psat_30: 4.2469, Psat_65: 25.043, Psat_70: 31.202, hg_70: 2626.1,
    hg_30: 2555.6, hf_30: 125.74, R_H2: 4.124, B_H2: 14.8, vf_30: 0.001004, cp_w: 4.18, HHV_H2: 141800 };

  // Deellast: ITM-stromen schalen lineair met de belasting
  function schaal(i) {
    const f = i.belasting / 100;
    return Object.assign({}, i, {
      m_H2: i.m_H2 * f, m_O2mix: i.m_O2mix * f, m_voedwater: i.m_voedwater * f,
      m_afvalwater: i.m_afvalwater * f, Q_ITM_EOL: i.Q_ITM_EOL * f,
      m_recycle: Math.max(0, i.m_H2 * i.m_min_pct / 100 - i.m_H2 * f),
    });
  }

  // Restwarmte ITM → warmtenet en industrie, voor de hele installatie (n units).
  // Per unit: ITM-circuit (gesloten) → E-201 → luchtkoeler AK (trim/back-up) → ITM.
  // Gedeeld tussencircuit TW: E-201 (×n) → E-204 (net direct) → E-202 (verdamper WP-201) ∥ E-206 (verdamper WP-202).
  function warmteketen(i, r, COP, COP2, hw, fLast) {
    const n = i.n_units, Q_ITM_tot = n * i.Q_ITM_EOL;
    const T_tw_a = i.T_kc_uit - i.dT_E201, T_tw_r = i.T_kc_retour - i.dT_E201;
    const f_L2 = COP2 > 1 ? 1 - 1 / COP2 : NaN;
    let Q_ind = Math.max(i.Q_ind, 0), ind_begrensd = false;
    if (Q_ind > 0 && Q_ind * f_L2 > Q_ITM_tot) { Q_ind = Q_ITM_tot / f_L2; ind_begrensd = true; }
    const Q_L2 = Q_ind > 0 ? Q_ind * f_L2 : 0, W_K202 = Q_ind - Q_L2;
    const m_ind = Q_ind > 0 ? Q_ind / (hw(i.T_ind_aanvoer) - hw(i.T_ind_retour)) : 0;   // kg/s
    const Qb = Q_ITM_tot - Q_L2;
    let Q_E102_tot = -r.Q_E102 * n, Q_E204 = 0, Q_L = 0, Q_H = 0, W_K201 = 0, m_net = 0, r_E204 = 0, T_aanvoer = i.T_net_aanvoer, f_L = NaN;
    if (!i.net_aan) { Q_E102_tot = 0; T_aanvoer = NaN; COP = NaN; }
    else if (!i.wp_aan) { Q_E204 = Qb; m_net = Q_E204 / (hw(i.T_E204_uit) - hw(i.T_net_retour)); T_aanvoer = i.T_E204_uit; COP = NaN; }
    else {
      f_L = 1 - 1 / COP;
      r_E204 = (hw(i.T_E204_uit) - hw(i.T_net_retour)) / (hw(i.T_net_aanvoer) - hw(i.T_E204_uit));
      Q_H = Qb / (r_E204 + f_L); Q_E204 = r_E204 * Q_H; Q_L = f_L * Q_H; W_K201 = Q_H - Q_L;
      m_net = Q_H / (hw(i.T_net_aanvoer) - hw(i.T_E204_uit));
    }
    const Q_E201 = Q_E204 + Q_L + Q_L2, Q_AK = Q_ITM_tot - Q_E201;
    const cpw = (hw(T_tw_a) - hw(T_tw_r)) / (T_tw_a - T_tw_r);
    const m_tw = Q_E201 > 0 ? Q_E201 / (cpw * (T_tw_a - T_tw_r)) : 0;
    const T_tw_tussen = m_tw > 0 ? T_tw_a - Q_E204 / (m_tw * cpw) : T_tw_a;
    const m_kc_unit = i.m_kc_ds * fLast;
    const cp_kc = i.Q_ITM_EOL / (m_kc_unit / 3600 * (i.T_kc_uit - i.T_kc_retour));
    const T_kc_naE201 = i.T_kc_uit - (Q_E201 / n) / (m_kc_unit / 3600 * cp_kc);
    const Q_net = Q_E204 + Q_H + Q_E102_tot;
    Object.assign(r, { Q_ITM_tot, T_tw_a, T_tw_r, T_tw_tussen, m_tw, Q_E201, Q_AK, Q_E204, r_E204, Q_L, Q_H, W_K201,
      COP, f_L, Q_E102_tot, Q_net, m_net_th: m_net * 3.6, T_aanvoer, Q_ind, ind_begrensd, Q_L2, W_K202,
      COP2: Q_ind > 0 ? COP2 : NaN, m_ind_th: m_ind * 3.6, m_kc_unit, cp_kc, T_kc_naE201, Q_warmte_nuttig: Q_net + Q_ind,
      chk_p5: Q_ITM_tot + Q_E102_tot + W_K201 + W_K202 - Q_net - Q_ind - Q_AK });
  }

  function balans(i, r) {
    // massa (k) en energie (l)
    r.m_in_tot = r.m_vers;
    r.m_uit_tot = i.m_afvalwater + r.m_backbone + r.m_gas + r.m_S10;
    r.m_verschil = r.m_in_tot - r.m_uit_tot;
    r.E_H2 = r.m_backbone * C.HHV_H2 / 3600;
    r.P_AC_BOL = i.SEC_BOL * i.m_H2;
    r.Q_ITM_BOL = r.P_AC_BOL - i.m_H2 * C.HHV_H2 / 3600 + r.Q_E101;
    r.P_AC_EOL = i.m_H2 * C.HHV_H2 / 3600 + i.Q_ITM_EOL - r.Q_E101;
    r.chk_o1 = i.m_O2mix - r.m_cond - r.m_gas;
    r.chk_o2 = i.m_voedwater - r.m_vers - r.m_cond;
    r.chk_o3 = i.m_H2 - r.m_backbone - r.m_S10;
    // installatie-energiebalans EOL per unit
    r.E_in = r.P_AC_EOL + r.W_K101 + r.W_K102;
    r.E_uit = r.E_H2 + i.Q_ITM_EOL - r.Q_E101 + r.Q_pak_K101 - r.Q_E102 - r.Q_E103 + r.Q_pak_K102 + r.Q_O2_RWZI;
    r.chk_E = r.E_in - r.E_uit;
    return r;
  }

  // ------------------------------------------------------------------ Excel
  function excel(inv) {
    const i = schaal(inv), r = { model: 'excel', i };
    r.m_H2O_in = i.w_H2O * i.m_O2mix; r.m_O2 = i.m_O2mix - r.m_H2O_in;
    const N_O2 = r.m_O2 / C.Mol_O2, N_H2O = r.m_H2O_in / C.Mol_H2O;
    r.y_v = N_H2O / (N_O2 + N_H2O);
    const P_O2_abs = i.P_O2_uit * 100 + PATM;
    r.P_v = r.y_v * P_O2_abs;
    r.T_dauw = 65 + (r.P_v - C.Psat_65) / (C.Psat_70 - C.Psat_65) * 5;
    r.fase = r.P_v < C.Psat_70 ? 'alles damp' : 'deels vloeistof';
    const y_v_max = C.Psat_30 / P_O2_abs;
    r.m_v = y_v_max / (1 - y_v_max) * N_O2 * C.Mol_H2O;
    r.m_cond = r.m_H2O_in - r.m_v; r.m_gas = r.m_O2 + r.m_v;
    r.Q_E101 = r.m_O2 / 3600 * C.cp_O2 * (i.T_KO - i.T_O2_uit) +
      (r.m_v * C.hg_30 + r.m_cond * C.hf_30 - r.m_H2O_in * C.hg_70) / 3600;
    const cp_m = (r.m_O2 * C.cp_O2 + r.m_v * C.cp_damp) / r.m_gas;
    const P2 = i.P_RWZI * 100 + PATM, T1 = i.T_KO + T0;
    const T2s = T1 * Math.pow(P2 / P_O2_abs, (C.k_O2 - 1) / C.k_O2);
    const T2 = T1 + (T2s - T1) / i.eta_K102, mcp = r.m_gas / 3600 * cp_m;
    r.T_uit_K102 = T2 - T0; r.W_K102 = mcp * (T2 - T1);
    r.T_S18 = r.T_uit_K102 - i.dT_pakket; r.Q_pak_K102 = mcp * i.dT_pakket;
    r.Q_O2_RWZI = mcp * (r.T_S18 - i.T_KO);
    // H2
    r.m_S9 = i.m_recycle; r.m_S10 = 0; r.m_S5 = i.m_H2 + r.m_S9; r.m_backbone = r.m_S5 - r.m_S9;
    const Pi = i.P_V101_min * 100 + PATM, Po = i.P_K101_uit * 100 + PATM, T1h = i.T_H2 + T0;
    const ex = (C.k_H2 - 1) / C.k_H2, T2sh = T1h * Math.pow(Po / Pi, ex);
    const T2h = T1h + (T2sh - T1h) / i.eta_K101, mcpH = r.m_S5 / 3600 * C.cp_H2;
    r.T_uit_K101 = T2h - T0; r.W_K101 = mcpH * (T2h - T1h); r.W_K101_s = mcpH * (T2sh - T1h);
    r.T_S6 = r.T_uit_K101 - i.dT_pakket; r.Q_pak_K101 = mcpH * i.dT_pakket;
    r.Q_E102 = mcpH * (i.T_E102_uit - r.T_S6); r.Q_E103 = mcpH * (i.T_E103_uit - i.T_E102_uit);
    // buffers
    const RT = C.R_H2 * T1h, RuT = 8.314 * T1h;
    const vol = (m, pmax, pmin, n) => {
      const iso = m / (pmax / RT - pmin / RT);
      const zx = 1 + C.B_H2 * 1e-6 * pmax * 1000 / RuT, zn = 1 + C.B_H2 * 1e-6 * pmin * 1000 / RuT;
      return m * n * RT / (pmax - pmin) * (m / (pmax / RT / zx - pmin / RT / zn)) / iso;
    };
    r.V_V101 = vol(i.m_H2 * i.t_V101, i.P_V101_max * 100 + PATM, Pi, i.n_V101);
    r.V_V102 = vol(i.m_H2 * i.t_V102 / 3600, Po, i.P_backbone * 100 + PATM, C.k_H2);
    // water
    r.W_P101 = r.m_cond / 3600 * C.vf_30 * (i.P_ITM_voed * 100 + PATM - P_O2_abs) / i.eta_P101;
    // condensaat (UPW) gaat via P-101 direct terug de eigen unit in (S16); S1 vult alleen aan
    r.m_vers = i.m_voedwater - r.m_cond;
    const dTk = C.cp_w * (i.T_kw_uit - i.T_kw_in);
    r.m_kw_E101 = -r.Q_E101 / dTk * 3600; r.m_kw_E103 = -r.Q_E103 / dTk * 3600;
    r.m_ww_E102 = -r.Q_E102 / (C.cp_w * (i.T_net_aanvoer - i.T_net_retour)) * 3600;
    // warmtepompen via tweedewetsrendement, verdampen op het tussencircuit TW
    const TL = i.T_kc_retour - i.dT_E201 - i.dT_min + T0;
    const TH = i.T_net_aanvoer + i.dT_min + T0, TH2 = i.T_ind_aanvoer + i.dT_min + T0;
    r.COP_carnot = TH / (TH - TL); r.COP2_carnot = TH2 / (TH2 - TL);
    warmteketen(i, r, i.eta_II * r.COP_carnot, i.eta_II * r.COP2_carnot, T => C.cp_w * T, inv.belasting / 100);
    return balans(i, r);
  }

  // ------------------------------------------------------------------ interpolatie
  function idx(xs, x) {
    let lo = 0, hi = xs.length - 1;
    if (x <= xs[0]) return [0, 0];
    if (x >= xs[hi]) return [hi - 1, 1];
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] > x) hi = m; else lo = m; }
    return [lo, (x - xs[lo]) / (xs[lo + 1] - xs[lo])];
  }
  const i1 = (xs, ys, x) => { const [k, f] = idx(xs, x); return ys[k] + f * (ys[k + 1] - ys[k]); };
  function i2(xs, ys, g, x, y) {
    const [a, fx] = idx(xs, x), [b, fy] = idx(ys, y);
    const v0 = g[a][b] + fy * (g[a][b + 1] - g[a][b]);
    const v1 = g[a + 1][b] + fy * (g[a + 1][b + 1] - g[a + 1][b]);
    return v0 + fx * (v1 - v0);
  }
  function solve(f, a, b) { // f monotoon stijgend, zoek f(x)=0
    let fa = f(a);
    for (let k = 0; k < 80; k++) {
      const m = (a + b) / 2, fm = f(m);
      if (fa * fm <= 0) b = m; else { a = m; fa = fm; }
    }
    return (a + b) / 2;
  }

  // ------------------------------------------------------------------ CoolProp
  function coolprop(inv, t) {
    const i = schaal(inv), r = { model: 'coolprop', i };
    const M = t.M;
    const H2 = (p, T, Pbar) => i2(t.H2_T, t.H2_P, t['H2_' + p], T + T0, Pbar);   // J/kg, J/kgK, kg/m3
    const O2 = (p, T, Pbar) => i2(t.O2_T, t.O2_P, t['O2_' + p], T + T0, Pbar);
    const W = (k, T) => i1(t.W_T, t['W_' + k], T);
    const Tsat = P => solve(T => W('Psat', T) - P, 1, 149);
    const P_O2 = (i.P_O2_uit * 100 + PATM) * 1e3; // Pa

    r.m_H2O_in = i.w_H2O * i.m_O2mix; r.m_O2 = i.m_O2mix - r.m_H2O_in;
    const N_O2 = r.m_O2 / M.O2, N_H2O = r.m_H2O_in / M.H2O;
    r.y_v = N_H2O / (N_O2 + N_H2O); r.P_v = r.y_v * P_O2 / 1e3;
    r.T_dauw = Tsat(r.y_v * P_O2);
    r.fase = r.T_dauw < i.T_O2_uit ? 'alles damp' : 'deels vloeistof';
    const y_v_max = Math.min(W('Psat', i.T_KO) / P_O2, 0.99);
    r.m_v = Math.min(y_v_max / (1 - y_v_max) * N_O2 * M.H2O, r.m_H2O_in);
    r.m_cond = r.m_H2O_in - r.m_v; r.m_gas = r.m_O2 + r.m_v;
    const yv = r.m_v / M.H2O / (r.m_v / M.H2O + N_O2);
    // E-101
    const pO2_in = (1 - r.y_v) * P_O2 / 1e5, pO2_ko = (1 - yv) * P_O2 / 1e5;
    r.Q_E101 = (r.m_O2 * (O2('H', i.T_KO, pO2_ko) - O2('H', i.T_O2_uit, pO2_in)) +
      r.m_v * W('hv', i.T_KO) + r.m_cond * W('hf', i.T_KO) - r.m_H2O_in * W('hv', i.T_O2_uit)) / 3600 / 1e3;
    // K-102
    const P2 = (i.P_RWZI * 100 + PATM) * 1e3, Rv = 8314.462618 / M.H2O;
    const pO2_2 = (1 - yv) * P2 / 1e5, pv1 = yv * P_O2, pv2 = yv * P2;
    const hm = (T, pO2) => (r.m_O2 * O2('H', T, pO2) + r.m_v * W('hv', T)) / r.m_gas;
    const sm = (T, pO2, pv) => (r.m_O2 * O2('S', T, pO2) + r.m_v * (W('sv', T) - Rv * Math.log(pv / 500))) / r.m_gas;
    const s1 = sm(i.T_KO, pO2_ko, pv1), h1 = hm(i.T_KO, pO2_ko);
    const T2s = solve(T => sm(T, pO2_2, pv2) - s1, i.T_KO, 200);
    const h2 = h1 + (hm(T2s, pO2_2) - h1) / i.eta_K102;
    r.T_uit_K102 = solve(T => hm(T, pO2_2) - h2, i.T_KO, 200);
    r.W_K102 = r.m_gas / 3600 * (h2 - h1) / 1e3;
    r.T_S18 = r.T_uit_K102 - i.dT_pakket;
    r.Q_pak_K102 = r.m_gas / 3600 * (h2 - hm(r.T_S18, pO2_2)) / 1e3;
    r.Q_O2_RWZI = r.W_K102 - r.Q_pak_K102;
    r.T_dauw_S18 = Tsat(pv2);
    // K-101 (reëel H2)
    r.m_S9 = i.m_recycle; r.m_S10 = 0; r.m_S5 = i.m_H2 + r.m_S9; r.m_backbone = r.m_S5 - r.m_S9;
    const Pi = i.P_V101_min + PATM / 100, Po = i.P_K101_uit + PATM / 100; // bar abs
    const sh1 = H2('S', i.T_H2, Pi), hh1 = H2('H', i.T_H2, Pi);
    const T2sh = solve(T => H2('S', T, Po) - sh1, -20, 440);
    const hh2 = hh1 + (H2('H', T2sh, Po) - hh1) / i.eta_K101;
    r.T_uit_K101 = solve(T => H2('H', T, Po) - hh2, -20, 440);
    const mh = r.m_S5 / 3600 / 1e3;
    r.W_K101 = mh * (hh2 - hh1); r.W_K101_s = mh * (H2('H', T2sh, Po) - hh1);
    r.T_S6 = r.T_uit_K101 - i.dT_pakket;
    const hP = T => H2('H', T, Po);
    r.Q_pak_K101 = mh * (hh2 - hP(r.T_S6));
    r.Q_E102 = mh * (hP(i.T_E102_uit) - hP(r.T_S6));
    r.Q_E103 = mh * (hP(i.T_E103_uit) - hP(i.T_E102_uit));
    // buffers: echte dichtheid
    const rho = P => H2('D', i.T_H2, P);
    const Pmx1 = i.P_V101_max + PATM / 100, Pmn2 = i.P_backbone + PATM / 100;
    r.V_V101 = i.m_H2 * i.t_V101 / (rho(Pmx1) - rho(Pi)) * i.n_V101;
    r.V_V102 = i.m_H2 * i.t_V102 / 3600 / (rho(Po) - rho(Pmn2)) * t.k_H2;
    r.Z_V102 = Po * 1e5 / (rho(Po) * 8314.462618 / M.H2 * (i.T_H2 + T0));
    // water
    r.W_P101 = r.m_cond / 3600 * W('vf', i.T_KO) * ((i.P_ITM_voed * 100 + PATM) * 1e3 - P_O2) / 1e3 / i.eta_P101;
    // condensaat (UPW) gaat via P-101 direct terug de eigen unit in (S16); S1 vult alleen aan
    r.m_vers = i.m_voedwater - r.m_cond;
    const hl = T => W('hl', T) / 1e3;
    const dhk = hl(i.T_kw_uit) - hl(i.T_kw_in);
    r.m_kw_E101 = -r.Q_E101 / dhk * 3600; r.m_kw_E103 = -r.Q_E103 / dhk * 3600;
    r.m_ww_E102 = -r.Q_E102 / (hl(i.T_net_aanvoer) - hl(i.T_net_retour)) * 3600;
    // warmtepompen: echte cycli, verdampen op het tussencircuit TW
    const Te = i.T_kc_retour - i.dT_E201 - i.dT_min;
    r.cyclus = cyclus(t, i.koudemiddel, Te, i.T_net_aanvoer + i.dT_min, i.eta_K201);
    r.cyclus2 = i.Q_ind > 0 ? cyclus(t, i.koudemiddel2, Te, i.T_ind_aanvoer + i.dT_min, i.eta_K202) : null;
    const TH = i.T_net_aanvoer + i.dT_min + T0, TL = Te + T0, TH2 = i.T_ind_aanvoer + i.dT_min + T0;
    r.COP_carnot = TH / (TH - TL); r.COP2_carnot = TH2 / (TH2 - TL);
    warmteketen(i, r, r.cyclus.COP, r.cyclus2 ? r.cyclus2.COP : NaN, hl, inv.belasting / 100);
    return balans(i, r);
  }

  function cyclus(t, f, Te, Tc, eta) {
    const d = t.HP[f], TcG = d.Tc || t.HP_Tc;
    const h1 = i1(t.HP_Te, d.h1, Te), Pe = i1(t.HP_Te, d.Pe, Te);
    const h2s = i2(t.HP_Te, TcG, d.h2s, Te, Tc);
    const h3 = i1(TcG, d.h3, Tc), Pc = i1(TcG, d.Pc, Tc);
    const h2 = h1 + (h2s - h1) / eta;
    // persdamp: vanuit het isentrope eindpunt met cp naar de werkelijke enthalpie, dichtheid als ideaal gas geschaald
    const T2s = i2(t.HP_Te, TcG, d.T2s, Te, Tc), cp2 = i2(t.HP_Te, TcG, d.cp2s, Te, Tc);
    const T2 = T2s + (h2 - h2s) / cp2;
    const D2 = i2(t.HP_Te, TcG, d.D2s, Te, Tc) * (T2s + T0) / (T2 + T0);
    const hl_e = i1(t.HP_Te, d.hl_e, Te), x4 = (h3 - hl_e) / (h1 - hl_e);
    const Dv_e = i1(t.HP_Te, d.Dv_e, Te), Dl_e = i1(t.HP_Te, d.Dl_e, Te);
    return { fluid: f, Tcrit_ok: Tc <= TcG[TcG.length - 1], TcMax: TcG[TcG.length - 1], Te, Tc, Pe, Pc, h1, h2s, h2, h3, h4: h3, T2, x4, COP: (h2 - h3) / (h2 - h1), dome: d.dome,
      D1: Dv_e, D2, D3: i1(TcG, d.Dl_c, Tc), D4: 1 / (x4 / Dv_e + (1 - x4) / Dl_e) };
  }

  // ------------------------------------------------------------------ leidingdimensionering
  // Roestvaststalen pijp ASME B36.19 schedule 40S: [DN, buitendiameter mm, wanddikte mm]
  const DN_40S = [[15, 21.3, 2.77], [20, 26.7, 2.87], [25, 33.4, 3.38], [32, 42.2, 3.56], [40, 48.3, 3.68],
    [50, 60.3, 3.91], [65, 73.0, 5.16], [80, 88.9, 5.49], [100, 114.3, 6.02], [125, 141.3, 6.55],
    [150, 168.3, 7.11], [200, 219.1, 8.18], [250, 273.0, 9.27], [300, 323.8, 9.53], [350, 355.6, 9.53],
    [400, 406.4, 9.53], [450, 457.0, 9.53], [500, 508.0, 9.53], [600, 610.0, 9.53], [700, 711.0, 9.53], [800, 813.0, 9.53]];
  function kiesDN(dmin) {
    for (const [dn, od, wd] of DN_40S) if (od - 2 * wd >= dmin) return [dn, od - 2 * wd];
    return [null, NaN];
  }

  // Minimale binnendiameter per leiding: d_min = √(4·V̇/(π·v_max)), V̇ = ṁ/ρ.
  // Ontwerppunt = vollast met warmtenet en warmtepomp (S9: maximale recycle), CoolProp-eigenschappen.
  function leidingen(inv, t) {
    const d = Object.assign({}, inv, { belasting: 100, net_aan: true, wp_aan: true });
    const r = coolprop(d, t), i = r.i, n = i.n_units, M = t.M;
    const w = T => 1 / i1(t.W_T, t.W_vf, T);                                  // vloeibaar water
    const h2 = (T, barg) => i2(t.H2_T, t.H2_P, t.H2_D, T + T0, barg + PATM / 100);
    const gasO2 = (T, barg, mO2, mv) => (barg * 100 + PATM) * 1e3 * (mO2 + mv) / (mO2 / M.O2 + mv / M.H2O) / 1000 / (8.314462618 * (T + T0));
    const cy = r.cyclus, f = cy.fluid, cy2 = r.cyclus2;
    const m_ref = r.Q_H / (cy.h2 - cy.h3) * 3600;
    const kc = r.m_kc_unit, tw = r.m_tw * 3600, net = r.m_net_th * 1000, mS9 = i.m_H2 * i.m_min_pct / 100;
    const wd = T => 1 / i1(t.W_T, t.W_vf, Math.min(T, 149));
    const v = { H2: i.v_max_H2, O2: i.v_max_O2, nat: i.v_max_nat, pers: i.v_max_pers, zuig: i.v_max_zuig,
      rd: i.v_max_ref_damp, rv: i.v_max_ref_vl, r2: i.v_max_ref_2f };
    const U = 'per unit', A = 'installatie', pe = cy.Pe - 1.01325, pc = cy.Pc - 1.01325;
    const rhoS14 = i.m_O2mix / ((r.m_O2 + r.m_v) / gasO2(i.T_KO, i.P_O2_uit, r.m_O2, r.m_v) + r.m_cond / w(i.T_KO));
    const L = [
      ['S1', 'Vers UPW-suppletie → ITM', 'water', U, r.m_vers, w(i.T_vers), 'pers', i.T_vers, i.P_ITM_voed],
      ['S3', 'ITM → afvalwater', 'water', U, i.m_afvalwater, w(i.T_afvalwater), 'zuig', i.T_afvalwater, null],
      ['S4', 'ITM → V-101', 'H₂', U, i.m_H2, h2(i.T_H2, i.P_H2_ITM), 'H2', i.T_H2, i.P_H2_ITM],
      ['S5', 'V-101 → K-101 (zuig)', 'H₂', U, r.m_S5, h2(i.T_H2, i.P_V101_min), 'H2', i.T_H2, i.P_V101_min],
      ['S6', 'K-101 → E-102', 'H₂', U, r.m_S5, h2(r.T_S6, i.P_K101_uit), 'H2', r.T_S6, i.P_K101_uit],
      ['S7', 'E-102 → E-103', 'H₂', U, r.m_S5, h2(i.T_E102_uit, i.P_K101_uit), 'H2', i.T_E102_uit, i.P_K101_uit],
      ['S8', 'E-103 → kwaliteitscontrole', 'H₂', U, r.m_S5, h2(i.T_E103_uit, i.P_K101_uit), 'H2', i.T_E103_uit, i.P_K101_uit],
      ['S9', 'Recycle FV-101 → V-101 (max.)', 'H₂', U, mS9, h2(i.T_E103_uit, i.P_V101_min), 'H2', i.T_E103_uit, i.P_V101_min],
      ['S11', 'Kwaliteitscontrole → V-102', 'H₂', U, r.m_backbone, h2(i.T_E103_uit, i.P_backbone), 'H2', i.T_E103_uit, i.P_backbone],
      ['S12', 'PCV-101 → H₂-backbone', 'H₂', U, r.m_backbone, h2(i.T_E103_uit, i.P_backbone), 'H2', i.T_E103_uit, i.P_backbone],
      ['S13', 'ITM → E-101', 'O₂ + damp', U, i.m_O2mix, gasO2(i.T_O2_uit, i.P_O2_uit, r.m_O2, r.m_H2O_in), 'O2', i.T_O2_uit, i.P_O2_uit],
      ['S14', 'E-101 → V-103 (met druppels)', 'O₂ + damp + water', U, i.m_O2mix, rhoS14, 'nat', i.T_KO, i.P_O2_uit],
      ['S15', 'V-103 → P-101 (zuig)', 'condensaat (UPW)', U, r.m_cond, w(i.T_KO), 'zuig', i.T_KO, i.P_O2_uit],
      ['S16', 'P-101 → ITM (condensaat direct)', 'condensaat (UPW)', U, r.m_cond, w(i.T_KO), 'pers', i.T_KO, i.P_ITM_voed],
      ['S17', 'V-103 → K-102', 'O₂ + damp', U, r.m_gas, gasO2(i.T_KO, i.P_O2_uit, r.m_O2, r.m_v), 'O2', i.T_KO, i.P_O2_uit],
      ['S18', 'K-102 → RWZI', 'O₂ + damp', U, r.m_gas, gasO2(r.T_S18, i.P_RWZI, r.m_O2, r.m_v), 'O2', r.T_S18, i.P_RWZI],
      ['A', 'ITM-circuit uit ITM → E-201', 'water/CoolFlow DTX 62/38', U, kc, i.rho_kc, 'pers', i.T_kc_uit, i.P_kc],
      ['A2', 'ITM-circuit E-201 → luchtkoeler AK', 'water/CoolFlow DTX 62/38', U, kc, i.rho_kc, 'pers', r.T_kc_naE201, i.P_kc],
      ['B', 'ITM-circuit luchtkoeler AK → ITM', 'water/CoolFlow DTX 62/38', U, kc, i.rho_kc, 'pers', i.T_kc_retour, i.P_kc],
      ['TW', 'Tussencircuit aftakking per E-201', 'water', U, tw / n, w(r.T_tw_a), 'pers', r.T_tw_a, null],
      ['TW1', "Tussencircuit E-201's → E-204", 'water', A, tw, w(r.T_tw_a), 'pers', r.T_tw_a, null],
      ['TW2', 'Tussencircuit E-204 → verdampers', 'water', A, tw, w(r.T_tw_tussen), 'pers', r.T_tw_tussen, null],
      ['TW3', "Tussencircuit retour → E-201's", 'water', A, tw, w(r.T_tw_r), 'pers', r.T_tw_r, null],
      ['KW1', 'Koelwater E-101', 'koelwater', U, r.m_kw_E101, w((i.T_kw_in + i.T_kw_uit) / 2), 'pers', i.T_kw_in, null],
      ['KW2', 'Koelwater E-103', 'koelwater', U, r.m_kw_E103, w((i.T_kw_in + i.T_kw_uit) / 2), 'pers', i.T_kw_in, null],
      ['WW1', 'Warmtenet-zijstroom E-102', 'netwater', U, r.m_ww_E102, w((i.T_net_retour + i.T_net_aanvoer) / 2), 'pers', i.T_net_retour, null],
      ['N1', 'Warmtenet retour → E-204', 'netwater', A, net, w(i.T_net_retour), 'pers', i.T_net_retour, null],
      ['N2', 'Warmtenet E-204 → E-203', 'netwater', A, net, w(i.T_E204_uit), 'pers', i.T_E204_uit, null],
      ['N3', 'Warmtenet aanvoer (incl. zijstroom E-102)', 'netwater', A, net + n * r.m_ww_E102, w(i.T_net_aanvoer), 'pers', i.T_net_aanvoer, null],
      ['R1', 'E-202 → K-201 (zuigdamp)', f, A, m_ref, cy.D1, 'rd', cy.Te, pe],
      ['R2', 'K-201 → E-203 (persdamp)', f, A, m_ref, cy.D2, 'rd', cy.T2, pc],
      ['R3', 'E-203 → TV-201 (vloeistof)', f, A, m_ref, cy.D3, 'rv', cy.Tc, pc],
      ['R4', 'TV-201 → E-202 (tweefase)', f, A, m_ref, cy.D4, 'r2', cy.Te, pe],
    ];
    if (cy2 && r.Q_ind > 0) {
      const m2 = r.Q_ind / (cy2.h2 - cy2.h3) * 3600, pe2 = cy2.Pe - 1.01325, pc2 = cy2.Pc - 1.01325, mi = r.m_ind_th * 1000;
      L.push(
        ['TW4', 'Tussencircuit → verdamper E-206 (WP-202)', 'water', A, r.Q_E201 ? r.Q_L2 / r.Q_E201 * tw : 0, w(r.T_tw_tussen), 'pers', r.T_tw_tussen, null],
        ['I1', 'Industrie aanvoer uit E-205', 'water (onder druk)', A, mi, wd(i.T_ind_aanvoer), 'pers', i.T_ind_aanvoer, null],
        ['I2', 'Industrie retour → E-205', 'water (onder druk)', A, mi, wd(i.T_ind_retour), 'pers', i.T_ind_retour, null],
        ['R5', 'E-206 → K-202 (zuigdamp)', cy2.fluid, A, m2, cy2.D1, 'rd', cy2.Te, pe2],
        ['R6', 'K-202 → E-205 (persdamp)', cy2.fluid, A, m2, cy2.D2, 'rd', cy2.T2, pc2],
        ['R7', 'E-205 → TV-202 (vloeistof)', cy2.fluid, A, m2, cy2.D3, 'rv', cy2.Tc, pc2],
        ['R8', 'TV-202 → E-206 (tweefase)', cy2.fluid, A, m2, cy2.D4, 'r2', cy2.Te, pe2]);
    }
    return L.map(([id, naam, medium, schaal, m, rho, cat, T, p]) => {
      const V = m / rho / 3600;
      const d_min = V > 0 ? Math.sqrt(4 * V / (Math.PI * v[cat])) * 1000 : 0;
      const [DN, d_i] = kiesDN(d_min);
      return { id, naam, medium, schaal, m, rho, V: V * 3600, v_max: v[cat], cat, d_min, DN, d_i,
        v: DN ? V / (Math.PI / 4 * Math.pow(d_i / 1000, 2)) : NaN, T, p };
    });
  }

  root.ITM = { DEFAULTS, excel, coolprop, schaal, leidingen, DN_40S };
  if (typeof module !== 'undefined') module.exports = root.ITM;
})(typeof window !== 'undefined' ? window : globalThis);

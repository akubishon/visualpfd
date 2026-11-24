"""Figuren voor het rekenverslag: PFD (per unit en warmteketen), log p-h, T-s en T-Q-diagrammen."""
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator  # noqa: E402

import CoolProp.CoolProp as CP  # noqa: E402
import itm_model as M  # noqa: E402

PS = CP.PropsSI
T0 = 273.15

plt.rcParams.update({
    "font.family": "serif", "mathtext.fontset": "cm", "font.size": 9, "axes.titlesize": 10,
    "axes.labelsize": 9, "legend.fontsize": 7.5, "savefig.bbox": "tight", "savefig.pad_inches": 0.03,
})


def komma(x, _=None):
    s = f"{x:g}"
    return s.replace(".", ",").replace("-", "−")


def nl_assen(ax):
    ax.xaxis.set_major_formatter(FuncFormatter(komma))
    ax.yaxis.set_major_formatter(FuncFormatter(komma))


def nlt(x, d=1):
    s = f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    return s.replace("-", "−")


KL = dict(H2="#1f5fa8", O2="#2a8a3e", w="#3aa0c8", TW="#e07b00", net="#c62828", ref="#6a3d9a",
          kw="#00838f", kc="#8d5524", ind="#ad1457", grijs="#555555")


# ================================================================== PFD-tekenhulp
class Tekening:
    def __init__(self, w, h, titel):
        self.fig, self.ax = plt.subplots(figsize=(w, h))
        self.ax.set_xlim(0, w * 10)
        self.ax.set_ylim(0, h * 10)
        self.ax.set_aspect("equal")
        self.ax.axis("off")
        self.ax.set_title(titel, fontsize=11, fontweight="bold", loc="left")

    def box(self, x, y, w, h, tekst, kleur="#f3f3f3", fs=8, rand="#333"):
        self.ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.3,rounding_size=1.2",
                                         fc=kleur, ec=rand, lw=1.1, zorder=3))
        self.ax.text(x, y, tekst, ha="center", va="center", fontsize=fs, zorder=4)

    def vat(self, x, y, w, h, tag, onder=None):
        self.ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle=f"round,pad=0,rounding_size={w/2*0.9}",
                                         fc="white", ec="#333", lw=1.2, zorder=3))
        self.ax.text(x, y, tag, ha="center", va="center", fontsize=7.5, rotation=90, zorder=4, fontweight="bold")
        if onder:
            self.ax.text(x, y - h / 2 - 2.2, onder, ha="center", va="top", fontsize=6.5, zorder=4)

    def hx(self, x, y, tag, r=3.2, onder=None, kl_w="#c62828", kl_k="#1565c0", rechts=False):
        self.ax.add_patch(Circle((x, y), r, fc="white", ec="#333", lw=1.2, zorder=3))
        zig = np.array([[-r * 0.8, -r * 0.1], [-r * 0.4, r * 0.45], [0, -r * 0.45], [r * 0.4, r * 0.45], [r * 0.8, -r * 0.1]])
        self.ax.plot(x + zig[:, 0], y + zig[:, 1], color=kl_k, lw=1.0, zorder=4)
        self.ax.text(x, y + r + 1.0, tag, ha="center", va="bottom", fontsize=7, fontweight="bold", zorder=4)
        if onder and rechts:
            self.ax.text(x + r * 0.5, y - r - 0.6, onder, ha="left", va="top", fontsize=6.3, zorder=4)
        elif onder:
            self.ax.text(x, y - r - 1.0, onder, ha="center", va="top", fontsize=6.3, zorder=4)

    def comp(self, x, y, tag, r=3.4, onder=None):
        self.ax.add_patch(Circle((x, y), r, fc="white", ec="#333", lw=1.2, zorder=3))
        self.ax.plot([x - r * 0.95, x + r * 0.95], [y + r * 0.3, y + r * 0.75], color="#333", lw=1, zorder=4)
        self.ax.plot([x - r * 0.95, x + r * 0.95], [y - r * 0.3, y - r * 0.75], color="#333", lw=1, zorder=4)
        self.ax.text(x, y + r + 1.0, tag, ha="center", va="bottom", fontsize=7, fontweight="bold", zorder=4)
        if onder:
            self.ax.text(x, y - r - 1.0, onder, ha="center", va="top", fontsize=6.3, zorder=4)

    def pomp(self, x, y, tag, r=2.6, onder=None):
        self.ax.add_patch(Circle((x, y), r, fc="white", ec="#333", lw=1.2, zorder=3))
        self.ax.add_patch(Polygon([[x - r * 0.5, y - r * 0.6], [x - r * 0.5, y + r * 0.6], [x + r * 0.7, y]],
                                  fc="#ddd", ec="#333", lw=0.8, zorder=4))
        self.ax.text(x, y + r + 1.0, tag, ha="center", va="bottom", fontsize=7, fontweight="bold", zorder=4)
        if onder:
            self.ax.text(x, y - r - 1.0, onder, ha="center", va="top", fontsize=6.3, zorder=4)

    def klep(self, x, y, tag, s=1.6, vert=False):
        if vert:
            pts1 = [[x - s, y - s], [x + s, y - s], [x, y]]
            pts2 = [[x - s, y + s], [x + s, y + s], [x, y]]
        else:
            pts1 = [[x - s, y - s], [x - s, y + s], [x, y]]
            pts2 = [[x + s, y - s], [x + s, y + s], [x, y]]
        for p in (pts1, pts2):
            self.ax.add_patch(Polygon(p, fc="white", ec="#333", lw=1.0, zorder=4))
        self.ax.text(x, y + s + 0.8, tag, ha="center", va="bottom", fontsize=6.5, fontweight="bold", zorder=4)

    def lijn(self, pts, kleur, label=None, li=None, pijl=True, lw=1.4, ls="-", fs=6.3, lpos=0.5, loff=(0, 1.2),
             ha="center"):
        pts = np.array(pts, float)
        self.ax.plot(pts[:, 0], pts[:, 1], color=kleur, lw=lw, ls=ls, zorder=2, solid_capstyle="butt")
        if pijl:
            a, b = pts[-2], pts[-1]
            self.ax.annotate("", xy=b, xytext=a + (b - a) * 0.0001 + (b - a) * 0.999 - (b - a) / max(np.linalg.norm(b - a), 1e-9) * 2.2,
                             arrowprops=dict(arrowstyle="-|>", color=kleur, lw=lw, mutation_scale=9), zorder=5)
        if label:
            k = li if li is not None else max(0, len(pts) // 2 - 1)
            a, b = pts[k], pts[k + 1]
            m = a + (b - a) * lpos
            self.ax.text(m[0] + loff[0], m[1] + loff[1], label, ha=ha, va="bottom", fontsize=fs, color=kleur, zorder=6,
                         bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.85))

    def tekst(self, x, y, s, fs=6.5, kleur="#222", ha="center", va="center", **kw):
        self.ax.text(x, y, s, ha=ha, va=va, fontsize=fs, color=kleur, zorder=6, **kw)

    def opslaan(self, pad):
        self.fig.savefig(pad)
        plt.close(self.fig)


def pfd_unit(r, i, pad):
    T = Tekening(17, 10.4, "PFD blad 1 – één ITM-unit (×8 parallel): H$_2$-lijn, O$_2$-lijn en water")
    d = T
    # ITM
    d.box(18, 52, 16, 26, "ITM\nNeptune V\n\n" + f"{nlt(i.m_H2, 0)} kg/h H$_2$\nEOL\n{nlt(r['P_AC_EOL'], 0)} kW$_e$",
          kleur="#e8eef7", fs=8)
    # H2-lijn (boven)
    yH = 88
    d.vat(40, yH, 6, 13, "V-101", onder=f"{nlt(r['V_V101'], 1)} m³\n20–29 barg")
    d.comp(58, yH, "K-101", onder=f"{nlt(r['W_K101'], 1)} kW\nη$_s$ = {nlt(i.eta_K101, 2)}")
    d.hx(72, yH, "PK-101", r=2.6, onder=f"pakketkoeler\n{nlt(r['Q_pak_K101'], 1)} kW", rechts=True)
    d.hx(88, yH, "E-102", onder=f"{nlt(r['Q_E102'], 1)} kW", rechts=True)
    d.hx(104, yH, "E-103", onder=f"{nlt(r['Q_E103'], 1)} kW", rechts=True)
    d.box(120, yH, 9, 7, "kwaliteits-\ncontrole", fs=6)
    d.vat(136, yH, 6, 13, "V-102", onder=f"{nlt(r['V_V102'], 2)} m³")
    d.klep(149, yH, "PCV-101")
    d.lijn([(26, 62), (26, yH), (37, yH)], KL["H2"], f"S4  {nlt(i.m_H2,0)} kg/h\n25 °C · 30 barg", li=1, lpos=0.45)
    d.lijn([(43, yH), (54.6, yH)], KL["H2"], "S5", lpos=0.5)
    d.lijn([(61.4, yH), (69.4, yH)], KL["H2"], None)
    d.tekst(65, yH + 2.6, f"{nlt(r['T_uit_K101'], 0)} °C", fs=6, kleur=KL["H2"])
    d.lijn([(74.6, yH), (84.8, yH)], KL["H2"], f"S6  {nlt(r['T_S6'], 0)} °C", lpos=0.5)
    d.lijn([(91.2, yH), (100.8, yH)], KL["H2"], f"S7  {nlt(i.T_E102_uit, 0)} °C")
    d.lijn([(107.2, yH), (115.5, yH)], KL["H2"], f"S8  {nlt(i.T_E103_uit, 0)} °C\n70 barg", lpos=0.62)
    d.lijn([(124.5, yH), (133, yH)], KL["H2"], "S11")
    d.lijn([(139, yH), (147.4, yH)], KL["H2"], None)
    d.lijn([(150.6, yH), (166, yH)], KL["H2"], f"S12  {nlt(i.m_H2,0)} kg/h\n66,2 barg → backbone", lpos=0.55)
    # recycle S9 + FV-101
    d.lijn([(111, yH), (111, 100), (40, 100), (40, yH + 6.5)], KL["H2"], "S9 recycle (0 kg/h bij vollast)", li=1,
           lpos=0.5, ls="--", lw=1.0)
    d.klep(75, 100, "FV-101")
    d.lijn([(40, yH + 6.5), (40, yH + 6.6)], KL["H2"], None, pijl=False)
    d.lijn([(43, yH + 4), (47, yH + 4), (47, 102.5)], KL["grijs"], "S10 blowoff", li=1, lpos=0.6, lw=0.9, loff=(5, -1))
    # koelmedia H2-lijn
    d.lijn([(72, 78), (72, yH - 2.6)], KL["TW"], "TW", li=0, lpos=0.1, loff=(-3, 0), lw=1.0)
    d.lijn([(88, 78), (88, yH - 3.2)], KL["TW"], "TW 45 °C", li=0, lpos=0.1, loff=(-5, 0), lw=1.0)
    d.lijn([(104, 78), (104, yH - 3.2)], KL["kw"], "KW2 20 °C", li=0, lpos=0.1, loff=(-6, 0), lw=1.0)
    # O2-lijn (onder)
    yO = 32
    d.hx(48, yO, "E-101", onder=f"{nlt(r['Q_E101'], 1)} kW", rechts=True)
    d.vat(68, yO + 2, 7, 15, "V-103", onder="KO-drum\n30 °C")
    d.comp(92, yO + 12, "K-102", onder=f"{nlt(r['W_K102'], 1)} kW\nη$_s$ = {nlt(i.eta_K102, 2)}")
    d.hx(108, yO + 12, "PK-102", r=2.6, onder="pakket-\nkoeler")
    d.pomp(68, 9, "P-101", onder=f"{nlt(r['W_P101']*1000, 0)} W")
    d.lijn([(26, 44), (26, yO), (44.8, yO)], KL["O2"], f"S13  {nlt(i.m_O2mix,0)} kg/h\nO$_2$+damp 70 °C", li=1, lpos=0.4)
    d.lijn([(51.2, yO), (64.5, yO)], KL["O2"], "S14", lpos=0.55)
    d.lijn([(68, yO + 9.5), (68, yO + 12), (88.6, yO + 12)], KL["O2"], f"S17  {nlt(r['m_gas'],1)} kg/h\n30 °C · 0,1 barg",
           li=1, lpos=0.5)
    d.lijn([(95.4, yO + 12), (105.4, yO + 12)], KL["O2"], f"{nlt(r['T_uit_K102'],0)} °C", lpos=0.5, fs=6)
    d.lijn([(110.6, yO + 12), (150, yO + 12)], KL["O2"], f"S18  {nlt(r['T_S18'],0)} °C · 0,7 barg → RWZI", lpos=0.5)
    d.lijn([(68, yO - 5.5), (68, 11.6)], KL["w"], f"S15\n{nlt(r['m_cond'],1)} kg/h", li=0, lpos=0.45, loff=(7, -2))
    d.lijn([(65.4, 9), (14, 9), (14, 39)], KL["w"], "S16 condensaat (UPW) → ITM", li=0, lpos=0.5)
    d.lijn([(48, yO - 12), (48, yO - 3.2)], KL["kw"], "KW1 20 °C", li=0, lpos=0.1, loff=(-6, 0), lw=1.0)
    # water ITM
    d.lijn([(1, 58), (10, 58)], KL["w"], f"S1 UPW\n{nlt(r['m_vers'],0)} kg/h", lpos=0.2, loff=(0, 1))
    d.lijn([(22, 39), (22, 20), (35, 20)], KL["w"], f"S3 afvalwater {nlt(i.m_afvalwater,0)} kg/h", li=1, lpos=0.5,
           loff=(3, 0.6))
    # ITM-circuit
    d.lijn([(10, 47), (2, 47)], KL["kc"], "A → E-201\n(blad 2)", lpos=0.4, loff=(0, 1))
    d.lijn([(2, 44), (10, 44)], KL["kc"], None)
    d.tekst(5, 41.5, "B ← AK", fs=6, kleur=KL["kc"])
    # legenda
    leg = [("H$_2$", KL["H2"]), ("O$_2$ + waterdamp", KL["O2"]), ("water / condensaat", KL["w"]),
           ("koelwatercircuit TW", KL["TW"]), ("koelwater 20→30 °C", KL["kw"]), ("ITM-koelcircuit", KL["kc"])]
    for k, (s, c) in enumerate(leg):
        d.ax.plot([122, 128], [26 - k * 3.6, 26 - k * 3.6], color=c, lw=2)
        d.tekst(130, 26 - k * 3.6, s, ha="left", fs=6.5)
    d.opslaan(pad)


def pfd_warmte(r, i, pad):
    d = Tekening(17, 11.2, "PFD blad 2 – warmteketen voor de hele installatie (8 units)")
    wp1, wp2 = r["wp1"], r["wp2"]
    yT, yR, yC, yTop = 56, 76, 95, 106
    # ---- ITM-koelcircuit (per unit, ×8) met E-201 en luchtkoeler AK
    d.box(12, yT, 15, 12, f"8× ITM-koelcircuit\n{nlt(r['m_kc_unit'],0)} kg/h\nper unit", kleur="#f6ede4", fs=6.5)
    d.hx(34, yT, "E-201 (×8)", onder=f"{nlt(r['Q_E201'],0)} kW", rechts=True)
    d.box(34, yR, 10, 6, "AK (×8)\nluchtkoeler", fs=6)
    d.tekst(34, yR + 5.5, f"Q$_{{AK}}$ = {nlt(abs(r['Q_AK']),0)} kW", fs=6)
    d.lijn([(19.5, yT), (30.8, yT)], KL["kc"], f"A {nlt(i.T_kc_uit,1)} °C", lpos=0.5)
    d.lijn([(34, yT + 3.2), (34, yR - 3.6)], KL["kc"], f"A2 {nlt(r['T_kc_naE201'],1)} °C", li=0, lpos=0.4, loff=(6.5, 0))
    d.lijn([(29, yR), (12, yR), (12, yT + 6.6)], KL["kc"], f"B {nlt(i.T_kc_retour,0)} °C", li=0, lpos=0.5)
    # ---- H2-koelers parallel aan E-201
    d.box(46, 44, 12, 7, f"H$_2$-koelers (×8)\nPK-101 + E-102\n{nlt(r['Q_H2_TW'],0)} kW", kleur="#e8eef7", fs=6)
    # ---- TW-lus
    d.hx(60, yT, "E-204", onder=f"{nlt(r['Q_E204'],0)} kW", rechts=True)
    d.hx(84, yT, "E-202", onder=f"verdamper WP-201\n{nlt(r['Q_L'],0)} kW")
    d.hx(132, yT, "E-206", onder=f"verdamper WP-202\n{nlt(r['Q_L2'],0)} kW")
    d.lijn([(37.2, yT), (56.8, yT)], KL["TW"], f"TW1 {nlt(r['T_tw_a'],1)} °C", lpos=0.62)
    d.lijn([(46, 47.8), (46, yT)], KL["TW"], None, pijl=False)
    d.lijn([(63.2, yT), (80.8, yT)], KL["TW"], f"TW2 {nlt(r['T_tw_tussen'],2)} °C", lpos=0.5)
    d.lijn([(87.2, yT), (128.8, yT)], KL["TW"], f"TW4 {nlt(r['T_tw_naE202'],2)} °C", lpos=0.62)
    d.lijn([(135.2, yT), (146, yT), (146, 33), (34, 33), (34, yT - 3.2)], KL["TW"],
           f"TW3 retour {nlt(r['T_tw_r'],1)} °C  ·  {nlt(r['m_tw'],0)} kg/h  → E-201's en H$_2$-koelers", li=2, lpos=0.45,
           loff=(0, -4.2))
    d.lijn([(46, 33), (46, 40.2)], KL["TW"], None)
    # ---- warmtenet
    d.lijn([(60, 12), (60, yT - 3.2)], KL["net"], f"N1 retour {nlt(i.T_net_retour,0)} °C\n{nlt(r['m_net'],0)} kg/h", li=0,
           lpos=0.15, loff=(10, 0))
    d.hx(84, yC, "E-203", onder=f"condensor WP-201\n{nlt(r['Q_H'],0)} kW", rechts=True)
    d.lijn([(60, yT + 3.2), (60, yC), (80.8, yC)], KL["net"], f"N2 {nlt(r['T_E204'],0)} °C", li=0, lpos=0.55, loff=(-5, 0))
    d.lijn([(84, yC + 3.2), (84, yTop), (104, yTop)], KL["net"],
           f"N3 aanvoer {nlt(i.T_net_aanvoer,0)} °C → warmtenet", li=1, lpos=0.5)
    # ---- WP-201
    d.comp(100, yR, "K-201", onder=f"{nlt(r['W_K201'],0)} kW")
    d.klep(72, yR, "TV-201", vert=True)
    d.lijn([(86.3, yT + 2.3), (97.6, yR - 2.4)], KL["ref"], "R1", lpos=0.5, loff=(3, -2))
    d.lijn([(100, yR + 3.4), (100, yC), (87.2, yC)], KL["ref"], f"R2 {nlt(wp1['T2'],0)} °C", li=0, lpos=0.5, loff=(6, 0))
    d.lijn([(81.7, yC - 2.3), (72, yR + 2.4)], KL["ref"], "R3", lpos=0.5, loff=(-3, 0))
    d.lijn([(72, yR - 1.6), (81.7, yT + 2.3)], KL["ref"], "R4", lpos=0.5, loff=(-3.5, -1))
    d.tekst(106, 64, f"WP-201: {wp1['fluid']}\n{nlt(wp1['Te'],0)} °C → {nlt(wp1['Tc'],0)} °C\nCOP = {nlt(wp1['COP'],2)}\n"
            f"ṁ = {nlt(wp1['m_ref'],0)} kg/h", fs=6.2, ha="left", kleur=KL["ref"])
    # ---- WP-202
    d.hx(132, yC, "E-205", onder=f"condensor WP-202\n{nlt(r['Q_ind'],0)} kW", rechts=True)
    d.comp(150, yR, "K-202", onder=f"{nlt(r['W_K202'],0)} kW")
    d.klep(120, yR, "TV-202", vert=True)
    d.lijn([(134.3, yT + 2.3), (147.6, yR - 2.4)], KL["ref"], "R5", lpos=0.5, loff=(3, -2))
    d.lijn([(150, yR + 3.4), (150, yC), (135.2, yC)], KL["ref"], f"R6 {nlt(wp2['T2'],0)} °C", li=0, lpos=0.5, loff=(6, 0))
    d.lijn([(129.7, yC - 2.3), (120, yR + 2.4)], KL["ref"], "R7", lpos=0.5, loff=(-3, 0))
    d.lijn([(120, yR - 1.6), (129.7, yT + 2.3)], KL["ref"], "R8", lpos=0.5, loff=(-3.5, -1))
    d.tekst(152, 64, f"WP-202: {wp2['fluid']}\n{nlt(wp2['Te'],0)} °C → {nlt(wp2['Tc'],0)} °C\nCOP = {nlt(wp2['COP'],2)}\n"
            f"ṁ = {nlt(wp2['m_ref'],0)} kg/h", fs=6.2, ha="left", kleur=KL["ref"])
    d.lijn([(122, yTop - 2), (122, yC), (128.8, yC)], KL["ind"], f"I2 retour {nlt(i.T_ind_retour,0)} °C", li=0,
           lpos=0.0, loff=(-1, 0.5))
    d.lijn([(132, yC + 3.2), (132, yTop), (168, yTop)], KL["ind"],
           f"I1 aanvoer {nlt(i.T_ind_aanvoer,0)} °C · {nlt(r['m_ind'],0)} kg/h → industrie", li=1, lpos=0.5)
    # ---- samenvatting en legenda
    s = (f"Bron: ITM {nlt(r['Q_ITM_tot'],0)} kW + H$_2$-koelers {nlt(r['Q_H2_tot'],0)} kW = {nlt(r['Q_bron'],0)} kW\n"
         f"Naar warmtenet {nlt(r['Q_net'],0)} kW  ·  naar industrie {nlt(r['Q_ind'],0)} kW\n"
         f"Compressoren K-201 + K-202 = {nlt(r['W_wp_tot'],0)} kW$_e$  ·  luchtkoelers {nlt(abs(r['Q_AK']),0)} kW")
    d.ax.text(3, 24, s, fontsize=7, va="top", ha="left", bbox=dict(fc="#fafafa", ec="#999", boxstyle="round,pad=0.5"))
    leg = [("ITM-koelcircuit (62/38 water/glycol)", KL["kc"]), ("koelwatercircuit TW (water)", KL["TW"]),
           ("warmtenet", KL["net"]), ("koudemiddel", KL["ref"]), ("industrie (water onder druk)", KL["ind"])]
    for k, (t_, c) in enumerate(leg):
        d.ax.plot([112, 118], [24 - k * 3.6, 24 - k * 3.6], color=c, lw=2)
        d.tekst(120, 24 - k * 3.6, t_, ha="left", fs=6.5)
    d.opslaan(pad)


# ================================================================== log p-h
def _isotherm(f, T, Pmin, Pmax, Tcrit):
    Ps = np.geomspace(Pmin, Pmax, 260)
    hs, ps = [], []
    if T < Tcrit - 0.2:
        Psat = PS("P", "T", T, "Q", 0, f)
        for P in Ps[Ps < Psat * 0.999]:
            try:
                hs.append(PS("H", "T", T, "P", P, f)); ps.append(P)
            except Exception:
                pass
        hs += [PS("H", "T", T, "Q", 1, f), PS("H", "T", T, "Q", 0, f)]
        ps += [Psat, Psat]
        for P in Ps[Ps > Psat * 1.001]:
            try:
                hs.append(PS("H", "T", T, "P", P, f)); ps.append(P)
            except Exception:
                pass
    else:
        for P in Ps:
            try:
                hs.append(PS("H", "T", T, "P", P, f)); ps.append(P)
            except Exception:
                pass
    return np.array(hs) / 1e3, np.array(ps) / 1e5


def logph(cyc, pad, zoom=False, lees=None, titel=""):
    f = cyc["fluid"]
    Tcrit, Pcrit = PS("Tcrit", f), PS("Pcrit", f)
    Ttrip = max(PS("Tmin", f), 230.0)
    Pe, Pc = cyc["Pe"] * 1e3, cyc["Pc"] * 1e3
    if zoom:
        Pmin, Pmax = Pe * 0.75, Pc * 1.35
        hmin = cyc["h3"] - 25
        hmax = cyc["h2"] + 15
    else:
        Pmin, Pmax = PS("P", "T", Ttrip + 5, "Q", 0, f), Pcrit * 2.2
        hmin = PS("H", "T", Ttrip + 5, "Q", 0, f) / 1e3 - 10
        hmax = PS("H", "T", Tcrit + 70, "P", Pmin, f) / 1e3
    fig, ax = plt.subplots(figsize=(7.2, 5.6) if not zoom else (7.2, 6.4))
    # koepel
    Ts = np.linspace(Ttrip, Tcrit - 0.01, 300)
    hl = np.array([PS("H", "T", T, "Q", 0, f) for T in Ts]) / 1e3
    hv = np.array([PS("H", "T", T, "Q", 1, f) for T in Ts]) / 1e3
    ps = np.array([PS("P", "T", T, "Q", 0, f) for T in Ts]) / 1e5
    ax.plot(hl, ps, color="black", lw=1.6, zorder=4)
    ax.plot(hv, ps, color="black", lw=1.6, zorder=4)
    # dampfractielijnen
    for x in np.arange(0.1, 0.95, 0.1):
        ax.plot(hl + x * (hv - hl), ps, color="#2e7d32", lw=0.55, ls=(0, (4, 2)), zorder=2)
        k = int(len(Ts) * (0.25 if not zoom else 0.55))
        if not zoom or (Pmin / 1e5 < ps[k] < Pmax / 1e5):
            hx_ = hl[k] + x * (hv[k] - hl[k])
            if hmin < hx_ < hmax:
                ax.text(hx_, ps[k], f"x={komma(round(x,1))}", fontsize=5.5, color="#2e7d32", rotation=75,
                        ha="center", va="center", zorder=3, bbox=dict(fc="white", ec="none", pad=0.2, alpha=0.8))
    # isothermen
    stapT = 10 if not zoom else 5
    Tlist = np.arange(math.ceil((Ttrip - T0) / stapT) * stapT, (Tcrit - T0) + 80, stapT)
    for Tc_ in Tlist:
        h_, p_ = _isotherm(f, Tc_ + T0, Pmin, Pmax, Tcrit)
        if len(h_) < 2:
            continue
        ax.plot(h_, p_, color="#c62828", lw=0.6, zorder=2)
        Plab = (PS("P", "T", Tc_ + T0, "Q", 0, f) * (0.62 if zoom else 0.45) if Tc_ + T0 < Tcrit - 0.2 else Pcrit * 1.25) / 1e5
        sel = (p_ > Pmin / 1e5 * 1.03) & (p_ < Pmax / 1e5 * 0.97) & (h_ > hmin + 2) & (h_ < hmax - 6)
        if sel.any():
            idx = np.where(sel)[0]
            j = idx[np.argmin(np.abs(np.log(p_[idx]) - np.log(Plab)))]
            ax.text(h_[j], p_[j], f"{Tc_:.0f} °C", fontsize=5.8, color="#c62828", ha="center", va="center", zorder=3,
                    bbox=dict(fc="white", ec="none", pad=0.1, alpha=0.85))
    # isentropen
    s_lo = PS("S", "T", Ttrip + 20, "Q", 1, f) / 1e3 - 0.1
    s_hi = PS("S", "T", Tcrit + 60, "P", Pmin, f) / 1e3
    stap_s = 0.05 if not zoom else 0.02
    if zoom:
        s_lo, s_hi = cyc["s1"] - 0.06, cyc["s1"] + 0.12
    for s in np.arange(round(s_lo / stap_s) * stap_s, s_hi, stap_s):
        Pss = np.geomspace(Pmin, Pmax, 120)
        hh, pp = [], []
        for P in Pss:
            try:
                hh.append(PS("H", "P", P, "S", s * 1e3, f) / 1e3); pp.append(P / 1e5)
            except Exception:
                pass
        if len(hh) < 3:
            continue
        hh, pp = np.array(hh), np.array(pp)
        ax.plot(hh, pp, color="#1565c0", lw=0.5, ls="-.", zorder=2)
        sel = (hh < hmax) & (hh > hmin) & (pp < Pmax / 1e5 * 0.95)
        if sel.any() and (round(s / stap_s) % 2 == 0):
            j = np.where(sel)[0][-1]
            ax.text(hh[j], pp[j], f"s={komma(round(s, 3))}", fontsize=5.2, color="#1565c0", rotation=60, ha="right",
                    va="top", zorder=3, bbox=dict(fc="white", ec="none", pad=0.1, alpha=0.75))
    # isochoren
    rhos = [0.5, 1, 2, 5, 10, 20, 50, 100, 200] if not zoom else [5, 10, 15, 20, 30, 40, 50, 60, 80, 100, 120, 150]
    for rho in rhos:
        Pss = np.geomspace(Pmin, Pmax, 140)
        hh, pp = [], []
        for P in Pss:
            try:
                h = PS("H", "P", P, "D", rho, f) / 1e3
                hh.append(h); pp.append(P / 1e5)
            except Exception:
                pass
        if len(hh) < 3:
            continue
        hh, pp = np.array(hh), np.array(pp)
        ax.plot(hh, pp, color="#8d6e63", lw=0.5, ls=":", zorder=2)
        sel = (hh < hmax) & (hh > hmin)
        if sel.any():
            j = np.where(sel)[0][-1]
            ax.text(hh[j], pp[j], f"{komma(rho)} kg/m³", fontsize=5.2, color="#6d4c41", ha="left", va="center",
                    zorder=3, bbox=dict(fc="white", ec="none", pad=0.1, alpha=0.75))
    # cyclus
    h1, h2, h3, h2s = cyc["h1"], cyc["h2"], cyc["h3"], cyc["h2s"]
    hpad = [h1 + (PS("H", "P", p, "S", cyc["s1"] * 1e3, f) / 1e3 - h1) / cyc["eta"] for p in np.linspace(Pe, Pc, 30)] \
        if not lees else list(np.linspace(h1, h2, 30))
    ppad = list(np.linspace(Pe, Pc, 30) / 1e5)
    kl = "#ff6f00"
    ax.plot(hpad, ppad, color=kl, lw=2.4, zorder=6)
    ax.plot([h2, h3], [Pc / 1e5] * 2, color=kl, lw=2.4, zorder=6)
    ax.plot([h3, h3], [Pc / 1e5, Pe / 1e5], color=kl, lw=2.4, zorder=6)
    ax.plot([h3, h1], [Pe / 1e5] * 2, color=kl, lw=2.4, zorder=6)
    pp1 = np.geomspace(Pe, Pc * 1.2, 40)
    ax.plot([PS("H", "P", p, "S", cyc["s1"] * 1e3, f) / 1e3 for p in pp1], pp1 / 1e5, color="#0d47a1", lw=1.3, ls="--",
            zorder=6)
    for nm, (h, p) in {"1": (h1, Pe), "2": (h2, Pc), "2s": (h2s, Pc), "3": (h3, Pc), "4": (h3, Pe)}.items():
        ax.plot(h, p / 1e5, "o", color="black", ms=4, zorder=7)
        off = {"1": (6, -10), "2": (6, 4), "2s": (-14, 6), "3": (-10, 4), "4": (-10, -11)}[nm]
        ax.annotate(nm, (h, p / 1e5), xytext=off, textcoords="offset points", fontsize=9, fontweight="bold", zorder=8)
    if lees:
        for nm, h in (("h$_1$", h1), ("h$_{2s}$", h2s), ("h$_3$ = h$_4$", h3)):
            ax.plot([h, h], [Pmin / 1e5, Pc / 1e5 if nm != "h$_1$" else Pe / 1e5], color="black", lw=0.8, ls="--", zorder=5)
            ax.text(h, Pmin / 1e5 * 1.03, f"{nm} ≈ {komma(h)}", rotation=90, fontsize=7, ha="right", va="bottom",
                    zorder=8, bbox=dict(fc="#fff8e1", ec="#999", pad=0.6))
        for nm, p in (("p$_e$", Pe), ("p$_c$", Pc)):
            ax.plot([hmin, h1 if nm == "p$_e$" else h3], [p / 1e5] * 2, color="black", lw=0.8, ls="--", zorder=5)
            ax.text(hmin + 1, p / 1e5 * 1.02, f"{nm} ≈ {komma(round(p/1e5, 1))} bar", fontsize=7, va="bottom",
                    zorder=8, bbox=dict(fc="#fff8e1", ec="#999", pad=0.6))
    ax.set_yscale("log")
    ax.set_xlim(hmin, hmax)
    ax.set_ylim(Pmin / 1e5, Pmax / 1e5)
    ax.set_xlabel("specifieke enthalpie h [kJ/kg]")
    ax.set_ylabel("druk p [bar absoluut]  (logaritmische schaal)")
    ax.set_title(titel or f"log p–h-diagram {f}")
    if zoom:
        ax.xaxis.set_major_locator(MultipleLocator(10))
        ax.xaxis.set_minor_locator(MultipleLocator(1))
        ax.grid(True, which="major", color="#bbb", lw=0.5)
        ax.grid(True, which="minor", axis="x", color="#e5e5e5", lw=0.35)
        ax.grid(True, which="minor", axis="y", color="#e5e5e5", lw=0.35)
    else:
        ax.grid(True, which="both", color="#e6e6e6", lw=0.4)
    nl_assen(ax)
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: komma(round(v, 1)) if (round(v, 1) * 10) % 10 in (2, 5) or zoom else ""))
    from matplotlib.lines import Line2D
    hand = [Line2D([], [], color="black", lw=1.6, label="verzadigingskoepel"),
            Line2D([], [], color="#c62828", lw=0.8, label="isothermen (T)"),
            Line2D([], [], color="#1565c0", lw=0.8, ls="-.", label="isentropen s [kJ/(kg·K)]"),
            Line2D([], [], color="#2e7d32", lw=0.8, ls=(0, (4, 2)), label="dampfractie x"),
            Line2D([], [], color="#8d6e63", lw=0.8, ls=":", label="isochoren ρ [kg/m³]"),
            Line2D([], [], color=kl, lw=2.4, label="cyclus 1-2-3-4"),
            Line2D([], [], color="#0d47a1", lw=1.3, ls="--", label="isentroop door 1 (s = s$_1$) → 2s")]
    ax.legend(handles=hand, loc="upper center", bbox_to_anchor=(0.5, -0.11), ncol=4, framealpha=0.95, fontsize=6.8)
    fig.savefig(pad)
    plt.close(fig)


def ts(cyc, pad, titel=""):
    f = cyc["fluid"]
    d = M.ts_cyclus(f, cyc["Te"], cyc["Tc"], cyc["eta"])
    fig, ax = plt.subplots(figsize=(7.0, 4.8))
    ax.plot(d["koepel"]["s"], d["koepel"]["T"], color="black", lw=1.5, label="verzadigingskoepel")
    # isobaren pe en pc
    for P, nm in ((cyc["Pe"] * 1e3, "p$_e$"), (cyc["Pc"] * 1e3, "p$_c$")):
        Ts_ = np.linspace(cyc["Te"] - 25 + T0, d["cyclus"]["T_pers"] + 30 + T0, 120)
        ss = []
        tt = []
        for T in Ts_:
            try:
                ss.append(PS("S", "T", T, "P", P, f) / 1e3); tt.append(T - T0)
            except Exception:
                pass
        ax.plot(ss, tt, color="#1565c0", lw=0.6, ls="-.")
        k_ = int(len(ss) * (0.93 if nm == "p$_c$" else 0.80))
        ax.text(ss[k_], tt[k_], f"  {nm} = {komma(round(P/1e5, 2))} bar", fontsize=6.5, color="#1565c0", ha="left", va="top")
    kl = "#ff6f00"
    for k, stuk in (("compressie", d["compressie"]), ("condensor", d["condensor"]), ("smoren", d["smoren"]),
                    ("verdamper", d["verdamper"])):
        a = np.array(stuk)
        ax.plot(a[:, 0], a[:, 1], color=kl, lw=2.2, ls="--" if k == "smoren" else "-")
    s1, T1 = d["punten"][1]
    s2s, T2s = d["punten"]["2s"]
    ax.plot([s1, s2s], [T1, T2s], color=kl, lw=1, ls=":")
    for nm, (s, T) in d["punten"].items():
        ax.plot(s, T, "o", color="black", ms=4)
        ax.annotate(str(nm), (s, T), xytext={1: (6, -10), 2: (6, 3), 3: (-10, 4), 4: (-12, -11), "2s": (-14, 4)}[nm],
                    textcoords="offset points", fontsize=9, fontweight="bold")
    ax.axhline(cyc["Te"], color="#999", lw=0.5)
    ax.axhline(cyc["Tc"], color="#999", lw=0.5)
    ax.set_xlabel("specifieke entropie s [kJ/(kg·K)]")
    ax.set_ylabel("temperatuur T [°C]")
    ax.set_title(titel or f"T–s-diagram {f}")
    smin = min(d["koepel"]["s"])
    ax.set_xlim(smin + (s1 - smin) * 0.35, s1 + (s1 - smin) * 0.25)
    ax.set_ylim(cyc["Te"] - 30, max(d["Tcrit"], d["cyclus"]["T_pers"]) + 15)
    ax.grid(True, color="#e6e6e6", lw=0.4)
    nl_assen(ax)
    fig.savefig(pad)
    plt.close(fig)


# ================================================================== T-Q-diagrammen
def tq(r, i, pad):
    """Temperatuur tegen overgedragen warmte voor E-201, E-204/E-202/E-206 en de condensors."""
    fig, axs = plt.subplots(2, 2, figsize=(7.4, 6.0))
    nl = lambda a: nl_assen(a)
    # (a) E-201
    ax = axs[0, 0]
    Q = r["Q_E201_unit"]
    ax.plot([0, Q], [i.T_kc_retour, i.T_kc_uit], color=KL["kc"], lw=2, label="ITM-circuit (warm)")
    ax.plot([0, Q], [r["T_tw_r"], r["T_tw_a"]], color=KL["TW"], lw=2, label="koelwatercircuit TW (koud)")
    for x, a, b in ((0, r["T_tw_r"], i.T_kc_retour), (Q, r["T_tw_a"], i.T_kc_uit)):
        ax.annotate("", xy=(x, b), xytext=(x, a), arrowprops=dict(arrowstyle="<->", lw=0.8))
        ax.text(x + (0.03 if x == 0 else -0.03) * Q, (a + b) / 2, f"ΔT = {komma(round(b - a, 1))} K", fontsize=6.5,
                ha="left" if x == 0 else "right")
    ax.set_title("(a) E-201 per unit – tegenstroom", fontsize=8.5)
    ax.set_xlabel("Q [kW]"); ax.set_ylabel("T [°C]"); ax.legend(loc="lower right"); nl(ax)
    # (b) TW-kant van E-204, E-202, E-206 tegen net en verdampers
    ax = axs[0, 1]
    q1, q2, q3 = r["Q_E204"], r["Q_E204"] + r["Q_L"], r["Q_E204"] + r["Q_L"] + r["Q_L2"]
    ax.plot([0, q1, q2, q3], [r["T_tw_a"], r["T_tw_tussen"], r["T_tw_naE202"], r["T_tw_r"]], color=KL["TW"], lw=2,
            label="TW (afkoelend)")
    ax.plot([0, q1], [r["T_E204"], i.T_net_retour], color=KL["net"], lw=2, label="net in E-204 (40→45 °C)")
    ax.plot([q1, q2], [r["T_evap"]] * 2, color=KL["ref"], lw=2, label="verdampen WP-201")
    ax.plot([q2, q3], [r["T_evap"]] * 2, color=KL["ref"], lw=2, ls="--", label="verdampen WP-202")
    ax.annotate("", xy=(q3, r["T_tw_r"]), xytext=(q3, r["T_evap"]), arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(q3 * 0.97, (r["T_tw_r"] + r["T_evap"]) / 2, f"ΔT$_{{min}}$ = {komma(i.dT_min)} K", fontsize=6.5, ha="right")
    ax.set_title("(b) TW-circuit: E-204 → E-202 → E-206", fontsize=8.5)
    ax.set_xlabel("cumulatief afgegeven Q [kW]"); ax.set_ylabel("T [°C]"); ax.set_ylim(36, 53)
    ax.legend(loc="lower center", bbox_to_anchor=(0.62, 0.12), fontsize=6.2); nl(ax)
    # (c) condensor WP-201
    ax = axs[1, 0]
    c = r["wp1"]
    m = c["m_ref"] / 3600
    Qd = m * c["q_desup"]; Qt = r["Q_H"]
    ax.plot([0, Qd, Qt], [c["T2"], c["Tc"], c["Tc"]], color=KL["ref"], lw=2, label=f"{c['fluid']} (2 → 3)")
    ax.plot([0, Qt], [i.T_net_aanvoer, r["T_E204"]], color=KL["net"], lw=2, label="netwater 45 → 70 °C")
    ax.annotate("", xy=(Qd, i.T_net_aanvoer - (i.T_net_aanvoer - r['T_E204']) * Qd / Qt), xytext=(Qd, c["Tc"]),
                arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(Qd + Qt * 0.02, c["Tc"] - 3, f"pinch ≈ {komma(round(c['Tc'] - (i.T_net_aanvoer - (i.T_net_aanvoer - r['T_E204']) * Qd / Qt), 1))} K",
            fontsize=6.5)
    ax.set_title("(c) E-203 condensor WP-201", fontsize=8.5)
    ax.set_xlabel("Q [kW] (vanaf de hete kant)"); ax.set_ylabel("T [°C]"); ax.legend(loc="lower left"); nl(ax)
    # (d) condensor WP-202
    ax = axs[1, 1]
    c = r["wp2"]
    m = c["m_ref"] / 3600
    Qd = m * c["q_desup"]; Qt = r["Q_ind"]
    ax.plot([0, Qd, Qt], [c["T2"], c["Tc"], c["Tc"]], color=KL["ref"], lw=2, label=f"{c['fluid']} (2 → 3)")
    ax.plot([0, Qt], [i.T_ind_aanvoer, i.T_ind_retour], color=KL["ind"], lw=2, label="industrie 75 → 95 °C")
    ax.set_title("(d) E-205 condensor WP-202", fontsize=8.5)
    ax.set_xlabel("Q [kW] (vanaf de hete kant)"); ax.set_ylabel("T [°C]"); ax.legend(loc="lower left"); nl(ax)
    for a in axs.flat:
        a.grid(True, color="#e6e6e6", lw=0.4)
    fig.tight_layout()
    fig.savefig(pad)
    plt.close(fig)


def alles(r, i, map_):
    os.makedirs(map_, exist_ok=True)
    pfd_unit(r, i, os.path.join(map_, "pfd_unit.pdf"))
    pfd_warmte(r, i, os.path.join(map_, "pfd_warmte.pdf"))
    for k in ("wp1", "wp2"):
        c = r[k]
        naam = "WP-201" if k == "wp1" else "WP-202"
        # het volledige diagram altijd met de exacte cyclus; het zoomdiagram in B met de afleeswaarden
        exact = M.warmtepomp(c["fluid"], c["Te"], c["Tc"], c["eta"])
        s1 = PS("S", "T", c["Te"] + T0, "Q", 1, c["fluid"]) / 1e3
        cx = dict(fluid=c["fluid"], Te=c["Te"], Tc=c["Tc"], eta=c["eta"], Pe=exact["P_evap_bar"] * 100,
                  Pc=exact["P_cond_bar"] * 100, h1=exact["h1"], h2=exact["h2"], h3=exact["h3"], s1=s1,
                  h2s=PS("H", "P", exact["P_cond_bar"] * 1e5, "S", s1 * 1e3, c["fluid"]) / 1e3)
        logph(cx, os.path.join(map_, f"logph_{k}.pdf"), titel=f"log p–h-diagram {c['fluid']} met cyclus {naam}")
        if r["versie"] == "B":
            lz = dict(cx, h1=c["h1"], h2=c["h2"], h3=c["h3"], h2s=c["h2s"], Pe=c["Pe"], Pc=c["Pc"])
            logph(lz, os.path.join(map_, f"logph_{k}_zoom.pdf"), zoom=True, lees=True,
                  titel=f"Aflezen: ingezoomd log p–h-diagram {c['fluid']} ({naam})")
        else:
            logph(cx, os.path.join(map_, f"logph_{k}_zoom.pdf"), zoom=True,
                  titel=f"Ingezoomd log p–h-diagram {c['fluid']} ({naam})")
        ts(cx, os.path.join(map_, f"ts_{k}.pdf"), titel=f"T–s-diagram {c['fluid']} met cyclus {naam}")
    tq(r, i, os.path.join(map_, "tq.pdf"))

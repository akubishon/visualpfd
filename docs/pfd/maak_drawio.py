"""
Bouwt het PFD als draw.io-bestand (docs/pfd/PFD.drawio) met dezelfde indeling als de visualpfd-app:
H₂-lijn bovenaan, warmteterugwinning in het midden (boven de O₂-lijn), O₂-lijn onderaan.

- Alleen standaard draw.io-iconen (bibliotheek Process Engineering / P&ID).
- Elke leiding is aan de apparaten vastgemaakt (bron → doel), zodat het schema bij verslepen blijft kloppen.
- Bij elke stroom staan temperatuur, druk en massadebiet (kg/s, hele installatie = 8 units) als tekst
  op de lijn, in plaats van stroomvlaggetjes.
- Blad 2 bevat de stroomtabel met dezelfde waarden.

De getallen komen uit itm_model (CoolProp, vollast EOL, standaardinvoer).

Gebruik (vanuit de repo-root):
    pip install CoolProp numpy
    python docs/pfd/maak_drawio.py
"""
import html
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HIER, "..", ".."))

from itm_model import Invoer, coolprop, leidingen  # noqa: E402

UIT = os.path.join(HIER, "PFD.drawio")

# ------------------------------------------------------------------ waarden
i = Invoer()
r = coolprop(i)
N = i.n_units
LD = {l["id"]: l for l in leidingen(i)}


def nl(v, d=1):
    s = f"{v:,.{d}f}"
    return s.replace(",", " ").replace(".", ",")


def kgs(kg_h, per_unit=True):
    """kg/h (per unit of installatie) → kg/s voor de hele installatie."""
    v = kg_h * (N if per_unit else 1) / 3600
    return nl(v, 3 if v < 1 else (2 if v < 10 else 1)) + " kg/s"


def MW(kW):
    return nl(kW / 1000, 2) + " MW" if abs(kW) >= 1000 else nl(kW, 0) + " kW"


# aannames voor drukken die het model niet berekent (zelfde drukken als voor de dichtheid in leidingen())
P_TW, P_NET, P_IND, P_KW, P_AFV = 5.0, 5.0, 9.0, 2.0, 1.0

cy, cy2 = r["cyclus"], r["cyclus2"]
m_ref1 = LD["R1"]["m"] / 3600
m_ref2 = LD["R5"]["m"] / 3600 if "R5" in LD else 0.0
tw_tot = r["m_tw"] * 3600                    # kg/h
tw_h2 = r["m_tw_H2_unit"] * N                # kg/h
net = r["m_net_th"] * 1000
ind = r["m_ind_th"] * 1000


def lab(sid, T, p, m, ster=False):
    p_txt = "" if p is None else f" · {nl(p, 2 if p < 1 else 1)} barg{'*' if ster else ''}"
    T_txt = "–" if T is None else f"{nl(T, 1)} °C"
    return f"<b>{sid}</b> {T_txt}{p_txt}<br>{m}"


# ------------------------------------------------------------------ kleuren (zoals visualpfd)
C = dict(h2="#1d6fb8", o2="#3a8a2c", waste="#8a4b2a", kc="#7b4bb2", net="#d27a1d", kw="#5f86bd",
         ref="#138a80", tw="#b8457e", ind="#b3261e", el="#7f6000", ink="#16202a")

# ------------------------------------------------------------------ opbouw
cellen = []
geo = {}
_n = [0]


def nid(p="c"):
    _n[0] += 1
    return f"{p}{_n[0]}"


def esc(s):
    return html.escape(s, quote=True)


def vertex(cid, x, y, w, h, style, value="", parent="1"):
    geo[cid] = (x, y, w, h)
    cellen.append(f'<mxCell id="{cid}" value="{esc(value)}" style="{style}" vertex="1" parent="{parent}">'
                  f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return cid


PID = "html=1;pointerEvents=1;align=center;verticalLabelPosition=bottom;verticalAlign=top;dashed=0;fontSize=10;"
LBL_L = "labelPosition=left;verticalLabelPosition=middle;align=right;verticalAlign=middle;"
LBL_R = "labelPosition=right;verticalLabelPosition=middle;align=left;verticalAlign=middle;"
LBL_T = "verticalLabelPosition=top;verticalAlign=bottom;"


def shape(cid, s, x, y, w, h, value="", extra=""):
    return vertex(cid, x, y, w, h, f"shape={s};{PID}{extra}", value)


def plaat(cid, x, y, value, extra=LBL_L):
    return shape(cid, "mxgraph.pid.heat_exchangers.heat_exchanger_(plate)", x, y, 80, 80, value, extra)


def buis(cid, x, y, value, w=60, extra=""):
    return shape(cid, "mxgraph.pid.heat_exchangers.shell_and_tube_heat_exchanger_1", x, y, w, w, value, extra)


def compressor(cid, x, y, w, value, extra=""):
    return shape(cid, "mxgraph.pid.compressors_-_iso.compressor,_vacuum_pump", x, y, w, w, value, extra)


def klep(cid, x, y, value, soort="gate", extra="", w=40, h=24):
    s = f"mxgraph.pid2valves.valve;valveType={soort}"
    return shape(cid, s, x, y, w, h, value, extra)


def pijl(cid, x, y, w, value, kleur, links=False):
    st = ("shape=mxgraph.arrows2.arrow;dy=0;dx=14;notch=0;html=1;whiteSpace=wrap;fontSize=10;"
          f"fillColor=#ffffff;strokeColor={kleur};fontColor={C['ink']};" + ("direction=west;" if links else ""))
    if links:
        WEST.add(cid)
    return vertex(cid, x, y, w, 28, st, value)


def tekst(x, y, w, h, value, extra="align=center;"):
    return vertex(nid("t"), x, y, w, h, f"text;html=1;whiteSpace=wrap;verticalAlign=middle;fontSize=10;{extra}", value)


def knoop(cid, x, y, kleur):
    """T-stuk / verzamelpunt (gevulde stip)."""
    return vertex(cid, x - 4, y - 4, 8, 8, f"ellipse;html=1;fillColor={kleur};strokeColor={kleur};", "")


WEST = set()                 # pijlen naar links (direction=west): draw.io draait hun poorten mee


def poort(cid, fx, fy):
    x, y, w, h = geo[cid]
    if cid in WEST:
        fx = 1 - fx
    return (x + fx * w, y + fy * h)


def edge(src, sp, tgt, tp, pts, kleur, label="", seg=None, pos=0.5, pijlpunt=True, stijl="", lx=0, ly=0,
         lstyle=""):
    """Leiding van src (poort sp) naar tgt (poort tp) via punten pts. Het label komt op segment seg
    (index in de polyline; standaard het langste segment) op fractie pos van dat segment."""
    a = poort(src, *sp) if sp is not None else None
    b = poort(tgt, *tp) if tp is not None else None
    poly = [a] + list(pts) + [b]
    lens = [abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in zip(poly, poly[1:])]
    L = sum(lens) or 1
    if seg is None:
        seg = max(range(len(lens)), key=lambda k: lens[k])
    d = sum(lens[:seg]) + lens[seg] * pos
    xrel = 2 * d / L - 1
    ex = 1 - sp[0] if src in WEST else sp[0]
    en = 1 - tp[0] if tgt in WEST else tp[0]
    st = (f"html=1;rounded=0;jumpStyle=arc;jumpSize=10;strokeWidth=1.6;strokeColor={kleur};"
          f"fontSize=9;fontColor={C['ink']};labelBackgroundColor=#ffffff;labelBorderColor=none;"
          f"endArrow={'block' if pijlpunt else 'none'};endFill=1;endSize=6;"
          f"exitX={ex};exitY={sp[1]};exitDx=0;exitDy=0;exitPerimeter=0;"
          f"entryX={en};entryY={tp[1]};entryDx=0;entryDy=0;entryPerimeter=0;{stijl}{lstyle}")
    pt = "".join(f'<mxPoint x="{x:g}" y="{y:g}"/>' for x, y in pts)
    arr = f'<Array as="points">{pt}</Array>' if pts else ""
    off = f'<mxPoint x="{lx}" y="{ly}" as="offset"/>' if (lx or ly) else ""
    cellen.append(f'<mxCell id="{nid("e")}" value="{esc(label)}" style="{st}" edge="1" parent="1" '
                  f'source="{src}" target="{tgt}"><mxGeometry x="{xrel:.4f}" relative="1" as="geometry">'
                  f'{arr}{off}</mxGeometry></mxCell>')


EL = "dashed=1;dashPattern=2 3;endArrow=none;strokeWidth=1.2;"
KW = "dashed=1;dashPattern=6 3;"
REF = "dashed=1;dashPattern=8 3;"

# ------------------------------------------------------------------ titel
tekst(30, 8, 1300, 30, "<b>PFD – 8 × ITM Neptune V (40 MW) · H₂-productie, warmteterugwinning en O₂-verwerking</b>",
      "align=left;fontSize=16;")
tekst(30, 34, 1300, 20, f"Vollast EOL, waarden uit het visualpfd-model (CoolProp). Debieten in kg/s voor de hele "
      f"installatie ({N} units). * = aangenomen druk.", "align=left;fontSize=10;fontColor=#586878;")

# ------------------------------------------------------------------ ITM-blok
vertex("itm", 330, 150, 200, 420, "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;verticalAlign=top;fontSize=11;"
       "strokeWidth=1.6;", "<b>8 × ITM Neptune V</b> (parallel)")
for k in range(8):
    vertex(f"itm{k + 1}", 350, 190 + k * 46, 160, 36, "rounded=0;whiteSpace=wrap;html=1;fontSize=10;fillColor=#f3f6f9;",
           f"ITM Neptune V #{k + 1}", parent="1")

vertex("ac", 330, 66, 200, 44, "rounded=0;whiteSpace=wrap;html=1;fontSize=10;", "<b>AC-net</b> (MV, windpark)")
edge("ac", (0.5, 1), "itm", (0.5, 0), [], C["el"], f"E1 · {MW(r['P_AC_EOL'] * N)}", stijl=EL, lx=0, ly=0)

# voedwater / afvalwater links
pijl("t_s1", 20, 286, 150, "Vers UPW (suppletie)", C["o2"])
edge("t_s1", (1, 0.5), "itm", (0, 150 / 420), [], C["o2"],
     lab("S1", i.T_vers, i.P_ITM_voed, kgs(r["m_vers"])), pos=0.45)
pijl("t_s3", 20, 406, 150, "Afvalwater", C["waste"], links=True)
edge("itm", (0, 270 / 420), "t_s3", (1, 0.5), [], C["waste"],
     lab("S3", i.T_afvalwater, P_AFV, kgs(i.m_afvalwater), ster=True), pos=0.45)

# ------------------------------------------------------------------ H2-lijn (y = 200)
Y = 200
shape("v101", "mxgraph.pid.vessels.pressurized_vessel", 660, 120, 60, 150,
      f"<b>V-101</b><br>LD-buffervat H₂<br>{nl(r['V_V101'], 0)} m³", "labelPosition=center;")
edge("itm", (1, (Y - 150) / 420), "v101", (0, (Y - 120) / 150), [], C["h2"],
     lab("S4", i.T_H2, i.P_H2_ITM, kgs(i.m_H2)))

vertex("pk101", 790, 120, 250, 170, "rounded=1;arcSize=4;whiteSpace=wrap;html=1;dashed=1;fillColor=none;"
       "verticalAlign=bottom;fontSize=10;strokeColor=#586878;",
       f"<b>K-101</b> H₂-compressorpakket · {MW(r['W_K101'] * N)} (E3)")
compressor("k101", 810, Y - 40, 80, "")
buis("pkk101", 950, Y - 30, "")
tekst(872, 244, 100, 30, f"pakketkoeler<br>{MW(r['Q_pak_K101'] * N)} naar TW", "fontSize=9;")
edge("v101", (1, (Y - 120) / 150), "k101", (0, 0.5), [], C["h2"], lab("S5", i.T_H2, i.P_V101_min, kgs(r["m_S5"])))
edge("k101", (1, 0.5), "pkk101", (0, 0.5), [], C["h2"], f"{nl(r['T_uit_K101'], 0)} °C")

buis("e102", 1130, Y - 30, "")
tekst(1166, 236, 90, 30, f"<b>E-102</b><br>{MW(-r['Q_E102'] * N)} naar TW", "fontSize=10;align=left;")
edge("pkk101", (1, 0.5), "e102", (0, 0.5), [], C["h2"], lab("S6", r["T_S6"], i.P_K101_uit, kgs(r["m_S5"])))
buis("e103", 1310, Y - 30, f"<b>E-103</b> eindkoeler<br>{MW(-r['Q_E103'] * N)}", extra="labelPosition=left;verticalLabelPosition=top;align=right;verticalAlign=bottom;spacingRight=-6;")
edge("e102", (1, 0.5), "e103", (0, 0.5), [], C["h2"], lab("S7", i.T_E102_uit, i.P_K101_uit, kgs(r["m_S5"])))
knoop("j_s9", 1500, Y, C["h2"])
edge("e103", (1, 0.5), "j_s9", (0.5, 0.5), [], C["h2"], lab("S8", i.T_E103_uit, i.P_K101_uit, kgs(r["m_S5"])),
     pijlpunt=False, pos=0.55)
vertex("qc", 1560, Y - 20, 110, 40, "rounded=0;whiteSpace=wrap;html=1;fontSize=10;", "<b>QC</b> kwaliteit")
edge("j_s9", (0.5, 0.5), "qc", (0, 0.5), [], C["h2"])
shape("v102", "mxgraph.pid.vessels.pressurized_vessel", 1760, 120, 60, 150,
      f"<b>V-102</b><br>HD-buffervat H₂<br>{nl(r['V_V102'], 1)} m³")
edge("qc", (1, 0.5), "v102", (0, (Y - 120) / 150), [], C["h2"],
     lab("S11", i.T_E103_uit, i.P_backbone, kgs(r["m_backbone"])))
klep("pcv101", 1870, Y - 12, "<b>PCV-101</b>", soort="globe")
edge("v102", (1, (Y - 120) / 150), "pcv101", (0, 0.5), [], C["h2"])
pijl("t_s12", 2040, Y - 14, 150, "<b>H₂-backbone</b>", C["h2"])
edge("pcv101", (1, 0.5), "t_s12", (0, 0.5), [], C["h2"], lab("S12", i.T_E103_uit, i.P_backbone, kgs(r["m_backbone"])))

# recycle S9 en blowoff S10
klep("fv101", 1250, 68, "<b>FV-101</b>", soort="globe", extra=LBL_T)
edge("j_s9", (0.5, 0.5), "fv101", (1, 0.5), [(1500, 80)], C["h2"], pijlpunt=True,
     stijl="dashed=1;dashPattern=4 3;")
edge("fv101", (0, 0.5), "v101", (0.7, 0), [(702, 80)], C["h2"],
     lab("S9", i.T_E103_uit, i.P_V101_min, kgs(r["m_S9"])) + " (recycle, alleen deellast)", seg=0,
     stijl="dashed=1;dashPattern=4 3;")
pijl("t_s10", 760, 26, 150, "H₂ blowoff", C["h2"])
edge("v101", (0.3, 0), "t_s10", (0, 0.5), [(678, 40)], C["h2"], "<b>S10</b> 0 kg/s", seg=1,
     stijl="dashed=1;dashPattern=4 3;")

# koelwater E-103
tekst(1280, 268, 130, 26, f"<b>KW2</b> in 20 °C · {nl(P_KW, 1)} barg*<br>{kgs(r['m_kw_E103'])}", "fontSize=9;")
tekst(1320, 110, 80, 26, "<b>KW2</b> uit 30 °C", "fontSize=9;")
edge(list(geo)[-2], (0.5, 0), "e103", (0.5, 1), [], C["kw"], stijl=KW)
edge("e103", (0.5, 0), list(geo)[-1], (0.5, 1), [], C["kw"], stijl=KW)

# ------------------------------------------------------------------ ITM-circuit + E-201 + AK
YE = 480                     # bovenkant E-201
shape("ak", "mxgraph.pid.misc.air_cooler", 680, 320, 80, 70,
      f"<b>AK ×8</b> luchtkoelers<br>trim · {MW(max(0.0, r['Q_AK']))}", LBL_R + "spacingLeft=6;")
plaat("e201", 680, YE, f"<b>E-201 ×8</b><br>{MW(r['Q_E201'])}<br>naar TW",
      extra="labelPosition=left;verticalLabelPosition=bottom;align=right;verticalAlign=top;spacingRight=-30;")
edge("itm", (1, (YE + 64 - 150) / 420), "e201", (0, 0.8), [], C["kc"],
     lab("A", i.T_kc_uit, i.P_kc, kgs(r["m_kc_unit"])))
edge("e201", (0.5, 0), "ak", (0.5, 1), [], C["kc"], f"<b>A2</b> {nl(r['T_kc_naE201'], 1)} °C", lx=0, ly=0)
edge("ak", (0, 0.5), "itm", (1, (355 - 150) / 420), [], C["kc"],
     lab("B", i.T_kc_retour, i.P_kc, kgs(r["m_kc_unit"])))

# ------------------------------------------------------------------ warmteterugwinning (midden)
YH = 680                     # bovenkant rij E-204 / E-202 / E-206
Y_RET, Y_AAN = 600, 650      # TW-retour (45 °C) en TW-aanvoer (51,5 °C)
X204, X202, X206 = 1040, 1290, 1620
plaat("e204", X204, YH, f"<b>E-204</b><br>directe<br>voorverwarming<br>{MW(r['Q_E204'])}")
plaat("e202", X202, YH, f"<b>E-202</b><br>verdamper WP-201<br>{MW(r['Q_L'])}")
plaat("e206", X206, YH, f"<b>E-206</b><br>verdamper WP-202<br>{MW(r['Q_L2'])}")

knoop("j_twa", 980, Y_AAN, C["tw"])   # samenkomst aanvoer (E-201's + H2-koelers)
knoop("j_twr", 1160, Y_RET, C["tw"])  # aftakking retour naar H2-koelers
# E-201 → aanvoer
edge("e201", (1, 0.8), "j_twa", (0.5, 0.5), [(790, YE + 64), (790, Y_AAN)], C["tw"],
     lab("TW", r["T_tw_a"], P_TW, kgs(tw_tot - tw_h2, False), ster=True), seg=1, pijlpunt=False)
edge("j_twa", (0.5, 0.5), "e204", (0.2, 0), [(X204 + 16, Y_AAN)], C["tw"],
     lab("TW1", r["T_tw_a"], P_TW, kgs(tw_tot, False), ster=True), seg=0, pos=0.5, lx=34, ly=-22)
edge("e204", (0.8, 0), "e202", (0.2, 0), [(X204 + 64, Y_AAN), (X202 + 16, Y_AAN)], C["tw"],
     lab("TW2", r["T_tw_tussen"], P_TW, kgs(tw_tot, False), ster=True), seg=1)
edge("e202", (0.8, 0), "e206", (0.2, 0), [(X202 + 64, Y_AAN), (X206 + 16, Y_AAN)], C["tw"],
     lab("TW4", r["T_tw_naE202"], P_TW, kgs(tw_tot, False), ster=True), seg=1)
edge("e206", (0.8, 0), "j_twr", (0.5, 0.5), [(X206 + 64, Y_RET)], C["tw"],
     lab("TW5", r["T_tw_r"], P_TW, kgs(tw_tot, False), ster=True), seg=1, pos=0.3, pijlpunt=False)
edge("j_twr", (0.5, 0.5), "e201", (1, 0.2), [(880, Y_RET), (880, YE + 16)], C["tw"],
     lab("TW3", r["T_tw_r"], P_TW, kgs(tw_tot - tw_h2, False), ster=True), seg=0, pos=0.25)
# aftakking naar de H2-koelers: retour → E-102 → pakketkoeler K-101 → aanvoer
edge("j_twr", (0.5, 0.5), "e102", (0.5, 1), [], C["tw"],
     lab("TWH1", r["T_tw_r"], P_TW, kgs(tw_h2, False), ster=True), pos=0.45)
edge("e102", (0.5, 0), "pkk101", (0.5, 0), [(1160, 150), (980, 150)], C["tw"], "", seg=1)
edge("pkk101", (0.5, 1), "j_twa", (0.5, 0.5), [], C["tw"],
     lab("TWH2", r["T_tw_a"], P_TW, kgs(tw_h2, False), ster=True), pos=0.62, pijlpunt=False)

# WP-201: E-202 → K-201 → E-203 → TV-201 → E-202
YC, YK = 940, 830            # bovenkant condensors, bovenkant compressoren
plaat("e203", X202, YC, f"<b>E-203</b><br>condensor WP-201<br>{MW(r['Q_H'])}")
compressor("k201", X202 - 70, YK, 60, f"<b>K-201</b><br>{MW(r['W_K201'])} (E6)<br>COP {nl(r['COP'], 2)}",
           extra=LBL_L + "spacingRight=4;")
klep("tv201", X202 + 92, YK + 18, "", extra="rotation=90;")
tekst(X202 + 124, YK + 20, 50, 20, "<b>TV-201</b>", "align=left;")
f1 = f"{nl(m_ref1, 1)} kg/s"
edge("e202", (0.2, 1), "k201", (0.5, 0), [(X202 + 16, YH + 105), (X202 - 40, YH + 105)], C["ref"],
     lab("R1", cy["T_evap"], cy["P_evap_bar"] - 1.01325, f1), seg=1, stijl=REF, lx=0, ly=-2)
edge("k201", (0.5, 1), "e203", (0.2, 0), [(X202 - 40, YC - 20), (X202 + 16, YC - 20)], C["ref"],
     lab("R2", cy["T_pers"], cy["P_cond_bar"] - 1.01325, f1), seg=0, stijl=REF, lx=-62)
edge("e203", (0.8, 0), "tv201", (1, 0.5), [(X202 + 64, YC - 20), (X202 + 112, YC - 20)], C["ref"],
     lab("R3", cy["T_cond"], cy["P_cond_bar"] - 1.01325, f1), seg=2, pos=0.6, stijl=REF, lx=-58)
edge("tv201", (0, 0.5), "e202", (0.8, 1), [(X202 + 112, YH + 105), (X202 + 64, YH + 105)], C["ref"],
     lab("R4", cy["T_evap"], cy["P_evap_bar"] - 1.01325, f1), seg=0, stijl=REF, lx=62)

# WP-202 (industrie)
plaat("e205", X206, YC, f"<b>E-205</b><br>condensor WP-202<br>{MW(r['Q_E205'])}")
compressor("k202", X206 - 70, YK, 60, f"<b>K-202</b><br>{MW(r['W_K202'])} (E7)<br>COP {nl(r['COP2'], 2)}",
           extra=LBL_L + "spacingRight=4;")
klep("tv202", X206 + 92, YK + 18, "", extra="rotation=90;")
tekst(X206 + 124, YK + 20, 50, 20, "<b>TV-202</b>", "align=left;")
f2 = f"{nl(m_ref2, 1)} kg/s"
edge("e206", (0.2, 1), "k202", (0.5, 0), [(X206 + 16, YH + 105), (X206 - 40, YH + 105)], C["ref"],
     lab("R5", cy2["T_evap"], cy2["P_evap_bar"] - 1.01325, f2), seg=1, stijl=REF, ly=-2)
edge("k202", (0.5, 1), "e205", (0.2, 0), [(X206 - 40, YC - 20), (X206 + 16, YC - 20)], C["ref"],
     lab("R6", cy2["T_pers"], cy2["P_cond_bar"] - 1.01325, f2), seg=0, stijl=REF, lx=-62)
edge("e205", (0.8, 0), "tv202", (1, 0.5), [(X206 + 64, YC - 20), (X206 + 112, YC - 20)], C["ref"],
     lab("R7", cy2["T_cond"], cy2["P_cond_bar"] - 1.01325, f2), seg=2, pos=0.3, stijl=REF, lx=62)
edge("tv202", (0, 0.5), "e206", (0.8, 1), [(X206 + 112, YH + 105), (X206 + 64, YH + 105)], C["ref"],
     lab("R8", cy2["T_evap"], cy2["P_evap_bar"] - 1.01325, f2), seg=0, stijl=REF, lx=62)

# warmtenet: retour → E-204 → E-203 → aanvoer
XT = 2040                    # rechterrand: aansluitingen
Y_NA, Y_NR = 1080, 1120
pijl("t_na", XT, Y_NA - 14, 150, "<b>Warmtenet aanvoer</b>", C["net"])
pijl("t_nr", XT, Y_NR - 14, 150, "<b>Warmtenet retour</b>", C["net"], links=True)
edge("t_nr", (0, 0.5), "e204", (0.2, 1), [(X204 + 16, Y_NR)], C["net"],
     lab("N1", i.T_net_retour, P_NET, kgs(net, False), ster=True), seg=0, pos=0.3)
edge("e204", (0.8, 1), "e203", (0.2, 1), [(X204 + 64, YC + 115), (X202 + 16, YC + 115)], C["net"],
     lab("N2", r["T_E204"], P_NET, kgs(net, False), ster=True), seg=1)
edge("e203", (0.8, 1), "t_na", (0, 0.5), [(X202 + 64, Y_NA)], C["net"],
     lab("N3", r["T_aanvoer"], P_NET, kgs(net, False), ster=True), seg=1, pos=0.25)

# industrie via E-205
pijl("t_ia", XT, YC + 6, 150, "<b>Industrie aanvoer</b>", C["ind"])
pijl("t_ir", XT, YC + 46, 150, "<b>Industrie retour</b>", C["ind"], links=True)
edge("e205", (1, 0.25), "t_ia", (0, 0.5), [], C["ind"],
     lab("I1", i.T_ind_aanvoer, P_IND, kgs(ind, False), ster=True), pos=0.55)
edge("t_ir", (0, 0.5), "e205", (1, 0.75), [], C["ind"],
     lab("I2", i.T_ind_retour, P_IND, kgs(ind, False), ster=True), pos=0.45, ly=0)

# ------------------------------------------------------------------ O2-lijn (onderaan)
YO = 1240
buis("e101", 640, YO - 30, f"<b>E-101</b> voorkoeler<br>{MW(-r['Q_E101'] * N)}",
     extra="labelPosition=left;verticalLabelPosition=top;align=right;verticalAlign=bottom;spacingRight=-20;")
edge("itm", (0.75, 1), "e101", (0, 0.5), [(480, YO)], C["o2"],
     lab("S13", i.T_O2_uit, i.P_O2_uit, kgs(i.m_O2mix)) + "<br>O₂ + waterdamp", seg=0, pos=0.5)
shape("v103", "mxgraph.pid.vessels.knock-out_drum", 840, YO - 70, 70, 140, "<b>V-103</b> KO-drum", LBL_T)
edge("e101", (1, 0.5), "v103", (0, 0.5), [], C["o2"], lab("S14", i.T_KO, i.P_O2_uit, kgs(i.m_O2mix)))

vertex("pk102", 1000, YO - 80, 250, 150, "rounded=1;arcSize=4;whiteSpace=wrap;html=1;dashed=1;fillColor=none;"
       "verticalAlign=bottom;fontSize=10;strokeColor=#586878;",
       f"<b>K-102</b> O₂-compressorpakket · {MW(r['W_K102'] * N)} (E4)")
compressor("k102", 1020, YO - 40, 80, "")
buis("pkk102", 1160, YO - 30, "")
tekst(1130, YO + 28, 120, 22, f"pakketkoeler {MW(r['Q_pak_K102'] * N)}", "fontSize=9;")
edge("v103", (0.86, 0.43), "k102", (0, 0.5), [], C["o2"], lab("S17", i.T_KO, i.P_O2_uit, kgs(r["m_gas"])))
edge("k102", (1, 0.5), "pkk102", (0, 0.5), [], C["o2"], f"{nl(r['T_uit_K102'], 0)} °C")
pijl("t_s18", 1460, YO - 14, 170, "<b>O₂ naar RWZI</b>", C["o2"])
edge("pkk102", (1, 0.5), "t_s18", (0, 0.5), [], C["o2"], lab("S18", r["T_S18"], i.P_RWZI, kgs(r["m_gas"])))

# condensaat: V-103 → P-101 → ITM
shape("p101", "mxgraph.pid.pumps.centrifugal_pump_1", 920, YO + 110, 50, 50,
      f"<b>P-101</b> · {nl(r['W_P101'] * N, 2)} kW (E5)", LBL_R + "spacingLeft=6;")
edge("v103", (0.4, 1), "p101", (0, 0.5), [(868, YO + 135)], C["o2"],
     lab("S15", i.T_KO, i.P_O2_uit, kgs(r["m_cond"])), seg=0, pos=0.5, lx=0)
edge("p101", (1, 0.12), "itm", (0.25, 1), [(1000, YO + 116), (1000, YO + 200), (380, YO + 200)], C["o2"],
     lab("S16", i.T_KO, i.P_ITM_voed, kgs(r["m_cond"])) + "<br>condensaat (UPW) direct terug", seg=2, pos=0.5)

# koelwater E-101
tekst(610, YO + 70, 120, 26, f"<b>KW1</b> in 20 °C · {nl(P_KW, 1)} barg*<br>{kgs(r['m_kw_E101'])}", "fontSize=9;")
kw1_in = list(geo)[-1]
tekst(630, YO - 120, 80, 20, "<b>KW1</b> uit 30 °C", "fontSize=9;")
kw1_uit = list(geo)[-1]
edge(kw1_in, (0.5, 0), "e101", (0.5, 1), [], C["kw"], stijl=KW)
edge("e101", (0.5, 0), kw1_uit, (0.5, 1), [], C["kw"], stijl=KW)

# ------------------------------------------------------------------ legenda
leg = [("H₂", C["h2"], ""), ("water / O₂ / condensaat", C["o2"], ""), ("afvalwater", C["waste"], ""),
       ("ITM-circuit (62/38 water/CoolFlow DTX)", C["kc"], ""), ("koelwatercircuit TW", C["tw"], ""),
       ("koudemiddel (WP-201 R1234ze(E), WP-202 R1233zd(E))", C["ref"], "8 3"), ("warmtenet", C["net"], ""),
       ("industrie", C["ind"], ""), ("koelwater KW", C["kw"], "6 3"), ("elektrisch", C["el"], "2 3")]
LX, LY = 1460, 1300
vertex("leg", LX, LY, 520, 30 + 20 * len(leg), "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;"
       "verticalAlign=top;align=left;spacingLeft=8;fontSize=11;strokeColor=#b4bec8;", "<b>Legenda</b>")
for k, (naam, kl, dp) in enumerate(leg):
    y = LY + 34 + 20 * k
    st = f"endArrow=none;html=1;strokeWidth=2;strokeColor={kl};" + (f"dashed=1;dashPattern={dp};" if dp else "")
    cellen.append(f'<mxCell id="{nid("l")}" style="{st}" edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
                  f'<mxPoint x="{LX + 12}" y="{y}" as="sourcePoint"/><mxPoint x="{LX + 60}" y="{y}" as="targetPoint"/>'
                  f'</mxGeometry></mxCell>')
    tekst(LX + 68, y - 9, 440, 18, naam, "align=left;fontSize=10;")
tekst(LX, LY + 36 + 20 * len(leg), 520, 30, "Label op de lijn: <b>stroom</b> temperatuur · druk (barg) · massadebiet "
      "(kg/s, alle 8 units samen). * = aangenomen druk.", "align=left;fontSize=9;fontColor=#586878;")

pfd_xml = "".join(cellen)

# ------------------------------------------------------------------ blad 2: stroomtabel
rows = []
for sid in ["S1", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S11", "S12", "S13", "S14", "S15", "S16", "S17",
            "S18", "A", "A2", "B", "TW", "TW-H", "TW1", "TW2", "TW4", "TW3", "N1", "N2", "N3", "I1", "I2",
            "KW1", "KW2", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]:
    if sid not in LD:
        continue
    l = LD[sid]
    m = l["m"] * (N if l["schaal"] == "per unit" else 1) / 3600
    if sid == "S9":
        m = r["m_S9"] * N / 3600
    p = l["p"]
    pster = {"TW": P_TW, "TW-H": P_TW, "TW1": P_TW, "TW2": P_TW, "TW3": P_TW, "TW4": P_TW, "N1": P_NET,
             "N2": P_NET, "N3": P_NET, "I1": P_IND, "I2": P_IND, "KW1": P_KW, "KW2": P_KW, "S3": P_AFV}
    p_txt = nl(p, 2 if p < 1 else 1) if p is not None else (nl(pster[sid], 1) + "*" if sid in pster else "–")
    rows.append(f"<tr><td><b>{sid}</b></td><td>{html.escape(l['naam'])}</td><td>{html.escape(l['medium'])}</td>"
                f"<td align='right'>{nl(l['T'], 1)}</td><td align='right'>{p_txt}</td>"
                f"<td align='right'>{nl(m, 3 if m < 1 else 2)}</td><td align='right'>{nl(m * 3600, 0)}</td></tr>")
tab = ("<b style='font-size:16px'>Stroomtabel – 8 × ITM Neptune V (vollast, EOL)</b><br>"
       "Bron: visualpfd-model (itm_model.py, CoolProp). Debieten voor de hele installatie. * = aangenomen druk."
       "<br><br><table border='1' cellpadding='4' style='border-collapse:collapse;font-size:11px'>"
       "<tr style='background:#f3f6f9'><th>Stroom</th><th>Van → naar</th><th>Medium</th><th>T (°C)</th>"
       "<th>p (barg)</th><th>ṁ (kg/s)</th><th>ṁ (kg/h)</th></tr>" + "".join(rows) + "</table>")
tab_xml = (f'<mxCell id="tab" value="{esc(tab)}" style="text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;'
           f'fontSize=11;" vertex="1" parent="1"><mxGeometry x="30" y="20" width="1100" height="1300" as="geometry"/>'
           f'</mxCell>')


def diagram(naam, did, inhoud, w, h):
    return (f'<diagram name="{naam}" id="{did}"><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" '
            f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{w}" pageHeight="{h}" '
            f'math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>{inhoud}</root></mxGraphModel>'
            f'</diagram>')


xml = ('<mxfile host="visualpfd">' + diagram("PFD", "pfd", pfd_xml, 2240, 1560)
       + diagram("Stroomtabel", "stroomtabel", tab_xml, 1169, 1654) + "</mxfile>\n")
with open(UIT, "w", encoding="utf-8") as fh:
    fh.write(xml)
print("geschreven:", os.path.relpath(UIT))

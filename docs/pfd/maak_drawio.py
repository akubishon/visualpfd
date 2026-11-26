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
C = dict(h2="#0050E6", o2="#00A030", waste="#8B4513", kc="#9C27B0", net="#FF8000", kw="#00A8E8",
         ref="#00A896", tw="#E6007E", ind="#D50000", el="#B8860B", ink="#111111")

# ------------------------------------------------------------------ opbouw
cellen = []
geo = {}
_n = [0]


def nid(p="c"):
    _n[0] += 1
    return f"_{p}{_n[0]}"


def esc(s):
    return html.escape(s, quote=True)


def vertex(cid, x, y, w, h, style, value="", parent="1"):
    geo[cid] = (x, y, w, h)
    STIJL[cid] = style
    cellen.append(f'<mxCell id="{cid}" value="{esc(value)}" style="{style}" vertex="1" parent="{parent}">'
                  f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return cid


PID = "html=1;pointerEvents=1;align=center;verticalLabelPosition=bottom;verticalAlign=top;dashed=0;fontSize=10;"
LBL_L = "labelPosition=left;verticalLabelPosition=middle;align=right;verticalAlign=middle;"
LBL_R = "labelPosition=right;verticalLabelPosition=middle;align=left;verticalAlign=middle;"
LBL_T = "verticalLabelPosition=top;verticalAlign=bottom;"


def shape(cid, s, x, y, w, h, value="", extra=""):
    return vertex(cid, x, y, w, h, f"shape={s};{PID}{extra}", value)


WARM, KOUD = "#E53935", "#1E63D6"   # poortmarkering: warme stroom (rood), koude stroom (blauw)
VLAK = "rounded=0;html=1;strokeColor=none;"


def merk(cid, warm=(), koud=()):
    """Gekleurd blokje op de connectoren van een wisselaar: rood = warme stroom, blauw = koude stroom.
    Getekend vóór de leidingen, zodat de pijlpunten erover vallen."""
    for kl, poorten in ((WARM, warm), (KOUD, koud)):
        for p in poorten:
            x, y = poort(cid, *p)
            vertex(nid("m"), x - 5, y - 5, 10, 10, f"rounded=0;html=1;fillColor={kl};strokeColor=#111111;"
                   "strokeWidth=0.8;")


# Platenwisselaar: draw.io-icoon 'Plate and Frame', een kwartslag gedraaid. Zichtbaar 80 × 70.
# Elk medium loopt diagonaal (het kruis): warm linksboven → rechtsonder, koud linksonder → rechtsboven. Poorten (draw.io-namen tussen haakjes):
TL, TR, BL, BR = (0, .94), (0, .06), (1, .94), (1, .06)     # linksboven (SW), rechtsboven (NW), ...
PL, PR = 4.8, 75.2                                          # x-positie poorten t.o.v. linkerkant


def plaat(cid, x, y, value, rechts=False):
    shape(cid, "mxgraph.pid.heat_exchangers.plate_and_frame_heat_exchanger", x + 5, y - 5, 70, 80, "",
          "rotation=90;fillColor=#ffffff;")
    merk(cid, warm=(TL, BR), koud=(BL, TR))
    if rechts:
        tekst(x + 86, y, 140, 70, value, "align=left;")
    else:
        tekst(x - 146, y, 140, 70, value, "align=right;")
    return cid


# Pijpenwisselaar (shell & tube): draw.io-icoon 'Single Pass', zichtbaar 100 × 34.
# Buiszijde W/E = warm proces, mantelzijde N/S = koelmiddel.
def buis(cid, x, y, value, extra="", mantel=True):
    shape(cid, "mxgraph.pid.heat_exchangers.single_pass_heat_exchanger", x, y, 100, 34, value,
          "fillColor=#ffffff;" + extra)
    merk(cid, warm=((0, .5), (1, .5)), koud=((.5, .2), (.5, .8)) if mantel else ())
    return cid


# Pakketkoeler (in het compressorpakket): draw.io-icoon 'Heat Exchanger (Coil Tubes)', zichtbaar 100 × 30.
# Spiraal NW → SE = warm gas, mantel SW → NE = koelmiddel.
def pakketkoeler(cid, x, y, mantel=True):
    shape(cid, "mxgraph.pid.heat_exchangers.heat_exchanger_(coil_tubes)", x, y, 100, 30, "", "fillColor=#ffffff;")
    merk(cid, warm=((.07, 0), (.93, 1)), koud=((.25, 1), (.75, 0)) if mantel else ())
    return cid


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
    return vertex(cid, x - 4, y - 4, 8, 8, f"ellipse;html=1;fillColor={kleur};strokeColor={kleur};"
                  "points=[[0.5,0.5,0]];", "")


WEST = set()                 # pijlen naar links (direction=west): draw.io draait hun poorten mee


# Standaard connectiepunten van de draw.io-iconen (uit de stencils / shape-code van draw.io).
RECHTHOEK = {(x, y) for x in (0, .25, .5, .75, 1) for y in (0, .25, .5, .75, 1) if x in (0, 1) or y in (0, 1)}
CONN = {
    "plate_and_frame_heat_exchanger": {(0, .06), (1, .06), (0, .94), (1, .94)},
    "heat_exchanger_(coil_tubes)": {(.07, 0), (.75, 0), (.25, 1), (.93, 1)},
    "single_pass_heat_exchanger": {(.5, .2), (.5, .8), (0, .5), (1, .5), (0, 0), (0, 1), (1, 0), (1, 1)},
    "compressor,_vacuum_pump": {(0, .5), (1, .5)},
    "air_cooler": {(.5, 0), (.5, 1), (0, .5), (1, .5), (1, .001), (1, .999), (0, .999), (0, .001)},
    "centrifugal_pump_1": {(.43, 0), (.43, 1), (.01, .5), (.86, .5), (.125, .125), (0, 1), (1, 0), (.855, 1)},
    "knock-out_drum": {(.393, 0), (.393, 1), (0, .5), (1, .458), (.775, .058), (.775, .942), (.005, .94),
                       (.005, .06)},
    "pressurized_vessel": {(.5, 0), (.5, 1), (0, .5), (1, .5), (.999, .063), (.999, .937), (.001, .937),
                           (.001, .063)},
    "valve": {(0, .5), (1, .5)},                     # pid2valves zonder aandrijving: leidingeinden
    "arrows2.arrow": {(0, .5), (1, .5)},
}
STIJL = {}


def toegestaan(cid):
    st = STIJL[cid]
    if "points=[[" in st:                              # eigen connectiepunten (ITM-blok, T-stukken)
        lst = st.split("points=")[1].split(";")[0]
        return {(float(a), float(b)) for a, b, *_ in __import__("json").loads(lst)}
    for k, v in CONN.items():
        if k in st:
            return v
    return RECHTHOEK


def poort(cid, fx, fy):
    assert (fx, fy) in toegestaan(cid), f"{cid}: ({fx}, {fy}) is geen connector van dit icoon"
    x, y, w, h = geo[cid]
    if cid in WEST:
        fx = 1 - fx
    if "rotation=90" in STIJL[cid]:                  # 90° rechtsom om het midden
        cx, cy_ = x + w / 2, y + h / 2
        dx, dy = (fx - .5) * w, (fy - .5) * h
        return (cx - dy, cy_ + dx)
    return (x + fx * w, y + fy * h)


def edge(src, sp, tgt, tp, pts, kleur, label="", seg=None, pos=0.5, pijlpunt=True, stijl="", lx=0, ly=0,
         lstyle=""):
    """Leiding van src (poort sp) naar tgt (poort tp) via punten pts. Het label komt op segment seg
    (index in de polyline; standaard het langste segment) op fractie pos van dat segment."""
    a = poort(src, *sp)
    b = poort(tgt, *tp)
    poly = [a] + list(pts) + [b]
    lens = [abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in zip(poly, poly[1:])]
    L = sum(lens) or 1
    if seg is None:
        seg = max(range(len(lens)), key=lambda k: lens[k])
    d = sum(lens[:seg]) + lens[seg] * pos
    xrel = 2 * d / L - 1
    ex = 1 - sp[0] if src in WEST else sp[0]
    en = 1 - tp[0] if tgt in WEST else tp[0]
    st = (f"html=1;rounded=0;jumpStyle=arc;jumpSize=10;strokeWidth=2;strokeColor={kleur};"
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
ITM_P = [[1, 50 / 420], [1, 210 / 420], [1, 370 / 420], [0, 150 / 420], [0, 270 / 420], [0.25, 1], [0.75, 1], [0.5, 0]]
vertex("itm", 330, 150, 200, 420, "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;verticalAlign=top;fontSize=11;"
       f"strokeWidth=1.6;points={ITM_P};".replace(" ", ""), "<b>8 × ITM Neptune V</b> (parallel)")
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
shape("v101", "mxgraph.pid.vessels.pressurized_vessel", 660, Y - 75, 60, 150,
      f"<b>V-101</b><br>LD-buffervat H₂<br>{nl(r['V_V101'], 0)} m³", "labelPosition=center;")
edge("itm", (1, 50 / 420), "v101", (0, 0.5), [], C["h2"],
     lab("S4", i.T_H2, i.P_H2_ITM, kgs(i.m_H2)))

vertex("pk101", 790, 120, 250, 170, "rounded=1;arcSize=4;whiteSpace=wrap;html=1;dashed=1;fillColor=none;"
       "verticalLabelPosition=top;verticalAlign=bottom;fontSize=10;strokeColor=#586878;",
       f"<b>K-101</b> H₂-compressorpakket · {MW(r['W_K101'] * N)} (E3)")
compressor("k101", 810, Y - 40, 80, "")
pakketkoeler("pkk101", 920, Y - 15)
tekst(800, 244, 140, 30, f"pakketkoeler {nl(r['T_uit_K101'], 0)} → {nl(r['T_S6'], 0)} °C<br>{MW(r['Q_pak_K101'] * N)} naar TW", "fontSize=9;")
edge("v101", (1, 0.5), "k101", (0, 0.5), [], C["h2"], lab("S5", i.T_H2, i.P_V101_min, kgs(r["m_S5"])))
edge("k101", (1, 0.5), "pkk101", (.07, 0), [(905, Y), (905, Y - 28), (927, Y - 28)], C["h2"],
     "")

buis("e102", 1110, Y - 17, "")
tekst(1214, 232, 90, 30, f"<b>E-102</b><br>{MW(-r['Q_E102'] * N)} naar TW", "fontSize=10;align=left;")
edge("pkk101", (.93, 1), "e102", (0, 0.5), [(1013, Y + 28), (1060, Y + 28), (1060, Y)], C["h2"], seg=3,
     label= lab("S6", r["T_S6"], i.P_K101_uit, kgs(r["m_S5"])))
buis("e103", 1290, Y - 17, f"<b>E-103</b> eindkoeler<br>{MW(-r['Q_E103'] * N)}", extra="labelPosition=left;verticalLabelPosition=top;align=right;verticalAlign=bottom;spacingRight=-6;")
edge("e102", (1, 0.5), "e103", (0, 0.5), [], C["h2"], lab("S7", i.T_E102_uit, i.P_K101_uit, kgs(r["m_S5"])))
knoop("j_s9", 1500, Y, C["h2"])
edge("e103", (1, 0.5), "j_s9", (0.5, 0.5), [], C["h2"], lab("S8", i.T_E103_uit, i.P_K101_uit, kgs(r["m_S5"])),
     pijlpunt=False, pos=0.55)
vertex("qc", 1560, Y - 20, 110, 40, "rounded=0;whiteSpace=wrap;html=1;fontSize=10;", "<b>QC</b> kwaliteit")
edge("j_s9", (0.5, 0.5), "qc", (0, 0.5), [], C["h2"])
shape("v102", "mxgraph.pid.vessels.pressurized_vessel", 1760, Y - 75, 60, 150,
      f"<b>V-102</b><br>HD-buffervat H₂<br>{nl(r['V_V102'], 1)} m³")
edge("qc", (1, 0.5), "v102", (0, 0.5), [], C["h2"],
     lab("S11", i.T_E103_uit, i.P_backbone, kgs(r["m_backbone"])))
klep("pcv101", 1870, Y - 12, "<b>PCV-101</b>", soort="globe")
edge("v102", (1, 0.5), "pcv101", (0, 0.5), [], C["h2"])
pijl("t_s12", 2040, Y - 14, 150, "<b>H₂-backbone</b>", C["h2"])
edge("pcv101", (1, 0.5), "t_s12", (0, 0.5), [], C["h2"], lab("S12", i.T_E103_uit, i.P_backbone, kgs(r["m_backbone"])))

# recycle S9 en blowoff S10
klep("fv101", 1250, 68, "<b>FV-101</b>", soort="globe", extra=LBL_T)
edge("j_s9", (0.5, 0.5), "fv101", (1, 0.5), [(1500, 80)], C["h2"], pijlpunt=True,
     stijl="dashed=1;dashPattern=4 3;")
edge("fv101", (0, 0.5), "v101", (0.999, 0.063), [(745, 80), (745, Y - 75 + 0.063 * 150)], C["h2"],
     lab("S9", i.T_E103_uit, i.P_V101_min, kgs(r["m_S9"])) + " (recycle, alleen deellast)", seg=0,
     stijl="dashed=1;dashPattern=4 3;")
pijl("t_s10", 760, 26, 150, "H₂ blowoff", C["h2"])
edge("v101", (0.001, 0.063), "t_s10", (0, 0.5), [(640, Y - 75 + 0.063 * 150), (640, 40)], C["h2"],
     "<b>S10</b> 0 kg/s", seg=2,
     stijl="dashed=1;dashPattern=4 3;")

# koelwater E-103
tekst(1275, 268, 130, 26, f"<b>KW2</b> in 20 °C · {nl(P_KW, 1)} barg*<br>{kgs(r['m_kw_E103'])}", "fontSize=9;")
tekst(1300, 110, 80, 26, "<b>KW2</b> uit 30 °C", "fontSize=9;")
edge(list(geo)[-2], (0.5, 0), "e103", (0.5, 0.8), [], C["kw"], stijl=KW)
edge("e103", (0.5, 0.2), list(geo)[-1], (0.5, 1), [], C["kw"], stijl=KW)

# ------------------------------------------------------------------ ITM-circuit + E-201 + AK
# Het ITM-circuit loopt altijd in serie: ITM → E-201 (warme kant) → luchtkoeler AK → ITM. Zonder warmte-
# afname staat alleen de koude kant van E-201 stil en voert AK alles af.
YE = 380                     # bovenkant E-201
plaat("e201", 680, YE, f"<b>E-201 ×8</b><br>{MW(r['Q_E201'])}<br>naar TW", rechts=True)
shape("ak", "mxgraph.pid.misc.air_cooler", 680 + PR - 40, 490, 80, 60,
      f"<b>AK ×8</b> luchtkoelers<br>altijd in serie · nu {MW(max(0.0, r['Q_AK']))}", LBL_R + "spacingLeft=6;")
edge("itm", (1, 210 / 420), "e201", TL, [(680 + PL, 360)], C["kc"],
     lab("A", i.T_kc_uit, i.P_kc, kgs(r["m_kc_unit"])), seg=0)
edge("e201", BR, "ak", (0.5, 0), [], C["kc"], f"<b>A2</b> {nl(r['T_kc_naE201'], 1)} °C", lx=42)
edge("ak", (0, 0.5), "itm", (1, 370 / 420), [], C["kc"],
     lab("B", i.T_kc_retour, i.P_kc, kgs(r["m_kc_unit"])))

# ------------------------------------------------------------------ warmteterugwinning (midden)
# In het platenwisselaar-icoon loopt elk medium diagonaal (zie het kruis): LB ↔ RO en LO ↔ RB.
# Warm medium: linksboven in → rechtsonder uit. Koud medium: linksonder in → rechtsboven uit (tegenstroom).
YH, YC, YK = 740, 420, 560   # bovenkant verdampers/E-204, condensors, compressoren
X204, X202, X206 = 1040, 1250, 1680
X203, X205 = X202 + 230, X206 + 230
Y_AAN, Y_RET = 340, 920      # TW-aanvoer (boven) en TW-retour (onder)
Y_TV = 860                   # koudemiddel TV → verdamper (onder de verdampers)
plaat("e204", X204, YH, "")
tekst(X204 - 160, YH, 135, 70, f"<b>E-204</b><br>directe<br>voorverwarming<br>{MW(r['Q_E204'])}", "align=right;")
plaat("e202", X202, YH, f"<b>E-202</b><br>verdamper WP-201<br>{MW(r['Q_L'])}", rechts=True)
plaat("e206", X206, YH, f"<b>E-206</b><br>verdamper WP-202<br>{MW(r['Q_L2'])}", rechts=True)

knoop("j_twa", 945, Y_AAN, C["tw"])   # samenkomst aanvoer (E-201's + H2-koelers)
knoop("j_twr", 900, Y_RET, C["tw"])   # aftakking retour naar de H2-koelers
edge("e201", TR, "j_twa", (0.5, 0.5), [(680 + PR, Y_AAN)], C["tw"],
     lab("TW", r["T_tw_a"], P_TW, kgs(tw_tot - tw_h2, False), ster=True), seg=1, pos=0.5, pijlpunt=False)
edge("j_twa", (0.5, 0.5), "e204", TL, [(X204 - 15, Y_AAN), (X204 - 15, YH - 20), (X204 + PL, YH - 20)], C["tw"],
     lab("TW1", r["T_tw_a"], P_TW, kgs(tw_tot, False), ster=True), seg=0, pos=0.5)
edge("e204", BR, "e202", TL, [(X204 + PR, YH + 90), (X202 - 20, YH + 90), (X202 - 20, YH - 20), (X202 + PL, YH - 20)],
     C["tw"], lab("TW2", r["T_tw_tussen"], P_TW, kgs(tw_tot, False), ster=True), seg=1, pos=0.5)
edge("e202", BR, "e206", TL, [(X202 + PR, YH + 90), (X206 - 20, YH + 90), (X206 - 20, YH - 20), (X206 + PL, YH - 20)],
     C["tw"], lab("TW4", r["T_tw_naE202"], P_TW, kgs(tw_tot, False), ster=True), seg=1, pos=0.62)
edge("e206", BR, "j_twr", (0.5, 0.5), [(X206 + PR, Y_RET)], C["tw"],
     lab("TW5", r["T_tw_r"], P_TW, kgs(tw_tot, False), ster=True), seg=1, pos=0.25, pijlpunt=False)
edge("j_twr", (0.5, 0.5), "e201", BL, [(680 + PL, Y_RET)], C["tw"],
     lab("TW3", r["T_tw_r"], P_TW, kgs(tw_tot - tw_h2, False), ster=True), seg=1, pos=0.62)
# aftakking naar de H2-koelers (parallel aan E-201): retour → E-102 → pakketkoeler K-101 → aanvoer.
# Met verwijzingen in plaats van een lange leiding dwars door het schema.
tekst(840, Y_RET + 18, 120, 30, "naar <b>E-102</b> en pakketkoeler K-101 (H₂-lijn)", "fontSize=9;")
edge("j_twr", (0.5, 0.5), list(geo)[-1], (0.5, 0), [], C["tw"],
     lab("TWH1", r["T_tw_r"], P_TW, kgs(tw_h2, False), ster=True), lx=70)
tekst(1100, 268, 120, 26, "<b>TWH1</b> van TW-retour (onder)", "fontSize=9;")
edge(list(geo)[-1], (0.5, 0), "e102", (0.5, 0.8), [], C["tw"])
edge("e102", (0.5, 0.2), "pkk101", (.75, 0), [(1160, 150), (995, 150)], C["tw"], "", seg=1)
edge("pkk101", (.25, 1), "j_twa", (0.5, 0.5), [], C["tw"],
     lab("TWH2", r["T_tw_a"], P_TW, kgs(tw_h2, False), ster=True), pos=0.55, lx=0)

# WP-201: E-202 (koude kant) → K-201 → E-203 (warme kant) → TV-201 → E-202
plaat("e203", X203, YC, "")
tekst(X203 + 9, YC + 72, 62, 44, f"<b>E-203</b><br>condensor<br>{MW(r['Q_H'])}", "fontSize=9;")
compressor("k201", X202 + 120, YK, 60, f"<b>K-201</b> · {MW(r['W_K201'])}<br>(E6) · COP {nl(r['COP'], 2)}", LBL_T)
klep("tv201", X203 + PR - 20, 628, "", extra="rotation=90;")
tekst(X203 + PR + 14, 630, 50, 20, "<b>TV-201</b>", "align=left;")
f1 = f"{nl(m_ref1, 1)} kg/s"
edge("e202", TR, "k201", (0, 0.5), [(X202 + PR, YK + 30)], C["ref"],
     lab("R1", cy["T_evap"], cy["P_evap_bar"] - 1.01325, f1), seg=0, pos=0.25, stijl=REF, lx=-55)
edge("k201", (1, 0.5), "e203", TL, [(X203 - 15, YK + 30), (X203 - 15, YC - 20), (X203 + PL, YC - 20)], C["ref"],
     lab("R2", cy["T_pers"], cy["P_cond_bar"] - 1.01325, f1), seg=1, pos=0.5, stijl=REF, lx=-58)
edge("e203", BR, "tv201", (0, 0.5), [], C["ref"],
     lab("R3", cy["T_cond"], cy["P_cond_bar"] - 1.01325, f1), pos=0.85, stijl=REF, lx=60)
edge("tv201", (1, 0.5), "e202", BL, [(X203 + PR, Y_TV), (X202 + PL, Y_TV)], C["ref"],
     lab("R4", cy["T_evap"], cy["P_evap_bar"] - 1.01325, f1), seg=1, pos=0.45, stijl=REF)

# WP-202 (industrie): E-206 → K-202 → E-205 → TV-202 → E-206
plaat("e205", X205, YC, "")
tekst(X205 + 9, YC + 72, 62, 44, f"<b>E-205</b><br>condensor<br>{MW(r['Q_E205'])}", "fontSize=9;")
compressor("k202", X206 + 120, YK, 60, f"<b>K-202</b> · {MW(r['W_K202'])}<br>(E7) · COP {nl(r['COP2'], 2)}", LBL_T)
klep("tv202", X205 + PR - 20, 628, "", extra="rotation=90;")
tekst(X205 + PR + 14, 630, 50, 20, "<b>TV-202</b>", "align=left;")
f2 = f"{nl(m_ref2, 1)} kg/s"
edge("e206", TR, "k202", (0, 0.5), [(X206 + PR, YK + 30)], C["ref"],
     lab("R5", cy2["T_evap"], cy2["P_evap_bar"] - 1.01325, f2), seg=0, pos=0.25, stijl=REF, lx=-55)
edge("k202", (1, 0.5), "e205", TL, [(X205 - 15, YK + 30), (X205 - 15, YC - 20), (X205 + PL, YC - 20)], C["ref"],
     lab("R6", cy2["T_pers"], cy2["P_cond_bar"] - 1.01325, f2), seg=1, pos=0.5, stijl=REF, lx=-58)
edge("e205", BR, "tv202", (0, 0.5), [], C["ref"],
     lab("R7", cy2["T_cond"], cy2["P_cond_bar"] - 1.01325, f2), pos=0.85, stijl=REF, lx=60)
edge("tv202", (1, 0.5), "e206", BL, [(X205 + PR, Y_TV), (X206 + PL, Y_TV)], C["ref"],
     lab("R8", cy2["T_evap"], cy2["P_evap_bar"] - 1.01325, f2), seg=1, pos=0.3, stijl=REF)

# warmtenet: retour → E-204 (koude kant) → E-203 (koude kant) → aanvoer
XT = 2120                    # rechterrand: aansluitingen
Y_NA, Y_IA, Y_IR, Y_NR = 370, 405, 565, 890
pijl("t_na", XT, Y_NA - 14, 150, "<b>Warmtenet aanvoer</b>", C["net"])
pijl("t_ia", XT, Y_IA - 14, 150, "<b>Industrie aanvoer</b>", C["ind"])
pijl("t_ir", XT, Y_IR - 14, 150, "<b>Industrie retour</b>", C["ind"], links=True)
pijl("t_nr", XT, Y_NR - 14, 150, "<b>Warmtenet retour</b>", C["net"], links=True)
edge("t_nr", (0, 0.5), "e204", BL, [(X204 + PL, Y_NR)], C["net"],
     lab("N1", i.T_net_retour, P_NET, kgs(net, False), ster=True), seg=0, pos=0.62)
edge("e204", TR, "e203", BL, [(X204 + PR, 680), (X203 + PL, 680)], C["net"],
     lab("N2", r["T_E204"], P_NET, kgs(net, False), ster=True), seg=1, pos=0.22)
edge("e203", TR, "t_na", (0, 0.5), [(X203 + PR, Y_NA)], C["net"],
     lab("N3", r["T_aanvoer"], P_NET, kgs(net, False), ster=True), seg=1, pos=0.62)

# industrie via E-205 (koude kant)
edge("e205", TR, "t_ia", (0, 0.5), [(X205 + PR, Y_IA)], C["ind"],
     lab("I1", i.T_ind_aanvoer, P_IND, kgs(ind, False), ster=True), seg=1, pos=0.5)
edge("t_ir", (0, 0.5), "e205", BL, [(X205 + PL, Y_IR)], C["ind"],
     lab("I2", i.T_ind_retour, P_IND, kgs(ind, False), ster=True), seg=0, pos=0.3)

# ------------------------------------------------------------------ O2-lijn (onderaan)
YO = 1150
buis("e101", 620, YO - 17, f"<b>E-101</b> voorkoeler<br>{MW(-r['Q_E101'] * N)}",
     extra="labelPosition=left;verticalLabelPosition=top;align=right;verticalAlign=bottom;spacingRight=-20;")
edge("itm", (0.75, 1), "e101", (0, 0.5), [(480, YO)], C["o2"],
     lab("S13", i.T_O2_uit, i.P_O2_uit, kgs(i.m_O2mix)) + "<br>O₂ + waterdamp", seg=0, pos=0.5)
shape("v103", "mxgraph.pid.vessels.knock-out_drum", 840, YO - 70, 70, 140, "<b>V-103</b> KO-drum", LBL_T)
edge("e101", (1, 0.5), "v103", (0, 0.5), [], C["o2"], lab("S14", i.T_KO, i.P_O2_uit, kgs(i.m_O2mix)))

vertex("pk102", 1000, YO - 80, 250, 150, "rounded=1;arcSize=4;whiteSpace=wrap;html=1;dashed=1;fillColor=none;"
       "verticalLabelPosition=top;verticalAlign=bottom;fontSize=10;strokeColor=#586878;",
       f"<b>K-102</b> O₂-compressorpakket · {MW(r['W_K102'] * N)} (E4)")
compressor("k102", 1020, YO - 40, 80, "")
pakketkoeler("pkk102", 1130, YO - 15, mantel=False)
tekst(1100, YO + 34, 150, 22, f"pakketkoeler {nl(r['T_uit_K102'], 0)} → {nl(r['T_S18'], 0)} °C · {MW(r['Q_pak_K102'] * N)}", "fontSize=9;")
YS17 = YO - 70 + 0.458 * 140              # gasuitlaat (nozzle) van de KO-drum
edge("v103", (1, 0.458), "k102", (0, 0.5), [(960, YS17), (960, YO)], C["o2"], seg=0, lstyle="",
     label= lab("S17", i.T_KO, i.P_O2_uit, kgs(r["m_gas"])), ly=22, lx=4)
edge("k102", (1, 0.5), "pkk102", (.07, 0), [(1115, YO), (1115, YO - 28), (1137, YO - 28)], C["o2"],
     "")
pijl("t_s18", 1460, YO - 14, 170, "<b>O₂ naar RWZI</b>", C["o2"])
edge("pkk102", (.93, 1), "t_s18", (0, 0.5), [(1223, YO + 28), (1270, YO + 28), (1270, YO)], C["o2"], seg=3,
     label= lab("S18", r["T_S18"], i.P_RWZI, kgs(r["m_gas"])))

# condensaat: V-103 → P-101 → ITM
shape("p101", "mxgraph.pid.pumps.centrifugal_pump_1", 920, YO + 110, 50, 50,
      f"<b>P-101</b> · {nl(r['W_P101'] * N, 2)} kW (E5)")
edge("v103", (0.393, 1), "p101", (0.01, 0.5), [(840 + 0.393 * 70, YO + 135)], C["o2"],
     lab("S15", i.T_KO, i.P_O2_uit, kgs(r["m_cond"])), seg=0, pos=0.5, lx=0)
edge("p101", (1, 0), "itm", (0.25, 1), [(1000, YO + 110), (1000, YO + 200), (380, YO + 200)], C["o2"],
     lab("S16", i.T_KO, i.P_ITM_voed, kgs(r["m_cond"])) + "<br>condensaat (UPW) direct terug", seg=2, pos=0.5)

# koelwater E-101
tekst(610, YO + 70, 120, 26, f"<b>KW1</b> in 20 °C · {nl(P_KW, 1)} barg*<br>{kgs(r['m_kw_E101'])}", "fontSize=9;")
kw1_in = list(geo)[-1]
tekst(630, YO - 120, 80, 20, "<b>KW1</b> uit 30 °C", "fontSize=9;")
kw1_uit = list(geo)[-1]
edge(kw1_in, (0.5, 0), "e101", (0.5, 0.8), [], C["kw"], stijl=KW)
edge("e101", (0.5, 0.2), kw1_uit, (0.5, 1), [], C["kw"], stijl=KW)

# ------------------------------------------------------------------ legenda
leg = [("H₂", C["h2"], ""), ("water / O₂ / condensaat", C["o2"], ""), ("afvalwater", C["waste"], ""),
       ("ITM-circuit (62/38 water/CoolFlow DTX)", C["kc"], ""), ("koelwatercircuit TW", C["tw"], ""),
       ("koudemiddel (WP-201 R1234ze(E), WP-202 R1233zd(E))", C["ref"], "8 3"), ("warmtenet", C["net"], ""),
       ("industrie", C["ind"], ""), ("koelwater KW", C["kw"], "6 3"), ("elektrisch", C["el"], "2 3")]
LX, LY = 1780, 960
vertex("leg", LX, LY, 440, 30 + 20 * (len(leg) + 2), "rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;"
       "verticalAlign=top;align=left;spacingLeft=8;fontSize=11;strokeColor=#b4bec8;", "<b>Legenda</b>")
for k, (naam, kl, dp) in enumerate(leg):
    y = LY + 34 + 20 * k
    st = f"endArrow=none;html=1;strokeWidth=2;strokeColor={kl};" + (f"dashed=1;dashPattern={dp};" if dp else "")
    cellen.append(f'<mxCell id="{nid("l")}" style="{st}" edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
                  f'<mxPoint x="{LX + 12}" y="{y}" as="sourcePoint"/><mxPoint x="{LX + 60}" y="{y}" as="targetPoint"/>'
                  f'</mxGeometry></mxCell>')
    tekst(LX + 68, y - 9, 360, 18, naam, "align=left;fontSize=10;")
for k, (naam, kl) in enumerate((("aansluiting warme stroom (wisselaar)", WARM), ("aansluiting koude stroom (wisselaar)", KOUD))):
    y = LY + 34 + 20 * (len(leg) + k)
    vertex(nid("l"), LX + 31, y - 5, 10, 10, f"rounded=0;html=1;fillColor={kl};strokeColor=#111111;strokeWidth=0.8;")
    tekst(LX + 68, y - 9, 360, 18, naam, "align=left;fontSize=10;")
tekst(LX, LY + 36 + 20 * (len(leg) + 2), 440, 30, "Label op de lijn: <b>stroom</b> temperatuur · druk (barg) · massadebiet "
      "(kg/s, alle 8 units samen). * = aangenomen druk.", "align=left;fontSize=9;fontColor=#586878;")

pfd_xml = "".join(cellen)

# ------------------------------------------------------------------ blad 2: stroomtabel
rows, json_rows = [], []
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
    json_rows.append(dict(id=sid, naam=l["naam"], medium=l["medium"], T=nl(l["T"], 1), p=p_txt,
                          kgs=nl(m, 3 if m < 1 else 2), kgh=nl(m * 3600, 0)))
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


xml = ('<mxfile host="visualpfd">' + diagram("PFD", "pfd", pfd_xml, 2340, 1420)
       + diagram("Stroomtabel", "stroomtabel", tab_xml, 1169, 1654) + "</mxfile>\n")
with open(UIT, "w", encoding="utf-8") as fh:
    fh.write(xml)
with open(os.path.join(HIER, "stromen.json"), "w", encoding="utf-8") as fh:
    __import__("json").dump(json_rows, fh, ensure_ascii=False, indent=1)
print("geschreven:", os.path.relpath(UIT), "en stromen.json")

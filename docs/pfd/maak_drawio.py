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


def plaat(cid, x, y, value, rechts=False, warm=(TL, BR), koud=(BL, TR)):
    shape(cid, "mxgraph.pid.heat_exchangers.plate_and_frame_heat_exchanger", x + 5, y - 5, 70, 80, "",
          "rotation=90;fillColor=#ffffff;")
    merk(cid, warm=warm, koud=koud)
    if not value:
        return cid
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
    cx, cy_ = x + w / 2, y + h / 2
    dx, dy = (fx - .5) * w, (fy - .5) * h
    if "rotation=90" in STIJL[cid]:                  # 90° rechtsom om het midden
        return (cx - dy, cy_ + dx)
    if "rotation=270" in STIJL[cid]:                 # 90° linksom: ingang W onder, uitgang E boven
        return (cx + dy, cy_ - dx)
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
ITM_P = [[1, 50 / 420], [1, 270 / 420], [1, 410 / 420], [0, 150 / 420], [0, 270 / 420], [0.25, 1], [0.75, 1], [0.5, 0]]
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

# ------------------------------------------------------------------ warmteterugwinning (midden)
# Platenwisselaars: elk medium loopt diagonaal (het kruis in het icoon): linksboven ↔ rechtsonder en
# linksonder ↔ rechtsboven. Elke warmtepomp is één blok: condensor boven, verdamper onder, compressor en
# smoorventiel aan de zijkanten. Door elk blok lopen twee rechte stromen: TW onder, warmtenet/industrie boven.
YC, YV = 440, 700            # bovenkant condensors en verdampers
Y_RET = 940                  # TW-retour (onder)
XT = 2080                    # rechterrand: aansluitingen
Y_NA, Y_IA, Y_IR, Y_NR = 340, 375, 550, 900

# ITM-circuit: altijd in serie ITM → E-201 (warme kant) → luchtkoelers AK → ITM
X201 = 680
plaat("e201", X201, YC, "")
tekst(X201 - 140, YC, 132, 70, f"<b>E-201 ×8</b><br>{MW(r['Q_E201'])}<br>naar TW", "align=right;")
shape("ak", "mxgraph.pid.misc.air_cooler", 800, 530, 80, 60,
      f"<b>AK ×8</b> luchtkoelers<br>altijd in serie · nu {MW(max(0.0, r['Q_AK']))}")
edge("itm", (1, 270 / 420), "e201", TL, [(X201 + PL, 420)], C["kc"],
     lab("A", i.T_kc_uit, i.P_kc, kgs(r["m_kc_unit"])), seg=0)
edge("e201", BR, "ak", (0.5, 0), [(840, YC + 70)], C["kc"], f"<b>A2</b> {nl(r['T_kc_naE201'], 1)} °C", seg=0)
edge("ak", (0, 0.5), "itm", (1, 410 / 420), [], C["kc"],
     lab("B", i.T_kc_retour, i.P_kc, kgs(r["m_kc_unit"])), pos=0.75)

# E-204: directe voorverwarming van het warmtenet met TW
X204 = 1000
plaat("e204", X204, YV, "")
tekst(X204 + 8, YV + 74, 64, 44, f"<b>E-204</b><br>voorverw.<br>{MW(r['Q_E204'])}", "fontSize=9;")
knoop("j_twa", 945, 400, C["tw"])     # samenkomst aanvoer (E-201's + H2-koelers)
knoop("j_twr", 900, Y_RET, C["tw"])   # aftakking retour naar de H2-koelers
edge("e201", TR, "j_twa", (0.5, 0.5), [(X201 + PR, 400)], C["tw"],
     lab("TW", r["T_tw_a"], P_TW, kgs(tw_tot - tw_h2, False), ster=True), seg=1, pijlpunt=False)
edge("j_twa", (0.5, 0.5), "e204", TL, [(980, 400), (980, YV - 20), (X204 + PL, YV - 20)], C["tw"],
     lab("TW1", r["T_tw_a"], P_TW, kgs(tw_tot, False), ster=True), seg=1, pos=0.68, lx=58)


def warmtepomp(naam, X, ev, co, k, tv, gespiegeld, cyc, m_ref, Q_co, Q_ev, W_k, cop, km, r_ids):
    """Warmtepomp als blok: condensor co boven (X, YC), verdamper ev onder (X, YV).
    Normaal: smoorventiel links, compressor rechts; gespiegeld: andersom."""
    s_ = -1 if gespiegeld else 1
    xk = X + 40 + s_ * 110               # compressorkolom
    # Laat bij WP-202 ruimte voor de industriële retour tussen condensor en smoorventiel.
    xt = X + (225 if gespiegeld else -70)
    if gespiegeld:   # koudemiddel: co BL ← K, co TR → TV, ev BR ← TV, ev TL → K
        plaat(co, X, YC, "", warm=(BL, TR), koud=(TL, BR))
        plaat(ev, X, YV, "", warm=(BL, TR), koud=(TL, BR))
        p_co_in, p_co_uit, p_ev_in, p_ev_uit = BL, TR, BR, TL
    else:            # koudemiddel: co BR ← K, co TL → TV, ev BL ← TV, ev TR → K
        plaat(co, X, YC, "")
        plaat(ev, X, YV, "")
        p_co_in, p_co_uit, p_ev_in, p_ev_uit = BR, TL, BL, TR
    xl = X + 82 if not gespiegeld else X - 64       # labels aan de kant van de compressor
    al = "align=left;" if not gespiegeld else "align=right;"
    tekst(xl, YC, 62, 70, f"<b>{co.upper().replace('E', 'E-', 1)}</b><br>condensor<br>{MW(Q_co)}", "fontSize=9;" + al)
    tekst(xl, YV, 62, 70, f"<b>{ev.upper().replace('E', 'E-', 1)}</b><br>verdamper<br>{MW(Q_ev)}", "fontSize=9;" + al)
    compressor(k, xk - 30, 575, 60, "", "rotation=270;")
    tekst(xk - 30 - 56 if not gespiegeld else xk + 34, 595, 52, 20, f"<b>{k.upper().replace('K', 'K-', 1)}</b>",
          "fontSize=9;" + ("align=right;" if not gespiegeld else "align=left;"))
    klep(tv, xt - 20, 458, "", extra="rotation=90;")
    tekst(xt + 6 if not gespiegeld else xt + 6, 460, 56, 20, f"<b>{tv.upper().replace('TV', 'TV-', 1)}</b>",
          "fontSize=9;align=left;")
    xa = lambda p_: X + (PL if p_ in (TL, BL) else PR)
    R1, R2, R3, R4 = r_ids
    edge(ev, p_ev_uit, k, (0, 0.5), [(xa(p_ev_uit), YV - 15), (xk, YV - 15)], C["ref"],
         lab(R1, cyc["T_evap"], cyc["P_evap_bar"] - 1.01325, m_ref), seg=1, stijl=REF, ly=-16)
    edge(k, (1, 0.5), co, p_co_in, [(xk, YC + 85), (xa(p_co_in), YC + 85)], C["ref"],
         lab(R2, cyc["T_pers"], cyc["P_cond_bar"] - 1.01325, m_ref), seg=1, stijl=REF, ly=18)
    edge(co, p_co_uit, tv, (0, 0.5), [(xa(p_co_uit), YC - 15), (xt, YC - 15)], C["ref"],
         lab(R3, cyc["T_cond"], cyc["P_cond_bar"] - 1.01325, m_ref), seg=1, stijl=REF, ly=-16)
    edge(tv, (1, 0.5), ev, p_ev_in, [(xt, YV + 85), (xa(p_ev_in), YV + 85)], C["ref"],
         lab(R4, cyc["T_evap"], cyc["P_evap_bar"] - 1.01325, m_ref), seg=1, stijl=REF, ly=16)
    x0, x1 = min(xk, xt) - 45, max(xk, xt) + 45
    vertex(nid("wp"), x0, YC - 45, x1 - x0, YV + 120 - (YC - 45), "rounded=1;arcSize=3;html=1;dashed=1;"
           "fillColor=none;strokeColor=#586878;verticalLabelPosition=bottom;verticalAlign=top;fontSize=10;",
           f"<b>{naam}</b> warmtepomp · {km}<br>{k.upper().replace('K', 'K-', 1)} {MW(W_k)} · COP {nl(cop, 2)}")


X1, X2 = 1330, 1800
warmtepomp("WP-201", X1, "e202", "e203", "k201", "tv201", False, cy, f"{nl(m_ref1, 1)} kg/s", r["Q_H"], r["Q_L"],
           r["W_K201"], r["COP"], i.koudemiddel, ("R1", "R2", "R3", "R4"))
warmtepomp("WP-202", X2, "e206", "e205", "k202", "tv202", True, cy2, f"{nl(m_ref2, 1)} kg/s", r["Q_E205"],
           r["Q_L2"], r["W_K202"], r["COP2"], i.koudemiddel2, ("R5", "R6", "R7", "R8"))

# TW-circuit: E-204 → verdamper E-202 → verdamper E-206 → retour → E-201
edge("e204", BR, "e202", TL, [(X204 + PR, YV + 100), (1180, YV + 100), (1180, YV - 20), (X1 + PL, YV - 20)],
     C["tw"], lab("TW2", r["T_tw_tussen"], P_TW, kgs(tw_tot, False), ster=True), seg=1)
edge("e202", BR, "e206", BL, [(X1 + PR, YV + 100), (X2 + PL, YV + 100)], C["tw"],
     lab("TW4", r["T_tw_naE202"], P_TW, kgs(tw_tot, False), ster=True), seg=1, pos=0.5)
edge("e206", TR, "j_twr", (0.5, 0.5), [(X2 + PR, YV - 20), (2060, YV - 20), (2060, Y_RET)], C["tw"],
     lab("TW5", r["T_tw_r"], P_TW, kgs(tw_tot, False), ster=True), seg=3, pos=0.1, pijlpunt=False)
edge("j_twr", (0.5, 0.5), "e201", BL, [(X201 + PL, Y_RET)], C["tw"],
     lab("TW3", r["T_tw_r"], P_TW, kgs(tw_tot - tw_h2, False), ster=True), seg=0)
# aftakking naar de H2-koelers (parallel aan E-201): retour → E-102 → pakketkoeler K-101 → aanvoer.
# Met verwijzingen in plaats van een lange leiding dwars door het schema.
tekst(840, Y_RET + 16, 120, 30, "naar <b>E-102</b> en pakketkoeler K-101 (H₂-lijn)", "fontSize=9;")
edge("j_twr", (0.5, 0.5), list(geo)[-1], (0.5, 0), [], C["tw"])
tekst(1100, 268, 120, 26, "<b>TWH1</b> van TW-retour (onder) · " + kgs(tw_h2, False), "fontSize=9;")
edge(list(geo)[-1], (0.5, 0), "e102", (0.5, 0.8), [], C["tw"])
edge("e102", (0.5, 0.2), "pkk101", (.75, 0), [(1160, 150), (995, 150)], C["tw"], "", seg=1)
edge("pkk101", (.25, 1), "j_twa", (0.5, 0.5), [], C["tw"],
     lab("TWH2", r["T_tw_a"], P_TW, kgs(tw_h2, False), ster=True), pos=0.6)

# warmtenet: retour → E-204 (koude kant) → condensor E-203 → aanvoer; industrie via condensor E-205
pijl("t_na", XT, Y_NA - 14, 150, "<b>Warmtenet aanvoer</b>", C["net"])
pijl("t_ia", XT, Y_IA - 14, 150, "<b>Industrie aanvoer</b>", C["ind"])
pijl("t_ir", X2 + 110, Y_IR - 14, 108, "<b>Industrie retour</b>", C["ind"], links=True)
pijl("t_nr", X204 + 480, Y_NR - 14, 150, "<b>Warmtenet retour</b>", C["net"], links=True)
edge("t_nr", (0, 0.5), "e204", BL, [(X204 + PL, Y_NR)], C["net"],
     lab("N1", i.T_net_retour, P_NET, kgs(net, False), ster=True), seg=0, pos=0.3)
edge("e204", TR, "e203", BL, [(X204 + PR, YC + 90), (X1 + PL, YC + 90)], C["net"],
     lab("N2", r["T_E204"], P_NET, kgs(net, False), ster=True), seg=1, pos=0.33)
edge("e203", TR, "t_na", (0, 0.5), [(X1 + PR, Y_NA)], C["net"],
     lab("N3", r["T_aanvoer"], P_NET, kgs(net, False), ster=True), seg=1, pos=0.62)
edge("e205", TL, "t_ia", (0, 0.5), [(X2 + PL, Y_IA)], C["ind"],
     lab("I1", i.T_ind_aanvoer, P_IND, kgs(ind, False), ster=True), seg=1, pos=0.55)
edge("t_ir", (0, 0.5), "e205", BR, [(X2 + PR, Y_IR)], C["ind"],
     lab("I2", i.T_ind_retour, P_IND, kgs(ind, False), ster=True), seg=0, lx=55, ly=27)

# ------------------------------------------------------------------ O2-lijn (onderaan)
YO = 1170
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
LX, LY = 1800, 1080
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


xml = ('<mxfile host="visualpfd">' + diagram("PFD", "pfd", pfd_xml, 2300, 1450)
       + diagram("Stroomtabel", "stroomtabel", tab_xml, 1169, 1654) + "</mxfile>\n")
with open(UIT, "w", encoding="utf-8") as fh:
    fh.write(xml)
with open(os.path.join(HIER, "stromen.json"), "w", encoding="utf-8") as fh:
    __import__("json").dump(json_rows, fh, ensure_ascii=False, indent=1)
print("geschreven:", os.path.relpath(UIT), "en stromen.json")

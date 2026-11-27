"""Koppeling tussen de twee draw.io-bladen en het live procesmodel."""

from functools import lru_cache
from pathlib import Path
import re
from xml.etree import ElementTree

PFD_MAP = Path(__file__).resolve().parents[1] / "docs" / "pfd"
OPSTELLINGEN = {"industrie": "Industriewarmte", "warmtenet": "Warmtenet + industrie"}

# De teksten beschrijven het apparaat in de stroomrichting van de getekende poorten.
APPARATEN = {
    "itm": ("ITM Neptune V", "De elektrolysers maken waterstof en zuurstof uit voedingswater. Het ITM-koelmiddel neemt restwarmte op.",
            ("Q_ITM_tot", "P_AC_tot"), ("T_vers", "T_H2", "T_O2_uit", "T_kc_uit", "T_kc_retour")),
    "ac": ("AC-net", "Het AC-net levert elektrisch vermogen aan de elektrolysers.", ("P_AC_tot",), ()),
    "v101": ("V-101 · Lagedrukbuffer", "V-101 vangt debietschommelingen op vóór K-101. Bij deellast komt er recycle bij.",
             ("V_V101",), ("T_H2",)),
    "pk101": ("K-101 · H₂-compressorpakket", "De compressor verhoogt de waterstofdruk. De pakketkoeler voert daarna een deel van de warmte af.",
              ("W_K101_tot", "Q_pak_K101_tot"), ("T_H2",)),
    "k101": ("K-101 · H₂-compressor", "Waterstof neemt tijdens compressie arbeid op. Druk, enthalpie en temperatuur stijgen.",
             ("W_K101_tot",), ("T_H2",)),
    "pkk101": ("Pakketkoeler K-101", "De warme persstroom staat warmte af en gaat vervolgens naar E-102.",
               ("Q_pak_K101_tot",), ()),
    "e102": ("E-102 · H₂-nakoeler", "De nakoeler verlaagt de temperatuur van H₂ uit de pakketkoeler.", ("Q_E102_tot",), ("T_E102_uit",)),
    "e103": ("E-103 · H₂-eindkoeler", "Koelwater voert warmte af zodat H₂ op de gewenste temperatuur naar de kwaliteitscontrole gaat.",
             ("Q_E103_tot",), ("T_E103_uit", "T_kw_in", "T_kw_uit")),
    "qc": ("QC · Kwaliteitscontrole", "Waterstof die deze processtap passeert gaat door naar de hogedrukbuffer.", (), ()),
    "v102": ("V-102 · Hogedrukbuffer", "V-102 buffert de geproduceerde waterstof vóór levering aan het backbone-net.", ("V_V102",), ()),
    "pcv101": ("PCV-101 · Drukregelklep", "De drukregelklep levert H₂ op de opgegeven backbone-druk.", (), ()),
    "fv101": ("FV-101 · Recycleklep", "Bij onvoldoende productiedebiet gaat een deel van de H₂ terug naar de zuigzijde van K-101.", (), ()),
    "e201": ("E-201 · Platenwisselaar", "ITM-koelmiddel geeft warmte af aan het TW-water. Beide media stromen aan hun eigen kant van de platen.",
             ("Q_E201",), ("T_kc_uit", "T_kc_retour")),
    "ak": ("AK · Luchtkoelers", "Het ITM-koelmiddel uit E-201 gaat via de luchtkoelers terug naar de ITM-units. De luchtkoelers voeren het overschot af.",
           ("Q_AK",), ("T_kc_retour",)),
    "e204": ("E-204 · Voorverwarmer", "TW-water verwarmt de warmtenetretour vóór de condensor van WP-201.", ("Q_E204",),
             ("T_net_retour", "T_E204_uit")),
    "e202": ("E-202 · Verdamper WP-201", "Koudemiddel verdampt aan de lage-drukzijde door warmte uit het TW-water op te nemen.", ("Q_L",), ()),
    "e203": ("E-203 · Condensor WP-201", "Koudemiddel condenseert en geeft zijn warmte af aan het warmtenet.", ("Q_H",),
             ("T_net_aanvoer",)),
    "e205": ("E-205 · Condensor WP-202", "Industriewater stroomt van de retour door E-205 naar de aanvoer. Koudemiddel condenseert en geeft hierbij warmte af.",
             ("Q_ind",), ("T_ind_aanvoer", "T_ind_retour")),
    "e206": ("E-206 · Verdamper WP-202", "Koudemiddel neemt warmte op uit het TW-water en verdampt.", ("Q_L2",), ()),
    "k201": ("K-201 · Compressor WP-201", "De compressor verhoogt de druk en enthalpie van de koudemiddeldamp.", ("W_K201", "COP"), ()),
    "k202": ("K-202 · Compressor WP-202", "De compressor verhoogt de druk en enthalpie van de koudemiddeldamp.", ("W_K202", "COP2"), ()),
    "tv201": ("TV-201 · Smoorventiel", "Vloeibaar koudemiddel expandeert naar de verdampingsdruk. De enthalpie blijft gelijk.", (), ()),
    "tv202": ("TV-202 · Smoorventiel", "Vloeibaar koudemiddel expandeert naar de verdampingsdruk. De enthalpie blijft gelijk.", (), ()),
    "wp201": ("WP-201 · Warmtenet", "E-202 neemt warmte op in de verdamper. De compressor zorgt voor een hogere temperatuur, waarna E-203 warmte afgeeft aan het net.",
              ("COP", "Q_H", "Q_L", "W_K201"), ("T_net_aanvoer", "T_net_retour")),
    "wp202": ("WP-202 · Industriewarmte", "E-206 neemt warmte op uit het TW-water. Na compressie geeft het koudemiddel die warmte samen met het compressorwerk af via E-205.",
              ("COP2", "Q_ind", "Q_L2", "W_K202"), ("T_ind_aanvoer", "T_ind_retour")),
    "e101": ("E-101 · O₂-voorkoeler", "Koelwater koelt het zuurstofmengsel af. Een deel van de waterdamp condenseert.", ("Q_E101_tot",),
             ("T_O2_uit", "T_KO", "T_kw_in", "T_kw_uit")),
    "v103": ("V-103 · KO-drum", "De KO-drum scheidt vloeibaar water af. Zuurstof en de resterende waterdamp gaan verder naar K-102.", (), ("T_KO",)),
    "pk102": ("K-102 · O₂-compressorpakket", "Het pakket comprimeert het vochtige O₂-mengsel en koelt de persstroom.", ("W_K102_tot", "Q_pak_K102_tot"), ()),
    "k102": ("K-102 · O₂-compressor", "De compressor brengt het vochtige gas op de leverdruk voor RWZI.", ("W_K102_tot",), ()),
    "pkk102": ("Pakketkoeler K-102", "De pakketkoeler voert warmte af uit het samengeperste gas.", ("Q_pak_K102_tot",), ()),
    "p101": ("P-101 · Condensaatpomp", "De pomp brengt condensaat op voedingswaterdruk en voert het direct terug naar ITM.", ("W_P101_tot",), ()),
    "t_s1": ("Vers UPW", "Vers ultrapuur water vult het teruggewonnen condensaat aan.", (), ("T_vers",)),
    "t_s3": ("Afvalwater", "Afvoer van proceswater uit de elektrolysers.", (), ("T_afvalwater",)),
    "t_s10": ("H₂-afblaasleiding", "Deze leiding is gesloten in de stationaire procesberekening.", (), ()),
    "t_s12": ("H₂-backbone", "Leverpunt van de geproduceerde waterstof.", (), ()),
    "t_s18": ("O₂ naar RWZI", "Leverpunt van het gecomprimeerde, vochtige zuurstofmengsel.", (), ()),
    "t_ia": ("Industrieaanvoer", "Het warme water stroomt uit E-205 naar de industriële verbruiker.", (), ("T_ind_aanvoer",)),
    "t_ir": ("Industrieretour", "Afgekoeld industriewater keert terug naar E-205.", (), ("T_ind_retour",)),
    "t_na": ("Warmtenetaanvoer", "Het warme netwater stroomt naar de afnemers.", (), ("T_net_aanvoer",)),
    "t_nr": ("Warmtenetretour", "Het afgekoelde netwater keert terug naar de voorverwarmer.", (), ("T_net_retour",)),
    "j_s9": ("H₂-splitsing", "Hier splitst het debiet in levering en recycle.", (), ()),
    "j_twa": ("TW-aanvoerverzamelpunt", "De warme takken van E-201 en de H₂-koelers komen samen.", (), ()),
    "j_twr": ("TW-retourverdeling", "Het afgekoelde water splitst naar E-201 en de H₂-koelers.", (), ()),
}

GROEPSLEDEN = {
    "itm": tuple(f"itm{j}" for j in range(1, 9)),
    "pk101": ("k101", "pkk101"), "pk102": ("k102", "pkk102"),
    "wp201": ("e202", "e203", "k201", "tv201"), "wp202": ("e205", "e206", "k202", "tv202"),
}

# Losse labels en gekleurde poortmarkeringen zijn losse cellen in de bron.
# Koppel ze aan hun apparaat zodat ze met het symbool meebewegen.
BIJLAGEN = {
    "industrie": {
        "pkk101": (9, (7, 8)), "e102": (14, (12, 13)), "e103": (None, (16, 17, 18, 19)),
        "e201": (38, (34, 35, 36, 37)), "e205": (50, (42, 43, 44, 45)), "e206": (51, (46, 47, 48, 49)),
        "k202": (52, ()), "tv202": (53, ()), "e101": (None, (64, 65, 66, 67)), "pkk102": (72, (70, 71)),
    },
    "warmtenet": {
        "pkk101": (11, (7, 8, 9, 10)), "e102": (18, (14, 15, 16, 17)), "e103": (None, (20, 21, 22, 23)),
        "e201": (41, (37, 38, 39, 40)), "e204": (49, (45, 46, 47, 48)), "e203": (60, (52, 53, 54, 55)),
        "e202": (61, (56, 57, 58, 59)), "k201": (62, ()), "tv201": (63, ()),
        "e205": (77, (69, 70, 71, 72)), "e206": (78, (73, 74, 75, 76)),
        "k202": (79, ()), "tv202": (80, ()), "e101": (None, (101, 102, 103, 104)), "pkk102": (109, (107, 108)),
    },
}

REFERENTIES = {
    "industrie": {"_t29": "KW2-in", "_t30": "KW2-uit", "_t78": "KW1-in", "_t79": "KW1-uit"},
    "warmtenet": {"_t33": "KW2-in", "_t34": "KW2-uit", "_t115": "KW1-in", "_t116": "KW1-uit",
                  "_t90": "TWH1", "_t92": "TWH1"},
}

ZONDER_LABEL = {
    ("k101", "pkk101"): "K101-uit", ("j_s9", "qc"): "S11-in",
    ("v102", "pcv101"): "V102-uit", ("j_s9", "fv101"): "S9-in",
    ("k102", "pkk102"): "K102-uit", ("e102", "pkk101"): "TWH-tussen",
}


@lru_cache(maxsize=2)
def schema(opstelling):
    bestand = "PFD.drawio" if opstelling == "industrie" else "PFD-warmtenet.drawio"
    model = ElementTree.parse(PFD_MAP / bestand).find("./diagram[@id='pfd']/mxGraphModel")
    cellen = {cell.get("id"): cell for cell in model.findall("root/mxCell")}
    if opstelling == "industrie":
        wp_cellen, legenda, industrienoot = {"_wp58": "wp202"}, "_t104", "_t63"
        cellen["_t33"].set("value", "H₂-koelers → externe koeling")
    else:
        wp_cellen, legenda, industrienoot = {"_wp68": "wp201", "_wp85": "wp202"}, "_t143", None
    for oud, nieuw in wp_cellen.items():
        cellen[oud].set("id", nieuw)
        cellen[nieuw] = cellen.pop(oud)

    labels = {}
    bijlagen = {}
    for onderdeel, (label_nr, markeringen) in BIJLAGEN[opstelling].items():
        hulp = [f"_m{nr}" for nr in markeringen]
        if label_nr:
            label = f"_t{label_nr}"
            labels[label] = onderdeel
            hulp.append(label)
        bijlagen[onderdeel] = hulp

    referenties = REFERENTIES[opstelling]
    apparaten = {}
    for cid, (naam, uitleg, getallen, velden) in APPARATEN.items():
        if cid not in cellen:
            continue
        apparaten[cid] = dict(naam=naam, uitleg=uitleg, getallen=getallen, velden=velden)
        if cid in ("itm", "wp201", "wp202", "pk101", "pk102", "ac", "v101", "v102", "p101", "ak", "e101", "e103", "v103"):
            labels[cid] = cid
    for j in range(1, 9):
        cid = f"itm{j}"
        apparaten[cid] = dict(apparaten["itm"], naam=f"ITM-unit {j}", unit=j,
                              getallen=(f"unit{j}.last", f"unit{j}.warmte", f"unit{j}.AC"))
        labels[cid] = cid

    leidingen = {}
    for cid, cell in cellen.items():
        bron, doel = cell.get("source"), cell.get("target")
        if cell.get("edge") != "1" or not bron or not doel:
            continue
        oud = cell.get("value", "")
        stream = re.match(r"<b>([A-Z][A-Z0-9]*)</b>", oud)
        if (bron, doel) == ("ac", "itm"):
            leidingen[cid] = dict(stroom=None, bron=bron, doel=doel, label=True, getal="P_AC_tot")
        else:
            stroom = stream[1] if stream else referenties.get(bron) or referenties.get(doel) or ZONDER_LABEL[bron, doel]
            leidingen[cid] = dict(stroom=stroom, bron=bron, doel=doel, label=bool(oud))
        cell.set("value", "")

    for cid, stroom in referenties.items():
        naam = stroom.replace("-in", " in").replace("-uit", " uit")
        cellen[cid].set("value", naam)
        apparaten[cid] = dict(naam=naam, uitleg="Aansluiting van de waterkring.", getallen=(), velden=())
    for cid in labels:
        cellen[cid].set("value", "")
    verwijder = [legenda, "_t2"]
    if industrienoot:
        verwijder.append(industrienoot)
    for cid in verwijder:
        model.find("root").remove(cellen[cid])
    cellen["_t1"].set("value", f"<b>PFD · {OPSTELLINGEN[opstelling]}</b>")
    for cid, cell in cellen.items():
        if cell.get("value", "").startswith("koudemiddel (WP-"):
            cell.set("value", "koudemiddel (warmtepompcircuit)")

    return {
        "xml": ElementTree.tostring(model, encoding="unicode"),
        "apparaten": apparaten, "leidingen": leidingen, "labels": labels, "bijlagen": bijlagen,
        "groepen": {cid: leden for cid, leden in GROEPSLEDEN.items() if cid in apparaten},
    }

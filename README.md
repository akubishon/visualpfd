# visualpfd – ITM Neptune V procesimulator

Visuele simulatie van het PFD van 8 × ITM Neptune V (40 MW) met massa- en energiebalans, doorgerekend met CoolProp.

## Streamlit-app (live CoolProp)
Dubbelklik `start_windows.bat` (Windows) of `start_mac_linux.sh` (Mac/Linux), of in een terminal:

    pip install -r requirements.txt
    streamlit run app.py

De app opent in je browser op http://localhost:8501. Elke schuifbeweging rekent het hele PFD
opnieuw door met echte CoolProp-aanroepen (circa 20 ms per doorrekening). Tabbladen: procesflowschema,
balansen, warmtepomp (log p–h), H₂-compressie (T–s), gevoeligheidsanalyse, rekenblad ↔ CoolProp,
stroomtabel en leidingen (beide te downloaden als CSV). Python 3.10 of nieuwer.

Bovenaan staat een statusbord met de 8 ITM-units (vollast, deellast, stand-by of onderhoud) en de
overige apparatuur. In de zijbalk kies je:
- Handmatig: een gevraagde installatielast; de units worden bijgeschakeld of de last wordt gelijk verdeeld.
- Dagprofiel wind: de last volgt een windprofiel over 24 uur; met ▶ Afspelen loopt de klok uur voor uur.
- Units uitvinken voor onderhoud, en het warmtenet of de warmtepomp uitzetten.

## Condensaat direct terug naar de units
Het condensaat uit de KO-drum V-103 is UPW. Het wordt niet meer met het verse voedwater gemengd: P-101 pompt het
via S16 direct terug in de eigen ITM-unit. S1 levert alleen de UPW-suppletie (voedwater − condensaat). Het
mengpunt en stroom S2 zijn vervallen.

## Warmteterugwinning uit het ITM-circuit
Elke ITM-unit heeft een eigen, gesloten koelcircuit (datasheet EOL: 62/38 water/CoolFlow DTX, 278.814 kg/h,
48 → 54,5 °C, 4,4 barg) dat standaard met luchtkoelers wordt gekoeld. In het model:
- **E-201 ×8**: per unit een platenwisselaar op het ITM-circuit, met de luchtkoeler **AK** erachter als trim/back-up.
  Het ITM-circuit blijft gesloten en wordt nergens gemengd.
- **Tussencircuit TW** (water, gedeeld): haalt de warmte uit de acht E-201's (≈ 45 → 51,5 °C bij ΔT 3 K).
- **E-204**: directe voorverwarming van het warmtenet vanuit TW.
- **WP-201** (E-202 verdamper op TW, K-201, E-203 condensor): tilt het net naar de aanvoertemperatuur.
- **WP-202** (E-206 verdamper op TW, K-202, E-205 condensor): levert de industrie op een eigen, hogere temperatuur
  (standaard 2 MW, 75 → 95 °C, R1233zd(E)).
- Wat niet wordt afgenomen, gaat via de luchtkoelers naar buiten.
- **H₂-warmte naar de industrie** (instelbaar): E-102 is gesplitst. E-102A koelt de H₂ (≈ 161 °C) tot
  T retour industrie + ΔT min (80 °C) en warmt het industriewater voor; E-102B koelt verder tot 50 °C voor de
  warmtenet-zijstroom. De pakketkoeler van K-101 (191 → 161 °C) kan mee worden teruggewonnen. WP-202 levert
  alleen nog de rest.

## Leidingdimensionering
Tabblad *Leidingen* (en de kaart onderaan de browserpagina) geeft per leiding de minimale binnendiameter
d_min = √(4·V̇ / (π·v_max)), met V̇ = ṁ/ρ uit CoolProp, plus de kleinste RVS-pijp ASME B36.19 sch. 40S die past
en de werkelijke snelheid daarin. Ontwerppunt: vollast per unit met warmtenet en warmtepomp aan; S9 bij maximale
recycle. De maximale snelheden staan als invoer in `Invoer` (`v_max_*`) en zijn in beide apps aan te passen.
In Python: `from itm_model import leidingen; leidingen()`.

## Simulatie in de browser (zonder Python)
Dubbelklik `browser/ITM-procesimulator.html`. Er is geen server en geen installatie nodig, en het werkt ook offline
(zonder internet gebruikt de pagina standaardlettertypes). De CoolProp-eigenschappen zitten al in het bestand.

## Python-model met echte CoolProp
    pip install CoolProp numpy
    python itm_model.py                       # vergelijking rekenblad ↔ CoolProp
    python itm_model.py --tables tables.json  # eigenschapstabellen opnieuw maken

Invoer aanpassen: de standaardwaarden staan in de dataclass `Invoer` bovenaan `itm_model.py`, bijvoorbeeld:

    from itm_model import Invoer, vergelijk
    vergelijk(Invoer(T_O2_uit=65, eta_K101=0.8, koudemiddel="Ammonia"))

## Losse bestanden (als je de pagina zelf wilt aanpassen)
Na een wijziging bouw je het losse bestand opnieuw met `python browser/bundel.py`.
`browser/index.html` + `model.js` + `tables.json` hebben een lokale webserver nodig, omdat de browser
`fetch` blokkeert bij bestanden die je met dubbelklik opent:

    python -m http.server 8000
    # open http://localhost:8000/index.html

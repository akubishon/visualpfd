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

## Warmteterugwinning: één gesloten koelwatercircuit
Elke ITM-unit heeft een eigen, gesloten koelcircuit (datasheet EOL: 62/38 water/CoolFlow DTX, 278.814 kg/h,
48 → 54,5 °C, 4,4 barg) dat standaard met luchtkoelers wordt gekoeld. Het schema is zo eenvoudig mogelijk gehouden:
- **Langs de units loopt één gesloten koelwatercircuit TW** (water, ≈ 45 → 51,5 °C). Per unit zitten daarop:
  - **E-201**: platenwisselaar op het ITM-circuit, met de luchtkoeler **AK** erachter als trim/back-up. Het
    ITM-circuit blijft gesloten.
  - **De H₂-koelers**: pakketkoeler K-101 (191 → 161 °C) en E-102 (161 → 50 °C).
- **Centraal op TW**: E-204 (directe voorverwarming net 40 → 45 °C), warmtepomp WP-201 (net naar 70 °C) en
  warmtepomp WP-202 (industrie op eigen temperatuur, standaard 2 MW bij 75 → 95 °C).
- Op koud koelwater blijven alleen E-101 (O₂ naar 30 °C) en E-103 (H₂ naar 25 °C): die moeten kouder dan het
  koelwatercircuit.
- Wat niet wordt afgenomen, gaat via de luchtkoelers naar buiten.

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

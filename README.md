# visualpfd – ITM Neptune V procesimulator

Visuele simulatie van het PFD van 8 × ITM Neptune V (40 MW) met massa- en energiebalans, doorgerekend met CoolProp.

## Lokale Streamlit-app met live CoolProp

Installeer de Python-pakketten eenmalig met Python 3.10 of nieuwer.

    pip install -r requirements.txt

Start met `start_windows.bat` op Windows of `./start_mac_linux.sh` op macOS en Linux. Als je de pakketten
in `.venv` hebt geïnstalleerd, gebruiken de scripts die omgeving. De app opent lokaal op
`http://127.0.0.1:8501`. CoolProp, de draw.io-symbolen en de formuleweergave werken na installatie offline.

- **Industriewarmte** opent met acht ITM-units op vollast en maximale afname via WP-202. Voor een eigen
  warmtevraag zet je **Maximale afname** uit. Kies **Warmtenet + industrie** voor E-204, WP-201 en WP-202.
- Kies **Warmtebalans**, **Massabalans** of **Samen**. Klik op een apparaat voor de aansluitingen en
  eventuele temperatuurinstellingen. Klik op een waarde voor de formule, getallen met eenheden en de herkomst.
  Klik op een tussenresultaat om de afleiding te volgen. Het schema markeert de betrokken leidingen.
- Versleep apparaten via hun symbool of groepskader. De lokale browseropslag bewaart de indeling per opstelling.
  Met **Herstel indeling** zet je de draw.io-posities terug.
- De **Stroomtabel** toont de actuele toestanden, dichtheden en debieten in kg/h, kg/s, m³/h en m³/s.
  **Analyses** biedt onder meer de warmtepompcyclus, gevoeligheidsanalyse, rekenbladvergelijking en leidingdimensionering.
- In de zijbalk kun je de last handmatig instellen, een winddag afspelen en units voor onderhoud uitschakelen.

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

## Warmtepompen: T–s-diagram en koudemiddelkeuze
Tabblad *Warmtepomp* (Streamlit) en de warmtepompkaart in de browser tonen voor WP-201 en WP-202 het T–s- en log p–h-diagram
met de vier stappen (verdampen, comprimeren, condenseren, smoren), de toestandspunten en een uitleg per stap. Daaronder staat een
vergelijking van 16 koudemiddelen (COP, drukken, perstemperatuur, dampfractie na het smoorventiel, slagvolume, GWP en
veiligheidsklasse). In Python: `vergelijk_koudemiddelen(T_verdamp, T_condens, eta, Q_condensor_kW)` en `ts_cyclus(...)`.

## log p-h-diagram tekenen (los script)

`logph_diagram.py` rekent alle koudemiddelen door, print een ranglijst op COP en tekent het log p-h-diagram
(koepel, isothermen, dampfractielijnen en de cyclus met COP) voor het beste middel.

```bash
python logph_diagram.py                         # beste voor WP-201 (40 -> 75 °C)
python logph_diagram.py --tcond 100 --top 3     # top 3 voor WP-202
python logph_diagram.py "R1233zd(E)" --tcond 100 --oververhitting 5 --opslaan wp202.png
python logph_diagram.py --lijst --zonder-hoge-gwp
```

Vanuit Python: `from logph_diagram import teken_logph; teken_logph("R1233zd(E)", T_evap=40, T_cond=100)`.

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

## Rekenverslag (PDF)
In `docs/` staan twee rekenverslagen die elke stap van het PFD doorrekenen en uitleggen (Cengel-methoden, debieten in kg/h):
- `rekenverslag_A_coolprop.pdf`: CoolProp-waarden met bij elke opzoeking de Cengel-check;
- `rekenverslag_B_cengel.pdf`: alleen Cengel-handberekening; de warmtepompen worden afgelezen uit het log p-h-diagram.

Beide bevatten een bijlage met verdedigingsvragen. Opnieuw maken (LaTeX met `latexmk` nodig):

    pip install CoolProp numpy matplotlib jinja2
    python docs/rekenverslag/genereer.py

## PFD in draw.io
`docs/pfd/PFD.drawio` (openen met draw.io / diagrams.net, voorbeeld: `docs/pfd/PFD.png`) heeft dezelfde indeling als de app:
H₂-lijn boven, warmteterugwinning in het midden, O₂-lijn onder. Alleen standaard draw.io-iconen (P&ID-bibliotheek), alle
leidingen vast aan de standaard connectoren van de iconen (het script controleert dat), en op elke lijn de temperatuur, druk en het massadebiet (kg/s, 8 units samen) in plaats van
stroomvlaggen. Platenwisselaars (Plate and Frame), pijpenwisselaars (Single Pass) en pakketkoelers (Coil Tubes) hebben op elke
aansluiting een rood (warme stroom) of blauw (koude stroom) blokje. In de platenwisselaars loopt elk medium
diagonaal, zoals het kruis in het icoon aangeeft. Het ITM-circuit loopt altijd in serie ITM → E-201 → luchtkoelers AK → ITM. Blad 2 is de stroomtabel. Opnieuw maken na een modelwijziging: `python docs/pfd/maak_drawio.py`.

`docs/pfd/PFD.pptx` is de PowerPoint-versie: het hele PFD, drie uitvergrote delen en de stroomtabel als bewerkbare tabellen.
Opnieuw maken (Node.js en internet nodig voor de draw.io-viewer): `cd docs/pfd && npm install && npx playwright install chromium && node maak_pptx.js`.

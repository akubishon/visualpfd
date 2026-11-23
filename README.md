# visualpfd – ITM Neptune V procesimulator

Visuele simulatie van het PFD van 8 × ITM Neptune V (40 MW) met massa- en energiebalans, doorgerekend met CoolProp.

## Streamlit-app (live CoolProp)
Dubbelklik `start_windows.bat` (Windows) of `start_mac_linux.sh` (Mac/Linux), of in een terminal:

    pip install -r requirements.txt
    streamlit run app.py

De app opent in je browser op http://localhost:8501. Elke schuifbeweging rekent het hele PFD
opnieuw door met echte CoolProp-aanroepen (circa 20 ms per doorrekening). Tabbladen: procesflowschema,
balansen, warmtepomp (log p–h), H₂-compressie (T–s), gevoeligheidsanalyse, rekenblad ↔ CoolProp en
stroomtabel (te downloaden als CSV). Python 3.10 of nieuwer.

Bovenaan staat een statusbord met de 8 ITM-units (vollast, deellast, stand-by of onderhoud) en de
overige apparatuur. In de zijbalk kies je:
- Handmatig: een gevraagde installatielast; de units worden bijgeschakeld of de last wordt gelijk verdeeld.
- Dagprofiel wind: de last volgt een windprofiel over 24 uur; met ▶ Afspelen loopt de klok uur voor uur.
- Units uitvinken voor onderhoud, en het warmtenet of de warmtepomp uitzetten.

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
`browser/index.html` + `model.js` + `tables.json` hebben een lokale webserver nodig, omdat de browser
`fetch` blokkeert bij bestanden die je met dubbelklik opent:

    python -m http.server 8000
    # open http://localhost:8000/index.html

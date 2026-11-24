"""Bouwt ITM-procesimulator.html (één bestand, werkt met dubbelklik) uit index.html + model.js + tables.json.

    python browser/bundel.py
"""
from pathlib import Path

d = Path(__file__).parent
html = (d / "index.html").read_text(encoding="utf-8")
model = (d / "model.js").read_text(encoding="utf-8")
tabellen = (d / "tables.json").read_text(encoding="utf-8").replace("</", "<\\/")

kop, rest = html.split("<style>", 1)
style, rest = rest.split("</style>", 1)
inhoud = rest
for oud, nieuw in [
    ('<script src="model.js"></script>',
     f"<script>\n{model}\n</script>\n<script>window.ITM_TABLES = {tabellen};</script>"),
    ("fetch('tables.json').then(x => x.json())", "Promise.resolve(window.ITM_TABLES)"),
]:
    assert oud in inhoud, oud
    inhoud = inhoud.replace(oud, nieuw)
kop = kop.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">', 1)
uit = ('<!doctype html>\n<html lang="nl">\n<head>\n' + kop.strip() + "\n<style>\nbody { margin: 0 } [hidden] { display: none !important }"
       + style + "</style>\n</head>\n<body>" + inhoud.rstrip() + "\n\n</body>\n</html>\n")
(d / "ITM-procesimulator.html").write_text(uit, encoding="utf-8")
print("geschreven:", d / "ITM-procesimulator.html")

"use strict";

const el = id => document.getElementById(id);
const app = el("app");
const werkruimte = el("werkruimte");
const schermknop = app.querySelector('[data-actie="volledig-scherm"]');
const tabs = ["warmte", "massa", "samen"];
const state = {
    args: null, diagram: null, tab: "samen", selectie: null, rekenpad: [],
    concept: new Map(), temperatuurOpen: false, inBehandeling: null, resultaat: null,
};
const basisVelden = [
    ["temperatuur", "Temperatuur"], ["druk", "Druk"], ["dichtheid", "Dichtheid"],
    ["kg_h", "Massadebiet kg/h"], ["kg_s", "Massadebiet kg/s"],
    ["m3_h", "Volumedebiet m³/h"], ["m3_s", "Volumedebiet m³/s"],
];
const compacteGetallen = new Map();
let vorigeHoogte;

function naarStreamlit(type, inhoud) {
    window.parent.postMessage({isStreamlitMessage: true, type, ...inhoud}, location.origin);
}

function hoogteDoorgeven() {
    const hoogte = Math.ceil(app.getBoundingClientRect().height) + 2;
    if (hoogte !== vorigeHoogte) {
        vorigeHoogte = hoogte;
        naarStreamlit("streamlit:setFrameHeight", {height: hoogte});
    }
}

function ontsnapHtml(tekst) {
    return String(tekst).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);
}

function opmaak(getal, decimalen) {
    if (getal == null) return "–";
    if (!compacteGetallen.has(decimalen)) {
        compacteGetallen.set(decimalen, new Intl.NumberFormat("nl-NL", {maximumFractionDigits: decimalen}));
    }
    return compacteGetallen.get(decimalen).format(getal);
}

function getaltekst(item, compact = false) {
    if (item.getal == null) return item.naam.startsWith("COP") ? "Uit" : "–";
    let waarde = Math.abs(item.getal) < 1e-9 ? 0 : item.getal;
    let eenheid = item.eenheid;
    let decimalen = 2;
    if (compact && eenheid === "kW" && Math.abs(waarde) >= 1000) {
        waarde /= 1000;
        eenheid = "MW";
    } else if (eenheid === "kg/h" && Math.abs(waarde) >= 10) {
        decimalen = 0;
    } else if (eenheid === "°C" || eenheid === "kW") {
        decimalen = 1;
    } else if (eenheid === "barg") {
        decimalen = 2;
    } else if (eenheid === "m³/s" || eenheid === "kg/s" || eenheid === "m³/h" || eenheid === "kg/m³") {
        decimalen = Math.abs(waarde) < 1 ? 6 : 3;
    }
    return opmaak(waarde, decimalen) + (eenheid ? " " + eenheid : "");
}

function knopWaarde(id, {stroom = "", apparaat = "", compact = false, ster = false, vervolgstap = false} = {}) {
    const item = state.args.data.waarden[id];
    if (!item) return "";
    const tekst = getaltekst(item, compact);
    const attrs = (stroom ? ' data-stroom="' + ontsnapHtml(stroom) + '"' : "")
        + (apparaat ? ' data-apparaat="' + ontsnapHtml(apparaat) + '"' : "")
        + (vervolgstap ? ' data-vervolgstap="1"' : "");
    return '<button type="button" class="waarde" data-waarde="' + ontsnapHtml(id) + '"' + attrs
        + ' title="' + ontsnapHtml(item.naam) + '" aria-label="' + ontsnapHtml(item.naam + " · " + tekst + " · Toon berekening") + '">'
        + ontsnapHtml(tekst) + (ster && item.getal != null ? "*" : "") + "</button>";
}

function synopsis() {
    const {data, uur, melding} = state.args;
    const n = data.waarden.n.getal;
    el("punt").innerHTML = (uur ? ontsnapHtml(uur) + " · " : "") + (n ? knopWaarde("n") + " actieve ITM-units" : "Installatie staat stil");
    el("melding").hidden = !melding;
    el("melding").textContent = melding;
    el("diagram-naam").textContent = "Klik op een apparaat, leiding of waarde";

    const kaarten = [];
    if (state.tab !== "massa") {
        for (const id of data.balans.warmte) kaarten.push([data.waarden[id].naam, id, "warmte"]);
    }
    if (state.tab !== "warmte") {
        for (const [naam, id] of data.balans.massa) kaarten.push([naam, id, "massa"]);
    }
    el("balans").innerHTML = kaarten.map(([naam, id, soort]) => {
        const wp = {COP: "wp201", COP2: "wp202"}[id];
        return '<button type="button" class="balans-kaart ' + soort + '" data-waarde="' + ontsnapHtml(id) + '"'
            + (wp ? ' data-apparaat="' + wp + '"' : '') + '><span class="naam">' + ontsnapHtml(naam)
            + '</span><span class="getal">' + ontsnapHtml(getaltekst(data.waarden[id], true)) + '</span></button>';
    }).join("");
    for (const tab of app.querySelectorAll("[data-tab]")) {
        const actief = tab.dataset.tab === state.tab;
        tab.setAttribute("aria-selected", actief);
        tab.tabIndex = actief ? 0 : -1;
    }
    el("pfd-panel").setAttribute("aria-labelledby", "tab-" + state.tab);
}

function stroomLabel(id, {toonDebiet = true, toonDruk = true} = {}) {
    const stroom = state.args.data.stromen[id];
    const v = stroom.waarden;
    const delen = [];
    if (state.tab !== "massa") {
        delen.push(knopWaarde(v.temperatuur, {stroom: id}));
        if (toonDruk) delen.push(knopWaarde(v.druk, {stroom: id, ster: stroom.druk_aanname}));
    }
    const massa = state.tab !== "warmte" && toonDebiet ? knopWaarde(v.kg_h, {stroom: id}) : "";
    return "<b>" + ontsnapHtml(id.replace("-in", " in").replace("-uit", " uit")) + "</b>"
        + (delen.length ? " " + delen.join(" · ") : "") + (massa ? (delen.length ? "<br>" : " ") + massa : "");
}

function labelApparaat(eigenaar) {
    const {apparaten} = state.args.blad;
    const {naam, getallen, unit} = apparaten[eigenaar];
    if (unit) {
        const status = state.args.status[unit - 1];
        return '<b>ITM Neptune V #' + unit + "</b><br>"
            + (status === "In bedrijf" ? knopWaarde(getallen[0], {apparaat: eigenaar})
                : '<span class="afwezig">' + ontsnapHtml(status) + "</span>");
    }
    let titel = naam;
    if (eigenaar === "itm") titel = "8 × " + naam;
    if (eigenaar === "v101" || eigenaar === "v102") {
        return "<b>" + ontsnapHtml(titel.split(" · ")[0]) + "</b><br>" + ontsnapHtml(titel.split(" · ")[1])
            + "<br>" + knopWaarde(getallen[0], {apparaat: eigenaar});
    }
    const cop = getallen.find(id => id === "COP" || id === "COP2");
    const toontWarmte = state.tab !== "massa" && eigenaar !== "itm";
    const cijfers = getallen.filter(id => id !== cop && toontWarmte).slice(0, 1);
    const labels = cijfers.map(id => knopWaarde(id, {apparaat: eigenaar, compact: true}));
    if (cop && eigenaar.startsWith("wp")) labels.unshift("COP " + knopWaarde(cop, {apparaat: eigenaar}));
    const kort = naam.includes(" · ") && !eigenaar.startsWith("wp") ? titel.split(" · ")[0] : titel;
    return "<b>" + ontsnapHtml(kort) + "</b>" + (labels.length ? "<br>" + labels.join(" · ") : "");
}

function updateLabels() {
    const {blad} = state.args;
    const labels = {};
    for (const [cid, leiding] of Object.entries(blad.leidingen)) {
        if (leiding.label) {
            labels[cid] = leiding.stroom ? stroomLabel(leiding.stroom)
                : (state.tab === "massa" ? "E1" : "E1 · " + knopWaarde(leiding.getal, {apparaat: "ac", compact: true}));
        }
    }
    for (const [id, eigenaar] of Object.entries(blad.labels)) labels[id] = labelApparaat(eigenaar);
    for (const [id, apparaat] of Object.entries(blad.apparaten)) {
        if (!id.startsWith("_t")) continue;
        labels[id] = stroomLabel(apparaat.naam.replace(/ (in|uit)$/, "-$1"), {
            toonDebiet: !apparaat.naam.endsWith(" uit"), toonDruk: false,
        });
    }
    state.diagram.labels(labels);
}

function geefApparaatNaam(id) {
    const apparaat = state.args.blad.apparaten[id];
    return apparaat ? apparaat.naam.split(" · ")[0] : id;
}

function verbindingen(selectie) {
    const {blad} = state.args;
    if (!selectie) return [];
    if (selectie.soort === "leiding") {
        return [[selectie.id, blad.leidingen[selectie.id]]];
    }
    if (selectie.soort === "stroom") {
        return Object.entries(blad.leidingen).filter(([, l]) => l.stroom === selectie.id);
    }
    const id = selectie.id;
    const leden = blad.groepen[id] || [];
    const knopen = new Set([id, ...leden]);
    if (blad.apparaten[id]?.unit) knopen.add("itm");
    return Object.entries(blad.leidingen).filter(([, l]) => knopen.has(l.bron) || knopen.has(l.doel));
}

function detailKaart(stroom, richting, verbinding, unit) {
    const {data} = state.args;
    const toestand = data.stromen[stroom];
    const waarden = {...toestand.waarden};
    if (unit) {
        Object.assign(waarden, toestand.per_unit);
        if (data.waarden["unit" + unit + ".last"].getal === 0) {
            for (const [veld] of basisVelden.slice(3)) waarden[veld] = "unit.uit." + veld;
        }
    }
    const richtingTekst = richting ? '<span class="richting">' + ontsnapHtml(richting) + "</span>" : "";
    const details = basisVelden.map(([veld, naam]) => "<div><dt>" + naam + "</dt><dd>"
        + knopWaarde(waarden[veld], {stroom, ster: veld === "druk" && toestand.druk_aanname})
        + "</dd></div>").join("");
    const herkomst = verbinding ? "<p class=\"medium\">" + ontsnapHtml(geefApparaatNaam(verbinding.bron)) + " → "
        + ontsnapHtml(geefApparaatNaam(verbinding.doel)) + "</p>" : "";
    return '<section class="aansluiting"><h3><button class="waarde" type="button" data-open-stroom="' + ontsnapHtml(stroom) + '">'
        + ontsnapHtml(stroom) + "</button>" + richtingTekst + '</h3><p class="medium">' + ontsnapHtml(toestand.medium)
        + (toestand.druk_aanname ? " · * aangenomen druk" : "") + "</p>" + herkomst + '<dl class="waardelijst">' + details + "</dl></section>";
}

function temperatuurFormulier(apparaat) {
    const velden = apparaat?.velden.filter(id => state.args.velden[id]) || [];
    if (!velden.length) return "";
    const resultaat = state.resultaat;
    const inputs = velden.map(id => {
        const veld = state.args.velden[id];
        const tekst = state.concept.get(id) ?? String(veld.waarde).replace(".", ",");
        const fout = resultaat?.ok === false && resultaat.veld === id;
        return '<label for="in-' + id + '"><span>' + ontsnapHtml(veld.naam) + '</span>'
            + '<input id="in-' + id + '" inputmode="decimal" name="' + id + '" value="' + ontsnapHtml(tekst)
            + '" aria-invalid="' + fout + '"' + (fout ? ' aria-describedby="veld-melding"' : "")
            + '> °C</label>';
    }).join("");
    const toonMelding = resultaat && (resultaat.ok || !resultaat.veld || velden.includes(resultaat.veld));
    return '<details class="temperaturen"' + (state.temperatuurOpen ? " open" : "") + '>'
        + '<summary>Temperatuur aanpassen</summary><form id="temperatuur-formulier">' + inputs
        + '<button class="hoofdknoop" type="submit" ' + (state.inBehandeling ? "disabled" : "") + ">Toepassen</button>"
        + (toonMelding ? '<p id="veld-melding" role="status" class="veld-melding' + (resultaat.ok ? " ok" : "") + '">'
            + ontsnapHtml(resultaat.tekst) + "</p>" : "") + "</form></details>";
}

function nummerVoorFormule(n) {
    if (n == null) return "\\text{–}";
    const afgerond = Number(Math.abs(n) < 1e-12 ? 0 : n.toPrecision(8));
    const str = String(afgerond);
    const [basis, exponent] = str.split("e");
    const notatie = basis.replace(".", "{,}") + (exponent ? "\\cdot10^{" + Number(exponent) + "}" : "");
    return n < 0 && afgerond !== 0 ? "\\left(" + notatie + "\\right)" : notatie;
}

function rekenstappen(id) {
    const {waarden} = state.args.data;
    const gezien = new Set();
    const stappen = [];
    function volg(sleutel, diepte) {
        if (gezien.has(sleutel) || !waarden[sleutel]) return;
        gezien.add(sleutel);
        const item = waarden[sleutel];
        if (diepte > 0) {
            for (const ref of Object.values(item.argumenten)) {
                if (waarden[ref]?.formule) volg(ref, diepte - 1);
            }
        }
        stappen.push([sleutel, item]);
    }
    volg(id, 2);
    return stappen;
}

function uitlegHtml(id) {
    if (!id) return "";
    const {waarden} = state.args.data;
    const root = waarden[id];
    if (!root) return "";
    const html = rekenstappen(id).map(([sleutel, item]) => {
        const {soort, symbool, formule, argumenten, uitleg, getal} = item;
        const invulling = Object.values(argumenten).map(ref => knobinding(ref, waarden)).join(" · ");
        const formuleHtml = (tex, label) => '<div class="formule" aria-label="' + label + '" data-tex="' + ontsnapHtml(tex) + '"></div>';
        const vullen = formatter => formule.replace(/@(\w+)/g, (_match, arg) => formatter(waarden[argumenten[arg]]));
        let formules = "";
        if (formule) {
            const voor = soort === "Bisectie" ? "" : symbool + " = ";
            formules += formuleHtml(voor + vullen(v => v.symbool), "Formule");
            if (getal != null && soort === "Berekening") {
                formules += formuleHtml(voor + vullen(v => nummerVoorFormule(v.getal)) + " = " + nummerVoorFormule(getal), "Ingevulde formule");
            }
        }
        return "<li><div class=\"stap-kop\"><b>" + ontsnapHtml(item.naam) + '</b><span class="stap-soort">' + ontsnapHtml(soort) + "</span></div>"
            + '<p class="beschrijving">' + ontsnapHtml(uitleg) + "</p>" + formules
            + (invulling ? '<p class="invulling">' + invulling + "</p>" : "")
            + '<p class="resultaat"><b>' + ontsnapHtml(getaltekst(item)) + "</b></p></li>";
    }).join("");
    return '<section class="rekenuitleg" aria-label="Berekening"><h3>Berekening · ' + ontsnapHtml(root.naam)
        + '</h3><ol class="rekenstappen">' + html + "</ol></section>";
}

function knobinding(id, waarden) {
    return ontsnapHtml(waarden[id].naam) + " " + knopWaarde(id, {vervolgstap: true});
}

function toonInspecteur() {
    const inspecteur = el("inspecteur");
    const geselecteerd = state.selectie;
    const gekozenGetal = state.rekenpad.at(-1);
    const zichtbaar = Boolean(geselecteerd || gekozenGetal);
    inspecteur.hidden = !zichtbaar;
    werkruimte.classList.toggle("heeft-selectie", zichtbaar);
    if (!zichtbaar) return;
    const actieveInvoer = document.activeElement;
    const focus = actieveInvoer instanceof HTMLInputElement && inspecteur.contains(actieveInvoer)
        ? {naam: actieveInvoer.name, begin: actieveInvoer.selectionStart, einde: actieveInvoer.selectionEnd} : null;
    const {blad, data} = state.args;
    const apparaat = geselecteerd?.soort === "apparaat" ? blad.apparaten[geselecteerd.id] : null;
    const lijnen = verbindingen(geselecteerd);
    const gekozenStroom = lijnen[0]?.[1].stroom;
    const titel = apparaat?.naam || (gekozenStroom ? "Stroom " + gekozenStroom : data.waarden[gekozenGetal]?.naam || "Elektrische aansluiting");
    const terug = state.rekenpad.length > 1 ? '<button type="button" class="kleine-knop" data-actie="terug">Terug</button>' : "";
    const sluiten = '<button type="button" class="kleine-knop" data-actie="sluiten">Sluiten</button>';
    const waarden = apparaat?.getallen.map(id =>
        "<div><dt>" + ontsnapHtml(data.waarden[id].naam) + "</dt><dd>" + knopWaarde(id, {apparaat: geselecteerd.id}) + "</dd></div>"
    ).join("");
    const gezien = new Set();
    const aansluitingen = lijnen.map(([, lijn]) => {
        if (!lijn.stroom || gezien.has(lijn.stroom)) return "";
        gezien.add(lijn.stroom);
        let richting = "";
        if (apparaat) {
            const leden = blad.groepen[geselecteerd.id] || [];
            const id = apparaat.unit ? "itm" : geselecteerd.id;
            const inwendig = leden.includes(lijn.doel) && leden.includes(lijn.bron);
            richting = inwendig ? "Intern" : (lijn.doel === id || leden.includes(lijn.doel) ? "In" : "Uit");
        }
        return detailKaart(lijn.stroom, richting, lijn, apparaat?.unit);
    }).join("");
    inspecteur.innerHTML = '<div class="inspecteur-kop"><h2>' + ontsnapHtml(titel) + '</h2><div class="inspecteur-knoppen">'
        + terug + sluiten + '</div></div>' + (apparaat ? '<p class="beschrijving">' + ontsnapHtml(apparaat.uitleg) + "</p>" : "")
        + (waarden ? '<dl class="waardelijst">' + waarden + "</dl>" : "") + temperatuurFormulier(apparaat)
        + uitlegHtml(gekozenGetal) + aansluitingen;
    for (const formule of inspecteur.querySelectorAll("[data-tex]")) {
        katex.render(formule.dataset.tex, formule, {throwOnError: false, strict: "ignore"});
    }
    if (focus) {
        const veld = inspecteur.querySelector('input[name="' + CSS.escape(focus.naam) + '"]');
        veld?.focus({preventScroll: true});
        veld?.setSelectionRange(focus.begin, focus.einde);
    }
}

function openSelectie(selectie) {
    state.selectie = selectie;
    state.rekenpad = [];
    state.temperatuurOpen = false;
    toonInspecteur();
    markeerStromen();
    el("inspecteur").scrollTop = 0;
}

function markeerStromen() {
    const regels = verbindingen(state.selectie);
    const laatste = state.rekenpad.at(-1);
    if (laatste) {
        const context = state.args.blad.apparaten;
        for (const [id, apparaat] of Object.entries(context)) {
            if (apparaat.getallen.includes(laatste)) regels.push(...verbindingen({soort: "apparaat", id}));
        }
        for (const [id, toestand] of Object.entries(state.args.data.stromen)) {
            if (Object.values(toestand.waarden).includes(laatste)) regels.push(...verbindingen({soort: "stroom", id}));
        }
    }
    state.diagram.markeer(regels.map(([id]) => id));
}

function openGetal(id, stroom, apparaat, vervolg) {
    if (!state.args.data.waarden[id]) return;
    if (vervolg) {
        if (state.rekenpad.at(-1) !== id) state.rekenpad.push(id);
    } else {
        if (apparaat && (state.selectie?.soort !== "apparaat" || state.selectie.id !== apparaat)) {
            state.selectie = {soort: "apparaat", id: apparaat};
            state.temperatuurOpen = false;
        } else if (stroom && !verbindingen(state.selectie).some(([, l]) => l.stroom === stroom)) {
            state.selectie = {soort: "stroom", id: stroom};
            state.temperatuurOpen = false;
        }
        state.rekenpad = [id];
    }
    toonInspecteur();
    markeerStromen();
    el("inspecteur").scrollTop = 0;
}

function tabelRijen() {
    const {blad, data} = state.args;
    const gezien = new Set();
    return Object.values(blad.leidingen).filter(({stroom}) => {
        if (!stroom || gezien.has(stroom)) return false;
        gezien.add(stroom);
        return true;
    }).map(({stroom, bron, doel}) => ({
        stroom, route: geefApparaatNaam(bron) + " → " + geefApparaatNaam(doel), toestand: data.stromen[stroom],
    }));
}

function toonTabel() {
    if (!el("stroomtabel").open || !state.args) return;
    const kop = ["Stroom", "Van → naar", "Medium", "°C", "barg", "kg/m³", "kg/h", "kg/s", "m³/h", "m³/s"];
    const rijen = tabelRijen().map(({stroom, route, toestand}) => {
        const cellen = basisVelden.map(([veld]) =>
            "<td>" + knopWaarde(toestand.waarden[veld], {stroom, ster: toestand.druk_aanname && veld === "druk"}) + "</td>"
        ).join("");
        return '<tr><td><button type="button" class="waarde" data-open-stroom="' + ontsnapHtml(stroom) + '">' + ontsnapHtml(stroom)
            + "</button></td><td>" + ontsnapHtml(route) + "</td><td>" + ontsnapHtml(toestand.medium) + "</td>" + cellen + "</tr>";
    }).join("");
    el("stroomtabel-inhoud").innerHTML = '<div class="tabel-werkbalk"><button type="button" class="kleine-knop" data-actie="csv">'
        + 'Stroomtabel als CSV</button></div><div class="tabel-scroll"><table><thead><tr>'
        + kop.map(naam => "<th scope=\"col\">" + naam + "</th>").join("") + "</tr></thead><tbody>" + rijen + "</tbody></table></div>";
}

function downloadTabel() {
    const {waarden} = state.args.data;
    const csv = cel => '"' + String(cel ?? "").replaceAll('"', '""') + '"';
    const rijen = tabelRijen().map(({stroom, route, toestand}) => [
        stroom, route, toestand.medium,
        ...basisVelden.map(([veld]) => String(waarden[toestand.waarden[veld]].getal ?? "").replace(".", ",")),
        toestand.druk_aanname ? "Modelaanname" : "",
    ]);
    rijen.unshift(["Stroom", "Van naar", "Medium", "T °C", "p barg", "ρ kg/m³", "kg/h", "kg/s", "m³/h", "m³/s", "Drukbasis"]);
    const url = URL.createObjectURL(new Blob(["\uFEFF", rijen.map(rij => rij.map(csv).join(";")).join("\r\n")], {type: "text/csv;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = "stroomtabel_" + state.args.opstelling + ".csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function update(args) {
    const nieuwSchema = !state.diagram || state.args?.opstelling !== args.opstelling;
    state.args = args;
    if (nieuwSchema) {
        state.diagram?.sluit();
        state.selectie = null;
        state.rekenpad = [];
        state.concept.clear();
        state.temperatuurOpen = false;
        state.resultaat = null;
        state.inBehandeling = null;
        state.diagram = new PfdDiagram(el("diagram"), args.opstelling, args.blad, openSelectie);
    }
    const melding = args.temperatuurmelding;
    if (melding && melding.id === state.inBehandeling) {
        state.inBehandeling = null;
        state.resultaat = melding;
        if (melding.ok) state.concept.clear();
    }
    state.rekenpad = state.rekenpad.filter(id => args.data.waarden[id]);
    synopsis();
    updateLabels();
    toonInspecteur();
    toonTabel();
    if (nieuwSchema) state.diagram.passend();
    markeerStromen();
    hoogteDoorgeven();
}

function kiesTab(naam) {
    state.tab = naam;
    synopsis();
    updateLabels();
    markeerStromen();
}

app.addEventListener("click", event => {
    if (!state.args) return;
    const doel = event.target.closest("[data-tab], [data-waarde], [data-open-stroom], [data-actie]");
    if (!doel) return;
    const {tab, waarde, stroom, apparaat, vervolgstap, openStroom, actie} = doel.dataset;
    if (waarde && el("diagram").contains(doel)) event.stopPropagation();
    if (tab) kiesTab(tab);
    if (waarde) openGetal(waarde, stroom, apparaat, vervolgstap === "1");
    if (openStroom) openSelectie({soort: "stroom", id: openStroom});
    if ((waarde || openStroom) && el("stroomtabel").contains(doel)) {
        el("inspecteur").scrollIntoView({block: "nearest"});
    }
    if (actie === "zoom-in") state.diagram.zoom("in");
    if (actie === "zoom-uit") state.diagram.zoom("uit");
    if (actie === "passend") state.diagram.passend();
    if (actie === "volledig-scherm") {
        const overgang = document.fullscreenElement ? document.exitFullscreen() : werkruimte.requestFullscreen();
        overgang.catch(() => {
            schermknop.textContent = "Volledig scherm niet beschikbaar";
        });
    }
    if (actie === "reset") {
        state.diagram.reset();
        updateLabels();
        state.diagram.passend();
        markeerStromen();
    }
    if (actie === "terug") {
        state.rekenpad.pop();
        toonInspecteur();
        markeerStromen();
        el("inspecteur").scrollTop = 0;
    }
    if (actie === "sluiten") openSelectie(null);
    if (actie === "csv") downloadTabel();
}, true);

app.addEventListener("input", event => {
    if (event.target.closest("#temperatuur-formulier")) state.concept.set(event.target.name, event.target.value);
});
app.addEventListener("toggle", event => {
    if (event.target.matches?.(".temperaturen")) state.temperatuurOpen = event.target.open;
    if (event.target === el("stroomtabel")) toonTabel();
}, true);
app.addEventListener("submit", event => {
    if (event.target.id !== "temperatuur-formulier") return;
    event.preventDefault();
    const waarden = Object.fromEntries([...new FormData(event.target)].filter(([naam]) => state.concept.has(naam)));
    if (!Object.keys(waarden).length || state.inBehandeling) return;
    const id = crypto.randomUUID();
    state.inBehandeling = id;
    state.resultaat = null;
    toonInspecteur();
    naarStreamlit("streamlit:setComponentValue", {dataType: "json", value: {id, opstelling: state.args.opstelling, waarden}});
});
app.addEventListener("keydown", event => {
    if (!state.args) return;
    const tab = event.target.closest("[data-tab]");
    if (!tab || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const huidig = tabs.indexOf(tab.dataset.tab);
    const volgend = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1
        : (huidig + (event.key === "ArrowLeft" ? -1 : 1) + tabs.length) % tabs.length;
    kiesTab(tabs[volgend]);
    el("tab-" + tabs[volgend]).focus();
});
for (const naam of ["mousedown", "pointerdown"]) {
    el("diagram").addEventListener(naam, event => {
        if (event.target.closest("[data-waarde]")) event.stopPropagation();
    }, true);
}
function stelDiagramHoogteIn() {
    app.style.setProperty("--pfd-hoogte", Math.round(window.parent.innerHeight * 0.82) + "px");
}

if (window.parent !== window) {
    stelDiagramHoogteIn();
    window.parent.addEventListener("resize", stelDiagramHoogteIn);
    window.addEventListener("pagehide", event => {
        if (!event.persisted) window.parent.removeEventListener("resize", stelDiagramHoogteIn);
    });
}
schermknop.hidden = !document.fullscreenEnabled;
document.addEventListener("fullscreenchange", () => {
    schermknop.textContent = document.fullscreenElement === werkruimte ? "Volledig scherm verlaten" : "Volledig scherm";
});
new ResizeObserver(() => {
    if (state.diagram?.passendInVenster) state.diagram.passend();
}).observe(el("diagram"));
new ResizeObserver(hoogteDoorgeven).observe(app);
window.addEventListener("message", event => {
    if (event.source === window.parent && event.origin === location.origin && event.data?.type === "streamlit:render") {
        update(event.data.args);
    }
});
naarStreamlit("streamlit:componentReady", {apiVersion: 1});
hoogteDoorgeven();

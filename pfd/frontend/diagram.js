"use strict";

// De HTML-labels van draw.io gaan door DOMPurify. Deze drie attributen koppelen
// de knoppen in een label aan het reeds berekende resultaat.
window.DOM_PURIFY_CONFIG.ADD_ATTR = window.DOM_PURIFY_CONFIG.ADD_ATTR.concat([
    "data-waarde", "data-stroom", "data-apparaat",
]);

class PfdDiagram {
    constructor(container, opstelling, blad, open) {
        this.container = container;
        this.blad = blad;
        this.opslag = "visualpfd.indeling.v1." + opstelling;
        this.open = open;
        this.verbindingen = [];
        this.bijlageEigenaar = new Map();
        for (const [eigenaar, ids] of Object.entries(blad.bijlagen)) {
            for (const id of ids) this.bijlageEigenaar.set(id, eigenaar);
        }
        this.laad();
    }

    laad() {
        this.graph = new Graph(this.container);
        this.editor = new Editor(true, null, null, this.graph);
        this.editor.setGraphXml(mxUtils.parseXml(this.blad.xml).documentElement);
        const graph = this.graph;
        this.model = graph.getModel();
        graph.setEnabled(true);
        graph.setHtmlLabels(true);
        graph.setConnectable(false);
        graph.setCellsEditable(false);
        graph.setCellsResizable(false);
        graph.setCellsDisconnectable(false);
        graph.setCellsCloneable(false);
        graph.resetEdgesOnMove = false;
        graph.setCellsLocked(false);
        graph.setGridEnabled(false);
        graph.setTooltips(false);
        graph.autoExtend = false;
        graph.isCellMovable = cell => this.magSlepen(cell.id);
        graph.isCellSelectable = cell => !!this.blad.apparaten[cell.id] || !!this.blad.leidingen[cell.id];

        this.basis = {};
        for (const id of Object.keys(this.blad.apparaten)) {
            for (const cel of this.cellenMetBijlagen(id)) {
                const geometrie = this.model.getGeometry(cel);
                this.basis[cel.id] = geometrie.clone();
            }
        }

        const verplaats = graph.moveCells.bind(graph);
        graph.moveCells = (cellen, dx, dy, _klonen, _doel, event) => {
            const ids = cellen.filter(cel => this.magSlepen(cel.id)).map(cel => cel.id);
            const uitgebreid = Array.from(new Set(ids.flatMap(id => this.cellenMetBijlagen(id))));
            if (!uitgebreid.length || (!dx && !dy)) return cellen;
            this.model.beginUpdate();
            try {
                verplaats(uitgebreid, dx, dy, false, null, event);
                this.herrouteer(new Map(uitgebreid.map(cel => [cel.id, {x: dx, y: dy}])));
            } finally {
                this.model.endUpdate();
            }
            this.bewaar();
            return cellen;
        };
        graph.addListener(mxEvent.CLICK, (_graph, event) => {
            const cel = event.getProperty("cell");
            if (!cel || event.getProperty("event")?.target?.closest("[data-waarde]")) return;
            const id = this.bijlageEigenaar.get(cel.id) || cel.id;
            if (this.blad.leidingen[id]) this.open({soort: "leiding", id});
            if (this.blad.apparaten[id]) this.open({soort: "apparaat", id});
        });
        this.herstel();
    }

    magSlepen(id) {
        const apparaat = this.blad.apparaten[id];
        return !!apparaat && !apparaat.unit;
    }

    cellenMetBijlagen(id) {
        const ids = [id, ...(this.blad.bijlagen[id] || [])];
        for (const lid of this.blad.groepen[id] || []) {
            ids.push(...this.cellenMetBijlagen(lid).map(cel => cel.id));
        }
        return ids.map(sleutel => this.model.getCell(sleutel)).filter(Boolean);
    }

    herrouteer(verplaatst) {
        for (const [id, leiding] of Object.entries(this.blad.leidingen)) {
            const bron = verplaatst.get(leiding.bron);
            const doel = verplaatst.get(leiding.doel);
            if (!bron && !doel) continue;

            const cel = this.model.getCell(id);
            const geometrie = this.model.getGeometry(cel).clone();
            if (bron && doel && bron.x === doel.x && bron.y === doel.y) {
                if (geometrie.points) {
                    geometrie.points = geometrie.points.map(punt => new mxPoint(punt.x + bron.x, punt.y + bron.y));
                }
            } else {
                geometrie.points = null;
                this.model.setStyle(cel, mxUtils.setStyle(this.model.getStyle(cel), "edgeStyle", "orthogonalEdgeStyle"));
            }
            this.model.setGeometry(cel, geometrie);
        }
    }

    bewaar() {
        const posities = {};
        for (const [id, begin] of Object.entries(this.basis)) {
            const {x, y} = this.model.getGeometry(this.model.getCell(id));
            if (x !== begin.x || y !== begin.y) posities[id] = {x, y};
        }
        try {
            localStorage.setItem(this.opslag, JSON.stringify(posities));
        } catch {
            // Het schema is ook bruikbaar met geblokkeerde browseropslag.
        }
    }

    herstel() {
        let posities;
        try {
            posities = JSON.parse(localStorage.getItem(this.opslag) || "{}");
        } catch {
            return;
        }
        const verplaatst = new Map();
        this.model.beginUpdate();
        try {
            for (const [id, begin] of Object.entries(this.basis)) {
                const positie = posities?.[id];
                if (!positie || !Number.isFinite(positie.x) || !Number.isFinite(positie.y)) continue;
                const geometrie = begin.clone();
                geometrie.x = positie.x;
                geometrie.y = positie.y;
                this.model.setGeometry(this.model.getCell(id), geometrie);
                verplaatst.set(id, {x: positie.x - begin.x, y: positie.y - begin.y});
            }
            this.herrouteer(verplaatst);
        } finally {
            this.model.endUpdate();
        }
    }

    reset() {
        try {
            localStorage.removeItem(this.opslag);
        } catch {
            // Zonder opslag wordt het geladen diagram opnieuw gebruikt.
        }
        this.sluit();
        this.laad();
    }

    labels(labels) {
        this.model.beginUpdate();
        try {
            for (const [id, html] of Object.entries(labels)) {
                const cel = this.model.getCell(id);
                if (cel && this.model.getValue(cel) !== html) this.model.setValue(cel, html);
            }
        } finally {
            this.model.endUpdate();
        }
    }

    passend() {
        this.passendInVenster = true;
        this.graph.fit(18);
        this.container.scrollLeft = 0;
        this.container.scrollTop = 0;
    }

    zoom(richting) {
        this.passendInVenster = false;
        if (richting === "in") this.graph.zoomIn();
        else this.graph.zoomOut();
    }

    markeer(ids) {
        for (const highlight of this.verbindingen) highlight.destroy();
        this.verbindingen = [];
        for (const id of new Set(ids)) {
            const toestand = this.graph.view.getState(this.model.getCell(id));
            if (!toestand) continue;
            const highlight = new mxCellHighlight(this.graph, "#158363", 3, false);
            highlight.highlight(toestand);
            this.verbindingen.push(highlight);
        }
    }

    sluit() {
        this.markeer([]);
        this.graph.destroy();
        this.container.replaceChildren();
    }
}

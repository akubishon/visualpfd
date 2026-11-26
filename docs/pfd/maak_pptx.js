/*
 * Maakt docs/pfd/PFD.pptx uit docs/pfd/PFD.drawio en docs/pfd/stromen.json:
 *   1. het hele PFD op één dia,
 *   2. drie uitvergrote delen (ITM en H2-lijn, warmteterugwinning, O2-lijn),
 *   3. de stroomtabel als bewerkbare PowerPoint-tabellen.
 *
 * Het PFD wordt gerenderd met de officiële draw.io-viewer (internet nodig) in Chromium via Playwright.
 *
 * Gebruik (vanuit de repo-root):
 *   python docs/pfd/maak_drawio.py          # eerst: PFD.drawio en stromen.json
 *   cd docs/pfd && npm install && node maak_pptx.js
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const pptxgen = require("pptxgenjs");

const HIER = __dirname;
const SCHAAL = 3;                           // renderresolutie (3 × schermpixels)
const VIEWER = "https://viewer.diagrams.net/js/viewer-static.min.js";

// uitsneden in pixels van de 1×-render (x, y, b, h)
const DELEN = [
  { titel: "ITM-units en H₂-lijn", clip: [0, 0, 2187, 640] },
  { titel: "Warmteterugwinning: koelwatercircuit TW, warmtenet en industrie", clip: [512, 316, 1675, 850] },
  { titel: "O₂-lijn en condensaat", clip: [330, 1165, 1380, 349] },
];

const GROEPEN = [
  { titel: "Stroomtabel – water en O₂-lijn", ids: ["S1", "S3", "S13", "S14", "S15", "S16", "S17", "S18"] },
  { titel: "Stroomtabel – H₂-lijn", ids: ["S4", "S5", "S6", "S7", "S8", "S9", "S11", "S12"] },
  { titel: "Stroomtabel – ITM-circuit, koelwatercircuit TW en koelwater",
    ids: ["A", "A2", "B", "TW", "TW-H", "TW1", "TW2", "TW4", "TW3", "KW1", "KW2"] },
  { titel: "Stroomtabel – warmtenet, industrie en warmtepompen",
    ids: ["N1", "N2", "N3", "I1", "I2", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"] },
];

async function renders() {
  const xml = fs.readFileSync(path.join(HIER, "PFD.drawio"), "utf8");
  const cfg = JSON.stringify({ highlight: "#0000ff", nav: false, resize: true, toolbar: "", xml, page: 0 });
  const attr = cfg.replace(/&/g, "&amp;").replace(/'/g, "&#39;");
  const html = `<html><body style="margin:0;background:#fff"><div class="mxgraph" data-mxgraph='${attr}'></div>`
    + `<script src="${VIEWER}"></script></body></html>`;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 2600, height: 1900 }, deviceScaleFactor: SCHAAL });
  await page.setContent(html, { waitUntil: "networkidle" });
  await page.waitForTimeout(3000);
  const el = await page.$(".mxgraph");
  const box = await el.boundingBox();
  const uit = { heel: { png: await el.screenshot(), w: box.width, h: box.height } };
  for (const d of DELEN) {
    const [x, y, w, h] = d.clip;
    uit[d.titel] = { png: await page.screenshot({ clip: { x: box.x + x, y: box.y + y, width: w, height: h } }), w, h };
  }
  await browser.close();
  return uit;
}

function past(w, h, maxW, maxH) {             // beeld passend in een vak, verhouding behouden
  const s = Math.min(maxW / w, maxH / h);
  return { w: w * s, h: h * s };
}

(async () => {
  const beelden = await renders();
  const stromen = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(HIER, "stromen.json"), "utf8"))
    .map((s) => [s.id, s]));

  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";                // 13,33 × 7,5 inch
  pres.title = "PFD – 8 × ITM Neptune V";
  pres.theme = { headFontFace: "Calibri", bodyFontFace: "Calibri" };
  const W = 13.333, H = 7.5, M = 0.4;
  const INKT = "111111", GRIJS = "586878";

  pres.defineSlideMaster({
    title: "PFD",
    background: { color: "FFFFFF" },
    objects: [
      { placeholder: { options: { name: "titel", type: "title", x: M, y: 0.2, w: W - 2 * M, h: 0.6,
        fontSize: 24, bold: true, color: INKT, valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "Vollast EOL · waarden uit het visualpfd-model (CoolProp) · debieten in kg/s voor alle 8 units"
        + " · * = aangenomen druk", options: { x: M, y: H - 0.35, w: W - 2 * M, h: 0.25, fontSize: 10,
        color: GRIJS, margin: 0 } } },
    ],
    slideNumber: { x: W - M - 0.5, y: H - 0.35, w: 0.5, h: 0.25, fontSize: 10, color: GRIJS, align: "right" },
  });

  const beeldDia = (titel, b, sectie) => {
    const s = pres.addSlide({ masterName: "PFD", sectionTitle: sectie });
    s.addText(titel, { placeholder: "titel" });
    const vak = { x: M, y: 0.9, w: W - 2 * M, h: H - 0.9 - 0.45 };
    const f = past(b.w, b.h, vak.w, vak.h);
    s.addImage({ data: "image/png;base64," + b.png.toString("base64"), x: vak.x + (vak.w - f.w) / 2, y: vak.y + (vak.h - f.h) / 2,
      w: f.w, h: f.h, altText: titel, objectName: "PFD " + titel });
    return s;
  };

  pres.addSection({ title: "PFD" });
  beeldDia("PFD – 8 × ITM Neptune V (40 MW)", beelden.heel, "PFD")
    .addNotes("Volledig procesflowschema. Bron: docs/pfd/PFD.drawio (bewerkbaar in draw.io).");
  pres.addSection({ title: "Uitvergroot" });
  for (const d of DELEN) beeldDia(d.titel, beelden[d.titel], "Uitvergroot");

  pres.addSection({ title: "Stroomtabel" });
  const kop = ["Stroom", "Van → naar", "Medium", "T (°C)", "p (barg)", "ṁ (kg/s)", "ṁ (kg/h)"];
  const kolom = [0.85, 4.6, 2.6, 0.95, 1.05, 1.15, 1.33];
  for (const g of GROEPEN) {
    const s = pres.addSlide({ masterName: "PFD", sectionTitle: "Stroomtabel" });
    s.addText(g.titel, { placeholder: "titel" });
    const kopRij = kop.map((t, k) => ({ text: t, options: { bold: true, fill: { color: "E8EDF2" },
      align: k >= 3 ? "right" : "left" } }));
    const rijen = g.ids.filter((id) => stromen[id]).map((id) => {
      const r = stromen[id];
      return [{ text: r.id, options: { bold: true } }, r.naam, r.medium,
        { text: r.T, options: { align: "right" } }, { text: r.p, options: { align: "right" } },
        { text: r.kgs, options: { align: "right" } }, { text: r.kgh, options: { align: "right" } }];
    });
    s.addTable([kopRij, ...rijen], { x: M, y: 1.0, w: W - 2 * M, colW: kolom, fontSize: 14, color: INKT,
      border: { type: "solid", pt: 0.75, color: "B4BEC8" }, rowH: 0.36, margin: 0.06, valign: "middle",
      objectName: g.titel });
  }

  const uit = path.join(HIER, "PFD.pptx");
  // zonder mapregels in de zip: zo opent het bestand ook vanuit OneDrive/SharePoint
  const JSZip = require("jszip");
  const bron = await JSZip.loadAsync(await pres.write({ outputType: "nodebuffer" }));
  const zip = new JSZip();
  for (const n of Object.keys(bron.files)) {
    if (!bron.files[n].dir) zip.file(n, await bron.files[n].async("nodebuffer"), { createFolders: false });
  }
  fs.writeFileSync(uit, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  console.log("geschreven:", path.relative(process.cwd(), uit));
})();

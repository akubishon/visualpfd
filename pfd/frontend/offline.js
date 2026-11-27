"use strict";

// Draw.io's standalone renderer defaults to viewer.diagrams.net for assets.
const basisURL = new URL("vendor/", location.href);
for (const [naam, pad] of Object.entries({
    DRAWIO_BASE_URL: "", STENCIL_PATH: "stencils", SHAPES_PATH: "shapes", STYLE_PATH: "styles",
    GRAPH_IMAGE_PATH: "img", mxImageBasePath: "mxgraph/images", mxBasePath: "mxgraph/",
    PROXY_URL: "proxy", DRAW_MATH_URL: "math",
})) {
    window[naam] = new URL(pad, basisURL).href;
}
window.onDrawioViewerLoad = () => {};

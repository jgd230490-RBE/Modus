// CLOCS card C-X1, option (a) (12 Nov 2026; John asked at 23:47 UTC on 11 Nov, no answer within the hour, so his standing
// instruction "if i dont answe within 1 hr continue with your reccomendation" took the recommendation): on the Locations
// page a site's row click frames the site's LAYOUT when it has one (zoom up to 17), not the zoom-11 centring that left the
// layout a cluster of symbols. A site without a layout keeps the centring; the Routes and Zones row clicks are untouched.
// The source checks below, and a behavioural run of the framing block with a stub map and stub mapboxgl.
// Run: node backend/tests/ui_fix_clocs_c_site_frame.js
const fs = require("fs"), path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n/g, "\n");
let pass = 0, fail = 0;
const ok = (label, cond, detail) => { if (cond) { pass++; console.log("  ✅ " + label); } else { fail++; console.log("  ❌ " + label + (detail ? "\n       " + detail : "")); } };
const fnBody = (head) => { const a = html.indexOf(head); if (a < 0) return ""; const b = html.indexOf("\n  };\n", a); return html.slice(a, b < 0 ? a + 2000 : b); };

const loc = fnBody("  const locateNode = (id) => {");
ok("⭐ C-X1: a Locations row click asks the layout card to frame the site (layoutFrameRef.current = id)",
   /layoutFrameRef\.current = id;/.test(loc), loc.slice(0, 400));
ok("C-X1: the row click still centres a site at zoom 11 or closer (a site without a layout opens as today)",
   loc.includes("m.easeTo({ center: feat.geometry.coordinates, zoom: Math.max(m.getZoom(), 11), duration: 700 });"));
ok("⭐ C-X1: one ref for it, beside the layout card's other refs", html.includes("  const layoutFrameRef = useRef(null);\n"));
const mounts = html.split("<SiteLayoutCard ").slice(1).map(x => x.slice(0, x.indexOf("\n")));
ok("⭐ C-X1: both layout cards (an editor's and a reader's) are given the ref",
   mounts.length === 2 && mounts.every(x => x.includes("frameRef={layoutFrameRef}")), JSON.stringify(mounts));
ok("C-X1: the card takes frameRef", html.includes("function SiteLayoutCard({ locId, mapRef, mapReady, handleRef, pickRef, reinstallRef, frameRef, drawing, onDraw, onZones }){"));

const a = html.indexOf("function SiteLayoutCard(");
const card = html.slice(a, html.indexOf("\nfunction ", a + 10));
const i = card.indexOf("if(frameRef && frameRef.current === locId");
const block = i < 0 ? "" : card.slice(i, card.indexOf("\n        }\n", i) + 10);
ok("⭐ C-X1: the card frames only for its own site, only on that site's own layout, never while drawing",
   block.startsWith("if(frameRef && frameRef.current === locId && lay && lay.location_id === locId && !drawing){"), block.slice(0, 200));
ok("⭐ C-X1: the frame is the shown phase's drawing, up to zoom 17, and once (the ref is cleared)",
   block.includes("frameRef.current = null;") && block.includes("m.fitBounds(b, { padding: 60, maxZoom: 17, duration: 700 })")
   && block.includes("(Array.isArray(fc) ? fc : (fc.features || [])).forEach("));

// behaviour: run the block with a stub map / mapboxgl
function run(st){
  const fits = [];
  class LngLatBounds { constructor(){ this.pts = []; } extend(c){ this.pts.push(c); } isEmpty(){ return !this.pts.length; } }
  const m = { fitBounds: (b, o) => fits.push({ b: b.pts, o }) };
  // eslint-disable-next-line no-new-func
  new Function("frameRef", "locId", "lay", "drawing", "p", "m", "mapboxgl", block)(st.frameRef, st.locId, st.lay, st.drawing, st.p, m, { LngLatBounds });
  return fits;
}
// a phase as the server sends it: its drawing is a FeatureCollection (site_layouts._phase_out), never a bare list. A first
// build walked p.features as a list and threw in Chrome ("forEach is not a function"): this stub has the real shape.
const feats = [{ geometry: { type: "Point", coordinates: [-0.9, 52.7] } },
               { geometry: { type: "Polygon", coordinates: [[[-0.901, 52.701], [-0.899, 52.701], [-0.899, 52.699], [-0.901, 52.701]]] } }];
const ph = { features: { type: "FeatureCollection", features: feats } };
if (block) {
  let r = { current: "loc_9" };
  let f = run({ frameRef: r, locId: "loc_9", lay: { location_id: "loc_9" }, drawing: false, p: ph });
  ok("⭐ C-X1 (behaviour): a site with a layout, opened from its row: framed on every point of the shown phase, the ref cleared",
     f.length === 1 && f[0].b.length === 5 && f[0].o.maxZoom === 17 && r.current === null, JSON.stringify(f));
  r = { current: "loc_9" };
  f = run({ frameRef: r, locId: "loc_9", lay: { location_id: "loc_3" }, drawing: false, p: ph });
  ok("C-X1 (behaviour): the previous site's layout (one render after a switch) is never framed; the ask waits",
     f.length === 0 && r.current === "loc_9");
  r = { current: "loc_9" };
  f = run({ frameRef: r, locId: "loc_9", lay: { location_id: "loc_9" }, drawing: false, p: { features: { type: "FeatureCollection", features: [] } } });
  ok("C-X1 (behaviour): a phase with nothing drawn: no frame (the row click's centring stays)", f.length === 0);
  r = { current: "loc_9" };
  f = run({ frameRef: r, locId: "loc_9", lay: { location_id: "loc_9" }, drawing: false, p: { features: feats } });
  ok("C-X1 (behaviour): a drawing handed over as a plain list is framed too", f.length === 1 && f[0].b.length === 5);
  r = { current: null };
  f = run({ frameRef: r, locId: "loc_9", lay: { location_id: "loc_9" }, drawing: false, p: ph });
  ok("C-X1 (behaviour): a card opened another way (a map click, a re-read after a save) does not move the map", f.length === 0);
  r = { current: "loc_9" };
  f = run({ frameRef: r, locId: "loc_9", lay: { location_id: "loc_9" }, drawing: true, p: ph });
  ok("C-X1 (behaviour): while the drawing tools are open, no frame", f.length === 0);
} else { ok("C-X1 (behaviour): the framing block was found", false); }

// the Routes and Zones uses of the same map are untouched
ok("C-X1: the Routes row click still frames the route (maxZoom 13)",
   html.includes("if(coords && m) { try { m.fitBounds(boundsOf(coords), { padding: 60, maxZoom: 13, duration: 700 }); } catch(e){} }"));
ok("C-X1: the Zones row click still frames the zone (maxZoom 13)",
   html.includes("if(m && pts.length) { try { m.fitBounds(boundsOf(pts), { padding: 80, maxZoom: 13, duration: 600 }); } catch(e){} }"));
ok("C-X1: the ref is set nowhere but the Locations row click", (html.match(/layoutFrameRef\.current = /g) || []).length === 1);
console.log(`\nui_fix_clocs_c_site_frame.js: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);

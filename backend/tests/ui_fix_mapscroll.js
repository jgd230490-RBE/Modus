/* ui_fix_mapscroll.js — 9 Nov 2026, the UI critique's wave 1 branch claude/ui-fix-map-scroll (notes\ui-critique-1109.md,
 * findings 2 and 18, card 2). Source checks on map/index.html and backend/tests/ui_audit.js; no browser (the browser
 * half is ui_audit.js's no-page-scroll check, which now scrolls the page and reads it back).
 *
 *   A. The page never scrolls: html held to the window, body the box every absolute panel sits in, clipping what pokes
 *      out (the parked route drawer made the page 80 px taller; focus or a script lifted the whole map).
 *   B. The route drawer: one height, its tab scrolls inside it, hidden while parked.
 *   C. "Report a concern" in the panel on a desk (it was only in the Link and QR card); the phone keeps its sheet's.
 *   D. The export dialog's Scale is filled as it opens: the regional plan reads "Fitted to the routes" at once.
 *   E. ui_audit.js scrolls a fixed page and reads it back.
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const audit = fs.readFileSync(path.join(__dirname, "ui_audit.js"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra) : "")); console.log("  ✗ " + label); }
}

// the page's own <style> blocks (the CSS), and the script
const css = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join("\n");
const cssNoComments = css.replace(/\/\*[\s\S]*?\*\//g, "");
// rules outside any @media (depth 0), in order
function topRules(src) {
  const out = []; let depth = 0, start = 0, sel = "";
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (c === "{") { if (depth === 0) { sel = src.slice(start, i).trim(); start = i + 1; } depth++; }
    else if (c === "}") { depth--; if (depth === 0) { out.push({ sel, body: src.slice(start, i) }); start = i + 1; } }
    else if (c === ";" && depth === 0) start = i + 1;
  }
  return out;
}
const rules = topRules(cssNoComments);
const plain = rules.filter(r => !r.sel.startsWith("@"));
const media = rules.filter(r => r.sel.startsWith("@media"));
const decl = (body, prop) => { const m = [...body.matchAll(new RegExp("(?:^|[;\\s{])" + prop.replace(/[-]/g, "\\-") + "\\s*:\\s*([^;]+)", "g"))]; return m.map(x => x[1].trim()); };

console.log("A. the page never scrolls");
const htmlRule = plain.filter(r => /^html$/.test(r.sel));
ok("A1 an html rule holds the root to the window: height:100% and overflow:hidden",
   htmlRule.length === 1 && decl(htmlRule[0].body, "height").includes("100%") && decl(htmlRule[0].body, "overflow").includes("hidden"), htmlRule);
const bodyHold = plain.filter(r => r.sel === "html body");
ok("A2 body is positioned (the containing block of every absolute panel) and the window's height",
   bodyHold.length === 1 && decl(bodyHold[0].body, "position").includes("relative") && decl(bodyHold[0].body, "height").includes("100%"), bodyHold);
ok("A3 body CLIPS what pokes out (overflow:clip, after an overflow:hidden fallback)",
   bodyHold.length === 1 && /overflow:\s*hidden;\s*overflow:\s*clip/.test(bodyHold[0].body), bodyHold[0] && bodyHold[0].body);
// nothing later or narrower sets html / body back to a scrolling overflow or an auto height
const mediaInner = media.flatMap(m => { const inner = m.body; return topRules(inner); });
const rootRules = plain.concat(mediaInner).filter(r => r.sel.split(",").some(s => /^\s*(html|body|html body)\s*$/.test(s)));
ok("A4 no rule sets html or body to overflow auto / scroll / visible",
   rootRules.every(r => !decl(r.body, "overflow").concat(decl(r.body, "overflow-y")).some(v => /auto|scroll|visible/.test(v))), rootRules.map(r => r.sel));
ok("A5 no rule gives html or body a min-height or a vh height (taller than the window)",
   rootRules.every(r => !decl(r.body, "min-height").length && !decl(r.body, "height").some(v => /vh/.test(v))), rootRules.map(r => r.sel));
ok("A6 the base body rule still says overflow:hidden (the old fallback is not lost)",
   plain.some(r => r.sel === "body" && decl(r.body, "overflow").includes("hidden")));
// the order matters: html body comes after the base body rule, or the base would win on the same property
const iBase = css.indexOf("body { margin:0; padding:0;"), iHold = css.indexOf("html body{ position:relative;");
ok("A7 the hold comes after the base body rule", iBase >= 0 && iHold > iBase, { iBase, iHold });
ok("A8 no script scrolls the window on the map (window.scrollTo / scrollBy with a non-zero offset)",
   !/window\.scroll(To|By)\(\s*[^0)]/.test(html.replace(/<style[\s\S]*?<\/style>/g, "")));

console.log("B. the route drawer");
const drawer = plain.find(r => r.sel === "#route-drawer");
ok("B1 the drawer has ONE height (46vh), not a content height up to a maximum",
   drawer && decl(drawer.body, "height").includes("46vh") && decl(drawer.body, "max-height").includes("46vh"), drawer && drawer.body);
ok("B2 parked, the drawer is hidden (visibility), after its slide (0s delay .28s)",
   drawer && decl(drawer.body, "visibility").includes("hidden") && /visibility 0s linear \.28s/.test(drawer.body));
const dOpen = plain.find(r => r.sel === "#route-drawer.open");
ok("B3 open, it is visible at once and slides up", dOpen && decl(dOpen.body, "visibility").includes("visible") && decl(dOpen.body, "transform").includes("translateY(0)"), dOpen && dOpen.body);
const dBody = plain.find(r => r.sel === ".drawer-body");
ok("B4 its tab scrolls inside it: overflow auto, flex 1 1 auto, min-height 0",
   dBody && decl(dBody.body, "overflow").includes("auto") && decl(dBody.body, "flex").includes("1 1 auto") && decl(dBody.body, "min-height").includes("0"), dBody && dBody.body);
ok("B5 the drawer is still a column (head, then the scrolling tab)", drawer && decl(drawer.body, "flex-direction").includes("column") && decl(drawer.body, "display").includes("flex"));
ok("B6 the drawer markup is unchanged: two tabs, a close, two bodies",
   /<div id="route-drawer">\s*<div class="drawer-head">[\s\S]*?id="tab-analysis"[\s\S]*?id="tab-detail"[\s\S]*?class="drawer-close"[\s\S]*?<\/div>\s*<div class="drawer-body" id="drawer-analysis"><\/div>\s*<div class="drawer-body" id="drawer-detail" style="display:none;"><\/div>\s*<\/div>/.test(html));
ok("B7 the drawer still opens and closes by the class only", /classList\.add\('open'\);\s*\n\s*\}\s*\n\s*function closeDrawer\(\)\{ document\.getElementById\('route-drawer'\)\.classList\.remove\('open'\); \}/.test(html));

ok("B8 at a desk the conditions panel sits left of the zoom buttons (right 52 px), the month text's 432 px kept",
   /@media \(min-width:1024px\)\{ body #tl-warnings\{ right:52px; \} \}/.test(css) && /body\.month-text-open #tl-warnings\{ right:432px; \}/.test(css)
   && /#tl-warnings\{[^}]*top:84px;[^}]*right:12px/.test(css));

console.log("C. Report a concern in the panel on a desk");
const share = (() => { const i = html.indexOf('<div class="control-group share-group" id="share-group">'); return i >= 0 ? html.slice(i, html.indexOf("</div>\n    </div>", i) + 20) : ""; })();
const shareBlock = (() => { const i = html.indexOf('<div class="control-group share-group" id="share-group">'); if (i < 0) return ""; let d = 0, j = i; const re = /<\/?div\b/g; re.lastIndex = i;
  let m; while ((m = re.exec(html))) { d += m[0] === "<div" ? 1 : -1; if (d === 0) { j = m.index; break; } } return html.slice(i, j); })();
ok("C1 the panel's share group carries a concern slot of its own", /<div class="concern-slot concern-panel-slot"><\/div>/.test(shareBlock), shareBlock.slice(-200));
ok("C2 it sits after the share row's buttons (Month as text, Link and QR code, Export)",
   shareBlock.indexOf("concern-panel-slot") > shareBlock.indexOf('id="rme-open"') && shareBlock.indexOf('id="btn-share"') > 0);
ok("C3 the Link and QR card keeps its own slot", /<p class="mt-note" id="share-note">[^<]*<\/p>\s*<div class="concern-slot"><\/div>\s*<\/div>/.test(html));
ok("C4 the phone sheet keeps its own slot", /onclick="sheetTo\('full'\)">Filters and layers<\/button>\s*<div class="concern-slot"><\/div>/.test(html));
const phoneHide = mediaInner.find(r => r.sel === ".concern-panel-slot");
ok("C5 below 768 px the panel's slot is hidden (the sheet carries it there), inside the one phone block",
   phoneHide && decl(phoneHide.body, "display").includes("none")
   && /@media \(max-width:767px\)\{\n {12}#kpi-hud, #menu-toggle, #timeline-bar, #tl-warnings, #route-drawer, #btn-detail\{ display:none !important; \}\n {12}\.concern-panel-slot\{ display:none; \}/.test(css)
   && (css.match(/@media \(max-width:767px\)/g) || []).length === 1);   // inside the ONE phone block (parse_map C3 counts it)
ok("C6 the slot is filled by the one renderer (every .concern-slot)", /document\.querySelectorAll\('\.concern-slot'\)\.forEach\(slot =>/.test(html));
ok("C7 the panel's button fills the panel's width", /\.concern-panel-slot \.concern-btn\{ width:100%;/.test(css));
ok("C8 the panel's comment no longer says the concern is only in the Link and QR card",
   !/"Report a concern" is in the Link and QR card -->/.test(html));
const slots = (html.match(/class="concern-slot[ "]/g) || []).length;
ok("C9 four slots: the sheet, the share card, the panel and the month text's (built in the script); the panel's once", slots === 4 && (html.match(/concern-panel-slot"/g) || []).length === 1, slots);

console.log("D. the export dialog's Scale");
const openFn = (() => { const i = html.indexOf("function openRouteExport() {"); return i >= 0 ? html.slice(i, html.indexOf("\n    }\n", i)) : ""; })();
ok("D1 openRouteExport fills the Scale before it shows the dialog", openFn.indexOf("syncRouteExport();") > 0 && openFn.indexOf("syncRouteExport();") < openFn.indexOf("p.hidden = false;"), openFn.length);
ok("D2 and still reads the places after (the 1:N figure and the sites)", openFn.indexOf("loadRouteExportPlaces();") > openFn.indexOf("p.hidden = false;"));
// run syncRouteExport with no places read yet (RME.plans empty): the regional plan's Scale is not blank
const syncSrc = (() => { const i = html.indexOf("function syncRouteExport() {"); return i >= 0 ? html.slice(i, html.indexOf("\n    }\n", i) + 6) : ""; })();
function runSync(plan, RME) {
  const els = { "rme-plan": { value: plan }, "rme-scale": { innerHTML: "" }, "rme-at": { hidden: false }, "rme-at-label": { hidden: false },
    "rme-plan-what": { textContent: "" }, "rme-go": { disabled: false }, "rme-go-png": { disabled: false } };
  const document = { getElementById: id => els[id] || null };
  // eslint-disable-next-line no-new-func
  new Function("document", "RME", syncSrc + "\nsyncRouteExport();")(document, RME);
  return els;
}
let e1; try { e1 = runSync("regional", { plans: [], places: [], fitted: null }); } catch (e) { e1 = { err: String(e) }; }
ok("D3 no places read yet, regional: the Scale reads 'Fitted to the routes'", e1["rme-scale"] && /^<option value="">Fitted to the routes<\/option>$/.test(e1["rme-scale"].innerHTML), e1["rme-scale"] || e1);
let e2; try { e2 = runSync("regional", { plans: [{ kind: "regional", scales: [], what: "w" }], places: [], fitted: 48000 }); } catch (e) { e2 = { err: String(e) }; }
ok("D4 after the read: 'Fitted to the routes (1:48,000)'", e2["rme-scale"] && /Fitted to the routes \(1:48,000\)/.test(e2["rme-scale"].innerHTML), e2["rme-scale"] || e2);
let e3; try { e3 = runSync("local", { plans: [{ kind: "local", scales: [2000, 2500, 3000], default: 2500, centred: true, what: "w" }], places: ["Harborough Compound"], fitted: null }); } catch (e) { e3 = { err: String(e) }; }
ok("D5 the local plan lists its scales with the default selected, no 'Fitted'",
   e3["rme-scale"] && /<option value="2500" selected>1:2,500<\/option>/.test(e3["rme-scale"].innerHTML) && !/Fitted/.test(e3["rme-scale"].innerHTML) && e3["rme-at"].hidden === false, e3["rme-scale"] || e3);

console.log("E. the UI audit scrolls a fixed page");
ok("E1 domChecks scrolls a fixed page (scrollTo, scrollingElement.scrollTop, body.scrollTop) and reads it back",
   /if \(arg\.fixed\) \{[\s\S]{0,400}window\.scrollTo\(0, 100000\); se\.scrollTop = 100000; body\.scrollTop = 100000;[\s\S]{0,200}out\.scrolledTo = /.test(audit));
ok("E2 an already-scrolled page counts (pageY), and both feed docVScroll",
   /out\.pageY = Math\.round\(Math\.max\(y0, b0, window\.scrollY\)\)/.test(audit) && /out\.docVScroll = Math\.max\(out\.docVScroll, out\.pageY, out\.scrolledTo\)/.test(audit));
ok("E3 it puts the page back where it was before the screenshot", /se\.scrollTop = y0; se\.scrollLeft = x0; body\.scrollTop = b0; window\.scrollTo\(x0, y0\);/.test(audit));
ok("E4 the probe runs before the offBottom hunt (which reads docVScroll)", audit.indexOf("out.scrolledTo =") > 0 && audit.indexOf("out.scrolledTo =") < audit.indexOf("if (arg.fixed && out.docVScroll)"));
ok("E5 the no-page-scroll failure says how (pageY, scrolledTo)", /id: "no-page-scroll", ok: !dom\.docVScroll, detail: dom\.docVScroll \? \{ by: dom\.docVScroll, pageY: dom\.pageY, scrolledTo: dom\.scrolledTo,/.test(audit));
ok("E6 the header lists the scroll-and-read-back", /scrolled \(scrollTo \/ scrollTop\) and read back/.test(audit));

console.log();
for (const f of fail) console.log("  FAIL:", f);
console.log(`\n${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);

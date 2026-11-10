/* ui_fix_map_card.js — 10 Nov 2026, the UI critique's wave 3 branch claude/ui-fix-map-card (notes\ui-critique-1109.md,
 * finding 18 (the rest after wave 1's map-scroll) and finding 25, card 18). Source checks on map/index.html and the user
 * guide, plus small sandboxes of the map's own functions; no browser (the browser half is ui_audit.js).
 *
 *   A. The resident's route card: a line nobody has filled in is left out for a resident (staff, the map inside the app,
 *      still see the gap); no "(fictional demo)" anywhere on the map (decision 6: the DEMO bar says it once).
 *   B. Every figure has its noun and unit: the Route carbon badges read "6.8 t CO₂e" (were "CO₂ 6.8"); the key says so;
 *      the phone's lead figure reads "125 movements a day" (was "125 a day"), and no "— a day" with no month on screen.
 *   C. The older public-map items wave 2 logged: the council switch's grey (4.23:1), the forecast status green (3.76:1),
 *      the 18 px "i" button (axe target-size) — each now 4.5:1 or 24 px.
 *
 * Its own file (the wave rule, §H): nothing appended to parse_map.js. Every check fails on the code before this branch.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
// a function's source, from "function name(" to the next line that starts a sibling function at the same indent
function fnSrc(name) {
  const i = html.indexOf("    function " + name + "(");
  if (i < 0) return "";
  const j = html.indexOf("\n    function ", i + 10);
  return html.slice(i, j > 0 ? j : i + 6000);
}
// WCAG relative luminance and contrast
function lum(hex) {
  const h = hex.replace("#", ""); const c = [0, 2, 4].map(k => parseInt(h.slice(k, k + 2), 16) / 255)
    .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
const token = (block, name) => { const m = block.match(new RegExp("--" + name + ":\\s*(#[0-9A-Fa-f]{6})")); return m ? m[1] : null; };
const rootBlock = (html.match(/:root\{([\s\S]*?)\n        \}/) || [])[1] || "";
const darkBlock = (html.match(/html\[data-look="dark"\]\{([\s\S]*?)\n        \}/) || [])[1] || "";

console.log("A. the resident's route card");
const card = fnSrc("routeCardHTML");
ok("A1 the route card's unset line ('Hours, responsible organisation, consent reference') is written only inside the app (EMBED)",
   card.includes("((typeof EMBED !== 'undefined' && EMBED) ? '<p class=\"mt-note\" data-unset-route-words=\"1\">Hours, responsible organisation, consent reference: not given yet.</p>' : '')")
   && (card.match(/consent reference/g) || []).length === 1, card.slice(card.indexOf("consent") - 200, card.indexOf("consent") + 200));
ok("A2 no '(fictional demo)' and no 'fictional demo)' anywhere on the map page (decision 6: the DEMO bar covers it)",
   !/\(fictional demo\)/.test(html) && !/fictional demo\)/.test(html));
// renderConcernLinks in a sandbox: a resident (not embedded) with no address and no form sees nothing; staff see the gap
{
  const src = fnSrc("renderConcernLinks");
  const run = (embed, email) => {
    const slots = [{ innerHTML: "x" }, { innerHTML: "x" }];
    const ctx = { EMBED: embed, TENANT: { name: "Scheme", demo_notice: "Fictional scheme", concern_email: email || null },
      TL: { on: false }, VIEW: { ready: false }, document: { querySelectorAll: () => slots },
      concernAddress: t => t.concern_email || null, concernFormOn: () => false, escHtml: s => String(s),
      concernMailto: a => "mailto:" + a, monthLabel: m => String(m), shareUrl: () => "" };
    vm.createContext(ctx); vm.runInContext(src + "\nrenderConcernLinks();", ctx);
    return slots.map(s => s.innerHTML);
  };
  let pub = null, staff = null, mail = null;
  try { pub = run(false); staff = run(true); mail = run(false, "a@b.example"); } catch (e) { pub = String(e); }
  ok("A3 the public map with no contact address writes NO placeholder in the concern slots", Array.isArray(pub) && pub.every(h => h === ""), pub);
  ok("A4 the map inside the app (staff) still says 'Report a concern: no contact address yet.' — without '(fictional demo)'",
     Array.isArray(staff) && staff.every(h => h === '<span class="concern-unset">Report a concern: no contact address yet.</span>'), staff);
  ok("A5 a typed address is still a 'Report a concern by email' link for everyone", Array.isArray(mail) && mail.every(h => /Report a concern by email<\/a>$/.test(h)), mail);
}

console.log("B. every figure has its noun and unit");
ok("B1 the Route carbon badge reads '<figure> t CO₂e' (one decimal under 10) — the unit after the number",
   html.includes("['concat', ['case', ['>=', ['get', 'f_co2'], 10], ['to-string', ['round', ['get', 'f_co2']]], ['to-string', ['get', 'f_co2']]], ' t CO₂e'], ''];"));
ok("B2 no badge starts with a bare 'CO₂ ' (the old 'CO₂ 6.8' with no unit)", !html.includes("['concat', 'CO₂ ',"));
ok("B3 the carbon key's pill reads '24 t CO₂e' and says what it is ('from that route in the month')",
   html.includes(`'<div class="ml-row ml-key"><span class="co-pill">24 t CO₂e</span>from that route in the month</div>'`) && !html.includes('<span class="co-pill">CO₂ 24</span>'));
ok("B4 the carbon key's grey row says grey is also a route with nothing in the month (it was 'Not routed yet · no figure')",
   html.includes("Nothing this month, or not routed yet</div>'") && !html.includes("Not routed yet · no figure"));
const sheet = html.slice(html.indexOf('<div class="m-peek" id="m-peek">'), html.indexOf('<div class="m-body" id="m-body">'));
ok("B5 the phone's first figure has its noun: a word slot 'm-trips-word' ('movements a day'), never a bare 'a day'",
   sheet.includes('<span id="m-trips-word">movements a day</span>') && !sheet.includes("<span>a day</span>"), sheet);
const rs = fnSrc("renderSheet");
ok("B6 the word follows the organisation's count (CW().short: 'movements a day' or 'visits a day')", rs.includes("set('m-trips-word', CW().short);"));
ok("B7 with no month on screen the two figures are hidden (no '— a day', '— vehicles'): both start hidden and follow TL.on",
   (sheet.match(/<div class="m-fig" hidden>/g) || []).length === 2
   && rs.includes("document.querySelectorAll('#m-peek .m-fig').forEach(el => { if (el.hidden !== !TL.on) el.hidden = !TL.on; });"));
ok("B8 the user guide (§8) describes the badge with its unit, and the grey route",
   guide.includes("a green badge on each route gives its tonnes of CO₂e in the month (<strong>6.8 t CO₂e</strong>); a grey route has nothing in that month, or is not routed yet.")
   && !guide.includes("a green <strong>CO₂</strong> badge"));

console.log("C. contrast and target size on the public map");
const ink2 = token(rootBlock, "ink-2"), okText = token(rootBlock, "ok-text"), okDark = token(darkBlock, "ok-text"), surfDark = token(darkBlock, "surface");
ok("C1 the council switch's unselected words are --ink-2 (was --muted, 4.23:1 on the switch's #eef2f7)",
   /\.kpi-switch button\{[^}]*color:var\(--ink-2\)/.test(html) && !/\.kpi-switch button\{[^}]*color:var\(--muted\)/.test(html));
ok("C2 …which is 4.5:1 or better on the switch's grey", ink2 && contrast(ink2, "#EEF2F7") >= 4.5, [ink2, ink2 && contrast(ink2, "#EEF2F7").toFixed(2)]);
ok("C3 in the app's Dark look the switch takes a dark ground (light words on #eef2f7 would be unreadable)",
   html.includes('html[data-look="dark"] .kpi-switch{ background:var(--surface-2); border-color:var(--ctl-line); }'));
ok("C4 the forecast status sentence is the text-grade green token, 4.5:1 or better on white (was #059669, 3.76:1)",
   html.includes("status.style.color = 'var(--ok-text)';") && !html.includes("status.style.color = CONFIG.COLORS.green;")
   && okText && contrast(okText, "#FFFFFF") >= 4.5, [okText, okText && contrast(okText, "#FFFFFF").toFixed(2)]);
ok("C5 …and in the app's Dark look 4.5:1 or better on the dark panel", okDark && surfDark && contrast(okDark, surfDark) >= 4.5, [okDark, surfDark]);
const infoRule = (html.match(/\n        \.info-i\{([^}]*)\}/) || [])[1] || "";
ok("C6 the 'i' button is 24 px (axe target-size), drawing the same 18 px circle inside a 3 px transparent border",
   /width:24px; height:24px;/.test(infoRule) && /border:3px solid transparent;/.test(infoRule) && /background-clip:padding-box;/.test(infoRule)
   && /box-shadow:inset 0 0 0 1\.5px #94A3B8;/.test(infoRule) && /margin:-3px;/.test(infoRule), infoRule);
ok("C7 its hit area is still 44 px (::after inset -10 px on 24 px)", html.includes('.info-i::after{ content:""; position:absolute; inset:-10px; }'));

console.log("D. the bulletin (finding 25, John's yes to the mockup)");
const bdoc = fs.readFileSync(path.join(ROOT, "backend", "bulletin_doc.py"), "utf8").replace(/\r\n?/g, "\n");
const exp = fs.readFileSync(path.join(ROOT, "backend", "export.py"), "utf8").replace(/\r\n?/g, "\n");
const mainPy = fs.readFileSync(path.join(ROOT, "backend", "main.py"), "utf8").replace(/\r\n?/g, "\n");
const app = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const tech = fs.readFileSync(path.join(ROOT, "frontend", "help", "technical", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const noPyComments = src => src.split("\n").filter(l => !/^\s*#/.test(l)).map(l => l.replace(/\s+#\s.*$/, "")).join("\n");
const bcode = noPyComments(bdoc), ecode = noPyComments(exp);
ok("D1 25a: the lede parses with any name: 'How many lorries are planned for <month>, where they go, and their carbon.'",
   bdoc.includes('"lede": f"How many lorries are planned for {month_long}, where they go, and their carbon.",') && !bcode.includes("The lorries {"));
ok("D2 25b: one name — the bulletin's band and PDF say no 'monthly newsletter', the one-page version no 'leaflet'",
   !bdoc.includes('_band_html(S, "monthly newsletter")') && !exp.includes('_bulletin_doc(S, "monthly newsletter"')
   && !exp.includes('_bulletin_doc(S, "leaflet"') && !bdoc.includes('_band_html(S, "leaflet")')
   && !/NEWSLETTER_LINE = "[^"]*newsletter/.test(bdoc) && !/in the monthly newsletter/.test(bdoc + exp));
ok("D3 25b: the leaflet is the bulletin's 'one-page version': the band, the tab title, the links, the PDF band, the file name",
   bdoc.includes('ONE_PAGE = "one-page version"') && bdoc.includes("+ _band_html(S, ONE_PAGE) +")
   && bdoc.includes("f\"<title>{e(S['brand_title'])} · {ONE_PAGE} · {e(S['tenant'])}</title>\"")
   && bdoc.includes('<a class="lnk" href="{leaflet_href}">One-page version</a><a class="lnk" href="{leaflet_pdf_href}">One-page version (PDF)</a>')
   && !bdoc.includes("The one-page leaflet") && !bdoc.includes(">Leaflet PDF<")
   && exp.includes('doc, usable = _bulletin_doc(S, "one-page version", buf)')
   && mainPy.includes("filename=\"bulletin-one-page-{y}-{m:02d}.pdf\"") && !mainPy.includes("filename=\"leaflet-"));
ok("D4 25b: the line under the title and the band name no kind ('monthly bulletin' / 'monthly newsletter' are gone)",
   bdoc.includes('<p class="sub">{tenant} · {as_at}</p>') && bdoc.includes('"band": _band_html(S, ""),')
   && exp.includes('doc, usable = _bulletin_doc(S, "", buf, pages)') && !bdoc.includes("· monthly bulletin ·"));
ok("D5 25b: the one-page version points to 'the full bulletin'; Config and both guides use the one name",
   bdoc.includes('NEWSLETTER_LINE = "Every route, the councils and the carbon are in the full bulletin:"')
   && exp.includes("are in the full bulletin: {S['newsletter_url']}")
   && app.includes("Printed on the bulletin and its one-page version.") && app.includes('"Public bulletin link (optional)"')
   && !/resident leaflet|Public newsletter link/.test(app)
   && !/newsletter|leaflet/i.test(guide.replace(/newsletter_url/g, "")) && !/newsletter|\bleaflet\b/i.test(tech.replace(/newsletter_url/g, "")));
ok("D6 25c: no numbered sections on the page ('02 Routes and roads' was its first) or in the PDF",
   bdoc.includes('<p class="kick">Routes and roads</p>') && bdoc.includes('<p class="kick">Carbon and the small print</p>')
   && bdoc.includes(`'<p class="kick">Councils</p>' if (M or C) else ""`) && !/class="kick">0\d/.test(bdoc)
   && exp.includes("        return P(E(words.upper()), K.st_kick)") && !exp.includes('P(f"{n}  {E(words.upper())}"'));
ok("D7 25d: one small script opens every scrolling map centred; the page and the one-page version both load it",
   bdoc.includes(`MAP_CENTRE_JS = ("<script>document.querySelectorAll('.mapwrap').forEach(function(w){"`)
   && bdoc.includes("var d=w.scrollWidth-w.clientWidth;if(d>0)w.scrollLeft=Math.round(d/2);});</script>\")")
   && bdoc.includes("</main>{map_centre_js}</body></html>") && bdoc.includes("wayscope.co.uk</footer></main>{MAP_CENTRE_JS}</body></html>')"));
ok("D8 25d: both maps sit in a frame with the pinned demo tag and the phone's one line",
   (bdoc.match(/\+ _mapbox\(f'<div class="mapwrap" data-bulletin="(map|council-map)"/g) || []).length === 2
   && bdoc.includes('MAP_HINT = "Drag the map sideways to see all of it."')
   && bdoc.includes(`return ('<div class="mapframe">' + wrap + (f'<span class="maptag">{_e(tag)}</span>' if tag else "")`));
ok("D9 25d: under 760 px the SVG's own tag is hidden and the pinned one shown (the demo tag stays in view); elsewhere hint and pin are hidden",
   (bdoc.match(/@media \(max-width:759px\)\{\{?\.maptag\{\{?display:block;position:absolute;left:7px;top:7px;/g) || []).length === 2
   && (bdoc.match(/\.mapwrap svg \.map-tag\{\{?display:none\}\}?/g) || []).length === 2
   && (bdoc.match(/\.maptag,\.maphint\{\{?display:none\}\}?/g) || []).length === 2);
ok("D10 18c: the lanes' key draws its samples at twice the map's size (the same widths, scaled), the closure sample too",
   html.includes("const FLOW_KEY_SCALE = 2;") && html.includes(`'<g transform="scale(' + FLOW_KEY_SCALE + ')">' + inner + '</g></svg>'`)
   && fnSrc("flowSample").includes("return flowKeySvg(") && fnSrc("divEdgeSample").includes("return flowKeySvg(")
   && !html.includes('<svg class="fl-sw" width="64" height="12" viewBox="0 0 64 12"'));

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);

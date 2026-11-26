/*
 * own_look_icons_rail.js — Wayscope's own icon set, step 1 (claude/own-look-icons-rail, 26 Nov 2026).
 * John's "Yes, as recommended" to Q1 to Q8 of the icon mockup (24 Nov 2026, notes own-look-icons-mockup-1124): the rail,
 * the phone's tab bar and its More list take the 19 page drawings (17 pages, the User guide's book, More's three dots) in
 * place of the 11 Oct line icons and the two inline drawings; the rail's "?" becomes the book; the NAV glyph values go.
 * One 24-unit grid, a 2-unit line with round ends and joins, currentColor, no fill but the dot; sizes unchanged.
 *
 * Needs typescript react react-dom jsdom via NODE_PATH, like dom_frontend.js; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("own_look_icons_rail.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra !== undefined ? "  " + JSON.stringify(extra) : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const css = html.slice(html.indexOf("<style>"), html.indexOf("</style>"));
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");

// ---------------------------------------------------------------- the mockup's drawings (icons.js WS_SET, 24 Nov 2026)
// [d, rings, dots]: copied from the mockup's own file, which John said yes to; the app must draw exactly these.
const MOCK = {
  dashboard:  ["M3 20h18M7 16v-3M12 16V6M17 16v-7"],
  submit:     ["M4 20v-4L14.5 5.5l4 4L8 20zM12 8l4 4M13 20h7"],
  forecasts:  ["M4 6h16M4 12h9M4 18h5M12.5 17l3 3 5.5-5.5"],
  carbon:     ["M6 18a10 10 0 0 1 12-12a10 10 0 0 1-12 12zM4 20l8.5-8.5"],
  abnormal:   ["M5 5h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM7 16h10", [[8.5, 19, 2], [15.5, 19, 2]]],
  stockpiles: ["M2 20h20M3 20l6.59-6.59a2 2 0 0 1 2.82 0l3.34 3.34M15.75 16.75l.34-.34a2 2 0 0 1 2.82 0L22 19.5"],
  pours:      ["M2.5 9l3.5-3.5h6L15.5 9 12 12.5H6zM17 16V9h1.5l2.5 2.5V16M3 16h18", [[7.5, 19, 2], [17.5, 19, 2]]],
  simulation: ["M10.5 7.5v9l4.5-4.5z", [[12, 12, 9]]],
  clp:        ["M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM9 13h6M9 17h3.5"],
  lookahead:  ["M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM3 10h18M8 3v4M16 3v4M12.5 15.5H17", null, [[8, 15.5, 1.75]]],
  concerns:   ["M5 4h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-4 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM12 7v3.5M12 13h.01"],
  locations:  ["M12 20.4L7.05 15.45a7 7 0 1 1 9.9 0z", null, [[12, 10.5, 2.25]]],
  routes:     ["M4.5 18.5h5.67a2 2 0 0 0 1.42-.59l5.82-5.82a2 2 0 0 0 .59-1.42V9.5", [[18, 6.5, 3]], [[4.5, 18.5, 2]]],
  zones:      ["M4 9.5L9.5 4H18a2 2 0 0 1 2 2v8.5L14.5 20H6a2 2 0 0 1-2-2zM8.5 12.5l4-4M11.5 15.5l4-4"],
  config:     ["M3 8h4M13 8h8M3 16h9M18 16h3", [[10, 8, 3], [15, 16, 3]]],
  users:      ["M3 20v-1a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v1M15.5 4.7a3.5 3.5 0 0 1 0 6.6M17.5 14.3a5 5 0 0 1 3.5 4.7v1", [[9, 8, 3.5]]],
  map:        ["M3 6h5l2-2h4l2 2h5v13h-5l-2-2h-4l-2 2H3zM9 5v13M15 5v13"],
  guide:      ["M12 7v13M12 7a3 3 0 0 0-3-3H3v13h6a3 3 0 0 1 3 3M12 7a3 3 0 0 1 3-3h6v13h-6a3 3 0 0 0-3 3"],
  more:       ["", null, [[5, 12, 1.75], [12, 12, 1.75], [19, 12, 1.75]]],
};
// today's paths before this branch (the 11 Oct NAV_ICON and the two inline drawings): none may be left
const OLD = [
  "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z", "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM3 21v-1a6 6 0 0 1 12 0v1M16 3.5a4 4 0 0 1 0 7.5M21 21v-1a6 6 0 0 0-4-5.7",
  "M5 19h4L19 9l-4-4L5 15zM13 7l4 4", "M5 6h14M5 12h14M5 18h9", "M5 19c0-8.3 5.7-14 14-14 0 8.3-5.7 14-14 14zM5 19l7-7", "M4 7h16v13H4zM4 11h16M9 4v5M15 4v5",
  "M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11zM12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z", "M6 18a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8 16h5a3 3 0 0 0 3-3v-3",
  "M12 3l8 4.5v9L12 21l-8-4.5v-9z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12h2M3 12h2M12 3v2M12 19v2M17 7l1.4-1.4M5.6 18.4L7 17M17 17l1.4 1.4M5.6 5.6L7 7",
  "M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2zM9 4v14M15 6v14", "M3 19h18L14 6l-3 5-2-3z", "M4 15h11l3-5h2v5h-1M4 15V9l6-3 5 3v6M7 18a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17 18a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  "M4 14h16M6 14v3M18 14v3M3 17h2M8 17h8M19 17h2M5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM19 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM7 14V8h10v6M2 11h3M19 11h3",
  "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM10 8.5l6 3.5-6 3.5z", "M7 3h7l5 5v13H7zM14 3v5h5M10 12h6M10 15.5h6M10 19h4", "M4 5h16v11H10l-5 4v-4H4zM12 8v4M12 14.5h.01",
  "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01",
];
const PAGES = ["dashboard", "submit", "forecasts", "carbon", "abnormal", "stockpiles", "pours", "simulation", "clp", "lookahead", "concerns",
               "locations", "routes", "zones", "config", "users", "map"];

// ---------------------------------------------------------------- 1. the source
const navSrc = src.slice(src.indexOf("const NAV = ["), src.indexOf("const DATA_PAGES"));
ok("1 source: no NAV entry carries a glyph (the 17 glyph: values are gone) and nothing reads it", !/glyph:/.test(navSrc) && !src.includes("it.glyph"));
ok("1 source: the 17 NAV entries are the 17 pages, in the rail's order", (navSrc.match(/\{ id: "([a-z]+)"/g) || []).map(s => s.slice(7, -1)).join() === PAGES.join(),
   (navSrc.match(/\{ id: "([a-z]+)"/g) || []).join());
ok("1 source: none of the old paths is left anywhere in the page (the 17 rail lines and the old guide's '?')", OLD.every(p => !html.includes(p)), OLD.filter(p => html.includes(p)));
ok("1 source: More's three filled dots and the guide's ring are no longer inline drawings: each is <NavIcon id=…/>",
   !html.includes('<circle cx="5" cy="12" r="1.8" />') && src.includes('<NavIcon id="more" />\n        <span>More</span>') && src.includes('<NavIcon id="guide" />\n          <span>User guide</span><span className="pm-note">new tab</span>'));
ok("1 source: the rail's '?' is the book (<NavIcon id=\"guide\" />), no '?' character left in the rail's guide link",
   !src.includes('opacity-80">?</span>') && /\{\(!tablet \|\| railShown\) && <a href=\{"\/help\/\?role="[\s\S]{0,700}<NavIcon id="guide" \/>\n\s*\{railShown && <span className="truncate">User guide<\/span>\}/.test(src));
ok("1 source: NavIcon draws one 24-unit box, a 2-unit line, round ends and joins, currentColor, no fill, hidden from readers",
   /function NavIcon\(\{ id \}\)\{[\s\S]{0,200}<svg className="nav-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"/.test(src)
   && !/strokeWidth="1\.7"/.test(src.slice(src.indexOf("function NavIcon"), src.indexOf("function PhoneMore"))));
ok("1 source: the only fill in NavIcon is the dot's (currentColor, no line)",
   (() => { const f = src.slice(src.indexOf("function NavIcon"), src.indexOf("// ================================================================= the phone shell"));
     return (f.match(/fill="/g) || []).length === 2 && f.includes('fill="none"') && f.includes('fill="currentColor" stroke="none"'); })());

// ---------------------------------------------------------------- 2. sizes: unchanged
ok("2 sizes: 18 px in the rail (.nav-ic)", /\.nav-ic\{width:18px;height:18px;flex:none;\}/.test(css));
ok("2 sizes: 22 px on the phone's tabs", /\.phone-tab \.nav-ic\{width:22px;height:22px;\}/.test(css));
ok("2 sizes: 20 px in the phone's More list", /\.phone-more-item \.nav-ic\{width:20px;height:20px;/.test(css));
ok("2 sizes: the folded rail keeps its count dot on the icon (.rail-dot in .rail-ico, hidden from readers, named on the button)",
   src.includes('<span className="rail-ico"><NavIcon id={it.id} />{badge != null && !railShown && <span className="rail-dot" aria-hidden="true" data-rail-dot={it.id}>{badge}</span>}</span>')
   && /\.rail-dot\{position:absolute;/.test(css));

// ---------------------------------------------------------------- 3. names kept
ok("3 names: a folded rail button is named by its page (and its count), the open one by its words",
   src.includes('aria-label={railShown ? undefined : it.label + (badgeWords ? ", " + badgeWords : "")}') && src.includes('{railShown && <span className="truncate flex-1">{it.label}</span>}')
   && src.includes('title={railShown || tablet ? undefined : it.label}'));
ok("3 names: the folded rail's User guide link is named \"User guide\" (it was '?'), the open one by its words",
   src.includes('title={railShown ? "Opens in a new tab" : "User guide"} aria-label={railShown ? undefined : "User guide"}'));

// ---------------------------------------------------------------- 4. the drawings, mounted
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`, { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.eval(js + "\nwindow.__I = { NAV, NAV_ICON, NavIcon, PhoneTabs, PhoneMore, PHONE_PAGES };");
const I = w.__I;
const mount = (C, props) => { const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  act(() => { r.render(w.React.createElement(C, props)); }); return { el, done: () => { act(() => { r.unmount(); }); el.remove(); } }; };

ok("4 set: NAV_ICON holds exactly the 19 drawings (17 pages, guide, more)", Object.keys(I.NAV_ICON).sort().join() === Object.keys(MOCK).sort().join(), Object.keys(I.NAV_ICON));
const same = (a, b) => JSON.stringify(a || []) === JSON.stringify(b || []);
const diff = Object.keys(MOCK).filter(k => { const m = MOCK[k], a = I.NAV_ICON[k] || {}; return (a.d || "") !== m[0] || !same(a.rings, m[1]) || !same(a.dots, m[2]); });
ok("⭐ 4 set: every drawing is the mockup's, number for number (icons.js WS_SET)", diff.length === 0, diff);

// the grid rules, walked from the path itself
const walk = (d) => {
  const t = (d.match(/[MmLlHhVvAaZz]|-?(?:\d+\.?\d*|\.\d+)/g) || []); let i = 0, x = 0, y = 0, sx = 0, sy = 0, cmd = "";
  const pts = [], segs = [], bad = [];
  const num = () => parseFloat(t[i++]);
  while (i < t.length) {
    if (/[A-Za-z]/.test(t[i])) cmd = t[i++];
    const rel = cmd === cmd.toLowerCase(), C = cmd.toUpperCase();
    if (C === "Z") { segs.push([x, y, sx, sy]); x = sx; y = sy; continue; }
    if (C === "M") { const a = num(), b = num(); x = rel ? x + a : a; y = rel ? y + b : b; sx = x; sy = y; pts.push([x, y]); cmd = rel ? "l" : "L"; continue; }
    if (C === "L") { const a = num(), b = num(), nx = rel ? x + a : a, ny = rel ? y + b : b; segs.push([x, y, nx, ny]); x = nx; y = ny; pts.push([x, y]); continue; }
    if (C === "H") { const a = num(), nx = rel ? x + a : a; segs.push([x, y, nx, y]); x = nx; pts.push([x, y]); continue; }
    if (C === "V") { const b = num(), ny = rel ? y + b : b; segs.push([x, y, x, ny]); y = ny; pts.push([x, y]); continue; }
    if (C === "A") { const rx = num(), ry = num(); num(); num(); num(); const a = num(), b = num(); if (rx !== ry) bad.push("an arc not of a circle");
      x = rel ? x + a : a; y = rel ? y + b : b; pts.push([x, y]); continue; }
    bad.push("command " + cmd); i++;
  }
  for (const [x0, y0, x1, y1] of segs) { const dx = x1 - x0, dy = y1 - y0; if (Math.hypot(dx, dy) < 0.05) continue;
    const ang = Math.atan2(dy, dx) * 180 / Math.PI, r = ((ang % 45) + 45) % 45; if (Math.min(r, 45 - r) > 0.6) bad.push("a line at " + ang.toFixed(1) + "°"); }
  return { pts, bad };
};
const rule = Object.keys(MOCK).map(k => { const ic = I.NAV_ICON[k] || {}; const { pts, bad } = walk(ic.d || "");
  const circ = [...(ic.rings || []), ...(ic.dots || [])];
  circ.forEach(c => { if (c[0] - c[2] < 2 || c[0] + c[2] > 22 || c[1] - c[2] < 2 || c[1] + c[2] > 22) bad.push("a circle outside 2..22"); });
  pts.forEach(p => { if (p[0] < 2 || p[0] > 22 || p[1] < 2 || p[1] > 22) bad.push("a point outside 2..22 " + p); });
  return bad.length ? k + ": " + bad.join(", ") : null; }).filter(Boolean);
ok("⭐ 4 grid: every drawing keeps inside 20 of the 24 units, every line flat, upright or at 45°, every curve an arc of a circle (no C / Q / S)", rule.length === 0, rule);
ok("4 grid: only the dot is filled: dots on Look-ahead, Locations, Routes and More only (a place, a route, a count of pages)",
   Object.keys(MOCK).filter(k => (I.NAV_ICON[k].dots || []).length).sort().join() === ["locations", "lookahead", "more", "routes"].join());

// each page's icon rendered
const svgOf = (id) => { const m = mount(I.NavIcon, { id }); const s = m.el.querySelector("svg"); const o = s && { vb: s.getAttribute("viewBox"), sw: s.getAttribute("stroke-width"),
  cap: s.getAttribute("stroke-linecap"), join: s.getAttribute("stroke-linejoin"), fill: s.getAttribute("fill"), stroke: s.getAttribute("stroke"), hid: s.getAttribute("aria-hidden"),
  cls: s.getAttribute("class"), icon: s.getAttribute("data-icon"), paths: [...s.querySelectorAll("path")].map(p => p.getAttribute("d")), circ: s.querySelectorAll("circle").length,
  filled: [...s.querySelectorAll("circle")].filter(c => c.getAttribute("fill") === "currentColor").length, title: s.querySelector("title") }; m.done(); return o; };
const rendered = Object.keys(MOCK).map(k => [k, svgOf(k)]);
const badR = rendered.filter(([k, o]) => !o || o.vb !== "0 0 24 24" || o.sw !== "2" || o.cap !== "round" || o.join !== "round" || o.fill !== "none" || o.stroke !== "currentColor"
  || o.hid !== "true" || o.cls !== "nav-ic" || o.icon !== k || o.title || o.paths.join() !== (MOCK[k][0] ? MOCK[k][0] : "")
  || o.circ !== (MOCK[k][1] || []).length + (MOCK[k][2] || []).length || o.filled !== (MOCK[k][2] || []).length).map(([k]) => k);
ok("⭐ 4 drawn: each of the 19 renders as one nav-ic svg, viewBox 24, stroke 2, round, currentColor, aria-hidden, its own lines, rings and dots", badR.length === 0, badR);

// ---------------------------------------------------------------- 5. the phone: tab bar and More list, mounted
const groups = I.NAV;
const tabs = mount(I.PhoneTabs, { groups, page: "lookahead", onPick(){}, moreOpen: false, onMore(){} });
const tb = [...tabs.el.querySelectorAll("button.phone-tab")];
ok("5 phone tabs: Dashboard, Look-ahead, Route map and More, each a button with its drawing and its word",
   tb.map(b => b.textContent).join("|") === "Dashboard|Look-ahead|Route map|More"
   && tb.map(b => (b.querySelector("svg.nav-ic") || {}).getAttribute && b.querySelector("svg.nav-ic").getAttribute("data-icon")).join() === "dashboard,lookahead,map,more"
   && tb.every(b => b.querySelector("svg").getAttribute("aria-hidden") === "true"), tb.map(b => b.innerHTML.slice(0, 80)));
ok("5 phone tabs: More keeps its expanded state and its control", tb[3].getAttribute("aria-expanded") === "false" && tb[3].getAttribute("aria-controls") === "phone-more");
tabs.done();
const more = mount(I.PhoneMore, { groups, page: "dashboard", onPick(){}, onClose(){}, role: { role: "planner", label: "Planner" }, who: null });
const items = [...more.el.querySelectorAll(".phone-more-item")];
const want = groups.flatMap(g => g.items).filter(it => !I.PHONE_PAGES.includes(it.id)).map(it => it.id);
ok("5 More list: every page under More has its own drawing (Simulation first, then the desk pages), then the User guide's book",
   items.map(b => (b.querySelector("svg.nav-ic") || { getAttribute: () => "none" }).getAttribute("data-icon")).join() === ["simulation", ...want.filter(k => k !== "simulation"), "guide"].join(),
   items.map(b => b.querySelector("svg") && b.querySelector("svg").getAttribute("data-icon")));
ok("5 More list: each item keeps its word (the guide 'User guide' + 'new tab'), each drawing hidden from readers",
   items.every(b => b.textContent.trim().length > 2 && b.querySelector("svg").getAttribute("aria-hidden") === "true")
   && items[items.length - 1].textContent === "User guidenew tab" && items[items.length - 1].tagName === "A");
more.done();

console.log(`own_look_icons_rail.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }

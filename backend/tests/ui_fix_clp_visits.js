/*
 * ui_fix_clp_visits.js — 11 Nov 2026, card D-F5 (John's yes), branch claude/clp-visits-words.
 *
 *   CLP monitoring's "Routes against their planning cap" counts lorry VISITS a day (one load = one visit; the cap is typed in
 *   visits) and its subtitle says so, but the bar words said "movements a day". The bars now say "visits a day". The data key
 *   (movements_per_day) keeps its name; the councils chart, which really counts movements, is unchanged.
 *
 * Its own file (BUILD.md rule 3: nothing appended to parse_frontend.js). Source checks only; the pack's words are in test_clp.py.
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");

const call = (key) => { const m = html.match(new RegExp(`clpBulletCfg\\(capped\\(C\\.${key}\\.rows\\), "([a-z_]+)", "([a-z]+)", "([a-z ]+)"\\)`)); return m ? m.slice(1) : null; };
const rc = call("route_caps"), sc = call("site_caps");

ok("🔴 D-F5: the route-cap bars say 'visits a day' (they count lorry visits), never 'movements a day'",
   rc && rc[2] === "visits a day", JSON.stringify(rc));
ok("D-F5: the route-cap bars still read the same figure (key movements_per_day, named by route)",
   rc && rc[0] === "movements_per_day" && rc[1] === "route", JSON.stringify(rc));
ok("D-F5: the site-cap bars are unchanged ('visits a day' on visits_per_day)",
   sc && sc[0] === "visits_per_day" && sc[2] === "visits a day", JSON.stringify(sc));
ok("D-F5: no CLP bullet chart is labelled 'movements a day' any more",
   !/clpBulletCfg\(capped\([^)]*\)[^)]*"movements a day"\)/.test(html) && /clpBulletCfg\(capped\([^)]*\)[^)]*"visits a day"\)/.test(html));
ok("D-F5: the councils chart keeps 'movements a day' (it counts movements)",
   html.includes("${clpN1(r.movements_per_day)} movements a day"));
const tip = (html.match(/"clp\.route_caps": \{[^}]*\}/) || [""])[0];
ok("D-F5: the route-cap 'i' box already says lorry visits a day", tip.includes("Lorry visits a day on each route"), tip.slice(0, 160));

console.log(`ui_fix_clp_visits.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }

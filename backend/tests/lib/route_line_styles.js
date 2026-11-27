/*
 * 27 Nov 2026 (claude/route-line-spec): the route-line table's copy, read out of the pages, for the harnesses that run a
 * SLICE of a page's script (new Function / vm). Every route line's value on the two pages is read from that copy
 * (`var ROUTE_LINE_STYLES = {...};`, the first statement of each page's main script, written by
 * backend/tools/route_line_styles_build.py from backend/route_line_styles.py), so a slice needs it in scope.
 *
 *   require("./lib/route_line_styles").install();   // ROUTE_LINE_STYLES, RLSP (the public map), RLS_R, RLS_C, RLS_S
 *
 * The values are the page's own copy, never a second list here: a page whose copy is stale fails
 * test_route_line_styles.py, not these harnesses.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..", "..");
const PAGES = { map: "map/index.html", frontend: "frontend/index.html" };

function load(page) {
  const text = fs.readFileSync(path.join(ROOT, PAGES[page]), "utf8");
  const m = text.match(/var ROUTE_LINE_STYLES = (\{.*\});\r?\n/);
  if (!m) throw new Error(`${PAGES[page]}: no route-line styles copy`);
  return JSON.parse(m[1]);
}

function install(target) {
  const g = target || globalThis;
  const all = Object.assign({}, load("map"), load("frontend"));
  g.ROUTE_LINE_STYLES = all;
  g.RLSP = all.public_map;
  g.RLS_R = all.routes_map;
  g.RLS_C = all.commit_map;
  g.RLS_S = all.simulation_map;
  return all;
}

// The page's text with every read of the table put back as the value it reads, written the way the page wrote its values
// before 27 Nov 2026 (quote: ' on the map page; numbers and arrays as JS, ", " between items), and every key sample's
// `var(--rl-…)` as its colour. For the source pins written against literal values: they keep pinning today's values,
// while the harness's own check (reads()) says the page takes them from the copy. A read that names no field is left
// as it is, so a pin on it fails rather than passing on a made-up value.
const VARS = { RLSP: "public_map", RLS_R: "routes_map", RLS_C: "commit_map", RLS_S: "simulation_map" };
function lit(v, q) {
  if (Array.isArray(v)) return "[" + v.map(x => lit(x, q)).join(", ") + "]";
  if (typeof v === "string") return q + v + q;
  if (v && typeof v === "object") return "{ " + Object.entries(v).map(([k, x]) => k + ": " + lit(x, q)).join(", ") + " }";
  return String(v);
}
function cssName(s, r, f) { return "--rl-" + [s, r, f].map(x => x.replace(/_/g, "-")).join("-"); }
function resolve(text, quote) {
  const q = quote || "'";
  const all = Object.assign({}, load("map"), load("frontend"));
  const names = {};
  for (const [s, roles] of Object.entries(all)) for (const [r, sp] of Object.entries(roles)) for (const [f, v] of Object.entries(sp)) names[cssName(s, r, f)] = v;
  const at = (text.match(/var ROUTE_LINE_STYLES = \{.*\};\r?\n/) || [""])[0];
  const body = text.replace(at, "\u0000RLS\u0000");
  const out = body
    .replace(/\b(RLSP|RLS_R|RLS_C|RLS_S)\.([a-z_]+)\.([a-z_]+)\b/g, (m, v, r, f) => {
      const sp = (all[VARS[v]] || {})[r];
      return sp && f in sp ? lit(sp[f], q) : m;
    })
    .replace(/var\((--rl-[a-z0-9-]+)\)/g, (m, n) => (n in names ? String(names[n]) : m));
  return out.replace("\u0000RLS\u0000", at);
}
// The reads a page makes of the table (RLSP.role.field and the like), and the ones that name no field in the copy.
function reads(text) {
  const all = Object.assign({}, load("map"), load("frontend"));
  const found = text.match(/\b(RLSP|RLS_R|RLS_C|RLS_S)\.[a-z_]+\.[a-z_]+\b/g) || [];
  const bad = found.filter(x => { const [v, r, f] = x.split("."); const sp = (all[VARS[v]] || {})[r]; return !sp || !(f in sp); });
  return { found, bad };
}

module.exports = { load, install, resolve, reads, PAGES };

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

module.exports = { load, install, PAGES };

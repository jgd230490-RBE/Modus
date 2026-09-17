// ===========================================================================
// Public map — package colouring of a linear alignment (the overlay module)
// ===========================================================================
//
// Modus, 16 Sep 2026. This file is PRODUCT CODE and carries NO project data. It
// used to be map/ipt_segments.js, which mixed the band table, the work-section
// names and the boundary chainages of one project into the functions that draw
// them. Those now arrive from the tenant package through
//
//     GET /api/public/alignment
//
// as one JSON object — see applyOverlayPackage() below for its shape — and every
// function here reads the window globals at CALL time, never at load time, so
// the order "load overlay.js, fetch the package, build the layers" is the only
// order there is. With no package (a fresh tenant) every global is empty, every
// builder returns an empty FeatureCollection, and the map simply draws no
// alignment. That is the correct behaviour for a tenant that has not supplied
// one, not a fault.
//
// Reference geometry only. Nothing here touches routes, forecasts, zones or
// haul roads, and nothing here is read by the backend.
//
// ---------------------------------------------------------------------------
// WHY THIS FILE SPLITS LINES INSTEAD OF STAMPING THEM
// ---------------------------------------------------------------------------
// The obvious approach — take each alignment feature's midpoint, find the
// nearest chainage marker, stamp one band on the whole feature — was checked
// against real survey data before this was built, and it does not work. Survey
// alignments arrive as LONG features (spans of tens of kilometres are normal)
// and usually carry no chainage property at all, while a band can be 2–5 km
// wide. One midpoint stamp paints a long feature a single colour and swallows
// every narrow band it crosses — exactly the bands the overlay exists to show.
//
// So: every vertex gets a chainage (from the package's chainage markers), and
// the line is CUT where the band changes. One source feature becomes one output
// feature per band it crosses, with the same properties a stamp would have set.
//
// Vocabulary: the code keeps the internal names `ipt` / IPT_SEGMENTS for the
// package bands and `ws` for the sections within them (the label users see is
// the tenant's `team_label`; the words in the code are identifiers, not UI).
//
// ⚠️ NAMING COLLISION, written down where it will be read: `ipt` on a ROUTE means
//    the team that owns the delivery (the #filter-ipt dropdown filters routes by
//    it); `ipt` on an ALIGNMENT SEGMENT means the package this ground is in. The
//    alignment layer's filter is driven by the legend checkboxes, never by
//    #filter-ipt, and the two must not be pointed at each other.

// --- Defaults: everything empty until applyOverlayPackage() runs -------------
window.IPT_SEGMENTS = window.IPT_SEGMENTS || [];
window.IPT_UNDERLAY = window.IPT_UNDERLAY || null;
window.WS_NAMES = window.WS_NAMES || {};
window.IPT_BOUNDS_PROVISIONAL = window.IPT_BOUNDS_PROVISIONAL || [];
window.WS_BOUNDARIES = window.WS_BOUNDARIES || [];
window.OVERLAY_VERSION = window.OVERLAY_VERSION || null;

// The package's `overlay` object, as the API returns it:
//   {
//     version:  'uk-demo-1',                      // free text, shown in the sidebar
//     alignment: FeatureCollection,               // LineString / MultiLineString features;
//                                                 //   properties.align_type === 'Main Track'
//                                                 //   is what the band layer paints
//     chainage:  FeatureCollection,               // Point features with properties.chain
//                                                 //   (metres, "42,900.00" or 42900)
//     bands:     [{ ipt, ws: [], label, ws_primary, chain_from, chain_to, colour,
//                   muted }],                     // contiguous, chain_to == next chain_from
//     underlay:  { key: 'Team 6', colour, width, opacity } | null,
//     section_names: { WS1: { name, ipt, note, provisional } },
//     boundaries: [{ chain_m, from_ws, to_ws, from_ipt, to_ipt, provisional, note }],
//     provisional_bounds: ['WS2/WS3 @ 14500'],
//     rail:      FeatureCollection | null,        // an existing railway, drawn under the hauls
//     view:      { center: [lon, lat], zoom }     // where the map opens
//   }
window.applyOverlayPackage = function (o) {
  o = o || {};
  var EMPTY = { type: 'FeatureCollection', features: [] };
  window.alignment_data = (o.alignment && o.alignment.features) ? o.alignment : EMPTY;
  window.chainage_global_data = (o.chainage && o.chainage.features) ? o.chainage : EMPTY;
  window.IPT_SEGMENTS = Array.isArray(o.bands) ? o.bands : [];
  window.IPT_UNDERLAY = o.underlay || null;
  window.WS_NAMES = o.section_names || {};
  window.WS_BOUNDARIES = Array.isArray(o.boundaries) ? o.boundaries : [];
  window.IPT_BOUNDS_PROVISIONAL = Array.isArray(o.provisional_bounds) ? o.provisional_bounds : [];
  window.evr_rail_data = (o.rail && o.rail.features) ? o.rail : EMPTY;
  window.OVERLAY_VIEW = o.view || null;
  window.OVERLAY_VERSION = o.version || null;
  return window;
};

// ---------------------------------------------------------------------------
// The colour rule, and what it is protecting
// ---------------------------------------------------------------------------
// ⚠️ MANDATORY: no band colour may reuse a hex the map already spends on a
//    route, a forecast, a selection or temporary haul. If it did, a planner
//    could not tell "this stretch is package 6" from "this route is laden" — and
//    the route layers are the ones that carry money. Asserted in
//    backend/tests/parse_map.js against the demo package, so a future palette
//    edit cannot quietly reintroduce one. Re-hexed for the Modus theme, 16 Sep.
window.IPT_RESERVED_COLOURS = [
  '#059669', '#f59e0b', '#C2790B', '#3B82F6', '#DC2626', '#2563EB', '#0F172A',
];
window.wsLabel = function (code) {
  var w = (window.WS_NAMES || {})[code];
  return w ? w.name : '';
};

// Chainage as a railway engineer writes it: 42900 -> "42+900".
window.chainText = function (m) {
  if (m == null || isNaN(m)) return '–';
  var v = Math.round(m);
  var sign = v < 0 ? '-' : '';
  v = Math.abs(v);
  var km = Math.floor(v / 1000);
  var rem = v % 1000;
  return sign + km + '+' + String(rem).padStart(3, '0');
};

window.IPT_DEFAULT = { ipt: 'Unknown', ws: [], label: 'Unassigned', colour: '#64748B' };
window.iptForChainage = function (chain_m) {
  if (chain_m == null || isNaN(chain_m)) return window.IPT_DEFAULT;
  var segs = window.IPT_SEGMENTS || [];
  for (var i = 0; i < segs.length; i++) {
    var s = segs[i];
    if (chain_m >= s.chain_from && chain_m < s.chain_to) return s;
  }
  return window.IPT_DEFAULT;
};

// ---------------------------------------------------------------------------
// Chainage lookup
// ---------------------------------------------------------------------------
// A 200 km corridor is ~200,000 alignment vertices against ~2,000 chainage points — hundreds of millions of
// distance tests brute force, which is seconds of blocked main thread on page
// load. A flat grid index makes it a handful of tests per vertex.
//
// Cell 0.02 deg lon x 0.01 deg lat is roughly 1.2–1.4 km x 1.1 km at European
// latitudes, and chainage markers are typically ~100 m apart along the line, so
// ring 0 or ring 1 almost always contains a hit.

var CELL_LON = 0.02;
var CELL_LAT = 0.01;
var LON_SCALE = 0.6;     // cos(mean latitude); recomputed from the data in buildChainageIndex
var MAX_RING = 60;       // ~66 km. Beyond that the vertex is not near the line.

function buildChainageIndex(chainageFC) {
  // the grid cells must be roughly square on the ground, and that depends on latitude
  if (chainageFC && chainageFC.features && chainageFC.features.length) {
    var latSum = 0, latN = 0;
    for (var li = 0; li < chainageFC.features.length; li++) {
      var lg = chainageFC.features[li].geometry;
      if (lg && lg.coordinates && lg.coordinates.length > 1) { latSum += lg.coordinates[1]; latN++; }
    }
    if (latN) LON_SCALE = Math.max(0.2, Math.cos((latSum / latN) * Math.PI / 180));
  }
  var grid = Object.create(null);
  var feats = (chainageFC && chainageFC.features) || [];
  var n = 0;
  for (var i = 0; i < feats.length; i++) {
    var p = feats[i];
    var props = p.properties || {};
    var raw = props.chain;
    if (raw == null) continue;
    // "42,900.00" -> 42900
    var m = parseFloat(String(raw).replace(/,/g, ''));
    if (isNaN(m)) continue;
    var c = p.geometry && p.geometry.coordinates;
    if (!c) continue;
    var lon = c[0], lat = c[1];
    var key = Math.floor(lon / CELL_LON) + '|' + Math.floor(lat / CELL_LAT);
    (grid[key] || (grid[key] = [])).push([lon, lat, m]);
    n++;
  }
  return { grid: grid, count: n };
}

// Nearest chainage in metres, or null if nothing is within MAX_RING cells.
function nearestChainage(index, lon, lat) {
  var gx = Math.floor(lon / CELL_LON);
  var gy = Math.floor(lat / CELL_LAT);
  var grid = index.grid;
  var best = null, bestD2 = Infinity;

  for (var r = 0; r <= MAX_RING; r++) {
    // Once a hit is closer than the guaranteed-empty inner radius of the next
    // ring, no further ring can beat it.
    if (best !== null) {
      var innerLat = (r - 1) * CELL_LAT;
      if (innerLat > 0 && bestD2 < innerLat * innerLat) break;
    }
    for (var dx = -r; dx <= r; dx++) {
      for (var dy = -r; dy <= r; dy++) {
        // ring only, not the filled square — inner cells were done already
        if (r > 0 && Math.abs(dx) !== r && Math.abs(dy) !== r) continue;
        var bucket = grid[(gx + dx) + '|' + (gy + dy)];
        if (!bucket) continue;
        for (var i = 0; i < bucket.length; i++) {
          var b = bucket[i];
          var ddx = (b[0] - lon) * LON_SCALE;
          var ddy = b[1] - lat;
          var d2 = ddx * ddx + ddy * ddy;
          if (d2 < bestD2) { bestD2 = d2; best = b[2]; }
        }
      }
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// Band splitting
// ---------------------------------------------------------------------------

var MIN_RUN_M = 250;   // collapse band runs shorter than this — see below
var EARTH_R = 6371000;

function metres(a, b) {
  var dLat = (b[1] - a[1]) * Math.PI / 180;
  var dLon = (b[0] - a[0]) * Math.PI / 180;
  var lat1 = a[1] * Math.PI / 180, lat2 = b[1] * Math.PI / 180;
  var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
          Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return 2 * EARTH_R * Math.asin(Math.sqrt(Math.min(1, h)));
}
window.iptMetres = metres;   // exposed for the test harness

function bandIndexOf(seg) {
  var segs = window.IPT_SEGMENTS;
  for (var i = 0; i < segs.length; i++) if (segs[i] === seg) return i;
  return -1;   // IPT_DEFAULT
}

// Nearest-marker assignment is not monotonic near a boundary: two adjacent
// vertices can snap to markers either side of it and the band flickers. That
// would emit dozens of one-vertex features. So any run shorter than MIN_RUN_M
// is absorbed into the longer of its neighbours before cutting.
// `steps[i]` is the length of the leg from vertex i to i+1, precomputed once —
// re-haversining inside the smoothing loop was the whole cost of this file.
function smoothRuns(bands, steps) {
  if (bands.length < 3) return bands;
  var guard = 0;
  while (guard++ < 50) {
    var runs = [];
    var start = 0;
    for (var i = 1; i <= bands.length; i++) {
      if (i === bands.length || bands[i] !== bands[start]) {
        var len = 0;
        for (var j = start; j < i - 1; j++) len += steps[j];
        runs.push({ from: start, to: i - 1, band: bands[start], len: len });
        start = i;
      }
    }
    if (runs.length < 2) break;

    // Absorb every too-short run in one pass, shortest first, so a long line
    // with many boundary flickers does not need one full rebuild per flicker.
    var order = [];
    for (var k = 0; k < runs.length; k++) if (runs[k].len < MIN_RUN_M) order.push(k);
    if (!order.length) break;
    order.sort(function (a, b) { return runs[a].len - runs[b].len; });

    var changed = false;
    for (var o = 0; o < order.length; o++) {
      var k2 = order[o];
      var prev = k2 > 0 ? runs[k2 - 1] : null;
      var next = k2 < runs.length - 1 ? runs[k2 + 1] : null;
      var into = null;
      if (prev && next) into = (prev.len >= next.len) ? prev.band : next.band;
      else if (prev) into = prev.band;
      else if (next) into = next.band;
      if (into === null || into === runs[k2].band) continue;
      for (var v = runs[k2].from; v <= runs[k2].to; v++) bands[v] = into;
      changed = true;
    }
    if (!changed) break;
  }
  return bands;
}

// ---------------------------------------------------------------------------
// Gap splitting — a PRE-EXISTING map defect this overlay exposed
// ---------------------------------------------------------------------------
// A surveyed alignment often stores physically discontinuous track as a single
// LineString with a straight edge bridging the hole: thousands of vertices a few
// metres apart, then one edge several kilometres long with nothing in between.
// On the first real survey this ran against, over a third of the drawn length
// was such straights — a double-track corridor measured as roughly three times
// its own length until they were cut.
//
// Drawn plainly, those straights are already on screen in black. Coloured by
// band they become worse than cosmetic: a long straight would be painted as a
// confident band cutting across country that has no railway on it.
//
// The cut is a RATIO test, not an absolute one. Some genuine short tracks are
// stored as a single two-vertex straight (median edge == the only edge, ratio
// 1x) and an absolute threshold alone would delete them. A gap is an edge that
// is both over GAP_MIN_M and far longer than the rest of its own part.
//
// ⚠️ This changes what the existing 'Rail alignment' layer draws, beyond the
//    handoff spec. Set GAP_SPLIT = false to restore the old behaviour and see
//    the straights again. Counts land in window.IPT_BUILD_STATS either way.

var GAP_SPLIT = true;
var GAP_MIN_M = 150;
var GAP_RATIO = 20;
var gapStats = { edges_cut: 0, km_removed: 0 };

function medianOf(arr) {
  if (!arr.length) return 0;
  var a = arr.slice().sort(function (x, y) { return x - y; });
  var h = a.length >> 1;
  return a.length % 2 ? a[h] : (a[h - 1] + a[h]) / 2;
}

// Every cut edge is also KEPT, as a two-point "bridge". The geometry cut stays
// hard — a bridge is a separate feature, flagged is_bridge, painted at 30%
// opacity on its own layer. So the corridor reads as continuous while the
// missing stretches stay visibly weaker, and nothing measured off the solid
// features includes a straight line across country. See BRIDGE_STEP_M below for
// why they are then densified rather than drawn as single straights.
function splitOnce(coords, out, bridges) {
  if (coords.length < 3) { out.push(coords); return false; }
  var steps = [];
  for (var i = 0; i < coords.length - 1; i++) steps.push(metres(coords[i], coords[i + 1]));
  var med = medianOf(steps);
  var cut = false;
  var start = 0;
  for (var j = 0; j < steps.length; j++) {
    if (steps[j] > GAP_MIN_M && steps[j] > GAP_RATIO * med) {
      if (j + 1 - start >= 2) out.push(coords.slice(start, j + 1));
      if (bridges) bridges.push([coords[j], coords[j + 1]]);
      start = j + 1;
      cut = true;
      gapStats.edges_cut++;
      gapStats.km_removed += steps[j] / 1000;
    }
  }
  if (!cut) { out.push(coords); return false; }
  if (coords.length - start >= 2) out.push(coords.slice(start));
  return true;
}

// Cutting a part changes the median of what is left, so an edge that looked
// ordinary against the whole line can look like a gap against the surviving
// run. Iterate until nothing more splits — otherwise the invariant asserted in
// backend/tests/test_ipt_overlay.js ("no gap-shaped edge survives") is only
// true of the first pass.
function splitAtGaps(coords, bridges) {
  if (!GAP_SPLIT || coords.length < 3) return [coords];
  var work = [coords];
  var depth = 0;
  while (depth++ < 20) {
    var next = [];
    var any = false;
    for (var i = 0; i < work.length; i++) if (splitOnce(work[i], next, bridges)) any = true;
    work = next;
    if (!any) break;
  }
  return work.length ? work : [coords];
}

// A bridge (a gap between survey features) can be tens of kilometres long —
// longer than most bands. Drawn as one straight it would have to be given ONE colour — the exact
// midpoint-stamping mistake this file exists to avoid, just at 30% opacity. So
// each bridge is densified to a vertex every BRIDGE_STEP_M and then fed through
// the same band splitter as everything else: it changes colour where it crosses
// a boundary, like the real track beside it.
var BRIDGE_STEP_M = 200;

function densify(a, b) {
  var d = metres(a, b);
  var n = Math.max(1, Math.min(400, Math.ceil(d / BRIDGE_STEP_M)));
  var pts = [];
  for (var i = 0; i <= n; i++) {
    var f = i / n;
    pts.push([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]);
  }
  return pts;
}

function segmentPart(coords, index, props, out, isBridge) {
  if (!coords || coords.length < 2) return;

  var bands = new Array(coords.length);
  var chains = new Array(coords.length);
  for (var i = 0; i < coords.length; i++) {
    var m = nearestChainage(index, coords[i][0], coords[i][1]);
    chains[i] = m;
    bands[i] = bandIndexOf(window.iptForChainage(m));
  }
  var steps = new Array(coords.length - 1);
  for (var s = 0; s < coords.length - 1; s++) steps[s] = metres(coords[s], coords[s + 1]);
  smoothRuns(bands, steps);

  var segStart = 0;
  for (var j = 1; j <= coords.length; j++) {
    if (j < coords.length && bands[j] === bands[segStart]) continue;

    // Share the boundary vertex with the next segment so the painted line has
    // no visible gap at a band change.
    var end = (j < coords.length) ? j : coords.length - 1;
    var slice = coords.slice(segStart, end + 1);
    if (slice.length >= 2) {
      var band = bands[segStart];
      var seg = band >= 0 ? window.IPT_SEGMENTS[band] : window.IPT_DEFAULT;
      var cs = [], ce = [];
      for (var q = segStart; q <= end; q++) if (chains[q] != null) { cs.push(chains[q]); ce.push(chains[q]); }
      var p = {};
      for (var key in props) p[key] = props[key];
      p.ipt = seg.ipt;
      p.ws = (seg.ws || []).join(',');
      // ⭐ The band table's boundaries ARE the work-section boundaries, so
      // every segment already falls inside exactly one WS band — no finer split
      // is needed to stamp it. ws_primary is the MAINLINE section that owns this
      // chainage; the other codes in `ws` are point assets (stations, halts,
      // depots) that sit on the same ground without owning the band.
      p.ws_primary = seg.ws_primary || '';
      p.ws_name = seg.ws_primary ? window.wsLabel(seg.ws_primary) : '';
      p.ipt_label = seg.label;
      p.ipt_colour = seg.colour;
      p.muted = !!seg.muted;            // an out-of-scope band: drawn muted, no underlay
      p.provisional = !!seg.provisional; // a band edge the package flags as unconfirmed
      p.chain_from_m = cs.length ? Math.round(Math.min.apply(null, cs)) : null;
      p.chain_to_m = ce.length ? Math.round(Math.max.apply(null, ce)) : null;
      p.is_main_track = (props.align_type === 'Main Track');
      p.is_bridge = !!isBridge;
      out.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: slice }, properties: p });
    }
    segStart = j;
  }
}

// Returns a NEW FeatureCollection. The input is not mutated, and the result is
// computed once and held, so a basemap style switch re-adds the same object
// with the properties already on it — no re-stamping on style.load.
window.buildIptAlignment = function (alignmentFC, chainageFC) {
  var t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
  if (!alignmentFC || !alignmentFC.features) return alignmentFC;
  var index = buildChainageIndex(chainageFC);
  if (!index.count) {
    console.warn('[IPT] no usable chainage markers — alignment left uncoloured');
    return alignmentFC;
  }

  gapStats = { edges_cut: 0, km_removed: 0 };
  var out = [];
  var src = alignmentFC.features;
  for (var i = 0; i < src.length; i++) {
    var f = src[i];
    var g = f.geometry;
    if (!g) continue;
    var raw = (g.type === 'LineString') ? [g.coordinates]
            : (g.type === 'MultiLineString') ? g.coordinates : [];
    for (var k = 0; k < raw.length; k++) {
      var bridges = [];
      var runs = splitAtGaps(raw[k], bridges);
      for (var r = 0; r < runs.length; r++) segmentPart(runs[r], index, f.properties || {}, out);
      // Bridges are emitted AFTER their own feature's runs but into the same
      // array, and the layer that draws them is added after the solid one, so a
      // bridge never paints over real track.
      for (var b = 0; b < bridges.length; b++) {
        segmentPart(densify(bridges[b][0], bridges[b][1]), index, f.properties || {}, out, true);
      }
    }
  }

  var t1 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
  var nBridge = 0;
  for (var q = 0; q < out.length; q++) if (out[q].properties.is_bridge) nBridge++;

  window.IPT_BUILD_STATS = {
    source_features: src.length,
    output_features: out.length,
    solid_features: out.length - nBridge,
    bridge_features: nBridge,
    chainage_markers: index.count,
    gap_split: GAP_SPLIT,
    gap_edges_cut: gapStats.edges_cut,
    gap_km_removed: Math.round(gapStats.km_removed * 10) / 10,
    ms: Math.round(t1 - t0),
  };
  if (typeof console !== 'undefined' && console.log) {
    console.log('[IPT] alignment overlay', window.IPT_BUILD_STATS);
  }
  return { type: 'FeatureCollection', features: out };
};

window.IPT_GAP_CONFIG = { split: GAP_SPLIT, min_m: GAP_MIN_M, ratio: GAP_RATIO };

// ---------------------------------------------------------------------------
// Chainage marker density
// ---------------------------------------------------------------------------
// Markers every ~100 m on a long corridor are, at corridor zoom, a grey smear,
// not information. Each point gets a `step_m` — the coarsest
// round interval its chainage falls on — and the map shows only the coarse ones
// until you zoom in.
//
//   step_m   what it is
//   10000    the 10 km ticks. All that is drawn at corridor zoom.
//    5000    the intermediate 5 km ticks
//    1000    kilometre ticks
//     500    half-kilometre ticks
//     100    everything else
//
// (window.CHAINAGE_STEP_COUNTS records how many of each a package produced.)
//
// ⚠️ Mapbox GL cannot use ['zoom'] inside a layer `filter`. So the tiering is
//    done in the PAINT and LAYOUT expressions instead — an outermost
//    ['step', ['zoom'], ...] whose branches test step_m — which is allowed, and
//    keeps both layer ids unchanged so the existing checkbox still works.
window.CHAINAGE_STEPS = [10000, 5000, 1000, 500, 100];

// ⚠️ The spec gave the on-tick test as
//        Math.abs(chain_m % step) < 0.5 || Math.abs(chain_m % step - step) < 0.5
//    which is WRONG for negative chainage, and a corridor's chainage can start
//    below zero. In JS, (-3982.3 % 10000) is -3982.3, so the first clause fails
//    and the second compares against -13982.3 — a negative tick can never
//    match. Normalising the remainder into [0, step) first fixes it and keeps
//    the intended tolerance, which exists because these values are floats
//    ("42,900.00") and not all of them land on an exact integer.
function onTick(m, step) {
  var r = ((m % step) + step) % step;
  return r < 0.5 || r > step - 0.5;
}
window.iptOnTick = onTick;

window.buildChainageSteps = function (chainageFC) {
  if (!chainageFC || !chainageFC.features) return chainageFC;
  var out = [];
  var counts = {};
  var steps = window.CHAINAGE_STEPS;
  for (var i = 0; i < chainageFC.features.length; i++) {
    var f = chainageFC.features[i];
    var raw = (f.properties || {}).chain;
    var m = raw == null ? NaN : parseFloat(String(raw).replace(/,/g, ''));
    var step = steps[steps.length - 1];
    if (!isNaN(m)) {
      for (var s = 0; s < steps.length; s++) {
        if (onTick(m, steps[s])) { step = steps[s]; break; }
      }
    }
    counts[step] = (counts[step] || 0) + 1;
    var p = {};
    for (var k in f.properties) p[k] = f.properties[k];
    p.step_m = step;
    p.chain_m = isNaN(m) ? null : Math.round(m);
    out.push({ type: 'Feature', geometry: f.geometry, properties: p });
  }
  window.CHAINAGE_STEP_COUNTS = counts;
  return { type: 'FeatureCollection', features: out };
};

// ---------------------------------------------------------------------------
// Work-section boundary ticks
// ---------------------------------------------------------------------------
// The package edges, drawn as a short mark ACROSS the alignment. Not a second
// coloured corridor and not a second chainage ladder: the chainage layer is a
// 100 m grid of thousands of points; this is a handful of lines that mean something.
//
// ⚠️ These are the SAME chainages the band table already cuts on. The package
//    declares them (boundaries) beside the bands, and they are asserted against
//    IPT_SEGMENTS in backend/tests/test_ipt_overlay.js and validated on upload
//    (tenant_package.validate_overlay) — a tick that drifts from the colour
//    change it marks would be worse than no tick.
//
// ⚠️ A boundary the package marks `provisional` is drawn but flagged in its popup.
//    A boundary chainage must equal the band edge it marks — the package supplies
//    both, and test_ipt_overlay.js asserts they agree; moving one without the
//    other puts the tick off the colour change.
//
// ⚠️ Point assets — a station, a halt, a depot — are sections, not mainline
//    bands, and get no tick: a tick would assert an edge the scope does not draw.
//    Chainage here is the package's single global datum; a local datum must not
//    be mixed in.

window.WS_TICK_COLOUR = '#334155';   // neutral slate: not a route, not a package

// A boundary further than this from any drawn Main Track is sitting over one of
// the alignment's holes. 100 m is comfortably beyond survey noise (with markers
// ~100 m apart the nearest-marker residual is under ~50 m) and below any hole
// worth warning about.
var NO_TRACK_M = 100;

function bearingBetween(a, b) {
  var y = Math.sin((b[0] - a[0]) * Math.PI / 180) * Math.cos(b[1] * Math.PI / 180);
  var x = Math.cos(a[1] * Math.PI / 180) * Math.sin(b[1] * Math.PI / 180) -
          Math.sin(a[1] * Math.PI / 180) * Math.cos(b[1] * Math.PI / 180) *
          Math.cos((b[0] - a[0]) * Math.PI / 180);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

// Points, not lines. The tick is drawn as a rotated glyph in a symbol layer so
// it stays a constant SIZE ON SCREEN: a fixed ground length would be one pixel
// at corridor zoom and half the viewport at zoom 16.
window.buildWsBoundaries = function (chainageFC, alignmentFC) {
  if (!chainageFC || !chainageFC.features) return { type: 'FeatureCollection', features: [] };
  var pts = [];
  for (var i = 0; i < chainageFC.features.length; i++) {
    var f = chainageFC.features[i];
    var raw = (f.properties || {}).chain;
    var m = raw == null ? NaN : parseFloat(String(raw).replace(/,/g, ''));
    var c = f.geometry && f.geometry.coordinates;
    if (isNaN(m) || !c) continue;
    pts.push({ m: m, lon: c[0], lat: c[1] });
  }
  pts.sort(function (a, b) { return a.m - b.m; });

  // de-duplicate: a survey's chainage file can repeat values, and two markers
  // sharing a value give a zero-length span and therefore no bearing
  var uniq = [];
  for (var u = 0; u < pts.length; u++) {
    if (!uniq.length || pts[u].m > uniq[uniq.length - 1].m) uniq.push(pts[u]);
  }

  var out = [];
  for (var k = 0; k < window.WS_BOUNDARIES.length; k++) {
    var b = window.WS_BOUNDARIES[k];
    if (uniq.length < 2) break;

    // index of the first marker at or beyond the boundary
    var hi = 0;
    while (hi < uniq.length && uniq[hi].m < b.chain_m) hi++;
    if (hi >= uniq.length) hi = uniq.length - 1;
    var lo = Math.max(0, hi - 1);
    if (lo === hi) hi = Math.min(uniq.length - 1, lo + 1);

    // position: interpolate between the bracketing markers
    var span = uniq[hi].m - uniq[lo].m;
    var t = span > 0 ? Math.max(0, Math.min(1, (b.chain_m - uniq[lo].m) / span)) : 0;
    var lon = uniq[lo].lon + (uniq[hi].lon - uniq[lo].lon) * t;
    var lat = uniq[lo].lat + (uniq[hi].lat - uniq[lo].lat) * t;

    // ⚠️ bearing comes from the markers EITHER SIDE of the boundary, widened by
    // one where the boundary lands exactly on a marker. Taking it from the
    // bracketing pair alone gave a zero-length span on an exact hit, and the
    // first version then silently reused the PREVIOUS tick's bearing — several
    // ticks were rotated to a different stretch of railway.
    var bl = Math.max(0, lo - (t <= 0.001 ? 1 : 0));
    var bh = Math.min(uniq.length - 1, hi + (t >= 0.999 ? 1 : 0));
    if (bh <= bl) { bl = Math.max(0, bh - 1); }
    var brg = bearingBetween([uniq[bl].lon, uniq[bl].lat], [uniq[bh].lon, uniq[bh].lat]);

    out.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lon, lat] },
      properties: {
        chain_m: b.chain_m,
        chain_txt: window.chainText(b.chain_m),
        bearing: Math.round(brg * 10) / 10,
        tick_rotate: Math.round(((brg + 90) % 360) * 10) / 10,
        from_ws: b.from_ws || '',
        to_ws: b.to_ws || '',
        // no next section: name the band being entered (the package's to_ipt), else say so
        label: (b.from_ws || '—') + ' | ' + (b.to_ws || b.to_ipt || 'Outside scope'),
        from_ipt: b.from_ipt || '',
        to_ipt: b.to_ipt || '',
        provisional: !!b.provisional,
        note: b.note || '',
        bearing_span_m: Math.round(uniq[bh].m - uniq[bl].m),
      },
    });
  }
  // Phase 5b: an ordinal along the corridor, used by map/index.html to label only
  // every OTHER boundary between zoom 11 and 12. Boundaries a few km apart
  // have labels that collide there.
  // Stamped here rather than computed in the layer expression because Mapbox has
  // no index-of operator, and because the order is a property of the data.
  out.sort(function (a, b) { return a.properties.chain_m - b.properties.chain_m; });
  for (var ix = 0; ix < out.length; ix++) out[ix].properties.idx = ix;

  // ⭐ Which of these boundaries has no surveyed track under it?
  //
  // The ticks are positioned from the chainage points, which normally cover the
  // corridor continuously. A surveyed alignment often does NOT — it can have
  // kilometres of holes — and a package edge that falls in one has genuinely no
  // drawn line for the tick to sit on.
  //
  // Measured here rather than hard-coded, so a refreshed alignment file changes
  // the answer instead of leaving a stale warning on the map.
  var flagged = 0;
  if (alignmentFC && alignmentFC.features) {
    var solid = [];
    for (var q = 0; q < alignmentFC.features.length; q++) {
      var af = alignmentFC.features[q];
      if (af.properties && af.properties.align_type === 'Main Track' &&
          af.properties.is_bridge !== true) solid.push(af.geometry.coordinates);
    }
    for (var o = 0; o < out.length; o++) {
      var pt = out[o].geometry.coordinates;
      var best = Infinity;
      for (var r2 = 0; r2 < solid.length; r2++) {
        var cs = solid[r2];
        for (var c2 = 0; c2 < cs.length; c2++) {
          var dd = metres(pt, cs[c2]);
          if (dd < best) best = dd;
        }
      }
      out[o].properties.track_gap_m = Math.round(best);
      out[o].properties.no_surveyed_track = best > NO_TRACK_M;
      if (best > NO_TRACK_M) flagged++;
    }
  }

  window.WS_BOUNDARY_STATS = {
    built: out.length,
    expected: window.WS_BOUNDARIES.length,
    no_surveyed_track: flagged,
  };
  return { type: 'FeatureCollection', features: out };
};

// Legend rows, one per unique IPT, generated from IPT_SEGMENTS so the table
// stays the single source of truth. A band flagged `muted` is shown muted rather than
// hidden — an unexplained grey line reads as a bug.
window.iptLegendRows = function () {
  var seen = Object.create(null);
  var rows = [];
  var segs = window.IPT_SEGMENTS || [];
  for (var i = 0; i < segs.length; i++) {
    var s = segs[i];
    if (seen[s.ipt]) {
      var r = seen[s.ipt];
      for (var j = 0; j < s.ws.length; j++) if (r.ws.indexOf(s.ws[j]) === -1) r.ws.push(s.ws[j]);
      if (r.labels.indexOf(s.label) === -1) r.labels.push(s.label);
      continue;
    }
    seen[s.ipt] = { ipt: s.ipt, colour: s.colour, ws: s.ws.slice(), labels: [s.label], muted: !!s.muted };
    rows.push(seen[s.ipt]);
  }
  return rows;
};

if (typeof module !== 'undefined' && module.exports) module.exports = window;

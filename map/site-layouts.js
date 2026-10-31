/*
 * site-layouts.js — draws a site's logistics layout on a Mapbox GL map (task 4c PR 1, 31 Oct 2026; the mockup John
 * approved, notes site-layouts-mockup-1030, app.js addOurLayers / render).
 *
 * ONE drawing for both maps: the staff Route map (map/index.html, read only) and the Locations page's map
 * (frontend/index.html). Every look — barrier blocks, Heras posts, hatching, symbols, words, arrowheads — is drawn
 * by these layers from each thing's properties and the server's ONE style table (GET /api/site-layouts/styles), so
 * a look is never decided in two places.
 *
 * Widths and sizes are METRES on the ground: drawn true to scale and never thinner than a hairline. The zoom stays
 * the top-level input of every expression (GL drops a layer whose zoom expression sits inside arithmetic); each
 * thing carries `_m` = 1 / cos(its latitude), so a metre is a metre anywhere.
 *
 *   const h = WSLayouts.install(map, styles, { prefix: "sl", before: () => "some-layer-id", minzoom: 16 });
 *   await h.ready;            // the symbol pictures are loaded
 *   h.setData(features);      // a GeoJSON FeatureCollection or a list of things
 *   h.setVisible(false);  h.reinstall();   // after map.setStyle (every layer and picture is dropped)
 *
 * 31 Oct 2026 (PR 2): the layout's WORDS (text things, area names, symbol labels) show only from zoom WORDS_Z (15), on
 * both maps — at the whole-scheme zoom they printed as a smudge over the site (the live test L1). And `geo`: the pure
 * geometry the drawing tools use (turn, resize, round to 7 dp, the holes that follow an area), testable in Node.
 */
(function () {
  "use strict";
  // metres a CSS pixel covers at zoom z, at the equator, divided out by cos(latitude) per thing (`_m`)
  const C0 = 40075016.686 / 512;
  const ZS = [12, 14, 16, 18, 20, 22];
  const metres = (val, minPx, add, per) => ["interpolate", ["exponential", 2], ["zoom"],
    ...ZS.flatMap((z) => {
      const v = ["max", minPx, ["*", val, ["coalesce", ["get", "_m"], 1.6], (2 ** z) / C0 / (per || 1)]];
      return [z, add ? ["+", add, v] : v];
    })];
  const W = (d) => ["coalesce", ["get", "w"], d];
  const OP = ["coalesce", ["get", "opacity"], 1];
  const isLine = (key) => ["all", ["==", ["get", "style"], key], ["==", ["geometry-type"], "LineString"]];
  const isArea = ["==", ["geometry-type"], "Polygon"];

  function svgDoc(inner) {
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="128" height="128">' + inner + "</svg>";
  }
  function loadSvg(inner) {
    return new Promise((res) => {
      const img = new Image(128, 128);
      img.onload = () => res(img);
      img.onerror = () => res(null);
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgDoc(inner));
    });
  }
  function patternImage(kind, hex) {
    const c = document.createElement("canvas"); c.width = c.height = 32; const g = c.getContext("2d");
    g.strokeStyle = hex; g.fillStyle = hex; g.lineWidth = 3;
    const diag = (flip) => {
      g.beginPath();
      for (let k = -32; k <= 64; k += 16) { if (flip) { g.moveTo(k, 32); g.lineTo(k + 32, 0); } else { g.moveTo(k, 0); g.lineTo(k + 32, 32); } }
      g.stroke();
    };
    if (kind === "hatch") diag(false);
    if (kind === "cross") { diag(false); diag(true); }
    if (kind === "dots") { for (const [x, y] of [[8, 8], [24, 24]]) { g.beginPath(); g.arc(x, y, 3.2, 0, 7); g.fill(); } }
    return g.getImageData(0, 0, 32, 32);
  }
  function darker(hex) {
    const n = parseInt(String(hex || "#6B7280").slice(1), 16);
    const f = (v) => Math.round(v * 0.62).toString(16).padStart(2, "0");
    return "#" + f(n >> 16) + f((n >> 8) & 255) + f(n & 255);
  }
  // metres east / north between two lon/lat points (site scale)
  const KY = 110574;
  const toM = (p, o) => [(p[0] - o[0]) * 111320 * Math.cos(o[1] * Math.PI / 180), (p[1] - o[1]) * KY];
  const bearing = (a, b) => { const m = toM(b, a); return (Math.atan2(m[0], m[1]) * 180 / Math.PI + 360) % 360; };
  function centroid(g) {
    const pts = g.type === "Point" ? [g.coordinates] : g.type === "LineString" ? g.coordinates : g.coordinates[0];
    const n = pts.length - (g.type === "Polygon" ? 1 : 0);
    let x = 0, y = 0;
    for (let i = 0; i < n; i++) { x += pts[i][0]; y += pts[i][1]; }
    return [x / n, y / n];
  }
  function areaM2(ring) {
    let s = 0;
    for (let i = 1; i < ring.length; i++) { const a = toM(ring[i - 1], ring[0]), b = toM(ring[i], ring[0]); s += a[0] * b[1] - b[0] * a[1]; }
    return Math.abs(s / 2);
  }
  const pt = (c, props) => ({ type: "Feature", geometry: { type: "Point", coordinates: c }, properties: props });
  const WORDS_Z = 15;

  // ---------------------------------------------------------------- geometry for the drawing tools (PR 2)
  const fromM = (m, o) => [o[0] + m[0] / (111320 * Math.cos(o[1] * Math.PI / 180)), o[1] + m[1] / KY];
  const r7 = (v) => Math.round(v * 1e7) / 1e7;
  function mapGeom(g, fn) {
    if (g.type === "Point") return { type: "Point", coordinates: fn(g.coordinates) };
    if (g.type === "LineString") return { type: "LineString", coordinates: g.coordinates.map(fn) };
    return { type: "Polygon", coordinates: g.coordinates.map((r) => r.map(fn)) };
  }
  const round7 = (g) => mapGeom(g, (p) => [r7(p[0]), r7(p[1])]);
  // turn by `deg` clockwise / resize by `k` / shift by e, n metres, about the thing's middle
  function rotate(g, deg, about) {
    const o = about || centroid(g), a = -deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    return mapGeom(g, (p) => { const m = toM(p, o); return fromM([m[0] * c - m[1] * s, m[0] * s + m[1] * c], o); });
  }
  function scale(g, k, about) { const o = about || centroid(g); return mapGeom(g, (p) => { const m = toM(p, o); return fromM([m[0] * k, m[1] * k], o); }); }
  function shift(g, e, n) { return mapGeom(g, (p) => fromM([e, n], p)); }
  // the turn + resize + shift that best takes points `a` onto points `b` (least squares; the survey points' fit)
  function fit(a, b) {
    const o = a[0], P = a.map((p, i) => [toM(p, o), toM(b[i], o)]), n = P.length;
    const mx = P.reduce((s, q) => s + q[0][0], 0) / n, my = P.reduce((s, q) => s + q[0][1], 0) / n;
    const MX = P.reduce((s, q) => s + q[1][0], 0) / n, MY = P.reduce((s, q) => s + q[1][1], 0) / n;
    let sxx = 0, A = 0, B = 0;
    for (const [[x0, y0], [X0, Y0]] of P) { const x = x0 - mx, y = y0 - my, X = X0 - MX, Y = Y0 - MY; sxx += x * x + y * y; A += x * X + y * Y; B += x * Y - y * X; }
    if (!sxx) { A = 1; B = 0; } else { A /= sxx; B /= sxx; }
    const f = (x, y) => [A * (x - mx) - B * (y - my) + MX, B * (x - mx) + A * (y - my) + MY];
    const worst = Math.max(0, ...P.map(([[x, y], [X, Y]]) => { const q = f(x, y); return Math.hypot(q[0] - X, q[1] - Y); }));
    return { worst, apply: (p) => { const m = toM(p, o); return fromM(f(m[0], m[1]), o); } };
  }
  function inRing(q, ring) {
    let c = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > q[1]) !== (yj > q[1]) && q[0] < (xj - xi) * (q[1] - yi) / (yj - yi) + xi) c = !c;
    }
    return c;
  }
  // An area's holes when its OUTSIDE edge went from `was` to `now` (the drawing tool holds no holes): moved, turned or
  // resized as a whole (every corner fits within 5 cm) the holes go with it; a corner moved, added or deleted leaves
  // them; a hole no longer inside the edge is dropped. -> { holes, dropped }
  function holesFollow(holes, was, now) {
    let out = holes;
    if (was && now && was.length === now.length && was.length > 3) {
      const t = fit(was.slice(0, -1), now.slice(0, -1));
      if (t.worst <= 0.05) out = holes.map((r) => r.map((q) => { const p = t.apply(q); return [r7(p[0]), r7(p[1])]; }));
    }
    const kept = out.filter((r) => r.every((q) => inRing(q, now || was)));
    return { holes: kept, dropped: out.length - kept.length };
  }
  const geo = { round7, mapGeom, rotate, scale, shift, fit, inRing, holesFollow, toM, fromM, lengthM: (cs) => cs.slice(1).reduce((s, p, i) => { const m = toM(p, cs[i]); return s + Math.hypot(m[0], m[1]); }, 0) };

  function install(map, styles, opts) {
    opts = opts || {};
    const P = (opts.prefix || "sl") + "-";
    const SRC = P + "things", DRV = P + "derived";
    const byKey = (v) => Array.isArray(v) ? Object.fromEntries(v.map((s) => [s.key, s])) : (v || {});
    const LINES = byKey(styles.lines), AREAS = byKey(styles.areas);
    const SYMS = {}; (styles.symbols || []).forEach((s) => { SYMS[s.key] = s; });
    const ids = [];
    let pics = null, data = { type: "FeatureCollection", features: [] }, derived = { type: "FeatureCollection", features: [] };
    let visible = opts.visible !== false;
    const ready = Promise.all([
      ...(styles.symbols || []).map((s) => loadSvg(s.svg).then((im) => ["s-" + s.key, im])),
      ...Object.entries(styles.glyphs || {}).map(([k, v]) => loadSvg(v).then((im) => ["g-" + k, im])),
    ]).then((list) => { pics = list.filter((x) => x[1]); addAll(); return true; });

    function img(id, im) { try { if (!map.hasImage(P + id)) map.addImage(P + id, im, { pixelRatio: 2 }); } catch (e) { /* the style is changing */ } }
    function pattern(kind, hex) { const id = `pat-${kind}-${hex.replace("#", "")}`; img(id, patternImage(kind, hex)); return P + id; }
    function before() { const b = typeof opts.before === "function" ? opts.before() : opts.before; return b && map.getLayer(b) ? b : undefined; }

    function addAll() {
      try { if (!pics || map.getSource(SRC)) return; } catch (e) { return; }   // the map went before the pictures came
      for (const [id, im] of pics) img(id, im);
      map.addSource(SRC, { type: "geojson", data });
      map.addSource(DRV, { type: "geojson", data: derived });
      ids.length = 0;
      const b = before();
      // opts.minzoom (31 Oct 2026, task 4c PR 4): nothing of the layout below this zoom (the public map: 16)
      const L = (o) => { o.id = P + o.id; o.layout = Object.assign({ visibility: visible ? "visible" : "none" }, o.layout || {}); if (opts.minzoom != null) o.minzoom = Math.max(o.minzoom || 0, opts.minzoom); map.addLayer(o, b); ids.push(o.id); };
      // ---- areas
      L({ id: "a-fill", type: "fill", source: SRC, filter: ["all", isArea, ["==", ["get", "fill"], "solid"]], layout: { "fill-sort-key": ["get", "z"] }, paint: { "fill-color": ["get", "color"], "fill-opacity": OP } });
      L({ id: "a-pat", type: "fill", source: SRC, filter: ["all", isArea, ["has", "pat"]], layout: { "fill-sort-key": ["get", "z"] }, paint: { "fill-pattern": ["get", "pat"], "fill-opacity": ["min", 1, ["+", 0.25, OP]] } });
      L({ id: "a-line", type: "line", source: SRC, filter: ["all", isArea, ["!=", ["get", "outline"], "dashed"]], paint: { "line-color": ["get", "color"], "line-width": metres(0.25, 1.6) } });
      L({ id: "a-dash", type: "line", source: SRC, filter: ["all", isArea, ["==", ["get", "outline"], "dashed"]], paint: { "line-color": ["get", "color"], "line-width": metres(0.25, 1.8), "line-dasharray": [4, 3] } });
      // ---- lines: the traffic bands first
      for (const key of ["oneway", "twoway", "lights"]) {
        L({ id: `l-${key}-band`, type: "line", source: SRC, filter: isLine(key), layout: { "line-cap": "butt", "line-join": "round", "line-sort-key": ["get", "z"] },
          paint: { "line-color": ["get", "color"], "line-width": metres(W((LINES[key] || {}).w || 3.5), 6), "line-opacity": ["*", key === "lights" ? 0.22 : 0.35, OP] } });
      }
      L({ id: "l-twoway-mid", type: "line", source: SRC, filter: isLine("twoway"), paint: { "line-color": "#FFFFFF", "line-width": metres(0.15, 1.5), "line-dasharray": [6, 4] } });
      L({ id: "l-lights-mid", type: "line", source: SRC, filter: isLine("lights"), paint: { "line-color": "#111827", "line-width": metres(0.2, 2), "line-dasharray": [1, 2] } });
      L({ id: "l-oneway-chev", type: "symbol", source: SRC, filter: isLine("oneway"), layout: { "symbol-placement": "line", "symbol-spacing": 70, "icon-image": P + "g-chev", "icon-size": metres(W(3.5), 0.18, 0, 64 / 0.7), "icon-allow-overlap": true, "icon-ignore-placement": true, "icon-rotation-alignment": "map" } });
      // a white edge under the thin lines, so they read on the aerial photo
      const thin = ["barrier", "heras", "hoarding", "ped", "cycle", "leader", "imported"];
      L({ id: "l-case", type: "line", source: SRC, filter: ["all", ["in", ["get", "style"], ["literal", thin]], ["==", ["geometry-type"], "LineString"]], layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#FFFFFF", "line-opacity": 0.85, "line-width": metres(W(0.3), 2, 2.5) } });
      L({ id: "l-barrier-base", type: "line", source: SRC, filter: isLine("barrier"), layout: { "line-cap": "butt" }, paint: { "line-color": "#FFFFFF", "line-width": metres(W(0.5), 4) } });
      L({ id: "l-barrier", type: "line", source: SRC, filter: isLine("barrier"), layout: { "line-cap": "butt" }, paint: { "line-color": ["get", "color"], "line-width": metres(W(0.5), 4), "line-dasharray": [2, 2], "line-opacity": OP } });
      L({ id: "l-heras", type: "line", source: SRC, filter: isLine("heras"), paint: { "line-color": ["get", "color"], "line-width": metres(W(0.12), 1.6), "line-opacity": OP } });
      L({ id: "l-heras-posts", type: "line", source: SRC, filter: isLine("heras"), layout: { "line-cap": "butt" }, paint: { "line-color": "#111827", "line-width": metres(0.45, 4), "line-dasharray": [1, 6.8] } });
      L({ id: "l-hoarding", type: "line", source: SRC, filter: isLine("hoarding"), layout: { "line-cap": "butt", "line-join": "miter" }, paint: { "line-color": ["get", "color"], "line-width": metres(W(0.3), 4), "line-opacity": OP } });
      L({ id: "l-cones-line", type: "line", source: SRC, filter: isLine("cones"), paint: { "line-color": ["get", "color"], "line-width": 1.5, "line-opacity": 0.45, "line-dasharray": [2, 3] } });
      L({ id: "l-cones", type: "symbol", source: SRC, filter: isLine("cones"), layout: { "symbol-placement": "line", "symbol-spacing": 18, "icon-image": P + "g-cone", "icon-size": metres(0.9, 0.14, 0, 64), "icon-allow-overlap": true, "icon-ignore-placement": true, "icon-rotation-alignment": "viewport" } });
      for (const [key, glyph] of [["ped", "g-walk"], ["cycle", "g-bike"]]) {
        L({ id: `l-${key}`, type: "line", source: SRC, filter: isLine(key), layout: { "line-cap": "butt" }, paint: { "line-color": ["get", "color"], "line-width": metres(W(1.2), 3), "line-dasharray": key === "ped" ? [1.6, 1] : [3, 1.2], "line-opacity": OP } });
        L({ id: `l-${key}-icon`, type: "symbol", source: SRC, filter: isLine(key), layout: { "symbol-placement": "line", "symbol-spacing": 160, "icon-image": P + glyph, "icon-size": metres(2.2, 0.2, 0, 64), "icon-allow-overlap": true, "icon-rotation-alignment": "viewport" } });
      }
      L({ id: "l-leader", type: "line", source: SRC, filter: isLine("leader"), paint: { "line-color": ["get", "color"], "line-width": metres(W(0.15), 1.6) } });
      L({ id: "l-imported", type: "line", source: SRC, filter: isLine("imported"), paint: { "line-color": ["get", "color"], "line-width": metres(W(0.2), 1.6) } });
      // ---- derived: arrowheads, lights, the crane, area words
      L({ id: "d-icons", type: "symbol", source: DRV, filter: ["in", ["get", "d"], ["literal", ["head", "headw", "lights", "cranec"]]],
        layout: { "icon-image": ["match", ["get", "d"], "head", P + "g-head", "headw", P + "g-headw", "lights", P + "g-lights", P + "s-mobilecrane"],
          "icon-size": metres(["coalesce", ["get", "sz"], 6], 0.22, 0, 64), "icon-rotate": ["coalesce", ["get", "rot"], 0],
          "icon-rotation-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true } });
      L({ id: "d-alabel", type: "symbol", source: DRV, minzoom: WORDS_Z, filter: ["==", ["get", "d"], "alabel"],
        layout: { "text-field": ["get", "text"], "text-font": ["DIN Pro Bold", "Arial Unicode MS Bold"], "text-size": metres(["get", "size"], 10), "text-allow-overlap": true, "text-ignore-placement": true, "text-rotation-alignment": "map", "text-letter-spacing": 0.06 },
        paint: { "text-color": ["get", "color"], "text-halo-color": "#FFFFFF", "text-halo-width": 1.6 } });
      // ---- symbols and words
      L({ id: "s-icons", type: "symbol", source: SRC, filter: ["==", ["get", "style"], "sym"],
        layout: { "icon-image": ["concat", P + "s-", ["get", "sym"]], "icon-size": metres(["coalesce", ["get", "size"], 3], 0.3, 0, 64), "icon-rotate": ["coalesce", ["get", "rot"], 0],
          "icon-rotation-alignment": "map", "icon-pitch-alignment": "map", "icon-allow-overlap": true, "icon-ignore-placement": true, "symbol-sort-key": ["get", "z"],
          "text-field": ["step", ["zoom"], "", WORDS_Z, ["coalesce", ["get", "label"], ""]], "text-font": ["DIN Pro Bold", "Arial Unicode MS Bold"], "text-size": metres(1.4, 10), "text-anchor": "top",
          "text-offset": [0, 1.4], "text-allow-overlap": true, "text-ignore-placement": true },
        paint: { "text-color": "#111827", "text-halo-color": "#FFFFFF", "text-halo-width": 1.6 } });
      for (const bold of [true, false]) {
        L({ id: bold ? "t-bold" : "t-reg", type: "symbol", source: SRC, minzoom: WORDS_Z, filter: ["all", ["==", ["get", "style"], "text"], bold ? ["==", ["get", "bold"], true] : ["!=", ["get", "bold"], true]],
          layout: { "text-field": ["get", "text"], "text-font": bold ? ["DIN Pro Bold", "Arial Unicode MS Bold"] : ["DIN Pro Regular", "Arial Unicode MS Regular"],
            "text-size": metres(["coalesce", ["get", "size"], 2.2], 9), "text-rotate": ["coalesce", ["get", "rot"], 0], "text-rotation-alignment": "map", "text-pitch-alignment": "map",
            "text-allow-overlap": true, "text-ignore-placement": true, "text-max-width": 40, "text-line-height": 1.15, "symbol-sort-key": ["get", "z"] },
          paint: { "text-color": ["coalesce", ["get", "color"], "#111827"], "text-halo-color": ["coalesce", ["get", "halo_color"], "#FFFFFF"], "text-halo-width": ["case", ["==", ["get", "halo"], true], 1.8, 0], "text-halo-blur": 0.2 } });
      }
      if (opts.onAdded) opts.onAdded(ids.slice());
    }

    function prepare(list) {
      const feats = [], drv = [];
      for (const f0 of list) {
        if (!f0 || !f0.geometry) continue;
        const p = Object.assign({}, f0.properties || {});
        const st = p.style;
        const kind = st === "sym" ? "sym" : st === "text" ? "text" : AREAS[st] ? "area" : LINES[st] ? "line" : null;
        if (!kind) continue;
        const c = centroid(f0.geometry);
        p._m = 1 / Math.cos(c[1] * Math.PI / 180);
        p.z = p.z || 0;
        if (kind === "line") p.color = p.color || LINES[st].color;
        if (kind === "area") {
          const s = AREAS[st];
          p.fill = p.fill || s.fill; p.color = p.color || s.color; p.outline = p.outline || s.outline;
          if (p.opacity == null) p.opacity = s.opacity;
          if (p.fill !== "solid" && p.fill !== "none") p.pat = pattern(p.fill, p.color);
          let label = p.text == null ? s.text : p.text;
          if (st === "crane_radius" && f0.geometry.type === "Polygon") {
            const ring = f0.geometry.coordinates[0], r = Math.sqrt(areaM2(ring) / Math.PI);
            drv.push(pt(c, { d: "cranec", _m: p._m }));
            drv.push(pt(ring[Math.floor(ring.length / 8)], { d: "alabel", text: `R ${Math.round(r)} m`, color: p.color, size: 2, _m: p._m }));
            label = "";
          }
          if (label) drv.push(pt(c, { d: "alabel", text: label, color: darker(p.color), size: 2.4, _m: p._m }));
        }
        if (kind === "line" && f0.geometry.coordinates.length > 1) {
          const cs = f0.geometry.coordinates, n = cs.length;
          const endRot = bearing(cs[n - 2], cs[n - 1]) - 90, startRot = bearing(cs[1], cs[0]) - 90;
          if (st === "oneway" || st === "leader") drv.push(pt(cs[n - 1], { d: "head", rot: endRot, sz: st === "leader" ? 1.6 : 3, _m: p._m }));
          if (st === "twoway") { drv.push(pt(cs[n - 1], { d: "headw", rot: endRot, sz: 4, _m: p._m })); drv.push(pt(cs[0], { d: "headw", rot: startRot, sz: 4, _m: p._m })); }
          if (st === "lights") { drv.push(pt(cs[0], { d: "lights", rot: 0, sz: 3.2, _m: p._m })); drv.push(pt(cs[n - 1], { d: "lights", rot: 0, sz: 3.2, _m: p._m })); }
        }
        if (kind === "sym" && !SYMS[p.sym]) continue;
        feats.push({ type: "Feature", geometry: f0.geometry, properties: p });
      }
      return [{ type: "FeatureCollection", features: feats }, { type: "FeatureCollection", features: drv }];
    }

    let raw = [];
    // a page that closes may call these after its map is gone (Mapbox throws from getSource / getLayer then)
    const src = (id) => { try { return map.getSource(id); } catch (e) { return null; } };
    const lyr = (id) => { try { return map.getLayer(id); } catch (e) { return null; } };
    function setData(fc) {
      const list = Array.isArray(fc) ? fc : ((fc && fc.features) || []);
      raw = list;
      [data, derived] = prepare(list);
      const s = src(SRC), d = src(DRV);
      if (s) s.setData(data);
      if (d) d.setData(derived);
    }
    function setVisible(on) {
      visible = !!on;
      for (const id of ids) if (lyr(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
      // data set while hidden can leave the old tiles on show (GL JS v3 does not reload a source none of whose
      // layers is visible): send it again as the layers come back
      if (visible) { const s = src(SRC), d = src(DRV); if (s) s.setData(data); if (d) d.setData(derived); }
    }
    function remove() {
      for (const id of ids.slice().reverse()) if (lyr(id)) map.removeLayer(id);
      for (const s of [SRC, DRV]) if (src(s)) map.removeSource(s);
      ids.length = 0;
    }
    // after map.setStyle: the layers, sources and pictures are gone; put them back with the last data
    function reinstall() {
      if (!pics) return;
      remove();
      addAll();
      setData(raw);   // the pattern pictures are made again for the new style (from the features as sent)
    }
    return { ready, setData, setVisible, remove, reinstall, layerIds: () => ids.slice(), prefix: P, count: () => data.features.length };
  }

  window.WSLayouts = { install, metres, centroid, areaM2, bearing, geo, WORDS_Z };
})();

/*
 * look_check.js — bundle E (W5 + W16), 13 Oct 2026. NOT part of the default suite: it runs IN A BROWSER, on the
 * Dashboard of a running app, pasted into the console (or a browser tool's javascript call). It measures what the
 * static harnesses cannot: chart boxes laid out, legends placed, no horizontal scroll, the accent tokens applied.
 *
 *     await (async () => { <this file> ; return await lookCheck({ open: true }); })()
 *
 * Returns one object; the session notes record the result of each run (size × look × accent).
 */
async function lookCheck(opts) {
  const o = opts || {};
  const frames = (n) => new Promise(r => { const f = () => (n-- <= 0 ? r() : requestAnimationFrame(f)); f(); });
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const visible = (el) => !el.closest("details:not([open])") && !el.closest("[hidden]") && !!(el.offsetParent || el.getClientRects().length);   // a closed <details> still lays out in Chrome
  const C = window.Chart;
  const closedBefore = [...document.querySelectorAll("details.dash-more:not([open])")];
  const builtWhileClosed = closedBefore.reduce((n, d) => n + [...d.querySelectorAll("[data-chart-box] canvas")].filter(c => C && C.getChart(c)).length, 0);
  if (o.open) { closedBefore.forEach(d => { d.open = true; }); await frames(2); await sleep(o.wait || 400); }
  const boxes = [...document.querySelectorAll("[data-chart-box]")].filter(visible).map(b => {
    const c = b.querySelector("canvas"); const ch = C && c ? C.getChart(c) : null;
    const br = b.getBoundingClientRect(), cr = c ? c.getBoundingClientRect() : { width: 0, height: 0 };
    const r = { title: ((b.parentElement && b.parentElement.querySelector(".chart-title")) || {}).textContent || "", w: Math.round(br.width), h: Math.round(br.height),
      built: !!ch, fits: Math.abs(cr.width - br.width) <= 1 && Math.abs(cr.height - br.height) <= 1, dpr: ch ? ch.currentDevicePixelRatio : null, legend: "none" };
    if (ch && ch.legend && ch.legend.options && ch.legend.options.display !== false && ch.legend.legendItems && ch.legend.legendItems.length) {
      const L = ch.legend, A = ch.chartArea;
      const inside = L.left >= -0.5 && L.top >= -0.5 && L.right <= ch.width + 0.5 && L.bottom <= ch.height + 0.5;
      const off = L.bottom <= A.top + 0.5 || L.top >= A.bottom - 0.5 || L.right <= A.left + 0.5 || L.left >= A.right - 0.5;
      r.legend = (inside && off ? "ok" : "BAD") + ":" + L.options.position;
    }
    r.ok = r.w > 0 && r.h > 0 && r.built && r.fits && (r.dpr == null || r.dpr <= 2) && !/^BAD/.test(r.legend);
    return r;
  });
  const main = document.querySelector("main");
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const out = {
    vw: innerWidth, vh: innerHeight, theme: document.documentElement.getAttribute("data-theme"), accent: document.documentElement.getAttribute("data-accent"),
    pageHScroll: document.documentElement.scrollWidth > innerWidth, mainHScroll: main ? main.scrollWidth > main.clientWidth + 1 : null,
    builtWhileClosed, boxes: boxes.length, allOk: boxes.every(b => b.ok), bad: boxes.filter(b => !b.ok),
    minH: boxes.length ? Math.min(...boxes.map(b => b.h)) : null, maxDpr: Math.max(0, ...boxes.map(b => b.dpr || 0)),
    legends: boxes.map(b => b.legend).filter(l => l !== "none"),
    railW: document.querySelector("aside.rail") ? Math.round(document.querySelector("aside.rail").getBoundingClientRect().width) : null,
    cardMinW: Math.round(Math.min(...[...document.querySelectorAll(".dash-card")].filter(visible).map(c => c.getBoundingClientRect().width))),
    tokens: { action: css("--action"), navy: css("--navy"), c1: css("--chart-1"), c2: css("--chart-2"), c3: css("--chart-3"), c4: css("--chart-4"), c5: css("--chart-5"),
              green: css("--green"), gold: css("--gold"), red: css("--red") },
  };
  if (o.fill) {   // the big screen, Charts section alone: how much of the height under the wall bar the charts take
    const sec = document.querySelector('[data-wall-section="Charts"]'), bar = document.querySelector(".dash-wallbar");
    if (sec && bar) { const top = bar.getBoundingClientRect().bottom, grid = sec.querySelector(".wall-charts").getBoundingClientRect();
      out.fillPct = Math.round(grid.height * 100 / (innerHeight - top)); }
  }
  return out;
}

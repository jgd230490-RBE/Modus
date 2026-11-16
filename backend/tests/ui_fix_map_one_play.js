/* ui_fix_map_one_play.js — 12 Nov 2026, branch claude/map-one-play: John's "option b now" on the mockup
 * notes\map-one-play-mockup-1112 (card B). Since the public map opens on this month (batch 7) the timeline bar is on screen
 * from the start, and a desk window showed TWO filled Play buttons (the Control Panel's "▶ Play forecast timeline" and the
 * bar's ▶; the full UI audit's filled-primaries warning on e038b56). Now, while the bar is on screen, the panel's button is
 * plain (surface, ink, a thin inset edge) and the bar's ▶ is the one filled Play; once the bar is closed it is filled again.
 * It still opens the bar and plays; no words change. Source checks on map/index.html plus a sandbox of syncTimelineFoot;
 * no browser (ui_audit.js is that). Every check of the change fails on the code before this branch (on 36aa6c8: 8 passed,
 * 6 failed; the 8 guard what stays).
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
function fnSrc(name) {
  let i = html.indexOf("    function " + name + "(");
  if (i < 0) return "";
  const j = html.indexOf("\n    function ", i + 10);
  return html.slice(i, j > 0 ? j : i + 6000);
}

console.log("B · the panel's Play is plain while the bar is on screen");
{
  const rule = (html.match(/body\.tl-bar-on \.fc-box #tl-open\{([^}]*)\}/) || [])[1] || "";
  ok("⭐ a rule makes the panel's Play plain while the bar is on screen", !!rule, rule);
  ok("⭐ plain = the surface, the ink, a thin inset edge, normal weight (the btn-ghost look)",
     /background:var\(--surface\)/.test(rule) && /color:var\(--ink\)/.test(rule)
     && /box-shadow:inset 0 0 0 1px var\(--ctl-line\)/.test(rule) && /font-weight:500/.test(rule), rule);
  ok("it keeps its height: no border is added (an inset edge instead)", rule && !/border/.test(rule), rule);
  ok("a hover for the plain button", /body\.tl-bar-on \.fc-box #tl-open:hover\{ background:var\(--surface-2\); \}/.test(html));
  ok("no other rule paints the panel's Play (the filled look comes from .btn alone)",
     html.split("\n").filter(l => l.includes("#tl-open") && l.includes("background") && !l.includes("body.tl-bar-on")).length === 0);
}

console.log("B · the class follows the bar, and only the bar");
{
  const src = fnSrc("syncTimelineFoot");
  ok("⭐ syncTimelineFoot sets tl-bar-on from the bar's own display",
     /document\.body\.classList\.toggle\('tl-bar-on', !!\(bar && bar\.style\.display === 'flex'\)\);/.test(src), src.slice(0, 600));
  const mk = () => {
    const cl = new Set();
    return { bar: { style: { display: "none" }, offsetHeight: 60 }, strip: { offsetHeight: 0 },
             body: { classList: { toggle: (k, on) => (on ? cl.add(k) : cl.delete(k)), has: k => cl.has(k) } }, foot: null };
  };
  const st = mk();
  const ctx = { Math, document: { getElementById: id => (id === "timeline-bar" ? st.bar : id === "t-strip" ? st.strip : null),
                                  body: st.body, documentElement: { style: { setProperty: (k, v) => { st.foot = v; } } } } };
  vm.createContext(ctx);
  let err = "";
  try { vm.runInContext(src + "\nthis.syncTimelineFoot = syncTimelineFoot;", ctx); } catch (x) { err = String(x); }
  if (typeof ctx.syncTimelineFoot === "function") {
    st.bar.style.display = "flex"; ctx.syncTimelineFoot();
    const on = st.body.classList.has("tl-bar-on");
    st.bar.style.display = "none"; ctx.syncTimelineFoot();
    const off = !st.body.classList.has("tl-bar-on");
    st.strip.offsetHeight = 50; ctx.syncTimelineFoot();
    const stripOnly = !st.body.classList.has("tl-bar-on") && st.body.classList.has("timeline-on");
    ok("⭐ bar shown → plain; bar closed → filled again", on && off, { on, off });
    ok("the tablet strip alone does not count (the panel's Play is the strip's only partner there)", stripOnly);
  } else ok("syncTimelineFoot runs in a sandbox", false, err);
  const paths = ["openTimeline", "closeTimeline", "showTimelineBar", "hideTimelineBar"];
  const bad = paths.filter(n => { const s = fnSrc(n); return !/bar\.style\.display\s*=\s*'(flex|none)'/.test(s) || !s.includes("syncTimelineFoot()"); });
  ok("⭐ every path that shows or hides the bar calls syncTimelineFoot (open, close, the × and a month bringing it back)", bad.length === 0, bad);
}

console.log("Kept");
{
  ok("the panel's button: same words, still opens the bar and plays",
     html.includes('<button type="button" class="btn" id="tl-open" onclick="startTimeline()">▶ Play forecast timeline</button>'));
  ok("the bar's Play keeps its orange fill",
     html.includes("#timeline-bar #tl-play{ width:48px; background:#C2410C; border-color:#C2410C; color:#fff; font-size:17px; font-weight:700; }"));
  ok("the grey 'loading' Play still covers the panel's button (A-F7)",
     html.includes("const PLAY_IDS = ['tl-open', 'tl-play', 'm-play', 'm-full-play'];")
     && /\.play-wait, \.play-wait:hover\{ opacity:\.45; cursor:progress; filter:grayscale\(1\); \}/.test(html));
  ok("the tour's Press Play tip still points at the bar's Play, the panel's as the fallback", /anchor: "tl-play", alt: "tl-open"/.test(html));
  ok("the filled look itself is unchanged (.btn on the action colour)",
     html.includes(".btn { width:100%; border:none; border-radius:6px; padding:8px; font-size:14px; font-weight:600; cursor:pointer; background:var(--action); color:var(--action-fg); }"));
}

console.log();
fail.forEach(f => console.log("  FAIL: " + f));
console.log(`\n${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);

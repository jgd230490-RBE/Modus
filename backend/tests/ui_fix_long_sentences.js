/*
 * ui_fix_long_sentences.js — UX programme decision U5 / Q10 (10 Nov 2026), branch claude/ui-fix-long-sentences.
 *
 * The five sentences of more than 25 words still on staff screens (Dashboard busiest hour, Submit's other lines, Data → Routes' key,
 * Config → Vehicles' note, Users' shared-codes notice) are now a few words or a key on the screen, with the explanation in an "i" box
 * of at most 30 words that links to its user-guide section; the detail is in the guide. InfoTip takes an optional `guide`.
 * Its own file (the wave rule). Source checks only: no React needed.
 */
const fs = require("fs");
const path = require("path");
let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };
const ROOT = path.resolve(__dirname, "..", "..");
const read = (...p) => fs.readFileSync(path.join(ROOT, ...p), "utf8").replace(/\r\n?/g, "\n");
const html = read("frontend", "index.html");
const guide = read("frontend", "help", "index.html");
const tech = read("frontend", "help", "technical", "index.html");
const words = (t) => t.replace(/<[^>]+>/g, " ").split(/\s+/).filter(w => /[A-Za-z0-9]/.test(w)).length;

// ---- InfoTip: the optional guide link
ok("InfoTip takes an optional guide prop and links it (the prop wins over the entry's own)",
   html.includes("function InfoTip({ id, label, value, guide }){") && html.includes("{(guide || e.guide) && <a href={GUIDE_URL(guide || e.guide)}"));

// ---- the six new boxes: at most 30 words, each with a guide anchor that exists in the user guide
const boxes = { "dash.busiest": "ug-gate-busiest", "submit.siblings": "ug-submit-siblings", "routes.legs": "ug-routes-legs",
  "cfg.veh.english": "ug-config-vehicles", "cfg.veh.minutes": "ug-config-vehicles", "cfg.veh.euro": "ug-config-vehicles" };
for (const [id, anchor] of Object.entries(boxes)) {
  const m = html.match(new RegExp('"' + id.replace(".", "\.") + '": \{ title: "[^"]*", text: "([^"]*)", guide: "([^"]*)"'));
  ok(`"i" box ${id} exists with its text and guide`, !!m);
  if (!m) continue;
  ok(`...${id}: ${words(m[1])} words (at most 30)`, words(m[1]) <= 30);
  ok(`...${id} links to ${anchor}, which exists in the user guide`, m[2] === anchor && guide.includes(`id="${anchor}"`));
}

// ---- the five sentences are gone from the screens
const gone = ["Different disciplines on one route are expected", "Each route has a laden leg out and an empty leg back",
  "The English name is what every screen shows", "The shared codes still work on this site", "They can be turned off once everyone has a login"];
for (const g of gone) ok(`gone from the screens: "${g}"`, !html.includes(g));

// ---- the server sends the specifics the box prints
const sim = read("backend", "sim.py"), mainpy = read("backend", "main.py");
ok("the server sends busiest_detail (the facts of the note, no lead-in) and busiest_loads, and the note itself is unchanged for other readers",
   sim.includes('"detail": detail') && mainpy.includes('out["busiest_detail"] = b.get("detail")') && mainpy.includes('out["busiest_loads"] = b.get("loads")') && sim.includes('note = (f"Busiest hour: the lorries arriving in the busiest clock hour'));

// ---- each screen's new words
ok("Dashboard: the panel's busiest-hour note reads 'Busiest hour · N loads a day' with a box that prints the server's specifics (busiest_detail)",
   html.includes('Busiest hour{ga.busiest_loads != null ? ` · ${grp(ga.busiest_loads)} loads a day` : ""}<InfoTip id="dash.busiest" value={ga.busiest_detail} />') && !html.includes("{ga.busiest_note}</div>"));
ok("Submit: the other-lines note keeps the list and puts the advice in a box", html.includes('<InfoTip id="submit.siblings" />') && html.includes("This route already carries {siblings.length} other forecast line"));
ok("Routes: the key is two short chips' worth of words plus a box", html.includes('Green chip: both legs. <span className="font-semibold">Amber ↦</span>: out only.<InfoTip id="routes.legs" />'));
ok("Config → Vehicles: no note under the table; the English, load / unload and Euro class headers carry the boxes",
   !html.includes("Blank load or unload minutes use the Planning defaults") && html.includes('<InfoTip id="cfg.veh.english" />') && html.includes('<InfoTip id="cfg.veh.minutes" />') && html.includes('<InfoTip id="cfg.veh.euro" />'));
ok("Users: 'Shared codes are still on.' and a link to the guide, still a note with the gold border",
   html.includes("<b>Shared codes are still on.</b>") && html.includes('GUIDE_URL("ug-shared-codes")') && html.includes('role="note" style={{ borderColor: "var(--gold)" }}'));

// ---- every fact is somewhere a person can find it
ok("guide: Busiest hour (spread over open hours, no-delivery bands off, no pour)", /Busiest hour<\/strong> gives the lorries arriving in the busiest clock hour[^<]*the whole loads are spread evenly over the gate&#39;s open hours[^<]*no-delivery bands[^<]*no concrete pour/.test(guide));
ok("guide: the route legs and the green / amber chip, and the row's cycle figures", /id="ug-routes-legs"[^>]*>[\s\S]*loaded leg out and an empty leg back[\s\S]*green vehicle chip[\s\S]*outbound leg only[\s\S]*cycle figures/i.test(guide));
ok("guide: Vehicles — the English name, blank minutes use the Planning defaults, Euro class is the CLP charts only (no carbon figure)",
   /id="ug-config-vehicles"[\s\S]{0,300}English<\/strong> name is the one every screen shows/.test(guide) && guide.includes("left blank, a vehicle uses the Planning defaults") && /only by the CLP monitoring charts[^<]*changes no carbon figure/.test(guide));
ok("guide: the shared codes (who can sign in with one, how it is recorded, how they end) and the other-lines note's reason", guide.includes('id="ug-shared-codes"') && /sign in without a login of their own, and what they do is recorded only as that code/.test(guide) && /Other lines on this route<\/strong>[^]*?counted twice/.test(guide));
ok("technical guide: the shared codes' removal is findable (t-shared-codes)", tech.includes('id="t-shared-codes"'));

console.log(`ui_fix_long_sentences.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }

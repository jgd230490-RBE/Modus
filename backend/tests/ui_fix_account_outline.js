/*
 * ui_fix_account_outline.js — 11 Nov 2026, card D-F4 (John's yes), branch claude/account-outline-add.
 *
 *   Account (the Look-ahead's last-week view) drew "Add to this week" as a FILLED button on the accent on every short line:
 *   three filled primaries on one page on live (rule R2: one filled primary a page). It is now an outline button (btn-sec
 *   btn-sm): the same words, click, title and disabled rule. Saving a box when it is left is unchanged.
 *
 * Its own file (BUILD.md rule 3). Source checks; the rendered row is pinned in render_frontend.js.
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");

const at = html.indexOf("<button onClick={() => doSpread(r)}");
const btn = at > 0 ? html.slice(at, html.indexOf("</button>", at) + 9) : "";

ok("D-F4: one 'Add to this week' button on the page source, the doSpread one", btn.length > 0 && (html.match(/>Add to this week<\/button>/g) || []).length === 1);
ok("🔴 D-F4: 'Add to this week' is an outline button (btn-sec btn-sm), never btn-pri",
   btn.includes('className="btn-sec btn-sm disabled:opacity-40"') && !btn.includes("btn-pri"), btn.slice(0, 160));
ok("🔴 D-F4: ...with no accent fill and no white text of its own",
   btn.length > 0 && !btn.includes("var(--action)") && !btn.includes("text-white"));
ok("D-F4: the same words, click, title and disabled rule",
   btn.includes("disabled={!!busy}") && btn.includes(">Add to this week</button>")
   && btn.includes("title={`Add ${grp(r.remaining_short, 1)} ${unitLbl(r.unit)} to this week, divided over its remaining weekdays. Refused if that week is confirmed.`}"));
ok("D-F4: the outline class is the app's own (a surface fill and a grey border), and btn-sm still sets the small size",
   /\.btn-sec\{[^}]*background:var\(--surface\);color:var\(--ink\);border:1px solid var\(--grey\);/.test(html) && /\.btn-sm\{padding:4px 10px;font-size:13px;\}/.test(html));

console.log(`ui_fix_account_outline.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }

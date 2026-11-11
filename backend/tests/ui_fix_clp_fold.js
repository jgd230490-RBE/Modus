/*
 * ui_fix_clp_fold.js — 11 Nov 2026, card D-F6 (John's yes), branch claude/clp-fold-stays.
 *
 *   CLP monitoring, about four screens down the Dashboard, closed whenever you left the Dashboard. It now keeps its
 *   place for the session (CLP_FOLD: open + month), opens there again, reads the month again and scrolls back to itself
 *   once; sign-out clears it. The behaviour is driven in dom_frontend.js (the D-F6 block after the CLP section);
 *   these are the source checks.
 */
const fs = require("fs");
const path = require("path");

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const at = html.indexOf("function ClpMonitoring({ months, initial }){");
const body = at > 0 ? html.slice(at, html.indexOf("\n}\n", at)) : "";
const so = html.indexOf("const signOut = () => {"), soBody = so > 0 ? html.slice(so, html.indexOf("};", so)) : "";

ok("🔴 D-F6: one session memory for the fold (open + month), declared just above ClpMonitoring",
   (html.match(/var CLP_FOLD = \{ open: false, month: null \};/g) || []).length === 1
   && html.indexOf("var CLP_FOLD = ") < at && at - html.indexOf("var CLP_FOLD = ") < 200);
ok("🔴 D-F6: the fold starts from it (open, then month) unless the page hands it a reply of its own",
   body.includes("useState(() => !!initial || CLP_FOLD.open)") && body.includes("(initial && initial.month) || CLP_FOLD.month || gaMonthToday(months)"));
ok("D-F6: every change of open or month is written back", body.includes("useEffect(() => { CLP_FOLD.open = open; CLP_FOLD.month = month; }, [open, month]);"));
ok("D-F6: it scrolls back once, after its figures are in, only when it was open when the Dashboard was left",
   body.includes("const backTo = useRef(!initial && CLP_FOLD.open);") && body.includes("if(!backTo.current || !data) return;")
   && body.includes("backTo.current = false;") && body.includes('el.scrollIntoView({ block: "start" })') && body.includes("<details ref={foldEl}"));
ok("D-F6: no stored figures: coming back reads the month again (the read is not skipped for a remembered month)",
   !/CLP_FOLD\.data/.test(html) && body.includes("if(data && data.month === month) return;"));
ok("🔴 D-F6: sign-out clears it, so the next person starts with the fold closed",
   soBody.includes("CLP_FOLD.open = false; CLP_FOLD.month = null;"));
ok("D-F6: the fold's memory is not kept in the browser's storage (it ends with the session in this tab)",
   !/(local|session)Storage[^\n]*CLP_FOLD|CLP_FOLD[^\n]*(local|session)Storage/.test(html));

console.log(`ui_fix_clp_fold.js: ${pass} passed, ${fail.length} failed`);
if (fail.length) { fail.forEach(f => console.log("  FAIL: " + f)); process.exit(1); }

// 12 Nov 2026 (batch 5): on a tablet card (.tab-cards, 768-1024 px) a cell's second line (a span with Tailwind's `block`)
// keeps its own line, as at a desk. PR #258's chip rule (td>span inline-block) outweighed `.block`, so CLP documents'
// "Issue 2 · 2 Nov 2026" ran into the approver's name, and #265's "Plan changed since Issue N" sat beside the status chip.
const fs = require("fs"), path = require("path");
const html = fs.readFileSync(path.join(__dirname, "..", "..", "frontend", "index.html"), "utf8").replace(/\r\n/g, "\n");
let pass = 0, fail = 0;
const ok = (name, cond, info) => { if (cond) { pass++; console.log("  ✓ " + name); } else { fail++; console.log("  ✗ " + name + (info ? " — " + info : "")); } };
const a = html.indexOf("TABLET-CARDS-START"), b = html.indexOf("TABLET-CARDS-END");
const block = a >= 0 && b > a ? html.slice(a, b) : "";
ok("the tablet card rules are found", block.length > 0);
ok("🔴 the chip rule (td>span inline-block) leaves a `block` span alone",
   /\.tab-cards>tbody>tr>td>span:not\(\.block\)\{display:inline-block;/.test(block) && !/\.tab-cards>tbody>tr>td>span\{display:inline-block/.test(block));
ok("🔴 a `block` span in a card cell is a line of its own",
   /\.tab-cards>tbody>tr>td>span\.block\{display:block;/.test(block));
// the CLP documents row's second lines are `block` spans in direct td children (what the rule must reach)
const row = html.slice(html.indexOf('data-clp-row={c.id}'), html.indexOf('data-clp-row={c.id}') + 4000);
ok("CLP documents: the approver's name under Last issue is a `block` span in its cell",
   /data-label="Last issue">[^\n]*<span className="block text-\[12px\] text-slate-500">\{c\.last_issue\.by\}<\/span>/.test(row));
ok("CLP documents: the status line and \"Plan changed since Issue N\" are `block` spans",
   /\{statusLine\(c\) && <span className="block /.test(row) && /data-clp-changed=\{c\.id\}/.test(html) && /<span className="block text-\[12px\] text-slate-500" data-clp-changed/.test(html));
console.log(`ui_fix_tab_cards_lines.js: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);

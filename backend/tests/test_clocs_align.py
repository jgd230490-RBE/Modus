"""
CLOCS alignment wording, 10 Nov 2026 (branch claude/clocs-align; John's yes to the mockup, "All as recommended").

What is asserted, each against the text before (every check fails on it):
  F1  the landing page names the CLOCS clauses Wayscope supports (5.1, 5.2, 5.6, 5.13), never "5.1–5.5";
  F2  the CLOCS reader card: "signing the CLP" stays with the reader, never "the CLP itself";
  F4  the Appendix L source names 85 % as Wayscope's planning level; the Route analysis and the collision evidence
      sheet say once whose search distances they are;
  F6  a figure that counts lorry visits says "lorry visits": Appendix J, the CLP monitoring charts 4 and 5 (and their
      "i" titles and the user guide), the collision evidence sheet and its XLSX; the quoted clause "5.1a type of vehicle
      movements" stays;
  F9  the technical guide's T9 heading has no clause label, its anchor stays;
  F12 the evidence box is titled "For the route risk assessment (CLOCS Standard v5, 5.1a)".
F3, F5, F11 and the CLP Word file's F4 lines are asserted on the built file in test_clp_doc / test_clp_records.

WHAT THIS DOES NOT PROVE
------------------------
  * Source level only: the PDFs and the XLSX are built in test_collisions / test_route_analysis, not here.
  * How the landing page and the guides look (the UI audit's compare run).

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_clocs_align.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  ok  ", label)
    else:
        FAIL.append(label + (f"  [{extra}]" if extra else ""))
        print("  FAIL", label, extra)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


LAND = read("landing", "index.html")
UG = read("frontend", "help", "index.html")
TG = read("frontend", "help", "technical", "index.html")
APP = read("frontend", "index.html")
CLP = read("backend", "clp.py")
APX = read("backend", "clp_doc_appendices_render.py")
EXP = read("backend", "export.py")
RA = read("backend", "route_analysis_render.py")

print("F1 / F2 · the landing page")
ok("🔴 F1 the landing page never says '5.1–5.5'", "5.1–5.5" not in LAND and "5.1&ndash;5.5" not in LAND)
ok("⭐ F1 the list names 5.1 risk assessment, 5.2 CLPs, 5.6 vehicle routing, 5.13 community engagement",
   "<li><b>The CLOCS Standard:</b> principal contractor requirements 5.1 risk assessment, 5.2 Construction Logistics "
   "Plans, 5.6 vehicle routing and 5.13 community engagement</li>" in LAND)
ok("⭐ F1 the Sources line: 5.1, 5.2, 5.6 and 5.13; the Standard stays unversioned",
   "Construction Logistics Plans, routes and the community: the CLOCS Standard, principal contractor requirements "
   "5.1, 5.2, 5.6 and 5.13." in LAND and not re.search(r"CLOCS Standard v\d", LAND))
ok("...5.11 monitoring is not claimed yet", "5.11" not in LAND)
ok("🔴 F2 the CLOCS reader keeps signing the CLP, never 'the CLP itself'",
   "<b>What stays with you:</b> signing the CLP, gate checks, traffic marshals and your delivery management system." in LAND
   and "the CLP itself" not in LAND)

print("F4 · whose level, whose distances")
ok("🔴 F4 Appendix L: 85 % is Wayscope's planning level, not a published standard",
   "from 85 % of capacity (Wayscope's planning level, not a published standard)" in APX)
ok("🔴 F4 the evidence sheet: '250 m and 100 m are Wayscope's search distances, not a CLOCS figure.', said once",
   'SEARCH_WORDS_EVIDENCE = "250 m and 100 m are Wayscope\'s search distances, not a CLOCS figure."' in EXP
   and EXP.count("+ SEARCH_WORDS_EVIDENCE") == 1)
ok("🔴 F4 the Route analysis: the summary's 250 m and the community page's distances are Wayscope's",
   'SEARCH_WORDS = "250 m is Wayscope\'s search distance, not a CLOCS figure."' in RA
   and '" " + SEARCH_WORDS if any(R["summary"].get("schools_health") is not None for R in routes)' in RA
   and "Wayscope's search distance{'s' if len(dists) > 1 else ''}" in RA)

print("F6 · lorry visits, where the figure counts visits")
ok("🔴 F6 Appendix J: 'Lorry visits a day', a visit counted once in each council its loaded leg enters",
   '"Lorry visits a day"' in APX and '"Movements a day"' not in APX and "A movement is one loaded lorry" not in APX
   and "One lorry visit (in and out) counts once in each council area its loaded leg enters." in APX
   and "adds distance, not a visit." in APX)
ok("🔴 F6 CLP monitoring charts 4 and 5: 'Lorry visits by vehicle type / by Euro class'; one load = one lorry visit",
   '"title": "Lorry visits by vehicle type"' in CLP and '"title": "Lorry visits by Euro class"' in CLP
   and "Movements by vehicle type" not in CLP and "Movements by Euro class" not in CLP
   and "(one load = one lorry visit)" in CLP and "one load = one movement" not in CLP)
ok("🔴 F6 their 'i' titles on the Dashboard and the user guide's list say the same",
   '"clp.vehicle_types": { title: "Lorry visits by vehicle type"' in APP and '"clp.euro_class": { title: "Lorry visits by Euro class"' in APP
   and "Movements by vehicle type" not in APP and "Movements by Euro class" not in APP
   and "<strong>Lorry visits by vehicle type</strong> and <strong>by Euro class</strong>" in UG
   and "Movements by vehicle type" not in UG)
ok("...the council chart keeps the organisation's own count (counting.words), untouched",
   "Movements and lorry distance by council" in UG)
_ev = EXP[EXP.index("# 10 Nov 2026 (F4): the evidence sheet"):]
ok("🔴 F6 the collision evidence sheet and its XLSX say lorry visits, never lorry movements",
   "lorry movements a day" not in _ev.lower() and "one movement being" not in _ev
   and '"Lorry visits a day planned"' in _ev and "plans {pdw} lorry visits a day" in _ev
   and '"Scheme lorry visits a day here"' in _ev and '"Scheme lorry visits a day, lowest"' in _ev
   and '"Scheme lorry visits a day, highest"' in _ev and "how many lorry visits a day at the peak" in _ev
   and "one visit being one load there and back" in _ev)
ok("...the clause row that quotes the Standard keeps its words", "5.1a type of vehicle movements" in EXP)

print("F9 / F12 · labels")
ok("🔴 F9 the technical guide's T9 heading carries no clause label; the anchor stays",
   '<h1 id="t9-collisions">T9 The collision history</h1>' in TG and "(CLOCS v5 C1)</h1>" not in TG)
ok("🔴 F12 the evidence box: 'For the route risk assessment (CLOCS Standard v5, 5.1a)'",
   '"For the route risk assessment (CLOCS Standard v5, 5.1a)"' in EXP and '"For the CLOCS route risk assessment"' not in EXP)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\ntest_clocs_align: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

"""
test_forecast_plan.py — backend/forecast_plan.py, the approved plan by route and month as a table and a CSV.
Wayscope, 12 Nov 2026 (claude/ui-map-forecast-detail-1111, option A2: the public map's "All routes"; the staff Download).

    python backend/tests/test_forecast_plan.py

Pure: no database, no FastAPI. The stand-in is R050 as the demo holds it (29 t a load, 22 working days), the figures the
map's own harness (ui_fix_map_route_story.js, ui_fix_map_all_routes.js) holds the page to, so the file and the screen
are held to one answer. The endpoint itself (staff only) is in smoke_forecast_plan.py.
"""
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import forecast_plan as fp  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


T = {5: 800, 6: 1000, 7: 1200, 8: 1400, 9: 1600, 10: 1600, 11: 1600, 12: 900, 13: 1100, 14: 1300, 15: 38000,
     16: 42000, 17: 38000, 18: 1200, 19: 1000, 20: 800}
lines = {}
for m in range(1, 61):
    lines[m] = []
    if m in T:
        lines[m].append({"route_id": "R050", "material_type": "Earthworks / soil", "qty_t": T[m],
                         "vehicle_loads": round(T[m] / 29, 3)})
    if 13 <= m <= 20:      # R011: two lines a month on one route, two materials
        lines[m].append({"route_id": "R011", "material_type": "Small aggregate", "qty_t": 600, "vehicle_loads": 30})
        lines[m].append({"route_id": "R011", "material_type": "Asphalt", "qty_t": 200, "vehicle_loads": 14})
lines[30] = [{"route_id": "R012", "material_type": "General / imported", "qty_t": 5, "vehicle_loads": 0.25},
             {"route_id": "R099", "material_type": "x", "qty_t": 0, "vehicle_loads": 0},
             {"route_id": "", "material_type": "x", "qty_t": 9, "vehicle_loads": 1}]
NAMES = {"R050": {"origin": "Tilton Viaduct site", "dest": "Wolds Link Inert Landfill"},
         "R011": {"origin": "=Northfield Quarry", "dest": "Melton Compound"}}

tab = fp.table(lines, 60, 22, 2, NAMES)
rows = {r["route_id"]: r for r in tab["rows"]}
ok("⭐ a row a route, in route order; a route with nothing approved and a line with no route are left out",
   [r["route_id"] for r in tab["rows"]] == ["R011", "R012", "R050"], str([r["route_id"] for r in tab["rows"]]))
r50 = rows["R050"]
ok("⭐ R050: 133,500 t in all; Apr 2027 (month 16) is 42,000 t and 132 movements a day; Sep 2026 is 5",
   r50["total_t"] == 133500 and r50["t"][16] == 42000 and fp.count_text(r50["count"][16]) == "132"
   and fp.count_text(r50["count"][9]) == "5" and fp.count_text(r50["peak_count"]) == "132", str(r50["count"].get(16)))
ok("⭐ a route's lines are added together, its materials biggest first",
   rows["R011"]["t"][13] == 800 and abs(rows["R011"]["count"][13] - 44 / 22 * 2) < 1e-9
   and rows["R011"]["materials"] == ["Small aggregate", "Asphalt"])
ok("⭐ the totals row adds the routes: Apr 2027 = R050's 131.66 + R011's 4 = 136 movements a day",
   fp.count_text(tab["total"]["count"][16]) == "136" and tab["total"]["t"][16] == 42800
   and tab["total"]["total_t"] == 133500 + 8 * 800 + 5)
ok("⭐ counting visits (per_visit 1) halves every count and nothing else: Apr 2027 reads 66",
   fp.count_text(fp.table(lines, 60, 22, 1, NAMES)["rows"][2]["count"][16]) == "66"
   and fp.table(lines, 60, 22, 1, NAMES)["rows"][2]["t"][16] == 42000 and fp.table(lines, 60, 22, 1)["per_visit"] == 1)
ok("a count a day is whole, 'under 1' below one, with comma thousands; tonnes are whole",
   fp.count_text(0.02) == "under 1" and fp.count_text(0) == "0" and fp.count_text(1448.3) == "1,448"
   and fp.count_text(131.66) == "132" and fp.tonnes_text(42000.4) == "42,000"
   and fp.count_text(rows["R012"]["count"][30]) == "under 1")
ok("working days can be given per month; a month with none counts nothing a day (no division by zero)",
   fp.count_text(fp.table(lines, 60, {m: (11 if m == 16 else 22) for m in range(1, 61)}, 2)["rows"][2]["count"][16]) == "263"
   and fp.table(lines, 60, 0, 2)["rows"][2]["count"][16] == 0)
ok("month labels: month 1 is Jan 2026, month 16 Apr 2027, month 60 Dec 2030",
   [fp.month_label(m, 2026) for m in (1, 16, 60)] == ["Jan 2026", "Apr 2027", "Dec 2030"])

# ---- the CSV ----
txt = fp.csv_text(tab, "count", 2026)
body = list(csv.reader(io.StringIO(txt.lstrip("﻿"))))
ok("⭐ CSV, movements a day: a byte-order mark, a heading row (Route, From, To, Material, 60 months, Busiest), a row a route, a totals row",
   txt.startswith("﻿") and body[0][:4] == ["Route", "From", "To", "Material"] and body[0][4] == "Jan 2026"
   and body[0][63] == "Dec 2030" and body[0][64] == "Busiest" and len(body[0]) == 65 and len(body) == 5, str(body[0][:6]))
r50c = [r for r in body if r[0] == "R050"][0]
ok("⭐ CSV: R050's row names the route and the material; Apr 2027 = 132, Sep 2026 = 5, a month with nothing is empty, Busiest = 132",
   r50c[1:4] == ["Tilton Viaduct site", "Wolds Link Inert Landfill", "Earthworks / soil"] and r50c[4 + 15] == "132"
   and r50c[4 + 8] == "5" and r50c[4] == "" and r50c[64] == "132", str(r50c[:4]))
ok("⭐ CSV: the last row is the totals ('All 3 routes'); a typed word that starts like a formula is kept as text",
   body[-1][0] == "All 3 routes" and body[-1][4 + 15] == "136"
   and [r for r in body if r[0] == "R011"][0][1] == "'=Northfield Quarry"
   and [r for r in body if r[0] == "R011"][0][3] == "Small aggregate, Asphalt")
tt = list(csv.reader(io.StringIO(fp.csv_text(tab, "t", 2026).lstrip("﻿"))))
ok("⭐ CSV, tonnes: the last column is the Total: R050 133,500; Apr 2027 42,000; the totals row adds up",
   tt[0][64] == "Total" and [r for r in tt if r[0] == "R050"][0][64] == "133,500"
   and [r for r in tt if r[0] == "R050"][0][4 + 15] == "42,000" and tt[-1][64] == f"{133500 + 6400 + 5:,}")
try:
    fp.csv_text(tab, "vehicles", 2026)
    bad = False
except ValueError:
    bad = True
ok("an unknown unit is refused", bad)
ok("the file is named for what it holds",
   fp.file_name("t", 2) == "approved-plan-tonnes.csv" and fp.file_name("count", 2) == "approved-plan-movements-a-day.csv"
   and fp.file_name("count", 1) == "approved-plan-visits-a-day.csv")
ok("one row with one route reads 'All 1 route'",
   list(csv.reader(io.StringIO(fp.csv_text(fp.table({1: [{"route_id": "R1", "qty_t": 1, "vehicle_loads": 1}]}, 12, 22, 2), "t", 2026))))[-1][0] == "All 1 route")

for f in FAIL:
    print("  FAIL:", f)
print(f"test_forecast_plan.py: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

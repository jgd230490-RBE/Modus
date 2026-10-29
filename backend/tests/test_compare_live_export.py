"""
The live-export compare tool (29 Oct 2026, task 3d): `backend/tools/compare_live_export.py`.

WHAT IS ASSERTED
----------------
  * identical tables read "same"; rows only on one side are counted on that side;
  * a changed value is reported with both values; `_at` columns, 1.0 vs 1, True vs 1 and 4th-decimal noise do not count;
  * rows are keyed as the tables are (forecasts by route / month / discipline / section; weeks add the week);
  * the baked and fetched tables read "baked" when they differ, never "differs";
  * a route's limit / closure results and an abnormal load's drawn route are ignored (a bake and a draw fill them);
  * the file loader takes an export ({"tables": ...}) and a bare table map; the CLI prints the table and exits 0;
  * the tool only reads: it writes nothing (the scratch directory holds just the two input files afterwards).

WHAT THIS DOES NOT PROVE
------------------------
  * It was run on the real live export on 29 Oct (notes\\session-1029-generator-fold.md), not here: these are small
    fixtures. No database, no network.

Run:  python backend/tests/test_compare_live_export.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import compare_live_export as cle  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label)
        print("FAIL:", label)


def fc(route, month, qty, **kw):
    r = {"route_id": route, "month_index": month, "discipline": "earthworks", "section_id": "WS4",
         "quantity": qty, "material_description": "Spoil", "submitted_by": "IPT1 planner"}
    r.update(kw)
    return r


live = {
    "forecasts": [fc("R050", 5, 38000), fc("R050", 6, 42000.0), fc("R050", 7, 1, material_description="old words"),
                  fc("R099", 1, 5)],
    "forecast_weeks": [{"route_id": "R001", "month_index": 1, "discipline": "d", "section_id": "S", "week_index": 1,
                        "planned_qty": 10, "created_at": "2026-10-28T00:00:00Z"},
                       {"route_id": "R001", "month_index": 1, "discipline": "d", "section_id": "S", "week_index": 2,
                        "planned_qty": 10}],
    "zones": [{"id": "Z001", "name": "A", "active": True, "lat": 52.1234567}],
    "routes": [{"id": "R001", "name": "x", "limits_hits": "[1]", "limits_status": "ok"}],
    "abnormal_loads": [{"id": "AL001", "name": "Girder", "roads_json": "[1]", "duration_hr": 0.25}],
    "route_geometry": [{"id": 1, "distance_km": 1.0}, {"id": 2, "distance_km": 2.0}],
    "locations": [{"id": "L001", "name": "Yard"}],
}
gen = {
    "forecasts": [fc("R050", 5, 38000.0), fc("R050", 6, 42000), fc("R050", 7, 1, material_description="new words"),
                  fc("R098", 1, 5)],
    "forecast_weeks": [{"route_id": "R001", "month_index": 1, "discipline": "d", "section_id": "S", "week_index": 1,
                        "planned_qty": 10.0, "created_at": "2026-10-29T00:00:00Z"},
                       {"route_id": "R001", "month_index": 1, "discipline": "d", "section_id": "S", "week_index": 2,
                        "planned_qty": 12}],
    "zones": [{"id": "Z001", "name": "A", "active": 1, "lat": 52.12345671}],
    "routes": [{"id": "R001", "name": "x", "limits_hits": None, "limits_status": None}],
    "abnormal_loads": [{"id": "AL001", "name": "Girder", "roads_json": None, "duration_hr": None}],
    "route_geometry": [{"id": 1, "distance_km": 1.0}],
    "locations": [{"id": "L001", "name": "Yard"}],
}
res = cle.compare(live, gen, show=3)

ok("1: an identical table reads same", cle.verdict(res["locations"]) == "same")
ok("2: 1.0 vs 1, True vs 1, 4th-decimal noise and *_at columns do not count", cle.verdict(res["zones"]) == "same")
f = res["forecasts"]
ok("3: forecasts counts: 4 live, 4 package, 1 only live, 1 only package, 1 changed",
   (f["live"], f["gen"], f["only_live"], f["only_gen"], f["changed"]) == (4, 4, 1, 1, 1))
ok("4: keyed by route / month / discipline / section", ("R099", 1, "earthworks", "WS4") in f["sample_only_live"]
   and ("R098", 1, "earthworks", "WS4") in f["sample_only_gen"])
ok("5: a changed value carries both values (live first)",
   f["sample_changed"][("R050", 7, "earthworks", "WS4")] == {"material_description": ("old words", "new words")})
w = res["forecast_weeks"]
ok("6: weeks add the week index to the key; only week 2's quantity differs",
   w["changed"] == 1 and list(w["sample_changed"]) == [("R001", 1, "d", "S", 2)])
ok("7: a route's limit and closure results are ignored", cle.verdict(res["routes"]) == "same")
ok("8: an abnormal load's drawn route is ignored", cle.verdict(res["abnormal_loads"]) == "same")
g = res["route_geometry"]
ok("9: a baked table that differs reads baked, not differs", cle.verdict(g) == "baked" and g["only_live"] == 1)
ok("10: a table that differs and is not baked reads differs", cle.verdict(f) == "differs")

text = cle.report(res)
ok("11: the report has one line per table and names the differing ones",
   all(t in text for t in res) and "only on live" in text and "changed" in text)
ok("12: the report lists only differing tables below the header",
   text.count("\nforecasts\n") == 1 and "\nzones\n" not in text and "\nroute_geometry\n" not in text)

with tempfile.TemporaryDirectory() as d:
    p1, p2 = os.path.join(d, "live.json"), os.path.join(d, "pkg.json")
    json.dump({"modus_package": 1, "tables": live}, open(p1, "w", encoding="utf-8"))
    json.dump(gen, open(p2, "w", encoding="utf-8"))
    ok("13: the loader takes an export and a bare table map",
       cle.load_tables(p1) == live and cle.load_tables(p2) == gen)
    buf = io.StringIO()
    code = None
    real = sys.stdout
    try:
        sys.stdout = buf
        buf.reconfigure = lambda **k: None
        code = cle.main([p1, p2, "--show", "2"])
    finally:
        sys.stdout = real
    ok("14: the CLI prints the table and returns 0", code == 0 and "table" in buf.getvalue() and "forecasts" in buf.getvalue())
    ok("15: it only reads: the directory still holds just the two input files", sorted(os.listdir(d)) == ["live.json", "pkg.json"])

ok("16: the baked list names the fetched and drawn tables a replace removes",
   all(t in cle.BAKED for t in ("route_geometry", "route_hour_times", "collision_records", "community_features",
                                "traffic_counts", "route_choice")))

print(f"test_compare_live_export.py: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

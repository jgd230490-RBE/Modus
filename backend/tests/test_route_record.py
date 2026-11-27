"""
The route choices record (17 Nov 2026, best option step 3; branch claude/route-choices-record; John's "Yes, as recommended"
to the third draft notes/route-choices-record-mockup-1117 and its Q1 to Q9; notes/session-1117-route-choices-record.md).

WHAT IS ASSERTED
  1. The table: one new tenanted table, registered everywhere a tenanted table must be (db, the organisation file, the
     demo refresh's LIVE_TABLES, the tenant audit), no REAL and no BOOLEAN column.
  2. Empty: no choice, no row, the totals nought.
  3. Make primary writes a row at the click, a trip BEFORE and AFTER as stored that day; one-leg presses for the same
     route and lorry within 10 minutes join one row; a choice that adds carbon shows as added (a positive figure).
  4. The sums: planned = trips x a trip's difference over the Approved lines from the day; the totals are the rows'
     planned figures added up and nothing else (collisions never); so far from recorded weeks.
  5. Ends: a re-route ends the row ("routed_again"), never deletes it, and the sums stop at that date (an end date
     inside a month counts that month's working days before it only); Make primary back ends it "undone"; a later Make
     primary of another line ends the old row "road_changed" and starts a new one.
  6. Busy-hours roads: Use writes one row for every lorry type that has the road, its planned share the band's share of
     the open window; Stop ends it "stopped"; a pause by a re-route ends it "road_changed"; the same band used again
     with the same road keeps its row.
  7. Q2: a busy-hours road in use before the record existed is taken in on the first read, from the day it was put in
     use, only while its road is still the line put in use.
  8. The read and the sheet: the staff read after _gate_arrivals_build, any staff login, kept through _staff_json; the
     spreadsheet carries the demo line and its columns; a typed name is text.
  9. Words: no "avoided", "safer" or "risk", no percentage beside a collision count, in the module, the fold, its "i"
     boxes and the guide's paragraph.

WHAT THIS DOES NOT PROVE
  * The real router is not called: the lines are drawn here. Postgres is not run. The time a Make primary takes on live
    with the record is not measured (locally the record adds well under a second).
  * The counts (left turns, cycle routes met, places, collisions) come from route_best.measures on a fixture with no
    community layer and no collision fetch: they are read, not checked here (test_route_best checks the rule's counts).

Run:  python backend/tests/test_route_record.py
"""
import datetime
import json
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)

TMP = tempfile.mkdtemp(prefix="wayscope_record_")
from portable import remove_scratch_db   # noqa: E402
for _v in ("DATABASE_URL", "ADMIN_TOKEN", "TENANT_ID"):
    os.environ.pop(_v, None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import network  # noqa: E402
import route_choice  # noqa: E402
import weeks  # noqa: E402
import tenant_package  # noqa: E402
import limits  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

try:
    import route_record  # noqa: E402
except Exception as e:      # the code before: no module
    route_record = None
    FAIL.append(f"⭐ backend/route_record.py imports ({e})")

# =========================================================================== #
#  1. The table                                                                #
# =========================================================================== #
DDL = db._TENANT_DDL.get("route_choice_record", "")
ok("⭐ one new tenanted table route_choice_record, keyed (tenant_id, id)",
   "route_choice_record" in db.TENANTED_TABLES and db._TENANT_PK.get("route_choice_record") == "(tenant_id, id)"
   and "PRIMARY KEY (tenant_id, id)" in DDL)
ok("⭐ ...in the organisation file after route_geometry, and kept by a demo refresh (LIVE_TABLES)",
   "route_choice_record" in tenant_package.ORDER
   and tenant_package.ORDER.index("route_choice_record") > tenant_package.ORDER.index("route_geometry")
   and '"route_choice_record")' in read("backend/tools/make_demo_tenant.py").split("LIVE_TABLES = (")[1].split("\n\n")[0])
ok("⭐ ...and in the tenant audit's own list", '"route_choice_record",' in read("backend/tests/test_tenant_audit.py"))
ok("⭐ no REAL column (Postgres REAL is float4) and no BOOLEAN: figures are JSON text, flags are words",
   DDL and " REAL" not in DDL.upper() and "BOOLEAN" not in DDL.upper() and "figures        TEXT NOT NULL" in DDL)
ok("...the record is data (a write moves the kept reads): not in NO_DATA_TABLES", "route_choice_record" not in db.NO_DATA_TABLES)

# =========================================================================== #
#  Fixture: R1 (Alt 1 longer: a choice that ADDS), R3 (Alt 1 shorter: SAVES)   #
# =========================================================================== #
ART = "Artic Tipper (44t)"
FLAT = "Artic Flatbed (44t)"
LAT = 52.5
T = db.current_tenant()
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'L1', 'Kelsey Quarry', ?, -1.0, 'Quarry')", (T, LAT))
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'L2', 'Mill Compound', ?, -0.9, 'Compound')", (T, LAT))
for rid in ("R1", "R3"):
    db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, ?, 'L1', 'L2', "
               "'Small aggregate', 'IPT1')", (T, rid))
MAIN = [[-1.0, LAT], [-0.95, LAT], [-0.9, LAT]]
NORTH = [[-1.0, LAT], [-0.95, LAT + 0.01], [-0.9, LAT]]
FAR = [[-1.0, LAT], [-0.95, LAT + 0.02], [-0.9, LAT]]
SOUTH = [[-1.0, LAT], [-0.95, LAT - 0.01], [-0.9, LAT]]


def put(rid, leg, alt, line, km, hr, prof=ART):
    if leg == "return":
        line = list(reversed(line))
    network._upsert_geom(rid, prof, json.dumps(line), km, hr, None, leg=leg, alt_index=alt, zones_applied="",
                         haul_zones="", avoids=None)


for leg in ("loaded", "return"):
    put("R1", leg, 0, MAIN, 7.0, 0.20)
    put("R1", leg, 1, FAR, 9.0, 0.24)
    put("R1", leg, 2, NORTH, 8.0, 0.22)
    put("R1", leg, 0, MAIN, 7.0, 0.21, prof=FLAT)
    put("R3", leg, 0, FAR, 9.0, 0.24)
    put("R3", leg, 1, MAIN, 7.0, 0.20)

NOV27 = (2027 - 2026) * 12 + 11
for fid, rid in (("F1", "R1"), ("F3", "R3")):
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, vehicle_type, status, ipt) VALUES (?, ?, ?, ?, 'earthworks', 'WS1', 2900, 't', "
               "'Small aggregate', ?, 'Approved', 'IPT1')", (T, fid, rid, NOV27, ART))
db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
           "material_type, vehicle_type, status, ipt) VALUES (?, 'F3P', 'R3', ?, 'earthworks', 'WS1', 2900, 't', "
           "'Small aggregate', ?, 'Pending', 'IPT1')", (T, NOV27 + 1, ART))


def rows_of(rid=None):
    return route_record.rows(rid) if route_record else []


def by_route(R, rid):
    return [r for r in R["rows"] if r["route_id"] == rid]


# =========================================================================== #
#  2. Empty                                                                    #
# =========================================================================== #
if route_record:
    R0 = route_record.record()
    ok("⭐ empty: no choice, no row; the totals nought", R0["rows"] == [] and R0["totals"]["planned"]["kg"] == 0
       and R0["totals"]["planned"]["trips"] == 0 and R0["diversions"] == 0, str(R0)[:300])

# =========================================================================== #
#  3. Make primary writes, joins, and says what it adds                        #
# =========================================================================== #
if route_record:
    network.promote_alternative("R3", ART, 1, leg="loaded", who="Pat")
    got = rows_of("R3")
    ok("⭐ a Make primary writes ONE row at the click: kind primary, the lorry, the option, the leg, by whom, in use",
       len(got) == 1 and got[0]["kind"] == "primary" and got[0]["vehicle_profile"] == ART and got[0]["alt_index"] == 1
       and got[0]["legs"] == ["loaded"] and got[0]["decided_by"] == "Pat" and got[0]["status"] == "in_use", str(got)[:400])
    f = (got[0]["figures"] if got else {}).get(ART) or {}
    ok("⭐ ...a trip BEFORE (the old main line, 9 + 9 km) and AFTER (the new one, 7 + 9 km) as stored that day",
       abs(f.get("before", {}).get("km", 0) - 18.0) < 1e-6 and abs(f.get("after", {}).get("km", 0) - 16.0) < 1e-6,
       str(f)[:300])
    ok("...with each side's line fingerprints, both legs", all((f.get(s, {}).get("prints") or {}).get(l)
                                                           for s in ("before", "after") for l in ("loaded", "return")))
    network.promote_alternative("R3", ART, 1, leg="return", who="Pat")
    got = rows_of("R3")
    f = (got[0]["figures"] if got else {}).get(ART) or {}
    ok("⭐ Q3: the way-back press within 10 minutes JOINS the row: both legs, the after re-read (7 + 7 km), before kept",
       len(got) == 1 and got[0]["legs"] == ["loaded", "return"] and abs(f["after"]["km"] - 14.0) < 1e-6
       and abs(f["before"]["km"] - 18.0) < 1e-6, str(got)[:400])
    R = route_record.record()
    r3 = by_route(R, "R3")[0]
    ok("⭐ a choice that SAVES: a trip 4 km, some minutes and some kg CO2e less (negative figures)",
       r3["per_trip"]["km"] == -4.0 and r3["per_trip"]["kg"] < 0 and r3["per_trip"]["min"] < 0, str(r3["per_trip"]))
    ok("...no diesel price set here: the fair cost is missing (a dash), never a made-up nought",
       r3["per_trip"]["eur"] is None and r3["planned"]["eur_missing"] is True, str(r3["planned"]))
    ok("⭐ planned: the Approved line only (100 trips in Nov 2027; the Pending month left out) x a trip",
       abs(r3["planned"]["trips"] - 100) < 1e-6 and abs(r3["planned"]["km"] - (-400.0)) < 0.05
       and abs(r3["planned"]["kg"] - 100 * r3["per_trip"]["kg"]) < 1.0, str(r3["planned"]))
    ok("...nothing recorded yet: so far nought", r3["so_far"]["trips"] == 0 and r3["so_far"]["kg"] == 0)
    ok("⭐ a count not held (no cycle routes in this fixture) is None, a dash, while the counts that are held still add up",
       r3["planned"]["cycle_meets"] is None and r3["planned"]["left_turns"] is not None and r3["planned"]["places"] is not None,
       str(r3["planned"]))
    import fairprice
    FAC = conversions.load_factors()
    COST = {"index_eur_per_l": 1.5, "fair_params": fairprice.params(FAC)}
    s3 = route_record.sums(rows_of("R3")[0], factors=FAC, cost=COST)
    ok("⭐ Q6: fair cost (model) at the month's diesel price from the saved distance and minutes: less on the shorter road, "
       "planned = 100 x a trip", s3["per_trip"]["eur"] is not None and s3["per_trip"]["eur"] < 0
       and abs(s3["planned"]["eur"] - round(100 * s3["per_trip"]["eur"], 2)) < 1.0 and not s3["planned"]["eur_missing"],
       str(s3["per_trip"]))
    ok("...the row's words: Alt 1, the lorry, since today, the route's ends, the two collision labels",
       r3["label"] == "Alt 1" and r3["lorry"] == ART and r3["since"] == datetime.date.today().isoformat()
       and r3["from"] == "Kelsey Quarry" and r3["to"] == "Mill Compound"
       and r3["collisions"]["after_label"] == "Alt 1" and r3["collisions"]["before_label"] == "Old main route", str(r3)[:300])

    network.promote_alternative("R1", ART, 1, leg="loaded", who="Sam")
    network.promote_alternative("R1", ART, 1, leg="return", who="Sam")
    R = route_record.record()
    r1 = by_route(R, "R1")[0]
    ok("⭐ a choice that ADDS carbon shows as added: positive kg, km and time a trip and planned (never hidden)",
       r1["per_trip"]["kg"] > 0 and r1["per_trip"]["km"] == 4.0 and r1["per_trip"]["min"] > 0 and r1["planned"]["kg"] > 0,
       str(r1["per_trip"]))
    ok("...only the lorry pressed: the flatbed on R1 has no row", all(r["lorry"] == ART for r in by_route(R, "R1")))
    tp = R["totals"]["planned"]
    ok("⭐ the totals are the rows' planned figures added up (carbon, time, distance, fair cost, loads)",
       all(abs(tp[k] - round(sum(r["planned"][k] for r in R["rows"]), 2 if k == "eur" else 1)) < 0.11
           for k in ("kg", "min", "km", "eur", "trips")), str(tp))
    ok("⭐ collisions are never multiplied by loads nor totalled: no collision figure in a planned block or the totals",
       all("collisions" not in r["planned"] and "collisions" not in r["so_far"] for r in R["rows"])
       and "collisions" not in tp and "collisions" not in route_record.TIMES_LOADS)

    # so far: a recorded week from the choice
    weeks.materialise_line("R3", "earthworks", "WS1", NOV27)
    wk = db.query("SELECT week_index FROM forecast_weeks WHERE tenant_id = ? AND route_id = 'R3' AND month_index = ? "
                  "ORDER BY week_index", (T, NOV27))
    weeks.set_actual("R3", NOV27, "earthworks", "WS1", int(wk[0]["week_index"]), actual_qty=580, by="Sam")
    R = route_record.record()
    r3 = by_route(R, "R3")[0]
    ok("⭐ Q4: so far from the recorded loads (580 t = 20 trips) x a trip, estimated",
       abs(r3["so_far"]["trips"] - 20) < 1e-6 and abs(r3["so_far"]["km"] - (-80.0)) < 0.05, str(r3["so_far"]))

# =========================================================================== #
#  5. Ends: a re-route, an undo, another line made the main route              #
# =========================================================================== #
if route_record:
    # Make primary back on R1, both legs: "undone"
    network.promote_alternative("R1", ART, 1, leg="loaded", who="Sam")
    mid = rows_of("R1")
    network.promote_alternative("R1", ART, 1, leg="return", who="Sam")
    got = rows_of("R1")
    ok("⭐ Q8: Make primary back to the line in use before ends the row 'undone' (never deleted)",
       len(got) == 1 and got[0]["status"] == "ended" and got[0]["ended_why"] == "undone"
       and got[0]["ended_on"] == datetime.date.today().isoformat(), str([(r["status"], r.get("ended_why")) for r in got]))
    ok("...the half-way press (one leg back) kept the row open and joined it", len(mid) == 1 and mid[0]["status"] == "in_use")

    # another line made the main route an hour later: the old row ends "road_changed", a new one starts
    network.promote_alternative("R1", ART, 2, leg="loaded", who="Sam")
    first = [r for r in rows_of("R1") if r["status"] == "in_use"]
    db.execute("UPDATE route_choice_record SET decided_at = ? WHERE tenant_id = ? AND id = ?",
               ((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).isoformat(timespec="seconds"),
                T, first[0]["id"]))
    network.promote_alternative("R1", ART, 1, leg="loaded", who="Sam")      # Alt 1 (the line that was Alt 2's... now 1)
    got = rows_of("R1")
    ok("⭐ a later Make primary of another line (after 10 minutes) ends the old row 'road_changed' and starts a new one",
       len([r for r in got if r["status"] == "in_use"]) == 1
       and any(r["id"] == first[0]["id"] and r["ended_why"] == "road_changed" for r in got), str([(r["id"][-25:], r["status"], r.get("ended_why")) for r in got]))

    # a re-route of R3 (a bake writes a new main line): "routed_again"
    put("R3", "loaded", 0, SOUTH, 8.0, 0.22)
    route_choice.refresh_zones()
    got = rows_of("R3")
    ok("⭐ Q8 / N4: routing the route again ends its row 'routed_again', the day it happened; never deleted",
       len(got) == 1 and got[0]["status"] == "ended" and got[0]["ended_why"] == "routed_again"
       and got[0]["ended_on"] == datetime.date.today().isoformat(), str([(r["status"], r.get("ended_why")) for r in got]))
    R = route_record.record()
    r3 = by_route(R, "R3")[0]
    ok("⭐ ...and its sums stop at that date: ended today, nothing planned in Nov 2027 counts",
       r3["planned"]["trips"] == 0 and r3["so_far"]["trips"] == 0 and r3["ended_words"] == "routed again", str(r3["planned"]))
    # an end INSIDE a month: Mon 1 to Mon 15 Nov 2027 is 10 of its 22 working days
    db.execute("UPDATE route_choice_record SET since = '2027-11-01', ended_on = '2027-11-15' WHERE tenant_id = ? AND id = ?",
               (T, got[0]["id"]))
    r3 = by_route(route_record.record(), "R3")[0]
    nd = len(route_choice.month_days(NOV27))
    # NARROWED 17 Nov 2026 (ui-best-option-1117, finding 8): the sums use WHOLE loads: 100 x 10 / 22 = 45.45 is 45 loads
    # (it was 45.5), and the km sum is those 45 x a trip's 4 km, so the shown loads times a trip is the shown sum
    ok("⭐ an end inside a month counts that month's working days before it only (100 x 10 / %d)" % nd,
       nd == 22 and r3["planned"]["trips"] == round(100 * 10 / 22) == 45
       and abs(r3["planned"]["km"] - 45 * r3["per_trip"]["km"]) < 1e-6, str(r3["planned"]))
    ok("...so far: only the recorded weeks before the end (week 1's 20 trips)", abs(r3["so_far"]["trips"] - 20) < 1e-6,
       str(r3["so_far"]))
    ok("an end is never undone by a later read: still ended", rows_of("R3")[0]["status"] == "ended")
    try:
        route_record.end(got[0]["id"], "deleted")
        bad = False
    except ValueError:
        bad = True
    ok("only the four ends are words a row can carry", bad and set(route_record.ENDED_WORDS) ==
       {"routed_again", "undone", "stopped", "road_changed"})

# =========================================================================== #
#  6. Busy-hours roads                                                         #
# =========================================================================== #
if route_record:
    # a fresh route for the busy-hours road
    db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, 'R5', 'L1', 'L2', "
               "'Small aggregate', 'IPT1')", (T,))
    for leg in ("loaded", "return"):
        put("R5", leg, 0, MAIN, 7.0, 0.20)
        put("R5", leg, 2, NORTH, 8.0, 0.22)
        put("R5", leg, 0, MAIN, 7.0, 0.21, prof=FLAT)
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, vehicle_type, status, ipt) VALUES (?, 'F5', 'R5', ?, 'earthworks', 'WS1', 2900, 't', "
               "'Small aggregate', ?, 'Approved', 'IPT1')", (T, NOV27, ART))
    route_choice.use_busy("R5", 2, "16:00", "19:00", who="Pat")
    got = rows_of("R5")
    ok("⭐ Q1b: Use on a busy-hours road writes ONE row: kind busy, every lorry type that has the road (the tipper; the "
       "flatbed has no Alt 2), both legs, the band",
       len(got) == 1 and got[0]["kind"] == "busy" and got[0]["vehicle_profile"] is None
       and set(got[0]["figures"]) == {ART} and got[0]["legs"] == ["loaded", "return"]
       and got[0]["hours_from"] == "16:00" and got[0]["hours_to"] == "19:00", str(got)[:400])
    route_choice.use_busy("R5", 2, "16:00", "19:00", who="Pat")
    ok("...the same band used again with the same road keeps its row", len(rows_of("R5")) == 1)
    R = route_record.record()
    r5 = by_route(R, "R5")[0]
    SH = route_choice.busy_share("16:00", "19:00", route_choice.busy_span("R5"))
    ok("⭐ planned: the band's share of the open window (16:00-17:00 of 08:00-17:00 = 1/9) of the 100 trips, 'of 100'",
       # NARROWED 17 Nov 2026 (finding 8): whole loads: 100 / 9 = 11.1 is 11 (it was 11.1), "of" a whole 100
       abs(SH - 1 / 9) < 1e-9 and r5["planned"]["trips"] == 11 and r5["planned"]["of"] == 100
       and abs(r5["planned"]["km"] - 11 * r5["per_trip"]["km"]) < 1e-6
       and r5["all_lorries"] is True and r5["collisions"]["before_label"] == "Main route", str(r5["planned"]))
    route_choice.stop_busy("R5", "16:00", who="Pat")
    got = rows_of("R5")
    ok("⭐ Q8: Stop ends the row 'stopped'", len(got) == 1 and got[0]["status"] == "ended" and got[0]["ended_why"] == "stopped")
    route_choice.use_busy("R5", 2, "16:00", "19:00", who="Pat")
    ok("⭐ a busy-hours road used again starts a NEW row", len([r for r in rows_of("R5") if r["status"] == "in_use"]) == 1
       and len(rows_of("R5")) == 2)
    put("R5", "loaded", 2, FAR, 9.0, 0.24)          # a re-route changes the busy-hours road
    route_choice.refresh_zones()
    got = [r for r in rows_of("R5") if r["status"] == "ended" and r["ended_why"] == "road_changed"]
    ok("⭐ Q8: a busy-hours road paused by a re-route ends its row 'road_changed'", len(got) == 1
       and not [r for r in rows_of("R5") if r["status"] == "in_use"], str([(r["status"], r.get("ended_why")) for r in rows_of("R5")]))

# =========================================================================== #
#  7. Q2: a busy-hours road in use before the record existed                   #
# =========================================================================== #
if route_record:
    db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, 'R7', 'L1', 'L2', "
               "'Small aggregate', 'IPT1')", (T,))
    for leg in ("loaded", "return"):
        put("R7", leg, 0, MAIN, 7.0, 0.20)
        put("R7", leg, 2, NORTH, 8.0, 0.22)
    # as route_choice.use_busy wrote it on 6 Nov, before the record (straight into the table, no record row)
    for leg in ("loaded", "return"):
        g = db.query("SELECT geometry FROM route_geometry WHERE tenant_id = ? AND route_id = 'R7' AND vehicle_profile = ? "
                     "AND leg = ? AND alt_index = 2", (T, ART, leg))[0]
        db.execute("INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, starts_on, ends_on, "
                   "hours_from, hours_to, days, reason_kind, reason_ref, status, source, km_delta, decided_by, decided_at, "
                   "created_at, updated_at, line_fp) VALUES (?, ?, 'R7', ?, ?, 2, NULL, NULL, '16:00', '19:00', '1111100', "
                   "'peak', '16:00-19:00', 'in_use', 'planner', 1.0, 'Jo', '2026-11-06T09:00:00+00:00', "
                   "'2026-11-06T09:00:00+00:00', '2026-11-06T09:00:00+00:00', ?)",
                   (T, f"P:R7:{ART}:{leg}:16:00", ART, leg, route_choice._fp(g["geometry"])))
    ok("before the first read: no row for R7", rows_of("R7") == [])
    R = route_record.record()
    r7 = by_route(R, "R7")
    ok("⭐ Q2: the first read takes it in, from the day it was put in use (6 Nov 2026), by whom",
       len(r7) == 1 and r7[0]["since"] == "2026-11-06" and r7[0]["kind"] == "busy" and r7[0]["decided_by"] == "Jo", str(r7)[:300])
    route_record.record()
    ok("...once only", len(rows_of("R7")) == 1)
    # a road that changed since it was put in use is NOT taken in
    db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, 'R8', 'L1', 'L2', "
               "'Small aggregate', 'IPT1')", (T,))
    for leg in ("loaded", "return"):
        put("R8", leg, 0, MAIN, 7.0, 0.20)
        put("R8", leg, 2, NORTH, 8.0, 0.22)
        db.execute("INSERT INTO route_choice (tenant_id, id, route_id, vehicle_profile, leg, alt_index, hours_from, hours_to, "
                   "days, reason_kind, reason_ref, status, source, decided_by, decided_at, created_at, updated_at, line_fp) "
                   "VALUES (?, ?, 'R8', ?, ?, 2, '16:00', '19:00', '1111100', 'peak', '16:00-19:00', 'in_use', 'planner', "
                   "'Jo', '2026-11-06T09:00:00+00:00', '2026-11-06T09:00:00+00:00', '2026-11-06T09:00:00+00:00', 'old-line')",
                   (T, f"P:R8:{ART}:{leg}:16:00", ART, leg))
    route_record.record()
    ok("⭐ Q2: ...only while its road is still the line put in use (a changed line is not taken in)", rows_of("R8") == [])

# =========================================================================== #
#  8. The read and the spreadsheet                                             #
# =========================================================================== #
MAIN_PY = read("backend/main.py")
ga = MAIN_PY.find("def _gate_arrivals_build(")
ep = MAIN_PY.find('@app.get("/api/route-choices/record")')
body = MAIN_PY[ep:MAIN_PY.find("\n@app.", ep + 10)] if ep > 0 else ""
ok("⭐ the staff read: after _gate_arrivals_build, any staff login, one kept build (_staff_json)",
   ga > 0 and ep > ga and "acc = _require_access()" in body
   and '_staff_json("route-choices/record", {}, route_record.record, acc)' in body)
ok("⭐ ...and the spreadsheet beside it", '@app.get("/api/route-choices/record.xlsx")' in MAIN_PY
   and "route_record.build_xlsx(R)" in MAIN_PY)
# NARROWED 17 Nov 2026 (finding 2): the endpoint passes the legs one press moves too; who made the choice as before
ok("⭐ Make primary's endpoint passes who made the choice",
   "network.promote_alternative(route_id, profile, alt_index, leg=want[0], who=_by(), legs=want)" in MAIN_PY)
NET = read("backend/network.py")
ok("⭐ the record is read BEFORE the swap and written before refresh_zones' sync",
   NET.find("_record.before_promote(route_id, profile, leg, alt_index)") < NET.find("TMP = -1")
   and NET.find("_record.after_promote(_rec, who=who)") < NET.find('road_sections._rebuild_quietly("alternative promoted")')
   and NET.find("_record.after_promote(_rec, who=who)") > NET.find("(alt_index, db.current_tenant(), route_id, profile, leg, TMP))"))
RC = read("backend/route_choice.py")
ok("⭐ Use, Stop and every refresh reach the record", "route_record.open_busy(route_id, alt, hours_from, hours_to, who=who, decided_at=now)" in RC
   and "route_record.stop_busy(route_id, hours_from)" in RC and 'route_record.sync_quietly("refresh")' in RC)
if route_record:
    import export
    if export.openpyxl is not None:
        import io
        R = route_record.record()
        db.execute("UPDATE route_choice_record SET decided_by = '=SUM(1,2)' WHERE tenant_id = ? AND route_id = 'R7'", (T,))
        R = route_record.record()
        data = route_record.build_xlsx(R)
        wb = export.openpyxl.load_workbook(io.BytesIO(data))
        ws = wb["Route choices"]
        cells = [[c.value for c in r] for r in ws.iter_rows()]
        head_row = next((r for r in cells if r[0] == "Route"), None)
        ok("⭐ Q7: the sheet: its head as drawn (route, choice, lorry types, made, by, ended, why … collisions before / after)",
           head_row is not None and head_row[:7] == ["Route", "Choice", "Lorry types", "Made", "By", "Ended", "Why ended"]
           and head_row[-2:] == ["Collisions, road before", "Collisions, road after"]
           and "Fair cost (model) planned (€)" in head_row and "Distance before (km)" in head_row, str(head_row))
        data_rows = [r for r in cells[cells.index(head_row) + 1:] if r[0]] if head_row else []
        ok("...a row a choice", len(data_rows) == len(R["rows"]), f"{len(data_rows)} vs {len(R['rows'])}")
        r7row = next((r for r in data_rows if r[0] == "R7"), None)
        ok("⭐ a typed name is text, never run as a formula", r7row is not None and r7row[4] == "'=SUM(1,2)", str(r7row))
        ok("...an ended row says why", any(r[6] == "routed again" for r in data_rows))
        ok("an About sheet says what is kept and what is not counted", "About" in wb.sheetnames
           and any("not a choice" in str(c.value) for row in wb["About"].iter_rows() for c in row))
    else:
        ok("openpyxl present for the sheet check", False)

# =========================================================================== #
#  9. Words                                                                    #
# =========================================================================== #
HTML = read("frontend/index.html")
a = HTML.find("function RouteChoicesRecord(")
fold = HTML[HTML.find("const RC_MONTHS"):HTML.find("\n}\n", a) + 3] if a > 0 else ""
infos = "".join(re.findall(r'"dash\.rc\.[a-z]+": \{[^\n]+', HTML))
guide = read("frontend/help/index.html")
gp = guide[guide.find('<p id="route-choices-record">'):]
gp = gp[:gp.find("</p>")]
mod = read("backend/route_record.py")
BAN = re.compile(r"\b(avoided|avoid|safer|safe|risk|risks|ratio)\b", re.I)
ok("⭐ no 'avoided', 'safer' or 'risk' in the fold, its 'i' boxes, the guide's paragraph or the module",
   fold and infos and gp and not BAN.search(fold) and not BAN.search(infos) and not BAN.search(gp) and not BAN.search(mod),
   str([BAN.findall(x) for x in (fold, infos, gp, mod)]))
ok("⭐ no percentage beside a collision count", fold and not re.search(r"[Cc]ollisions?[^\n]{0,80}%", fold)
   and not re.search(r"[Cc]ollisions?[^\n]{0,80}%", gp))
ok("⭐ the fold is first under the Simulation line and closed each visit",
   HTML.find("<SimDashLine ") < HTML.find("<RouteChoicesRecord ") < HTML.find("<TrafficDash ")
   and "const [open, setOpen] = useState(false);" in fold)
ok("⭐ it sits before function EmptyState (the Dashboard pins slice up to it)",
   a > 0 and a < HTML.find("function EmptyState(") and a > HTML.find("function Dashboard("))
ok("⭐ the three 'i' boxes, each 30 words or fewer, and the guide links",
   len(re.findall(r'"dash\.rc\.(planned|places|collisions)": \{', HTML)) == 3
   and all(len(t.split()) <= 30 for t in re.findall(r'"dash\.rc\.[a-z]+": \{ title: "[^"]+", text: "([^"]+)"', HTML))
   and '<h2 id="t1-route-choices-record">' in read("frontend/help/technical/index.html"))
ok("⭐ the fold's own words as agreed (title, empty, the diversions line, Planned / So far, no loads yet)",
   all(s in fold for s in ("Route choices: what each saved or added", "No route choice yet.",
                           "A choice made on Routes is kept here: another main route, or a road for the busy hours.",
                           "on a dated diversion: a closure, not a choice, so not counted here.", "No loads recorded yet",
                           "A lorry passes, planned:", "Planned, not measured", "Fair cost (model)")))

_src = read("frontend/index.html")
_rr = read("backend/route_record.py")
ok("⭐ C3 (routes rethink Q9): the record's columns, tip and sheet say Left-hand turns and Community; 'Left turns' and 'Places' are gone",
   '["left_turns", "count", "Left-hand turns"]' in _src and '["places", "count", "Community"]' in _src
   and '"Left-hand turns planned"' in _rr and '"Community planned"' in _rr and '("Community", "Schools' in _rr
   and '"Left turns"' not in _src and '["places", "count", "Places"]' not in _src
   and "Left turns planned" not in _rr and "Places planned" not in _rr and '("Places", "Schools' not in _rr)
remove_scratch_db(db, TMP)
print(f"test_route_record: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  ✗", f)
sys.exit(1 if FAIL else 0)

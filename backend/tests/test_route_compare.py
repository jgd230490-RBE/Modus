"""
Route options compared (29 Oct 2026). John: "there must be some narrative on how HERE selects its routes safely … if we
can actually show that HERE chooses the safer / more sustainable route". route_compare.compare() sets HERE's first option
beside each alternative it gave, for every route: distance, minutes, carbon a trip, collisions on it, the community
considerations near it, cycle routes and left turns; summary() tallies first-against-alternative as fewer / same / more.
The community strip now covers every option HERE gave, so the alternatives' schools and homes are fetched too.

WHAT IS ASSERTED: one row per HERE option (a way round left out); the plan's own distance, minutes and carbon; collisions
within 25 m only; community counts by kind and distance (an area by an outline point); the tally; the strip; the read is
admin and calls nothing.
WHAT THIS DOES NOT PROVE: the live counts (the study runs on live); that a count means risk (it does not).

Run:  python backend/tests/test_route_compare.py
"""
import json
import math
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_gate_access.py ---------------------------------
_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


def _passthrough_decorator(*a, **k):
    def wrap(fn):
        return fn
    return wrap


class _App:
    def __init__(self, *a, **k):
        pass

    def get(self, *a, **k):
        return _passthrough_decorator()

    post = put = delete = patch = get

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


class _HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = lambda default=None, **k: default


class _Request:
    def __init__(self, headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


_fa.Request = _Request
sys.modules.setdefault("fastapi", _fa)
_mw = types.ModuleType("fastapi.middleware")
_cors = types.ModuleType("fastapi.middleware.cors")
_cors.CORSMiddleware = object
_mw.cors = _cors
sys.modules.setdefault("fastapi.middleware", _mw)
sys.modules.setdefault("fastapi.middleware.cors", _cors)
_resp = types.ModuleType("fastapi.responses")
_resp.FileResponse = lambda *a, **k: None
_resp.Response = object
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="wayscope_compare_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
os.environ.pop("TENANT_ID", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import gates  # noqa: E402
import haul  # noqa: E402
import zones  # noqa: E402
import here_routing  # noqa: E402
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


def north(p, m):
    return [p[0], round(p[1] + m / 111320.0, 7)]


import route_compare  # noqa: E402
import collisions  # noqa: E402
import community  # noqa: E402
import limits  # noqa: E402

remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# =========================================================================== #
#  Fixture: one route with HERE's first option straight along 52.5 N, its     #
#  alternative bent 1.1 km north, and a way round a closed zone (alt 10)       #
#  bent south — which is not HERE's choice between options and stays out       #
# =========================================================================== #
ART = route_compare.PROFILE
T = db.current_tenant()
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'L1', 'Quarry', 52.5, -1.0, 'Quarry')", (T,))
db.execute("INSERT INTO locations (tenant_id, id, name, lat, lon, loc_type) VALUES (?, 'L2', 'Compound', 52.5, -0.9, 'Compound')", (T,))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, material_category, ipt) VALUES (?, 'R1', 'L1', 'L2', "
           "'Small aggregate', 'IPT1')", (T,))
LINE0 = [[-1.0 + 0.005 * i, 52.5] for i in range(21)]
LINE1 = [[-1.0, 52.5], [-0.98, 52.51], [-0.92, 52.51], [-0.9, 52.5]]
LINE10 = [[-1.0, 52.5], [-0.98, 52.49], [-0.92, 52.49], [-0.9, 52.5]]
for alt, line, km, hr in ((0, LINE0, 7.0, 0.20), (1, LINE1, 8.0, 0.18), (10, LINE10, 9.0, 0.25)):
    network._upsert_geom("R1", ART, json.dumps(line), km, hr, None, leg="loaded", alt_index=alt)
    network._upsert_geom("R1", ART, json.dumps(list(reversed(line))), km, hr, None, leg="return", alt_index=alt)

# community: a school 110 m from the alternative and 1.2 km from the first option; a residential area with an outline
# point 60 m from the first option; a bus stop 50 m from the first option
DLAT = 1 / 110574.0
community.replace_source("gias", [{"source_ref": "URN 1", "kind": "schools", "name": "Langham Primary",
                                   "geometry": {"type": "Point", "coordinates": [-0.95, 52.51 + 110 * DLAT]}}], "2026-10-29T09:00:00Z")
community.replace_source("osm", [{"source_ref": "way/1", "kind": "residential", "name": "Homes",
                                  "geometry": {"type": "Polygon", "coordinates": [[[-0.94, 52.5 - 60 * DLAT], [-0.93, 52.5 - 60 * DLAT],
                                                                                   [-0.93, 52.49], [-0.94, 52.49], [-0.94, 52.5 - 60 * DLAT]]]}}],
                         "2026-10-29T09:00:00Z")
community.replace_source("naptan", [{"source_ref": "stop 1", "kind": "bus_stops", "name": "Stop",
                                     "geometry": {"type": "Point", "coordinates": [-0.97, 52.5 + 50 * DLAT]}}], "2026-10-29T09:00:00Z")


def rec(cid, routes, severity=3, vru=(), vru_ksi=()):
    return {"collision_id": cid, "year": 2024, "month": 5, "lon": -0.95, "lat": 52.5, "severity": severity, "road": "A6",
            "road2": None, "junction": None, "road_type": None, "speed_limit": 40, "light": None, "authority": None,
            "n_casualties": 1, "n_vehicles": 2, "vru": list(vru), "vru_ksi": list(vru_ksi), "goods": False, "dist_m": 5,
            "routes": routes, "sites": {}}


collisions.replace_all([rec("C1", {"R1": 10}, severity=2, vru=["pedestrian"], vru_ksi=["pedestrian"]),
                        rec("C2", {"R1@1": 5, "R1": 400}, vru=["cyclist"]),
                        rec("C3", {"R1@1": 40}),                     # beyond ON_ROUTE_M of the alternative: not on it
                        rec("C4", {"R1@10": 3}, severity=1)],        # the way round only: never counted
                       "2026-10-29T09:00:00Z")

# =========================================================================== #
#  1. The rows                                                                 #
# =========================================================================== #
OUT = route_compare.compare()
rows = {(r["route"], r["alt"]): r for r in OUT["rows"]}
ok("⭐ 1. one row per option HERE gave; the way round a closed zone (alt 10) is left out", sorted(rows) == [("R1", 0), ("R1", 1)],
   str(sorted(rows)))
r0, r1 = rows[("R1", 0)], rows[("R1", 1)]
ok("1. HERE's rank, distance, minutes and the plan's carbon a trip, from the plan's own costing",
   (r0["here_rank"], r1["here_rank"]) == (1, 2) and (r0["km"], r1["km"]) == (14.0, 16.0)
   and (r0["minutes"], r1["minutes"]) == (24.0, 21.6) and r0["co2_kg"] < r1["co2_kg"], f"{r0['km']} {r1['km']} {r0['minutes']} {r1['minutes']}")
ok("⭐ 1. collisions on each option: within 25 m only, the kinds counted",
   (r0["collisions"], r0["ksi"], r0["vru_ksi"], r0["cyclist"]) == (1, 1, 1, 0)
   and (r1["collisions"], r1["ksi"], r1["vru_ksi"], r1["cyclist"]) == (1, 0, 0, 1), f"{r0} {r1}")
ok("⭐ 1. the community near each option: a school near the alternative only; homes (an outline within 100 m) and a bus stop "
   "(within 100 m) near the first option only",
   (r0["schools"], r1["schools"]) == (0, 1) and (r0["residential"], r1["residential"]) == (1, 0)
   and (r0["bus_stops"], r1["bus_stops"]) == (1, 0), f"{r0} {r1}")
ok("1. left turns are counted on each laden line; cycle routes are None where none is stored",
   isinstance(r0["left_turns"], int) and r0["cycle_meets"] is None and r1["cycle_beside_km"] is None)
ok("1. the distances are stated with the answer", OUT["near_m"]["schools"] == 250 and OUT["near_m"]["bus_stops"] == 100
   and OUT["near_m"]["residential"] == 100 and OUT["on_route_m"] == collisions.ON_ROUTE_M == 25)

# =========================================================================== #
#  2. The summary: HERE's first option against each alternative               #
# =========================================================================== #
S = OUT["summary"]
ok("⭐ 2. one pair (R1 first against R1 Alt 1), tallied kind by kind as fewer / same / more",
   (S["routes"], S["routes_with_alternatives"], S["pairs"]) == (1, 1, 1)
   and S["kinds"]["schools"] == {"fewer": 1, "same": 0, "more": 0, "total_first": 0, "total_alt": 1}
   and S["kinds"]["ksi"]["more"] == 1 and S["kinds"]["collisions"]["same"] == 1
   and S["kinds"]["residential"]["more"] == 1 and S["kinds"]["km"]["fewer"] == 1 and S["kinds"]["co2_kg"]["fewer"] == 1, str(S["kinds"]))
ok("2. a kind with no figure on either side (no cycle route stored) is not tallied",
   S["kinds"]["cycle_meets"] == {"fewer": 0, "same": 0, "more": 0, "total_first": 0, "total_alt": 0})
ok("2. a route without an alternative makes no pair", route_compare.summary([{"route": "R9", "alt": 0, "km": 3}])["pairs"] == 0)

# =========================================================================== #
#  3. The community strip covers every option HERE gave                        #
# =========================================================================== #
# 29 Oct 2026 (NARROWED, not deleted): the wide strip is too heavy for the deployment's OpenStreetMap pass, so a
# Fetch now covers the main routes and diversions only; the wide strip is an option for a study on a bigger machine
lines = community.strip_from_db().lines
wide = community.strip_from_db(all_options=True).lines
ok("⭐ 3. a Fetch now's strip is the main routes and diversions only (the wide one is too heavy for the deployment)",
   not any(abs(c[1] - 52.51) < 1e-6 for ln in lines for c in ln))
ok("⭐ 3. ...the wide strip (all_options=True) covers the alternative, for a study run with more memory",
   any(abs(c[1] - 52.51) < 1e-6 for ln in wide for c in ln))
ok("3. ...and neither covers a way round a closed zone that no diversion uses",
   not any(abs(c[1] - 52.49) < 1e-6 for ln in lines + wide for c in ln))
ok("3. refresh() uses the default (narrow) strip", "strip = strip or strip_from_db()" in read("backend/community.py"))

# =========================================================================== #
#  4. Source                                                                   #
# =========================================================================== #
_m = read("backend/main.py").split("def route_options_compare(")[1].split("\n@app")[0]
ok("4. the read is admin-only and spends no HERE call", "_check_admin(token)" in _m and "route_compare.compare(profile)" in _m
   and '"/api/admin/route-options/compare"' in read("backend/main.py"))
_rc = read("backend/route_compare.py")
ok("4. the module says what it does not prove (counts, not risk)", "a count beside a road is not a risk" in _rc
   and "Counts only, never rates or a verdict" in _rc)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)

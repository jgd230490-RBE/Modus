"""
The route sheet for drivers and the route's typed words (16 Oct 2026, CLOCS v5 C2 + C3; notes/clocs-v5-gap-1016.md) —
backend/route_sheet.py, export.build_route_sheet_pdf, network.set_route_sheet_text / set_site_rules and the endpoints
GET /api/routes/{id}/route-sheet.pdf, PUT /api/admin/routes/{id}/sheet-text, the location's site_rules.

WHAT IS ASSERTED
----------------
  * C2: why this route and the permitted diversions on a route, the site rules on a location — trimmed, blank = None,
    at most network.SHEET_TEXT_MAX characters (refused in words, nothing written), only the fields sent are written;
    they are in the schema twice (DDL + ALTER), travel in the tenant package, and reach the Routes page read, the public
    map's route features (both legs) and the location read;
  * C3: one A4 PORTRAIT page per route: the legs, the last mile (by hand, along the line), the gates the BAKE uses at
    each end (gates.resolve with the route's gate ids and the role), their hours and closed days, the scheme's
    no-delivery windows, the lorry-limits words for every stored state, "Not typed" for an empty field, the gate note
    when a leg ends more than 200 m from its gate, one gate both ways drawn and named once;
  * the longest typed words (400 characters in all four fields) still make ONE page, the body text stepping down;
  * a team code reads its own team's routes only; the endpoints are staff only / admin only (source; http_smoke over HTTP);
  * the screens: the Routes page panel and button, the location's box, the public map's route card (source).

WHAT THIS DOES NOT PROVE
------------------------
Mapbox is never called (portable.offline): the maps here are drawn without a basemap. How the page LOOKS was checked by
rendering it from a local copy of the demo database with the basemap (notes/session-1016-route-sheet.md). HERE is never
called: geometry rows are typed in.

Run:  python3 backend/tests/test_route_sheet.py
"""
import json
import math
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_route_map_export.py ----------------------------
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


def _Query(default=None, **k):
    return default


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query


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


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


_resp.Response = _Response
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass

    async def get_response(self, path, scope):
        return None


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="rbe_rs_")
from portable import remove_scratch_db, pdf_text, offline   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import gates  # noqa: E402
import zones  # noqa: E402
import tenant_package  # noqa: E402
import export  # noqa: E402
import basemap  # noqa: E402
import io
from PIL import Image as PILImage
import bulletin_doc  # noqa: E402
import route_sheet as rs  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
access.set_current("planner123")
PLANNER = access.current()
TEAM1 = {"role": "ipt", "ipt": "IPT1", "label": "North Team"}
TEAM2 = {"role": "ipt", "ipt": "IPT2", "label": "Central Team"}
offline(export)            # Mapbox is never called: no basemap in any PDF here

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def flat(pdf):
    return " ".join(pdf_text(pdf).split())


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# =========================================================================== #
#  Fixture: a straight 6.8 km road east along 52.5° N, A at its west end     #
# =========================================================================== #
ART, R8 = "Artic Tipper (44t)", "Rigid 8-wheeler (32t)"
LAT = 52.5
STEP = 0.001                                      # degrees of longitude between vertices (~67.7 m at 52.5° N)
LOADED = [(round(-1.0 + i * STEP, 6), LAT) for i in range(101)]            # A (-1.0) -> B (-0.9)
RETURN = list(reversed(LOADED))
for _id, _name, _type, _lon in (("L1", "Kelsey Quarry", "Quarry", -1.0), ("L2", "Mill Compound", "Compound", -0.9),
                                ("L3", "Ridge Pit", "Quarry", -1.2)):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)", (_id, _name, LAT, _lon, _type))
for _rid, _o, _d, _ipt in (("R1", "L1", "L2", "IPT 1"), ("R2", "L3", "L2", "IPT 2"), ("R3", "L1", "L2", "IPT 1")):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES (?, ?, ?, ?, ?)",
               (_rid, _o, _d, "Small aggregate", _ipt))
tenant_package.import_rows("ipts", [
    {"id": "IPT1", "label": "North Team", "manager": None, "active": True, "merged_into": None},
    {"id": "IPT2", "label": "Central Team", "manager": None, "active": True, "merged_into": None}])


def _geom(rid, prof, leg, coords, km, hr):
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
               "duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               ("default", rid, prof, leg, 0, json.dumps([list(c) for c in coords]), km, hr))


_geom("R1", ART, "loaded", LOADED, 6.8, 0.25)       # 15 min
_geom("R1", ART, "return", RETURN, 6.9, 1.1)        # 66 min
_geom("R1", R8, "loaded", LOADED[:50], 3.4, 0.2)    # a second vehicle, shorter (drawn only when asked for)
_geom("R2", ART, "loaded", [(-1.2, LAT), (-0.9, LAT)], 20.0, 0.5)
# R3 has no stored road route at all


def hav(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


# =========================================================================== #
#  1. C2: the typed words                                                     #
# =========================================================================== #
ok("⭐ the three new columns are in the DDL (the SQLite rebuild keeps only those) AND ALTERed on an existing database",
   "route_reason TEXT" in db._TENANT_DDL["routes"] and "permitted_deviations TEXT" in db._TENANT_DDL["routes"]
   and "site_rules         TEXT" in db._TENANT_DDL["locations"]
   and all(f'("{t}", "{c}", "TEXT")' in read("backend/db.py") for t, c in
           (("routes", "route_reason"), ("routes", "permitted_deviations"), ("locations", "site_rules"))))
ok("...and the belt-and-braces location guard knows site_rules", '("site_rules", "TEXT")' in read("backend/network.py"))
ok("the cap is 400 characters: what fits in a block on the one page", network.SHEET_TEXT_MAX == 400)
r = network.set_route_sheet_text("R1", {"route_reason"}, route_reason="  Agreed in the CLP: avoids the village centre.  ")
ok("⭐ a reason is stored trimmed; the field NOT sent is left alone (None here)",
   r == {"id": "R1", "route_reason": "Agreed in the CLP: avoids the village centre.", "permitted_deviations": None}, str(r))
r = network.set_route_sheet_text("R1", {"permitted_deviations"}, permitted_deviations="The signed diversion only.")
ok("...sending only the diversions keeps the reason", r["route_reason"] == "Agreed in the CLP: avoids the village centre."
   and r["permitted_deviations"] == "The signed diversion only.", str(r))
r = network.set_route_sheet_text("R1", {"permitted_deviations"}, permitted_deviations="   ")
ok("🔴 blank clears to None (never an empty string in the database)", r["permitted_deviations"] is None
   and db.query("SELECT permitted_deviations FROM routes WHERE id = 'R1'")[0]["permitted_deviations"] is None)
r = network.set_route_sheet_text("R1", {"route_reason"}, route_reason="x" * 401)
ok("🔴 401 characters are refused in words, and nothing is written",
   r == {"error": "why this route is 401 characters: at most 400 fit on the route sheet"}
   and db.query("SELECT route_reason FROM routes WHERE id = 'R1'")[0]["route_reason"] == "Agreed in the CLP: avoids the village centre.", str(r))
ok("...400 exactly is taken; text that is not text is refused; an unknown route is 'route not found'",
   network.set_route_sheet_text("R2", {"route_reason"}, route_reason="y" * 400)["route_reason"] == "y" * 400
   and network.set_route_sheet_text("R2", {"route_reason"}, route_reason=5) == {"error": "why this route must be text"}
   and network.set_route_sheet_text("R9", {"route_reason"}, route_reason="a") == {"error": "route not found"})
network.set_route_sheet_text("R2", {"route_reason"}, route_reason=None)
network.set_route_sheet_text("R1", {"permitted_deviations"}, permitted_deviations="If the A-road is closed: the signed diversion only.")
ok("⭐ the site rules on a location: trimmed, blank clears, 401 refused, an unknown location 'not found'",
   network.set_site_rules("L2", " 15 mph on site. ") == {"id": "L2", "site_rules": "15 mph on site."}
   and network.set_site_rules("L1", "") == {"id": "L1", "site_rules": None}
   and network.set_site_rules("L2", "z" * 401) == {"error": "the site rules is 401 characters: at most 400 fit on the route sheet"}
   and network.set_site_rules("L9", "a") == {"error": "not found"}
   and db.query("SELECT site_rules FROM locations WHERE id = 'L2'")[0]["site_rules"] == "15 mph on site.")
_st = {x["id"]: x for x in network.routes_status()}
ok("⭐ the Routes page read carries both words (None when not typed)",
   _st["R1"]["route_reason"] == "Agreed in the CLP: avoids the village centre."
   and _st["R1"]["permitted_deviations"] == "If the A-road is closed: the signed diversion only."
   and _st["R2"]["route_reason"] is None and _st["R2"]["permitted_deviations"] is None)
_pm = [f["properties"] for f in network.public_map_data()["features"] if f["properties"].get("route_id") == "R1"]
ok("⭐ the public map's route features carry both words on BOTH legs (the route card reads them)",
   len(_pm) == 2 and {p["leg"] for p in _pm} == {"loaded", "return"}
   and all(p["route_reason"] == "Agreed in the CLP: avoids the village centre." for p in _pm)
   and all(p["permitted_deviations"].startswith("If the A-road") for p in _pm), str(_pm)[:200])
_loc = {f["properties"]["id"]: f["properties"] for f in network.locations_geojson()["features"]}
ok("the location read carries the site rules (the form fills its box from it)",
   _loc["L2"]["site_rules"] == "15 mph on site." and _loc["L1"]["site_rules"] is None)
_pkg = tenant_package.export_tenant()
ok("⭐ the words travel in the tenant package (a column is a column: nothing to add to ORDER)",
   {r_["id"]: r_["route_reason"] for r_ in _pkg["tables"]["routes"]}["R1"] == "Agreed in the CLP: avoids the village centre."
   and {l_["id"]: l_["site_rules"] for l_ in _pkg["tables"]["locations"]}["L2"] == "15 mph on site.")

# =========================================================================== #
#  2. C3: what the sheet prints, as data                                       #
# =========================================================================== #
# the gates at the site: one way in near the road's end, one way out 330 m south of where the return starts
G_IN = gates.create_gate("L2", "North gate", LAT + 0.0003, -0.9, direction="access", open_from="07:00", open_to="18:00",
                         open_days="1111100")
G_OUT = gates.create_gate("L2", "South gate", LAT - 0.003, -0.9, direction="egress")
_doc = conversions.load_factors()
_doc["planning"]["peak_bands"] = [{"from": "07:00", "to": "09:00"}, {"from": "15:00", "to": "16:00"}]
config.save(_doc, by="tester"); config.invalidate()
network.set_site_rules("L1", "Report to the weighbridge.")

S = rs.sheet("R1", acc=PLANNER)
ok("⭐ the route by its places and team NAME, the vehicle drawn: the default lorry, baked",
   S["origin"] == "Kelsey Quarry" and S["dest"] == "Mill Compound" and S["team"] == "North Team"
   and S["vehicle"] == ART and S["baked_vehicles"] == sorted([ART, R8]) and S["drawn"] is True, str(S["team"]))
ok("...the legs as stored, A to B and back", S["loaded"] == LOADED and S["return"] == RETURN)
_du = export._du()
_k = lambda km: f"{export._dist(km):.1f} {_du}"
ok("⭐ the distances in the tenant's unit and the driving time, by hand: 15 min loaded, 1 h 06 min back",
   S["loaded_words"] == f"{_k(6.8)}, about 15 min driving" and S["return_words"] == f"{_k(6.9)}, about 1 h 06 min driving",
   f"{S['loaded_words']} | {S['return_words']}")
_in, _out = S["last_mile_in"], S["last_mile_out"]
_len = lambda pts: sum(hav(a, b) for a, b in zip(pts, pts[1:]))
ok("⭐ THE LAST MILE by hand: the loaded leg's last vertices until 1.5 km along the line is reached (23 steps of ~67.7 m), "
   "ending at B; the return's first, starting at B",
   _in[-1] == LOADED[-1] and _out[0] == RETURN[0] and len(_in) == 24 and len(_out) == 24
   and _len(_in) >= 1500 > _len(_in[1:]) and _len(_out) >= 1500 > _len(_out[:-1]), f"{len(_in)} {_len(_in):.0f}")
ok("...rs.within on a line shorter than the reach keeps the whole line", rs.within(LOADED[:3], 1500) == LOADED[:3]
   and rs.within([], 1500) == [])
e, x_ = S["entry"], S["exit"]
ok("⭐ the gates the BAKE uses: entry = the access gate (default for arriving), exit = the egress gate; hours, closed days",
   e["name"] == "North gate" and e["hours"] == "07:00–18:00" and e["closed"] == "closed on Saturdays and Sundays"
   and x_["name"] == "South gate" and x_["hours"] is None and x_["closed"] is None, f"{e} {x_}")
ok("...the scheme's no-delivery windows in words", S["peak_words"] == "07:00–09:00 and 15:00–16:00")
# CHANGED 16 Oct 2026 (the user: "gates are usually right by the public road with a suitable bellmouth … ensure there is a
# haul road drawn to every gate"): the note says what to do — draw the gate's access road (none here) — and the threshold
# fell from 200 m to 50 m (a bellmouth for two 16.5 m lorries, and a margin): a route with its access road ends AT the gate
ok("⭐ the leg's gap to its gate, in metres, by hand: 33 m to the North gate (inside 50 m: no note), 334 m to the South gate "
   "(a note: draw its access road)",
   e["gap_m"] == round(hav(e["at"], LOADED[-1])) == 33 and x_["gap_m"] == round(hav(x_["at"], RETURN[0])) == 334
   and S["gate_notes"] == ["The return route on file starts 334 m from South gate: draw the gate's access road from the public "
                           "road, then work the route out again."]
   and S["same_gate"] is False and rs.GATE_FAR_M == 50.0, f"{e['gap_m']} {x_['gap_m']} {S['gate_notes']}")
# a gate that HAS its access road but whose stored route ends far from it: the route is stale, so the note says re-work it
_zr = zones.create_zone("South gate access road", {"type": "LineString", "coordinates": [[-0.9, LAT - 0.0035], [-0.9, LAT - 0.003]]},
                        kind=zones.HAUL_KIND, speed_kph=10, haul_mode="splice")
gates.update_gate(G_OUT["id"], access_zone_id=_zr["id"])
ok("...a gate WITH its access road and a route ending far from it: 'work the route out again (the gate or its access road has "
   "moved since)'", rs.sheet("R1", acc=PLANNER)["gate_notes"] == [
       "The return route on file starts 334 m from South gate: work the route out again (the gate or its access road has moved since)."])
gates.update_gate(G_OUT["id"], access_zone_id="")
db.execute("UPDATE route_geometry SET geometry = ? WHERE route_id = 'R1' AND vehicle_profile = ? AND leg = 'return'",
           (json.dumps([[-0.9, LAT - 0.003 + 0.0002]] + [list(c) for c in RETURN]), ART))
ok("🔴 ...a leg starting 22 m from its gate (inside the bellmouth threshold) gets no note",
   rs.sheet("R1", acc=PLANNER)["gate_notes"] == [] and rs.sheet("R1", acc=PLANNER)["exit"]["gap_m"] == 22,
   str(rs.sheet("R1", acc=PLANNER)["exit"]["gap_m"]))
db.execute("UPDATE route_geometry SET geometry = ? WHERE route_id = 'R1' AND vehicle_profile = ? AND leg = 'return'",
           (json.dumps([list(c) for c in RETURN]), ART))
ok("...the typed words and the site rules at BOTH ends", S["route_reason"] == "Agreed in the CLP: avoids the village centre."
   and S["site_rules_dest"] == "15 mph on site." and S["site_rules_origin"] == "Report to the weighbridge.")
# a route gate id picks the gate (the bake's rule): R1 told to use the South gate both ways is refused for entry (egress only)
db.execute("UPDATE routes SET dest_gate_id = ? WHERE id = 'R1'", (G_OUT["id"],))
_sg = rs.sheet("R1", acc=PLANNER)
ok("🔴 a route naming an egress-only gate still ARRIVES by a gate that takes arrivals (gates.resolve's fall-through)",
   _sg["entry"]["name"] == "North gate" and _sg["exit"]["name"] == "South gate")
db.execute("UPDATE routes SET dest_gate_id = NULL WHERE id = 'R1'")
# one gate both ways
_both = gates.create_gate("L3", "Pit gate", LAT, -1.2, direction="both")
db.execute("UPDATE routes SET origin_id = 'L2', dest_id = 'L3' WHERE id = 'R3'")
_geom("R3", ART, "loaded", [(-0.9, LAT), (-1.19, LAT)], 20.0, 0.5)
_geom("R3", ART, "return", [(-1.19, LAT), (-0.9, LAT)], 20.0, 0.5)
S3 = rs.sheet("R3", acc=PLANNER)
ok("⭐ ONE gate both ways: drawn and named once; a leg ending 677 m from it gets ONE note for both",
   S3["same_gate"] is True and S3["entry"]["name"] == S3["exit"]["name"] == "Pit gate"
   and S3["gate_notes"] == [f"The route on file ends and starts {S3['entry']['gap_m']:,} m from Pit gate: draw the gate's access "
                            "road from the public road, then work the route out again."]
   and S3["entry"]["gap_m"] == round(hav((-1.2, LAT), (-1.19, LAT))), str(S3["gate_notes"]))
db.execute("DELETE FROM route_geometry WHERE route_id = 'R3'")
db.execute("UPDATE routes SET origin_id = 'L1', dest_id = 'L2' WHERE id = 'R3'")
S3 = rs.sheet("R3", acc=PLANNER)
ok("🔴 a route with no stored road route: nothing drawn, no last mile, no gate note, the limits say so",
   S3["drawn"] is False and S3["loaded"] == [] and S3["last_mile_in"] == [] and S3["gate_notes"] == []
   and S3["vehicle"] is None and S3["loaded_words"] is None
   and S3["limits_lines"] == ["No road route has been worked out for this route yet."])
ok("the vehicle can be asked for (a baked one); an unbaked one falls back to the default",
   rs.sheet("R1", vehicle=R8, acc=PLANNER)["loaded"] == LOADED[:50] and rs.sheet("R1", vehicle="Nope", acc=PLANNER)["vehicle"] == ART)


def _err(rid, acc):
    try:
        rs.sheet(rid, acc=acc)
        return None
    except rs.SheetError as ex:
        return str(ex)


ok("⭐ a team code reads its OWN team's routes only: North gets R1, not Central's R2 (the same words as an unknown route)",
   _err("R1", TEAM1) is None and _err("R2", TEAM1) == "no route R2" and _err("R2", TEAM2) is None
   and _err("R9", PLANNER) == "no route R9")

# ---- the lorry-limits words, every stored state ----


def _hit(verdict, headline="Weight limit 7.5 t", leg="loaded", prof=ART):
    return {"vehicle_profile": prof, "vehicle_label": prof, "leg": leg, "source": "osm", "ext_id": "w1", "kind": "weight",
            "limit": 7.5, "unit": "t", "headline": headline, "exceptions": None, "point": False, "verdict": verdict,
            "vehicle_value": 44, "margin": None, "note": None}


def _lim(hits, status="ok", at="2026-10-13T12:00:00+00:00"):
    db.execute("UPDATE routes SET limits_hits = ?, limits_checked_at = ?, limits_status = ? WHERE id = 'R1'",
               (json.dumps(hits) if hits is not None else None, at, status))
    s_ = rs.sheet("R1", acc=PLANNER)
    return s_["limits_status"], s_["limits_lines"]


_lab = conversions.vehicle_label(conversions.load_factors(), ART)
ok("🔴 never checked: says so, and to follow the signs", _lim(None, None, None) == ("not_checked", ["Not checked yet on this route. Follow the road signs."]))
ok("...a check that failed: says it did not finish", _lim(None, "error: boom") == ("not_checked", ["The last check (2026-10-13) did not finish. Follow the road signs."]))
ok("⭐ checked, nothing along it: 'No stored ... limit along this route', the date, the signs first",
   _lim([]) == ("clear", ["No stored weight, height or width limit along this route (checked 2026-10-13). The signs on the road come first."]))
ok("...checked, two limits within this lorry, one over ANOTHER vehicle: 'None of the 2 ...' (the other vehicle's hits are not counted)",
   _lim([_hit("within"), _hit("within", "Height limit 5 m"), _hit("exceeds", prof=R8)])
   == ("clear", [f"None of the 2 stored weight, height or width limits along this route is below the {_lab} (checked 2026-10-13). "
                 "The signs on the road come first."]))
ok("⭐ at the limit / not known: 'to look at', each named, never called clear",
   _lim([_hit("at_limit"), _hit("unknown", "Width limit 2.5 m")])
   == ("look", ["Weight limit 7.5 t: at the limit for this lorry", "Width limit 2.5 m: not known for this lorry",
                f"None is below the {_lab} (checked 2026-10-13). The signs on the road come first."]))
_o = _lim([_hit("exceeds", f"Weight limit {n} t") for n in range(1, 6)])
ok("⭐ OVER: the first three by limits.breach_text (the clash rail's words), '+2 more', ask the site team",
   _o[0] == "over" and _o[1][:3] == [__import__("limits").breach_text([_hit("exceeds", f"Weight limit {n} t")], ART) for n in (1, 2, 3)]
   and _o[1][3] == "+2 more" and _o[1][4] == "Checked 2026-10-13. Ask the site team before running this vehicle on this route.", str(_o))
_lim(None, None, None)

# =========================================================================== #
#  3. The PDF                                                                  #
# =========================================================================== #
S = rs.sheet("R1", acc=PLANNER)
PDF = export.build_route_sheet_pdf(S)
T = flat(PDF)
ok("⭐ ONE A4 PORTRAIT page; title, places, the route's id, team and vehicle in words, issued date",
   PDF[:5] == b"%PDF-" and PDF.count(b"/Type /Page\n") == 1 and b"/MediaBox [ 0 0 595.2756 841.8898 ]" in PDF
   and "Route sheet" in T and "Kelsey Quarry to Mill Compound" in T and "R1 · North Team · Small aggregate · drawn for the" in T
   and f"Issued {S['issued']}" in T, T[:300])
ok("⭐ the legend and the last mile, the arriving and leaving blocks with the gate, hours, closed days and the windows",
   f"Loaded, A to B: {S['loaded_words']}" in T and "Empty, back to A" in T and "The last mile: about 1.5 km in and out of B" in T
   and "Arriving at B, Mill Compound" in T and "Gate in: North gate" in T and "Open 07:00–18:00, closed on Saturdays and Sundays" in T
   and "No deliveries 07:00–09:00 and 15:00–16:00 (the scheme's no-delivery windows)" in T
   and "Leaving B" in T and "Gate out: South gate" in T and f"Then follow the amber route back to A: {S['return_words']}." in T   # NARROWED 23 Oct 2026: amber, solid
   and "Gate in" in T and "Gate out" in T, T)
# two columns: the text comes out a row at a time (both headings, then both bodies), so each row is checked in that order
ok("⭐ the typed words under their headings, two to a row; 'Not typed' nowhere here (nothing is missing); the gate note in metres",
   "Why this route Permitted diversions Agreed in the CLP: avoids the village centre. If the A-road is closed: the signed diversion only." in T
   and "Site rules at B, Mill Compound Site rules at A, Kelsey Quarry 15 mph on site. Report to the weighbridge." in T
   and "Not typed" not in T and "starts 334 m from South gate" in T, T)
network.set_site_rules("L1", None)
network.set_route_sheet_text("R1", {"permitted_deviations"}, permitted_deviations=None)
T2 = flat(export.build_route_sheet_pdf(rs.sheet("R1", acc=PLANNER)))
ok("🔴 an empty field reads 'Not typed' under its heading, never vanishes",
   "Why this route Permitted diversions Agreed in the CLP: avoids the village centre. Not typed" in T2
   and "Site rules at B, Mill Compound Site rules at A, Kelsey Quarry 15 mph on site. Not typed" in T2, T2[-500:])
ok("⭐ the footer: a planning document, the site team and the signs first; no Mapbox credit for a map it did not draw (offline)",
   "A planning document: the site team's instructions and the road signs come first." in T and "Mapbox" not in T
   and S.get("basemap") is False)
ok("🔴 no team id, no 'truck', no 'baked' / 'geometry' / 'server' where a person reads it",
   not re.search(r"\bIPT ?\d\b", T) and not re.search(r"\btrucks?\b", T, re.I)
   and not re.search(r"\b(un)?baked?\b|\bgeometry\b|\bserver\b|\bendpoint\b", T, re.I), T)
_rn = export._demo_notice
export._demo_notice = lambda: "Fictional scheme"
try:
    SD = rs.sheet("R1", acc=PLANNER)
    TD = flat(export.build_route_sheet_pdf(SD))
finally:
    export._demo_notice = _rn
ok("⭐ on a demo tenant: 'DEMO · Fictional scheme' in the heading and the 'Demo - fictional scheme' tag on BOTH maps",
   "DEMO · Fictional scheme" in TD and TD.count("Demo - fictional scheme") == 2 and SD["map_demo_tag"] == bulletin_doc.DEMO_MAP_TAG, TD[:300])
# the longest words in all four fields still make one page
network.set_route_sheet_text("R1", {"route_reason", "permitted_deviations"}, route_reason="Wide words make long lines. " * 14,
                             permitted_deviations="Wide words make long lines. " * 14)
network.set_site_rules("L1", ("Mmmm wwww " * 40)[:400]); network.set_site_rules("L2", ("Mmmm wwww " * 40)[:400])
_lim([_hit("exceeds", f"Weight limit {n} t on a long named road with exceptions") for n in range(1, 9)])
SL = rs.sheet("R1", acc=PLANNER)
PL = export.build_route_sheet_pdf(SL)
ok("⭐ the LONGEST case (400 characters in all four fields, eight limits over, a gate note) is still ONE page, above the footer, "
   "the body text stepped down from 8.4 pt",
   PL.count(b"/Type /Page\n") == 1 and SL["lowest_y"] >= SL["footer_top"] and SL["body_size"] in export.RS_BODY_SIZES
   and SL["body_size"] < export.RS_BODY_SIZES[0], f"{SL['body_size']} {SL['lowest_y']:.1f} {SL['footer_top']:.1f}")
ok("...the sizes step 8.4, 7.8, 7.2 and the normal case keeps the largest", export.RS_BODY_SIZES == (8.4, 7.8, 7.2)
   and S["body_size"] == 8.4)

# 17 Oct 2026 (the user): the default gate hours (08:00–17:00) and a gate's shut times, on the drivers' sheet
ok("⭐ a gate with no hours typed never has the default printed as its own: `hours` stays None, the default rides beside",
   S["exit"]["hours"] is None and S["exit"]["default_hours"] == "08:00–17:00" and S["entry"]["default_hours"] is None
   and S["entry"]["hours"] == "07:00–18:00", f"{S['entry']} {S['exit']}")
_arr0, _lv0 = export.route_sheet_lines(dict(S, entry=dict(S["entry"], hours=None, default_hours="08:00–17:00")))
ok("...an untyped gate in reads 'Open hours: none typed for this gate (planned on 08:00–17:00, the default)' — not 'Not typed'",
   _arr0[1] == "Open hours: none typed for this gate (planned on 08:00–17:00, the default), closed on Saturdays and Sundays"
   and "Not typed" not in _arr0[1], str(_arr0))
gates.update_gate(G_IN["id"], shut_windows=[{"from": "12:00", "to": "12:30"}, {"from": "08:30", "to": "09:15"}])
S2 = rs.sheet("R1", acc=PLANNER)
P2 = export.build_route_sheet_pdf(S2)
T3 = flat(P2)
ok("⭐ the gate in's shut times print on their own line ('Gate shut 08:30–09:15 and 12:00–12:30'), the sheet still one page",
   S2["entry"]["name"] == "North gate" and S2["entry"]["shut"] == "08:30–09:15 and 12:00–12:30"
   and "Gate shut 08:30–09:15 and 12:00–12:30" in T3 and P2.count(b"/Type /Page\n") == 1, T3[:500])
_arr1, _lv1 = export.route_sheet_lines(dict(S2, exit=dict(S2["exit"], shut="12:00–12:30")))
ok("...a different gate out names its own shut times on the 'Gate out' line; one gate both ways does not repeat them",
   _lv1[0] == "Gate out: South gate (shut 12:00–12:30)"
   and export.route_sheet_lines(dict(S2, exit=dict(S2["entry"])))[1][0] == "Gate out: North gate", str(_lv1))
_arr2, _lv2 = export.route_sheet_lines(dict(S2, load_entry={"name": "Weighbridge (in)", "hours": None, "default_hours": "08:00–17:00",
                                                             "shut": "12:00–12:30", "closed": "closed on Sundays"}))
ok("⭐ the review: A's gate IN (where the lorry comes to load, timed by the Dashboard and the Simulation) gets its hours or the "
   "default said so, closed days and shut times, before 'leave loaded by'",
   "At A, come in by Weighbridge (in): open hours none typed (planned on 08:00–17:00, the default), closed on Sundays, shut 12:00–12:30." in _lv2
   and _lv2.index("At A, come in by Weighbridge (in): open hours none typed (planned on 08:00–17:00, the default), closed on Sundays, shut 12:00–12:30.")
   < next((i for i, x in enumerate(_lv2) if x.startswith("At A, leave loaded by")), 99)
   and not any(x.startswith("At A, leave loaded by") for x in export.route_sheet_lines(dict(S2, load_entry={}))[1] if not S2["load_exit"].get("name")),
   str(_lv2))
# the LONGEST case again with every new line: four shut times on the gate in, four on the gate out, A's gate in typed
gates.update_gate(G_IN["id"], shut_windows=[{"from": "08:00", "to": "08:30"}, {"from": "10:00", "to": "10:30"},
                                            {"from": "12:00", "to": "12:30"}, {"from": "15:00", "to": "15:30"}])
gates.update_gate(G_OUT["id"], shut_windows=[{"from": "08:10", "to": "08:40"}, {"from": "10:10", "to": "10:40"},
                                             {"from": "12:10", "to": "12:40"}, {"from": "15:10", "to": "15:40"}])
SL2 = rs.sheet("R1", acc=PLANNER)
PL2 = export.build_route_sheet_pdf(SL2)
TL2 = flat(PL2)
ok("⭐ the LONGEST case with four shut times on each gate is still ONE page above the footer, both shut lines printed",
   PL2.count(b"/Type /Page\n") == 1 and SL2["lowest_y"] >= SL2["footer_top"]
   and "Gate shut 08:00–08:30, 10:00–10:30, 12:00–12:30 and 15:00–15:30" in TL2 and "(shut 08:10–08:40," in TL2,
   f"{SL2['body_size']} {SL2['lowest_y']:.1f} {SL2['footer_top']:.1f} " + TL2[:200])
gates.update_gate(G_OUT["id"], shut_windows=[])
gates.update_gate(G_IN["id"], shut_windows=[])
ok("clearing the shut times takes the line off the sheet", rs.sheet("R1", acc=PLANNER)["entry"]["shut"] is None
   and "Gate shut" not in flat(export.build_route_sheet_pdf(rs.sheet("R1", acc=PLANNER))))
_lim(None, None, None)
TE = flat(export.build_route_sheet_pdf(rs.sheet("R3", acc=PLANNER)))
ok("🔴 a route with no stored road route still makes its page, and says so on the map",
   "No road route has been worked out for this route yet." in TE and "Route sheet" in TE)
ok("the file is named for the route, safely", rs.file_name({"route_id": "R1"}) == "route-sheet-R1.pdf"
   and rs.file_name({"route_id": "R/1 x"}) == "route-sheet-R-1-x.pdf")
ok("⭐ the return leg is drawn BESIDE the loaded one (3.2 pt to the left of travel) so a road used both ways shows both",
   export._rs_offset([(0, 0), (10, 0)], 3.2) == [(0, 3.2), (10, 3.2)] and export._rs_offset([(0, 0), (10, 0)], 0) == [(0, 0), (10, 0)])
ok("...the maps frame the gates as well as the last mile (a gate just off the road's end is on the map)",
   'near += [g["at"] for g in (S["entry"], S["exit"]) if g.get("at")]' in read("backend/route_sheet.py"))
ok("one read, nothing stored: the module writes nothing", "db.execute" not in read("backend/route_sheet.py")
   and "UPDATE" not in read("backend/route_sheet.py") and "INSERT" not in read("backend/route_sheet.py"))

# =========================================================================== #
#  4. The endpoints (source; http_smoke drives them over HTTP)                 #
# =========================================================================== #
_mn = read("backend/main.py")
_ep = _mn[_mn.index('@app.get("/api/routes/{route_id}/route-sheet.pdf")'):_mn.index("def _route_map_plan(")]
ok("⭐ the route sheet is STAFF ONLY (_staff_request, 401), a team code is held to its own team (SheetError = 404), "
   "named for the route, never cached",
   "if not _staff_request(request):" in _ep and 'raise HTTPException(401, "sign in — the route sheet is for staff")' in _ep
   and "route_sheet.sheet(route_id, vehicle=vehicle, acc=access.current())" in _ep
   and "except route_sheet.SheetError as e:\n        raise HTTPException(404, str(e))" in _ep
   and "route_sheet.file_name(S)" in _ep and '"Cache-Control": "no-store"' in _ep)
_sx = _mn[_mn.index("class RouteSheetText(BaseModel):"):_mn.index('@app.delete("/api/admin/routes/{route_id}")')]
ok("⭐ the words are written by an ADMIN (_check_admin), only the fields sent, 404 / 400 in words",
   '@app.put("/api/admin/routes/{route_id}/sheet-text")' in _sx and "_check_admin(token)" in _sx
   and "network.set_route_sheet_text(route_id, sent, **{k: getattr(body, k) for k in sent})" in _sx
   and 'raise HTTPException(404 if res["error"] == "route not found" else 400, res["error"])' in _sx)
ok("...the location's site rules: on create when given, on update ONLY when sent (an older client cannot blank them), "
   "refused over 400 before anything is written",
   "site_rules: Optional[str] = None" in _mn and 'rules_given = "site_rules" in set(_fields_set(body))' in _mn
   and "network.set_site_rules(location_id, body.site_rules)" in _mn and "network.set_site_rules(out[\"id\"], body.site_rules)" in _mn
   and 'network.sheet_text_problem(body.site_rules, "the site rules")' in _mn)

# =========================================================================== #
#  5. The screens (source)                                                     #
# =========================================================================== #
_fe = read("frontend/index.html")
ok("⭐ the Routes page: the 'Route sheet · drivers' panel under the planning figures, with the two boxes, a counter, its own save",
   "function RouteSheetText({ route, token, onSaved })" in _fe
   and "{editingRoute && <RouteSheetText route={(status || []).find(r => r.id === editingRoute) || {}} token={token} onSaved={reloadNetwork} />}" in _fe
   and 'label: "Why this route"' in _fe and 'label: "Permitted diversions"' in _fe
   and "`${API}/admin/routes/${encodeURIComponent(route.id)}/sheet-text${qs}`" in _fe and "of {SHEET_TEXT_MAX} characters" in _fe)
ok("...the app's cap is the server's (400), and over it the save is disabled",
   f"const SHEET_TEXT_MAX = {network.SHEET_TEXT_MAX};" in _fe and 'disabled={busy || over("route_reason") || over("permitted_deviations")}' in _fe)
ok("⭐ the download button beside the route map export, for the route picked in the list, and in the panel",
   "<RouteSheetButton routeId={selected} />" in _fe and "<RouteSheetButton routeId={route.id} />" in _fe
   and "`${API}/routes/${encodeURIComponent(routeId)}/route-sheet.pdf`" in _fe and "Route sheet (drivers)" in _fe)
ok("⭐ the location form's 'Site rules for drivers' box, sent as null when blank",
   "Site rules for drivers (optional)" in _fe and 'site_rules: (f.site_rules || "").trim() || null,' in _fe
   and 'site_rules: p.site_rules || "" });' in _fe)
_mp = read("map/index.html")
ok("⭐ the public map: the route card and the route analysis both show the typed words, escaped, and only when typed",
   "function routeWordsHTML(rid)" in _mp and "html += routeWordsHTML(rid);" in _mp and "routeWordsHTML(routeId)+" in _mp
   and "escHtml(String(r[1]).trim())" in _mp and ".filter(r => r[1] && String(r[1]).trim())" in _mp)
# 16 Oct 2026 (browser check): the rules first landed INSIDE the phone-only @media block, so the desktop's route analysis
# showed the words unstyled at 16 px. Brace depth from the start of the stylesheet to the rule must be 0 (top level).
_css0 = _mp.index("<style")
_at = _mp.index(".route-words{")
_seg = _mp[_mp.index(">", _css0) + 1:_at]
ok("🔴 the route words' CSS is at the TOP level of the map's stylesheet (not inside the phone-only block): 14 px everywhere",
   _seg.count("{") - _seg.count("}") == 0 and "</style>" not in _seg
   and ".route-words p{ margin:0; font-size:14px;" in _mp, str(_seg.count("{") - _seg.count("}")))

# =========================================================================== #
print()

# =========================================================================== #
#  23 Oct 2026 — the route line redesign on paper: the legs go into the        #
#  picture under the road names, the haul-road stretches are dotted            #
# =========================================================================== #
# the split on its own: a five-point leg, the middle three on a two-point haul road 220 m long
_road = [(-0.9, 52.5), (-0.9, 52.502)]
_leg5 = [(-0.91, 52.499), (-0.9, 52.5), (-0.9, 52.501), (-0.9, 52.502), (-0.89, 52.503)]
_pc = rs.haul_pieces(_leg5, [_road])
ok("⭐ 23 Oct: haul_pieces — the three points on the haul road are one piece, in the leg's order; the public ends stay off it",
   _pc == [[(-0.9, 52.5), (-0.9, 52.501), (-0.9, 52.502)]], str(_pc))
ok("23 Oct: no road, nothing; a leg 50 m off the road, nothing; a lone point on the road is no piece",
   rs.haul_pieces(_leg5, []) == [] and rs.haul_pieces([(-0.9008, 52.5), (-0.9008, 52.502)], [_road]) == []
   and rs.haul_pieces([(-0.91, 52.499), (-0.9, 52.5), (-0.89, 52.503)], [_road]) == [])
# on the fixture: a haul road drawn along three consecutive vertices of R1's road (STEP apart, 67.7 m)
_zh = zones.create_zone("Mid-route haul road", {"type": "LineString", "coordinates": [list(LOADED[40]), list(LOADED[42])]},
                        kind=zones.HAUL_KIND, speed_kph=10, haul_mode="splice")
SH = rs.sheet("R1", acc=PLANNER)
_r6 = lambda pieces: [[(round(a, 6), round(b, 6)) for a, b in p] for p in pieces]
ok("⭐ 23 Oct: the sheet carries the haul-road stretches of both legs (three points each here) and none in the last mile",
   _r6(SH["haul_loaded"]) == [[LOADED[40], LOADED[41], LOADED[42]]] and _r6(SH["haul_return"]) == [[LOADED[42], LOADED[41], LOADED[40]]]
   and SH["haul_last_in"] == [] and SH["haul_last_out"] == [], str((SH["haul_loaded"], SH["haul_return"]))[:300])
TH = flat(export.build_route_sheet_pdf(SH))
ok("23 Oct: the legend names the loaded leg, the empty return and the haul road; the leaving words say the amber route, never a dashed one",
   "Loaded, A to B" in TH and "Empty, back to A" in TH and "On a haul road" in TH and "Then follow the amber route back to A" in TH
   and "dashed" not in TH, TH[:400])
# the legs go into the basemap request as path overlays under the road names, when the URL fits
_calls = []
_bio = io.BytesIO(); PILImage.new("RGB", (4, 4), (250, 250, 250)).save(_bio, "PNG"); _PNG4 = _bio.getvalue()
_real_fetch = basemap.fetch
basemap.fetch = lambda v, token=None, timeout=12, retina=True, overlays=None, before_layer=None, style=None: (_calls.append((v, overlays, before_layer)), _PNG4)[1]
try:
    SP = rs.sheet("R1", acc=PLANNER)
    PDFP = export.build_route_sheet_pdf(SP)
finally:
    basemap.fetch = _real_fetch
_ov = [c_ for c_ in _calls if c_[1]]
ok("⭐ 23 Oct: both maps ask Mapbox for the picture WITH the legs under the road names: four path overlays each — two white edges, "
   "then green and amber — before road-label-simple; the sheet records that the legs are in the picture",
   len(_calls) == 2 and len(_ov) == 2 and SP.get("map_legs_in_basemap") is True
   and all(bl == "road-label-simple" and len(ov) == 4 and all(o.startswith("path-") for o in ov) and "+ffffff-" in ov[0] and "+ffffff-" in ov[1]
           and "+059669-" in ov[2] and "+f59e0b-" in ov[3] for _, ov, bl in _ov),
   str([(bl, [o[:24] for o in (ov or [])]) for _, ov, bl in _calls])[:400])
ok("23 Oct: each request fits the API's URL limit, and the picture is drawn into the sheet",
   all(len(basemap.url(v, "", overlays=ov, before_layer=bl)) <= basemap.URL_MAX for v, ov, bl in _ov) and b"/Subtype /Image" in PDFP
   and basemap.URL_MAX == 7800 and basemap.LABELS_LAYER == "road-label-simple")
# the overlay helpers on their own: a URL with overlays carries them before the centre and the layer before the token; the
# polyline encoder round-trips Google's example; a simplified line keeps its ends; an offset line moves left of travel
_v0 = basemap.view([(-1.0, 52.5), (-0.9, 52.5)], 640, 300)
_u0 = basemap.url(_v0, "pk.x", overlays=["path-2+059669-1(abc)"], before_layer="road-label-simple")
ok("23 Oct: basemap.url puts the overlays before the centre and before_layer before the token; without overlays it is the plain URL",
   "/static/path-2+059669-1(abc)/" in _u0 and "?before_layer=road-label-simple&access_token=pk.x" in _u0
   and basemap.url(_v0, "pk.x") == basemap.url(_v0, "pk.x", overlays=None, before_layer="road-label-simple")
   and "before_layer" not in basemap.url(_v0, "pk.x"), _u0)
ok("23 Oct: encode_polyline round-trips Google's own example; simplify_px keeps a straight line's two ends; offset_lonlat moves a west-east line north (left of travel)",
   basemap.encode_polyline([(-120.2, 38.5), (-120.95, 40.7), (-126.453, 43.252)]) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
   and basemap.simplify_px(_v0, [(-1.0, 52.5), (-0.95, 52.5), (-0.9, 52.5)], 0.8) == [(-1.0, 52.5), (-0.9, 52.5)]
   and all(lat > 52.5 for _, lat in basemap.offset_lonlat(_v0, [(-1.0, 52.5), (-0.9, 52.5)], 4.0)))
ok("23 Oct: a refusal from Mapbox (an HTTP error) does not mark it down, so the plain picture can follow at once",
   "except urllib.error.HTTPError:" in open(os.path.join(BACKEND, "basemap.py"), encoding="utf-8").read())
zones.delete_zone(_zh["id"])

for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)

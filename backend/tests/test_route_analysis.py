"""
The Route analysis, 9 Nov 2026 (v2.1 task 2.1-6; mockup notes/route-analysis-mockup-1108/, John's yes to Q1-Q13).

WHAT IS ASSERTED
----------------
  1. The asks: sections (blank = all, in the file's order; an unknown one or only the assessor page refused in words),
     routes (1 to 12, in the order asked, no repeats), the file names (Q1).
  2. gather(): one lorry for the whole file (Q3: the first route's busiest Approved lorry when none is asked); section A
     from the STORED limit checks only — the picked lorry's, numbered A to B, the other lorries "the same" or listed
     (Q7), a diversion's limits apart; the closures said "not held" in words when none are held (Q8); section B the
     stored community places within the Routes page's distances, schools / hospitals / health NAMED and the rest counted
     (Q9); C the route collision evidence itself; D its cycle and left-turn figures; E the stored busy-hour times (Q11);
     F dated diversions only (Q12), a period with no way round said.
  3. A team login reads its own team's routes only (another team's = no such route).
  4. The PDF: the first page (routes side by side, the page list), each ticked section and only those, route by route
     (Q6), C as the evidence's own pages (its cycle block and assessor page left to D and the analysis's own page), the
     page for the assessor pointing at the sections, "not in this file" for an unticked one; no rate, no score, no
     "movements", no collision's hour.
  5. The XLSX: a sheet per ticked section only, the route in the first column, C the evidence workbook merged.
  6. export.build_collision_evidence_pdf: unchanged with no canvas (bytes, its own assessor page); into a canvas it returns
     the next page number and leaves out what it is told to (Q10, Q13).
  7. The endpoints: staff only (401), an unknown lorry 422, no route 404, another team's 404, one at a time (a second
     press answered busy, 503 in words), named and never cached; the old evidence addresses still there (Q13).
  8. Source level: stored data only (nothing fetched: no refresh / fetch / urlopen in the two modules), the build inside
     heavy_reads.solo("route-analysis"); the Routes page's menu replaces the two evidence buttons in both places, its
     sections the server's, the ticks remembered in try / catch, the 12 cap; the guides.

WHAT THIS DOES NOT PROVE
------------------------
  * Mapbox is never called (portable.offline): the maps are drawn on a grey ground here. The pictures were looked at
    by eye on a local copy (notes/session-1108-route-analysis.md).
  * The busy-hour times are given to hour_times.times_for() here, not stored from HERE.
  * Nothing renders in a browser; Postgres is not used.
"""
import io
import json
import os
import re
import sys
import tempfile
import threading
import types
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


class _HTTPException(Exception):
    def __init__(self, status_code, detail=None, headers=None):
        super().__init__(detail)
        self.status_code, self.detail, self.headers = status_code, detail, headers


class _App:
    def __init__(self, *a, **k):
        pass

    def _deco(self, *a, **k):
        return lambda f: f
    get = post = put = delete = patch = _deco

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


def _Query(default=None, **k):
    return default


class _Request:
    def __init__(self, headers=None, cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = dict(cookies or {})


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query
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

TMP = tempfile.mkdtemp(prefix="wayscope_route_analysis_")
from portable import remove_scratch_db, offline, pdf_text   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN", "MAP_PASSWORD"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import network  # noqa: E402
import collisions as cl  # noqa: E402
import export  # noqa: E402
import hour_times  # noqa: E402
import heavy_reads  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import route_analysis_doc as RA  # noqa: E402
import route_analysis_render as RR  # noqa: E402
offline(export)

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


def raises(fn):
    try:
        fn()
    except Exception as e:      # noqa: BLE001
        return e
    return None


def text(pdf):
    return " ".join(pdf_text(pdf, "").split())


# --------------------------------------------------------------------------- #
#  The scheme: two sites, R1 (team 1) A to B with an alternative, R2 (team 2) #
# --------------------------------------------------------------------------- #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)
config.invalidate()
T = db.current_tenant()
LAT0 = 52.60
DLAT = 1 / 110574.0
DLON = 1 / (111320.0 * 0.6074)
ROUTE = [[-0.95, LAT0], [-0.925, LAT0], [-0.90, LAT0]]
ALT = [[-0.95, LAT0 + 553 * DLAT], [-0.90, LAT0 + 553 * DLAT]]
BENT = [[-0.95, LAT0], [-0.925, LAT0 + 2000 * DLAT], [-0.90, LAT0]]
PROF = network.DEFAULT_PROFILE
OTHER = next(k for k in (conversions.load_factors().get("vehicles") or {}) if k != PROF)


def P(lon_m, lat_m, lon0=-0.925):
    return round(lon0 + lon_m * DLON, 6), round(LAT0 + lat_m * DLAT, 6)


for lid, name, lon in (("LA", "Quarry A", -0.95), ("LB", "Site B", -0.90)):
    db.execute("INSERT INTO locations (tenant_id, id, name, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)",
               (T, lid, name, "destination", LAT0, lon))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?, ?)", (T, "R1", "LA", "LB", "IPT1"))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?, ?)", (T, "R2", "LB", "LA", "IPT2"))
for rid, line in (("R1", ROUTE), ("R2", list(reversed(ROUTE)))):
    for prof in (PROF, OTHER):
        network._upsert_geom(rid, prof, json.dumps(line), 3.4, 0.1, None, leg="loaded", alt_index=0)
        network._upsert_geom(rid, prof, json.dumps(list(reversed(line))), 3.4, 0.1, None, leg="return", alt_index=0)
network._upsert_geom("R1", PROF, json.dumps(ALT), 3.6, 0.1, None, leg="loaded", alt_index=1)
# the plan: R1's busiest Approved lorry is OTHER (two lines), PROF one line
for fid, rid, mi, veh in (("F1", "R1", 10, OTHER), ("F2", "R1", 11, OTHER), ("F3", "R1", 11, PROF), ("F4", "R2", 11, PROF)):
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, vehicle_type, status, ipt) VALUES (?, ?, ?, ?, '', ?, ?, 't', ?, ?, 'Approved', 'IPT1')",
               (T, fid, rid, mi, fid, 2900.0, "General / imported", veh))
# section A: R1's stored limit check — a weight limit below both lorries (out and back), a height limit above PROF only,
# and one on the stored alternative (a diversion's)
HITS = []
for prof in (PROF, OTHER):
    for leg in ("loaded", "return"):
        HITS.append({"vehicle_profile": prof, "leg": leg, "source": "osm", "ext_id": "w1", "kind": "maxweight", "limit": 7.5, "vehicle_value": 44,
                     "unit": "t", "headline": "Weight limit 7.5 t", "name": "Station Road", "ref": None,
                     "exceptions": "Except for access", "point": False, "verdict": "exceeds", "anchor": list(P(-600, 0)),
                     "alt_index": 0})
HITS.append({"vehicle_profile": PROF, "leg": "loaded", "source": "osm", "ext_id": "h1", "kind": "maxheight", "limit": 4.4, "vehicle_value": 4.0,
             "unit": "m", "headline": "Height limit 4.4 m", "name": "Mill Lane", "ref": None, "exceptions": None,
             "point": True, "verdict": "within", "anchor": list(P(800, 12)), "alt_index": 0})
HITS.append({"vehicle_profile": PROF, "leg": "loaded", "source": "osm", "ext_id": "w9", "kind": "maxweight", "limit": 18, "vehicle_value": 44,
             "unit": "t", "headline": "Weight limit 18 t", "name": "Gartree Road", "ref": None, "exceptions": None,
             "point": False, "verdict": "exceeds", "anchor": list(P(0, 553)), "alt_index": 1})
db.execute("UPDATE routes SET limits_hits = ?, limits_checked_at = ?, limits_status = 'ok' WHERE tenant_id = ? AND id = ?",
           (json.dumps(HITS), "2026-11-02T10:00:00Z", T, "R1"))
# section B: a school and a health centre within 250 m, a bus stop within 100 m, a school 400 m away (out)
for fid, kind, name, ll in (("gias:1", "schools", "Test Primary", P(10, 100)), ("osm:2", "health", "Brook Surgery", P(900, -60)),
                            ("naptan:3", "bus_stops", "Mill Lane stop", P(300, 40)), ("gias:4", "schools", "Far School", P(0, -400))):
    db.execute("INSERT INTO community_features (tenant_id, feature_id, kind, source, source_ref, name, detail, geometry_json, "
               "dist_m, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (T, fid, kind, fid.split(":")[0], fid.split(":")[1], name, None,
                json.dumps({"type": "Point", "coordinates": list(ll)}), 0.0, "2026-11-01"))
db.execute("INSERT INTO community_meta (tenant_id, meta_id, state, fetched_at, detail_json) VALUES (?, ?, ?, ?, ?)",
           (T, __import__("community").META_ID, "done", "2026-11-01T09:00:00Z",
            json.dumps({"sources": {"gias": {"fetched_at": "2026-11-01"}, "osm": {"fetched_at": "2026-11-01"}}})))
# section C: the collision history fetched (DfT's files stubbed; three collisions on R1, one near it, one far)
C_HEAD = ("collision_index,collision_year,collision_ref_no,location_easting_osgr,location_northing_osgr,longitude,latitude,"
          "police_force,collision_severity,number_of_vehicles,number_of_casualties,date,day_of_week,time,"
          "local_authority_highway_current,first_road_class,first_road_number,road_type,speed_limit,junction_detail,"
          "second_road_class,second_road_number,light_conditions")
V_HEAD = "collision_index,collision_year,collision_ref_no,vehicle_reference,vehicle_type"
K_HEAD = ("collision_index,collision_year,collision_ref_no,vehicle_reference,casualty_reference,casualty_class,"
          "casualty_severity,casualty_type,escooter_flag")


def _files(table, y):
    if y != 2025:
        return {"collision": C_HEAD, "vehicle": V_HEAD, "casualty": K_HEAD}[table] + "\n"
    if table == "collision":
        pts = {"C1": (*P(0, 10), 2, "14/03/2025", "08:15"), "C2": (*P(30, 15), 3, "02/04/2025", "17:40"),
               "C3": (*P(-1000, 200), 1, "20/06/2025", "16:00"), "C8": (*P(1000, -5), 2, "30/12/2025", "23:05"),
               "C5": (-0.5, 52.0, 2, "01/07/2025", "08:15")}
        return "\n".join([C_HEAD] + [f"2025{k},2025,{k},0,0,{lon},{lat},33,{sev},2,1,{d},3,{t},E10000018,3,6,6,30,3,-1,0,1"
                                      for k, (lon, lat, sev, d, t) in pts.items()]) + "\n"
    if table == "vehicle":
        return "\n".join([V_HEAD, "2025C1,2025,C1,1,21", "2025C2,2025,C2,1,9"]) + "\n"
    return "\n".join([K_HEAD, "2025C1,2025,C1,1,1,3,2,0,0", "2025C2,2025,C2,1,1,1,3,1,0"]) + "\n"


def _dl(url, dest):
    m = re.search(r"-(collision|vehicle|casualty)-(\d{4})\.csv$", url.rsplit("/", 1)[-1])
    t = _files(m.group(1), int(m.group(2)))
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(t)
    return url, len(t)


_cst = cl.refresh(fetchers={"download": _dl}, today=date(2026, 10, 16))
ok("0: the fixture's collision history fetched (stubbed)", _cst["state"] == "done", str(_cst)[:300])
# section E: busy-hour times as stored (given here; see the docstring)
_HRS = {h: 0.40 + (0.08 if h in ("08:00", "17:00") else 0) for h in hour_times.HOURS}
hour_times.times_for = lambda rid: ({PROF: {"loaded": {0: dict(_HRS), 1: {h: v + 0.05 for h, v in _HRS.items()}},
                                            "return": {0: dict(_HRS), 1: dict(_HRS)}}} if rid == "R1" else {})

# --------------------------------------------------------------------------- #
#  1. The asks                                                                 #
# --------------------------------------------------------------------------- #
ok("1: the sections in the file's order, A to F then the assessor's page (Q6)",
   RA.SECTION_KEYS == ["limits", "community", "collisions", "cycle", "hours", "diversions", "assessor"]
   and [RA.LETTER[k] for k in RA.SECTION_KEYS] == ["A", "B", "C", "D", "E", "F", None])
ok("1: blank sections = all; asked ones come back in the file's order", RA.parse_sections(None) == RA.SECTION_KEYS
   and RA.parse_sections("hours,limits") == ["limits", "hours"])
_e = raises(lambda: RA.parse_sections("limits,weather"))
ok("1: an unknown section is refused in words", isinstance(_e, RA.AskError) and "Pick the sections" in str(_e))
_e = raises(lambda: RA.gather(["R1"], sections="assessor"))
ok("1: only the assessor's page is refused: a section first", isinstance(_e, RA.AskError) and "at least one section" in str(_e))
ok("1: routes in the order asked, no repeats", RA.parse_routes("R2, R1,R2") == ["R2", "R1"])
_e = raises(lambda: RA.parse_routes(""))
ok("1: no route refused in words", isinstance(_e, RA.AskError) and "at least one route" in str(_e))
_e = raises(lambda: RA.parse_routes(",".join(f"R{i}" for i in range(13))))
ok("1: 13 routes refused: up to 12 (Q2)", RA.MAX_ROUTES == 12 and isinstance(_e, RA.AskError) and "up to 12" in str(_e))
ok("1: the file names (Q1)", RA.file_name({"routes": [{"id": "R001"}]}) == "route-analysis-R001.pdf"
   and RA.file_name({"routes": [{"id": "R1"}, {"id": "R2"}, {"id": "R3"}]}, "xlsx") == "route-analysis-3-routes.xlsx")

# --------------------------------------------------------------------------- #
#  2. gather()                                                                 #
# --------------------------------------------------------------------------- #
ok("2: no lorry asked: the first route's busiest Approved lorry (Q3)", RA.default_lorry("R1") == OTHER
   and RA.default_lorry("R2") == PROF)
D = RA.gather(["R1"], lorry=PROF, now=date(2026, 11, 9))
R = D["routes"][0]
ok("2: one lorry for the whole file, its name", D["lorry"] == PROF and D["lorry_text"] == conversions.vehicle_label(
    conversions.load_factors(), PROF) and R["vehicle"] == PROF)
L = R["limits"]
ok("2 A: the stored check, its date, the picked lorry's limits on the route numbered A to B",
   L["checked"] == "2 Nov 2026" and [g["no"] for g in L["items"]] == [1, 2]
   and [g["road"] for g in L["items"]] == ["Station Road", "Mill Lane"], str([(g.get("no"), g["road"]) for g in L["items"]]))
_w, _h = L["items"]
ok("2 A: below this lorry, out and back, 'except for access' kept; above it, a point beside the route said as such",
   _w["verdict_words"] == "Below this lorry" and _w["legs_words"] == "out and back" and _w["exceptions"] == "Except for access"
   and _h["verdict_words"] == "Above this lorry" and _h["legs_words"] == "out" and _h["where"] and "from the route" in _h["where"])
ok("2 A: a limit on a stored alternative is a diversion's, apart", [g["road"] for g in L["diversion_items"]] == ["Gartree Road"])
ok("2 A: the other lorry differs (it has no height limit stored) and is listed (Q7)",
   L["others"]["n"] == 1 and L["others"]["different"] == [OTHER] and not L["others"]["same"])
ok("2 A: no closures held: said in words, never fetched for the file (Q8)", R["closures"]["held"] is False and R["closures"]["why"])
C = R["community"]
ok("2 B: within the Routes page's distances: the school and the health centre named, the bus stop counted, the far school out",
   [p["name"] for p in C["named"]] == ["Test Primary", "Brook Surgery"] and [p["name"] for p in C["others"]] == ["Mill Lane stop"]
   and C["counts"]["schools"] == 1 and C["counts"]["health"] == 1 and C["counts"]["bus_stops"] == 1 and C["fetched"] == "1 Nov 2026",
   str((C["named"], C["others"], C["counts"])))
ok("2 B: named A to B, numbered; their distance from the route in metres",
   [p["no"] for p in C["named"]] == [1, 2] and 80 <= C["named"][0]["m"] <= 120)
ok("2 C: the route collision evidence itself, fetched", R["evidence"]["route_id"] == "R1" and R["evidence"]["fetched"]
   and R["evidence"]["headline"][0]["on"] == 3, str(R["evidence"].get("headline", [{}])[0]))
ok("2 D: the cycle and left-turn figures from the evidence's own pass", R["cycle"]["turn_min"] == cl.TURN_MIN_DEG
   and R["cycle"]["columns"] == R["evidence"]["headline"])
E = R["hours"]
ok("2 E: the stored busy-hour times per option, at 08:00 and 12:00 (Q11)",
   E["worked_out"] and [r_["alt"] for r_ in E["rows"]] == [0, 1] and E["rows"][0]["at"]["08:00"] is not None
   and E["rows"][0]["at"]["08:00"] > E["rows"][0]["at"]["12:00"], str(E["rows"]))
ok("2 (B-F7): out_m / back_m are the stored leg distances (3.4 km each), as the screens show; the line's own length only "
   "where none is stored", R["out_m"] == 3400.0 and R["back_m"] == 3400.0, (R["out_m"], R["back_m"]))
ok("2 F: no diversion planned: an empty list, nothing invented", R["diversions"]["items"] == [] and R["diversions"]["no_way"] == [])
_base = {"loaded": ROUTE, "return": list(reversed(ROUTE)),
         "diversions": [{"kind": "busy", "when": "Weekdays 16:00–19:00", "loaded": ALT, "return": ALT},
                        {"kind": "zone", "when": "Sat 19 Dec 2027 – Sun 3 Jan 2028", "because": ["Christmas trading"],
                         "loaded": BENT, "return": list(reversed(ROUTE)), "loaded_words": "by Gartree Road"}]}
_F = RA._diversions("R1", _base, cl.index_from_db())
ok("2 F: a dated diversion is listed, the busy-hours road is not (it is E's, Q12); further by its length",
   len(_F["items"]) == 1 and _F["items"][0]["because"] == ["Christmas trading"] and _F["items"][0]["out_diverted"]
   and not _F["items"][0]["back_diverted"] and _F["items"][0]["out_more_m"] is not None and _F["items"][0]["out_more_m"] > 0)
ok("2: the first page's row: out / back, limits below '1 out · 1 back', closures not held, schools · health '1 · 1'",
   R["summary"]["limits_below"] == "1 out · 1 back" and R["summary"]["closures"] == "not held"
   and R["summary"]["schools_health"] == "1 · 1" and R["summary"]["out_back"], str(R["summary"]))
D2 = RA.gather(["R2", "R1"], sections="limits,community", now=date(2026, 11, 9))
ok("2: several routes in the order asked; an unticked section is not gathered",
   [x["id"] for x in D2["routes"]] == ["R2", "R1"] and "evidence" not in D2["routes"][0] and "hours" not in D2["routes"][0]
   and D2["lorry"] == PROF)

# --------------------------------------------------------------------------- #
#  3. A team login                                                             #
# --------------------------------------------------------------------------- #
_team1 = {"role": "ipt", "label": "North Team", "ipt": "IPT1"}
_e = raises(lambda: RA.gather(["R2"], acc=_team1))
ok("3: a team login asking for another team's route: no such route", isinstance(_e, RA.AnalysisError))
ok("3: ...its own team's route: gathered", RA.gather(["R1"], acc=_team1, sections="limits")["routes"][0]["id"] == "R1")
_e = raises(lambda: RA.gather(["NOPE"]))
ok("3: no such route: AnalysisError", isinstance(_e, RA.AnalysisError))

# --------------------------------------------------------------------------- #
#  4. The PDF                                                                  #
# --------------------------------------------------------------------------- #
PDF = RR.build_pdf(D)
ok("4: a PDF, its page count kept (first, A, B, C's pages, D, E, the assessor's; F said there)",
   PDF[:5] == b"%PDF-" and D["pages"] >= 8, str(D.get("pages")))
TX = text(PDF)
if TX:
    ok("4: the first page: the title, the lorry, what the file is and is not, the page list",
       "Route analysis" in TX and "In this file" in TX and "not the assessment" in TX
       and "The route at a glance" in TX and "nothing was fetched for this file" in TX, TX[:600])
    ok("4: every ticked section's heading", all(h in TX for h in ("Restrictions and lorry limits", "Community places",
       "C · Collisions", "Cycle routes and left turns", "Busy-hour times", "For the route risk assessment")), TX[:2000])
    ok("4 A: the limits by name and the lorry's position against them", "Station Road" in TX and "Below this lorry" in TX
       and "Above this lorry" in TX and "Except for access" in TX.replace("except for access", "Except for access"))
    ok("4 A: the closures not held, in words; the other lorry's limits differ", "No road closures are set up" in TX
       or "No planned road closures are held" in TX)
    ok("4 B: the named places, the counts, when fetched", "Test Primary" in TX and "Brook Surgery" in TX
       and "As fetched 1 Nov 2026" in TX)
    ok("4 C: the evidence's own pages, its assessor page left to the analysis", "This route and its alternatives" in TX
       and TX.count("For the route risk assessment (CLOCS Standard v5, 5.1a)") <= 1 and "For the CLOCS route risk assessment" not in TX)
    ok("4 E: the busy-hour table", "Round trip by the hour it sets off" in TX and "08:00" in TX)
    # 11 Nov 2026 (CLOCS card B-F7): the header's length is the stored (routed) distance, as on the Routes screen and the
    # Route sheet (3.4 km stored for R1's legs = 2.1 mi); section C's page head says "Made", as every other page does
    ok("4 (B-F7): the route's length in the header is the stored distance: 2.1 mi out and back (3.4 km), not the drawn line's",
       "2.1 mi out, 2.1 mi back" in TX or "2.1 km out" not in TX and "3.4 km out, 3.4 km back" in TX, TX[:900])
    ok("4 (B-F7): section C's page head says 'Made', no page says 'Issued'", "Issued" not in TX and "Made 9 Nov 2026" in TX)
    ok("4: the assessor's page points at the sections, F 'not in this file' when unticked does not arise here",
       "Evidence: C · Collisions" in TX and "Evidence: A · Restrictions and lorry limits" in TX)
    ok("4: no collision's hour on any page (the hours' chart counts only)", not re.search(r"\b(08:15|17:40|23:05)\b", TX))
    # the analysis's own pages (C is the route collision evidence as it was, its words unchanged)
    _own_t = text(RR.build_pdf(RA.gather(["R1"], lorry=PROF, sections="limits,community,cycle,hours,diversions,assessor",
                                         now=date(2026, 11, 9))))
    ok("4: no verdict, rate or 'movements' word on the analysis's own pages",
       _own_t and not re.search(r"high[- ]risk|safest|risk score|\brating\b|per million|movements", _own_t, re.I)
       and not re.search(r"high[- ]risk|safest|risk score", TX, re.I), str(re.findall(r"high[- ]risk|safest|movements", _own_t, re.I)))
    _P2 = RR.build_pdf(RA.gather(["R2", "R1"], sections="limits,assessor", now=date(2026, 11, 9)))
    _t2 = text(_P2)
    ok("4: two routes: route by route (R2 then R1), only the ticked sections, the others said 'section not in this file'",
       "The routes side by side" in _t2 and _t2.index("R2 ·") < _t2.rindex("R1 ·") and "Community places" not in _t2.split("Not in this file")[0][-400:]
       and "Busy-hour times: section not in this file" in _t2 and "Round trip by the hour" not in _t2, _t2[:800])
else:
    ok("4: pdftotext missing: the PDF is at least as long as a page per section", len(PDF) > 20000)
_Dd = RA.gather(["R1"], sections="cycle,hours,collisions", now=date(2026, 11, 9))
_Dd["routes"][0]["diversions"] = {"items": [], "no_way": [{"when": "Mar 2027", "because": ["Bridge works"], "kept": False}]}
ok("4 F: no diversion: one line for the assessor's page, a period with no way round said",
   RR.diversions_line(_Dd["routes"][0]["diversions"]).startswith("No diversion is planned")
   and "No way round yet in Mar 2027 (Bridge works)" in RR.diversions_line(_Dd["routes"][0]["diversions"]))

# --------------------------------------------------------------------------- #
#  5. The XLSX                                                                 #
# --------------------------------------------------------------------------- #
import openpyxl  # noqa: E402
WB = openpyxl.load_workbook(io.BytesIO(RR.build_xlsx(D)))
_names = WB.sheetnames
ok("5: a sheet per section, the contents first and About last", _names[0] == "Contents" and _names[-1] == "About"
   and {"Routes side by side", "A Limits", "A Closures and zones", "B Community places", "D Cycle and left turns",
        "E Busy-hour times", "F Diversions"} <= set(_names) and any(n.startswith("C ") for n in _names), str(_names))
ok("5: C is the evidence workbook merged, its cycle sheet left to D when D is ticked",
   "C Collisions" in _names and not any(n.startswith("C Cycle") for n in _names), str(_names))
ok("5: every section sheet has the route first", all(WB[n].cell(row=1, column=1).value == "Route"
                                                      for n in _names if n[:2] in ("A ", "B ", "C ", "D ", "E ", "F ")))
_b = [[c.value for c in r] for r in WB["B Community places"].iter_rows(min_row=2)]
ok("5: B lists every place, named and counted", sorted(r[3] for r in _b) == ["Brook Surgery", "Mill Lane stop", "Test Primary"])
_W2 = openpyxl.load_workbook(io.BytesIO(RR.build_xlsx(D2)))
ok("5: unticked sections get no sheet", not any(n[:2] in ("C ", "D ", "E ", "F ") for n in _W2.sheetnames), str(_W2.sheetnames))
_c = [[c.value for c in r] for r in WB["C Collisions"].iter_rows()]
ok("5: the merged collisions sheet never carries an hour or a day column",
   not any(re.search(r"\b(hour|time|day)\b", str(h or ""), re.I) for h in _c[0]), str(_c[0]))

# --------------------------------------------------------------------------- #
#  6. The evidence PDF's own builder                                          #
# --------------------------------------------------------------------------- #
EV = cl.evidence("R1", now=date(2026, 11, 9))
_own = export.build_collision_evidence_pdf(dict(EV))
ok("6: with no canvas: the evidence PDF as before (bytes, its own assessor page)", _own[:5] == b"%PDF-"
   and (not TX or "For the route risk assessment" in text(_own)))
from reportlab.pdfgen import canvas as _rc  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
_buf = io.BytesIO()
_cv = _rc.Canvas(_buf, pagesize=A4)
_n = export.build_collision_evidence_pdf(dict(EV), canvas=_cv, page_start=5, skip={"assessor", "cycle", "cycle_by_hour"})
_cv.save()
ok("6: into a canvas: the next page number back, nothing saved by it", isinstance(_n, int) and _n > 5)
if TX:
    _t6 = text(_buf.getvalue())
    ok("6: ...its assessor page and cycle block left out when told", re.search(r"For the route risk assessment(?! \(CLOCS)", _t6) is None   # NARROWED 10 Nov 2026 (F12): section C's box says "(CLOCS Standard v5, 5.1a)"
       and "Cycle routes and left turns" not in _t6 and "Page 5" in _t6, _t6[-400:])

# --------------------------------------------------------------------------- #
#  7. The endpoints                                                            #
# --------------------------------------------------------------------------- #
access.current = lambda: None
_e = raises(lambda: main.route_analysis_pdf(routes="R1", request=_Request()))
ok("7: no credential: 401", getattr(_e, "status_code", None) == 401)
_e = raises(lambda: main.route_analysis_xlsx(routes="R1", request=_Request()))
ok("7: ...the XLSX too", getattr(_e, "status_code", None) == 401)
access.current = lambda: {"role": "planner", "label": "Planner"}
main._staff_request = lambda request=None: True
_r = main.route_analysis_pdf(routes="R1", lorry=PROF, sections="limits,assessor", request=_Request())
ok("7: a planner: the PDF, named, never cached", _r.body[:5] == b"%PDF-" and _r.media_type == "application/pdf"
   and 'filename="route-analysis-R1.pdf"' in _r.headers["Content-Disposition"] and _r.headers["Cache-Control"] == "no-store")
_rx = main.route_analysis_xlsx(routes="R1,R2", request=_Request())
ok("7: the XLSX, two routes", _rx.body[:2] == b"PK" and 'filename="route-analysis-2-routes.xlsx"' in _rx.headers["Content-Disposition"])
_e = raises(lambda: main.route_analysis_pdf(routes="R1", lorry="Hovercraft", request=_Request()))
ok("7: an unknown lorry: 422 in words", getattr(_e, "status_code", None) == 422 and "lorry" in str(_e.detail))
_e = raises(lambda: main.route_analysis_pdf(routes="NOPE", request=_Request()))
ok("7: no such route: 404", getattr(_e, "status_code", None) == 404)
_e = raises(lambda: main.route_analysis_pdf(routes="R1", sections="weather", request=_Request()))
ok("7: an unknown section: 422", getattr(_e, "status_code", None) == 422)
access.current = lambda: _team1
_e = raises(lambda: main.route_analysis_pdf(routes="R2", request=_Request()))
ok("7: a team login asking for another team's route: 404", getattr(_e, "status_code", None) == 404)
access.current = lambda: {"role": "planner", "label": "Planner"}
_hold, _go = threading.Event(), threading.Event()


def _holder():
    with heavy_reads.solo("route-analysis"):
        _hold.set()
        _go.wait(10)


heavy_reads.SOLO_WAIT_S = 0.2
_th = threading.Thread(target=_holder)
_th.start()
_hold.wait(5)
_e = raises(lambda: main.route_analysis_pdf(routes="R1", sections="limits", request=_Request()))
_go.set()
_th.join(5)
ok("7: one at a time: a second press while one is being made is busy, 503 in words",
   getattr(_e, "status_code", None) == 503 and "Another route analysis is being made" in str(getattr(_e, "detail", "")))
_src_main = read("backend/main.py")
_f = _src_main.split("def _route_analysis(")[1].split("\n@app.")[0]
ok("7: staff checked first; built inside heavy_reads.solo('route-analysis')",
   _f.index("if not _staff_request(request):") < _f.index('heavy_reads.solo("route-analysis"'))
ok("7: the old evidence addresses still answer (Q13)", '@app.get("/api/routes/{route_id}/collision-evidence.pdf")' in _src_main
   and '@app.get("/api/routes/{route_id}/collision-evidence.xlsx")' in _src_main
   and '@app.get("/api/routes/analysis.pdf")' in _src_main and '@app.get("/api/routes/analysis.xlsx")' in _src_main)

# --------------------------------------------------------------------------- #
#  8. Source level                                                             #
# --------------------------------------------------------------------------- #
_doc, _ren = read("backend/route_analysis_doc.py"), read("backend/route_analysis_render.py")
ok("8: stored data only: nothing fetched for the file", not re.search(
   r"\.refresh\(|start_refresh|fetch_all|check_all\(|urlopen|requests\.|httpx|route_with_haul|bake_", _doc + _ren))
ok("8: no 'movements' in the new modules' words; no collision hour printed",
   "movement" not in (_doc + _ren).lower().replace("# ", "").split('"""')[0] or not re.search(r'"[^"\n]*movements[^"\n]*"', _doc + _ren))
APP = read("frontend/index.html")
_m = APP.split("function RouteAnalysisMenu(")[1].split("\nfunction ")[0]
ok("8: app: the Route analysis menu in the Routes header and the full-screen column, the evidence buttons gone",
   "<RouteAnalysisMenu routes={status || []} picked={selected} vehicles={vehicles} />" in APP
   and "<RouteAnalysisMenu routes={routes} picked={r.id} vehicles={vehicles} />" in APP
   and "CollisionEvidenceButton" not in APP and "Collision evidence (PDF)" not in APP)
_secs = re.findall(r'\["(\w+)", "[A-F]?", "', APP.split("const RA_SECTIONS = ")[1].split(";")[0])
ok("8: app: the sections are the server's, in its order", _secs == RA.SECTION_KEYS, str(_secs))
ok("8: app: the ticks remembered in this browser in try / catch; up to 12 routes; PDF and XLSX; errors in words",
   "localStorage.setItem(RA_KEY" in _m and "try { localStorage.setItem" in _m and "const RA_MAX = 12;" in APP
   and 'download("pdf")' in _m and 'download("xlsx")' in _m and 'errSay("The route analysis could not be made.", e)' in _m)
GUIDE, TECH = read("frontend/help/index.html"), read("frontend/help/technical/index.html")
ok("8: the user guide names the Route analysis and its sections, no back-end words",
   "Route analysis" in GUIDE and "page for the assessor" in GUIDE
   and not re.search(r"route-analysis|/api/|heavy_reads|endpoint", GUIDE.split("Route analysis")[1][:2500]))
ok("8: the technical guide: the addresses, the solo build, stored data only", "/api/routes/analysis.pdf" in TECH
   and "route_analysis_doc" in TECH and "solo" in TECH)

remove_scratch_db(db, TMP)
print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)

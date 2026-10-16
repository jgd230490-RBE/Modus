"""
The collision history along the routes, 16 Oct 2026 (CLOCS v5 C1; branch claude/collision-history).

WHAT IS ASSERTED
----------------
  1. The words and codes: the strip is the community layer's (250 m / 500 m), "on the route" is 25 m, places are 50 m;
     the vulnerable road users are the CLOCS v5 list as STATS19 codes; goods vehicles over 3.5 t are types 20, 21, 98;
     every output word is evidence, never a verdict (no score, rating, "high-risk", "safest", "predict", "accident" …);
     the ink is no reserved colour; the latest final year turns over in August.
  2. The route index: which route (primary or alternative) and which site a point is near, and how far.
  3. The readers, on small files in DfT's own column names: in / out of the strip, no position, outside the box; the
     month kept and never the day; road, junction, light in words; goods vehicles; each road user hurt, and KSI.
  4. refresh(): the five final years, three tables each (a year with nothing in the strip reads only its collision
     file), every file deleted; the newest year not out yet steps back and says so; a failure changes nothing; no
     routes and no sites is said in words; start_refresh refuses a second run.
  5. Storage and the payload: year and month only (no day or time column), counts, period, the OGL credit.
  6. The evidence for one route: the route and its alternative in adjacent columns, on the route vs within 250 m, the
     places with two or more collisions ordered along the route, the community considerations near each; a team code
     reads its own team's routes only.
  7. The PDF and the XLSX: the title, the period, the counts, the place, "not the assessment", the caveats, the credit;
     not fetched → said so; the XLSX's sheets and one row per collision, no day.
  8. The endpoints: staff only (401 for nothing and for the map password's cookie), refresh a planner's or an admin's
     (403 for a team code), evidence 404 for another team's route; the plans take collisions=1, off by default.
  9. The CLP plans: the collisions in the frame, KSI only on the regional plan, drawn and listed; left off unless added.
 10. Source level: the map group hidden unless staff, off by default, read only when ticked, never from DfT, the popup
     month-only; the slight ones off until ticked; the app's Config panel, the Routes buttons, the export card's box;
     the public map and the bulletin never read it; the tables tenanted and in the package; the guides.

WHAT THIS DOES NOT PROVE
------------------------
  * DfT is NOT called: the live check is in notes/route-risk-research-1016.md (16 Oct 2026, the 2025 files).
  * Nothing renders in a browser here; Mapbox is never called (portable.offline).
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
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
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


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

TMP = tempfile.mkdtemp(prefix="wayscope_collisions_")
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
import community  # noqa: E402
import collisions as cl  # noqa: E402
import route_map_export  # noqa: E402
import export  # noqa: E402
import tenant_package  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import gate  # noqa: E402
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


def boot():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); db.init_tenant()
    taxonomy.seed_taxonomy()
    config.seed_from_file(conversions)
    config.invalidate()


# the strip: one straight route east-west at 52.60 N from A (-0.95) to B (-0.90), an alternative 553 m north of it,
# a site at each end
LAT0 = 52.60
DLAT = 1 / 110574.0              # one metre north
DLON = 1 / (111320.0 * 0.6074)   # one metre east at 52.6 N
ROUTE = [[-0.95, LAT0], [-0.925, LAT0], [-0.90, LAT0]]
ALT = [[-0.95, LAT0 + 553 * DLAT], [-0.90, LAT0 + 553 * DLAT]]
mid = -0.925

# --------------------------------------------------------------------------- #
#  1. The words and codes                                                      #
# --------------------------------------------------------------------------- #
ok("1: the strip is the community layer's: 250 m along the routes, 500 m round the sites (R2)",
   cl.NEAR_ROUTE_M == community.STRIP_ROUTE_M == 250 and cl.NEAR_SITE_M == community.STRIP_SITE_M == 500)
ok("1: 'on the route' is 25 m, a place is two collisions within 50 m (R2, R4), five years (R1)",
   cl.ON_ROUTE_M == 25 and cl.CLUSTER_M == 50 and cl.YEARS == 5)
ok("1: the vulnerable road users are the CLOCS v5 list (§2.7), in that order (R3)",
   cl.VRU_KEYS == ["pedestrian", "cyclist", "motorcyclist", "horse_rider", "escooter", "mobility"])
_codes = {v["key"]: v["types"] for v in cl.VRU}
ok("1: ...as the STATS19 casualty_type codes of the 2025 data guide (PPT is 33, as the 2025 file has it)",
   _codes == {"pedestrian": {"0"}, "cyclist": {"1"}, "motorcyclist": {"2", "3", "4", "5", "23", "97"},
              "horse_rider": {"16"}, "escooter": {"33"}, "mobility": {"22"}})
ok("1: goods vehicles over 3.5 t are vehicle types 20, 21, 98 (not 19, the vans)", cl.GOODS_TYPES == {"20", "21", "98"})
ok("1: severity 1 fatal, 2 serious, 3 slight", cl.SEVERITY == {1: "Fatal", 2: "Serious", 3: "Slight"})
ok("1: the source is OGL v3.0 and the GOV.UK page; the files are data.dft.gov.uk's per-year tables",
   cl.SOURCE["licence"] == "OGL v3.0" and cl.SOURCE["url"] == "https://www.gov.uk/government/statistical-data-sets/road-safety-open-data"
   and cl.URL.format(table="collision", year=2025) ==
   "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-2025.csv")
ok("1: the latest final year turns over in August (final data in late July)",
   cl.latest_final_year(date(2026, 7, 31)) == 2024 and cl.latest_final_year(date(2026, 8, 1)) == 2025
   and cl.latest_final_year(date(2026, 10, 16)) == 2025)
ok("1: the names (R10): 'Collision history' and 'Route collision evidence', never 'route risk'",
   cl.LAYER_NAME == "Collision history" and cl.SHEET_NAME == "Route collision evidence")
_words = " ".join([cl.CAVEAT, cl.NOT_A_VERDICT, cl.WHAT, cl.LAYER_NAME, cl.SHEET_NAME] + [l for _, l in cl.ROWS])
VERDICT = re.compile(r"high[- ]risk|dangerous|safest|safe route|black ?spot|risk score|risk rating|\brating\b|"
                     r"accident|predict|optimi[sz]e|real-time|\bsecure\b|telematics|live tracking|\bAI\b", re.I)
ok("1: every output word is evidence, never a verdict (and none of the banned public words)",
   not VERDICT.search(_words), str(VERDICT.findall(_words)))
ok("1: the caveat says what DfT says: police-reported only, many non-fatal never recorded, severity recording changed",
   "Police-reported" in cl.CAVEAT and "no legal duty" in cl.CAVEAT and "never recorded" in cl.CAVEAT and "2016" in cl.CAVEAT)
ok("1: 'This is evidence for a route risk assessment. It is not the assessment.'",
   cl.NOT_A_VERDICT == "This is evidence for a route risk assessment. It is not the assessment.")
ok("1: the table rows are counts only — no rate, no per km, no score", all("per" not in l.lower().split() and "%" not in l
                                                                           for _, l in cl.ROWS))
ok("1: a vowel takes 'An' ('An e-scooter …')", any(l.startswith("An e-scooter") for _, l in cl.ROWS))
RESERVED = {"#94BBF9", "#5A96F6", "#2071F3", "#0B55CB", "#073888", "#DC2626", "#C8102E", "#FF8C14", "#E8590C", "#E8681E",
            "#FF8312", "#D97706", "#F59E0B", "#C2790B", "#059669", "#3B82F6", "#2563EB", "#0F766E", "#0D9488",
            "#4C1D95", "#155E75", "#57534E", "#64748B", "#7C3AED", "#89A3DC", "#6A8BD2", "#4A72C9", "#2D4E95"}
ok("1: the collision ink is one dark ink, no reserved colour, no community kind's colour (a hue would claim a meaning)",
   export.CE_INK.upper() not in RESERVED and export.CE_INK.upper() not in {k["colour"].upper() for k in community.KINDS}
   and "COLL_INK = '#27272A'" in read("map/index.html") and export.CE_INK == "#27272A")
ok("1: road words", cl.road_words("3", "6") == "A6" and cl.road_words("1", "1") == "M1" and cl.road_words("5", "123") == "C road"
   and cl.road_words("6", "0") == "Unclassified road" and cl.road_words("-1", "") is None and cl.road_words("4", "0") == "B road")

# --------------------------------------------------------------------------- #
#  2. The route index                                                          #
# --------------------------------------------------------------------------- #
IX = cl.RouteIndex([("R1", ROUTE), ("R1@1", ALT)], [("LB", "Site B", -0.90, LAT0)])
_r, _s = IX.near(mid, LAT0 + 100 * DLAT)
ok("2: a point 100 m off the route is near R1 (about 100 m) and not near the alternative 453 m away",
   abs(_r.get("R1", 0) - 100) < 2 and "R1@1" not in _r and not _s, str(_r))
_r, _s = IX.near(mid, LAT0 + 400 * DLAT)
ok("2: a point 400 m north is near the alternative only (153 m)", list(_r) == ["R1@1"] and abs(_r["R1@1"] - 153) < 2, str(_r))
_r, _s = IX.near(-0.90 + 450 * DLON, LAT0)
ok("2: a point 450 m past the site is near the site only (500 m round a site)", not _r and abs(_s.get("LB", 0) - 450) < 3, str((_r, _s)))
_r, _s = IX.near(-0.94, LAT0 - 300 * DLAT)
ok("2: a point 300 m off the route, far from the site, is near nothing", not _r and not _s)
ok("2: the box covers the routes and sites with the reach; a far point is outside it",
   IX.in_box(mid, LAT0) and not IX.in_box(-0.5, 52.0) and IX.bbox[0] < -0.95 and IX.bbox[3] > LAT0 + 553 * DLAT)
ok("2: route keys: the primary is the route id, an alternative 'id@n'", cl.route_key("R7") == "R7" and cl.route_key("R7", 2) == "R7@2")

boot()
T = db.current_tenant()
for lid, name, lon in (("LA", "Quarry A", -0.95), ("LB", "Site B", -0.90)):
    db.execute("INSERT INTO locations (tenant_id, id, name, role, lat, lon) VALUES (?, ?, ?, ?, ?, ?)", (T, lid, name, "destination", LAT0, lon))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?, ?)", (T, "R1", "LA", "LB", "IPT1"))
db.execute("INSERT INTO routes (tenant_id, id, origin_id, dest_id, ipt) VALUES (?, ?, ?, ?, ?)", (T, "R2", "LB", "LA", "IPT2"))
PROF = network.DEFAULT_PROFILE
network._upsert_geom("R1", PROF, json.dumps(ROUTE), 3.4, 0.1, None, leg="loaded", alt_index=0)
network._upsert_geom("R1", PROF, json.dumps(list(reversed(ROUTE))), 3.4, 0.1, None, leg="return", alt_index=0)
network._upsert_geom("R1", PROF, json.dumps(ALT), 3.6, 0.1, None, leg="loaded", alt_index=1)
DIX = cl.index_from_db()
ok("2: index_from_db reads every stored road route under its key (the primary once: a reversed leg is kept, it is "
   "the same key) and the alternative under 'R1@1', and the sites",
   {k for k, _ in DIX.lines} == {"R1", "R1@1"} and len(DIX.sites) == 2, str([k for k, _ in DIX.lines]))

# --------------------------------------------------------------------------- #
#  3. The readers                                                              #
# --------------------------------------------------------------------------- #
FX = os.path.join(TMP, "fx")
os.makedirs(FX, exist_ok=True)
C_HEAD = ("collision_index,collision_year,collision_ref_no,location_easting_osgr,location_northing_osgr,longitude,latitude,"
          "police_force,collision_severity,number_of_vehicles,number_of_casualties,date,day_of_week,time,"
          "local_authority_highway_current,first_road_class,first_road_number,road_type,speed_limit,junction_detail,"
          "second_road_class,second_road_number,light_conditions")
V_HEAD = "collision_index,collision_year,collision_ref_no,vehicle_reference,vehicle_type"
K_HEAD = ("collision_index,collision_year,collision_ref_no,vehicle_reference,casualty_reference,casualty_class,"
          "casualty_severity,casualty_type,escooter_flag")


def P(lon_m, lat_m, lon0=mid):
    return round(lon0 + lon_m * DLON, 6), round(LAT0 + lat_m * DLAT, 6)


def collision_rows(y):
    pts = {
        "C1": (*P(0, 10), 2, "15/03/%d" % y, "3", "6", "6", "30", "13", "6", "0", "1"),       # on R1, A6, T junction, KSI
        "C2": (*P(30, 15), 3, "02/04/%d" % y, "3", "6", "6", "30", "0", "-1", "0", "4"),      # 33 m from C1: a place
        "C3": (*P(-1000, 200), 1, "20/06/%d" % y, "4", "582", "6", "40", "0", "-1", "0", "1"),  # within 250 m, not on
        "C4": (*P(-1000, 400), 2, "01/07/%d" % y, "6", "0", "6", "30", "0", "-1", "0", "1"),   # near the alternative only
        "C5": (-0.5, 52.0, 2, "01/07/%d" % y, "3", "1", "6", "60", "0", "-1", "0", "1"),       # far away
        "C6": ("", "", 2, "01/07/%d" % y, "3", "1", "6", "60", "0", "-1", "0", "1"),           # no position
        "C7": (*P(450, 0, -0.90), 3, "11/11/%d" % y, "5", "0", "6", "30", "0", "-1", "0", "1"),  # near site B only
        "C8": (*P(1000, -5), 2, "30/12/%d" % y, "3", "6", "3", "70", "0", "-1", "0", "6"),    # on R1, dual, dark
    }
    out = [C_HEAD]
    for cid, (lon, lat, sev, d, rc, rn, rt, sl, jd, rc2, rn2, light) in pts.items():
        out.append(f"{y}{cid},{y},{cid},0,0,{lon},{lat},33,{sev},2,1,{d},3,08:15,E10000018,{rc},{rn},{rt},{sl},{jd},"
                   f"{rc2},{rn2},{light}")
    return "\n".join(out) + "\n"


def vehicle_rows(y):
    return "\n".join([V_HEAD, f"{y}C1,{y},C1,1,21", f"{y}C1,{y},C1,2,9", f"{y}C3,{y},C3,1,9", f"{y}C8,{y},C8,1,19",
                      f"{y}C5,{y},C5,1,21"]) + "\n"


def casualty_rows(y):
    return "\n".join([K_HEAD,
                      f"{y}C1,{y},C1,1,1,3,2,0,0",       # pedestrian, serious
                      f"{y}C2,{y},C2,1,1,1,3,1,0",       # cyclist, slight
                      f"{y}C3,{y},C3,1,1,1,1,97,0",      # motorcyclist (cc unknown), fatal
                      f"{y}C3,{y},C3,2,2,2,3,9,0",       # car passenger: not a VRU
                      f"{y}C4,{y},C4,1,1,1,3,9,0",
                      f"{y}C7,{y},C7,1,1,1,3,16,0",      # horse rider, slight
                      f"{y}C8,{y},C8,1,1,1,2,33,1",      # e-scooter / powered transporter, serious
                      f"{y}C8,{y},C8,2,2,1,3,22,0"]) + "\n"   # mobility scooter, slight


def write(name, text):
    p = os.path.join(FX, name)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


Y = 2025
keep = cl.read_collisions(write("c.csv", collision_rows(Y)), DIX, year=Y)
ok("3: in the strip: C1, C2, C3 (route), C4 (alternative), C7 (site), C8; out: far away, no position",
   sorted(k[4:] for k in keep) == ["C1", "C2", "C3", "C4", "C7", "C8"], str(sorted(keep)))
c1 = keep.get(f"{Y}C1", {})
ok("3: the month is kept (2025-03), never the day or the time", c1.get("month") == "2025-03" and "date" not in c1
   and "time" not in c1 and "day" not in json.dumps(c1).lower().replace("daylight", ""), str(c1.get("month")))
ok("3: road, junction, road type, speed limit, light and highway authority in words",
   c1.get("road") == "A6" and c1.get("junction") == "T or staggered junction" and c1.get("road_type") == "Single carriageway"
   and c1.get("speed_limit") == 30 and c1.get("light") == "Daylight" and c1.get("authority") == "E10000018"
   and keep[f"{Y}C8"]["road_type"] == "Dual carriageway" and keep[f"{Y}C8"]["light"] == "Darkness, no lighting"
   and keep[f"{Y}C2"]["junction"] is None)
ok("3: each collision's distance to each route it is near (C1 ~10 m from R1; C4 only near R1@1; C7 only near the site)",
   abs(c1["routes"]["R1"] - 10) < 2 and list(keep[f"{Y}C4"]["routes"]) == ["R1@1"]
   and not keep[f"{Y}C7"]["routes"] and "LB" in keep[f"{Y}C7"]["sites"])
cl.read_vehicles(write("v.csv", vehicle_rows(Y)), keep)
ok("3: a goods vehicle over 3.5 t is marked (C1: type 21), a van (19) and a car are not",
   keep[f"{Y}C1"]["goods"] and not keep[f"{Y}C3"]["goods"] and not keep[f"{Y}C8"]["goods"])
cl.read_casualties(write("k.csv", casualty_rows(Y)), keep)
ok("3: the road users hurt, and those killed or seriously injured",
   keep[f"{Y}C1"]["vru"] == ["pedestrian"] and keep[f"{Y}C1"]["vru_ksi"] == ["pedestrian"]
   and keep[f"{Y}C2"]["vru"] == ["cyclist"] and keep[f"{Y}C2"]["vru_ksi"] == []
   and keep[f"{Y}C3"]["vru"] == ["motorcyclist"] and keep[f"{Y}C3"]["vru_ksi"] == ["motorcyclist"]
   and keep[f"{Y}C4"]["vru"] == [] and keep[f"{Y}C7"]["vru"] == ["horse_rider"]
   and keep[f"{Y}C8"]["vru"] == ["escooter", "mobility"] and keep[f"{Y}C8"]["vru_ksi"] == ["escooter"],
   str({k[4:]: (v["vru"], v["vru_ksi"]) for k, v in keep.items()}))
ok("3: a casualty of a collision outside the strip is never read in", f"{Y}C5" not in keep)
_bom = cl.read_collisions(write("bom.csv", "﻿" + collision_rows(Y)), DIX, year=Y)
ok("3: a file with a byte-order mark reads the same", sorted(_bom) == sorted(keep))

# --------------------------------------------------------------------------- #
#  4. refresh()                                                                #
# --------------------------------------------------------------------------- #
CALLS = []


def stub_download(files_for, fail=None, missing=()):
    def dl(url, dest):
        CALLS.append(url)
        name = url.rsplit("/", 1)[-1]
        if any(m in name for m in missing):
            raise RuntimeError(f"could not download {url}: HTTP 404")
        if fail and fail in name:
            raise RuntimeError(f"could not download {url}: timed out")
        m = re.search(r"-(collision|vehicle|casualty)-(\d{4})\.csv$", name)
        text = files_for(m.group(1), int(m.group(2)))
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return url, len(text.encode("utf-8"))
    return dl


def only_2025(table, y):
    if y != 2025:
        return {"collision": C_HEAD, "vehicle": V_HEAD, "casualty": K_HEAD}[table] + "\n"
    return {"collision": collision_rows, "vehicle": vehicle_rows, "casualty": casualty_rows}[table](y)


_temps_before = {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("wayscope_collisions_")}
st = cl.refresh(by="Pat Planner", fetchers={"download": stub_download(only_2025)}, today=date(2026, 10, 16))
ok("4: done: the five final years 2021-2025, the period in words", st["state"] == "done" and st["years"] == [2021, 2022, 2023, 2024, 2025]
   and st["period"] == "2021–2025", str(st))
ok("4: the five years' collision files asked for; vehicles and casualties only for the year with collisions in the strip",
   sorted(u.rsplit("/", 1)[-1] for u in CALLS) == sorted(
       [f"dft-road-casualty-statistics-collision-{y}.csv" for y in range(2021, 2026)]
       + ["dft-road-casualty-statistics-vehicle-2025.csv", "dft-road-casualty-statistics-casualty-2025.csv"]), str(CALLS))
# NARROWED 16 Oct 2026 (found on live): the counts are the collisions along the routes and round the sites; C4, near the
# alternative only, is counted apart (it was 6 / 4 / 5 with it)
ok("4: the counts: 5 collisions along the routes and round the sites, 3 KSI, 5 with a vulnerable road user hurt",
   st["counts"] == {"all": 5, "ksi": 3, "vru": 5}, str(st["counts"]))
ok("4: ...and the one near the alternative only (C4, serious) counted apart",
   st["alternatives_only"] == {"all": 1, "ksi": 1}, str(st.get("alternatives_only")))
ok("4: the files read are listed in words", "2025 casualties" in " ".join(st["files"]) and "2025 vehicles" in " ".join(st["files"]))
ok("4: the work folder is removed (every downloaded file gone)",
   {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("wayscope_collisions_")} <= _temps_before | {os.path.basename(TMP)})
ok("4: by whom and when", st["by"] == "Pat Planner" and st["fetched_at"])
CALLS.clear()
st2 = cl.refresh(fetchers={"download": stub_download(only_2025, missing=("-2026.csv",))}, today=date(2027, 8, 2))
ok("4: the newest year not published yet (2026 → 404): five years step back to 2021-2025 and the page says so",
   st2["state"] == "done" and st2["years"] == [2021, 2022, 2023, 2024, 2025]
   and any("2026 data is not published yet" in n for n in st2["notes"]), str(st2))
_before = cl.status()["counts"]
st3 = cl.refresh(fetchers={"download": stub_download(only_2025, fail="casualty-2025")}, today=date(2026, 10, 16))
ok("4: a failure changes nothing: the error in words, the old rows and years kept",
   st3["state"] == "failed" and "nothing was changed" in (st3["error"] or "") and "2025" in st3["error"]
   and cl.status()["counts"] == _before and st3["years"] == [2021, 2022, 2023, 2024, 2025], str(st3.get("error")))
_saved = db.query("SELECT COUNT(*) AS n FROM collision_records WHERE tenant_id = ?", (T,))[0]["n"]
st4 = cl.refresh(fetchers={"download": stub_download(only_2025)}, index=cl.RouteIndex([], []), today=date(2026, 10, 16))
ok("4: no routes and no sites is said in words, nothing changed",
   st4["state"] == "failed" and "no route is worked out and no site has a position" in st4["error"]
   and db.query("SELECT COUNT(*) AS n FROM collision_records WHERE tenant_id = ?", (T,))[0]["n"] == _saved)
st5 = cl.refresh(fetchers={"download": stub_download(only_2025)}, index=cl.RouteIndex([], [("LB", "B", -0.90, LAT0)]),
                 today=date(2026, 10, 16))
ok("4: sites only (no road route yet): fetched round the sites, and the page says so",
   st5["state"] == "done" and st5["counts"]["all"] == 1 and any("only the sites were searched round" in n for n in st5["notes"]))
cl.refresh(fetchers={"download": stub_download(only_2025)}, today=date(2026, 10, 16))
cl._write_meta("running", cl._detail(cl._meta_row()), started_at=cl._now())
_again = cl.start_refresh(by="x", fetchers={"download": stub_download(only_2025)})
ok("4: start_refresh refuses a second run while one is running", _again["started"] is False and "already running" in _again["message"])
cl._write_meta("done", cl._detail(cl._meta_row()))
_sync = cl.start_refresh(by="y", sync=True, fetchers={"download": stub_download(only_2025)}, today=date(2026, 10, 16))
ok("4: ...and starts one otherwise (sync here)", _sync["started"] is True and cl.status()["state"] == "done")
ok("4: nothing is fetched on a page view: only refresh() reaches the downloader",
   read("backend/collisions.py").count('fetch["download"](') == 1
   and "default_fetchers()" in read("backend/collisions.py").split("def refresh(")[1][:600])

# --------------------------------------------------------------------------- #
#  5. Storage and the payload                                                  #
# --------------------------------------------------------------------------- #
_cols = [c.lower() for c in db._columns_of(db.get_conn().cursor(), "collision_records")]
ok("5: stored with the year and month only — no day, date or time column (R6)",
   "year" in _cols and "month" in _cols and not any(c in _cols for c in ("date", "day", "time", "day_of_week")), str(_cols))
PL = cl.payload()
# 16 Oct 2026 (found on live: 1,013 of 1,887 were near a stored alternative only, drawn on roads the map shows no route on)
_al = {f"{Y}{k}": cl.along(keep[f"{Y}{k}"]) for k in ("C1", "C2", "C3", "C4", "C7", "C8")}
ok("5: along: near a primary route or a site is 'route'; near a stored alternative only is 'alternative'",
   _al == {f"{Y}C1": "route", f"{Y}C2": "route", f"{Y}C3": "route", f"{Y}C4": "alternative", f"{Y}C7": "route",
           f"{Y}C8": "route"}, str(_al))
ok("5: ...a collision near both a route and an alternative is 'route'", cl.along({"routes": {"R1": 9, "R1@1": 40}, "sites": {}}) == "route"
   and cl.along({"routes": {"R1@1": 40, "R1@2": 9}, "sites": {}}) == "alternative" and cl.along({"routes": {}, "sites": {"LB": 400}}) == "route")
ok("5: every feature carries along; the payload still carries all of them (the map filters) and the split counts",
   all(f["properties"]["along"] in ("route", "alternative") for f in PL["features"])
   and sum(f["properties"]["along"] == "alternative" for f in PL["features"]) == 1
   and PL["alternatives_only"] == {"all": 1, "ksi": 1})
ok("5: the payload is a FeatureCollection of points, fatal last so they draw on top",
   PL["type"] == "FeatureCollection" and len(PL["features"]) == 6
   and [f["properties"]["severity"] for f in PL["features"]] == sorted([f["properties"]["severity"] for f in PL["features"]], reverse=True))
_p1 = next(f["properties"] for f in PL["features"] if "R1" in f["properties"]["routes"] and f["properties"]["severity"] == 1)
ok("5: a feature carries severity in words, month, road, junction, who was hurt, goods, distance — no day",
   _p1["severity_word"] == "Fatal" and _p1["month"] == "2025-06" and _p1["vru_words"] == ["Motorcyclist"]
   and _p1["ksi"] is True and "date" not in _p1 and "time" not in _p1)
ok("5: the credit line is the OGL statement naming DfT road safety data",
   PL["credit"] == "Collision history: contains public sector information licensed under the Open Government Licence v3.0 "
                   "(DfT road safety data).")
ok("5: the strip, the period and the name ride along", PL["strip"] == {"route_m": 250, "site_m": 500, "on_route_m": 25}
   and PL["period"] == "2021–2025" and PL["name"] == "Collision history")
_sql = read("backend/collisions.py")
import ast  # noqa: E402
_stmts = [n.value for n in ast.walk(ast.parse(_sql)) if isinstance(n, ast.Constant) and isinstance(n.value, str)
          and re.match(r"\s*(SELECT|DELETE|INSERT|UPDATE)\b", n.value)]
ok("5: every query in collisions.py names tenant_id (whole statements, read with ast)", len(_stmts) >= 8
   and all("tenant_id" in q for q in _stmts), str([q[:80] for q in _stmts if "tenant_id" not in q]))

# --------------------------------------------------------------------------- #
#  6. The evidence for one route                                               #
# --------------------------------------------------------------------------- #
db.execute("INSERT INTO community_features (tenant_id, feature_id, kind, source, source_ref, name, detail, geometry_json, "
           "dist_m, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (T, "gias:1", "schools", "gias", "1", "Test Primary", None,
            json.dumps({"type": "Point", "coordinates": list(P(10, 100))}), 90.0, "2026-10-16"))
db.execute("INSERT INTO community_features (tenant_id, feature_id, kind, source, source_ref, name, detail, geometry_json, "
           "dist_m, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (T, "gias:2", "schools", "gias", "2", "Further School", None,
            json.dumps({"type": "Point", "coordinates": list(P(10, 180))}), 170.0, "2026-10-16"))
E = cl.evidence("R1", now=date(2026, 10, 16))
ok("6: the route and its stored alternative, in adjacent columns", [c["label"] for c in E["columns"]] == ["This route", "Alternative 1"]
   and [c["key"] for c in E["columns"]] == ["R1", "R1@1"])
on, near = E["columns"][0]["on"], E["columns"][0]["near"]
ok("6: on the route (25 m): C1, C2, C8; within 250 m: and C3", on["all"] == 3 and near["all"] == 4, str((on["all"], near["all"])))
ok("6: fatal / serious / KSI on and near", (on["fatal"], on["serious"], on["ksi"]) == (0, 2, 2)
   and (near["fatal"], near["serious"], near["ksi"]) == (1, 2, 3), str((on, near)))
ok("6: KSI by road user: a pedestrian (C1), an e-scooter user (C8) on it; a motorcyclist (C3) only within 250 m",
   on["vru_ksi:pedestrian"] == 1 and on["vru_ksi:escooter"] == 1 and on["vru_ksi:motorcyclist"] == 0
   and near["vru_ksi:motorcyclist"] == 1 and near["vru_ksi:cyclist"] == 0 and near["vru_ksi:horse_rider"] == 0)
ok("6: any VRU hurt, goods vehicle, goods KSI, junction", near["vru_any"] == 4 and near["goods"] == 1 and near["goods_ksi"] == 1
   and near["junction"] == 1)
ok("6: the alternative counts its own: C4 only", E["columns"][1]["near"]["all"] == 1 and E["columns"][1]["on"]["all"] == 0)
ok("6: one place: C1 and C2, 33 m apart; C8 alone is not a place", len(E["locations"]) == 1
   and sorted(i[4:] for i in E["locations"][0]["ids"]) == ["C1", "C2"], str([L["ids"] for L in E["locations"]]))
L1 = E["locations"][0] if E["locations"] else {}
ok("6: the place in words: roads, junction, severities, who was hurt, years, how far along from A",
   L1.get("roads") == ["A6", "Unclassified road"] and L1.get("junction") == ["T or staggered junction"] and (L1.get("serious"), L1.get("slight")) == (1, 1)
   and L1.get("vru_words") == ["Pedestrian", "Cyclist"] and L1.get("years") == [2025] and abs((L1.get("along_m") or 0) - 1700) < 60,
   str(L1))
ok("6: the community considerations near it: the nearest of each kind, in metres",
   L1.get("community") == [{"kind": "Schools", "name": "Test Primary", "m": L1["community"][0]["m"]}]
   and 80 <= L1["community"][0]["m"] <= 100, str(L1.get("community")))
ok("6: the period, the caveat, 'not the assessment' and the credit ride along",
   E["period"] == "2021–2025" and E["caveat"] == cl.CAVEAT and E["not_a_verdict"] == cl.NOT_A_VERDICT and E["credit"] == PL["credit"])
ok("6: the records are the primary route's own (not C4, near the alternative only; not C7, near the site only)",
   sorted(r["collision_id"][4:] for r in E["records"]) == ["C1", "C2", "C3", "C8"])
# places ordered along the route, never by count: two more places, the far one with more collisions
_extra = [dict(keep[f"{Y}C1"], collision_id=f"X{i}", lon=lon, lat=LAT0, severity=3, routes={"R1": 1.0}, sites={},
               vru=[], vru_ksi=[], ksi=False, year=2024)
          for i, lon in enumerate((-0.94, -0.94 + 20 * DLON, -0.905, -0.905 + 10 * DLON, -0.905 + 20 * DLON))]
_locs = cl.locations(_extra, DIX, ROUTE)
ok("6: places are ordered along the route from A (nearest A first), not by how many collisions",
   [L["n"] for L in _locs] == [2, 3] and [L["no"] for L in _locs] == [1, 2] and _locs[0]["along_m"] < _locs[1]["along_m"])
ok("6: a team code reads its own team's routes only", raises(lambda: cl.evidence("R2", acc={"role": "ipt", "ipt": "IPT1"}))
   .__class__ is cl.EvidenceError and cl.evidence("R1", acc={"role": "ipt", "ipt": "IPT1"})["route_id"] == "R1")
ok("6: no such route → EvidenceError", isinstance(raises(lambda: cl.evidence("NOPE")), cl.EvidenceError))
ok("6: the file names", cl.file_name(E) == "route-collision-evidence-R1.pdf" and cl.file_name(E, "xlsx") == "route-collision-evidence-R1.xlsx")

# --------------------------------------------------------------------------- #
#  7. The PDF and the XLSX                                                     #
# --------------------------------------------------------------------------- #
_pdf = export.build_collision_evidence_pdf(E)
ok("7: the PDF is built (no basemap here: offline)", _pdf[:5] == b"%PDF-" and E["basemap"] is False and E["pages"] >= 1)
_t = " ".join(pdf_text(_pdf, "").split()) if shutil.which("pdftotext") else ""
ok("7: the title, the route, the period and DfT's words",
   not _t or ("Route collision evidence" in _t and "Quarry A" in _t and "Site B" in _t
              and "Police-reported injury collisions, 2021–2025 (DfT, final data)" in _t), _t[:400])
ok("7: the counts table, both columns, the route and the alternative",
   not _t or ("On the route (25 m)" in _t and "Within 250 m" in _t and "This route" in _t and "Alternative 1" in _t
              and "A pedestrian killed or seriously injured" in _t), _t[:900])
ok("7: the place, along the route, with the school near it",
   not _t or ("Places with more than one collision" in _t and "from A: A6" in _t and "Schools: Test Primary" in _t), _t[-1400:])
ok("7: every page says it is evidence, not the assessment, with DfT's caveats and the credit",
   not _t or (_t.count("It is not the assessment") == E["pages"] and "no legal duty" in _t
              and "Open Government Licence v3.0 (DfT road safety data)" in _t), _t[-900:])
ok("7: no verdict word on the sheet", not _t or not VERDICT.search(_t), str(VERDICT.findall(_t)))
_x = export.build_collision_evidence_xlsx(E)
import openpyxl  # noqa: E402
wb = openpyxl.load_workbook(io.BytesIO(_x))
ok("7: the XLSX: Summary, Places, Collisions, About", wb.sheetnames == ["Summary", "Places", "Collisions", "About"])
wc = wb["Collisions"]
_hdr = [c.value for c in wc[1]]
ok("7: one row per collision near the route, with the month and never the day", wc.max_row - 1 == 4 and "Month" in _hdr
   and not any(h and re.search(r"\b(date|day|time)\b", h, re.I) for h in _hdr), str(_hdr))
ok("7: ...nearest the route first, with 'On the route (25 m)' marked",
   [wc.cell(row=i, column=_hdr.index("Metres from this route") + 1).value for i in range(2, 6)]
   == sorted(wc.cell(row=i, column=_hdr.index("Metres from this route") + 1).value for i in range(2, 6))
   and "On the route (25 m)" in _hdr and wc.cell(row=2, column=_hdr.index("On the route (25 m)") + 1).value == "yes")
ws = wb["Summary"]
ok("7: the Summary's counts are numbers, the same as the PDF's",
   [ws.cell(row=6, column=j).value for j in (2, 3, 4, 5)] == [3, 4, 0, 1])
ok("7: the About sheet carries the caveat, 'not the assessment' and the source",
   [wb["About"].cell(row=i, column=1).value for i in (1, 2)] == [cl.CAVEAT, cl.NOT_A_VERDICT]
   and cl.SOURCE["url"] in wb["About"].cell(row=4, column=1).value)
_ex = read("backend/export.py")
_b = _ex.split("def build_collision_evidence_pdf(")[1].split("\ndef ")[0]
ok("7: on the map the slight ones are drawn first, so the KSI sit on top; the places are numbered",
   "for sev in (3, 2, 1):" in _b and "_ce_tag(c, *P(L[\"lon\"], L[\"lat\"]), L[\"no\"])" in _b)
ok("7: the demo's map carries its tag", '_map_tag(c, S.get("map_demo_tag"), cw, h1)' in _b
   and 'bulletin_doc.DEMO_MAP_TAG if notice else None' in read("backend/collisions.py"))
# not fetched yet
db.execute("DELETE FROM collision_records WHERE tenant_id = ?", (T,))
db.execute("DELETE FROM collision_meta WHERE tenant_id = ?", (T,))
E0 = cl.evidence("R1")
_t0 = " ".join(pdf_text(export.build_collision_evidence_pdf(E0), "").split()) if shutil.which("pdftotext") else ""
ok("7: not fetched yet: the sheet says so (and where it is fetched), no table",
   E0["fetched"] is False and (not _t0 or ("not been fetched yet" in _t0 and "Config page, Map and bulletin" in _t0
                                           and "How many, and where" not in _t0)), _t0[:500])
cl.refresh(fetchers={"download": stub_download(only_2025)}, today=date(2026, 10, 16))

# --------------------------------------------------------------------------- #
#  8. The endpoints                                                            #
# --------------------------------------------------------------------------- #
access.set_current(None)
for fn, label in ((lambda r: main.collision_layer(request=r), "GET /api/collisions"),
                  (lambda r: main.collision_status(request=r), "GET /api/collisions/status"),
                  (lambda r: main.collision_evidence_pdf("R1", request=r), "the evidence PDF"),
                  (lambda r: main.collision_evidence_xlsx("R1", request=r), "the evidence XLSX")):
    _e = raises(lambda: fn(_Request()))
    ok(f"8: {label} with no credential: 401", getattr(_e, "status_code", None) == 401)
os.environ["MAP_PASSWORD"] = "pw"
os.environ["GATE_SECRET"] = "s3cret-for-the-harness"
try:
    _mapc = gate.issue(gate.LEVEL_MAP) if hasattr(gate, "issue") else None
except Exception:
    _mapc = None
if _mapc:
    _e = raises(lambda: main.collision_layer(request=_Request(cookies={gate.COOKIE: _mapc})))
    ok("8: ...with the map password's cookie: 401 (R6: never on the public map)", getattr(_e, "status_code", None) == 401)
_src_main = read("backend/main.py")
for name in ("collision_layer", "collision_status", "_collision_evidence"):
    _f = _src_main.split(f"def {name}(")[1].split("\n@app.")[0].split("\ndef ")[0]
    ok(f"8: {name} checks _staff_request first", "if not _staff_request(request):" in _f and "401" in _f)
access.set_current("planner123")
_pl = main.collision_layer(request=_Request())
ok("8: a planner gets the layer", _pl["type"] == "FeatureCollection" and len(_pl["features"]) == 6)
_r = main.collision_evidence_pdf("R1", request=_Request())
ok("8: the evidence PDF: a PDF, named, never cached", _r.body[:5] == b"%PDF-" and _r.media_type == "application/pdf"
   and 'filename="route-collision-evidence-R1.pdf"' in _r.headers["Content-Disposition"] and _r.headers["Cache-Control"] == "no-store")
_rx = main.collision_evidence_xlsx("R1", request=_Request())
ok("8: the evidence XLSX likewise", _rx.body[:2] == b"PK" and "spreadsheetml" in _rx.media_type
   and 'filename="route-collision-evidence-R1.xlsx"' in _rx.headers["Content-Disposition"])
_e = raises(lambda: main.collision_evidence_pdf("NOPE", request=_Request()))
ok("8: no such route: 404", getattr(_e, "status_code", None) == 404)
_orig_cur = access.current
access.current = lambda: {"role": "ipt", "label": "North Team", "ipt": "IPT1"}
_e = raises(lambda: main.collision_refresh(request=_Request()))
ok("8: a team code's POST /api/collisions/refresh is refused, 403", getattr(_e, "status_code", None) == 403)
_e = raises(lambda: main.collision_evidence_pdf("R2", request=_Request()))
ok("8: a team code asking for another team's route: 404", getattr(_e, "status_code", None) == 404)
ok("8: ...its own team's route: the sheet", main.collision_evidence_pdf("R1", request=_Request()).body[:5] == b"%PDF-")
access.current = lambda: None
_e = raises(lambda: main.collision_refresh(request=_Request()))
ok("8: POST /refresh with no credential: 401", getattr(_e, "status_code", None) == 401)
access.current = _orig_cur
_cr = _src_main.split("def collision_refresh(")[1].split("\n@app.")[0]
ok("8: a planner or an admin starts the fetch", 'acc.get("role") not in ("planner", "admin")' in _cr and "collisions.start_refresh(" in _cr)
ok("8: the plan endpoints take collisions=1, OFF by default, through to route_map_export.plan",
   "collisions: int = 0," in _src_main.split("def route_map_export_pdf(")[1][:700]
   and "collisions: int = 0," in _src_main.split("def route_map_export_png(")[1][:700]
   and "collisions=bool(collisions))" in _src_main)

# --------------------------------------------------------------------------- #
#  9. The CLP plans                                                            #
# --------------------------------------------------------------------------- #
import basemap  # noqa: E402
v = basemap.view_centred(mid, LAT0, basemap.zoom_for_scale(20000, LAT0, route_map_export.FRAME_W_MM, route_map_export.W_PX),
                         route_map_export.W_PX, route_map_export.H_PX)
_reg = route_map_export.collisions_in_frame(v, "regional")
_loc = route_map_export.collisions_in_frame(v, "local")
ok("9: the regional plan draws the killed or seriously injured only; the local and site plans all three",
   route_map_export.COLLISION_KSI_ONLY == ("regional",) and _reg["ksi_only"] and not _loc["ksi_only"]
   and all(c["ksi"] for c in _reg["records"]) and any(not c["ksi"] for c in _loc["records"])
   and len(_reg["records"]) < len(_loc["records"]), str((len(_reg["records"]), len(_loc["records"]))))
ok("9: a plan draws no alternatives, so it leaves out a collision near a stored alternative only (C4)",
   not any(c["collision_id"].endswith("C4") for c in _loc["records"] + _reg["records"])
   and all(c["along"] == "route" for c in _loc["records"])
   and 'or c["along"] != "route":' in read("backend/route_map_export.py"))
ok("9: ...in the frame only, with the period and the credit", _loc["period"] == "2021–2025" and _loc["credit"] == PL["credit"]
   and _loc["severities"] == [1, 2, 3])
_far = basemap.view_centred(-0.5, 52.0, v["zoom"], v["w"], v["h"])
ok("9: a frame with none in it lists none", route_map_export.collisions_in_frame(_far, "local")["records"] == [])
S = {"tenant": "Test scheme", "month_long": "October 2026", "filter_words": "All routes", "map_legend_title": "Two-way movements a day",
     "volume_legend": [], "as_at": "Approved plan as at 16 Oct 2026", "map_routes": [], "places": [], "map_sections": [], "controls": [],
     "map_demo_tag": None}
S["plan"] = {"kind": "regional", "name": "Regional plan", "view": v, "denom": 20000, "scale_words": "1:20,000", "centre": None,
             "places": [], "fitted": False, "community": None, "community_asked": False, "collisions": _reg, "collisions_asked": True}
_tp = " ".join(pdf_text(export.build_route_map_pdf(S), "").split()) if shutil.which("pdftotext") else ""
ok("9: the plan's panel lists the collisions, KSI only said so, 'not the assessment', the credit",
   not _tp or ("Police-reported injury collisions, 2021–2025 (DfT)" in _tp and "the slight ones are on the local and site plans" in _tp
               and "not the assessment" in _tp and "(DfT road safety data)" in _tp and "Slight" not in _tp.split("(DfT)")[1][:60]), _tp[-700:])
S["plan"]["collisions"] = None
_tn = " ".join(pdf_text(export.build_route_map_pdf(S), "").split()) if shutil.which("pdftotext") else ""
ok("9: left off (the default): no block, no credit", not _tn or ("Police-reported injury collisions" not in _tn and "DfT road safety" not in _tn))
_rp = read("backend/route_map_export.py")
ok("9: plan() adds them only when asked", 'P["collisions"] = collisions_in_frame(P["view"], kind) if (collisions and P["view"]) else None' in _rp)
_bp = _ex.split("def build_route_map_pdf(")[1].split("\ndef ")[0]
ok("9: drawn over the routes and the community symbols", _bp.index("_draw_bulletin_schematic(") < _bp.index('_draw_community(c, PL, P, "over")')
   < _bp.index("_ce_dot(c, *P(r[\"lon\"], r[\"lat\"]), sev)"))

# --------------------------------------------------------------------------- #
# 10. Source level                                                             #
# --------------------------------------------------------------------------- #
MAP, APP = read("map/index.html"), read("frontend/index.html")
_grp = MAP.split('<div class="control-group" id="collision-group" hidden>')
ok("10: map — the group is hidden in the markup", len(_grp) == 2)
ok("10: map — ...and shown only when whoami answers level 'staff'",
   "communityStaff(RME.staff); collisionStaff(RME.staff);" in MAP and "if (g) g.hidden = !COLL.staff;" in MAP
   and "if (!COLL.staff) { COLL.on = false;" in MAP)
_inp = re.search(r'<input[^>]*id="layer-collisions"[^>]*>', MAP).group(0)
ok("10: map — OFF by default (no checked attribute), and the slight ones off until their own box is ticked",
   not re.search(r'\schecked(\s|>|=)', _inp.replace("this.checked", ""))
   and not re.search(r'\schecked(\s|>|=)', re.search(r'<input[^>]*id="coll-slight"[^>]*>', MAP).group(0))
   and "if (!slight) f.push(['<=', ['get', 'severity'], 2]);" in MAP)
_tog = MAP.split("function toggleCollisions(")[1].split("\n    }")[0]
ok("10: map — read only when ticked, only from /api/collisions, never from DfT",
   "if (COLL.on && !COLL.data) loadCollisions();" in _tog and MAP.count("fetch('/api/collisions'") == 1
   and "data.dft.gov.uk" not in MAP and "data.dft.gov.uk" not in APP)
_pop = MAP.split("function collisionPopup(")[1].split("function renderCollisionPanel(")[0]
ok("10: map — the popup gives the month and year, never the day or time (R6), and says it is evidence",
   "{ month: 'long', year: 'numeric' }" in _pop and "day:" not in _pop and "time" not in _pop.lower().replace("toLocaleDateString", "")
   and "not the assessment" in _pop)
ok("10: map — one ink, size by severity, slight a hollow ring (no colour that claims a rating)",
   "'circle-color': ['case', ['==', ['get', 'severity'], 3], '#FFFFFF', COLL_INK]" in MAP
   and "['match', ['get', 'severity'], 1, 4.5, 2, 3.4, 2.2]" in MAP)
ok("10: map — a collision near an alternative only is drawn only while Alternative routes is ticked, and comes and goes with it",
   "if (!altsShown()) f.push(['==', ['get', 'along'], 'route']);" in MAP
   and "function altsShown() { return !!(document.getElementById('layer-alts') || {}).checked; }" in MAP
   and "if (typeof COLL !== 'undefined' && COLL.data) { ensureCollisionLayers(); renderCollisionPanel(); }"
       in MAP.split("function toggleAlts(")[1].split("\n    }")[0])
_ecl = MAP.split("function ensureCollisionLayers(")[1].split("function collisionPopup(")[0]
ok("10: map — a tick on an existing layer goes straight on (the filter is not left waiting for the map to go idle)",
   _ecl.index("if (map.getLayer('collision-points')) {") < _ecl.index("if (!map.isStyleLoaded()) { map.once('idle', ensureCollisionLayers); return; }")
   and "map.setFilter('collision-points', collisionFilter());" in _ecl.split("if (!map.isStyleLoaded())")[0])
ok("10: map — the group's words count the alternatives' apart and say how to see them",
   "are along the alternative routes only: " in MAP and "tick Alternative routes to see them." in MAP)
ok("10: app — the Config panel counts them apart too",
   "are along the stored alternative routes only: on the Route map while Alternative routes is ticked" in APP)
ok("10: map — re-added after a basemap switch", "if (typeof COLL !== 'undefined' && COLL.data) ensureCollisionLayers();" in MAP)
ok("10: map — the export card's box adds collisions=1, off by default",
   "if (col && col.checked) q.set('collisions', '1');" in MAP and 'id="rme-collisions"' in MAP
   and not re.search(r'\schecked', re.search(r'<input[^>]*id="rme-collisions"[^>]*>', MAP).group(0)))
_cblock = MAP.split("// ---------------------------------------------------------------- the collision history")[1].split("checkRouteExportStaff();")[0]
_vis = " ".join(re.findall(r"'([^'\n]{12,})'|`([^`]{12,})`", _cblock).__str__().split())
ok("10: map — no verdict word in the group's words", not VERDICT.search(_vis), str(VERDICT.findall(_vis)))
_cp = APP.split("function CollisionPanel(")[1].split("\nfunction ")[0]
ok("10: app — Config → Map and bulletin carries the panel; a planner or admin fetches; asks every 5 s while it runs",
   "<CollisionPanel access={access} />" in APP and 'fetch(`${API}/collisions/refresh`, { method: "POST" })' in _cp
   and 'access.role === "planner" || access.role === "admin"' in _cp and "setTimeout(read, 5000)" in _cp
   and APP.count("/collisions/status") == 1)
ok("10: app — the panel says it is not the assessment, staff only, never the public map or bulletin, and when to fetch again",
   "It is not the assessment." in _cp and "never on the public map or the bulletin" in _cp and "late-July release" in _cp)
_cb = APP.split("function CollisionEvidenceButton(")[1].split("\nfunction ")[0]
ok("10: app — the Routes page's buttons (PDF and XLSX) for the route picked in the list",
   "<CollisionEvidenceButton routeId={selected} />" in APP and 'go("pdf")' in _cb and 'go("xlsx")' in _cb
   and "collision-evidence.${kind}" in APP)
ok("10: app — the Routes page export menu's box", 'if(addColl) q.set("collisions", "1");' in APP and "data-rme-collisions" in APP
   and "useState(false);   // 16 Oct 2026 (CLOCS v5 C1)" in APP)
ok("10: app — no verdict word on the panel or the buttons", not VERDICT.search(_cp + _cb), str(VERDICT.findall(_cp + _cb)))
ok("10: the public map's data and the bulletin never read the collision history (R6)",
   "collision" not in read("backend/network.py").split("def public_map_data(")[1].split("\ndef ")[0].lower()
   and "import collisions" not in read("backend/bulletin.py") and "import collisions" not in read("backend/bulletin_doc.py"))
ok("10: the tables are tenanted, in the package (last) and in the audit's registry",
   {"collision_records", "collision_meta"} <= set(db.TENANTED_TABLES)
   and tenant_package.ORDER[-2:] == ["collision_records", "collision_meta"]
   and '"collision_records", "collision_meta",' in read("backend/tests/test_tenant_audit.py"))
GUIDE, TECH = read("frontend/help/index.html"), read("frontend/help/technical/index.html")
_g = GUIDE.split("<li><strong>Collision history</strong>")[1].split("</li>")[0] if "<li><strong>Collision history</strong>" in GUIDE else ""
ok("10: the user guide says what it is, who sees it, where it comes from, what it cannot tell you, and that it is not the assessment",
   _g and "staff only" in _g and "STATS19" in _g and "250 m" in _g and "not the assessment" in _g
   and "police" in _g and "2016" in _g and "never the day or time" in _g and "Collision evidence (PDF)" in _g)
ok("10: the guides say the alternatives' collisions show with Alternative routes and the plans leave them out",
   "those near a stored alternative route only appear while <em>Alternative routes</em>" in _g
   and "<code>alternatives_only</code>" in TECH)
ok("10: the technical guide: the endpoints, the files, the years rule, the codes, the licence",
   'id="t9-collisions"' in TECH and "/api/collisions" in TECH and "data.dft.gov.uk" in TECH and "late July" in TECH
   and "casualty_class" in TECH and "Open Government Licence v3.0" in TECH)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)

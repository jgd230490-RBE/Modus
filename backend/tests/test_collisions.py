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
    # 28 Oct 2026 (0d): the hour each happened (C1 falls on a Saturday in 2025: the date wins over day_of_week's "3")
    times = {"C1": "08:15", "C2": "17:40", "C8": "23:05", "C3": "16:00"}
    out = [C_HEAD]
    for cid, (lon, lat, sev, d, rc, rn, rt, sl, jd, rc2, rn2, light) in pts.items():
        out.append(f"{y}{cid},{y},{cid},0,0,{lon},{lat},33,{sev},2,1,{d},3,{times.get(cid, '08:15')},E10000018,{rc},{rn},{rt},"
                   f"{sl},{jd},{rc2},{rn2},{light}")
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
# NARROWED 28 Oct 2026 (0d, John's yes to notes\collision-time-mockup-1028): the hour and a weekday flag are kept in the
# details too; still never the date, the day or the minute
ok("3: the month is kept (2025-03), never the date, the day or the minute", c1.get("month") == "2025-03" and "date" not in c1
   and "time" not in c1 and "day" not in json.dumps(c1).lower().replace("daylight", "").replace("weekday", "")
   and ":15" not in json.dumps(c1), str(c1.get("month")))
ok("3: ...the hour (08:15 -> 8) and whether it fell Monday to Friday, read from the date (Sat 15 Mar 2025 -> False although "
   "day_of_week says 3)", c1["detail"].get("hour") == 8 and c1["detail"].get("weekday") is False
   and keep[f"{Y}C2"]["detail"]["hour"] == 17 and keep[f"{Y}C2"]["detail"]["weekday"] is True, str(c1.get("detail")))
ok("3: hour and weekday readers: blank or odd time -> None; DfT's day_of_week when the date does not read (1 Sunday, 7 Saturday)",
   cl._hour_of("") is None and cl._hour_of("-1") is None and cl._hour_of("24:00") is None and cl._hour_of("00:59") == 0
   and cl._weekday_of("", "1") is False and cl._weekday_of("", "7") is False and cl._weekday_of("x", "2") is True
   and cl._weekday_of("", "") is None and cl._weekday_of("03/11/2026") is True)
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
# NARROWED 22 Oct 2026 (evidence v3): the fetch also asks for DfT's traffic counts; the road safety files are as before
ok("4: the five years' collision files asked for; vehicles and casualties only for the year with collisions in the strip",
   sorted(u.rsplit("/", 1)[-1] for u in CALLS if "data.dft.gov.uk" in u) == sorted(
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
# 22 Oct 2026 (evidence v2): the plan beside the counts — R1's Approved lines (month 11 its busiest) and R2's, and one
# stored run R1 and R2 share over the route's first 1.7 km (runs are built from stored road routes; set by hand here)
for fid, rid, mi, q in (("F1", "R1", 10, 2900.0), ("F2", "R1", 11, 5800.0), ("F3", "R2", 11, 2900.0)):
    db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, "
               "material_type, vehicle_type, status, ipt) VALUES (?, ?, ?, ?, '', '', ?, 't', ?, ?, 'Approved', 'IPT1')",
               (T, fid, rid, mi, q, "General / imported", PROF))
db.execute("INSERT INTO route_sections (tenant_id, section_id, leg, routes_json, geometry_json, length_km, built_at) "
           "VALUES (?, ?, ?, ?, ?, ?, ?)", (T, "Stest", "loaded", json.dumps(["R1", "R2"]), json.dumps(ROUTE[:2]), 1.69, "x"))
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
# NARROWED 22 Oct 2026 (evidence v2): the places are the appendix, each row "1.7 km: A6 …" under its stretch's heading
ok("7: the place, along the route, with the school near it",
   not _t or ("Appendix: places with more than one collision" in _t and "km: A6" in _t and "from A: A6" not in _t
              and "Stretch 1 · A6" in _t and "Schools: Test Primary" in _t), _t[-1400:])
# NARROWED 22 Oct 2026 (evidence v3): the assessor's last page also says it, once more, in its lead
ok("7: every page says it is evidence, not the assessment, with DfT's caveats and the credit",
   not _t or (_t.count("It is not the assessment") == E["pages"] + 1 and "no legal duty" in _t
              and "Open Government Licence v3.0 (DfT road safety data)" in _t), _t[-900:])
ok("7: no verdict word on the sheet", not _t or not VERDICT.search(_t), str(VERDICT.findall(_t)))
_x = export.build_collision_evidence_xlsx(E)
import openpyxl  # noqa: E402
wb = openpyxl.load_workbook(io.BytesIO(_x))
# NARROWED 22 Oct 2026 (evidence v2): the Stretches sheet after the Summary
# NARROWED 22 Oct 2026 (evidence v3): the routes compared, the lorries, the cycle routes and left turns
ok("7: the XLSX: Summary, Stretches, Routes compared, Lorries, Cycle and left turns, Places, Collisions, About",
   # NARROWED 22 Oct 2026 (v3 part 2): and the comparison with roads like these
   # NARROWED 28 Oct 2026 (0d): and By time of day after the routes compared
   wb.sheetnames == ["Summary", "Stretches", "Routes compared", "By time of day", "Lorries", "Compared with roads like these",
                     "Cycle and left turns",
                     "Places", "Collisions", "About"],
   str(wb.sheetnames))
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
# REVERSED 22 Oct 2026 (evidence v2, the user's yes): the 40 numbered place tags piled up in town; the map labels the
# stretches instead and the places are numbered in the appendix only
ok("7: on the map the slight ones are drawn first, so the KSI sit on top; the STRETCHES are labelled, the places are not",
   "for sev in (3, 2, 1):" in _b and "_ce_tag(c, *P(L[\"lon\"], L[\"lat\"]), L[\"no\"])" not in _b
   and 'S["stretch_labels"].append(t)' in _b and E.get("stretch_labels") == ["1  A6"], str(E.get("stretch_labels")))
ok("7: the demo's map carries its tag", '_map_tag(c, S.get("map_demo_tag"), cw, h1)' in _b
   and 'bulletin_doc.DEMO_MAP_TAG if notice else None' in read("backend/collisions.py"))

# --------------------------------------------------------------------------- #
#  7b. Evidence v2 (22 Oct 2026, the user's yes to notes\collision-evidence-   #
#      v2-mockup-1022): stretches, the plan beside, the strip, the fold        #
# --------------------------------------------------------------------------- #
ok("7b: the new counts row: a vulnerable road user hurt, a goods vehicle over 3.5 t involved (C1: pedestrian + type 21)",
   ("vru_goods", "A vulnerable road user hurt, a goods vehicle over 3.5 t involved") in cl.ROWS
   and E["columns"][0]["on"]["vru_goods"] == 1 and E["columns"][0]["near"]["vru_goods"] == 1
   and E["columns"][1]["near"]["vru_goods"] == 0)
ok("7b: route_road: a numbered first road; else a numbered second road; else none",
   cl.route_road({"road": "A6", "road2": "B582"}) == "A6" and cl.route_road({"road": "Unclassified road", "road2": "B4114"}) == "B4114"
   and cl.route_road({"road": "C road", "road2": None}) is None and cl.route_road({"road": "B road", "road2": "Unclassified road"}) is None)
MI = 1609.344


def _c(i, road, sl=30, sev=3, road2=None):
    return {"collision_id": f"S{i}", "road": road, "road2": road2, "speed_limit": sl, "severity": sev, "ksi": sev < 3,
            "vru": [], "vru_ksi": [], "goods": False}


_on = [(0.2 * MI, _c(1, "B4114")), (0.5 * MI, _c(2, "B4114")), (0.9 * MI, _c(3, "Unclassified road", road2="B4114")),
       (1.1 * MI, _c(4, "B4114")), (1.3 * MI, _c(5, "B582")), (1.6 * MI, _c(6, "B4114")),
       (2.0 * MI, _c(7, "A563")), (2.2 * MI, _c(8, "A563")), (2.6 * MI, _c(9, "A563")), (3.0 * MI, _c(10, "A563"))]
_st = cl.stretches(_on, 4.0 * MI)
ok("7b: stretches: cut where the recorded road changes; a road named by fewer than 4 collisions (B582 once) joins its "
   "neighbour; a side-road record counts for its numbered second road",
   [s["name"] for s in _st] == ["B4114", "A563"] and len(_st[0]["on"]) == 6 and len(_st[1]["on"]) == 4,
   str([(s["name"], len(s["on"])) for s in _st]))
ok("7b: ...the boundary half way between the last of one road and the first of the next; from A to B, no gap",
   _st[0]["from_m"] == 0 and abs(_st[0]["to_m"] - 1.8 * MI) < 1 and _st[1]["from_m"] == _st[0]["to_m"]
   and _st[1]["to_m"] == 4.0 * MI and [s["no"] for s in _st] == [1, 2])
_long = [(i * 0.5 * MI, _c(i, "A6", 30 if i < 6 else 60)) for i in range(1, 13)]
_sl = cl.stretches(_long, 7.0 * MI)
ok("7b: one road longer than 5 mi is split once where its speed limits change (30 → 60 mph), each part named by its limits",
   [s["name"] for s in _sl] == ["A6, 30 mph", "A6, 60 mph"] and abs(_sl[0]["to_m"] - 2.75 * MI) < 1
   and _sl[-1]["to_m"] == 7.0 * MI, str([(s["name"], s["from_m"] / MI, s["to_m"] / MI) for s in _sl]))
ok("7b: ...not when it is 5 mi or shorter", [s["name"] for s in cl.stretches(_long, 5.0 * MI)] == ["A6"])
_mixed = [(i * 0.5 * MI, _c(i, "A6", (30, 60)[i % 2])) for i in range(1, 13)]
ok("7b: ...nor when the limits do not change in one place (fewer than 80 % on their side)",
   [s["name"] for s in cl.stretches(_mixed, 7.0 * MI)] == ["A6"])
_none = cl.stretches([(100.0, _c(1, "Unclassified road")), (900.0, _c(2, "C road"))], 2000.0)
ok("7b: no numbered road at all: one stretch, the whole route", [(s["name"], s["from_m"], s["to_m"]) for s in _none]
   == [("The whole route", 0.0, 2000.0)] and len(_none[0]["on"]) == 2)
ok("7b: no collision on the route: one stretch, the whole route", [s["name"] for s in cl.stretches([], 1000.0)] == ["The whole route"])
ok("7b: the fixture route is one stretch, A6 (C1, C8 name it; C2 on an unclassified road joins it)",
   [(s["name"], s["n"], s["ksi"], s["places"], s["place_nos"]) for s in E["stretches"]] == [("A6", 3, 2, 1, (1, 1))],
   str([(s["name"], s["n"], s["ksi"], s["places"], s["place_nos"]) for s in E["stretches"]]))
_fac = conversions.load_factors()
_vs = _fac.get("vehicles", {}) or {}
import derived  # noqa: E402
_fbp, _fbn = derived.payload_for(None, _fac)


def _loads(q):
    return main._month_kpi_line({"route_id": "R1", "quantity": q, "unit": "t", "material_type": "General / imported",
                                 "vehicle_type": PROF}, "vehicles", _fac, _vs, _fbp, _fbn)["vehicle_loads"]


_wd = main._working_days(_fac)
PLAN = E["plan"] or {}
ok("7b: the plan: R1's busiest month of Approved lines (month 11, not 10), its movements a day that month, the vehicle",
   PLAN.get("month") == 11 and PLAN.get("month_words") == "Nov 2026" and abs(PLAN.get("per_day", 0) - _loads(5800) / _wd) < 1e-9
   and PLAN.get("vehicles") == [conversions.vehicle_label(_fac, PROF)], str(PLAN))
ok("7b: ...the shared run: R1 + R2 that month, over its first 1.7 km (road_load's rule: Σ owners' loads ÷ working days)",
   len(PLAN.get("segments") or []) == 1 and PLAN["segments"][0][0] < 5 and abs(PLAN["segments"][0][1] - 1690) < 40
   and abs(PLAN["segments"][0][2] - (_loads(5800) + _loads(2900)) / _wd) < 1e-9, str(PLAN.get("segments")))
_lo, _hi = E["stretches"][0]["lorries"]
ok("7b: the stretch's lorries: the lowest and highest whole movements a day along it — R1's own past the run, the run's",
   (_lo, _hi) == (int(_loads(5800) / _wd + 0.5), int((_loads(5800) + _loads(2900)) / _wd + 0.5)), str((_lo, _hi)))
_pl = {"per_day": 3.4, "segments": [(0.0, 1000.0, 9.6)]}
ok("7b: stretch_lorries: covered → the run's figure; a stretch past it → the route's own; partly → both; no plan → None",
   cl.stretch_lorries(_pl, 0, 1000) == (10, 10) and cl.stretch_lorries(_pl, 1000, 2000) == (3, 3)
   and cl.stretch_lorries(_pl, 500, 2000) == (3, 10) and cl.stretch_lorries(None, 0, 10) is None
   and cl.stretch_lorries(_pl, 0, 1030) == (10, 10) and cl.stretch_lorries(_pl, 0, 1240) == (10, 10)
   and cl.stretch_lorries(_pl, 0, 1260) == (3, 10))   # GAP_M: a gap under 250 m (a gate's last metres) is not a stretch
ok("7b: the uncovered gap that brings in the route's own figure is GAP_M = 250 m", cl.GAP_M == 250 and cl.OVERLAP_M == 50)
ok("7b: a route with no Approved line has no plan (and the sheet says so)",
   cl.plan_beside("R404", DIX, ROUTE) is None and "plan_error" in E)
ok("7b: the plan never becomes a rate: nothing divides a collision count by a lorry figure",
   not re.search(r"\[\"n\"\]\s*/|ksi\"\]\s*/|/\s*plan|/\s*st\[\"lorries", read("backend/collisions.py") + _ex))
ok("7b: densest_window: the 1-unit window with the most collisions on the route, None with fewer than 3",
   cl.densest_window([(m, None) for m in (100, 2000, 2100, 2300, 2400, 5000)], 1000) == (1700.0, 2700.0)
   and cl.densest_window([(1.0, None), (2.0, None)], 1000) is None,
   str(cl.densest_window([(m, None) for m in (100, 2000, 2100, 2300, 2400, 5000)], 1000)))
ok("7b: pdf_nearby: schools and health within 250 m, bus stops within 100 m; nothing else (the XLSX keeps them all)",
   cl.pdf_nearby([{"kind": "Schools", "name": "S", "m": 240}, {"kind": "Bus stops", "name": "B", "m": 101},
                  {"kind": "Bus stops", "name": "B2", "m": 99}, {"kind": "Sports facilities", "name": "X", "m": 20},
                  {"kind": "Health centres", "name": "H", "m": 250}, {"kind": "Hospitals", "name": "Y", "m": 251}])
   == [{"kind": "Schools", "name": "S", "m": 240}, {"kind": "Bus stops", "name": "B2", "m": 99},
       {"kind": "Health centres", "name": "H", "m": 250}])
ok("7b: each place keeps every kind's nearest (no limit of four) for the XLSX, and its stretch",
   "nearby_community(L[\"lon\"], L[\"lat\"], index, limit=None, feats=feats)" in read("backend/collisions.py")
   and L1.get("stretch") == 1 and L1.get("nearby_pdf") == L1.get("community"))
ok("7b: the map draws the collisions ON the route only (C1, C2, C8; not C3, 200 m off it)",
   E["drawn_count"] == 3 and sorted(r["collision_id"][4:] for r in E["on"]) == ["C1", "C2", "C8"])
ok("7b: the PDF: the strip, the stretch table with the plan beside it, the ring and square explained",
   not _t or ("Along the route, A to B" in _t and "Along the route, stretch by stretch" in _t
              and "ring: a vulnerable road user hurt" in _t and "square: a goods vehicle over 3.5 t involved" in _t
              and f"R1 plans {int(_loads(5800) / _wd + 0.5)} lorry movements a day in its busiest month (Nov 2026" in _t
              and f"{_lo}–{_hi}" in _t and "neither is divided by the other" in _t and "The whole route" in _t), _t[:2400])
ok("7b: the PDF says what is drawn and what is only counted",
   not _t or ("Drawn: the 3 collisions on this route's road route (within 25 m)" in _t
              and "1 more within 250 m, on side and parallel roads, are counted in the table, not drawn" in _t), _t[:1500])
ok("7b: a counts row 0 in every column is folded into one sentence (horse rider, mobility scooter, …); the rest print",
   not _t or ("A horse rider killed or seriously injured" not in _t and "A mobility scooter user killed" not in _t
              and "No cyclist, horse rider or mobility scooter user was killed or seriously injured on either route or "
                  "within 250 m, 2021–2025." in _t
              and "A pedestrian killed or seriously injured" in _t
              and "A vulnerable road user hurt, a goods vehicle over 3.5 t involved" in _t), _t[:2600])
ok("7b: ...the XLSX Summary keeps every row, the zero ones too",
   [ws.cell(row=i, column=1).value for i in range(6, 6 + len(cl.ROWS))] == [l for _, l in cl.ROWS])
ok("7b: the appendix follows the counts table and names its Nearby rule",
   not _t or ("Appendix: places with more than one collision" in _t and "bus stops (100 m)" in _t))
ok("7b: no rate, score or ranking words on the sheet",
   not _t or not re.search(r"\bper (mile|km|lorry|movement)\b|\brate\b|\bworst\b|\branked?\b|\bscore\b", _t, re.I),
   str(re.findall(r"\bper (?:mile|km|lorry|movement)\b|\brate\b|\bworst\b|\branked?\b|\bscore\b", _t, re.I)))
_wt = wb["Stretches"]
_sh = [c.value for c in _wt[3]]
ok("7b: the XLSX Stretches sheet: one row a stretch, the counts and the lorries as numbers",
   _sh[:3] == ["No", "Stretch", "Road"] and _wt.cell(row=4, column=2).value == "A6" and _wt.cell(row=4, column=8).value == 3
   and _wt.cell(row=4, column=15).value == _lo and _wt.cell(row=4, column=16).value == _hi and _wt.max_row == 4, str(_sh))
ok("7b: the XLSX Collisions sheet adds the distance from A and the stretch (blank off the route)",
   _hdr[_hdr.index("Distance from A (km)") + 1] == "Stretch"           # NARROWED 22 Oct 2026 (v3): detail columns follow
   and sorted(wc.cell(row=i, column=_hdr.index("Stretch") + 1).value or 0 for i in range(2, 6)) == [0, 1, 1, 1])
ok("7b: the inset is drawn only at twice the map's scale or more, in a free corner, and says its window and scale",
   "if mag < 2:" in _b and (E["inset"] is None or (E["inset"]["mag"] >= 2 and "× the scale of the map" in E["inset"]["words"])))
_lay = export.collision_strip_layout(E, 500)
ok("7b: the strip: one mark per collision on the route, stacked by distance from A, bins at least 6.5 pt wide",
   sum(len(v) for v in _lay["bins"].values()) == 3 and _lay["top"] >= 1
   and (_lay["pw"] * _lay["bin"] * _lay["unit_m"] / _lay["length_m"]) >= 6.5)
ok("7b: no verdict word in the new words", not VERDICT.search(" ".join(cl.PDF_NEARBY_M) + _b + " ".join(
   s["name"] for s in E["stretches"])))

# --------------------------------------------------------------------------- #
#  7c. Evidence v3 (22 Oct 2026, the user's yes to notes\collision-evidence-   #
#      v3-mockup-1022): lorries, cycle routes, left turns, the routes compared, #
#      the CLOCS box, the assessor's page                                       #
# --------------------------------------------------------------------------- #
VX_HEAD = ("collision_index,collision_year,collision_ref_no,vehicle_reference,vehicle_type,towing_and_articulation,"
           "vehicle_manoeuvre_historic,vehicle_manoeuvre,journey_purpose_of_driver_historic,journey_purpose_of_driver")
_vk = {k: dict(keep[k], goods=False, detail={}) for k in (f"{Y}C1", f"{Y}C3", f"{Y}C8")}
cl.read_vehicles(write("vx.csv", "\n".join([
    VX_HEAD,
    f"{Y}C1,{Y},C1,1,21,1,-1,7,-1,1",      # 7.5 t+, articulated, turning left (2024 field), journey for work
    f"{Y}C1,{Y},C1,2,98,0,-1,19,-1,6",     # a second goods vehicle, weight not recorded, going ahead
    f"{Y}C3,{Y},C3,1,20,0,8,-1,1,-1",      # 3.5-7.5 t waiting to turn left (only the _historic field filled), work (historic)
    f"{Y}C8,{Y},C8,1,9,0,-1,7,-1,9",       # a car turning left: not a goods vehicle, but a left turn
]) + "\n"), _vk)
_d1, _d3, _d8 = (_vk[f"{Y}{k}"]["detail"] for k in ("C1", "C3", "C8"))
ok("7c: read_vehicles: weight classes in order (7.5 t+, 3.5-7.5 t, not recorded), articulated, turning left, work journey",
   _d1.get("goods_types") == ["21", "98"] and _d1.get("goods_artic") is True and _d1.get("goods_left") is True
   and _d1.get("goods_work") is True and _vk[f"{Y}C1"]["goods"] is True, str(_d1))
ok("7c: ...the years before 2024 fill only the _historic fields: they are read when the new field is -1",
   _d3.get("goods_types") == ["20"] and _d3.get("goods_left") is True and _d3.get("goods_work") is True and _d3.get("goods_artic") is False, str(_d3))
ok("7c: ...a car turning left is a left turn, not a goods vehicle",
   _d8.get("left_turn") is True and _d8.get("goods_types") == [] and _vk[f"{Y}C8"]["goods"] is False, str(_d8))
ok("7c: the goods words: 'weight not recorded' is DfT's 98, counted as over 3.5 t", cl.GOODS_WORDS["98"] == "weight not recorded"
   and cl.GOODS_TYPES == {"20", "21", "98"} and cl.LEFT_MANOEUVRES == {"7", "8"})
_ux = cl.read_collisions(write("cu.csv", C_HEAD + ",urban_or_rural_area\n" + collision_rows(Y).split("\n")[1] + ",2\n"), DIX, year=Y)
ok("7c: DfT's urban / rural flag is kept (2 = rural); missing reads None",
   next(iter(_ux.values()))["detail"]["urban"] == 2 and keep[f"{Y}C1"]["detail"]["urban"] is None)
_cols3 = [c.lower() for c in db._columns_of(db.get_conn().cursor(), "collision_records")]
ok("7c: stored as detail_json (one column, migrated on boot); still no day, date or time column",
   "detail_json" in _cols3 and not any(c in _cols3 for c in ("date", "day", "time", "day_of_week")))
ok("7c: the fetch says it read the vehicle details", cl.status()["vehicle_details"] is True)
_rr = cl.records(["R1"])
ok("7c: the details come back from storage", any((c.get("detail") or {}).get("goods_types") == ["21"] for c in _rr), str([c.get("detail") for c in _rr]))
ok("7c: has_details only when every counted collision carries them (C2 has no vehicle row in the fixture)",
   cl.has_details([{"detail": {"goods_types": []}}]) and not cl.has_details([{"detail": {"goods_types": []}}, {"detail": {"urban": 1}}])
   and E["details"] is False and not any(k in E["columns"][0]["on"] for k, _ in cl.DETAIL_ROWS))
_drows = cl.ROWS + cl.DETAIL_ROWS
_syn = [dict(c, detail={"goods_types": ["21"], "goods_artic": True, "goods_left": True, "left_turn": True}, vru=["cyclist"],
             routes={"R1": 5.0}) for c in _rr[:1]]
_cf = cl.counts_for(_syn, "R1", _drows)
ok("7c: the detail rows count when the details are there",
   (_cf["on"]["goods_75"], _cf["on"]["goods_artic"], _cf["on"]["goods_left"], _cf["on"]["cyclist_left"], _cf["on"]["cyclist_any"]) == (1, 1, 1, 1, 1))
# the route's own left turns, on an L: east 600 m then north 600 m (anticlockwise = a left turn); east then south = a right
_E = [[-0.95 + i * 50 * DLON, LAT0] for i in range(13)]
_left = _E + [[_E[-1][0], LAT0 + i * 50 * DLAT] for i in range(1, 13)]
_right = _E + [[_E[-1][0], LAT0 - i * 50 * DLAT] for i in range(1, 13)]
_lt = cl.left_turns(DIX, _left)
ok("7c: left_turns: a 90 degree turn to the left is one turn, about 600 m from A; a right turn is none",
   len(_lt) == 1 and 80 <= _lt[0]["deg"] <= 100 and abs(_lt[0]["m"] - 600) < 40 and cl.left_turns(DIX, _right) == [], str(_lt))
_cyc = [("Test cycle path", [[-0.95 + 100 * DLON, LAT0 + 10 * DLAT], [-0.95 + 500 * DLON, LAT0 + 10 * DLAT]]),
        ("NCN test", [[-0.95 + 590 * DLON, LAT0 - 100 * DLAT], [-0.95 + 590 * DLON, LAT0 + 100 * DLAT]])]
_g = cl._SegGrid(DIX, _cyc)
_ca = cl.cycle_along(DIX, _E, _g)
ok("7c: cycle_along: 400 m beside a cycle path 10 m away (within 20 m), one crossing route meets it (within 8 m)",
   380 <= len(_ca["beside_m"]) * 10 <= 500 and [n for _, n in _ca["meets"]] == ["NCN test"] and abs(_ca["meets"][0][0] - 590) < 20,
   str((len(_ca["beside_m"]), _ca["meets"])))
ok("7c: a left turn within 30 m of a cycle route names it", cl.left_turns(DIX, _left, _g)[0]["cycle"] == "NCN test")
ok("7c: the measures are fixed and said on the sheet", (cl.CYCLE_BESIDE_M, cl.CYCLE_MEETS_M, cl.TURN_MIN_DEG, cl.TURN_CYCLE_M) == (20, 8, 45, 30))
# the cycle routes on the fixture route, then the evidence again
for i, (n, ln) in enumerate(_cyc):
    db.execute("INSERT INTO community_features (tenant_id, feature_id, kind, source, source_ref, name, detail, geometry_json, "
               "dist_m, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (T, f"osm:c{i}", "cycle", "osm", f"c{i}", n, None, json.dumps({"type": "LineString", "coordinates": ln}), 5.0, "2026-10-16"))
E3 = cl.evidence("R1", now=date(2026, 10, 16))
H3 = E3["headline"]
ok("7c: the routes compared: this route and Alternative 1, side by side; the plan's lorries for this route only",
   [h["label"] for h in H3] == ["This route", "Alternative 1"] and H3[0]["on"] == 3 and H3[1]["on"] == 0
   and H3[0]["lorries"] is not None and H3[1]["lorries"] is None and H3[0]["goods"] == 1 and H3[0]["cyclist"] == 1, str(H3))
ok("7c: ...and the cycle figures for each (beside, meets, left turns)",
   H3[0]["beside"] is not None and H3[0]["meets"] == 1 and H3[0]["turns"] == 0 and "turns_cycle" in H3[1], str(H3))
ok("7c: the lorry list: each collision on the route with a goods vehicle, from A",
   [L_["collision_id"][4:] for L_ in E3["lorry_list"]] == ["C1"] and E3["lorry_list"][0]["severity"] == "Serious")
ok("7c: the alternatives are drawn (dashed) and the cycle routes too", [l for l, _ in E3["alt_lines"]] == ["Alternative 1"]
   and len(E3["cycle_lines"]) == 2 and E3["cycle_shown"] is True)
ok("7c: the community credit is on the sheet (schools, health, bus stops and cycle routes come from that layer)",
   "OpenStreetMap contributors (ODbL)" in (E3["community_credit"] or ""))
_pdf3 = export.build_collision_evidence_pdf(E3)
_t3 = " ".join(pdf_text(_pdf3, "").split()) if shutil.which("pdftotext") else ""
ok("7c: the PDF: page 1 opens with the routes compared and the CLOCS box",
   not _t3 or ("This route and its alternatives" in _t3 and "For the CLOCS route risk assessment" in _t3
               and "5.6a assess and select routes" in _t3 and "the project's own incidents (5.1a) are not in this data" in _t3), _t3[:1500])
ok("7c: ...the cycle routes and the route's left turns, said as facts with how they are measured",
   not _t3 or ("Cycle routes and the route's left turns" in _t3 and "run beside a cycle route (within 20 m)" in _t3
               and "The route makes 0 left turns" in _t3 and "mapped by volunteers" in _t3), _t3[:3000])
ok("7c: ...the lorry table, and a note that the details come with the next fetch (C2 has none in the fixture)",
   not _t3 or ("Collisions on the route involving a goods vehicle over 3.5 t" in _t3 and "read from the next fetch" in _t3))
ok("7c: ...the last page is for the assessor: ten questions, the boxes, the sign-off, and it says it is not a CLOCS form",
   not _t3 or ("For the route risk assessment" in _t3 and "not a CLOCS form" in _t3 and "10. What measures are proposed" in _t3
               and "Assessed by" in _t3 and "Review before phase" in _t3) and E3["assessor_page"] == E3["pages"], _t3[-1500:])
ok("7c: ...the community credit in the footer", not _t3 or "OpenStreetMap contributors (ODbL)" in _t3)
ok("7c: no verdict word anywhere on the v3 sheet, and none of CLOCS's own 'safest' / 'high-risk'",
   not _t3 or not VERDICT.search(_t3), str(VERDICT.findall(_t3)))
_cw = " ".join(a + " " + b for a, b in export.CLOCS_MAP) + export.CLOCS_NOTE + " ".join(" ".join(q) for q in export.ASSESSOR_QUESTIONS)
ok("7c: the CLOCS box and the questions: clause numbers with neutral words, never 'safe' (whole word) or 'high-risk'",
   not VERDICT.search(_cw) and not re.search(r"\bsafe\b|\bsafety\b", _cw, re.I) and len(export.ASSESSOR_QUESTIONS) == 10
   and len(export.CLOCS_MAP) == 8)
ok("7c: the lorry ink is its own: not a reserved colour, not a community kind's, not the collision ink",
   export.CE_LORRY.upper() not in RESERVED and export.CE_LORRY.upper() not in {k["colour"].upper() for k in community.KINDS}
   and export.CE_LORRY != export.CE_INK)
_wb3 = openpyxl.load_workbook(io.BytesIO(export.build_collision_evidence_xlsx(E3)))
_rc = _wb3["Routes compared"]
ok("7c: the XLSX: the routes compared (one column each), the lorries, the cycle routes and left turns",
   [c.value for c in _rc[1]] == ["What", "This route", "Alternative 1"] and _wb3["Lorries"].max_row == 2
   and _wb3["Cycle and left turns"].cell(row=2, column=1).value == "A cycle route meets the route", str([c.value for c in _rc[1]]))
db.execute("DELETE FROM community_features WHERE tenant_id = ? AND kind = 'cycle'", (T,))   # later sections as before


# --------------------------------------------------------------------------- #
#  7d. Evidence v3 part 2 (22 Oct 2026): compared with roads like these —      #
#      DfT's traffic counts × DfT's national rates (traffic.py; R5 reversed    #
#      for this one comparison, at the user's word)                            #
# --------------------------------------------------------------------------- #
import traffic  # noqa: E402
ok("7d: road_class: motorway; A or other, urban or rural by DfT's flag; nothing without the flag",
   traffic.road_class("M1", None) == "motorway" and traffic.road_class("A6", 2) == "rural_a" and traffic.road_class("A563", 1) == "urban_a"
   and traffic.road_class("B4114", 2) == "rural_other" and traffic.road_class("A6", None) is None and traffic.road_class(None, 1) is None)
ok("7d: urban_of: the majority of DfT's flags on the stretch; a tie or none says nothing",
   traffic.urban_of([{"detail": {"urban": 2}}, {"detail": {"urban": 2}}, {"detail": {"urban": 1}}]) == 2
   and traffic.urban_of([{"detail": {"urban": 2}}, {"detail": {"urban": 1}}]) is None and traffic.urban_of([{}]) is None)
ok("7d: poisson_range: the counts a typical road with 41.9 expected shows 95 times in 100 are 30-55 (the research's figure)",
   traffic.poisson_range(41.9) == (30, 55) and traffic.poisson_range(13.3) == (7, 21) and traffic.poisson_range(0) == (0, 0),
   str((traffic.poisson_range(41.9), traffic.poisson_range(13.3))))
ok("7d: reading: below / within / above the range — words, never a verdict",
   [traffic.reading(k, (30, 55)) for k in (29, 30, 55, 56)] == ["below the range", "within the range", "within the range", "above the range"])
ok("7d: the rates are RAS0302's 2021-2025 (rural A 2025 = 155.1, urban A FSC 2021 = 136.2)",
   traffic.RATES["rural_a"]["all"][2025] == 155.1 and traffic.RATES["urban_a"]["fsc"][2021] == 136.2
   and all(set(v["all"]) == set(range(2021, 2026)) for v in traffic.RATES.values()))
LA_CSV = '"local_authority_id","local_authority_name","local_authority_code","year","link_length_km"\n60,"Leicestershire","E10000018",2025,1\n153,"Leicester","E06000016",2025,1\n'
AADF_HEAD = ("count_point_id,year,road_name,road_type,latitude,longitude,link_length_km,estimation_method,pedal_cycles,"
             "all_hgvs,all_motor_vehicles")


def aadf_rows():
    out = [AADF_HEAD]
    for y in range(2019, 2026):
        lon, lat = P(200, 20)
        out.append(f"901,{y},A6,Major,{lat},{lon},3.0,{'Counted' if y == 2023 else 'Estimated'},50,400,10000")
        out.append(f"902,{y},A6,Major,52.0,-0.5,2.0,Estimated,0,0,99999")                 # far away
        out.append(f"903,{y},U,Minor,{lat},{lon},,Estimated,0,0,500")                     # a minor road's sample point
    return "\n".join(out) + "\n"


ok("7d: authority_ids: DfT's id for each ONS code the collisions name", traffic.authority_ids(write("la.csv", LA_CSV), {"E10000018"}) == {"E10000018": "60"})
_ar = traffic.read_aadf(write("aadf.csv", aadf_rows()), DIX, set(range(2021, 2026)))
ok("7d: read_aadf: the major-road count points near a route, for the years asked; not the far one, not a minor road's",
   sorted({r["count_point_id"] for r in _ar}) == ["901"] and sorted(r["year"] for r in _ar) == list(range(2021, 2026))
   and _ar[0]["link_km"] == 3.0 and _ar[0]["aadf_all"] == 10000.0, str(_ar[:1]))
_yrs = list(range(2021, 2026))
_exv = traffic.expected_for(DIX, ROUTE, 0.0, 3400.0, "A6", 2, _yrs, _ar)
_want = sum((10000 + 50) * 365 * (3400.0 / 1609.344) / 1e9 * traffic.RATES["rural_a"]["all"][y] for y in _yrs)
_want_f = sum((10000 + 50) * 365 * (3400.0 / 1609.344) / 1e9 * traffic.RATES["rural_a"]["fsc"][y] for y in _yrs)
ok("7d: expected_for: (AADF + pedal cycles) × 365 × the stretch's miles × each year's rate, summed; the range; what was used",
   abs(_exv["expected"] - _want) < 1e-9 and abs(_exv["expected_fsc"] - _want_f) < 1e-9 and _exv["range"] == traffic.poisson_range(_want)
   and _exv["class_words"] == "rural A roads" and _exv["counted"] == [2023] and _exv["points"] == ["901"] and _exv["aadf"] == (10000.0, 10000.0),
   str(_exv))
ok("7d: ...and says why not: another road's count, urban or rural not known, an unnumbered road, a year with no count",
   traffic.expected_for(DIX, ROUTE, 0, 3400, "A47", 2, _yrs, _ar) == {"why": "no traffic count on this road"}
   and traffic.expected_for(DIX, ROUTE, 0, 3400, "A6", None, _yrs, _ar) == {"why": "urban or rural not known"}
   and traffic.expected_for(DIX, ROUTE, 0, 3400, "Unclassified road", 2, _yrs, _ar) == {"why": "no numbered road"}
   and traffic.expected_for(DIX, ROUTE, 0, 3400, "A6", 2, _yrs + [2026], _ar)["why"].startswith("no traffic count or rate for 2026"))


def with_urban(table, y):
    text = only_2025(table, y)
    if table != "collision" or y != 2025:
        return text
    lines = text.strip().split("\n")
    return "\n".join([lines[0] + ",urban_or_rural_area,collision_adjusted_severity_serious"]
                     + [ln + ",2,0.5" for ln in lines[1:]]) + "\n"


def traffic_dl(url, dest):
    if "local_authority_traffic.csv" in url:
        text = LA_CSV
    elif "dft_aadf_local_authority_id_60" in url:
        text = aadf_rows()
    elif "data.dft.gov.uk" in url:
        return stub_download(with_urban)(url, dest)
    else:
        raise RuntimeError(f"could not download {url}: HTTP 404")
    with open(dest, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return url, len(text)


_st7 = cl.refresh(fetchers={"download": traffic_dl}, today=date(2026, 10, 16))
ok("7d: the fetch reads the traffic counts for the authorities the collisions name, beside the collisions",
   _st7["state"] == "done" and len(traffic.stored()) == 5 and "traffic counts E10000018" in " ".join(_st7["files"])
   and cl._detail(cl._meta_row()).get("traffic_points") == 1, str(_st7.get("files")))
E4 = cl.evidence("R1", now=date(2026, 10, 16))
_s4 = E4["stretches"][0]["expected"]
ok("7d: the stretch compared: expected, its range, where the observed sits; fatal or serious on DfT's adjusted basis",
   "expected" in _s4 and _s4["class"] == "rural_a" and _s4["reading"] in ("below the range", "within the range", "above the range")
   and _s4["fsc_basis"] == "adjusted" and abs(_s4["obs_fsc"] - (0 + 0.5 * 3)) < 1e-9, str(_s4))
ok("7d: the headline gives the whole route's expected when every stretch has one; the alternatives none",
   E4["headline"][0]["expected"]["covers"] == "all" and abs(E4["headline"][0]["expected"]["expected"] - _s4["expected"]) < 1e-9
   and E4["headline"][1].get("expected") is None and export._exp_cell(E4["headline"][1]) == "—")
_t4 = " ".join(pdf_text(export.build_collision_evidence_pdf(E4), "").split()) if shutil.which("pdftotext") else ""
ok("7d: the PDF: Compared with roads like these, the road type, the range, the yardstick's caveats and the credit",
   not _t4 or ("Compared with roads like these" in _t4 and "rural A roads" in _t4 and "(typical range)" in _t4
               and "RAS0302" in _t4 and "Small numbers" in _t4 and "DfT road traffic statistics" in _t4
               and "Expected for roads like these" in _t4), _t4[:3000])
ok("7d: ...never a ratio, a score or a verdict on the road", not _t4 or (not VERDICT.search(_t4)
   and not re.search(r"\b(O/E|ratio|times the (national )?average|safer|worse than)\b", _t4, re.I)), str(VERDICT.findall(_t4)))
_wb4 = openpyxl.load_workbook(io.BytesIO(export.build_collision_evidence_xlsx(E4)))
_ce = _wb4["Compared with roads like these"]
_ch = [c.value for c in _ce[1]]
ok("7d: the XLSX: one row a stretch, the expected and its range as numbers, the count points used",
   _ce.cell(row=2, column=_ch.index("Expected") + 1).value == round(_s4["expected"], 1)
   and _ce.cell(row=2, column=_ch.index("DfT count points") + 1).value == "901", str(_ch))
ok("7d: a sheet with no traffic counts says so in one line (no empty table, no rate words)",
   not _t or ("Compared with roads like these: DfT's traffic counts have not been fetched yet" in _t))
cl.refresh(fetchers={"download": stub_download(only_2025)}, today=date(2026, 10, 16))     # the fixture as before
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
# 28 Oct 2026 (claude/overlays-after-switch): the idle wait is gone — the gate is styleReady() (the style document parsed);
# the pin is NARROWED to that gate, same order (the tick on an existing layer comes before the gate, and never waits).
ok("10: map — a tick on an existing layer goes straight on, before the style-ready gate (no idle wait anywhere since 28 Oct 2026)",
   _ecl.index("if (map.getLayer('collision-points')) {") < _ecl.index("if (!styleReady()) return;")
   and "map.setFilter('collision-points', collisionFilter());" in _ecl.split("if (!styleReady())")[0]
   and "once('idle'" not in _ecl and "isStyleLoaded" not in _ecl.split("if (!styleReady())")[1])
ok("10: map — the group's words count the alternatives' apart and say how to see them",
   "are along the alternative routes only: " in MAP and "tick Alternative routes to see them." in MAP)
ok("10: app — the Config panel counts them apart too",
   " are near alternative routes only.`" in APP and "stored alternative routes" not in APP)   # NARROWED 22 Oct 2026 (words sweep; the user: few words on screens): shorter
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
   "Evidence, not the assessment." in _cp and "Staff only." in _cp and "Fetch again after changing routes, and each August." in _cp   # NARROWED 27 Oct 2026 (the final UI pass): fewer words   # NARROWED 22 Oct 2026 (words sweep; the user: few words on screens): the panel is three short sentences; where it never shows is in the guide and T9
   and "never on the public map or the bulletin" in read("frontend/help/index.html"))
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
   and tenant_package.ORDER[-3:-1] == ["collision_records", "collision_meta"]     # NARROWED 22 Oct 2026: traffic_counts last
   and '"collision_records", "collision_meta",' in read("backend/tests/test_tenant_audit.py"))
GUIDE, TECH = read("frontend/help/index.html"), read("frontend/help/technical/index.html")
_g = GUIDE.split("<li><strong>Collision history</strong>")[1].split("</li>")[0] if "<li><strong>Collision history</strong>" in GUIDE else ""
ok("10: the user guide says what it is, who sees it, where it comes from, what it cannot tell you, and that it is not the assessment",
   _g and "staff only" in _g and "the government&rsquo;s road safety figures" in _g and "STATS19" not in _g and "250 m" in _g and "not the assessment" in _g   # NARROWED 28 Oct 2026 (the user: no data-set names in the user guide): STATS19 is named in technical #t1-guide-sources
   and "safety data (STATS19), released each late July" in TECH
   and "police" in _g and "2016" in _g and "never the day or time" in _g and "Collision evidence (PDF)" in _g)
ok("10: v2 (22 Oct 2026): the user guide describes the stretches, the strip, the lorries beside (never a rate), the fold "
   "and the appendix's Nearby rule; the technical guide the rules behind them",
   "<em>stretch by stretch</em>" in _g and "never divided into a rate" in _g   # NARROWED 22 Oct 2026 (words sweep; the user: few words in the user guide): the fold, the Nearby rule and the sheet are in T9
   and "folded into a sentence" in TECH and "100 m" in TECH and "<em>Stretches sheet</em>" in TECH
   and "The evidence sheet, v2 (22 Oct 2026)." in TECH and "<code>vru_goods</code>" in TECH and "<code>PDF_NEARBY_M</code>" in TECH
   and "keep the year and month only (R6)" in TECH)
ok("10: v3 (22 Oct 2026): the user guide describes the routes compared, the CLOCS box, the lorries, the cycle routes, the "
   "left turns and the assessor's page; the technical guide the fields and the measures",
   "the route beside its alternatives" in _g and "not a CLOCS form" in _g   # NARROWED 22 Oct 2026 (words sweep; the user: few words in the user guide): the squares and the next-fetch rule are in T9
   and "violet squares" in TECH and "read from the next Fetch now" in TECH and "The evidence sheet, v3 (22 Oct 2026)." in TECH and "<code>detail_json</code>" in TECH
   and "<code>DETAIL_ROWS</code>" in TECH and "45&deg;" in TECH)
ok("10: v3 part 2: the guides say how 'compared with roads like these' is worked out, that it is a range never a score, "
   "and its caveats",
   "<em>Compared with roads like these</em>" in _g and "never a score" in _g and "city-centre roads" in TECH   # NARROWED 22 Oct 2026 (words sweep; the user: few words in the user guide): the caveat is in T9
   and "<code>traffic.py</code>" in TECH and "<code>traffic.RATES</code>" in TECH and "never a ratio" in TECH
   and "dft_aadf_local_authority_id_" in TECH)
ok("10: the guides say the alternatives' collisions show with Alternative routes and the plans leave them out",
   "those near an alternative route only appear while <em>Alternative routes</em>" in _g   # NARROWED 22 Oct 2026 (words sweep; the user: few words in the user guide): "stored" left; the plans rule is in T9
   and "the route map plans leave them out" in TECH
   and "<code>alternatives_only</code>" in TECH)
ok("10: the technical guide: the endpoints, the files, the years rule, the codes, the licence",
   'id="t9-collisions"' in TECH and "/api/collisions" in TECH and "data.dft.gov.uk" in TECH and "late July" in TECH
   and "casualty_class" in TECH and "Open Government Licence v3.0" in TECH)

# --------------------------------------------------------------------------- #
#  11. The abnormal loads' lines (23 Oct 2026; the user: "yes the strip should  #
#      include the abnormal lines")                                            #
# --------------------------------------------------------------------------- #
# a load drawn 2 km south of R1 (both legs), one withdrawn load drawn 3 km south, one load not drawn yet
ABN = [[-0.95, LAT0 - 2000 * DLAT], [-0.925, LAT0 - 2000 * DLAT], [-0.90, LAT0 - 2000 * DLAT]]
ABN_GONE = [[-0.95, LAT0 - 3000 * DLAT], [-0.90, LAT0 - 3000 * DLAT]]
for _id, _st, _g in (("AL1", "approved", ABN), ("AL2", "withdrawn", ABN_GONE), ("AL3", "pending", None)):
    db.execute("INSERT INTO abnormal_loads (tenant_id, id, name, ipt, status, geometry_json, return_geometry_json) "
               "VALUES (?, ?, ?, ?, ?, ?, ?)",
               (T, _id, "Load " + _id, "IPT1", _st, json.dumps(_g) if _g else None, json.dumps(list(reversed(_g))) if _g else None))
AIX = cl.index_from_db()
ok("⭐ 11: index_from_db takes in the drawn load's line under its id (both legs, kept once), never a withdrawn load's nor a load "
   "not drawn yet; the routes and sites as before",
   {k for k, _ in AIX.lines} == {"R1", "R1@1", "AL1"} and sum(1 for k, _ in AIX.lines if k == "AL1") == 2
   and len(AIX.sites) == 2 and AIX.in_box(mid, LAT0 - 2000 * DLAT), str([k for k, _ in AIX.lines]))
ok("11: a point on the load's line is near AL1 only (not R1, not a site), and 'along' calls it a route (no '@' in the key)",
   (lambda rs: list(rs[0].keys()) == ["AL1"] and rs[0]["AL1"] < 25 and not rs[1])(AIX.near(*P(0, -1990)))
   and cl.along({"routes": {"AL1": 3.0}, "sites": {}}) == "route")


def with_abn(table, y):
    """The 2025 rows plus C9, 10 m from the load's line and about 2 km from R1, its alternative and both sites."""
    text = only_2025(table, y)
    if table == "collision" and y == 2025:
        lon, lat = P(0, -1990)
        text += f"{y}C9,{y},C9,0,0,{lon},{lat},33,2,2,1,05/05/{y},3,08:15,E10000018,3,6,6,30,0,-1,0,1\n"
    return text


CALLS.clear()
sta = cl.refresh(fetchers={"download": stub_download(with_abn)}, today=date(2026, 10, 16))
ok("⭐ 11: a fetch stores the collision on the load's line and counts it with the routes': 6 along the routes and round the "
   "sites (was 5), 4 KSI (C9 is serious), the one near the alternative only still apart",
   sta["state"] == "done" and sta["counts"] == {"all": 6, "ksi": 4, "vru": 5} and sta["alternatives_only"] == {"all": 1, "ksi": 1},
   str((sta.get("counts"), sta.get("alternatives_only"))))
_c9 = [f for f in cl.payload()["features"] if "AL1" in f["properties"]["routes"]]
_lon9, _lat9 = P(0, -1990)
ok("11: the payload carries it near AL1 ONLY (R1's own evidence, which reads a collision's routes, is untouched: 2 km "
   "away), along = route, so the staff map draws it with the routes' and not only with Alternative routes",
   len(_c9) == 1 and _c9[0]["properties"]["routes"] == ["AL1"] and _c9[0]["properties"]["along"] == "route"
   and abs(_c9[0]["geometry"]["coordinates"][0] - _lon9) < 1e-6 and abs(_c9[0]["geometry"]["coordinates"][1] - _lat9) < 1e-6
   and _c9[0]["properties"]["dist_m"] <= 25,
   str(_c9)[:300])
db.execute("UPDATE abnormal_loads SET status = 'withdrawn' WHERE tenant_id = ? AND id = 'AL1'", (T,))
stb = cl.refresh(fetchers={"download": stub_download(with_abn)}, today=date(2026, 10, 16))
ok("11: once the load is withdrawn its line leaves the strip: the next fetch drops C9 (back to 5 / 3)",
   stb["counts"] == {"all": 5, "ksi": 3, "vru": 5} and not any("AL1" in f["properties"]["routes"] for f in cl.payload()["features"]),
   str(stb.get("counts")))
db.execute("DELETE FROM abnormal_loads WHERE tenant_id = ? AND id IN ('AL1', 'AL2', 'AL3')", (T,))
cl.refresh(fetchers={"download": stub_download(only_2025)}, today=date(2026, 10, 16))
_ix = read("frontend/index.html")
ok("11: the words: the Config card says the abnormal loads' routes are in the strip; so do both guides",
   "m of a route, the abnormal loads' too, and " in _ix
   and "within 250 m of every route (the abnormal loads&rsquo; routes too) and 500 m of every site" in read("frontend/help/index.html")
   and "each abnormal load&rsquo;s drawn line under the load&rsquo;s id" in read("frontend/help/technical/index.html"))
ok("11: collisions.index_from_db reads the abnormal loads' lines the way community.strip_from_db does (both legs, not withdrawn)",
   "FROM abnormal_loads WHERE tenant_id = ? \"\n                      \"AND status != 'withdrawn'" in read("backend/collisions.py")
   and read("backend/collisions.py").count('"return_geometry_json"') >= 1)

# --------------------------------------------------------------------------- #
#  12. By time of day (28 Oct 2026, task 0d; John's yes to                     #
#      notes\collision-time-mockup-1028, every question as recommended)       #
# --------------------------------------------------------------------------- #
ok("12: a fetch records that the hours are in (status 'hours')", cl.status()["hours"] is True)
ok("12: the busy bands are fixed before any route is looked at: weekdays 07:00–10:00 and 16:00–19:00; 10 and 1 in 20",
   cl.BUSY_BANDS == [("07:00", "10:00"), ("16:00", "19:00")] and cl.MIDDAY == ("10:00", "16:00")
   and cl.OFFER_MIN == 10 and cl.OFFER_P == 0.05)
ok("12: the exact test on two counts (R001 on live, 28 Oct: 17 vs 5 -> 0.008; 27 vs 15 -> 0.044; 33 vs 26 -> 0.22)",
   abs(cl.chance_of_fewer(17, 5) - 0.0085) < 0.001 and abs(cl.chance_of_fewer(27, 15) - 0.0442) < 0.001
   and abs(cl.chance_of_fewer(33, 26) - 0.217) < 0.002 and cl.chance_of_fewer(0, 0) == 1.0
   and cl.chance_of_fewer(10, 10) > 0.5)
_r001 = [2, 0, 0, 0, 0, 4, 7, 9, 5, 3, 6, 3, 3, 9, 5, 7, 11, 7, 9, 12, 4, 7, 2, 3]
_a001 = [0, 0, 0, 0, 0, 1, 1, 1, 3, 1, 4, 3, 4, 2, 9, 4, 4, 10, 1, 3, 2, 3, 3, 3]


def _hc(wk):
    return {"weekday": wk, "weekend": 0, "unknown": 0}


_off = cl.busy_offers([("This route", 0, _hc(_r001)), ("Alternative 1", 1, _hc(_a001))])
ok("12: R001's live hours: Alternative 1 offered in both busy bands (17 vs 5, 27 vs 15), the middle of the day beside them",
   len(_off) == 1 and _off[0]["alt"] == 1 and [(b["from"], b["route"], b["alt"]) for b in _off[0]["bands"]]
   == [("07:00", 17, 5), ("16:00", 27, 15)] and (_off[0]["midday"]["route"], _off[0]["midday"]["alt"]) == (33, 26), str(_off))
_r014 = [0] * 24
_r014[7], _r014[16], _r014[17] = 3, 6, 5
_a014 = [0] * 24
_a014[7], _a014[16], _a014[17] = 4, 6, 5
ok("12: no offer when the counts are about the same (R014: 11 vs 11) or the route had fewer than 10 in the band; 10 vs 0 is",
   cl.busy_offers([("This route", 0, _hc(_r014)), ("Alternative 1", 1, _hc(_a014))]) == []
   and cl.busy_offers([("This route", 0, _hc([0] * 7 + [9] + [0] * 16)), ("Alternative 1", 1, _hc([0] * 24))]) == []
   and cl.busy_offers([("This route", 0, _hc([0] * 7 + [10] + [0] * 16)),
                       ("Alternative 1", 1, _hc([0] * 24))])[0]["bands"][0]["route"] == 10)
ok("12: an alternative is never offered against itself, nor a route without alternatives",
   cl.busy_offers([("This route", 0, _hc(_r001))]) == [] and cl.busy_offers([]) == [])
_w = cl.offer_words(_off[0], "2021–2025")
ok("12: the words: counts against counts with the years; no rate, no verdict",
   _w == "Alternative 1 had fewer in the busy hours: 5 against 17 (07:00–10:00) and 15 against 27 (16:00–19:00), weekdays "
   "2021–2025. Between 10:00 and 16:00: 26 against 33."
   and cl.offer_words(_off[0], "2021–2025", short=True).startswith(
       "Alternative 1 had fewer collisions on it in the busy hours: 5 against 17")
   and not VERDICT.search(_w) and "%" not in _w and "per " not in _w, _w)
_hcs = cl.hour_counts([{"detail": {"hour": 8, "weekday": True}}, {"detail": {"hour": 8, "weekday": True}},
                       {"detail": {"hour": 22, "weekday": False}}, {"detail": {"hour": None, "weekday": True}}, {"detail": {}}])
ok("12: hour_counts: weekdays by hour, the weekend as one total, no hour or no day counted apart",
   _hcs["weekday"][8] == 2 and sum(_hcs["weekday"]) == 2 and _hcs["weekend"] == 1 and _hcs["unknown"] == 2)
ok("12: has_hours is False while any record was fetched before the hours (no 'hour' key)",
   cl.has_hours([{"detail": {"hour": 3}}, {"detail": {"hour": None}}]) and not cl.has_hours([{"detail": {"hour": 3}}, {"detail": {}}]))
E12 = cl.evidence("R1", now=date(2026, 10, 16))
T12 = E12["time_of_day"]
ok("12: the evidence: on R1 C2 (Wed 17:40) and C8 (Tue 23:05) on weekdays, C1 (Sat) at the weekend; the alternative none",
   T12["shown"] and T12["columns"][0]["weekday"][17] == 1 and T12["columns"][0]["weekday"][23] == 1
   and sum(T12["columns"][0]["weekday"]) == 2 and T12["columns"][0]["weekend"] == 1
   and [c_["label"] for c_ in T12["columns"]] == ["This route", "Alternative 1"] and sum(T12["columns"][1]["weekday"]) == 0,
   str(T12["columns"])[:300])
ok("12: ...the busy bands on page 1's table (0 in the morning, 1 in the evening), no offer on counts this small",
   E12["headline"][0]["busy"] == [0, 1] and E12["headline"][1]["busy"] == [0, 0] and T12["offers"] == [],
   str((E12["headline"][0].get("busy"), T12["offers"])))
ok("12: ...the route's gates' hours (none typed here: the default gate hours) and the scheme's no-delivery bands (none)",
   T12["gates"] == {"from": "08:00", "to": "17:00"} and T12["no_delivery"] == [], str((T12["gates"], T12["no_delivery"])))
_hr = export.collision_headline_rows(E12)
ok("12: page 1's table gains '…on weekdays 07:00–10:00' and '…on weekdays 16:00–19:00' after the KSI row",
   [r_[0] for r_ in _hr][2:5] == ["…killed or seriously injured (KSI)", "…on weekdays 07:00–10:00", "…on weekdays 16:00–19:00"]
   and _hr[4][1:] == ["1", "0"], str([r_[0] for r_ in _hr]))
_pdf12 = export.build_collision_evidence_pdf(E12)
_t12 = " ".join(pdf_text(_pdf12, "").split()) if shutil.which("pdftotext") else ""
ok("12: the PDF: the 'By time of day' block, the weekends, the rule, 'Nothing is switched', no alternative clearly fewer",
   not _t12 or ("By time of day" in _t12 and "Weekday collisions on the route by the hour they happened" in _t12
                and "Weekends: 1 on this route; 0 on Alternative 1." in _t12 and "Nothing is switched" in _t12
                and "No alternative had clearly fewer in the busy hours." in _t12 and "on weekdays 16:00–19:00" in _t12
                and "shaded: the route's gates open (08:00–17:00)" in _t12), _t12[:300])
ok("12: no verdict word on the sheet with the block in", not _t12 or not VERDICT.search(_t12), str(VERDICT.findall(_t12)))
_wb12 = openpyxl.load_workbook(io.BytesIO(export.build_collision_evidence_xlsx(E12)))
_wh = _wb12["By time of day"]
ok("12: the XLSX sheet: 24 hour rows, the bands in order, the weekends; one column per road route",
   [_wh.cell(row=3, column=j).value for j in (1, 2, 3)] == ["Hour", "This route, weekdays", "Alternative 1, weekdays"]
   and _wh.cell(row=21, column=1).value == "17:00–18:00" and _wh.cell(row=21, column=2).value == 1
   and _wh.cell(row=27, column=1).value == "23:00–24:00" and _wh.cell(row=27, column=2).value == 1
   and [_wh.cell(row=r_, column=1).value for r_ in (28, 29, 30, 31)]
   == ["Weekdays 07:00–10:00", "Weekdays 10:00–16:00", "Weekdays 16:00–19:00", "Weekends, all hours"]
   and [_wh.cell(row=r_, column=2).value for r_ in (28, 29, 30, 31)] == [0, 0, 1, 1],
   str([[_wh.cell(row=r_, column=j).value for j in (1, 2, 3)] for r_ in range(1, 34)]))
_hdr12 = [c_.value for c_ in _wb12["Collisions"][1]]
ok("12: R6 at the record level: no sheet lists one collision's hour (the Collisions sheet has no hour, day or time column)",
   not any(h and re.search(r"\b(date|day|time|hour)\b", h, re.I) for h in _hdr12) and "Month" in _hdr12, str(_hdr12))
ok("12: ...nor the map's payload (a feature carries the month only)",
   all("hour" not in f["properties"] and "weekday" not in f["properties"] and "detail" not in f["properties"]
       for f in cl.payload()["features"]))
# a record fetched before 28 Oct (no 'hour' in its details): the evidence says the hours come with the next fetch
_old_rows = db.query("SELECT collision_id, detail_json FROM collision_records WHERE tenant_id = ?", (T,))
db.execute("UPDATE collision_records SET detail_json = ? WHERE tenant_id = ? AND collision_id = ?",
           (json.dumps({"urban": 1}), T, _old_rows[0]["collision_id"]))
E12b = cl.evidence("R1", now=date(2026, 10, 16))
_t12b = " ".join(pdf_text(export.build_collision_evidence_pdf(E12b), "").split()) if shutil.which("pdftotext") else ""
ok("12: fetched before the hours: no busy rows, no chart, the sheet says the hours come with the next fetch",
   E12b["time_of_day"]["shown"] is False and E12b["headline"][0]["busy"] is None
   and not any(r_[0].startswith("…on weekdays") for r_ in export.collision_headline_rows(E12b))
   and (not _t12b or "The hour of each collision comes with the next fetch" in _t12b)
   and openpyxl.load_workbook(io.BytesIO(export.build_collision_evidence_xlsx(E12b)))["By time of day"].cell(row=1, column=1).value
   .startswith("The hour of each collision comes with the next fetch"))
for r_ in _old_rows:
    db.execute("UPDATE collision_records SET detail_json = ? WHERE tenant_id = ? AND collision_id = ?",
               (r_["detail_json"], T, r_["collision_id"]))
_off2 = [dict(_off[0], words=_w, extra="6.2 mi longer each way")]
E12c = dict(E12, time_of_day=dict(T12, offers=_off2))
_t12c = " ".join(pdf_text(export.build_collision_evidence_pdf(E12c), "").split()) if shutil.which("pdftotext") else ""
ok("12: with an offer, the PDF prints its sentence and the extra length, and no 'clearly fewer' denial",
   not _t12c or ("Alternative 1 had fewer in the busy hours: 5 against 17 (07:00–10:00)" in _t12c
                 and "Alternative 1 is 6.2 mi longer each way." in _t12c and "No alternative had clearly fewer" not in _t12c),
   _t12c[-900:])
_ug, _tg = read("frontend/help/index.html"), read("frontend/help/technical/index.html")
_ug_ct = _ug[_ug.index("<em>By time of day</em>"):_ug.index("<em>By time of day</em>") + 400] if "<em>By time of day</em>" in _ug else ""
ok("12: the user guide: By time of day in a few words (the busy hours, the Routes line, nothing is switched), no method or API",
   "07:00&ndash;10:00 and 16:00&ndash;19:00" in _ug_ct and "nothing is switched" in _ug_ct and "under the route&rsquo;s options" in _ug_ct
   and not re.search(r"Binomial|exact test|/api/|detail_json|OFFER_", _ug_ct), _ug_ct[:200])
ok("12: the technical guide T9 holds the method: the fields read, the bands, 10 and 0.05, the test, the endpoint, offered only",
   'id="t9-time-of-day"' in _tg and "<code>OFFER_MIN</code> = 10" in _tg and "<code>OFFER_P</code> = 0.05" in _tg
   and "Binomial(route + alternative, &frac12;)" in _tg and "/api/routes/{id}/collision-hours" in _tg
   and "Offered, never applied" in _tg and _tg.index('id="t9-time-of-day"') < _tg.index('id="t10-public-map"'))
# 28 Oct 2026 (found on live after PR #160: the evidence answered 500) — location_gates.active is BOOLEAN on Postgres and an
# integer in SQLite, so "active = 1" in SQL broke the sheet on live only. No backend query compares `active` in SQL now.
_active_sql = []
for _f in sorted(os.listdir(BACKEND)):
    if _f.endswith(".py"):
        for _n in ast.walk(ast.parse(read("backend/" + _f))):
            if isinstance(_n, ast.Constant) and isinstance(_n.value, str) and re.search(r"\bactive\s*(=|!=|<>)\s*(1|0|TRUE|FALSE)\b", _n.value, re.I) \
                    and re.search(r"\b(SELECT|UPDATE|DELETE|WHERE)\b", _n.value):
                _active_sql.append(f"{_f}: {_n.value[:80]}")
ok("12: no backend SQL compares `active` with a number or TRUE / FALSE (BOOLEAN on Postgres, an integer in SQLite)",
   not _active_sql, str(_active_sql))
db.execute("INSERT INTO location_gates (tenant_id, id, location_id, name, direction, lat, lon, active, open_from, open_to) "
           "VALUES (?, 'GA1', 'LA', 'In', 'access', ?, ?, ?, '06:00', '18:00')", (T, LAT0, -0.95, True))
db.execute("INSERT INTO location_gates (tenant_id, id, location_id, name, direction, lat, lon, active, open_from, open_to) "
           "VALUES (?, 'GA2', 'LA', 'Old', 'access', ?, ?, ?, '00:00', '23:00')", (T, LAT0, -0.95, False))
ok("12: gate_span: the route's gates' hours, a stopped gate left out (Python decides, not SQL)",
   cl.gate_span({"origin_id": "LA", "dest_id": "LB"}) == (360, 1080), str(cl.gate_span({"origin_id": "LA", "dest_id": "LB"})))
db.execute("DELETE FROM location_gates WHERE tenant_id = ? AND id IN ('GA1', 'GA2')", (T,))
# a route with no collision near it, after a fetch that stored the hours: "none", never "the hours come with the next fetch"
E12d = cl.evidence("R2", now=date(2026, 10, 16))
_t12d = " ".join(pdf_text(export.build_collision_evidence_pdf(E12d), "").split()) if shutil.which("pdftotext") else ""
ok("12: a route with no collisions near it: the hours are shown as none (0 in the busy rows), the sheet says so, the Routes "
   "line has nothing to offer",
   E12d["time_of_day"]["shown"] is True and E12d["headline"][0]["busy"] == [0, 0]
   and cl.busy_hours("R2") == {"shown": True, "offers": [], "period": "2021–2025"}
   and (not _t12d or ("No collisions on this route (within 25 m), 2021–2025." in _t12d
                      and "comes with the next fetch" not in _t12d)), _t12d[-600:])
# 28 Oct 2026 (found on live after #160: a route re-routed after the fetch gained an "Alt 2" with 0 collisions on it — its road
# had never been searched — and was offered as "0 against 48"). The fetch records the roads it searched; only those are offered.
ok("12: the fetch records the road routes it searched along (the route and its alternative here)",
   cl.searched_keys() == {"R1", "R1@1"}, str(cl.searched_keys()))
_cols3 = [("This route", 0, _hc(_r001)), ("Alternative 1", 1, _hc(_a001)), ("Alternative 2", 2, _hc([0] * 24))]
ok("12: an alternative drawn after the fetch (R1@2, never searched) is left out of the comparison; the route is always kept",
   [c[1] for c in cl._searched_only("R1", _cols3)] == [0, 1]
   and [o["alt"] for o in cl.busy_offers(cl._searched_only("R1", _cols3))] == [1]
   and [o["alt"] for o in cl.busy_offers(_cols3)] == [1, 2])
_det12 = cl._detail(cl._meta_row())
cl._write_meta("done", {k: v for k, v in _det12.items() if k != "searched"})
ok("12: ...a fetch made before this rule (no list stored) leaves every column in, as before",
   cl.searched_keys() is None and [c[1] for c in cl._searched_only("R1", _cols3)] == [0, 1, 2])
cl._write_meta("done", _det12)
_mid = []


def _peek_dl(url, dest):
    _mid.append(cl.status()["hours"])
    return stub_download(only_2025)(url, dest)


cl.refresh(fetchers={"download": _peek_dl}, today=date(2026, 10, 16))
ok("12: while a fetch runs the status still says the stored rows carry their hours (it read False mid-fetch on live)",
   _mid and all(h is True for h in _mid) and cl.status()["hours"] is True, str(_mid[:3]))
# 29 Oct 2026 (found on live after U8c: R017's busy-hour offer was "Alt 10" — task 0c's way round a closed zone, not one of
# HERE's alternatives). A way round is never offered for the busy hours and is named "Way round" wherever a column is labelled.
import route_choice  # noqa: E402
_W = route_choice.WAY_ROUND_BASE
ok("12: column labels: this route, Alternative n (short Alt n), Way round (a second: Way round 2)",
   [cl.column_label(a) for a in (0, 1, 2, _W, _W + 1)] == ["This route", "Alternative 1", "Alternative 2", "Way round", "Way round 2"]
   and cl.column_label(2, short=True) == "Alt 2" and cl.column_label(_W, short=True) == "Way round")
_cols4 = [("This route", 0, _hc(_r001)), ("Alternative 1", 1, _hc(_a001)), ("Way round", _W, _hc([0] * 24))]
_det_w = cl._detail(cl._meta_row())
cl._write_meta("done", dict(_det_w, searched=sorted(set(_det_w.get("searched") or []) | {f"R1@{_W}"})))
ok("12: a way round is left out of the busy-hour comparison even when the fetch searched along it",
   [c[1] for c in cl._searched_only("R1", _cols4)] == [0, 1] and [o["alt"] for o in cl.busy_offers(cl._searched_only("R1", _cols4))] == [1])
cl._write_meta("done", {k: v for k, v in _det_w.items() if k != "searched"})
ok("12: ...and with no searched list (an older fetch) too", [c[1] for c in cl._searched_only("R1", _cols4)] == [0, 1])
cl._write_meta("done", _det_w)
network._upsert_geom("R1", PROF, json.dumps(ALT), 3.7, 0.1, None, leg="loaded", alt_index=_W)
E12w = cl.evidence("R1", now=date(2026, 10, 16))
ok("12: the evidence names the way round 'Way round', never 'Alternative 10' (the table, the hours, the routes compared)",
   [c["label"] for c in E12w["columns"]] == ["This route", "Alternative 1", "Way round"]
   and [c["label"] for c in E12w["time_of_day"]["columns"]] == ["This route", "Alternative 1", "Way round"]
   and [h["label"] for h in E12w["headline"]] == ["This route", "Alternative 1", "Way round"]
   and all(o["alt"] < _W for o in E12w["time_of_day"]["offers"]), str([c["label"] for c in E12w["columns"]]))
_x12w = openpyxl.load_workbook(io.BytesIO(export.build_collision_evidence_xlsx(E12w)))["By time of day"]
ok("12: ...the XLSX's By time of day header too", _x12w.cell(row=3, column=4).value == "Way round, weekdays",
   str([_x12w.cell(row=3, column=j).value for j in (1, 2, 3, 4)]))
db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = 'R1' AND alt_index = ?", (T, _W))
ok("12: the offer is never applied: collisions.py writes nothing to routes, route_geometry or route_choice",
   not re.search(r"(UPDATE|INSERT INTO|DELETE FROM)\s+(routes|route_geometry|route_choice)\b", read("backend/collisions.py")))

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)

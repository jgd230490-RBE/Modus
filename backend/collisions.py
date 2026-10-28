"""
collisions.py — COLLISION HISTORY along the routes (CLOCS v5 C1, 16 Oct 2026; notes/route-risk-research-1016.md).

WHY
---
CLOCS Standard v5 asks the client (4.1a) and the principal contractor (5.1a) to consider "high-risk roads, junctions
and routes using historical crash data", and the principal contractor to "assess and select the safest routes"
considering "the potential for conflict with vulnerable road users" (5.6a). A delivery management system holds none of
that. This module keeps, per tenant, the police-reported injury collisions (DfT road safety open data, STATS19) that lie
along the tenant's routes, fetched ONCE by a staff action (start_refresh) and never on a page view. It is EVIDENCE for a
person's route risk assessment, never a verdict: counts with their period, no score, no rate, no ranking, no colour
status (the user's decisions R1-R10, 16 Oct 2026, all as recommended).

THE DATA (checked live 16 Oct 2026)
-----------------------------------
GOV.UK "Road safety open data", Open Government Licence v3.0. Three CSV tables a year (collision, vehicle, casualty)
joined on collision_index, Great Britain only. Final data comes out in late July for the year before; this module reads
the latest FIVE final years (R1), whole, at every refresh (DfT occasionally corrects earlier years). The server ignores
Range requests and refuses HEAD, so each file is downloaded whole (~19-21 MB a table a year), read, and deleted before
the next.

THE STRIP (R2)
--------------
The community layer's: 250 m each side of every stored road route (both legs, every vehicle) and 500 m round every
site. Stored alternatives (alt_index 1-2) are in it too, so a route's alternatives can be set side by side. Since
23 Oct 2026 (the user: the strip should include the abnormal lines) each abnormal load's own drawn line is in it as
well, under the load's id (both legs; a withdrawn load's is left out), so the load's road has its own evidence and
the counts and the staff map take it in like a route (its key carries no '@', so it is never 'alternative'). Every kept
collision carries its distance to each route it is near; "on the route" is within ON_ROUTE_M (25 m: the 2025 data
flattens after 20 m, and 25 m allows for a dual carriageway).

WHO SEES IT (R6)
----------------
Staff only. The public map and the bulletin never show it. A collision is stored with its year and month, never its day
or time. 28 Oct 2026 (task 0d, John's yes to notes/collision-time-mockup-1028): its HOUR (0-23) and whether it fell Monday
to Friday are kept too, in detail_json, for counts by time of day only — no screen, popup or sheet prints one collision's
hour, and the date and the minute are still never stored.

BUSY HOURS (0d)
---------------
The evidence counts each route's and alternative's collisions ON the route on weekdays by hour, and in the two busy bands
(BUSY_BANDS, chosen before looking at any route). An alternative is OFFERED for a band only when the route had at least
OFFER_MIN there in the five years and an exact test on the two counts says a gap this big comes by chance less than
OFFER_P of the time (busy_offers). Offered only: nothing is switched; applying it waits for task 0c's route_choice.
"""
import csv
import json
import math
import os
import shutil
import tempfile
import threading
from datetime import datetime, date, timedelta, timezone

import db

ON_ROUTE_M = 25
NEAR_ROUTE_M = 250          # = community.STRIP_ROUTE_M (asserted)
NEAR_SITE_M = 500           # = community.STRIP_SITE_M (asserted)
CLUSTER_M = 50              # R4: two or more collisions within this of each other are one location
YEARS = 5                   # R1
FINAL_MONTH = 8             # final data for year Y is out by August of Y+1 ("late July"); before that, Y-1 is the latest

URL = "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-{table}-{year}.csv"
PAGE = "https://www.gov.uk/government/statistical-data-sets/road-safety-open-data"
SOURCE = {"name": "DfT road safety data (STATS19)", "licence": "OGL v3.0", "url": PAGE,
          "attribution": "Contains public sector information licensed under the Open Government Licence v3.0 "
                         "(DfT road safety data)"}

# the words every output uses (R10; the wording rules in the research note §5)
LAYER_NAME = "Collision history"
SHEET_NAME = "Route collision evidence"
WHAT = "Police-reported injury collisions"
CAVEAT = ("Police-reported injury collisions on public roads (DfT STATS19), final data. There is no legal duty to report "
          "every injury collision to the police and many non-fatal ones are never recorded; since 2016 many forces "
          "changed how they record severity, which affects serious and slight counts over time. Each collision is "
          "counted once for every route it is near.")
NOT_A_VERDICT = "This is evidence for a route risk assessment. It is not the assessment."

SEVERITY = {1: "Fatal", 2: "Serious", 3: "Slight"}

# R3: the CLOCS v5 vulnerable road users (§2.7), as STATS19 casualty_type codes (the 2025 data guide). casualty_class 3
# is a pedestrian too. Code 23 is the electric motorcycle (the guide also prints 23 for the powered transporter; the
# 2025 file uses 33 for that, so 33 it is).
VRU = [
    {"key": "pedestrian", "label": "Pedestrian", "types": {"0"}},
    {"key": "cyclist", "label": "Cyclist", "types": {"1"}},
    {"key": "motorcyclist", "label": "Motorcyclist", "types": {"2", "3", "4", "5", "23", "97"}},
    {"key": "horse_rider", "label": "Horse rider", "types": {"16"}},
    {"key": "escooter", "label": "E-scooter or powered transporter user", "types": {"33"}},
    {"key": "mobility", "label": "Mobility scooter user", "types": {"22"}},
]
VRU_KEYS = [v["key"] for v in VRU]
VRU_LABEL = {v["key"]: v["label"] for v in VRU}
GOODS_TYPES = {"20", "21", "98"}       # goods over 3.5 t (under 7.5 t, 7.5 t and over, weight not known)
# 22 Oct 2026 (evidence v3): the words for each goods class on the sheet; "98" is DfT's goods vehicle whose weight the
# police did not record, counted as over 3.5 t as DfT counts it
GOODS_WORDS = {"21": "7.5 t and over", "20": "3.5–7.5 t", "98": "weight not recorded"}
LEFT_MANOEUVRES = {"7", "8"}            # turning left, waiting to turn left (the same codes in the 2024 and older fields)

ROAD_CLASS = {"1": "M", "2": "A(M)", "3": "A", "4": "B", "5": "C", "6": "Unclassified road"}
JUNCTION = {"0": None, "13": "T or staggered junction", "16": "Crossroads", "17": "Junction with more than four arms",
            "18": "Private drive or entrance", "19": "Other junction"}
ROAD_TYPE = {"1": "Roundabout", "2": "One way street", "3": "Dual carriageway", "6": "Single carriageway",
             "7": "Slip road", "12": "One way street or slip road"}
LIGHT = {"1": "Daylight", "4": "Darkness, lights lit", "5": "Darkness, lights unlit", "6": "Darkness, no lighting",
         "7": "Darkness, lighting not known"}

META_ID = "current"
STALE_RUN = timedelta(minutes=45)
_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def latest_final_year(today=None):
    """The newest year whose FINAL data should be out on `today` (late July of the year after)."""
    today = today or date.today()
    return today.year - 1 if today.month >= FINAL_MONTH else today.year - 2


def road_words(cls, num):
    """'A6', 'M1', 'B6047', 'C road', 'Unclassified road' from STATS19 first_road_class / first_road_number."""
    c = ROAD_CLASS.get(str(cls or ""))
    if not c:
        return None
    if c == "Unclassified road":
        return c
    n = str(num or "").strip()
    if c == "C" or not n or n in ("0", "-1"):
        return "C road" if c == "C" else f"{c} road"
    return f"{c}{n}"


# --------------------------------------------------------------------------- #
#  The routes, keyed                                                           #
# --------------------------------------------------------------------------- #
def route_key(route_id, alt_index=0):
    return str(route_id) if not alt_index else f"{route_id}@{int(alt_index)}"


class RouteIndex:
    """Every stored road route (keyed route_key: the primary 'R001', an alternative 'R001@1'; both legs and every
    vehicle under one key) and every site, with distances in metres on a local equirectangular projection — the
    community layer's Strip, but answering WHICH route a point is near and how far."""
    CELL = 600.0

    def __init__(self, lines, sites, route_m=NEAR_ROUTE_M, site_m=NEAR_SITE_M):
        # lines: [(key, [[lon, lat], ...])], sites: [(id, name, lon, lat)]
        self.lines = [(k, l) for k, l in (lines or []) if len(l) >= 2]
        self.sites = list(sites or [])
        self.route_m, self.site_m = route_m, site_m
        pts = [c for _, l in self.lines for c in l] + [(s[2], s[3]) for s in self.sites]
        lat0 = (sum(p[1] for p in pts) / len(pts)) if pts else 52.0
        self.kx, self.ky = 111320.0 * math.cos(math.radians(lat0)), 110574.0
        self.grid = {}
        reach = max(route_m, site_m)
        for key, l in self.lines:
            for a, b in zip(l, l[1:]):
                A, B = self._xy(a), self._xy(b)
                self._index(("r", key, A, B), min(A[0], B[0]) - reach, max(A[0], B[0]) + reach,
                            min(A[1], B[1]) - reach, max(A[1], B[1]) + reach)
        for sid, _name, lon, lat in self.sites:
            S = self._xy((lon, lat))
            self._index(("s", sid, S, S), S[0] - reach, S[0] + reach, S[1] - reach, S[1] + reach)
        pad_x, pad_y = (reach + 100) / self.kx, (reach + 100) / self.ky
        self.bbox = ([min(p[0] for p in pts) - pad_x, min(p[1] for p in pts) - pad_y,
                      max(p[0] for p in pts) + pad_x, max(p[1] for p in pts) + pad_y] if pts else None)

    def _xy(self, c):
        return (c[0] * self.kx, c[1] * self.ky)

    def _index(self, item, x0, x1, y0, y1):
        for gx in range(int(x0 // self.CELL), int(x1 // self.CELL) + 1):
            for gy in range(int(y0 // self.CELL), int(y1 // self.CELL) + 1):
                self.grid.setdefault((gx, gy), []).append(item)

    @staticmethod
    def _seg(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

    def in_box(self, lon, lat):
        b = self.bbox
        return bool(b) and b[0] <= lon <= b[2] and b[1] <= lat <= b[3]

    def near(self, lon, lat):
        """({route_key: metres}, {site_id: metres}) for every route within route_m and site within site_m."""
        p = (lon * self.kx, lat * self.ky)
        routes, sites = {}, {}
        for kind, key, a, b in self.grid.get((int(p[0] // self.CELL), int(p[1] // self.CELL)), ()):
            d = self._seg(p, a, b)
            if kind == "r":
                if d <= self.route_m and (key not in routes or d < routes[key]):
                    routes[key] = d
            elif d <= self.site_m and (key not in sites or d < sites[key]):
                sites[key] = d
        return ({k: round(v, 1) for k, v in routes.items()}, {k: round(v, 1) for k, v in sites.items()})

    def metres(self, a, b):
        return math.hypot((a[0] - b[0]) * self.kx, (a[1] - b[1]) * self.ky)


def _coords(g):
    try:
        c = json.loads(g) if isinstance(g, str) else g
    except (TypeError, ValueError):
        return []
    c = c.get("coordinates") if isinstance(c, dict) else c
    out = []
    for p in c or []:
        try:
            out.append([float(p[0]), float(p[1])])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def index_from_db():
    """The tenant's RouteIndex: every stored road route (primary and alternatives, both legs, every vehicle; a line
    drawn twice kept once per key), each abnormal load's drawn line under the load's id (23 Oct 2026; both legs; not a
    withdrawn load's) and every site with a position."""
    import community
    tenant = db.current_tenant()
    lines, seen = [], set()
    for r in db.query("SELECT route_id, alt_index, geometry FROM route_geometry WHERE tenant_id = ? "
                      "AND geometry IS NOT NULL ORDER BY route_id, alt_index, vehicle_profile, leg", (tenant,)):
        coords = _coords(r["geometry"])
        if len(coords) < 2:
            continue
        thin = community._thin(coords)
        key = route_key(r["route_id"], r.get("alt_index") or 0)
        sig = (key, tuple((round(c[0], 3), round(c[1], 3)) for c in thin[:: max(1, len(thin) // 20)]))
        if sig in seen:
            continue
        seen.add(sig)
        lines.append((key, thin))
    # 23 Oct 2026 (the user: "the strip should include the abnormal lines"): each load's own drawn line, both legs,
    # under the load's id — community.strip_from_db's rule. A withdrawn load's line is left out; a load not drawn yet
    # has no line. The key carries no "@", so its collisions count and draw like a route's (along == "route").
    for r in db.query("SELECT id, geometry_json, return_geometry_json FROM abnormal_loads WHERE tenant_id = ? "
                      "AND status != 'withdrawn' ORDER BY id", (tenant,)):
        for col in ("geometry_json", "return_geometry_json"):
            coords = _coords(r.get(col))
            if len(coords) < 2:
                continue
            thin = community._thin(coords)
            key = str(r["id"])
            sig = (key, tuple((round(c[0], 3), round(c[1], 3)) for c in thin[:: max(1, len(thin) // 20)]))
            if sig in seen:
                continue
            seen.add(sig)
            lines.append((key, thin))
    sites = [(l["id"], l.get("name") or l["id"], float(l["lon"]), float(l["lat"])) for l in db.query(
        "SELECT id, name, lon, lat FROM locations WHERE tenant_id = ? AND lat IS NOT NULL AND lon IS NOT NULL", (tenant,))]
    return RouteIndex(lines, sites)


# --------------------------------------------------------------------------- #
#  Reading the three DfT tables                                                #
# --------------------------------------------------------------------------- #
def _rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            yield r


def read_collisions(path, index, year=None):
    """{collision_index: record} for the collisions in one year's collision file that lie in the strip. A row with no
    position, or one outside the strip's box, is skipped before any distance is worked out."""
    out = {}
    for r in _rows(path):
        lon, lat = r.get("longitude"), r.get("latitude")
        try:
            lon, lat = float(lon), float(lat)
        except (TypeError, ValueError):
            continue
        if not index.in_box(lon, lat):
            continue
        routes, sites = index.near(lon, lat)
        if not routes and not sites:
            continue
        try:
            sev = int(r.get("collision_severity") or 3)
        except ValueError:
            sev = 3
        d = (r.get("date") or "").strip()          # dd/mm/yyyy: only the month is kept (R6)
        month = f"{d[6:10]}-{d[3:5]}" if len(d) == 10 and d[2] == "/" else None
        hour, weekday = _hour_of(r.get("time")), _weekday_of(d, r.get("day_of_week"))
        yr = r.get("collision_year") or (month[:4] if month else year)
        out[r["collision_index"]] = {
            "collision_id": r["collision_index"],
            "year": int(yr) if str(yr or "").isdigit() else year,
            "month": month,
            "lon": round(lon, 6), "lat": round(lat, 6),
            "severity": sev if sev in SEVERITY else 3,
            "road": road_words(r.get("first_road_class"), r.get("first_road_number")),
            "road2": road_words(r.get("second_road_class"), r.get("second_road_number")),
            "junction": JUNCTION.get(str(r.get("junction_detail") or "").strip()),
            "road_type": ROAD_TYPE.get(str(r.get("road_type") or "").strip()),
            "speed_limit": int(r["speed_limit"]) if str(r.get("speed_limit") or "").isdigit() else None,
            "light": LIGHT.get(str(r.get("light_conditions") or "").strip()),
            "authority": (r.get("local_authority_highway_current") or r.get("local_authority_highway") or "").strip() or None,
            "n_casualties": int(r["number_of_casualties"]) if str(r.get("number_of_casualties") or "").isdigit() else None,
            "n_vehicles": int(r["number_of_vehicles"]) if str(r.get("number_of_vehicles") or "").isdigit() else None,
            "vru": [], "vru_ksi": [], "goods": False,
            # 22 Oct 2026 (v3): DfT's urban (1) / rural (2) flag, and the vehicle details read_vehicles adds
            "detail": {"urban": int(r["urban_or_rural_area"]) if str(r.get("urban_or_rural_area") or "").strip() in ("1", "2") else None,
                       # DfT's probability that a collision is serious once severity recording is adjusted (fatal = 1):
                       # the observed figure beside DfT's adjusted fatal-or-serious rates
                       "adj_serious": _adj(r.get("collision_adjusted_severity_serious")),
                       # 28 Oct 2026 (0d, John's yes to notes\collision-time-mockup-1028): the hour (0-23) and whether it was
                       # Monday to Friday — never the date or the minute; only counts by hour are ever shown (R6)
                       "hour": hour, "weekday": weekday},
            "dist_m": min(list(routes.values()) + list(sites.values())),
            "routes": routes, "sites": sites,
        }
    return out


def _hour_of(t):
    """DfT's time "HH:MM" -> its hour, 0-23 (None when blank or not a time)."""
    t = str(t or "").strip()
    h = t.split(":")[0] if ":" in t else ""
    return int(h) if h.isdigit() and 0 <= int(h) <= 23 else None


def _weekday_of(d, dow=None):
    """True Monday to Friday, False at the weekend, from the date (dd/mm/yyyy); DfT's day_of_week (1 = Sunday … 7 =
    Saturday) when the date does not read. None when neither does."""
    try:
        return date(int(d[6:10]), int(d[3:5]), int(d[0:2])).weekday() < 5
    except (TypeError, ValueError, IndexError):
        v = str(dow or "").strip()
        return (v not in ("1", "7")) if v in ("1", "2", "3", "4", "5", "6", "7") else None


def _code(r, field):
    """A vehicle field from the 2024 specification, else its _historic twin (the years before 2024 fill only that)."""
    v = str(r.get(field) or "").strip()
    if v in ("", "-1"):
        v = str(r.get(field + "_historic") or "").strip()
    return v


def _adj(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def read_vehicles(path, keep):
    """Marks the kept collisions that involved a goods vehicle over 3.5 t and (22 Oct 2026, v3) records the details the
    sheet reads: the goods vehicles' weight classes, articulated, a goods vehicle turning or waiting to turn left, a goods
    vehicle on a journey for work, and any vehicle turning or waiting to turn left."""
    for r in _rows(path):
        c = keep.get(r.get("collision_index"))
        if c is None:
            continue
        d = c.setdefault("detail", {})
        for k, v in (("goods_types", []), ("goods_artic", False), ("goods_left", False), ("goods_work", False),
                     ("left_turn", False)):
            d.setdefault(k, v)
        vt = str(r.get("vehicle_type") or "").strip()
        left = _code(r, "vehicle_manoeuvre") in LEFT_MANOEUVRES
        d["left_turn"] = d["left_turn"] or left
        if vt in GOODS_TYPES:
            c["goods"] = True
            if vt not in d["goods_types"]:
                d["goods_types"] = sorted(d["goods_types"] + [vt], key=lambda x: ("21", "20", "98").index(x))
            d["goods_artic"] = d["goods_artic"] or str(r.get("towing_and_articulation") or "").strip() == "1"
            d["goods_left"] = d["goods_left"] or left
            d["goods_work"] = d["goods_work"] or _code(r, "journey_purpose_of_driver") == "1"


def read_casualties(path, keep):
    """The road users hurt in each kept collision (VRU keys, in VRU order), and those killed or seriously injured."""
    by_type = {t: v["key"] for v in VRU for t in v["types"]}
    for r in _rows(path):
        c = keep.get(r.get("collision_index"))
        if c is None:
            continue
        t = str(r.get("casualty_type") or "").strip()
        k = "pedestrian" if str(r.get("casualty_class") or "").strip() == "3" else by_type.get(t)
        if not k and str(r.get("escooter_flag") or "").strip() == "1":
            k = "escooter"
        if not k:
            continue
        if k not in c["vru"]:
            c["vru"].append(k)
        if str(r.get("casualty_severity") or "").strip() in ("1", "2") and k not in c["vru_ksi"]:
            c["vru_ksi"].append(k)
    for c in keep.values():
        c["vru"].sort(key=VRU_KEYS.index)
        c["vru_ksi"].sort(key=VRU_KEYS.index)


# --------------------------------------------------------------------------- #
#  Storage                                                                     #
# --------------------------------------------------------------------------- #
_COLS = ("collision_id", "year", "month", "lon", "lat", "severity", "road", "road2", "junction", "road_type",
         "speed_limit", "light", "authority", "n_casualties", "n_vehicles", "vru_json", "vru_ksi_json", "goods",
         "dist_m", "routes_json", "sites_json", "fetched_at", "detail_json")


def _meta_row():
    rows = db.query("SELECT * FROM collision_meta WHERE tenant_id = ? AND meta_id = ?", (db.current_tenant(), META_ID))
    return rows[0] if rows else None


def _detail(row):
    try:
        return json.loads(row["detail_json"]) if row and row.get("detail_json") else {}
    except Exception:
        return {}


def _write_meta(state, detail, by=None, started_at=None, fetched_at=None):
    tenant = db.current_tenant()
    if _meta_row():
        db.execute("UPDATE collision_meta SET state = ?, started_at = COALESCE(?, started_at), "
                   "fetched_at = COALESCE(?, fetched_at), by_whom = COALESCE(?, by_whom), detail_json = ? "
                   "WHERE tenant_id = ? AND meta_id = ?",
                   (state, started_at, fetched_at, by, json.dumps(detail, ensure_ascii=False), tenant, META_ID))
    else:
        db.execute("INSERT INTO collision_meta (tenant_id, meta_id, state, started_at, fetched_at, by_whom, detail_json) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (tenant, META_ID, state, started_at, fetched_at, by, json.dumps(detail, ensure_ascii=False)))


def replace_all(records, fetched_at):
    """Every stored collision replaced in one transaction (a failed refresh never reaches here)."""
    tenant = db.current_tenant()
    rows = []
    for c in records:
        rows.append((tenant, c["collision_id"], c["year"], c["month"], c["lon"], c["lat"], c["severity"], c["road"],
                     c["road2"], c["junction"], c["road_type"], c["speed_limit"], c["light"], c["authority"],
                     c["n_casualties"], c["n_vehicles"], json.dumps(c["vru"]), json.dumps(c["vru_ksi"]),
                     1 if c["goods"] else 0, c["dist_m"], json.dumps(c["routes"], separators=(",", ":")),
                     json.dumps(c["sites"], separators=(",", ":")), fetched_at,
                     json.dumps(c.get("detail") or {}, separators=(",", ":"))))
    db.execute_atomic([
        ("DELETE FROM collision_records WHERE tenant_id = ?", (tenant,)),
        ("INSERT INTO collision_records (tenant_id, " + ", ".join(_COLS) + ") VALUES (" +
         ", ".join("?" * (len(_COLS) + 1)) + ")", rows, True),
    ])
    return len(rows)


def along(c):
    """'route' when a collision is near a PRIMARY road route (the ones the map draws) or a site; 'alternative' when it is
    near a stored alternative only (16 Oct 2026, found on live: 1,013 of 1,887 were, and the map drew them on roads it
    shows no route on). The map, the counts and the CLP plans use 'route'; the alternatives' show with the map's
    Alternative routes layer, and each route's evidence sheet sets the alternatives in their own columns."""
    return "route" if (c.get("sites") or any("@" not in k for k in c.get("routes") or {})) else "alternative"


def _load(r):
    c = dict(r)
    for k, dflt in (("vru_json", []), ("vru_ksi_json", []), ("routes_json", {}), ("sites_json", {}), ("detail_json", {})):
        try:
            c[k[:-5]] = json.loads(c.pop(k) or "null") or dflt
        except (TypeError, ValueError):
            c[k[:-5]] = dflt
    c["goods"] = bool(c.get("goods"))
    c["ksi"] = c.get("severity") in (1, 2)
    c["along"] = along(c)
    return c


def records(route_keys=None):
    """The stored collisions (dicts, newest first). With route_keys, only those near at least one of them."""
    out = []
    for r in db.query("SELECT * FROM collision_records WHERE tenant_id = ? ORDER BY year DESC, month DESC, collision_id",
                      (db.current_tenant(),)):
        c = _load(r)
        if route_keys is not None and not any(k in c["routes"] for k in route_keys):
            continue
        out.append(c)
    return out


def status():
    row = _meta_row()
    det = _detail(row)
    # 16 Oct 2026: the counts are the collisions along the routes the map draws (and round the sites); those near a
    # stored alternative only are counted apart (alternatives_only)
    n = {"all": 0, "ksi": 0, "vru": 0}
    alt = {"all": 0, "ksi": 0}
    for r in db.query("SELECT severity, vru_json, routes_json, sites_json FROM collision_records WHERE tenant_id = ?",
                      (db.current_tenant(),)):
        try:
            c = {"routes": json.loads(r["routes_json"] or "{}"), "sites": json.loads(r["sites_json"] or "{}")}
        except (TypeError, ValueError):
            c = {"routes": {}, "sites": {}}
        ksi = r["severity"] in (1, 2)
        if along(c) == "alternative":
            alt["all"] += 1
            alt["ksi"] += 1 if ksi else 0
            continue
        n["all"] += 1
        n["ksi"] += 1 if ksi else 0
        n["vru"] += 1 if (r["vru_json"] or "[]") != "[]" else 0
    state = (row or {}).get("state") or "never"
    if state == "running" and row and row.get("started_at"):
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(row["started_at"].replace("Z", "+00:00")) > STALE_RUN:
                state = "failed"
                det.setdefault("error", "the last fetch stopped without finishing (the server restarted?)")
        except ValueError:
            pass
    years = det.get("years") or []
    return {"state": state, "started_at": (row or {}).get("started_at"), "fetched_at": (row or {}).get("fetched_at"),
            "by": (row or {}).get("by_whom"), "error": det.get("error"), "notes": det.get("notes") or [],
            "years": years, "period": period_words(years), "files": det.get("files") or [],
            "strip": {"route_m": NEAR_ROUTE_M, "site_m": NEAR_SITE_M, "on_route_m": ON_ROUTE_M},
            "counts": n, "alternatives_only": alt, "source": SOURCE,
            "vehicle_details": bool(det.get("vehicle_details")),
            "hours": bool(det.get("hours")),
            "credit": credit_line() if n["all"] or alt["all"] or years else "",
            "name": LAYER_NAME, "what": WHAT}


def period_words(years):
    ys = sorted(int(y) for y in years or [])
    if not ys:
        return ""
    return f"{ys[0]}–{ys[-1]}" if len(ys) > 1 else str(ys[0])


def credit_line():
    return f"{LAYER_NAME}: {SOURCE['attribution'][0].lower() + SOURCE['attribution'][1:]}."


def _feature(c):
    p = {"severity": c["severity"], "severity_word": SEVERITY[c["severity"]], "ksi": c["ksi"],
         "year": c["year"], "month": c["month"], "road": c["road"], "road2": c["road2"], "junction": c["junction"],
         "road_type": c["road_type"], "speed_limit": c["speed_limit"], "light": c["light"],
         "vru": c["vru"], "vru_words": [VRU_LABEL[k] for k in c["vru"]], "vru_any": bool(c["vru"]),
         "vru_ksi": c["vru_ksi"], "goods": c["goods"], "dist_m": c["dist_m"], "routes": sorted(c["routes"]),
         "along": c["along"]}
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]}, "properties": p}


def payload():
    """GET /api/collisions: the stored collisions as a GeoJSON FeatureCollection (fatal first, so they draw on top
    when the map sorts by order) with the status beside it."""
    st = status()
    feats = [_feature(c) for c in sorted(records(), key=lambda c: -c["severity"])]
    return {"type": "FeatureCollection", "features": feats, "severity": [{"key": k, "label": v} for k, v in SEVERITY.items()],
            "vru_kinds": VRU, **{k: st[k] for k in ("state", "fetched_at", "years", "period", "strip", "counts", "alternatives_only",
                                                    "credit", "notes", "error", "name", "what")}}


def in_view(bbox, ksi_only=False):
    """For a plan: the stored collisions inside the frame [w, s, e, n]."""
    out = []
    for c in records():
        if (ksi_only and not c["ksi"]) or c["along"] != "route":
            continue
        if bbox[0] <= c["lon"] <= bbox[2] and bbox[1] <= c["lat"] <= bbox[3]:
            out.append(c)
    return out


# --------------------------------------------------------------------------- #
#  Fetch                                                                       #
# --------------------------------------------------------------------------- #
TABLE_WORDS = {"collision": "collisions", "vehicle": "vehicles", "casualty": "casualties"}


def default_fetchers():
    import community_sources as cs
    return {"download": cs.download}


def fetch_years(index, years, workdir, fetch):
    """Read every year's three tables; returns (records, files). Raises RuntimeError in words on the first failure."""
    keep_all, files = {}, []
    for y in years:
        paths = {}
        try:
            for table in ("collision", "vehicle", "casualty"):
                p = os.path.join(workdir, f"{table}-{y}.csv")
                final, n = fetch["download"](URL.format(table=table, year=y), p)
                paths[table] = p
                if table == "collision":
                    keep = read_collisions(p, index, year=y)
                    if not keep:
                        break           # nothing in the strip this year: the other two tables are not needed
                elif table == "vehicle":
                    read_vehicles(p, keep)
                else:
                    read_casualties(p, keep)
                files.append(f"{y} {TABLE_WORDS[table]} ({round(n / 1e6, 1)} MB)")
                try:
                    os.remove(p)        # the next table is ~20 MB: the disk holds one at a time
                except OSError:
                    pass
        except RuntimeError as e:
            raise RuntimeError(f"the {y} data could not be read: {str(e)[:180]}")
        keep_all.update(keep)
    return list(keep_all.values()), files


def refresh(by=None, fetchers=None, index=None, today=None):
    """Fetch the latest five final years along the tenant's routes and store what lies in the strip. Synchronous;
    start_refresh() runs it on a thread. All or nothing: a failure keeps what was stored. Returns status()."""
    fetch = dict(default_fetchers(), **(fetchers or {}))
    old = _detail(_meta_row())
    det = {"years": old.get("years") or [], "files": old.get("files") or [], "notes": [], "error": None}
    _write_meta("running", det, by=by, started_at=_now())
    index = index or index_from_db()
    if not index.bbox:
        det["error"] = "nothing to fetch along: no route is worked out and no site has a position yet"
        _write_meta("failed", det)
        return status()
    if not index.lines:
        det["notes"].append("No route is routed yet, so only the sites were searched round.")
    last = latest_final_year(today)
    workdir = tempfile.mkdtemp(prefix="wayscope_collisions_")
    try:
        # the newest final year may be later than the calendar says (or not yet out): step back while it is missing
        for back in range(0, 3):
            years = list(range(last - back - YEARS + 1, last - back + 1))
            try:
                recs, files = fetch_years(index, years, workdir, fetch)
                break
            except RuntimeError as e:
                if back < 2 and "HTTP 404" in str(e) and str(years[-1]) in str(e):
                    continue
                det["error"] = f"{e}; nothing was changed"
                _write_meta("failed", det)
                return status()
        # 22 Oct 2026 (evidence v3): DfT's traffic counts along the routes, for "expected for roads like these" — from
        # the authorities the collisions name; a failure here keeps the collisions and the counts already stored
        traffic_rows, traffic_note = None, None
        if index.lines:
            try:
                import traffic
                traffic_rows, tfiles, tmissing = traffic.fetch(index, years, {c["authority"] for c in recs if c.get("authority")},
                                                               workdir, fetch["download"])
                files = files + tfiles
                if tmissing:
                    traffic_note = ("The traffic counts for " + ", ".join(tmissing) + " could not be read; the other "
                                    "authorities' were.")
            except Exception as e:          # noqa: BLE001 — said on the page, never fatal to the collisions
                print(f"🚧 collisions: the traffic counts could not be read: {str(e)[:300]}", flush=True)   # the reason: the log only
                traffic_note = "The traffic counts could not be read just now; the ones already stored were kept."
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    now = _now()
    replace_all(recs, now)
    if traffic_rows is not None:
        import traffic
        traffic.replace_all(traffic_rows, now)
        det["traffic_points"] = len({r["count_point_id"] for r in traffic_rows})
    if traffic_note:
        det["notes"].append(traffic_note)
    det.update({"years": years, "files": files, "error": None})
    if back:
        det["notes"].append(f"The {last} data is not published yet; the latest five final years are {period_words(years)}.")
    det["vehicle_details"] = True     # 22 Oct 2026 (v3): rows fetched from here on carry detail_json
    det["hours"] = True               # 28 Oct 2026 (0d): ...and the hour and weekday
    _write_meta("done", det, fetched_at=now)
    return status()


def start_refresh(by=None, sync=False, **kw):
    tenant = db.current_tenant()
    with _LOCK:
        st = status()
        if st["state"] == "running":
            return dict(st, started=False, message="a fetch is already running")
        _write_meta("running", dict(_detail(_meta_row()), error=None), by=by, started_at=_now())

    def run():
        tok = db.set_current_tenant(tenant)
        try:
            refresh(by=by, **kw)
        except Exception as e:      # noqa: BLE001
            det = _detail(_meta_row())
            det["error"] = f"the fetch stopped: {str(e)[:200]}"
            _write_meta("failed", det)
        finally:
            try:
                db.reset_current_tenant(tok)
            except Exception:
                pass

    if sync:
        run()
    else:
        threading.Thread(target=run, name="collision-refresh", daemon=True).start()
    return dict(status(), started=True)


# --------------------------------------------------------------------------- #
#  The evidence for one route                                                  #
# --------------------------------------------------------------------------- #
ROWS = [
    ("all", WHAT),
    ("fatal", "Fatal"),
    ("serious", "Serious"),
    ("ksi", "Killed or seriously injured (KSI), all road users"),
    *[(f"vru_ksi:{v['key']}", f"{'An' if v['label'][0] in 'AEIOU' else 'A'} {v['label'].lower()} killed or seriously injured")
      for v in VRU],
    ("vru_any", "A vulnerable road user hurt, any severity"),
    ("goods", "A goods vehicle over 3.5 t involved"),
    ("goods_ksi", "A goods vehicle over 3.5 t involved, KSI"),
    # 22 Oct 2026 (evidence v2, the user's yes to the mockup): the case CLOCS is written for, as its own row
    ("vru_goods", "A vulnerable road user hurt, a goods vehicle over 3.5 t involved"),
    ("cyclist_any", "A cyclist hurt, any severity"),
    ("junction", "At or within 20 m of a junction"),
]
# 22 Oct 2026 (evidence v3): rows that need the vehicle details (read from the fetch after v3 shipped); the sheet shows
# them only when every collision it counts carries them, never a zero that only means "not read yet"
DETAIL_ROWS = [
    ("goods_75", "A goods vehicle of 7.5 t and over involved"),
    ("goods_artic", "An articulated goods vehicle involved"),
    ("goods_left", "A goods vehicle over 3.5 t turning or waiting to turn left"),
    ("cyclist_left", "A cyclist hurt while a vehicle was turning or waiting to turn left"),
]


def _count(recs, key):
    def hit(c):
        if key == "all":
            return True
        if key == "fatal":
            return c["severity"] == 1
        if key == "serious":
            return c["severity"] == 2
        if key == "ksi":
            return c["ksi"]
        if key.startswith("vru_ksi:"):
            return c["ksi"] and key[8:] in c["vru_ksi"]
        if key == "vru_any":
            return bool(c["vru"])
        if key == "goods":
            return c["goods"]
        if key == "goods_ksi":
            return c["goods"] and c["ksi"]
        if key == "vru_goods":
            return c["goods"] and bool(c["vru"])
        if key == "cyclist_any":
            return "cyclist" in c["vru"]
        d = c.get("detail") or {}
        if key == "goods_75":
            return "21" in (d.get("goods_types") or [])
        if key == "goods_artic":
            return bool(d.get("goods_artic"))
        if key == "goods_left":
            return bool(d.get("goods_left"))
        if key == "cyclist_left":
            return "cyclist" in c["vru"] and bool(d.get("left_turn"))
        if key == "junction":
            return bool(c["junction"])
        return False
    return sum(1 for c in recs if hit(c))


def counts_for(recs, key, rows=None):
    """The table's two columns for one route key: on the route (within ON_ROUTE_M) and within NEAR_ROUTE_M."""
    rows = ROWS if rows is None else rows
    near = [c for c in recs if key in c["routes"]]
    on = [c for c in near if c["routes"][key] <= ON_ROUTE_M]
    return {"on": {k: _count(on, k) for k, _ in rows}, "near": {k: _count(near, k) for k, _ in rows}}


def has_details(recs):
    """True when every record carries the v3 vehicle details (fetched after 22 Oct 2026)."""
    return all("goods_types" in (c.get("detail") or {}) for c in recs)


# 28 Oct 2026 (0d): the busy hours, weekdays — the CLP form's example bands, fixed before any route is looked at (John's
# yes, Q1); the middle of the day is shown beside them, never offered on
BUSY_BANDS = [("07:00", "10:00"), ("16:00", "19:00")]
MIDDAY = ("10:00", "16:00")
OFFER_MIN = 10        # the route had at least this many on it in the band over the five years...
OFFER_P = 0.05        # ...and a gap this big comes by chance less than 1 time in 20 (an exact test on the two counts)


def has_hours(recs):
    """True when every record carries the hour and weekday (fetched after 28 Oct 2026)."""
    return all("hour" in (c.get("detail") or {}) for c in recs)


def hours_known(recs):
    """The hours can be shown: every record has its hour — or, with no record near the route at all, the last fetch stored
    the hours (so the sheet says there were none, never that the hours are still to come)."""
    return has_hours(recs) if recs else bool(_detail(_meta_row()).get("hours"))


def _h(t):
    return int(t[:2])


def hour_counts(recs):
    """{'weekday': [24 counts by hour, Monday to Friday], 'weekend': n, 'unknown': n (no hour or no day recorded)}."""
    wk, we, unk = [0] * 24, 0, 0
    for c in recs:
        d = c.get("detail") or {}
        h, w = d.get("hour"), d.get("weekday")
        if h is None or w is None:
            unk += 1
        elif w:
            wk[h] += 1
        else:
            we += 1
    return {"weekday": wk, "weekend": we, "unknown": unk}


def band_sum(hours, band):
    a, b = _h(band[0]), _h(band[1])
    return sum(hours[a:b])


def chance_of_fewer(route_n, alt_n):
    """One-sided exact test on two counts on an equal footing: the chance that the alternative's share of the pair is
    as small as this or smaller, were each collision as likely on either (Binomial(route_n + alt_n, 1/2))."""
    n = route_n + alt_n
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(alt_n + 1)) / 2 ** n


def busy_offers(columns_hours):
    """[(label, alt, [{band, route, alt}], midday)] — for each alternative, the busy bands where it had clearly fewer on it
    than this route (OFFER_MIN, OFFER_P). columns_hours: [(label, alt_index, hour_counts)], this route first."""
    if not columns_hours or columns_hours[0][1]:
        return []
    r_hours = columns_hours[0][2]["weekday"]
    out = []
    for label, alt, hc in columns_hours[1:]:
        bands = []
        for band in BUSY_BANDS:
            rn, an = band_sum(r_hours, band), band_sum(hc["weekday"], band)
            if rn >= OFFER_MIN and chance_of_fewer(rn, an) < OFFER_P:
                bands.append({"from": band[0], "to": band[1], "route": rn, "alt": an})
        if bands:
            out.append({"label": label, "alt": alt, "bands": bands,
                        "midday": {"from": MIDDAY[0], "to": MIDDAY[1], "route": band_sum(r_hours, MIDDAY),
                                   "alt": band_sum(hc["weekday"], MIDDAY)}})
    return out


def offer_words(o, period, short=False):
    """'Alternative 1 had fewer in the busy hours: 5 against 17 (07:00–10:00) and …, weekdays 2021–2025.' (short: the
    Routes page's line)."""
    bands = [f"{b['alt']} against {b['route']} ({b['from']}–{b['to']})" for b in o["bands"]]
    joined = bands[0] if len(bands) == 1 else ", ".join(bands[:-1]) + " and " + bands[-1]
    if short:
        return f"{o['label']} had fewer collisions on it in the busy hours: {joined}, weekdays {period}."
    mid = o["midday"]
    rest = (f" Between {mid['from']} and {mid['to']}: {mid['alt']} against {mid['route']}." if mid else "")
    return f"{o['label']} had fewer in the busy hours: {joined}, weekdays {period}.{rest}"


def gate_span(route_row, factors=None):
    """(from, to) in minutes: the earliest a gate at either end of the route opens to the latest one shuts (each gate's
    own hours, else the default gate hours) — the hours the route's lorries can be on the road. No gate at either end:
    the default gate hours."""
    import gate_hours
    tenant = db.current_tenant()
    spans = []
    for end in ("origin", "dest"):
        gid, lid = route_row.get(f"{end}_gate_id"), route_row.get(f"{end}_id")
        # 28 Oct 2026 (found on live, a 500): never compare `active` in SQL — BOOLEAN on Postgres, an integer in SQLite
        gates = [g for g in db.query("SELECT * FROM location_gates WHERE tenant_id = ? AND location_id = ?", (tenant, lid))
                 if g.get("active") not in (False, 0, "0", "false", "f")]
        if gid:
            gates = [g for g in gates if g["id"] == gid] or gates
        for g in gates:
            (a, b), _basis = gate_hours.effective_window(g, factors)
            if a is not None and b is not None:
                spans.append((a, b) if b > a else (0, 24 * 60))     # a gate open past midnight: the whole day
    if not spans:
        d = gate_hours.default_hours(factors)
        return gate_hours.minutes_of(d["from"]), gate_hours.minutes_of(d["to"])
    return min(a for a, _ in spans), max(b for _, b in spans)


def _chainage(index, line, p):
    """Metres along `line` (from its first vertex) to the point on it nearest `p`."""
    return _project(index, line, p)[1]


def _project(index, line, p):
    """(metres from `line`, metres along it from its first vertex) for the point on `line` nearest `p`."""
    best, at, run = None, 0.0, 0.0
    P = index._xy(p)
    for a, b in zip(line, line[1:]):
        A, B = index._xy(a), index._xy(b)
        dx, dy = B[0] - A[0], B[1] - A[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((P[0] - A[0]) * dx + (P[1] - A[1]) * dy) / L2))
        d = math.hypot(P[0] - (A[0] + t * dx), P[1] - (A[1] + t * dy))
        if best is None or d < best:
            best, at = d, run + t * math.sqrt(L2)
        run += math.sqrt(L2)
    return (best if best is not None else float("inf")), at


def line_length_m(index, line):
    """The length of `line` in metres on the index's projection (the one _project measures along)."""
    return sum(math.hypot(*(B - A for A, B in zip(index._xy(a), index._xy(b)))) for a, b in zip(line, line[1:]))


def locations(recs, index, line):
    """R4: every place where two or more collisions lie within CLUSTER_M of each other (single linkage), ordered along
    `line` from its start — never by count."""
    pts = [c for c in recs]
    groups, seen = [], set()
    for i, c in enumerate(pts):
        if i in seen:
            continue
        seen.add(i)
        g, todo = [c], [c]
        while todo:
            x = todo.pop()
            for j, o in enumerate(pts):
                if j not in seen and index.metres((x["lon"], x["lat"]), (o["lon"], o["lat"])) <= CLUSTER_M:
                    seen.add(j)
                    g.append(o)
                    todo.append(o)
        if len(g) >= 2:
            groups.append(g)
    out = []
    for g in groups:
        lon = sum(c["lon"] for c in g) / len(g)
        lat = sum(c["lat"] for c in g) / len(g)
        roads = []
        for c in g:
            for r in (c["road"], c["road2"]):
                if r and r not in roads:
                    roads.append(r)
        juncs = sorted({c["junction"] for c in g if c["junction"]})
        vru = [k for k in VRU_KEYS if any(k in c["vru"] for c in g)]
        years = sorted({c["year"] for c in g if c["year"]})
        out.append({"lon": lon, "lat": lat, "n": len(g),
                    "fatal": sum(1 for c in g if c["severity"] == 1), "serious": sum(1 for c in g if c["severity"] == 2),
                    "slight": sum(1 for c in g if c["severity"] == 3), "roads": roads, "junction": juncs,
                    "vru": vru, "vru_words": [VRU_LABEL[k] for k in vru], "goods": sum(1 for c in g if c["goods"]),
                    "years": years, "along_m": _chainage(index, line, (lon, lat)) if len(line) >= 2 else None,
                    "ids": [c["collision_id"] for c in g]})
    out.sort(key=lambda L: (L["along_m"] is None, L["along_m"] or 0))
    for i, L in enumerate(out, 1):
        L["no"] = i
    return out


def nearby_community(lon, lat, index, limit=4, within_m=NEAR_ROUTE_M, feats=None):
    """The community considerations within `within_m` of a point: the NEAREST of each kind (points only), nearest kind
    first, at most `limit` kinds (None: every kind) — 'Schools: Langham Primary 120 m'."""
    import community
    best = {}
    for f in (community.features() if feats is None else feats):
        g = f.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        d = index.metres((lon, lat), g["coordinates"][:2])
        kind = f["properties"]["kind"]
        if d <= within_m and (kind not in best or d < best[kind][0]):
            best[kind] = (d, f["properties"].get("name"))
    out = []
    for kind, (d, name) in sorted(best.items(), key=lambda kv: kv[1][0])[:limit]:
        label = community.KIND_BY_KEY.get(kind, {}).get("label") or kind
        out.append({"kind": label, "name": name or label, "m": int(round(d))})
    return out


# --------------------------------------------------------------------------- #
#  22 Oct 2026 — evidence v2 (the user's yes to notes\collision-evidence-v2-   #
#  mockup-1022): the route stretch by stretch, the plan's lorries beside it    #
# --------------------------------------------------------------------------- #
# The PDF's "Nearby" (the appendix): schools and health within 250 m, bus stops within 100 m (people at the kerb). Every
# other kind, and every kind's nearest within 250 m, stays in the XLSX.
PDF_NEARBY_M = {"schools": NEAR_ROUTE_M, "hospitals": NEAR_ROUTE_M, "health": NEAR_ROUTE_M, "bus_stops": 100}
STRETCH_KINDS = {"schools": "schools", "hospitals": "health", "health": "health"}   # the stretch table's two counts
STRETCH_MIN = 4                     # a road that fewer collisions than this name joins its neighbour
STRETCH_SPLIT_M = 5 * 1609.344      # one road longer than 5 mi is split once where its speed limits change
SPEED_LOW_MAX = 40                  # 20-40 mph is one band, 50-70 the other
SPLIT_AGREE = 0.8                   # ...when at least 80 % of its collisions fall on the right side of the split
OVERLAP_M = 50                      # a run of the scheme's lorries counts on a stretch it covers by more than this
GAP_M = 250                         # ...and the route's own figure where no run covers more than this (a gate's last
                                    # few metres, where two bakes drew the road apart, are not a stretch of their own)


def pdf_nearby(community_list):
    """The PDF's Nearby cell from a place's community list: schools and health within 250 m, bus stops within 100 m."""
    import community
    limit = {community.KIND_BY_KEY[k]["label"]: m for k, m in PDF_NEARBY_M.items() if k in community.KIND_BY_KEY}
    return [x for x in community_list or [] if x["kind"] in limit and x["m"] <= limit[x["kind"]]]


def _numbered(road):
    """A road with a number ('A6', 'B4114', 'M1'), not 'C road', 'B road' or 'Unclassified road'."""
    return bool(road) and not road.endswith(" road")


def route_road(c):
    """The road a collision on the route names for the route: its first road when numbered, else its second (a
    collision at a side road's mouth is often recorded on the side road), else None."""
    if _numbered(c.get("road")):
        return c["road"]
    if _numbered(c.get("road2")):
        return c["road2"]
    return None


def _speed_words(limits):
    lo, hi = min(limits), max(limits)
    return f"{lo} mph" if lo == hi else f"{lo}–{hi} mph"


def _split_by_speed(part):
    """One stretch of one road ({"from_m", "to_m", "road", "on": [(m, c)]}) split once where its recorded speed limits
    change between 20-40 and 50-70 mph — only when it is longer than STRETCH_SPLIT_M, both sides keep STRETCH_MIN
    collisions and SPLIT_AGREE of them fall on their side. A list of one or two parts."""
    if part["to_m"] - part["from_m"] <= STRETCH_SPLIT_M:
        return [part]
    pts = [(m, c["speed_limit"]) for m, c in part["on"] if c.get("speed_limit")]
    n = len(pts)
    best = None
    for k in range(STRETCH_MIN, n - STRETCH_MIN + 1):
        for left_low in (True, False):
            good = sum(1 for _, s in pts[:k] if (s <= SPEED_LOW_MAX) == left_low) \
                + sum(1 for _, s in pts[k:] if (s <= SPEED_LOW_MAX) != left_low)
            if best is None or good > best[0]:
                best = (good, k, left_low)
    if not best or best[0] < SPLIT_AGREE * n:
        return [part]
    _, k, left_low = best
    cut = (pts[k - 1][0] + pts[k][0]) / 2
    out = []
    for a, b, low in ((part["from_m"], cut, left_low), (cut, part["to_m"], not left_low)):
        on = [(m, c) for m, c in part["on"] if a <= m < b or (b == part["to_m"] and m >= a)]
        lims = [c["speed_limit"] for _, c in on if c.get("speed_limit") and (c["speed_limit"] <= SPEED_LOW_MAX) == low]
        out.append({"from_m": a, "to_m": b, "road": part["road"], "on": on,
                    "speed": _speed_words(lims) if lims else None})
    return out


def stretches(on, length_m):
    """
    The route cut into stretches from A, from the collisions ON it: `on` is [(metres from A, record)] sorted. Each
    stretch is the road DfT records for its collisions (route_road); a road that fewer than STRETCH_MIN collisions
    name joins the neighbour with more; one road longer than STRETCH_SPLIT_M is split once by speed limit. Boundaries
    fall half way between the last collision of one road and the first of the next — they come from the collisions,
    not from a road map (the stored road routes carry no road names). No numbered road at all: one stretch, the whole
    route. Returns [{"no", "from_m", "to_m", "road", "speed", "name", "on"}], in order from A, covering 0..length_m.
    """
    runs = []
    for m, c in on:
        r = route_road(c)
        if not r:
            continue
        if runs and runs[-1]["road"] == r:
            runs[-1]["ch"].append(m)
        else:
            runs.append({"road": r, "ch": [m]})

    def join():
        k = 0
        while k < len(runs) - 1:
            if runs[k]["road"] == runs[k + 1]["road"]:
                runs[k]["ch"] += runs.pop(k + 1)["ch"]
            else:
                k += 1
    while len(runs) > 1:
        i = min(range(len(runs)), key=lambda k: (len(runs[k]["ch"]), k))
        if len(runs[i]["ch"]) >= STRETCH_MIN:
            break
        j = max((x for x in (i - 1, i + 1) if 0 <= x < len(runs)), key=lambda x: len(runs[x]["ch"]))
        runs[j]["ch"] = sorted(runs[j]["ch"] + runs[i]["ch"])
        del runs[i]
        join()
    if not runs:
        parts = [{"from_m": 0.0, "to_m": length_m, "road": None, "on": list(on)}]
    else:
        cuts = [0.0] + [(runs[k]["ch"][-1] + runs[k + 1]["ch"][0]) / 2 for k in range(len(runs) - 1)] + [length_m]
        parts = []
        for k, r in enumerate(runs):
            a, b = cuts[k], max(cuts[k + 1], cuts[k])
            parts.append({"from_m": a, "to_m": b, "road": r["road"],
                          "on": [(m, c) for m, c in on if a <= m < b or (k == len(runs) - 1 and m >= a)]})
    out = []
    for p in parts:
        out.extend(_split_by_speed(p) if p["road"] else [p])
    for i, s in enumerate(out, 1):
        s["no"] = i
        s.setdefault("speed", None)
        s["name"] = (f"{s['road']}, {s['speed']}" if s["speed"] else s["road"]) if s["road"] else "The whole route"
    return out


def plan_loads(factors=None):
    """
    {route_id: {month_index: loads}} and {route_id: {month_index: [vehicle names]}} over the APPROVED forecast — the
    public map bar's loads (main._month_kpi_line: tonnes ÷ payload, fractional), one query, no route analysis.
    """
    import main
    import derived
    import conversions
    factors = factors or conversions.load_factors()
    vs = factors.get("vehicles", {}) or {}
    fb_payload, fb_name = derived.payload_for(None, factors)
    loads, vehicles = {}, {}
    for r in db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND status = 'Approved' "
                      "ORDER BY month_index, route_id, discipline, section_id, id", (db.current_tenant(),)):
        line = main._month_kpi_line(r, "vehicles", factors, vs, fb_payload, fb_name)
        mi = int(r["month_index"])
        rl = loads.setdefault(r["route_id"], {})
        rl[mi] = rl.get(mi, 0.0) + float(line.get("vehicle_loads") or 0.0)
        vv = vehicles.setdefault(r["route_id"], {}).setdefault(mi, [])
        if line.get("vehicle_name") and line["vehicle_name"] not in vv:
            vv.append(line["vehicle_name"])
    return loads, vehicles


def plan_beside(route_id, index, line):
    """
    The plan's lorries for the evidence (CLOCS 4.1a: crash data beside "volume, frequency and type of vehicle
    movements"): this route's BUSIEST month of Approved lines, its movements a day that month, and the stretches of
    its loaded road route the scheme's other routes share (road_sections' stored runs) with every owner's movements a
    day summed — road_load's rule (one movement = one load there and back, never doubled), read without a route
    analysis. None when the route has no Approved line. Never divided into a collision count.
    """
    import main
    import conversions
    import road_sections
    import gate_arrivals
    factors = conversions.load_factors()
    wd = main._working_days(factors)
    loads, vehicles = plan_loads(factors)
    own = loads.get(route_id) or {}
    own = {m: v for m, v in own.items() if v > 0}
    if not own:
        return None
    month = max(own, key=lambda m: (own[m], -m))
    per_day = own[month] / wd
    segs = []
    if len(line) >= 2:
        for run in road_sections.stored_runs("loaded"):
            if route_id not in run["routes"] or len(run["geometry"]) < 2:
                continue
            g = run["geometry"]
            probe = g[:: max(1, len(g) // 12)] + [g[-1]]
            along = [_project(index, line, p)[1] for p in probe]
            v = sum((loads.get(r) or {}).get(month, 0.0) for r in run["routes"]) / wd
            segs.append((min(along), max(along), v))
    return {"month": month, "month_words": gate_arrivals.month_label(month), "per_day": per_day,
            "vehicles": (vehicles.get(route_id) or {}).get(month) or [], "segments": segs}


def _whole(x):
    return int(math.floor(x + 0.5))


def stretch_lorries(plan, a, b):
    """(lowest, highest) whole movements a day of the scheme's lorries along [a, b] metres from A: the shared runs that
    cover it by more than OVERLAP_M, and this route's own figure where none covers more than GAP_M of it in all. None
    without a plan."""
    if not plan:
        return None
    vals, covered = [], []
    for s0, s1, v in plan["segments"]:
        lo, hi = max(a, s0), min(b, s1)
        if hi - lo > OVERLAP_M:
            vals.append(v)
            covered.append((lo, hi))
    covered.sort()
    gap, at = 0.0, a
    for lo, hi in covered:
        if lo > at:
            gap += lo - at
        at = max(at, hi)
    gap += max(0.0, b - at)
    if gap > GAP_M or not vals:
        vals.append(plan["per_day"])
    return _whole(min(vals)), _whole(max(vals))


def stretch_summary(parts, locs, plan, features, index, line, du_words):
    """Each stretch's row: the counts on the route, the places in it (by number), the scheme's lorries a day, the
    schools and health within 250 m of it. `du_words(metres)` gives a distance in the tenant's unit."""
    near_kinds = []
    for f in features or []:
        g = f.get("geometry") or {}
        k = STRETCH_KINDS.get((f.get("properties") or {}).get("kind"))
        if g.get("type") != "Point" or not k or len(line) < 2:
            continue
        d, m = _project(index, line, g["coordinates"][:2])
        if d <= NEAR_ROUTE_M:
            near_kinds.append((m, k))
    out = []
    last = len(parts) - 1
    for i, s in enumerate(parts):
        a, b = s["from_m"], s["to_m"]
        inside = (lambda m: a <= m < b or (i == last and m >= a))
        recs = [c for _, c in s["on"]]
        nos = [L["no"] for L in locs if L.get("along_m") is not None and inside(L["along_m"])]
        for L in locs:
            if L["no"] in nos:
                L["stretch"] = s["no"]
        out.append({"no": s["no"], "name": s["name"], "road": s["road"], "speed": s["speed"],
                    "from_m": a, "to_m": b, "from_words": du_words(a), "to_words": du_words(b),
                    "length_words": du_words(b - a),
                    "n": len(recs), "fatal": sum(1 for c in recs if c["severity"] == 1),
                    "ksi": sum(1 for c in recs if c["ksi"]), "vru_ksi": sum(1 for c in recs if c["vru_ksi"]),
                    "goods": sum(1 for c in recs if c["goods"]), "places": len(nos),
                    "place_nos": (nos[0], nos[-1]) if nos else None,
                    "lorries": stretch_lorries(plan, a, b),
                    "schools": sum(1 for m, k in near_kinds if k == "schools" and inside(m)),
                    "health": sum(1 for m, k in near_kinds if k == "health" and inside(m))})
    return out


def point_at(index, line, metres):
    """The (lon, lat) `metres` along `line` from its first vertex (on the index's projection)."""
    run = 0.0
    for a, b in zip(line, line[1:]):
        A, B = index._xy(a), index._xy(b)
        L = math.hypot(B[0] - A[0], B[1] - A[1])
        if run + L >= metres and L > 0:
            t = (metres - run) / L
            return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
        run += L
    return list(line[-1]) if line else None


def line_between(index, line, a_m, b_m):
    """The vertices of `line` between a_m and b_m metres from its start, with the two end points."""
    out, run = [point_at(index, line, a_m)], 0.0
    for a, b in zip(line, line[1:]):
        A, B = index._xy(a), index._xy(b)
        run += math.hypot(B[0] - A[0], B[1] - A[1])
        if a_m < run < b_m:
            out.append(list(b))
    out.append(point_at(index, line, b_m))
    return [p for p in out if p]


# --------------------------------------------------------------------------- #
#  22 Oct 2026 - evidence v3: cycle routes beside / meeting the route, the     #
#  route's own left turns, the routes compared                                 #
# --------------------------------------------------------------------------- #
CYCLE_BESIDE_M = 20       # a stretch of route runs "beside" a cycle route when one is within this
CYCLE_MEETS_M = 8         # a cycle route "meets" the route where it comes within this (crossing or joining)
CYCLE_MEET_GAP_M = 60     # ...one place per run, runs closer than this along the route joined
TURN_WINDOW_M = 25        # a left turn: the heading over the next 25 m turned 45 degrees or more anticlockwise
TURN_MIN_DEG = 45         #   from the heading over the last 25 m (x east, y north; UK traffic turns left across
TURN_JOIN_M = 40          #   the nearside, where a cyclist rides); turns closer than 40 m are one, at the sharpest
TURN_CYCLE_M = 30         # a left turn "where the route meets a cycle route": one within this of the turn


def _resample(index, line, step):
    """Points every `step` metres along `line` on the index's projection, with their distance from its start."""
    P = [index._xy(p) for p in line]
    out, carry, run = [(P[0], 0.0)], 0.0, 0.0
    for a, b in zip(P, P[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        t = step - carry
        while t <= seg and seg > 0:
            out.append(((a[0] + (b[0] - a[0]) * t / seg, a[1] + (b[1] - a[1]) * t / seg), run + t))
            t += step
        carry = (carry + seg) % step
        run += seg
    return out


class _SegGrid:
    """The cycle routes' segments in 100 m cells, for 'how far is the nearest cycle route' along a route."""
    CELL = 100.0

    def __init__(self, index, lines):
        self.g = {}
        for name, line in lines:
            P = [index._xy(p) for p in line]
            for a, b in zip(P, P[1:] or P):
                for gx in range(int(min(a[0], b[0]) // self.CELL) - 1, int(max(a[0], b[0]) // self.CELL) + 2):
                    for gy in range(int(min(a[1], b[1]) // self.CELL) - 1, int(max(a[1], b[1]) // self.CELL) + 2):
                        self.g.setdefault((gx, gy), []).append((a, b, name))

    def nearest(self, p):
        best, name = None, None
        for a, b, n in self.g.get((int(p[0] // self.CELL), int(p[1] // self.CELL)), ()):
            d = RouteIndex._seg(p, a, b)
            if best is None or d < best:
                best, name = d, n
        return (best, name) if best is not None else (float("inf"), None)


def cycle_lines():
    """The community layer's cycle routes (National Cycle Network and cycle paths, OpenStreetMap) as (name, line) pairs."""
    import community
    out = []
    for f in community.features(kinds=["cycle"]):
        g = f.get("geometry") or {}
        name = (f.get("properties") or {}).get("name") or "Cycle route"
        if g.get("type") == "LineString":
            out.append((name, g["coordinates"]))
        elif g.get("type") == "MultiLineString":
            out.extend((name, l) for l in g["coordinates"])
    return out


def cycle_along(index, line, grid):
    """{'beside_m': [metres from A, sampled every 10 m, beside a cycle route], 'meets': [(metres from A, name)]} for
    one route: within CYCLE_BESIDE_M is beside; within CYCLE_MEETS_M is a meeting, one per run."""
    beside, touch = [], []
    if grid is None or len(line) < 2:
        return {"beside_m": [], "meets": []}
    for p, m in _resample(index, line, 10.0):
        d, n = grid.nearest(p)
        if d <= CYCLE_BESIDE_M:
            beside.append(m)
        if d <= CYCLE_MEETS_M:
            touch.append((m, n))
    meets = []
    for m, n in touch:
        if meets and m - meets[-1][1] <= CYCLE_MEET_GAP_M:
            meets[-1][1] = m
        else:
            meets.append([m, m, n])
    return {"beside_m": beside, "meets": [((a + b) / 2, n) for a, b, n in meets]}


def left_turns(index, line, grid=None):
    """The route's own left turns: [{'m', 'deg', 'cycle', 'cycle_m'}] where the heading over the next TURN_WINDOW_M
    turns TURN_MIN_DEG or more anticlockwise from the last, one per TURN_JOIN_M at its sharpest, with the nearest cycle
    route within TURN_CYCLE_M (if any). Worked out from the stored road route, so a roundabout's gentle entry may not
    count: the sheet says how it is measured."""
    if len(line) < 2:
        return []
    pts = _resample(index, line, 5.0)
    k = int(TURN_WINDOW_M / 5)

    def hd(a, b):
        return math.atan2(b[1] - a[1], b[0] - a[0])
    cand = []
    for i in range(k, len(pts) - k):
        d = math.degrees(hd(pts[i][0], pts[i + k][0]) - hd(pts[i - k][0], pts[i][0]))
        d = (d + 180) % 360 - 180
        if d >= TURN_MIN_DEG:
            cand.append((i, d))
    turns = []
    for i, d in cand:
        if turns and i - turns[-1][0] <= int(TURN_JOIN_M / 5):
            if d > turns[-1][1]:
                turns[-1] = (i, d)
        else:
            turns.append((i, d))
    out = []
    for i, d in turns:
        p, m = pts[i]
        cd, cn = grid.nearest(p) if grid is not None else (float("inf"), None)
        out.append({"m": m, "deg": int(round(d)), "cycle": cn if cd <= TURN_CYCLE_M else None,
                    "cycle_m": int(round(cd)) if cd <= TURN_CYCLE_M else None})
    return out


def densest_window(on, width_m):
    """(start, end) metres from A of the window `width_m` long holding the most collisions on the route (the first
    such window from A), or None with fewer than 3 — the evidence map's inset frames it, chosen only for legibility."""
    ms = sorted(m for m, _ in on)
    best = None
    j = 0
    for i, m in enumerate(ms):
        while ms[j] < m - width_m:
            j += 1
        n = i - j + 1
        if best is None or n > best[0]:
            best = (n, ms[j], m)
    if not best or best[0] < 3:
        return None
    _, a, b = best
    mid = (a + b) / 2
    return max(0.0, mid - width_m / 2), mid + width_m / 2


class EvidenceError(LookupError):
    """No such route (for this tenant, or for this team code)."""


def _route_row(route_id, acc=None):
    """The route's row; EvidenceError when there is none, or when a team code asks for another team's route."""
    rows = db.query("SELECT * FROM routes WHERE tenant_id = ? AND id = ?", (db.current_tenant(), route_id))
    if not rows:
        raise EvidenceError(f"no route {route_id}")
    r = rows[0]
    own = (acc or {}).get("ipt") if isinstance(acc, dict) else None
    if own:
        import access
        if (access.canonical_ipt(r.get("ipt")) or r.get("ipt")) != (access.canonical_ipt(own) or own):
            raise EvidenceError(f"no route {route_id}")
    return r


def _word_offers(offers, period, km_of):
    """Each offer's words, and how much longer or shorter the alternative is (the loaded leg, the tenant's unit)."""
    import export
    du = export._du()
    r_km = km_of(0)
    for o in offers:
        a_km = km_of(o["alt"])
        if a_km is not None and r_km is not None:
            o["extra"] = f"{export._dist(abs(a_km - r_km)):.1f} {du} {'longer' if a_km >= r_km else 'shorter'} each way"
        o["words"] = offer_words(o, period)
        o["short"] = offer_words(o, period, short=True)
    return offers


def busy_hours(route_id, acc=None):
    """
    28 Oct 2026 (0d): the Routes page's line under a route's options — the alternatives that had clearly fewer collisions on
    them in the weekday busy hours (busy_offers), read from the stored collisions and the stored road routes only (no
    map, plan or traffic: quick). {"shown": every record has its hour, "offers": [...], "period"}. Offered, never applied.
    """
    import network
    _route_row(route_id, acc)
    geo = {}
    for g in db.query("SELECT alt_index, vehicle_profile, distance_km FROM route_geometry WHERE tenant_id = ? AND route_id = ? "
                      "AND leg = 'loaded' AND geometry IS NOT NULL", (db.current_tenant(), route_id)):
        geo.setdefault(int(g.get("alt_index") or 0), {})[g["vehicle_profile"]] = g.get("distance_km")
    keys = [(a, route_key(route_id, a)) for a in sorted(geo)] or [(0, route_key(route_id))]
    recs = records([k for _, k in keys])
    period = status()["period"]
    if not hours_known(recs):
        return {"shown": False, "offers": [], "period": period}
    cols = []
    for alt, key in keys:
        on_c = [c for c in recs if c["routes"].get(key, 1e9) <= ON_ROUTE_M]
        cols.append(("This route" if not alt else f"Alt {alt}", alt, hour_counts(on_c)))
    prim = geo.get(0) or {}
    used = network.DEFAULT_PROFILE if network.DEFAULT_PROFILE in prim else (sorted(prim)[0] if prim else None)

    def km_of(alt):
        v = (geo.get(alt) or {}).get(used)
        return float(v) if v is not None else None
    offers = _word_offers(busy_offers(cols) if cols and not cols[0][1] else [], period, km_of)
    return {"shown": True, "offers": offers, "period": period}


def evidence(route_id, acc=None, now=None):
    """
    Everything one Route collision evidence sheet prints, as data: the route, the period, the counts on the route and
    within 250 m for the route and each stored alternative, the locations with more than one collision along the
    primary route, the community considerations near each, the collisions themselves (for the map and the XLSX).
    A team code (acc with an ipt) reads its own team's routes only: EvidenceError otherwise.
    """
    import network
    import conversions
    import export
    import bulletin_doc
    tenant = db.current_tenant()
    r = _route_row(route_id, acc)
    locs = {l["id"]: l for l in db.query("SELECT id, name FROM locations WHERE tenant_id = ? AND id IN (?, ?)",
                                         (tenant, r["origin_id"], r["dest_id"]))}
    geo = {}
    for g in db.query("SELECT * FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND geometry IS NOT NULL",
                      (tenant, route_id)):
        geo.setdefault(int(g.get("alt_index") or 0), {}).setdefault(g["vehicle_profile"], {})[g["leg"]] = g
    prim = geo.get(0) or {}
    used = network.DEFAULT_PROFILE if network.DEFAULT_PROFILE in prim else (sorted(prim)[0] if prim else None)
    legs = prim.get(used) or {}
    loaded = _coords(legs["loaded"]["geometry"]) if legs.get("loaded") else []
    ret = _coords(legs["return"]["geometry"]) if legs.get("return") else []
    du = export._du()

    def length_words(alt):
        g = ((geo.get(alt) or {}).get(used) or {}).get("loaded")
        if not g:
            g = next((v.get("loaded") for v in (geo.get(alt) or {}).values() if v.get("loaded")), None)
        if not g or g.get("distance_km") is None:
            return None
        return f"{export._dist(float(g['distance_km'])):.1f} {du}"

    keys = [(0, route_key(route_id))] + [(a, route_key(route_id, a)) for a in sorted(geo) if a]
    recs = records([k for _, k in keys])
    index = index_from_db()
    # 22 Oct 2026 (v3): the rows that need the vehicle details only once every counted collision carries them
    details = bool(recs) and has_details(recs)
    rows = ROWS + (DETAIL_ROWS if details else [])
    columns = []
    for alt, key in keys:
        columns.append({"key": key, "alt": alt, "label": "This route" if not alt else f"Alternative {alt}",
                        "length": length_words(alt), **counts_for(recs, key, rows)})
    key0 = route_key(route_id)
    prim_recs = [c for c in recs if key0 in c["routes"]]
    locs_out = locations(prim_recs, index, loaded)
    import community
    feats = community.features()

    def du_words(metres):
        return f"{export._dist(metres / 1000):.1f}"
    for L in locs_out:
        # 22 Oct 2026 (v2): every kind's nearest within 250 m (the XLSX keeps them all); the PDF prints pdf_nearby()
        L["community"] = nearby_community(L["lon"], L["lat"], index, limit=None, feats=feats)
        L["nearby_pdf"] = pdf_nearby(L["community"])
        if L["along_m"] is not None:
            L["along_words"] = f"{du_words(L['along_m'])} {du} from A"
            L["along_short"] = f"{du_words(L['along_m'])} {du}"
    # 22 Oct 2026 (v2): each collision's distance from A along the loaded road route; the stretches from those on it
    length_m = line_length_m(index, loaded) if len(loaded) >= 2 else 0.0
    for c in prim_recs:
        c["along_m"] = _chainage(index, loaded, (c["lon"], c["lat"])) if len(loaded) >= 2 else None
    on = sorted(((c["along_m"], c) for c in prim_recs if c["routes"][key0] <= ON_ROUTE_M and c["along_m"] is not None),
                key=lambda mc: (mc[0], mc[1]["collision_id"]))
    parts = stretches(on, length_m) if len(loaded) >= 2 else []
    try:
        plan = plan_beside(route_id, index, loaded)
        plan_error = None
    except Exception as e:                      # the evidence never fails for want of the plan: it says so instead
        plan, plan_error = None, f"the plan's lorry figures could not be read ({e.__class__.__name__})"
    stretch_rows = stretch_summary(parts, locs_out, plan, feats, index, loaded, du_words)
    for s in parts:
        for _, c in s["on"]:
            c["stretch"] = s["no"]
    window = densest_window(on, 1609.344 if du == "mi" else 1000.0)
    for s in stretch_rows:
        s["mid"] = point_at(index, loaded, (s["from_m"] + s["to_m"]) / 2) if len(loaded) >= 2 else None
    inset_line = line_between(index, loaded, *window) if window else []
    # 22 Oct 2026 (v3): cycle routes and the route's own left turns, for the route and each alternative; the routes
    # compared side by side on page 1; the lorry-involved collisions on the route, listed
    cl_lines = cycle_lines()
    grid = _SegGrid(index, cl_lines) if cl_lines else None
    mu = 1609.344 if du == "mi" else 1000.0

    def leg_of(alt):
        g = ((geo.get(alt) or {}).get(used) or {}).get("loaded")
        if not g:
            g = next((v.get("loaded") for v in (geo.get(alt) or {}).values() if v.get("loaded")), None)
        return _coords(g["geometry"]) if g else []
    headline, alt_lines, hours_cols = [], [], []
    hours_known_ = hours_known(recs)     # 28 Oct 2026 (0d): counts by hour once every record has its hour (or none is near)
    cyc0, turns0 = {"beside_m": [], "meets": []}, []
    for col in columns:
        line = loaded if not col["alt"] else leg_of(col["alt"])
        if col["alt"] and line:
            alt_lines.append((col["label"], line))
        cyc = cycle_along(index, line, grid)
        turns = left_turns(index, line, grid)
        if not col["alt"]:
            cyc0, turns0 = cyc, turns
        on_c = [c for c in recs if c["routes"].get(col["key"], 1e9) <= ON_ROUTE_M]
        hc = hour_counts(on_c)
        hours_cols.append((col["label"], col["alt"], hc))
        headline.append({
            "label": col["label"], "length": col.get("length"), "on": len(on_c),
            "ksi": sum(1 for c in on_c if c["ksi"]), "fatal": sum(1 for c in on_c if c["severity"] == 1),
            "vru_ksi": sum(1 for c in on_c if c["vru_ksi"]), "cyclist": sum(1 for c in on_c if "cyclist" in c["vru"]),
            "cyclist_ksi": sum(1 for c in on_c if "cyclist" in c["vru_ksi"]), "goods": sum(1 for c in on_c if c["goods"]),
            "beside": f"{export._dist(len(cyc['beside_m']) * 10 / 1000):.1f}" if grid is not None else None,
            "meets": len(cyc["meets"]) if grid is not None else None, "turns": len(turns),
            "turns_cycle": sum(1 for x in turns if x["cycle"]) if grid is not None else None,
            "lorries": (plan["per_day"] if plan else None) if not col["alt"] else None,
            # 28 Oct 2026 (0d): the weekday busy bands, on the route
            "busy": [band_sum(hc["weekday"], b) for b in BUSY_BANDS] if hours_known_ else None,
        })
    for x in turns0:
        x["words"] = f"{du_words(x['m'])} {du}"
    for s in stretch_rows:
        a, b, last = s["from_m"], s["to_m"], s["no"] == len(stretch_rows)
        inside = (lambda m: a <= m < b or (last and m >= a))
        recs_s = [c for c in prim_recs if c.get("stretch") == s["no"]]
        s["cyclist"] = sum(1 for c in recs_s if "cyclist" in c["vru"])
        s["cyclist_ksi"] = sum(1 for c in recs_s if "cyclist" in c["vru_ksi"])
        s["beside"] = f"{export._dist(sum(1 for m in cyc0['beside_m'] if inside(m)) * 10 / 1000):.1f}" if grid is not None else None
        s["meets"] = sum(1 for m, _ in cyc0["meets"] if inside(m)) if grid is not None else None
    # 22 Oct 2026 (v3): expected for roads like these — DfT's traffic counts on the stretch × DfT's national rate for its
    # road type (traffic.py); the observed fatal-or-serious figure on DfT's adjusted basis where every collision has it
    import traffic
    trows = traffic.stored()
    years_held = status()["years"]
    for s in stretch_rows:
        recs_s = [c for c in prim_recs if c.get("stretch") == s["no"]]
        if not trows:
            s["expected"] = {"why": "traffic counts not fetched yet"}
            continue
        e = traffic.expected_for(index, loaded, s["from_m"], s["to_m"], s.get("road"), traffic.urban_of(recs_s),
                                 years_held, trows)
        if "expected" in e:
            adj = [(c.get("detail") or {}).get("adj_serious") for c in recs_s if c["severity"] != 1]
            if all(a is not None for a in adj):
                e["obs_fsc"], e["fsc_basis"] = sum(1 for c in recs_s if c["severity"] == 1) + sum(adj), "adjusted"
            else:
                e["obs_fsc"], e["fsc_basis"] = sum(1 for c in recs_s if c["ksi"]), "reported"
            e["reading"] = traffic.reading(s["n"], e["range"])
            e["reading_fsc"] = traffic.reading(int(round(e["obs_fsc"])), e["range_fsc"])
        s["expected"] = e
    with_exp = [s for s in stretch_rows if "expected" in s["expected"]]
    if headline:
        if with_exp and len(with_exp) == len(stretch_rows):
            tot = sum(s["expected"]["expected"] for s in with_exp)
            headline[0]["expected"] = {"expected": tot, "range": traffic.poisson_range(tot), "covers": "all"}
        elif with_exp:
            headline[0]["expected"] = {"covers": f"{len(with_exp)} of {len(stretch_rows)} stretches"}
        else:
            headline[0]["expected"] = None
    lorry_list = []
    for c in sorted((c for c in prim_recs if c["goods"] and c["routes"][key0] <= ON_ROUTE_M),
                    key=lambda c: (c.get("along_m") or 0, c["collision_id"])):
        d = c.get("detail") or {}
        lorry_list.append({"mi": c.get("along_m"), "words": f"{du_words(c['along_m'])} {du}" if c.get("along_m") is not None else "",
                           "road": " / ".join(r for r in (c["road"], c["road2"]) if r) or "Road not recorded",
                           "junction": c["junction"], "severity": SEVERITY[c["severity"]], "year": c["year"],
                           "goods_words": ", ".join(GOODS_WORDS[g] for g in d.get("goods_types") or []) if details else None,
                           "artic": bool(d.get("goods_artic")), "left": bool(d.get("goods_left")), "work": bool(d.get("goods_work")),
                           "vru_words": [VRU_LABEL[k] for k in c["vru"]], "collision_id": c["collision_id"]})
    st = status()
    factors = conversions.load_factors()
    notice = export._demo_notice() or None
    # 28 Oct 2026 (0d): by time of day — each road route's weekday hours on the route, the busy bands, the hours the
    # route's lorries can be on the road (its gates) and the scheme's no-delivery bands; an alternative offered only
    # where the gap is clear (busy_offers). Offered, never switched.
    import gate_hours
    span = gate_span(r, factors)
    offers = busy_offers(hours_cols) if hours_known_ else []
    def km_of(alt):
        g = ((geo.get(alt) or {}).get(used) or {}).get("loaded")
        return float(g["distance_km"]) if g and g.get("distance_km") is not None else None
    _word_offers(offers, st["period"], km_of)
    time_of_day = {
        "shown": hours_known_, "bands": [{"from": a, "to": b} for a, b in BUSY_BANDS],
        "midday": {"from": MIDDAY[0], "to": MIDDAY[1]},
        "columns": [{"label": lab, "alt": alt, **hc} for lab, alt, hc in hours_cols] if hours_known_ else [],
        "gates": {"from": gate_hours._hhmm(span[0]), "to": gate_hours._hhmm(span[1] % (24 * 60)) if span[1] < 24 * 60 else "24:00"} if span else None,
        "no_delivery": gate_hours.peak_bands(factors),
        "offers": offers, "offer_min": OFFER_MIN,
    }
    as_at = now or date.today()
    return {
        "route_id": route_id, "title": SHEET_NAME, "tenant": export._tenant_name() or "Wayscope",
        "demo_notice": notice, "map_demo_tag": bulletin_doc.DEMO_MAP_TAG if notice else None,
        "origin": (locs.get(r["origin_id"]) or {}).get("name") or r["origin_id"],
        "dest": (locs.get(r["dest_id"]) or {}).get("name") or r["dest_id"],
        "vehicle_text": conversions.vehicle_label(factors, used) if used else None,
        "loaded": loaded, "return": ret, "drawn": bool(loaded),
        "years": st["years"], "period": st["period"], "fetched_at": st["fetched_at"], "fetched": bool(st["fetched_at"]),
        "columns": columns, "rows": rows, "details": details, "locations": locs_out,
        "headline": headline, "alt_lines": alt_lines, "cycle_lines": cl_lines, "cycle_shown": grid is not None,
        "turns": turns0, "cycle": {"beside": headline[0]["beside"] if headline else None,
                                   "meets": [{"m": m, "words": f"{du_words(m)} {du}", "name": n} for m, n in cyc0["meets"]]},
        "time_of_day": time_of_day,
        "lorry_list": lorry_list, "traffic_shown": bool(with_exp), "traffic_credit": traffic.SOURCE["attribution"] + "." if with_exp else None,
        "records": [c for c in prim_recs],
        "on": [c for _, c in on], "stretches": stretch_rows, "plan": plan, "plan_error": plan_error,
        "length_m": length_m, "inset_window": window, "inset_line": inset_line, "unit": du,
        "on_route_m": ON_ROUTE_M, "near_route_m": NEAR_ROUTE_M, "cluster_m": CLUSTER_M,
        "caveat": CAVEAT, "not_a_verdict": NOT_A_VERDICT, "credit": credit_line(),
        "issued": f"{as_at:%d %b %Y}".lstrip("0"),
        # 22 Oct 2026 (v3): the schools, health, bus stops and cycle routes on the sheet come from the community layer
        "community_credit": (community.credit_line() if (feats or cl_lines) else None),
    }


def file_name(S, ext="pdf"):
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(S["route_id"]))
    return f"route-collision-evidence-{safe}.{ext}"

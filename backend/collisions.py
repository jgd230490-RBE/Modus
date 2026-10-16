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
site. Stored alternatives (alt_index 1-2) are in it too, so a route's alternatives can be set side by side. Every kept
collision carries its distance to each route it is near; "on the route" is within ON_ROUTE_M (25 m: the 2025 data
flattens after 20 m, and 25 m allows for a dual carriageway).

WHO SEES IT (R6)
----------------
Staff only. The public map and the bulletin never show it. A collision is stored with its year and month, never its day
or time.
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
    drawn twice kept once per key) and every site with a position."""
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
            "dist_m": min(list(routes.values()) + list(sites.values())),
            "routes": routes, "sites": sites,
        }
    return out


def read_vehicles(path, keep):
    """Marks the kept collisions that involved a goods vehicle over 3.5 t."""
    for r in _rows(path):
        c = keep.get(r.get("collision_index"))
        if c is not None and str(r.get("vehicle_type") or "").strip() in GOODS_TYPES:
            c["goods"] = True


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
         "dist_m", "routes_json", "sites_json", "fetched_at")


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
                     json.dumps(c["sites"], separators=(",", ":")), fetched_at))
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
    for k, dflt in (("vru_json", []), ("vru_ksi_json", []), ("routes_json", {}), ("sites_json", {})):
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
        det["notes"].append("No route has a stored road route yet, so only the sites were searched round.")
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
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    now = _now()
    replace_all(recs, now)
    det.update({"years": years, "files": files, "error": None})
    if back:
        det["notes"].append(f"The {last} data is not published yet; the latest five final years are {period_words(years)}.")
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
    ("junction", "At or within 20 m of a junction"),
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
        if key == "junction":
            return bool(c["junction"])
        return False
    return sum(1 for c in recs if hit(c))


def counts_for(recs, key):
    """The table's two columns for one route key: on the route (within ON_ROUTE_M) and within NEAR_ROUTE_M."""
    near = [c for c in recs if key in c["routes"]]
    on = [c for c in near if c["routes"][key] <= ON_ROUTE_M]
    return {"on": {k: _count(on, k) for k, _ in ROWS}, "near": {k: _count(near, k) for k, _ in ROWS}}


def _chainage(index, line, p):
    """Metres along `line` (from its first vertex) to the point on it nearest `p`."""
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
    return at


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


def nearby_community(lon, lat, index, limit=4, within_m=NEAR_ROUTE_M):
    """The community considerations within `within_m` of a point: the NEAREST of each kind (points only), nearest kind
    first, at most `limit` kinds — 'Schools: Langham Primary 120 m'."""
    import community
    best = {}
    for f in community.features():
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


class EvidenceError(LookupError):
    """No such route (for this tenant, or for this team code)."""


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
    rows = db.query("SELECT * FROM routes WHERE tenant_id = ? AND id = ?", (tenant, route_id))
    if not rows:
        raise EvidenceError(f"no route {route_id}")
    r = rows[0]
    own = (acc or {}).get("ipt") if isinstance(acc, dict) else None
    if own:
        import access
        if (access.canonical_ipt(r.get("ipt")) or r.get("ipt")) != (access.canonical_ipt(own) or own):
            raise EvidenceError(f"no route {route_id}")
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
    columns = []
    for alt, key in keys:
        columns.append({"key": key, "alt": alt, "label": "This route" if not alt else f"Alternative {alt}",
                        "length": length_words(alt), **counts_for(recs, key)})
    prim_recs = [c for c in recs if route_key(route_id) in c["routes"]]
    locs_out = locations(prim_recs, index, loaded)
    for L in locs_out:
        L["community"] = nearby_community(L["lon"], L["lat"], index)
        if L["along_m"] is not None:
            L["along_words"] = f"{export._dist(L['along_m'] / 1000):.1f} {du} from A"
    st = status()
    factors = conversions.load_factors()
    notice = export._demo_notice() or None
    as_at = now or date.today()
    return {
        "route_id": route_id, "title": SHEET_NAME, "tenant": export._tenant_name() or "Wayscope",
        "demo_notice": notice, "map_demo_tag": bulletin_doc.DEMO_MAP_TAG if notice else None,
        "origin": (locs.get(r["origin_id"]) or {}).get("name") or r["origin_id"],
        "dest": (locs.get(r["dest_id"]) or {}).get("name") or r["dest_id"],
        "vehicle_text": conversions.vehicle_label(factors, used) if used else None,
        "loaded": loaded, "return": ret, "drawn": bool(loaded),
        "years": st["years"], "period": st["period"], "fetched_at": st["fetched_at"], "fetched": bool(st["fetched_at"]),
        "columns": columns, "rows": ROWS, "locations": locs_out,
        "records": [c for c in prim_recs],
        "on_route_m": ON_ROUTE_M, "near_route_m": NEAR_ROUTE_M, "cluster_m": CLUSTER_M,
        "caveat": CAVEAT, "not_a_verdict": NOT_A_VERDICT, "credit": credit_line(),
        "issued": f"{as_at:%d %b %Y}".lstrip("0"),
        "community_credit": None,
    }


def file_name(S, ext="pdf"):
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(S["route_id"]))
    return f"route-collision-evidence-{safe}.{ext}"

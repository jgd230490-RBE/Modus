"""
traffic.py — DfT's traffic counts along the routes, and "expected for roads like these". Wayscope, 22 Oct 2026.

WHY THIS EXISTS
---------------
The user, on the Route collision evidence: "I can see all the collisions clearly but don't have anything to compare it
to." Counts alone cannot be compared: a busy A road always has more collisions than a quiet one. The comparison highway
engineers use is observed beside expected — the collisions a stretch had beside what a typical GB road of the same type
would see with the same traffic. This reverses decision R5 (no rates) for this one comparison, at the user's word on
the v3 mockup (notes, collision-evidence-v3-mockup-1022; research: traffic-findings.md beside it). It is shown as a
count and a range, never a ratio, a score or a verdict: "within / below / above the range a typical road would show".

THE DATA (checked 22 Oct 2026)
------------------------------
* DfT road traffic statistics, annual average daily flow (AADF) by count point, per local authority:
  https://storage.googleapis.com/dft-statistics/road-traffic/downloads/aadf/local_authority_id/dft_aadf_local_authority_id_<id>.csv
  (the bucket behind roadtraffic.dft.gov.uk, which answered 503 all day), DfT's ids from
  .../downloads/data-gov-uk/local_authority_traffic.csv (local_authority_code = the ONS code). Open Government Licence
  v3.0 (data.gov.uk, "GB road traffic counts"). Every major-road link has a count point; minor roads only a sample with
  no link length, so a B road usually has no figure.
* The rates: Reported road casualties Great Britain 2025, table RAS0302 (published 30 Jul 2026): reported injury
  collisions, and fatal or serious collisions (severity adjusted), per billion vehicle miles including pedal cycles, by
  road type (motorway; urban / rural A roads; urban / rural other roads), 2021-2025. Typed in below with the URL; a new
  year is added when DfT publishes it (late July / September).

THE METHOD
----------
For each stretch: the count points within MATCH_M of the stretch's own road route (± REACH_M past its ends) on the same
road; each year, their AADF (all motor vehicles + pedal cycles, the rate's denominator) weighted by link length ×
365 × the stretch's length = vehicle miles; × that year's rate for the stretch's road type = expected collisions that
year; summed over the collision years. Urban or rural: DfT's own flag on the stretch's collisions (the rates use the
same ONS classification), the majority. The range is where a typical road's count would fall 95 times in 100 (Poisson).
"""
import csv
import math
import os

import db

LA_LIST_URL = "https://storage.googleapis.com/dft-statistics/road-traffic/downloads/data-gov-uk/local_authority_traffic.csv"
AADF_URL = "https://storage.googleapis.com/dft-statistics/road-traffic/downloads/aadf/local_authority_id/dft_aadf_local_authority_id_{id}.csv"
SOURCE = {"name": "DfT road traffic statistics (AADF)", "licence": "OGL v3.0",
          "url": "https://roadtraffic.dft.gov.uk/downloads",
          "attribution": "Contains public sector information licensed under the Open Government Licence v3.0 "
                         "(DfT road traffic statistics; DfT Reported road casualties GB, table RAS0302)"}
RATES_URL = "https://www.gov.uk/government/statistical-data-sets/reported-road-accidents-vehicles-and-casualties-tables-for-great-britain"
MATCH_M = 150             # a count point counts for a stretch within this of its road route...
REACH_M = 400             # ...and up to this past either end (a point sits mid-link; the link can start before the stretch)
KEEP_M = 250              # the fetch keeps count points within this of any route (the collision strip)
MI = 1609.344

# RAS0302 (Collision_rates sheet), per billion vehicle miles incl. pedal cycles, GB. "all" = reported injury collisions;
# "fsc" = fatal or serious collisions, severity adjusted. Typed in 22 Oct 2026 from the 2025 edition.
RATES = {
    "motorway":    {"all": {2021: 56.2, 2022: 50.3, 2023: 48.1, 2024: 46.4, 2025: 45.2},
                    "fsc": {2021: 11.7, 2022: 11.3, 2023: 10.8, 2024: 10.7, 2025: 10.8}},
    "urban_a":     {"all": {2021: 682.4, 2022: 655.6, 2023: 625.6, 2024: 580.1, 2025: 566.5},
                    "fsc": {2021: 136.2, 2022: 138.3, 2023: 134.8, 2024: 129.6, 2025: 131.8}},
    "rural_a":     {"all": {2021: 177.2, 2022: 170.1, 2023: 163.4, 2024: 158.7, 2025: 155.1},
                    "fsc": {2021: 53.6, 2022: 54.1, 2023: 51.7, 2024: 50.9, 2025: 50.4}},
    "urban_other": {"all": {2021: 602.8, 2022: 600.1, 2023: 583.2, 2024: 554.3, 2025: 552.1},
                    "fsc": {2021: 131.1, 2022: 134.8, 2023: 133.7, 2024: 133.6, 2025: 138.3}},
    "rural_other": {"all": {2021: 298.7, 2022: 306.7, 2023: 302.4, 2024: 296.1, 2025: 303.2},
                    "fsc": {2021: 94.6, 2022: 95.6, 2023: 95.1, 2024: 93.8, 2025: 97.3}},
}
CLASS_WORDS = {"motorway": "motorways", "urban_a": "urban A roads", "rural_a": "rural A roads",
               "urban_other": "urban B, C and unclassified roads", "rural_other": "rural B, C and unclassified roads"}
_COLS = ("count_point_id", "year", "road_name", "road_type", "lon", "lat", "link_km", "aadf_all", "aadf_cycles",
         "aadf_hgvs", "method", "authority", "fetched_at")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def authority_ids(la_csv_path, ons_codes):
    """{ons code: DfT local_authority_id} for the ONS codes asked, from DfT's local authority list."""
    out = {}
    with open(la_csv_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            code = (r.get("local_authority_code") or "").strip()
            if code in ons_codes and r.get("local_authority_id"):
                out[code] = str(r["local_authority_id"]).strip()
    return out


def read_aadf(path, index, years, keep_m=KEEP_M):
    """The count points of one AADF file within keep_m of a route (major roads only: a minor road's sample point has no
    link length), for the years asked, as row dicts."""
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                y = int(r.get("year") or 0)
            except ValueError:
                continue
            if y not in years or (r.get("road_type") or "").strip() != "Major":
                continue
            lon, lat, km = _num(r.get("longitude")), _num(r.get("latitude")), _num(r.get("link_length_km"))
            if lon is None or lat is None or not km or not index.in_box(lon, lat):
                continue
            routes, _ = index.near(lon, lat)
            if not routes or min(routes.values()) > keep_m:
                continue
            out.append({"count_point_id": str(r["count_point_id"]).strip(), "year": y,
                        "road_name": (r.get("road_name") or "").strip(), "road_type": "Major",
                        "lon": round(lon, 6), "lat": round(lat, 6), "link_km": km,
                        "aadf_all": _num(r.get("all_motor_vehicles")), "aadf_cycles": _num(r.get("pedal_cycles")) or 0.0,
                        "aadf_hgvs": _num(r.get("all_hgvs")), "method": (r.get("estimation_method") or "").strip(),
                        "authority": None})
    return out


def fetch(index, years, ons_codes, workdir, download):
    """Every count point along the routes for the years asked: DfT's local authority list, then one AADF file per
    authority the collisions name. Returns (rows, files in words, authorities whose file could not be read). An
    authority's file that fails is skipped and named; the list failing, or every file failing, raises RuntimeError."""
    la_path = os.path.join(workdir, "local_authority_traffic.csv")
    download(LA_LIST_URL, la_path)
    ids = authority_ids(la_path, set(ons_codes))
    rows, files, missing = [], [], []
    for code, la in sorted(ids.items()):
        p = os.path.join(workdir, f"aadf-{la}.csv")
        try:
            _, n = download(AADF_URL.format(id=la), p)
        except Exception:               # noqa: BLE001 — one authority's file; the others still count
            missing.append(code)
            continue
        got = read_aadf(p, index, set(years))
        for r in got:
            r["authority"] = code
        rows.extend(got)
        files.append(f"traffic counts {code} ({round(n / 1e6, 1)} MB)")
        try:
            os.remove(p)
        except OSError:
            pass
    if ids and len(missing) == len(ids):
        raise RuntimeError("no traffic count file could be read")
    return rows, files, missing


def replace_all(rows, fetched_at):
    tenant = db.current_tenant()
    vals = [(tenant,) + tuple(r.get(c) for c in _COLS[:-1]) + (fetched_at,) for r in rows]
    db.execute_atomic([
        ("DELETE FROM traffic_counts WHERE tenant_id = ?", (tenant,)),
        ("INSERT INTO traffic_counts (tenant_id, " + ", ".join(_COLS) + ") VALUES (" + ", ".join("?" * (len(_COLS) + 1)) + ")",
         vals, True),
    ])
    return len(vals)


def stored():
    return [dict(r) for r in db.query("SELECT * FROM traffic_counts WHERE tenant_id = ? ORDER BY year, count_point_id",
                                      (db.current_tenant(),))]


# --------------------------------------------------------------------------- #
#  Expected for roads like these                                               #
# --------------------------------------------------------------------------- #
def road_class(road, urban):
    """The RAS0302 road type for a stretch's road and DfT's urban (1) / rural (2) flag; None when it cannot be said."""
    if not road:
        return None
    if road.startswith("M") or road.endswith("(M)"):
        return "motorway"
    if urban not in (1, 2):
        return None
    kind = "a" if road.startswith("A") else "other"
    return ("urban_" if urban == 1 else "rural_") + kind


def urban_of(recs):
    """DfT's urban (1) / rural (2) flag of most of these collisions; None with no flag or a tie."""
    n1 = sum(1 for c in recs if (c.get("detail") or {}).get("urban") == 1)
    n2 = sum(1 for c in recs if (c.get("detail") or {}).get("urban") == 2)
    return 1 if n1 > n2 else (2 if n2 > n1 else None)


def _pois_cdf(k, mu):
    if k < 0:
        return 0.0
    term = math.exp(-mu)
    s = term
    for i in range(1, k + 1):
        term *= mu / i
        s += term
    return s


def poisson_range(mu, p=0.025):
    """(lowest, highest) count a typical road with `mu` expected would show 95 times in 100."""
    if mu <= 0:
        return 0, 0
    lo = next(k for k in range(10000) if _pois_cdf(k, mu) >= p)
    hi = next(k for k in range(10000) if _pois_cdf(k, mu) >= 1 - p)
    return lo, hi


def expected_for(index, line, a_m, b_m, road, urban, years, rows):
    """
    Expected collisions on [a_m, b_m] metres of `line`: {'expected', 'range', 'expected_fsc', 'range_fsc', 'class',
    'class_words', 'aadf' (lowest, highest of the latest year), 'counted' (years with a count, not an estimate),
    'points'} — or {'why': words} when it cannot be worked out.
    """
    import collisions as cl
    if not road or (not road.startswith(("A", "B", "M")) and not road.endswith("(M)")):
        return {"why": "no numbered road"}
    cls = road_class(road, urban)
    if cls is None:
        return {"why": "urban or rural not known"}
    mine = []
    for r in rows:
        if (r.get("road_name") or "") != road:
            continue
        d, m = cl._project(index, line, (r["lon"], r["lat"]))
        if d <= MATCH_M and a_m - REACH_M <= m <= b_m + REACH_M:
            mine.append(r)
    if not mine:
        return {"why": "no traffic count on this road"}
    miles = (b_m - a_m) / MI
    exp_all = exp_fsc = 0.0
    used, counted, aadf_last = [], set(), []
    for y in sorted(years):
        ry = [r for r in mine if r["year"] == y and r.get("aadf_all") is not None]
        rate_all, rate_fsc = RATES[cls]["all"].get(y), RATES[cls]["fsc"].get(y)
        if not ry or rate_all is None:
            return {"why": f"no traffic count or rate for {y}"}
        den = sum(r["link_km"] for r in ry)
        aadf = sum(r["link_km"] * (r["aadf_all"] + (r.get("aadf_cycles") or 0.0)) for r in ry) / den
        bvm = aadf * 365 * miles / 1e9
        exp_all += bvm * rate_all
        exp_fsc += bvm * rate_fsc
        used.extend(r["count_point_id"] for r in ry)
        counted.update(y for r in ry if r.get("method") == "Counted")
        if y == max(years):
            aadf_last = [r["aadf_all"] for r in ry]
    return {"expected": exp_all, "range": poisson_range(exp_all), "expected_fsc": exp_fsc, "range_fsc": poisson_range(exp_fsc),
            "class": cls, "class_words": CLASS_WORDS[cls], "aadf": (min(aadf_last), max(aadf_last)) if aadf_last else None,
            "counted": sorted(counted), "points": sorted(set(used))}


def reading(observed, rng):
    """Where an observed count sits against the range a typical road would show — words only, never a verdict."""
    lo, hi = rng
    if observed < lo:
        return "below the range"
    if observed > hi:
        return "above the range"
    return "within the range"


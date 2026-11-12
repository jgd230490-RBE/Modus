"""
smoke_public_map_kept.py — the REAL app: the public map's three heavy reads are kept once built (12 Nov 2026, card A-F7 (a)
on John's page "Everything left", BUILD.md rule 13; branch claude/map-cold-open).

    pip install -r backend/requirements.txt httpx      # .venv-smoke, or CI
    python backend/tests/smoke_public_map_kept.py

On 11 Nov the public map took 15.7-19.5 s from a new tab before a month could be picked. Counted on a local copy, its cold
open makes ~430 database connections, ~315 of them in three reads every visitor rebuilt: /api/public/map-data (48),
/api/public/forecast-matrix (126) and /api/public/month-kpis/months (141). On live, with the Postgres pool empty, each is a
fresh connection (PR #263). This boots `main.app` on a scratch SQLite database, imports the demo package and checks:

  * each of the three is built once and then served kept, the SAME bytes, until a write moves the data version;
  * the kept body is exactly what the read built (the JSON FastAPI would have sent);
  * only the map's own shapes are kept (the whole horizon, no profile); another window or a profile is built each time;
  * units are kept apart (vehicles and m3 are two entries);
  * a second open of the three makes NO database connection (counted on db.get_conn);
  * a warmer builds all three, so the first visitor after an edit does not;
  * still behind the map gate: no cookie answers 401 and builds nothing; a bad unit is still a 400.

NOT covered: PostgreSQL, live timings (after the merge, read only), the heavy-slot 503 under load (heavy_reads' own harness).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient
    from fastapi.encoders import jsonable_encoder
    import httpx  # noqa: F401
except Exception as e:  # the stubbed sandbox
    print(f"smoke_public_map_kept.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_pmkept_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "MAP_GATE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE"):
    os.environ.pop(v, None)
os.environ.update({"PLANNER_CODE": "plan-code-xyz", "ADMIN_CODE": "admin-code-xyz", "IPT1_CODE": "north-code-xyz",
                   "MAP_PASSWORD": "map-pass-xyz", "GATE_SECRET": "gate-secret-for-tests-only", "WAYSCOPE_WARM_CACHE": "0"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "pmkept.db")
import main  # noqa: E402
import network  # noqa: E402
import read_cache  # noqa: E402
import tenant_package  # noqa: E402
from portable import pin_today, DEMO_AS_OF  # noqa: E402
_PINNED = pin_today(DEMO_AS_OF)

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  ok  ", label)
    else:
        FAIL.append(f"{label} {extra}".strip())
        print("  FAIL", label, extra)


# count the builds of each read, and the database connections
BUILDS = {"map": 0, "matrix": 0, "months": 0}
_pmd, _fm, _mk = network.public_map_data, main._forecast_matrix, main._month_kpis_payloads


def _count(key, fn):
    def wrapped(*a, **k):
        BUILDS[key] += 1
        return fn(*a, **k)
    return wrapped


network.public_map_data = _count("map", _pmd)
main._forecast_matrix = _count("matrix", _fm)
main._month_kpis_payloads = _count("months", _mk)
CONNS = [0]
_gc = db.get_conn


def _counting_conn(*a, **k):
    CONNS[0] += 1
    return _gc(*a, **k)


db.get_conn = _counting_conn

MAP = "/api/public/map-data"
MATRIX = "/api/public/forecast-matrix?from=1&to=60&unit=vehicles&sections=1"
MONTHS = "/api/public/month-kpis/months?unit=vehicles"
THREE = (("map", MAP), ("matrix", MATRIX), ("months", MONTHS))


def opened(c, path):
    before = dict(BUILDS)
    r = c.get(path)
    return r, {k: BUILDS[k] - before[k] for k in BUILDS}


with TestClient(main.app, base_url="https://testserver") as c:
    pkg = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
    ok("the demo package imports", bool(tenant_package.import_tenant(pkg).get("ok")))
    read_cache.clear()

    r0, b0 = opened(c, MAP)
    ok("🔴 still behind the map gate: no cookie answers 401 and builds nothing", r0.status_code == 401 and not any(b0.values()),
       f"{r0.status_code} {b0}")
    ok("signed in to the map", c.post("/api/map-auth", json={"password": "map-pass-xyz"}).status_code == 200)

    first = {}
    for key, path in THREE:
        r1, b1 = opened(c, path)
        r2, b2 = opened(c, path)
        first[key] = r1.content
        ok(f"⭐ {key}: the first open builds it, the second is served kept (one build)",
           r1.status_code == 200 and r2.status_code == 200 and b1[key] == 1 and b2[key] == 0, f"{r1.status_code} {b1} {b2}")
        ok(f"...{key}: the kept answer is the same bytes, as JSON", r1.content == r2.content
           and r2.headers.get("content-type", "").startswith("application/json"))

    # the kept body is exactly what the read builds (FastAPI's own encoding of the builder's answer)
    want_map = read_cache.json_bytes(jsonable_encoder(_pmd(profile=None)))
    want_matrix = read_cache.json_bytes(jsonable_encoder(_fm(1, 60, "vehicles", 1)))
    pages = _mk(range(1, main.MONTH_COUNT + 1), "vehicles")
    want_months = read_cache.json_bytes(jsonable_encoder({"unit": "vehicles", "months": {str(m): pages[m] for m in sorted(pages)}}))
    ok("⭐ the kept bodies are exactly the reads' own answers (map-data, forecast-matrix, month-kpis/months)",
       first["map"] == want_map and first["matrix"] == want_matrix and first["months"] == want_months,
       f"{len(first['map'])}/{len(want_map)} {len(first['matrix'])}/{len(want_matrix)} {len(first['months'])}/{len(want_months)}")
    ok("...and they carry what the map reads (features; routes with co2_t and section_co2_max; sixty months)",
       len(json.loads(first["map"]).get("features") or []) > 0 and "section_co2_max" in json.loads(first["matrix"])
       and len(json.loads(first["matrix"])["routes"]) > 0 and len(json.loads(first["months"])["months"]) == main.MONTH_COUNT)

    CONNS[0] = 0
    for _, path in THREE:
        c.get(path)
    ok("⭐ a second open of the three makes NO database connection (it made ~315 on the local copy)", CONNS[0] == 0, str(CONNS[0]))

    db.bump_data_version()
    for key, path in THREE:
        r3, b3 = opened(c, path)
        ok(f"⭐ a write in between: {key} is built afresh (never an older plan)", r3.status_code == 200 and b3[key] == 1, str(b3))

    w1 = opened(c, "/api/public/forecast-matrix?from=3&to=5&unit=vehicles")[1]
    w2 = opened(c, "/api/public/forecast-matrix?from=3&to=5&unit=vehicles")[1]
    ok("another window of the matrix is built each time (only the map's whole horizon is kept)", w1["matrix"] == 1 and w2["matrix"] == 1,
       f"{w1} {w2}")
    p1 = opened(c, MAP + "?profile=Artic")[1]
    p2 = opened(c, MAP + "?profile=Artic")[1]
    ok("a map-data with a profile is built each time", p1["map"] == 1 and p2["map"] == 1, f"{p1} {p2}")
    u1 = opened(c, "/api/public/month-kpis/months?unit=m3")
    u2 = opened(c, "/api/public/month-kpis/months?unit=m3")
    u3 = opened(c, MONTHS)
    ok("units are kept apart: m3 built once and kept, vehicles still kept beside it",
       u1[0].status_code == 200 and u1[1]["months"] == 1 and u2[1]["months"] == 0 and u3[1]["months"] == 0
       and json.loads(u1[0].content)["unit"] == "m3", f"{u1[1]} {u2[1]} {u3[1]}")
    ok("🔴 a bad unit is still a 400 (and builds nothing)", c.get("/api/public/month-kpis/months?unit=bogus").status_code == 400
       and c.get("/api/public/forecast-matrix?unit=bogus").status_code == 400)

    db.bump_data_version()
    ok("the warmer is registered", "public_map" in read_cache.WARMERS)
    before = dict(BUILDS)
    read_cache.WARMERS["public_map"]()       # this warmer alone (the staff warmer reads map-data through other reads too)
    built = {k: BUILDS[k] - before[k] for k in BUILDS}
    # map-data's builder (network.public_map_data) is also called inside another read's build, so it may run twice
    ok("⭐ the warmer builds all three after an edit", built["matrix"] == 1 and built["months"] == 1 and built["map"] >= 1, str(built))
    db.bump_data_version()
    res = read_cache.warm(db.current_tenant())
    ok("...and runs in read_cache.warm() with the others, without an error", res.get("public_map") == "ok", str(res))
    after = {k: opened(c, p)[1][k] for k, p in THREE}
    ok("...so the next visitor's three reads are served kept", after == {"map": 0, "matrix": 0, "months": 0}, str(after))

print(f"{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)

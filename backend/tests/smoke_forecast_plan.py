"""
smoke_forecast_plan.py — the REAL app: the approved plan as a file is for staff. Wayscope, 12 Nov 2026
(claude/ui-map-forecast-detail-1111, option A2; John's call 7: Copy for everyone, Download for staff only at first).

    pip install -r backend/requirements.txt httpx      # .venv-smoke, or CI
    python backend/tests/smoke_forecast_plan.py

It boots `main.app` with FastAPI's TestClient on a scratch SQLite database and imports the demo package. Then
GET /api/routes/forecast-plan.csv:

    as nobody, and with the map password's cookie (the public map's visitor): 401, whatever the page shows;
    with a planner code and with a team code: 200, a CSV whose figures are the public map's own
    (/api/public/month-kpis/months: a route's loads over the working days, in the organisation's unit).

NOT covered: PostgreSQL (SQLite only), a browser (the button: ui_fix_map_all_routes.js and the Chrome check in the
session note). run_suite.py runs every backend/tests/smoke_*.py with --smoke-py.
"""
import csv
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
except Exception as e:  # the stubbed sandbox
    print(f"smoke_forecast_plan.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_fplan_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY", "MAP_GATE", "SMTP_USER", "SMTP_PASSWORD", "DEMO_LEADS",
          "OS_MAPS_KEY", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE"):
    os.environ.pop(v, None)
os.environ.update({
    "ADMIN_TOKEN": "adm-token-fplan",
    "PLANNER_CODE": "plan-code-fplan",
    "IPT1_CODE": "north-code-fplan",
    "MAP_PASSWORD": "map-pass-fplan",
    "GATE_SECRET": "gate-secret-for-tests-only",
    "WAYSCOPE_WARM_CACHE": "0",
})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "fplan.db")
import main  # noqa: E402
sys.path.insert(0, HERE)
from portable import pin_today, DEMO_AS_OF, remove_scratch_db  # noqa: E402
_PINNED = pin_today(DEMO_AS_OF)

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


TOKEN = {"token": "adm-token-fplan"}
PLAN = {"X-Access-Code": "plan-code-fplan"}
TEAM = {"X-Access-Code": "north-code-fplan"}
DEMO = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
BASE = "https://testserver"
URL = "/api/routes/forecast-plan.csv"

with TestClient(main.app, base_url=BASE) as admin:
    r = admin.post("/api/admin/tenant/import", params=TOKEN, json=DEMO)
    ok("0. the demo package imports", r.status_code == 200, r.text[:200])

    nobody = TestClient(main.app, base_url=BASE, raise_server_exceptions=False)
    r = nobody.get(URL)
    ok("1. ⭐ as nobody: 401", r.status_code == 401, f"{r.status_code} {r.text[:120]}")
    visitor = TestClient(main.app, base_url=BASE, raise_server_exceptions=False)
    r = visitor.post("/api/map-auth", json={"password": "map-pass-fplan"})
    ok("1. the map password opens the map (a visitor's cookie)", r.status_code == 200 and r.json().get("ok") is True, r.text[:120])
    r = visitor.get("/api/public/month-kpis/months", params={"unit": "vehicles"})
    ok("1. ...and the visitor reads the map's month figures (the same plan, on the screen)", r.status_code == 200 and len(r.json().get("months", {})) > 0,
       str(r.status_code))
    MONTHS = r.json().get("months", {}) if r.status_code == 200 else {}
    r = visitor.get(URL)
    ok("1. ⭐ the map password's visitor is REFUSED the file: 401, and no CSV in the answer", r.status_code == 401 and "Route,From" not in r.text,
       f"{r.status_code} {r.text[:120]}")
    r = visitor.get(URL, params={"unit": "t"})
    ok("1. ⭐ ...in tonnes too", r.status_code == 401, str(r.status_code))

    r = admin.get(URL, headers=PLAN)
    ok("2. ⭐ a planner gets the file: 200, text/csv, an attachment named for what it holds, not kept by a browser",
       r.status_code == 200 and r.headers.get("content-type", "").startswith("text/csv")
       and 'filename="approved-plan-movements-a-day.csv"' in r.headers.get("content-disposition", "")
       and r.headers.get("cache-control") == "no-store", f"{r.status_code} {dict(r.headers)}"[:300])
    body = list(csv.reader(io.StringIO(r.content.decode("utf-8").lstrip("﻿")))) if r.status_code == 200 else [[]]
    head = body[0]
    ok("2. the heading row: Route, From, To, Material, the programme's 60 months, Busiest",
       head[:4] == ["Route", "From", "To", "Material"] and head[4] == "Jan 2026" and head[-2] == "Dec 2030" and head[-1] == "Busiest"
       and len(head) == 65, str(head[:6]))

    # the map's own figures for the same plan: a route's loads over the month's working days, x the organisation's count
    def screen(rid, m):
        kp = MONTHS.get(str(m)) or {}
        loads = sum(float(l.get("vehicle_loads") or 0) for l in kp.get("lines", []) if l.get("route_id") == rid)
        wd = float(kp.get("working_days") or 0)
        x = (loads / wd if wd > 0 else 0) * 2
        return "" if not loads else ("under 1" if 0 < x < 1 else f"{int(x + 0.5):,}")

    rows = {r_[0]: r_ for r_ in body[1:-1]}
    routes_on_map = sorted({l["route_id"] for kp in MONTHS.values() for l in kp.get("lines", []) if float(l.get("qty_t") or 0) > 0})
    ok("2. ⭐ a row for every route the map's plan carries, and a totals row that says how many",
       sorted(rows) == routes_on_map and len(routes_on_map) > 5 and body[-1][0] == f"All {len(routes_on_map)} routes",
       f"{len(rows)} rows, {len(routes_on_map)} on the map, last {body[-1][:1]}")
    diff = [(rid, m, rows[rid][3 + m], screen(rid, m)) for rid in rows for m in range(1, 61) if rows[rid][3 + m] != screen(rid, m)]
    ok("2. ⭐ EVERY cell of the file is the map's own figure for that route and month (movements a day, whole, 'under 1' below one)",
       not diff and len(rows) > 5, str(diff[:3]))
    named = [rid for rid in rows if rows[rid][1] and rows[rid][2] and rows[rid][3]]
    ok("2. every row names where the route runs from and to, and its material in words", len(named) == len(rows), f"{len(named)} of {len(rows)}")

    r = admin.get(URL, params={"unit": "t"}, headers=PLAN)
    tb = list(csv.reader(io.StringIO(r.content.decode("utf-8").lstrip("﻿")))) if r.status_code == 200 else [[]]
    tonnes = sum(float(l.get("qty_t") or 0) for kp in MONTHS.values() for l in kp.get("lines", []))
    ok("3. ⭐ in tonnes: the last column is Total, and the totals row's total is the map's whole plan",
       r.status_code == 200 and tb[0][-1] == "Total" and 'filename="approved-plan-tonnes.csv"' in r.headers.get("content-disposition", "")
       and tb[-1][-1] == f"{int(tonnes + 0.5):,}", f"{tb[-1][-1:]} vs {tonnes}")
    r = admin.get(URL, params={"unit": "vehicles"}, headers=PLAN)
    ok("3. an unknown unit is a 400", r.status_code == 400, str(r.status_code))
    r = admin.get(URL, headers=TEAM)
    ok("3. a team code gets the whole plan too (the map shows every route to anyone it lets in)",
       r.status_code == 200 and len(list(csv.reader(io.StringIO(r.content.decode("utf-8"))))) == len(body), str(r.status_code))

try:
    remove_scratch_db(db, TMP)
except Exception:
    pass
for f in FAIL:
    print("  FAIL:", f)
print(f"smoke_forecast_plan.py: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

"""
http_smoke.py — the REAL HTTP layer, end to end. Wayscope (G2, 16 Sep 2026; rebrand 29 Sep).

    pip install -r backend/requirements.txt httpx      # a venv, or CI
    python3 backend/tests/http_smoke.py

Every other harness stubs FastAPI and calls endpoint bodies directly, so none of them
proves that a route is registered, that a query parameter or a JSON body reaches the
function, that the gate middleware reads the cookie it set, or that a Response comes
back with the headers the browser needs. This one boots `main.app` with FastAPI's
TestClient (lifespan and middleware included) against a scratch SQLite database and
drives it the way the browser and an admin would:

    gate → sign-in → empty tenant → import the demo package → read it back through
    /api/meta, the map overlay, the Look-ahead and both exports → export the tenant →
    refuse bad input.

When FastAPI is not installed (the stubbed harnesses' environment) it prints SKIPPED
and exits 0 with "0 passed, 0 failed", so the suite runner stays green there.

NOT covered: PostgreSQL (SQLite only), HERE (no key — routes stay UNBAKED), Mapbox
(the PDF falls back to its schematic map when the static-map service is unreachable),
and any browser rendering.
"""
import json
import os
import re
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
    print(f"http_smoke.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

# --- environment: a deployment with every secret set, no external keys -----------------
TMP = tempfile.mkdtemp(prefix="modus_http_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN",
          "MAPBOX_PUBLIC_TOKEN", "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY", "MAP_GATE",
          "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE"):
    os.environ.pop(v, None)
os.environ.update({
    "ADMIN_TOKEN": "adm-token-xyz",
    "PLANNER_CODE": "plan-code-xyz",
    "ADMIN_CODE": "admin-code-xyz",
    "IPT1_CODE": "north-code-xyz",
    "MAP_PASSWORD": "map-pass-xyz",
    "GATE_SECRET": "gate-secret-for-tests-only",
})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "http.db")
import main  # noqa: E402
import gate  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


TOKEN = {"token": "adm-token-xyz"}
PLAN = {"X-Access-Code": "plan-code-xyz"}
NORTH = {"X-Access-Code": "north-code-xyz"}
DEMO = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))

# https: the gate cookie is Secure (as it must be on Render), so a plain-http client would
# never send it back — which is also what a browser does.
with TestClient(main.app, base_url="https://testserver") as c:
    # ---------------------------------------------------------------- 1. boot + gate
    r = c.get("/api/health")
    ok("health answers 200 on SQLite", r.status_code == 200 and r.json().get("backend") == "sqlite", r.text[:120])
    r = c.get("/")
    ok("the app page is served, named Wayscope, with no-cache", r.status_code == 200 and "Wayscope" in r.text
       and r.headers.get("cache-control") == "no-cache", str(r.status_code))
    ok("...and its <head> carries the favicon links and the manifest",
       '<link rel="icon" href="/favicon.ico" sizes="32x32">' in r.text and '<link rel="manifest" href="/site.webmanifest">' in r.text
       and '<link rel="icon" href="/favicon.svg" type="image/svg+xml">' in r.text)
    # 29 Sep: the brand files are served without any cookie — a refused visitor sees the logo.
    for path, ctype in (("/favicon.ico", "image/x-icon"), ("/favicon.svg", "image/svg+xml"),
                        ("/site.webmanifest", "application/manifest+json"),
                        ("/apple-touch-icon.png", "image/png"), ("/icon-192.png", "image/png"),
                        ("/brand/logo-header-on-dark.svg", "image/svg+xml"),
                        ("/brand/logo-stacked-on-dark.svg", "image/svg+xml"),
                        ("/brand/theme-tokens.css", "text/css")):
        r = c.get(path)
        ok(f"{path} is served without a cookie, {ctype}, no-cache",
           r.status_code == 200 and r.headers.get("content-type", "").startswith(ctype)
           and r.headers.get("cache-control") == "no-cache" and len(r.content) > 0,
           f"{r.status_code} {r.headers.get('content-type')}")
    r = c.get("/favicon.svg")
    ok("the SVG favicon is a real SVG", r.status_code == 200 and b"<svg" in r.content[:400])
    r = c.get("/brand/../backend/factors.json")
    ok("🔴 the brand mount cannot be walked out of", r.status_code in (404, 400), str(r.status_code))
    r = c.get("/site.webmanifest")
    _man = r.json()
    ok("the manifest names Wayscope and its icons all answer 200 at the root",
       "Wayscope" in _man.get("name", "") and _man.get("icons")
       and all(c.get(i["src"]).status_code == 200 for i in _man["icons"]), str(_man.get("icons")))
    r = c.get("/map/")
    ok("🔴 the map is closed without a credential — the password page, 401",
       r.status_code == 401 and "password" in r.text.lower(), str(r.status_code))
    ok("...and the password page is branded: Wayscope title, the stacked logo, no RBE-era wording",
       "<title>Wayscope — map access</title>" in r.text and 'src="/brand/logo-stacked-on-dark.svg"' in r.text
       and "alliance" not in r.text.lower() and "Modus" not in r.text)
    # 11 Oct 2026 (the demo bar): the app's iframes ask for /map/?embed=1&v=…; the gate reads the path only
    r = c.get("/map/?embed=1&v=1")
    ok("🔴 the embedded map's address (/map/?embed=1) is closed the same way — the password page, 401",
       r.status_code == 401 and "<title>Wayscope — map access</title>" in r.text, str(r.status_code))
    r = c.get("/help/")
    ok("🔴 the guide is closed without a staff sign-in — 401", r.status_code == 401, str(r.status_code))
    r = c.get("/api/public/alignment")
    ok("🔴 the overlay API is gated like the map — 401 JSON", r.status_code == 401
       and r.headers.get("content-type", "").startswith("application/json"), str(r.status_code))

    r = c.get("/api/meta")
    m = r.json()
    ok("meta is readable before sign-in (the sign-in screen needs it)", r.status_code == 200)
    ok("a fresh tenant is EMPTY: no routes, teams or sections",
       m["routes"] == [] and m["ipts"] == [] and m["work_sections"] == [], str({k: len(m[k]) for k in ("routes", "ipts", "work_sections")}))
    ok("...and carries the default tenant words: Wayscope, Team, EUR, no country",
       m["tenant"]["name"] == "Wayscope" and m["tenant"]["team_label"] == "Team"
       and m["tenant"]["currency"] == "EUR" and m["tenant"]["country"] is None, str(m["tenant"]))

    r = c.post("/api/auth", json={"code": "wrong"})
    ok("a wrong access code is refused — 401", r.status_code == 401)
    r = c.post("/api/auth", json={"code": "submitter123"})
    ok("🔴 the old demo codes do not work when real codes are set", r.status_code == 401)
    r = c.post("/api/auth", json={"code": "plan-code-xyz"})
    ok("the planner code signs in", r.status_code == 200 and r.json()["role"] == "planner", r.text[:160])
    ok("...and the middleware sets the signed gate cookie", gate.COOKIE in r.cookies or gate.COOKIE in c.cookies,
       str(dict(r.headers)))
    ok("...and a planner is offered all six slots while the tenant names none",
       r.json().get("ipts") == ["IPT1", "IPT2", "IPT3", "IPT4", "IPT5", "IPT6"], str(r.json().get("ipts")))

    r = c.get("/map/")
    ok("with the staff cookie the map opens and loads the overlay module",
       r.status_code == 200 and "overlay.js" in r.text and "Wayscope" in r.text, str(r.status_code))
    _map_doc = r.text
    r = c.get("/map/?embed=1&v=1")
    ok("...and /map/?embed=1 (the app's iframe) is the same document, which reads the flag itself (11 Oct, the demo bar)",
       r.status_code == 200 and r.text == _map_doc and "get('embed') === '1'" in r.text, str(r.status_code))
    r = c.get("/map/overlay.js")
    ok("the overlay module is served", r.status_code == 200 and "applyOverlayPackage" in r.text)
    r = c.get("/map/data/alignment.js")
    ok("🔴 no static alignment file is served — 404", r.status_code == 404, str(r.status_code))
    r = c.get("/help/")
    ok("with the staff cookie the guide opens, as Wayscope", r.status_code == 200 and "Wayscope — User guide" in r.text,
       str(r.status_code))

    r = c.get("/api/public/alignment")
    b = r.json()
    ok("an empty tenant's overlay is {} plus its words and no teams",
       r.status_code == 200 and set(b) == {"tenant", "teams"} and b["teams"] == [], str(b)[:160])
    etag0 = r.headers.get("etag") or ""
    ok("the overlay carries an ETag", bool(etag0), str(dict(r.headers)))
    r = c.get("/api/public/alignment", headers={"If-None-Match": etag0})
    ok("⭐ a matching If-None-Match gets 304 with no body", r.status_code == 304 and not r.content, str(r.status_code))

    r = c.get("/api/restrictions/layers")
    ok("no country → no restriction provider, no layers", r.status_code == 200
       and r.json().get("provider") is None and r.json().get("layers") == [], r.text[:160])

    # ------------------------------------------------------------ 2. the tenant package
    r = c.get("/api/admin/tenant/status")
    ok("🔴 tenant status without the admin token — 403", r.status_code == 403, str(r.status_code))
    r = c.get("/api/admin/tenant/status", params=TOKEN)
    ok("tenant status with the token says EMPTY", r.status_code == 200 and r.json()["empty"] is True, r.text[:160])

    r = c.post("/api/admin/tenant/import", params=TOKEN, json={"modus_package": 99, "tables": {}})
    ok("a package of the wrong format is refused — 400 with the reason",
       r.status_code == 400 and "modus_package" in r.text, r.text[:160])
    r = c.post("/api/admin/tenant/import", json=DEMO)
    ok("🔴 import without the admin token — 403", r.status_code == 403, str(r.status_code))
    r = c.post("/api/admin/tenant/import", params=TOKEN, json=DEMO)
    res = r.json()
    ok("⭐ the demo package imports over HTTP", r.status_code == 200 and res.get("ok") is True, r.text[:200])
    # NARROWED 5 Oct 2026 (demo v2): 74 forecasts (72 approved + Pending + Rejected), 14 gates,
    # 5 zones, 6 haul-road links travel with the package too
    ok("...with every table's rows inserted",
       # NARROWED 11 Oct 2026 (carbon phase 4): + 2 routes, 4 forecasts, 18 weeks, 2 gates (the muck-away choice)
       res.get("inserted", {}).get("routes") == 20 and res["inserted"].get("forecasts") == 78
       and res["inserted"].get("forecast_weeks") == 342 and res["inserted"].get("location_gates") == 16
       and res["inserted"].get("zones") == 5 and res["inserted"].get("route_haul_roads") == 6, str(res.get("inserted")))
    ok("...and the GB diesel price applied", res.get("fuel_index_applied") == ["GB"], str(res.get("fuel_index_applied")))
    r = c.post("/api/admin/tenant/import", params=TOKEN, json=DEMO)
    ok("🔴 a second import into a non-empty tenant is refused — 400",
       r.status_code == 400 and "already holds data" in r.text, r.text[:160])

    # 11 Oct 2026 (the demo bar, review): with the demo tenant in, a visitor with no cookie. Inside the app (the
    # iframe's /map/?embed=1, sent as a frame) the bar above carries the notice, so the password page leaves its pill
    # out; /map/ on its own, and /map/?embed=1 typed into the tab (Sec-Fetch-Dest: document), keep it.
    _jar = c.cookies
    c.cookies = type(_jar)()
    try:
        r_emb = c.get("/map/?embed=1&v=1", headers={"Sec-Fetch-Dest": "iframe"})
        r_emb_nohdr = c.get("/map/?embed=1&v=1")
        r_alone = c.get("/map/")
        r_typed = c.get("/map/?embed=1&v=1", headers={"Sec-Fetch-Dest": "document"})
    finally:
        c.cookies = _jar
    ok("⭐ demo tenant, no cookie: the app's iframe (/map/?embed=1) gets the password page, 401, WITHOUT the notice pill (the bar has it)",
       r_emb.status_code == 401 and 'id="p" name="p" type="password"' in r_emb.text and 'class="demo-notice"' not in r_emb.text
       and r_emb_nohdr.status_code == 401 and 'class="demo-notice"' not in r_emb_nohdr.text, f"{r_emb.status_code} {r_emb_nohdr.status_code}")
    ok("⭐ .../map/ on its own gets the password page WITH the notice pill (no bar above it)",
       r_alone.status_code == 401 and '<div class="demo-notice">Fictional demo scheme · nothing here is real</div>' in r_alone.text,
       str(r_alone.status_code))
    ok("🔴 ...and /map/?embed=1 typed into the tab (a top-level page) keeps the pill too",
       r_typed.status_code == 401 and 'class="demo-notice"' in r_typed.text, str(r_typed.status_code))

    m = c.get("/api/meta").json()
    ok("meta now reads the demo tenant: its name, £, GB",
       m["tenant"]["name"].startswith("Wolds Link") and m["tenant"]["currency_symbol"] == "£"
       and m["tenant"]["country"] == "GB", str(m["tenant"]))
    ok("...three named teams, eight sections, twenty routes",
       [i["label"] for i in m["ipts"]] == ["North Team", "Central Team", "South Team"]
       and len(m["work_sections"]) == 8 and len(m["routes"]) == 20,
       str([i["label"] for i in m["ipts"]]))

    r = c.post("/api/auth", json={"code": "north-code-xyz"})
    ok("⭐ a team code signs in under the team's NAME", r.status_code == 200
       and r.json()["label"] == "North Team" and r.json()["ipt"] == "IPT1", r.text[:160])
    ok("...and the planner picker offers the tenant's three slots, not six",
       c.post("/api/auth", json={"code": "plan-code-xyz"}).json().get("ipts") == ["IPT1", "IPT2", "IPT3"])

    r = c.get("/api/public/alignment")
    b = r.json()
    ok("⭐ the map overlay arrives: version, six bands, five boundaries, the view",
       b.get("version") == "wolds-link-demo-2" and len(b.get("bands", [])) == 6
       and len(b.get("boundaries", [])) == 5 and b.get("view", {}).get("zoom"), str(list(b))[:160])
    ok("...with the team names the map shows",
       {t["id"]: t["label"] for t in b["teams"]} == {"IPT1": "North Team", "IPT2": "Central Team", "IPT3": "South Team"},
       str(b.get("teams")))
    ok("...and a NEW ETag, so a browser holding the empty overlay refetches", r.headers.get("etag") != etag0)

    bad = json.loads(json.dumps({k: v for k, v in b.items() if k not in ("tenant", "teams")}))
    bad["bands"][-1]["chain_to"] = 1
    r = c.put("/api/admin/overlay", params=TOKEN, json=bad)
    ok("🔴 a backwards band is refused over HTTP — 400 naming it", r.status_code == 400 and "runs backwards" in r.text,
       r.text[:160])
    bad["bands"][-1]["chain_to"] = b["bands"][-1]["chain_to"]
    bad["boundaries"][0]["chain_m"] += 3
    r = c.put("/api/admin/overlay", params=TOKEN, json=bad)
    ok("🔴 a boundary off every band edge is refused — 400", r.status_code == 400 and "not a band edge" in r.text,
       r.text[:160])
    r = c.put("/api/admin/overlay", json=b)
    ok("🔴 overlay upload without the token — 403", r.status_code == 403)

    # REVERSED (H1, 29 Sep 2026): a GB tenant now HAS a restriction provider (National
    # Highways planned closures) and an automatic diesel series (DESNZ). The demo's typed
    # placeholder is the index until the first DESNZ fetch replaces it. lazy=0: this must
    # never start a background fetch of gov.uk from the harness.
    r = c.get("/api/restrictions/layers")
    ok("GB (H1) → the restriction provider is National Highways, one layer, 100 m",
       r.json().get("provider", {}).get("key") == "nh_closures" and r.json().get("match_m") == 100.0
       and [l["key"] for l in r.json().get("layers", [])] == ["nh_closures"], r.text[:200])
    r = c.get("/api/fuel-index?lazy=0", headers=PLAN)
    fi = r.json() if r.status_code == 200 else {}
    idx = fi.get("index") or {}
    ok("GB (H1) → the automatic series is DESNZ, and the demo's typed GB placeholder is the index until it is fetched",
       r.status_code == 200 and idx.get("country") == "GB" and idx.get("auto_available") is True
       and (idx.get("provider") or {}).get("key") == "desnz" and idx.get("eur_per_l") == 1.955
       and idx.get("source") == "manual", str(idx)[:200])
    r = c.get("/api/forecast-weeks/restrictions?bucket=commit", headers=PLAN)
    ok("GB (H1) → the look-ahead's restriction status names the provider and the ROADWORKS word",
       r.status_code == 200 and r.json().get("provider") == "nh_closures" and r.json().get("flag_label") == "ROADWORKS", r.text[:200])
    r = c.get("/api/forecast-weeks/tark-tee?bucket=commit", headers=PLAN)
    ok("...and the pre-H1 path still answers (an alias, hidden from the schema)", r.status_code == 200)
    r = c.get("/api/meta")
    ok("GB (H1) → /api/meta carries hidden_vehicles (the EU names) and the tenant's distance unit (miles)",
       r.json().get("hidden_vehicles") and all(v.startswith("N3 ") or v == "Rigid 7.5t" for v in r.json()["hidden_vehicles"])
       and r.json()["tenant"].get("distance_unit") == "mi", str(r.json().get("hidden_vehicles"))[:200])

    # ------------------------------------------------------- 3. the data, as people read it
    r = c.get("/api/forecasts", headers=PLAN)
    rows = r.json() if r.status_code == 200 else []
    ok("a planner sees all 78 forecast rows (76 approved, 1 pending, 1 rejected — demo v2 + the muck-away line)", r.status_code == 200 and len(rows) == 78, f"{r.status_code} {len(rows)}")
    r = c.get("/api/forecasts", headers=NORTH)
    nrows = r.json() if r.status_code == 200 else []
    ok("⭐ the North Team code sees ONLY North Team's rows",
       r.status_code == 200 and nrows and all(x.get("ipt") == "IPT1" for x in nrows) and len(nrows) < len(rows),
       f"{r.status_code} {len(nrows)}")
    r = c.get("/api/forecasts")
    ok("🔴 forecasts without a code — 401", r.status_code == 401, str(r.status_code))

    # ------------------------------------------- 3b. the carbon planner (10 Oct 2026, phase 2)
    # The demo package ships NO geometry, so every line is unbaked: transport is excluded and
    # says so. One route is then baked BY HAND (no HERE) with the illustrative distances of
    # notes/carbon-why-different-1010.md §3 (R001 Kilby Ridge → Harborough, 18.4 + 19.1 km), so
    # the figures can be checked through the real HTTP layer against the note and the Dashboard.
    r = c.post("/api/carbon/scenario", json={})
    ok("🔴 the carbon scenario without a code — 401", r.status_code == 401, str(r.status_code))
    r = c.post("/api/carbon/scenario", headers=PLAN, json={})
    cs = r.json() if r.status_code == 200 else {}
    bt = (cs.get("baseline") or {}).get("totals") or {}
    ok("⭐ the carbon scenario answers a planner: 76 approved line-months, unbaked network EXCLUDED from transport",
       r.status_code == 200 and len(cs.get("lines") or []) == 76 and bt.get("baked_lines") == 0
       and bt.get("excludes_unbaked") is True and bt.get("transport_t") == 0 and bt.get("material_t", 0) > 0,
       f"{r.status_code} {r.text[:200]}")
    ok("...with the known limits, the Planned items and every factor's source, year and status",
       len(cs.get("limits") or []) >= 7 and len(cs.get("planned") or []) >= 4
       and all(f.get("status") for f in cs.get("factors") or []) and cs.get("unit") == "km")
    r = c.post("/api/carbon/scenario", headers=NORTH, json={})
    ok("⭐ the North Team code's scenario holds only North Team's lines",
       r.status_code == 200 and r.json()["lines"] and all(l["ipt"] == "IPT1" for l in r.json()["lines"])
       and len(r.json()["lines"]) < 72, f"{r.status_code} {r.text[:160]}")
    r = c.post("/api/carbon/scenario", headers=PLAN,
               json={"allocation": {"Small aggregate": {"Fencing": 70, "Drainage": 40}}})
    ok("🔴 an allocation over 100 % is refused — 400 naming the sum", r.status_code == 400 and "110" in r.text, r.text[:160])
    r = c.post("/api/carbon/scenario", headers=PLAN,
               json={"alternatives": [{"name": "x", "levers": [{"driver": "material", "scope": {"category": "Precast / concrete"}, "epd": {"kg_per_t": 90}}]}]})
    ok("🔴 an EPD without its source is refused — 400", r.status_code == 400 and "source" in r.text, r.text[:160])
    r = c.post("/api/carbon/scenario", headers=PLAN, json={"status": "Everything"})
    ok("an unknown status is refused — 400", r.status_code == 400)
    # phase 4: the demo's landfill-vs-reuse choice. 27,800 t of surplus cut over Sep–Dec:
    # landfill 27,800 × 19.55376 = 543.595 t; to the recycling hub 27,800 × 1.01398 = 28.189 t → −515.406 t
    r = c.post("/api/carbon/scenario", headers=PLAN, json={"alternatives": [
        {"name": "Reuse the cut", "levers": [{"driver": "disposal", "scope": {"route_id": "R019"}, "to_route": "R020"}]}]})
    cs = r.json() if r.status_code == 200 else {}
    _l19 = [l for l in cs.get("lines") or [] if l["route_id"] == "R019"]
    _a = (cs.get("alternatives") or [{}])[0]
    ok("⭐ demo (phase 4): the surplus cut to the fictional landfill is a Waste line at 19.55376 kg/t (543.595 t) …",
       r.status_code == 200 and len(_l19) == 4 and all(l["disposal_route"] == "landfill" and l["sheet"] == "Waste" for l in _l19)
       and abs(sum(l["disposal_t"] for l in _l19) - 543.595) < 0.002, str(_l19)[:300])
    ok("⭐ …and sending it to the fictional soil-recycling hub moves 515.406 t, ranked as the disposal decision",
       (_a.get("drivers") or [{}])[0].get("driver") == "disposal" and abs(_a.get("delta_t", 0) + 515.406) < 0.002, str(_a.get("drivers"))[:200])

    _r001 = [x for x in rows if x["route_id"] == "R001" and x["status"] == "Approved"]
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
               "duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("default", "R001", "Artic Tipper (44t)", "loaded", 0, "[[-1.2,52.5],[-1.1,52.6]]", 18.4, 0.42))
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
               "duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("default", "R001", "Artic Tipper (44t)", "return", 0, "[[-1.1,52.6],[-1.2,52.5]]", 19.1, 0.44))
    try:
        r = c.post("/api/carbon/scenario", headers=PLAN, json={"alternatives": [
            {"name": "Electric on R001", "levers": [{"driver": "fuel", "scope": {"route_id": "R001"}, "fuel": "electric"}]}]})
        cs = r.json() if r.status_code == 200 else {}
        bt = (cs.get("baseline") or {}).get("totals") or {}
        cl = c.get("/api/costing/lines?status=Approved", headers=PLAN).json()
        cl_r001 = sum(x["co2_t"] for x in cl["lines"] if x["route_id"] == "R001" and x["co2_t"] is not None)
        ok("⭐ R001 baked by hand: 62,500 t over four months, 75.99 t CO2e — the note's worked example, over HTTP",
           len(_r001) == 4 and abs(sum(x["quantity"] for x in _r001) - 62500) < 1e-6 and bt.get("baked_lines") == 4
           and abs(bt.get("transport_t", 0) - 75.99) < 0.01, f"{bt.get('baked_lines')} {bt.get('transport_t')}")
        ok("⭐ ...the SAME figure the Dashboard reads from /api/costing/lines (one number)", abs(bt.get("transport_t", 0) - cl_r001) < 0.002,
           f"{bt.get('transport_t')} vs {cl_r001}")
        ok("...and the NH Carbon Tool basis beside it: 261.82 t, labelled, not added in",
           abs(bt.get("transport_nh_t", 0) - 261.82) < 0.01 and "NH Carbon Tool" in (cs.get("methods") or {}).get("nh_tool", ""),
           str(bt.get("transport_nh_t")))
        alt = (cs.get("alternatives") or [{}])[0]
        fc = cs.get("fleet_compare") or {}
        ok("⭐ electric on R001: the ranked driver is diesel vs electric, carbon down, more trips at the lower payload",
           (alt.get("drivers") or [{}])[0].get("driver") == "fuel" and alt.get("delta_t", 0) < -50
           and fc.get("lines") == 4 and fc["electric"]["trips"] > fc["diesel"]["trips"], str(alt.get("drivers"))[:200])
        # after the show (11 Oct 2026, items 12 and 14): well-to-wheel and the modules, over HTTP.
        # 75.99 t at 0.93939 kg/km is 80,893 artic-km; × the 0.22058 well-to-tank row = 17.84 t
        ok("⭐ well-to-wheel over HTTP: R001's 75.99 t tank-to-wheel + 17.84 t well-to-tank, beside the total (not in it)",
           abs(bt.get("transport_wtt_t", 0) - 17.84) < 0.01 and abs(bt.get("transport_wtw_t", 0) - 93.83) < 0.02
           and abs(bt.get("total_t", 0) - (bt.get("material_t", 0) + bt.get("transport_t", 0) + bt.get("disposal_t", 0))) < 0.01,
           f"{bt.get('transport_wtt_t')} {bt.get('transport_wtw_t')}")
        st = (cs.get("baseline") or {}).get("stages") or {}
        ok("...the life-cycle modules add up to the total over HTTP", st and abs(sum(st.values()) - bt.get("total_t", 0)) < 0.01, str(st))
        # item 11: the summary PDF through the real HTTP layer — the demo notice and the stamp on it
        r = c.post("/api/carbon/summary.pdf", json={})
        ok("🔴 the carbon summary without a code — 401", r.status_code == 401, str(r.status_code))
        r = c.post("/api/carbon/summary.pdf", headers=PLAN, json={"alternatives": [
            {"name": "Electric on R001", "levers": [{"driver": "fuel", "scope": {"route_id": "R001"}, "fuel": "electric"}]}],
            "commentary": "Smoke check & <nothing> else"})
        from portable import pdf_text
        _st = " ".join(pdf_text(r.content).split()) if r.status_code == 200 else ""
        ok("⭐ the carbon summary over HTTP: a one-page PDF, stamped, with the fictional-scheme notice and the commentary as typed",
           r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf") and r.content[:5] == b"%PDF-"
           and "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" in _st
           and "Fictional demo scheme" in _st and "Smoke check & <nothing> else" in _st
           and "Battery electric lorries, where Config has an electric profile for that lorry — route R001" in _st,
           f"{r.status_code} {_st[:300]}")
        r = c.post("/api/carbon/summary.pdf", headers=PLAN, json={"commentary": "x" * 1501})
        ok("🔴 a commentary over 1,500 characters is refused — 400", r.status_code == 400 and "1500" in r.text, r.text[:160])
    finally:
        db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = ? AND vehicle_profile = ?",
                   ("default", "R001", "Artic Tipper (44t)"))

    # ------------------------------------------- 3c. the carbon target (11 Oct 2026, before the freeze)
    # The demo network is unbaked again here, so the figures are material + waste disposal. The one
    # decision is phase 4's: the surplus cut to the soil-recycling hub instead of the landfill, −515.406 t.
    _reuse = [{"driver": "disposal", "scope": {"route_id": "R019"}, "to_route": "R020"}]
    r = c.put("/api/carbon/target", json={"mode": "pct", "levers": _reuse})
    ok("🔴 the carbon target without a code — 401", r.status_code == 401, str(r.status_code))
    r = c.put("/api/carbon/target", headers=NORTH, json={"mode": "pct", "levers": _reuse})
    ok("🔴 a team code cannot set the carbon target — 403", r.status_code == 403, str(r.status_code))
    r = c.get("/api/carbon/target", headers=PLAN)
    ok("the demo ships with no carbon target: target and status null",
       r.status_code == 200 and r.json() == {"target": None, "status": None}, r.text[:160])
    r = c.put("/api/carbon/target", headers=PLAN, json={"mode": "pct", "levers": _reuse, "ui_state": {"disposal": {"R019": {"to_route": "R020"}}},
                                                        "updated_by": "Smoke planner"})
    ct = r.json() if r.status_code == 200 else {}
    tg, st = ct.get("target") or {}, ct.get("status") or {}
    ok("⭐ a planner sets a % target over HTTP: stored with who set it, the decisions in words",
       r.status_code == 200 and tg.get("mode") == "pct" and tg.get("updated_by") == "Smoke planner" and tg.get("levers") == _reuse
       and tg.get("lever_words") and "Soil" in tg["lever_words"][0], r.text[:300])
    ok("⭐ ...the server's own figures read back consistently: the cut is phase 4's 515.406 t, the % is that over the plan",
       st.get("scope") == "scheme" and abs((st.get("approved_t", 0) - st.get("with_decisions_t", 0)) - 515.406) < 0.002
       and tg.get("set_at_approved_t") == st.get("approved_t") and tg.get("cap_t") == st.get("with_decisions_t")
       # NARROWED 11 Oct 2026 (% held to 6 dp, R1): to 0.00001, was 0.06 (the 1 dp rounding)
       and abs(tg.get("pct_below", 0) - 515.406 * 100 / st.get("approved_t", 1)) < 0.00001, str(st)[:300])
    # NARROWED 11 Oct 2026 (R1): to 0.002, was 0.01; and the plan with the decisions IS the target the moment it is set
    ok("⭐ ...target = approved × (1 − %) to 0.002, the gaps are the differences, and with the decisions it is exactly on target",
       abs(st.get("target_t", 0) - st.get("approved_t", 0) * (1 - tg.get("pct_below", 0) / 100)) < 0.002
       and abs(st.get("gap_as_forecast_t", 0) - (st.get("approved_t", 0) - st.get("target_t", 0))) < 0.002
       and abs(st.get("gap_with_decisions_t", 9) - (st.get("with_decisions_t", 0) - st.get("target_t", 0))) < 0.002
       and abs(st.get("gap_with_decisions_t", 9)) <= 0.001 and st.get("target_t") == st.get("with_decisions_t"), str(st)[:300])
    ok("⭐ R2 over HTTP: the server's own verdicts — as forecast not on target (515.4 over), with the decisions on target",
       st.get("on_target_as_forecast") is False and st.get("on_target_with_decisions") is True, str(st)[:300])
    # the one Pending demo line is R013's soil to a compound: soils have no primary factor and the route is
    # unbaked, so it adds 0.0 all-in — counted as 0, not left out
    ok("...the pending line adds 0.0 (soil to a compound, unrouted), transport 0 (nothing routed), months listed, nothing invalid",
       st.get("pending_t") == 0.0 and st.get("approved_transport_t") == 0.0 and st.get("invalid") is None
       and len(st.get("by_month") or []) >= 4
       and abs(sum(m["approved_t"] for m in st["by_month"]) - st.get("approved_t", 0)) < 0.02, str(st)[:300])
    r = c.get("/api/carbon/target", headers=NORTH)
    sn = (r.json() or {}).get("status") or {} if r.status_code == 200 else {}
    # REVERSED 11 Oct 2026 (the review: the scheme's % applied to North's lines, which the decision does not touch, read
    # "253.2 over the target" to every show visitor while the scheme was on target). It asserted North's target_t =
    # its approved plan × (1 − %). Now a team code gets no share of the scheme's target, and so no verdict.
    ok("⭐ the North Team code reads it: scope team, its own lines (the cut is Central's line, so none here), NOT compared with the scheme's target",
       r.status_code == 200 and sn.get("scope") == "team" and 0 < sn.get("approved_t", 0) < st.get("approved_t", 0)
       and sn.get("with_decisions_t") == sn.get("approved_t")
       and sn.get("target_t") is None and sn.get("gap_with_decisions_t") is None and sn.get("on_target_with_decisions") is None
       and sn.get("on_target_as_forecast") is None, str(sn)[:300])
    tn = (r.json() or {}).get("target") or {} if r.status_code == 200 else {}
    ok("🔴 R3 over HTTP: North's GET carries no stored decisions and no page state, and no words for the route-scoped decision",
       r.status_code == 200 and tn.get("mode") == "pct" and "levers" not in tn and "ui_state" not in tn
       and tn.get("lever_words") == [] and "R019" not in r.text and "R020" not in r.text, str(tn)[:300])
    r = c.put("/api/carbon/target", headers=PLAN, json={"mode": "cap", "updated_by": "Smoke planner"})
    cc = r.json() if r.status_code == 200 else {}
    ok("⭐ switch to a fixed cap: every number kept, the target is the cap",
       r.status_code == 200 and cc["target"]["mode"] == "cap" and cc["target"]["cap_t"] == tg.get("cap_t")
       and cc["target"]["pct_below"] == tg.get("pct_below") and cc["status"]["target_t"] == tg.get("cap_t"), r.text[:300])
    r = c.get("/api/carbon/target", headers=NORTH)
    ok("🔴 ...and a team code sees no share of a fixed cap (target_t null)", r.status_code == 200 and r.json()["status"]["target_t"] is None
       and r.json()["status"]["gap_as_forecast_t"] is None and r.json()["status"]["on_target_as_forecast"] is None
       and "levers" not in r.json()["target"], r.text[:200])
    r = c.put("/api/carbon/target", headers=PLAN, json={"mode": "pct", "levers": []})
    ok("🔴 no decisions — 400 with the sentence", r.status_code == 400 and "Choose at least one decision" in r.text, r.text[:160])
    r = c.delete("/api/carbon/target", headers=NORTH)
    ok("🔴 a team code cannot clear it — 403", r.status_code == 403, str(r.status_code))
    r = c.delete("/api/carbon/target", headers=PLAN)
    ok("⭐ a planner clears it: target null, and GET agrees", r.status_code == 200 and r.json()["target"] is None
       and c.get("/api/carbon/target", headers=PLAN).json() == {"target": None, "status": None}, r.text[:160])
    # the Submit forecast preview's all-in carbon, over HTTP: 1,000 t of cut to the landfill = 1000 × 19.55376
    r = c.post("/api/costing/preview", headers=PLAN, json={"route_id": "R019", "vehicle_type": "Artic Tipper (44t)",
                                                          "material_type": "Earthworks / soil", "unit": "t",
                                                          "cells": [{"month_index": 10, "quantity": 1000}]})
    pc = (r.json() or {}).get("carbon") or {} if r.status_code == 200 else {}
    ok("⭐ the preview carries its carbon: 1,000 t to the landfill = 19.554 tCO2e disposal, transport unrouted (never estimated)",
       r.status_code == 200 and pc.get("disposal_t") == 19.554 and pc.get("material_t") is None and pc.get("transport_t") is None
       and pc.get("unrouted") is True and pc.get("total_t") == 19.554 and "landfill" in (pc.get("basis") or ""), str(pc))
    r = c.post("/api/costing/preview", headers=PLAN, json={"route_id": "R002", "vehicle_type": "Artic Tipper (44t)",
                                                          "material_type": "Small aggregate", "unit": "t",
                                                          "cells": [{"month_index": 10, "quantity": 2900}]})
    pc = (r.json() or {}).get("carbon") or {} if r.status_code == 200 else {}
    ok("...and a delivery: 2,900 t of aggregate = 22.629 tCO2e to make (2900 × 7.80307), transport not counted until routed",
       r.status_code == 200 and pc.get("material_t") == 22.629 and pc.get("total_t") == 22.629 and pc.get("unrouted") is True
       and "not counted until the route has a distance" in (pc.get("basis") or ""), str(pc))

    r = c.get("/api/lookahead", headers=PLAN)
    la = r.json() if r.status_code == 200 else {}
    ok("the Look-ahead page reads over HTTP", r.status_code == 200 and "commit" in la, r.text[:200])
    flags = (la.get("clashes") or {}).get("flags") or []
    ok("...its flag codes are the documented ones (the app names them for people)",
       all(f.get("code") in ("SHORTAGE", "DAYS_NE_WEEK", "STOCKPILE_OVER", "ROUTE_CAP", "IPT_SHARE", "TARK_TEE",
                             "UNBAKED", "PARENT_CHANGED") for f in flags), str({f.get("code") for f in flags}))
    ok("...and the unbaked demo network is flagged, not estimated",
       any(f.get("code") == "UNBAKED" for f in flags) or (la.get("clashes") or {}).get("by_code", {}).get("UNBAKED"),
       str((la.get("clashes") or {}).get("by_code")))

    r = c.get("/api/forecast-weeks/export", params={"format": "xlsx"}, headers=PLAN)
    ok("⭐ the XLSX export downloads (real openpyxl)", r.status_code == 200
       and r.headers.get("content-type", "").startswith("application/vnd.openxmlformats")
       and r.content[:2] == b"PK" and "attachment" in r.headers.get("content-disposition", ""),
       f"{r.status_code} {r.headers.get('content-type')}")
    xlsx_bytes = r.content
    r = c.get("/api/forecast-weeks/export", params={"format": "pdf"}, headers=PLAN)
    ok("⭐ the PDF export downloads (real reportlab)", r.status_code == 200
       and r.headers.get("content-type") == "application/pdf" and r.content[:5] == b"%PDF-",
       f"{r.status_code} {r.headers.get('content-type')} {r.content[:60]!r}")
    pdf_bytes = r.content

    try:
        import io
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
        ws = wb[wb.sheetnames[0]]
        head = [cell.value for cell in ws[1]]
        teams_col = head.index("Team") if "Team" in head else None
        vals = [row[teams_col].value for row in ws.iter_rows(min_row=2)] if teams_col is not None else []
        ok("the XLSX header uses the tenant's words — 'Team' and £", "Team" in head and "£" in head and "IPT" not in head,
           str(head[:20]))
        ok("⭐ ...and its Team column carries team NAMES, never ids",
           vals and all(v in ("North Team", "Central Team", "South Team") for v in vals), str(sorted(set(map(str, vals)))[:5]))
        cl = wb["Clashes"] if "Clashes" in wb.sheetnames else None
        cl_txt = " ".join(str(c.value) for row in cl.iter_rows() for c in row if c.value) if cl else ""
        ok("⭐ the Clashes sheet shows flag NAMES and team names — no code with IPT in it, no team id",
           cl is not None and "UNBAKED" in cl_txt and not re.search(r"IPT_|\bIPT ?[1-6]\b", cl_txt)
           and [c.value for c in cl[1]][2] == "Team", cl_txt[:200])
        about = wb["About"] if "About" in wb.sheetnames else None
        about_txt = " ".join(str(c.value) for row in about.iter_rows() for c in row if c.value) if about else ""
        ok("the About sheet names the tenant", "Wolds Link" in about_txt, about_txt[:120])
    except Exception as e:
        ok("the XLSX opens in openpyxl", False, repr(e))

    try:
        with open(os.path.join(TMP, "week.pdf"), "wb") as f:
            f.write(pdf_bytes)
        txt = ""
        try:  # pdftotext, when the machine has it: poppler's (CI installs poppler-utils) or
            # Xpdf's (Git for Windows ships one). Ask both for UTF-8 — Xpdf defaults to Latin-1,
            # which fails a UTF-8 decode and silently emptied this block on Windows (7 Oct 2026).
            import subprocess
            txt = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", "-eol", "unix",
                                  os.path.join(TMP, "week.pdf"), "-"],
                                 capture_output=True, timeout=60).stdout.decode("utf-8", errors="replace")
        except Exception:
            txt = ""
        if txt:
            ok("the PDF names the tenant and never a team id", "Wolds Link" in txt and not re.search(r"\bIPT ?[1-6]\b", txt),
               txt[:160])
            flat = re.sub(r"\s+", " ", txt)
            ok("...its team column is headed with the tenant's word, not IPT", "TEAM /" in txt and "IPT /" not in txt,
               txt[:400])
            ok("...it shows team names (the cell may wrap) and £, and says the routes are not baked",
               re.search(r"\b(North|Central|South)\b", txt) and "Team" in txt and "£ WEEK" in txt
               and "not baked" in flat.lower(), flat[:300])
            ok("...and its footer is country-neutral", "Road-user charges are not on this sheet" in txt
               and "vignette" not in txt.lower() and "Estonia" not in txt, txt[-300:])
        else:
            ok("the PDF is a non-trivial document (text extraction unavailable here)", len(pdf_bytes) > 5000, str(len(pdf_bytes)))
    except Exception as e:
        ok("the PDF could be written", False, repr(e))

    r = c.get("/api/public/map-data")
    ok("the public map data reads (staff cookie)", r.status_code == 200, str(r.status_code))

    # ------------------------------------------------------------ 4. export and replace
    r = c.get("/api/admin/tenant/export", params=TOKEN)
    ok("⭐ the tenant exports as a JSON attachment", r.status_code == 200
       and r.headers.get("content-type", "").startswith("application/json")
       and "attachment" in r.headers.get("content-disposition", ""), str(r.status_code))
    pkg = r.json() if r.status_code == 200 else {}
    ok("...a valid package of the same size", pkg.get("modus_package") == 1
       and len(pkg["tables"]["routes"]) == 20 and len(pkg["tables"]["forecasts"]) == 78
       and len(pkg["tables"]["forecast_weeks"]) == 342 and len(pkg["tables"]["location_gates"]) == 16)
    r = c.post("/api/admin/tenant/import", params=dict(TOKEN, replace=1), json=pkg)
    ok("⭐ replace=1 re-imports the exported tenant over itself", r.status_code == 200 and r.json().get("replaced") is True,
       r.text[:160])
    m2 = c.get("/api/meta").json()
    ok("...and nothing is lost or doubled", len(m2["routes"]) == 20 and len(m2["ipts"]) == 3
       and len(c.get("/api/forecasts", headers=PLAN).json()) == 78)

    # ------------------------------------------------------------ 5. H9: demo requests (8 Oct)
    # Signed out, no cookie, no code: the landing page's visitor. SMTP stubbed at the module.
    r = c.post("/api/gate-signout")
    c.cookies.clear()
    import demo_request as _dr
    _sent = []
    class _SMTPStub:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, m): _sent.append(m)
        ehlo_resp = b"250-AUTH LOGIN PLAIN"
        def auth_plain(self, challenge=None): return ""
        def auth_login(self, challenge=None): return ""
        def auth(self, mech, authobject, initial_response_ok=True): return (235, b"Accepted")
    _real = _dr.smtplib.SMTP
    _dr.smtplib.SMTP = _SMTPStub
    try:
        for v in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY"):
            os.environ.pop(v, None)
        form = {"name": "Ada Example", "email": "ada@example.org", "organisation": "Example Civils",
                "role": "Principal contractor", "wants": "the look-ahead", "updates": "yes", "website": ""}
        r = c.post("/api/public/demo-request", follow_redirects=False, data=form)
        ok("⭐ no sender configured: the form POST (signed out) answers 200 with the access page", r.status_code == 200
           and "map-pass-xyz" in r.text and "north-code-xyz" in r.text and "fictional" in r.text, str(r.status_code))
        ok("...no-store, and it never carries the planner or admin code", r.headers.get("cache-control") == "no-store"
           and "plan-code-xyz" not in r.text and "admin-code-xyz" not in r.text)
        r = c.post("/api/public/demo-request", follow_redirects=False, data=dict(form, website="bot"))
        ok("a honeypot hit is a 303 to thanks.html", r.status_code == 303 and r.headers["location"] == "https://wayscope.co.uk/thanks.html")
        r = c.post("/api/public/demo-request", follow_redirects=False, data=dict(form, email="nope"))
        ok("an invalid form is a 303 to error.html", r.status_code == 303 and r.headers["location"] == "https://wayscope.co.uk/error.html")
        os.environ.update({"SMTP_USER": "sender@wayscope.co.uk", "SMTP_PASSWORD": "app-pass", "DEMO_FROM": "Wayscope <sender@wayscope.co.uk>",
                           "DEMO_NOTIFY": "notify@wayscope.co.uk"})
        r = c.post("/api/public/demo-request", follow_redirects=False, data=dict(form, email="bea@example.org"))
        ok("⭐ sender configured: the POST is a 303 to thanks.html and the background task sent two emails",
           r.status_code == 303 and r.headers["location"] == "https://wayscope.co.uk/thanks.html" and len(_sent) == 2
           and _sent[0]["To"] == "bea@example.org" and _sent[1]["To"] == "notify@wayscope.co.uk", f"{r.status_code} {len(_sent)}")
        ok("...the email carries both codes", "map-pass-xyz" in _sent[0].get_body(preferencelist=("plain",)).get_content()
           and "north-code-xyz" in _sent[0].get_body(preferencelist=("plain",)).get_content())
        ok("🔴 /api/public/route-forecasts is still closed to the same signed-out visitor",
           c.get("/api/public/route-forecasts").status_code == 401)
        r = c.get("/api/admin/diagnostics/smtp")
        ok("the SMTP probe is refused without the admin token", r.status_code == 403, str(r.status_code))
        r = c.get("/api/admin/diagnostics/smtp", params=TOKEN)
        ok("...and with it reports a login (stubbed) as ok at step 'done'", r.status_code == 200 and r.json().get("ok") is True
           and r.json().get("step") == "done" and r.json().get("user") == "sender@wayscope.co.uk", r.text[:200])
        r = c.get("/api/admin/demo-requests.csv")
        ok("the CSV is refused without the admin token", r.status_code == 403, str(r.status_code))
        r = c.get("/api/admin/demo-requests.csv", params=TOKEN)
        ok("...and served with it: text/csv, three stored rows (the honeypot and the invalid one are not rows)",
           r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
           and r.text.count(chr(10)) == 3 and "ada@example.org" in r.text and "bea@example.org" in r.text
           and "shown on screen" in r.text and ",sent," in r.text, r.text[:300])
    finally:
        _dr.smtplib.SMTP = _real
        for v in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY"):
            os.environ.pop(v, None)

    r = c.get("/map/")
    ok("after sign-out the map is closed again", r.status_code == 401, str(r.status_code))
    r = c.post("/api/map-auth", json={"password": "map-pass-xyz"})
    ok("the map password opens the map…", r.status_code == 200 and c.get("/map/").status_code == 200)
    ok("…but 🔴 not the guide", c.get("/help/").status_code == 401)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

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
    # 12 Oct 2026 (C4): the monthly bulletin's page is staff-only like the guide, with its own refusal page
    r = c.get("/bulletin/?month=10")
    ok("🔴 the monthly bulletin page is closed without a staff sign-in — 401, the bulletin's own sign-in page (the middleware's)",
       r.status_code == 401 and "The monthly bulletin is for signed-in staff" in r.text and "user guide" not in r.text.lower(),
       f"{r.status_code} {r.text[:120]}")
    r = c.get("/api/bulletin/month.pdf?month=10")
    ok("🔴 ...and so is its PDF — 401", r.status_code == 401, str(r.status_code))
    r = c.get("/api/public/alignment")
    ok("🔴 the overlay API is gated like the map — 401 JSON", r.status_code == 401
       and r.headers.get("content-type", "").startswith("application/json"), str(r.status_code))

    r = c.get("/api/meta")
    m = r.json()
    ok("meta is readable before sign-in (the sign-in screen needs it)", r.status_code == 200)
    # NARROWED 12 Oct 2026 (D31): before sign-in the answer is the PUBLIC shape and says so
    ok("a fresh tenant is EMPTY: no routes, teams or sections — and before sign-in the shape is `public`",
       m["routes"] == [] and m["ipts"] == [] and m["work_sections"] == [] and m.get("scope") == "public",
       str({k: len(m[k]) for k in ("routes", "ipts", "work_sections")}) + " " + str(m.get("scope")))
    ok("...and carries the default tenant words: Wayscope, Team, EUR, no country",
       m["tenant"]["name"] == "Wayscope" and m["tenant"]["team_label"] == "Team"
       and m["tenant"]["currency"] == "EUR" and m["tenant"]["country"] is None, str(m["tenant"]))
    ok("D31: the public shape carries what the sign-in screen and the public map read — units, vehicles, labels, months, factors, seasonal windows",
       m["units"] and m["vehicles"] and m["vehicle_labels"].get("langs") and m["months"]["count"] == 60
       and isinstance(m["factors"], dict) and isinstance(m["seasonal_restrictions"], list) and m["disciplines"])

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
    # 12 Oct 2026 (C11 closed): the bake and every other admin call refuse without the token, with a wrong one, and —
    # the part that was open until now — with ADMIN_TOKEN UNSET even when the right token is sent
    r = c.post("/api/admin/bake-routes")
    ok("🔴 C11: POST /api/admin/bake-routes without the admin token — 403, no HERE call", r.status_code == 403, str(r.status_code))
    r = c.post("/api/admin/bake-routes", params={"token": "wrong"})
    ok("🔴 C11: ...with a wrong token — 403", r.status_code == 403, str(r.status_code))
    _saved_admin = os.environ.pop("ADMIN_TOKEN")
    try:
        r_bake = c.post("/api/admin/bake-routes", params=TOKEN)
        r_stat = c.get("/api/admin/tenant/status", params=TOKEN)
        r_exp = c.get("/api/admin/tenant/export", params=TOKEN)
    finally:
        os.environ["ADMIN_TOKEN"] = _saved_admin
    ok("🔴 C11 CLOSED: with ADMIN_TOKEN unset the admin surface is refused (403) even with the token that would match — bake, status, export",
       r_bake.status_code == 403 and r_stat.status_code == 403 and r_exp.status_code == 403
       and "not configured" in r_bake.text, f"{r_bake.status_code} {r_stat.status_code} {r_exp.status_code} {r_bake.text[:80]}")
    r = c.get("/api/admin/tenant/status", params=TOKEN)
    ok("...and with it set again the token opens the surface as before", r.status_code == 200, str(r.status_code))

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
        # 12 Oct 2026 (D31 / D18): the same visitor — no cookie, no code — reads /api/meta and asks for the network
        r_meta_out = c.get("/api/meta")
        r_meta_hdr = c.get("/api/meta", headers=PLAN)
        r_gates_out = c.get("/api/gates")
        r_who_out = c.get("/api/public/whoami")
    finally:
        c.cookies = _jar
    _mo = r_meta_out.json()
    ok("🔴 D31: with the demo tenant in, /api/meta to a visitor with NO cookie and NO code is the PUBLIC shape: the tenant's words, "
       "the vehicles and factors, but NO routes, NO teams, NO sections",
       r_meta_out.status_code == 200 and _mo["scope"] == "public" and _mo["tenant"]["name"].startswith("Wolds Link")
       and _mo["routes"] == [] and _mo["ipts"] == [] and _mo["work_sections"] == [] and len(_mo["vehicles"]) > 0
       and isinstance(_mo["factors"].get("vehicle_payload_t"), dict) and isinstance(_mo["seasonal_restrictions"], list),
       str({k: _mo.get(k) for k in ("scope", "routes", "ipts", "work_sections")})[:200])
    ok("⭐ D31: ...and the SAME visitor with the planner code in the header (the staff app's fetch) gets the staff shape: twenty routes, three teams, eight sections",
       r_meta_hdr.status_code == 200 and r_meta_hdr.json()["scope"] == "staff" and len(r_meta_hdr.json()["routes"]) == 20
       and [i["label"] for i in r_meta_hdr.json()["ipts"]] == ["North Team", "Central Team", "South Team"]
       and len(r_meta_hdr.json()["work_sections"]) == 8, str(r_meta_hdr.json().get("scope")))
    ok("🔴 D18: /api/gates to a visitor with no credential is the map's 401 JSON, not the gate list",
       r_gates_out.status_code == 401 and r_gates_out.json().get("detail") == "the map is password protected", r_gates_out.text[:120])
    ok("🔴 whoami: a visitor with no credential gets the gate's 401, and learns nothing", r_who_out.status_code == 401, str(r_who_out.status_code))
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
    # NARROWED 12 Oct 2026 (D31): this client holds the STAFF cookie (from /api/auth above) and sends no header — the
    # app's iframe — and that alone earns the staff shape
    ok("⭐ ...three named teams, eight sections, twenty routes — the staff shape, on the staff COOKIE alone (no header)",
       [i["label"] for i in m["ipts"]] == ["North Team", "Central Team", "South Team"]
       and len(m["work_sections"]) == 8 and len(m["routes"]) == 20 and m["scope"] == "staff",
       str([i["label"] for i in m["ipts"]]) + " " + str(m.get("scope")))
    ok("§2.5: every meta route carries max_vehicles_per_day — 20 on R016, 30 on R018 (the demo's village caps), None elsewhere",
       {r["route_id"]: r["max_vehicles_per_day"] for r in m["routes"] if r["max_vehicles_per_day"] is not None} == {"R016": 20, "R018": 30}
       and all("max_vehicles_per_day" in r for r in m["routes"]))

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
    # NARROWED 11 Oct 2026 (EU vehicles removed): the four EU names left the product, so the GB demo hides
    # Rigid 7.5t alone — asserted exactly, since "N3 or Rigid 7.5t" would now pass on the one name and prove nothing.
    ok("GB (H1) → /api/meta carries hidden_vehicles (Rigid 7.5t alone, no EU name) and the tenant's distance unit (miles)",
       r.json().get("hidden_vehicles") == ["Rigid 7.5t"]
       and not any(v.startswith("N3 ") for v in r.json().get("vehicles") or [])
       and r.json()["tenant"].get("distance_unit") == "mi", str(r.json().get("hidden_vehicles"))[:200])
    ok("11 Oct 2026: GB → /api/meta offers English vehicle names only, and leads with the UK trade names",
       r.json()["vehicle_labels"]["langs"] == ["en"] and (r.json().get("planning_vehicles") or [None])[0] == "Rigid 8-wheeler (32t)",
       str(r.json().get("vehicle_labels", {}).get("langs")))

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

    # B4 (12 Oct 2026): with NO geometry the map draws nothing, so the bulletin's roll-up is EMPTY and names every
    # line as not drawn — it never presents zeros as figures. The baked case is 3c below.
    r = c.get("/api/bulletin/month?month=10", headers=PLAN)
    _pe = r.json() if r.status_code == 200 else {}
    ok("⭐ the bulletin on the unbaked demo: empty (four headline figures null), all 19 October lines named as on routes the map does not draw",
       r.status_code == 200 and _pe["rollup"]["empty"] is True and _pe["rollup"]["headline"]["two_way_a_day"] is None
       and _pe["rollup"]["headline"]["routes_in_use"] == 0 and _pe["rollup"]["routes_not_drawn"]["lines"] == 19
       and len(_pe["rollup"]["routes_not_drawn"]["routes"]) == 19
       # NARROWED 12 Oct 2026 (the review and fix pass): plain words, "with no stored road route yet", not "not yet baked"
       and _pe["rollup"]["note"] == ("No approved forecast on a route the map draws in this month: 19 lines on 19 routes "
                                     "with no stored road route yet, listed below and not counted.")
       and _pe["conditions"]["route_caps"]["wording"] == "planning flag", f"{r.status_code} {str(_pe)[:300]}")
    # NARROWED 12 Oct 2026 (the tests-and-regressions review): the carbon figures on that empty roll-up are
    # BOTH None (co2_t_a_day used to read 0.0), and there is no co2_error to carry
    ok("…its carbon block: both figures None, not_baked False (no counted line at all), no error",
       _pe["rollup"]["carbon"]["co2_t_a_day"] is None and _pe["rollup"]["carbon"]["co2_t_in_month"] is None
       and _pe["rollup"]["carbon"]["not_baked"] is False and _pe["rollup"]["carbon"]["error"] is None, str(_pe["rollup"].get("carbon")))

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
        # 12 Oct 2026 (B2): the public map's two feeds carry that figure too, per line per month, with no co2_error
        r = c.get("/api/public/forecast-matrix", params={"from": 1, "to": 60, "unit": "t"})
        fm = r.json() if r.status_code == 200 else {}
        _fm001 = [x for x in fm.get("routes") or [] if x["route_id"] == "R001"]
        _fm_sum = sum(v for x in _fm001 for v in (x.get("co2_t") or {}).values() if v is not None)
        ok("⭐ B2: /api/public/forecast-matrix carries co2_t per line per month for the hand-baked R001, keyed like monthly, summing to the costlines figure",
           r.status_code == 200 and _fm001 and all(set(x.get("co2_t") or {}) == set(x["monthly"]) for x in _fm001)
           and all(v is not None for x in _fm001 for v in x["co2_t"].values()) and abs(_fm_sum - cl_r001) < 0.002,
           f"{r.status_code} {_fm_sum} vs {cl_r001} {[x.get('co2_t') for x in _fm001][:2]}")
        ok("B2: ...an UNBAKED route's months read None, never a zero (the rest of the demo is not baked here)",
           any(all(v is None for v in x["co2_t"].values()) for x in fm.get("routes") or [] if x["route_id"] != "R001"))
        ok("B2: ...and co2_error is absent on the happy path", "co2_error" not in fm and "working_days" in fm)
        # 12 Oct 2026 (Track C review): sections=1 adds the largest section-month (the map's section ramp); absent without it
        r = c.get("/api/public/forecast-matrix", params={"from": 1, "to": 60, "unit": "t", "sections": 1})
        ok("Track C review: forecast-matrix with sections=1 answers 200 and carries section_co2_max (None or a positive figure); without it the key is absent",
           r.status_code == 200 and "section_co2_max" in r.json()
           and (r.json()["section_co2_max"] is None or r.json()["section_co2_max"] > 0) and "section_co2_max" not in fm, r.text[:200])
        _m001 = sorted({x["month_index"] for x in _r001})[0]
        r = c.get("/api/public/month-kpis", params={"month": _m001, "unit": "t"})
        mk = r.json() if r.status_code == 200 else {}
        ok("B2: /api/public/month-kpis for R001's first month: co2_t present on its line, co2_error absent",
           r.status_code == 200 and "co2_error" not in mk
           and any(l["route_id"] == "R001" and l["co2_t"] is not None for l in mk.get("lines") or []), f"{r.status_code} {str(mk)[:160]}")
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

        # --------------------------------------- 3c. the monthly bulletin (B4, 12 Oct 2026), while R001 is baked
        r = c.get("/api/bulletin/month?month=10")
        ok("🔴 the bulletin without a code — 401", r.status_code == 401, str(r.status_code))
        ok("🔴 a month outside the horizon is refused — 422", c.get("/api/bulletin/month?month=0", headers=PLAN).status_code == 422)
        r = c.get("/api/bulletin/month?month=10", headers=PLAN)
        pg = r.json() if r.status_code == 200 else {}
        hl = (pg.get("rollup") or {}).get("headline") or {}
        _wd = pg.get("working_days")
        ok("⭐ the bulletin answers a planner for Oct 2026: the four headline figures present, working days stated, the demo notice on it",
           r.status_code == 200 and pg["month"] == {"index": 10, "label": "Oct 2026", "label_long": "October 2026",
                                                     "from": "2026-10-01", "to": "2026-10-31"}
           and all(hl.get(k) is not None for k in ("two_way_a_day", "movements_in_month", "routes_in_use", "tonnes"))
           and _wd and hl["working_days"] == _wd and pg["demo_notice"] == "Fictional demo scheme · nothing here is real"
           and pg["plan_only"] is True, f"{r.status_code} {str(pg)[:300]}")
        _kp = c.get("/api/public/month-kpis?month=10", headers=PLAN).json()
        _r001 = [l for l in _kp["lines"] if l["route_id"] == "R001"]
        ok("⭐ …the figures are the map bar's rules over the map's own payload: R001 is the ONE drawn route — 16,900 t ÷ 29 t "
           "= 582.759 loads ÷ working days; vehicles = ceil per line from the same trips_per_vehicle_day; the 18 undrawn routes named",
           hl["routes_in_use"] == 1 and abs(hl["tonnes"] - 16900) < 1e-6 and abs(hl["movements_in_month"] - 16900 / 29) < 1e-3
           and abs(hl["two_way_a_day"] - 16900 / 29 / _wd) < 1e-3 and len(_r001) == 1 and _r001[0]["trips_per_vehicle_day"]
           and pg["rollup"]["vehicles"]["fleet"] == -(-(16900 / 29 / _wd) // _r001[0]["trips_per_vehicle_day"])
           and pg["rollup"]["routes_not_drawn"]["lines"] == 18 and len(pg["rollup"]["routes_not_drawn"]["routes"]) == 18
           and "R001" not in pg["rollup"]["routes_not_drawn"]["routes"], f"{hl} {pg['rollup'].get('vehicles')} {_r001}")
        _cl10 = sum(x["co2_t"] for x in cl["lines"] if x["route_id"] == "R001" and x["month_index"] == 10 and x["co2_t"] is not None)
        ok("⭐ …carbon is the costlines figure the Dashboard reads (R001, October), stamped as the Carbon page stamps it",
           abs(pg["rollup"]["carbon"]["co2_t_in_month"] - _cl10) < 0.002 and _cl10 > 0
           and pg["rollup"]["carbon"]["stamp"] == "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures",
           f"{pg['rollup']['carbon']} vs {_cl10}")
        ok("…and the block is a figure, not a gap: not_baked False, no error (12 Oct 2026 review)",
           pg["rollup"]["carbon"]["not_baked"] is False and pg["rollup"]["carbon"]["error"] is None)
        _b = pg["rollup"]["busiest_routes"]
        ok("…the busiest route is R001 by its places, with \"no planning cap typed\"; the team row reads the tenant's name, never an id",
           len(_b) == 1 and _b[0]["label"] == "Kilby Ridge Quarry → Harborough Compound" and _b[0]["cap_wording"] == "no planning cap typed"
           and [t["key"] for t in pg["rollup"]["breakdown"]["team"]] == ["South Team"] and "IPT" not in r.text, str(_b)[:200])
        _cn = pg["conditions"]
        ok("⭐ …conditions of the month from what is STORED: no stored check, so \"never checked\" on all 19 routes (National Highways provider)",
           _cn["restrictions"]["status"] == "never checked" and len(_cn["restrictions"]["never_checked_routes"]) == 19
           and _cn["restrictions"]["hits"] == [] and _cn["restrictions"]["provider"] == "nh_closures", str(_cn["restrictions"])[:200])
        ok("⭐ …Stockpile Tilton over at the end of October by 510 t (40,510 against 40,000 — the figure the live map showed on 11 Oct)",
           [(p["name"], p["capacity_qty"], p["balance_end"], p["over_by"]) for p in _cn["stockpiles_over"]]
           == [("Stockpile Tilton", 40000.0, 40510.0, 510.0)], str(_cn["stockpiles_over"]))
        ok("⭐ …and its sentence says the balance is RECORDED (typed week actuals carried forward), never \"the plan puts\" (D23)",
           # NARROWED 12 Oct 2026 (the review and fix pass): "has a capacity of", not "holds"
           _cn["stockpiles_over"][0]["wording"] == ("Stockpile Tilton has a capacity of 40,000 t; 40,510 t recorded in it at the end "
                                                    "of Oct 2026, from the week actuals typed so far, carried forward.")
           and "plan puts" not in r.text, str(_cn["stockpiles_over"][0].get("wording")))
        _cap = _cn["route_caps"]
        ok("⭐ …the typed cap on R016 (20 a day) is exceeded by October's loaded trips a day and reads \"planning flag\", never a block",
           _cap["wording"] == "planning flag" and _cap["routes_with_cap"] == 2 and [e["route_id"] for e in _cap["exceeded"]] == ["R016"]
           and _cap["exceeded"][0]["cap"] == 20 and _cap["exceeded"][0]["two_way_a_day"] > 20
           and "never a block" in _cap["note"] and "planning flag" in r.text, str(_cap)[:300])
        ok("…no seasonal window on the demo (the seed has none)", _cn["seasonal"] == [])
        r2 = c.get("/api/bulletin/month?month=10", headers=NORTH)
        pn = r2.json() if r2.status_code == 200 else {}
        ok("⭐ the North Team code gets the SCHEME's figures (the public map's) with the per-team rows limited to its own team — "
           "none here, the one drawn route is South Team's",
           r2.status_code == 200 and pn["rollup"]["headline"] == hl and pn["rollup"]["busiest_routes"] == _b
           and pn["rollup"]["breakdown"]["team"] == [] and pn["scope"]["team"] == "North Team"
           and pn["rollup"]["breakdown"]["discipline"] == pg["rollup"]["breakdown"]["discipline"], f"{r2.status_code} {str(pn.get('scope'))}")
        # 12 Oct 2026 (C4): the bulletin as people read it, over HTTP — the PDF and the page, from the same roll-up.
        # Mapbox is never called: portable.offline() refuses the static-image fetch, so the map is the schematic.
        import export
        from portable import offline
        _real_open = offline(export)
        try:
            r = c.get("/api/bulletin/month.pdf?month=10", headers=PLAN)
            _bt = pdf_text(r.content) if r.status_code == 200 else ""
            _bp = [" ".join(x.split()) for x in _bt.split("\f") if x.strip()]
            _bj = " ".join(_bt.split())
            _figs = (f"{hl['two_way_a_day']:,.0f}", f"{hl['movements_in_month']:,.1f}", f"{hl['routes_in_use']:,}", f"{hl['tonnes']:,.0f} t")
            ok("⭐ the bulletin PDF over HTTP: a PDF named for the month, not cached, \"fictional demo scheme\" on every page",
               r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf") and r.content[:5] == b"%PDF-"
               and r.headers.get("content-disposition") == 'attachment; filename="bulletin-2026-10.pdf"'
               and r.headers.get("cache-control") == "no-store" and len(_bp) >= 2
               and all("fictional demo scheme" in x.lower() for x in _bp), f"{r.status_code} {len(_bp)} pages")
            ok("⭐ ...page 1 carries the four headline figures equal to /api/bulletin/month's roll-up",
               bool(_bp) and all(f in _bp[0] for f in _figs), f"{_figs} | {_bp[0][:400] if _bp else ''}")
            ok("...the busiest route by its places, the stockpile over capacity, the never-checked routes, the carbon stamp, the planning flag",
               "Kilby Ridge Quarry to Harborough Compound" in _bj and "Stockpile Tilton has a capacity of 40,000 t" in _bj
               and "never checked for any of this month's routes" in _bj
               and "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" in _bj
               and "Route R016:" in _bj and "planning flag of 20 a day" in _bj, _bj[:600])
            ok("🔴 ...no team id, none of the banned words",
               not re.search(r"\bIPT\s*[-_ ]?\s*[1-6]\b", _bj) and not re.search(r"\b(secure|real[- ]time|telematics|optimi[sz]e|predict|live tracking)\b", _bj, re.I)
               and not re.search(r"\bAI\b", _bj))
            r = c.get("/bulletin/?month=10", headers=PLAN)
            ok("⭐ the bulletin page over HTTP with a code: HTML, not cached, the same four figures, the PDF alongside",
               r.status_code == 200 and r.headers.get("content-type", "").startswith("text/html")
               and r.headers.get("cache-control") == "no-store" and all(f in r.text for f in _figs)
               and 'href="/api/bulletin/month.pdf?month=10">Download the PDF</a>' in r.text
               and "Fictional demo scheme · nothing here is real" in r.text, f"{r.status_code} {r.text[:200]}")
            ok("...a team code is staff too: the page and the PDF open for the North Team code",
               c.get("/bulletin/?month=10", headers=NORTH).status_code == 200
               and c.get("/api/bulletin/month.pdf?month=10", headers=NORTH).status_code == 200)
            ok("🔴 ...a month outside the horizon is refused — 422", c.get("/api/bulletin/month.pdf?month=61", headers=PLAN).status_code == 422
               and c.get("/bulletin/?month=0", headers=PLAN).status_code == 422)
        finally:
            export.urllib.request.urlopen = _real_open
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

    # ------------------------------------------------- 3b. 12 Oct 2026 (§2.2d): shared road sections
    # The demo package ships 0 geometry rows, so the index is empty here: the endpoint must
    # still answer, say so, and never invent a section.
    r = c.get("/api/public/road-load", params={"month": 10})
    ok("⭐ /api/public/road-load answers 200 on the unbaked demo", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    rl = r.json() if r.status_code == 200 else {}
    # REVERSED 12 Oct 2026 (the review and fix pass): the feed counts what the public map bar counts — lines on routes
    # the map DRAWS. On the unbaked demo that is none, so the totals are empty and every October line is NAMED in
    # routes_not_drawn (until then they were counted in the totals, which the bar beside the map never shows)
    ok("...empty runs, the month, the loaded leg, the planning block's working days and a note naming the undrawn lines",
       rl.get("runs") == [] and rl.get("month") == 10 and rl.get("leg") == "loaded" and (rl.get("working_days") or 0) > 0
       and rl.get("totals", {}).get("runs") == 0 and rl.get("totals", {}).get("lines") == 0
       and any("no stored road route" in n and "routes_not_drawn" in n for n in rl.get("notes", [])), str(rl.get("notes")))
    ok("...and the October demo volume is NOT in the totals (the map draws none of it): all 19 lines named in routes_not_drawn",
       rl.get("totals", {}).get("routes_with_volume") == 0 and rl.get("totals", {}).get("trips") == 0
       and rl.get("routes_not_drawn", {}).get("lines") == 19 and len(rl.get("routes_not_drawn", {}).get("routes", [])) == 19
       and rl.get("totals", {}).get("co2_t") == 0.0, str(rl.get("totals")))
    _ret = c.get("/api/public/road-load", params={"month": 10, "leg": "return"})
    # NARROWED 12 Oct 2026: the status is checked too — called as a function, month-kpis' `unit` default was
    # FastAPI's Query object and this answered 400 "unit must be one of [...]"; the note is the LAST line
    ok("...the return leg answers 200 too, with its 'never added' note",
       _ret.status_code == 200 and (_ret.json().get("notes") or [""])[-1].startswith("Return leg"), _ret.text[:160])
    # NARROWED 12 Oct 2026 (the tenancy / wording review): the 400 reads as words, not a Python list
    _bad = c.get("/api/public/road-load", params={"month": 10, "leg": "x"})
    ok("an unknown leg is a 400 whose reason reads \"leg must be one of 'loaded' or 'return'\"",
       _bad.status_code == 400 and _bad.json().get("detail") == "leg must be one of 'loaded' or 'return'", _bad.text[:120])
    ok("⭐ the feed carries the Carbon page's planning-estimate stamp beside its CO2e figures (12 Oct 2026 review)",
       rl.get("carbon", {}).get("stamp") == "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures"
       and "approved plan only" in rl.get("carbon", {}).get("rule", ""), str(rl.get("carbon")))
    ok("a month out of range is a 422", c.get("/api/public/road-load", params={"month": 99}).status_code == 422)
    r = c.post("/api/admin/road-sections/rebuild")
    ok("🔴 the admin rebuild is 403 without the token", r.status_code == 403, str(r.status_code))
    ok("🔴 ...so are status and the diagnostic", c.get("/api/admin/road-sections/status").status_code == 403
       and c.get("/api/admin/diagnostics/road-sections").status_code == 403)
    r = c.post("/api/admin/road-sections/rebuild", params=TOKEN)
    ok("with the token the rebuild answers: 0 routes indexed, 0 runs, not stale", r.status_code == 200
       and r.json().get("routes_indexed") == 0 and r.json().get("runs") == 0 and r.json().get("stale") is False, r.text[:200])
    r = c.get("/api/admin/diagnostics/road-sections", params=TOKEN)
    ok("the diagnostic prints the status text", r.status_code == 200 and "0 routes indexed" in r.json().get("text", ""), r.text[:200])
    # 12 Oct 2026 (the tests-and-regressions review): status had only its 403 here; the 200 and the
    # diagnostic's leg check over the real transport
    r = c.get("/api/admin/road-sections/status", params=TOKEN)
    ok("with the token status answers 200: 0 routes indexed, both legs listed with 0 runs, not stale",
       r.status_code == 200 and r.json().get("routes_indexed") == 0 and r.json().get("stale") is False
       and set(r.json().get("legs", {})) == {"loaded", "return"} and r.json()["legs"]["return"]["runs"] == 0, r.text[:200])
    ok("the diagnostic refuses an unknown leg with 400 (token accepted)",
       c.get("/api/admin/diagnostics/road-sections", params=dict(TOKEN, leg="x")).status_code == 400)
    # ------------------------------------------------- 3c. 12 Oct 2026 (§2.2b, D27): movements and carbon per council
    # The shipped demo package carries no areas, so the feed answers empty and says so; the admin import of the seed
    # file (backend/data/areas_demo.geojson) loads the nine polygons over the real transport. Nothing is baked here,
    # so every area reads 0 movements and the clip is empty — the live clip runs on Render after a bake.
    r = c.get("/api/public/areas", params={"month": 10})
    ar = r.json() if r.status_code == 200 else {}
    ok("⭐ /api/public/areas answers 200 on the demo with no areas: empty, with the note and the working days",
       r.status_code == 200 and ar.get("areas") == [] and (ar.get("working_days") or 0) > 0
       and "No council areas are loaded for this tenant." in ar.get("notes", []) and ar.get("attribution") == [], r.text[:200])
    ok("a month out of range or no month is a 422", c.get("/api/public/areas", params={"month": 99}).status_code == 422
       and c.get("/api/public/areas").status_code == 422)
    AREAS_SEED = json.load(open(os.path.join(BACKEND, "data", "areas_demo.geojson"), encoding="utf-8"))
    ok("🔴 the areas import is 403 without the token, and so is the list",
       c.post("/api/admin/areas/import", json=AREAS_SEED).status_code == 403 and c.get("/api/admin/areas").status_code == 403)
    _bad_fc = {"type": "FeatureCollection", "features": AREAS_SEED["features"][:1]}          # no licence lines
    r = c.post("/api/admin/areas/import", params=TOKEN, json=_bad_fc)
    ok("an import with no licence lines is a 400 that says so (token accepted)",
       r.status_code == 400 and "licence lines" in r.json().get("detail", ""), r.text[:200])
    r = c.post("/api/admin/areas/import", params=TOKEN, json=AREAS_SEED)
    ok("⭐ with the token the seed imports: 9 areas (8 districts, 1 county), the two ONS lines, the clip empty (nothing baked)",
       r.status_code == 200 and r.json().get("imported") == 9 and r.json().get("tiers") == {"district": 8, "county": 1}
       and r.json().get("attribution") == sorted(AREAS_SEED["attribution"]) and r.json()["clip"]["rows"] == 0, r.text[:300])
    r = c.get("/api/admin/areas", params=TOKEN)
    ok("the admin list answers 200: nine areas without geometry, no route entering any (unbaked)",
       r.status_code == 200 and len(r.json().get("areas", [])) == 9 and all("geometry" not in a for a in r.json()["areas"])
       and all(a["routes_entering"] == [] for a in r.json()["areas"]), r.text[:200])
    r = c.get("/api/public/areas", params={"month": 10})
    ar = r.json() if r.status_code == 200 else {}
    _by = {a["name"]: a for a in ar.get("areas", [])}
    ok("⭐ the feed now serves the nine polygons with the two licence lines, 0 movements each (nothing drawn), 0.0 t",
       r.status_code == 200 and len(_by) == 9 and ar.get("attribution") == AREAS_SEED["attribution"]
       and all(a["movements_per_day"] == 0 and a["co2_t"] == 0.0 and a["geometry"]["type"] in ("Polygon", "MultiPolygon")
               for a in ar["areas"]), r.text[:200])
    ok("...the demo's sites where the package coordinates put them (Harborough 8, Melton 2, Blaby, Charnwood, Rutland 1)",
       [_by.get(n, {}).get("sites_count") for n in ("Harborough", "Melton", "Blaby", "Charnwood", "Rutland")] == [8, 2, 1, 1, 1])
    ok("...of the 13 the totals carry (the card's '8 of 13'), and one label point per area for the map's one label",
       ar.get("totals", {}).get("sites") == 13
       and all(isinstance(a.get("label_point"), list) and len(a["label_point"]) == 2 for a in ar.get("areas", [])), r.text[:200])
    ok("...and the October lines are named as undrawn, never counted in an area",
       len(ar.get("routes_not_drawn", [])) == 19 and ar.get("totals", {}).get("loads") == 0)
    # 12 Oct 2026 (Track C review): the polygons once (no month roll-up), the month's figures without them
    r = c.get("/api/public/areas/shapes")
    sh = r.json() if r.status_code == 200 else {}
    ok("⭐ Track C review: /api/public/areas/shapes serves the nine polygons, their label points and the two licence lines, and no month figure",
       r.status_code == 200 and len(sh.get("areas", [])) == 9 and sh.get("attribution") == AREAS_SEED["attribution"]
       and all(a["geometry"]["type"] in ("Polygon", "MultiPolygon") and len(a.get("label_point") or []) == 2 for a in sh["areas"])
       and all("movements_per_day" not in a for a in sh["areas"]), r.text[:200])
    r = c.get("/api/public/areas", params={"month": 10, "geometry": 0})
    ok("Track C review: /api/public/areas?geometry=0 gives the same figures without the polygons",
       r.status_code == 200 and len(r.json().get("areas", [])) == 9 and all("geometry" not in a and "label_point" not in a for a in r.json()["areas"])
       and [(a["area_id"], a["movements_per_day"]) for a in r.json()["areas"]] == [(a["area_id"], a["movements_per_day"]) for a in ar["areas"]], r.text[:200])
    # ------------------------------------------- 3d. the network behind the gate (12 Oct 2026, map review D18)
    # The twelve reads that needed no credential until today, read three ways: the staff COOKIE (this client, no
    # header), the planner CODE in the header with no cookie, and — at the end of this file — the MAP cookie and
    # nobody at all. The two staff writes under the same prefixes keep their own checks behind the gate.
    NETWORK_READS = ("/api/routes/status", "/api/routes/summary", "/api/routes/geojson", "/api/routes/R001/geometries",
                     "/api/routes/R001/analysis", "/api/routes/analysis-batch?route_ids=R001,R002", "/api/locations/geojson",
                     "/api/gates", "/api/haul-roads", "/api/routes/R001/haul-roads", "/api/routes/R001/restrictions",
                     "/api/routes/restrictions")
    import restrictions as _rx
    # the National Highways feed is never fetched from a harness: two closures, one current and far from every route,
    # one ENDED and drawn on the stretch R016 is given below
    _now_ms = int(__import__("time").time() * 1000)
    _day_ms = 86400000
    def _fake_nh_page(offset, count=_rx.NH_PAGE, timeout=None):
        if offset:
            return {"type": "FeatureCollection", "features": []}
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-2.5, 53.5], [-2.49, 53.51]]},
             "properties": {"OBJECTID": 2, "description": "Lane closure for barrier works", "road_number": "M6",
                            "eventtype": "Lane closure", "natureofworks": "Barrier works", "formattedeventnumber": "NH-0002",
                            "scheduledplannedstartdate": _now_ms - 2 * _day_ms, "scheduledplannedenddate": _now_ms + 400 * _day_ms}},
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-0.9, 52.7], [-0.895, 52.705]]},
             "properties": {"OBJECTID": 1, "description": "Carriageway closure for resurfacing, finished", "road_number": "A607",
                            "eventtype": "Carriageway closure", "natureofworks": "Resurfacing", "formattedeventnumber": "NH-0001",
                            "scheduledplannedstartdate": _now_ms - 40 * _day_ms, "scheduledplannedenddate": _now_ms - 10 * _day_ms}}]}
    _real_nh_page = _rx._nh_page
    _rx._nh_page = _fake_nh_page
    _rx.clear_cache()
    # R016 (cap 20 in the demo) baked by hand along the ended closure, both legs
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
               "duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("default", "R016", "Artic Tipper (44t)", "loaded", 0, "[[-0.9,52.7],[-0.89,52.71]]", 1.3, 0.05))
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
               "duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("default", "R016", "Artic Tipper (44t)", "return", 0, "[[-0.89,52.71],[-0.9,52.7]]", 1.3, 0.05))
    try:
        _codes = {p: c.get(p).status_code for p in NETWORK_READS}
        ok("⭐ D18: all twelve network reads answer 200 to the staff COOKIE alone (the app's iframe sends no header)",
           all(v == 200 for v in _codes.values()), str(_codes))
        _jar = c.cookies
        c.cookies = type(_jar)()
        try:
            _codes_hdr = {p: c.get(p, headers=PLAN).status_code for p in NETWORK_READS}
            _codes_none = {p: c.get(p).status_code for p in NETWORK_READS}
            _bodies_none = {p: c.get(p).json().get("detail") for p in NETWORK_READS}
            r_put_none = c.put("/api/routes/R999/status", json={"status": "Approved"})
            r_put_hdr = c.put("/api/routes/R999/status", json={"status": "Approved"}, headers=PLAN)
            r_put_north = c.put("/api/routes/R999/status", json={"status": "Approved"}, headers=NORTH)
            r_cap_none = c.put("/api/locations/L001/capacity", json={"capacity_qty": 1, "capacity_unit": "t"})
            r_cap_hdr = c.put("/api/locations/L001/capacity", json={"capacity_qty": 1, "capacity_unit": "t"}, headers=PLAN)
            r_who_plan = c.get("/api/public/whoami", headers=PLAN)
            r_who_north = c.get("/api/public/whoami", headers=NORTH)
            r_who_none = c.get("/api/public/whoami")
        finally:
            c.cookies = _jar
        ok("⭐ D18: ...and 200 to the planner CODE in the header with no cookie (the staff app's own fetches)",
           all(v == 200 for v in _codes_hdr.values()), str(_codes_hdr))
        ok("🔴 D18: ...and 401 to NOBODY — every one of the twelve, with the map's wording",
           all(v == 401 for v in _codes_none.values()) and all(d == "the map is password protected" for d in _bodies_none.values()),
           str(_codes_none) + str(_bodies_none)[:200])
        ok("🔴 D18: the staff WRITE PUT /api/routes/{id}/status with no credential is refused at the gate (401, the map's wording) — before its own approver check",
           r_put_none.status_code == 401 and r_put_none.json().get("detail") == "the map is password protected", r_put_none.text[:120])
        ok("D18: ...with the planner code it passes the gate unchanged and reaches its body (404: no forecast for R999)",
           r_put_hdr.status_code == 404 and "No forecast" in r_put_hdr.text, f"{r_put_hdr.status_code} {r_put_hdr.text[:80]}")
        ok("D18: ...and a team code passes the gate but is refused by the body's own approver check (403)",
           r_put_north.status_code == 403 and "cannot approve" in r_put_north.text, f"{r_put_north.status_code} {r_put_north.text[:80]}")
        ok("D18: PUT /api/locations/{id}/capacity: 401 at the gate with nothing; with a code the body's admin check answers (403, no token)",
           r_cap_none.status_code == 401 and r_cap_hdr.status_code == 403 and "admin token" in r_cap_hdr.text,
           f"{r_cap_none.status_code} {r_cap_hdr.status_code} {r_cap_hdr.text[:80]}")
        ok("⭐ whoami: the planner code is staff with no team; the North Team code is staff with its team's NAME",
           r_who_plan.status_code == 200 and r_who_plan.json() == {"level": "staff", "team_label": None}
           and r_who_north.status_code == 200 and r_who_north.json() == {"level": "staff", "team_label": "North Team"},
           f"{r_who_plan.text} {r_who_north.text}")
        ok("🔴 whoami: never a code, never a team id", "IPT" not in r_who_north.text and "north-code-xyz" not in r_who_north.text
           and "plan-code-xyz" not in r_who_plan.text and r_who_none.status_code == 401)
        # §2.5 row 2: the cap on the public map's route features
        _md = c.get("/api/public/map-data").json()
        _lines = {(f["properties"]["route_id"], f["properties"]["leg"]): f["properties"] for f in _md["features"]
                  if f["geometry"]["type"] == "LineString" and f["properties"].get("route_id")}
        ok("⭐ §2.5: the hand-baked R016 draws both legs on the public map and BOTH carry max_vehicles_per_day 20 (its typed cap)",
           set(_lines) == {("R016", "loaded"), ("R016", "return")} and all(p["max_vehicles_per_day"] == 20 for p in _lines.values()),
           str({k: v.get("max_vehicles_per_day") for k, v in _lines.items()}))
        # §2.2c (c) and §2.3: the restriction check and the drawn layer, over HTTP, against the stubbed feed
        r = c.get("/api/routes/restrictions")
        ok("§2.2c: GET /api/routes/restrictions by default sees no hit — the only closure on R016 has ENDED",
           r.status_code == 200 and r.json()["routes"] == {} and r.json()["current_only"] is True
           and r.json()["expired_or_future_excluded"] == 1, r.text[:200])
        r = c.get("/api/routes/restrictions?include_expired=1")
        _h = (r.json().get("routes") or {}).get("R016", {}).get("hits") or []
        ok("⭐ §2.2c: ...and with include_expired=1 R016 lists the ended closure NH-0001 with its dates, so a past month can show it",
           r.status_code == 200 and r.json()["current_only"] is False and sorted({x["event_number"] for x in _h}) == ["NH-0001"]
           and all(x["from"] and x["to"] for x in _h), r.text[:300])
        r = c.get("/api/restrictions")
        _fc0 = r.json()
        ok("§2.3: GET /api/restrictions by default carries the one current closure and reports the ended one dropped",
           r.status_code == 200 and [f["properties"]["event_number"] for f in _fc0["features"]] == ["NH-0002"]
           and _fc0["expired_or_future"] == 1 and _fc0["total_records"] == 2 and "clipped" not in _fc0, r.text[:200])
        r = c.get("/api/restrictions?include_expired=1&bbox=-1.0,52.6,-0.8,52.8")
        _fc1 = r.json()
        ok("⭐ §2.3: ...bbox=<the corridor>&include_expired=1 keeps only the closure inside the window and says it clipped 1",
           r.status_code == 200 and [f["properties"]["event_number"] for f in _fc1["features"]] == ["NH-0001"]
           and _fc1["clipped"] == 1 and _fc1["bbox"] == [-1.0, 52.6, -0.8, 52.8] and _fc1["counts"] == {"nh_closures": 1}, r.text[:200])
        r = c.get("/api/restrictions?bbox=10,10,11,11")
        ok("§2.3: a window with nothing in it is an empty collection, clipped 1 (the ended one was already dropped by the default read)",
           r.status_code == 200 and r.json()["features"] == [] and r.json()["clipped"] == 1, r.text[:200])
        r = c.get("/api/restrictions?bbox=junk")
        ok("🔴 §2.3: a bad bbox is a 400 that says the shape", r.status_code == 400 and "west,south,east,north" in r.text, r.text[:120])
    finally:
        _rx._nh_page = _real_nh_page
        _rx.clear_cache()
        db.execute("DELETE FROM route_geometry WHERE tenant_id = ? AND route_id = ?", ("default", "R016"))

    # ------------------------------------------------------------ 4. export and replace
    r = c.get("/api/admin/tenant/export", params=TOKEN)
    ok("⭐ the tenant exports as a JSON attachment", r.status_code == 200
       and r.headers.get("content-type", "").startswith("application/json")
       and "attachment" in r.headers.get("content-disposition", ""), str(r.status_code))
    pkg = r.json() if r.status_code == 200 else {}
    ok("...a valid package of the same size", pkg.get("modus_package") == 1
       and len(pkg["tables"]["routes"]) == 20 and len(pkg["tables"]["forecasts"]) == 78
       and len(pkg["tables"]["forecast_weeks"]) == 342 and len(pkg["tables"]["location_gates"]) == 16)
    ok("...and it carries the route_sections table (empty: nothing is baked here)",
       "route_sections" in pkg.get("tables", {}) and pkg["tables"]["route_sections"] == [])
    ok("...and the nine council areas imported above, with an empty clip table (§2.2b)",
       len(pkg.get("tables", {}).get("areas", [])) == 9 and pkg["tables"].get("route_area_km") == [])
    r = c.post("/api/admin/tenant/import", params=dict(TOKEN, replace=1), json=pkg)
    ok("⭐ replace=1 re-imports the exported tenant over itself", r.status_code == 200 and r.json().get("replaced") is True,
       r.text[:160])
    m2 = c.get("/api/meta").json()
    ok("...and nothing is lost or doubled", len(m2["routes"]) == 20 and len(m2["ipts"]) == 3
       and len(c.get("/api/forecasts", headers=PLAN).json()) == 78)
    ok("...and the council areas came back with the package (9)",
       len(c.get("/api/admin/areas", params=TOKEN).json().get("areas", [])) == 9)

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
        ok("🔴 ...and so is /api/public/road-load (12 Oct 2026, §2.2d)",
           c.get("/api/public/road-load", params={"month": 10}).status_code == 401)
        ok("🔴 ...and so is /api/public/areas (12 Oct 2026, §2.2b)",
           c.get("/api/public/areas", params={"month": 10}).status_code == 401)
        ok("🔴 ...and so is /api/public/areas/shapes (Track C review, 12 Oct 2026)",
           c.get("/api/public/areas/shapes").status_code == 401)
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
    ok("🔴 D18: ...and so is the network — the twelve reads answer 401 to the signed-out visitor",
       all(c.get(p).status_code == 401 for p in NETWORK_READS))
    r = c.post("/api/map-auth", json={"password": "map-pass-xyz"})
    ok("the map password opens the map…", r.status_code == 200 and c.get("/map/").status_code == 200)
    ok("…but 🔴 not the guide", c.get("/help/").status_code == 401)
    ok("…and 🔴 not the monthly bulletin (staff only, D10)", c.get("/bulletin/?month=10").status_code == 401
       and c.get("/api/bulletin/month.pdf?month=10").status_code == 401)
    # 12 Oct 2026 (D18 / D31 / whoami): the MAP cookie — the outside viewer with the shared password
    _codes_map = {p: c.get(p).status_code for p in NETWORK_READS}
    ok("⭐ D18: the map cookie opens all twelve network reads (the public-safe reads the map draws from)",
       all(v == 200 for v in _codes_map.values()), str(_codes_map))
    r = c.get("/api/public/areas", params={"month": 10})
    ok("⭐ §2.2b: the map cookie reads the council areas (the outside viewer is the audience, D27) — the nine polygons",
       r.status_code == 200 and len(r.json().get("areas", [])) == 9, f"{r.status_code} {r.text[:120]}")
    ok("🔴 ...but not the admin list or import", c.get("/api/admin/areas").status_code == 403
       and c.post("/api/admin/areas/import", json={"type": "FeatureCollection", "features": []}).status_code == 403)
    r = c.get("/api/public/whoami")
    ok("⭐ whoami: the map cookie is level `map`, no team", r.status_code == 200 and r.json() == {"level": "map", "team_label": None}, r.text)
    _mm = c.get("/api/meta").json()
    ok("🔴 D31: the map cookie is NOT staff — /api/meta stays the public shape (no routes, no teams, no sections) while the map still gets its factors and seasonal windows",
       _mm["scope"] == "public" and _mm["routes"] == [] and _mm["ipts"] == [] and _mm["work_sections"] == []
       and isinstance(_mm["factors"], dict) and isinstance(_mm["seasonal_restrictions"], list), str(_mm.get("scope")))
    r = c.put("/api/routes/R001/status", json={"status": "Approved"})
    ok("🔴 D18: the map cookie passes the gate on the staff write but the body's own check refuses it — 401 with the STAFF wording (sign in), nothing approved",
       r.status_code == 401 and "access code" in r.text and "password" not in r.text, f"{r.status_code} {r.text[:100]}")
    r = c.put("/api/locations/L001/capacity", json={"capacity_qty": 1, "capacity_unit": "t"})
    ok("🔴 D18: ...and the capacity write is refused by its admin check (403)", r.status_code == 403, f"{r.status_code} {r.text[:80]}")

    # 12 Oct 2026 (the review and fix pass): the app's Sign out on a shared machine. It used to clear the code in the
    # tab only, so the 12-hour STAFF cookie kept the staff shape of /api/meta, whoami "staff" and /help/ open to the
    # next person. Now it POSTs /api/gate-signout?keep=map: the staff cookie becomes a map cookie (expiring no later).
    r = c.post("/api/auth", json={"code": "plan-code-xyz"})
    ok("⭐ the STAFF cookie alone opens the monthly bulletin page (the Dashboard's link opens it in a new tab with no header)",
       r.status_code == 200 and c.get("/bulletin/?month=10").status_code == 200)
    ok("sign-out check: a planner sign-in sets the STAFF cookie (whoami staff, /help/ open, the staff /api/meta, all without a header)",
       r.status_code == 200 and c.get("/api/public/whoami").json().get("level") == "staff"
       and c.get("/help/").status_code == 200 and c.get("/api/meta").json().get("scope") == "staff")
    r = c.post("/api/gate-signout", params={"keep": "map"})
    ok("⭐ Sign out (keep=map): 200, and the same machine is now MAP level — whoami says map", r.status_code == 200
       and c.get("/api/public/whoami").json() == {"level": "map", "team_label": None}, c.get("/api/public/whoami").text)
    _mo = c.get("/api/meta").json()
    ok("🔴 ...the staff surface is closed to the next person: /api/meta is the public shape and /help/ is refused",
       _mo.get("scope") == "public" and _mo.get("routes") == [] and _mo.get("ipts") == [] and c.get("/help/").status_code == 401,
       str(_mo.get("scope")))
    ok("🔴 ...and the monthly bulletin is closed to the next person too", c.get("/bulletin/?month=10").status_code == 401)
    ok("⭐ ...while the public map still opens on that machine", c.get("/map/").status_code == 200)
    r = c.post("/api/gate-signout", params={"keep": "map"})
    ok("...a second keep=map sign-out on a map cookie leaves it alone (still map)", r.status_code == 200
       and c.get("/api/public/whoami").json().get("level") == "map")
    r = c.get("/api/admin/road-sections/status", params={"token": "é-not-the-token"})
    ok("🔴 a non-ASCII admin token is a 403, not a 500 (hmac.compare_digest on str raised TypeError)", r.status_code == 403,
       f"{r.status_code} {r.text[:80]}")

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

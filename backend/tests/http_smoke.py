"""
http_smoke.py — the REAL HTTP layer, end to end. Modus G2, 16 Sep 2026.

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
    ok("the app page is served, named Modus, with no-cache", r.status_code == 200 and "Modus" in r.text
       and r.headers.get("cache-control") == "no-cache", str(r.status_code))
    r = c.get("/map/")
    ok("🔴 the map is closed without a credential — the password page, 401",
       r.status_code == 401 and "password" in r.text.lower(), str(r.status_code))
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
    ok("...and carries the default tenant words: Modus, Team, EUR, no country",
       m["tenant"]["name"] == "Modus" and m["tenant"]["team_label"] == "Team"
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
       r.status_code == 200 and "overlay.js" in r.text and "Modus" in r.text, str(r.status_code))
    r = c.get("/map/overlay.js")
    ok("the overlay module is served", r.status_code == 200 and "applyOverlayPackage" in r.text)
    r = c.get("/map/data/alignment.js")
    ok("🔴 no static alignment file is served — 404", r.status_code == 404, str(r.status_code))
    r = c.get("/help/")
    ok("with the staff cookie the guide opens, as Modus", r.status_code == 200 and "Modus — User guide" in r.text,
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
    ok("...with every table's rows inserted",
       res.get("inserted", {}).get("routes") == 18 and res["inserted"].get("forecasts") == 72
       and res["inserted"].get("forecast_weeks") == 324, str(res.get("inserted")))
    ok("...and the GB diesel price applied", res.get("fuel_index_applied") == ["GB"], str(res.get("fuel_index_applied")))
    r = c.post("/api/admin/tenant/import", params=TOKEN, json=DEMO)
    ok("🔴 a second import into a non-empty tenant is refused — 400",
       r.status_code == 400 and "already holds data" in r.text, r.text[:160])

    m = c.get("/api/meta").json()
    ok("meta now reads the demo tenant: its name, £, GB",
       m["tenant"]["name"].startswith("Wolds Link") and m["tenant"]["currency_symbol"] == "£"
       and m["tenant"]["country"] == "GB", str(m["tenant"]))
    ok("...three named teams, eight sections, eighteen routes",
       [i["label"] for i in m["ipts"]] == ["North Team", "Central Team", "South Team"]
       and len(m["work_sections"]) == 8 and len(m["routes"]) == 18,
       str([i["label"] for i in m["ipts"]]))

    r = c.post("/api/auth", json={"code": "north-code-xyz"})
    ok("⭐ a team code signs in under the team's NAME", r.status_code == 200
       and r.json()["label"] == "North Team" and r.json()["ipt"] == "IPT1", r.text[:160])
    ok("...and the planner picker offers the tenant's three slots, not six",
       c.post("/api/auth", json={"code": "plan-code-xyz"}).json().get("ipts") == ["IPT1", "IPT2", "IPT3"])

    r = c.get("/api/public/alignment")
    b = r.json()
    ok("⭐ the map overlay arrives: version, six bands, five boundaries, the view",
       b.get("version") == "wolds-link-demo-1" and len(b.get("bands", [])) == 6
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

    r = c.get("/api/restrictions/layers")
    ok("GB → still no restriction provider", r.json().get("provider") is None)
    r = c.get("/api/fuel-index", headers=PLAN)
    fi = r.json() if r.status_code == 200 else {}
    idx = fi.get("index") or {}
    ok("GB → no automatic fuel bulletin, and the demo's typed GB price is the index",
       r.status_code == 200 and idx.get("country") == "GB" and idx.get("auto_available") is False
       and idx.get("eur_per_l") == 1.43, str(idx)[:200])

    # ------------------------------------------------------- 3. the data, as people read it
    r = c.get("/api/forecasts", headers=PLAN)
    rows = r.json() if r.status_code == 200 else []
    ok("a planner sees all 72 forecast rows", r.status_code == 200 and len(rows) == 72, f"{r.status_code} {len(rows)}")
    r = c.get("/api/forecasts", headers=NORTH)
    nrows = r.json() if r.status_code == 200 else []
    ok("⭐ the North Team code sees ONLY North Team's rows",
       r.status_code == 200 and nrows and all(x.get("ipt") == "IPT1" for x in nrows) and len(nrows) < len(rows),
       f"{r.status_code} {len(nrows)}")
    r = c.get("/api/forecasts")
    ok("🔴 forecasts without a code — 401", r.status_code == 401, str(r.status_code))

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
        try:  # poppler's pdftotext, when the machine has it (CI installs poppler-utils)
            import subprocess
            txt = subprocess.run(["pdftotext", "-layout", os.path.join(TMP, "week.pdf"), "-"],
                                 capture_output=True, text=True, timeout=60).stdout
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
       and len(pkg["tables"]["routes"]) == 18 and len(pkg["tables"]["forecasts"]) == 72
       and len(pkg["tables"]["forecast_weeks"]) == 324)
    r = c.post("/api/admin/tenant/import", params=dict(TOKEN, replace=1), json=pkg)
    ok("⭐ replace=1 re-imports the exported tenant over itself", r.status_code == 200 and r.json().get("replaced") is True,
       r.text[:160])
    m2 = c.get("/api/meta").json()
    ok("...and nothing is lost or doubled", len(m2["routes"]) == 18 and len(m2["ipts"]) == 3
       and len(c.get("/api/forecasts", headers=PLAN).json()) == 72)

    r = c.post("/api/gate-signout")
    c.cookies.clear()
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

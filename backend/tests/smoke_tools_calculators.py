"""
smoke_tools_calculators.py — the REAL app serving the haul calculators (claude/tools-calculators, 17 Nov 2026).

    pip install -r backend/requirements.txt httpx      # .venv-smoke, or CI
    python backend/tests/smoke_tools_calculators.py

Boots `main.app` with FastAPI's TestClient on a scratch SQLite database, the gate ON (MAP_PASSWORD set) and staff codes set,
and asks as an OUTSIDER with no cookie at all:

  1. /tools/calculators and /tools/calculators.js answer, no demo bar, every security header, no cookie set;
  2. /api/tools/calculators/sum answers the three example answers of card 2, refuses each missing figure with one plain
     sentence (and nothing else in the answer), is no-store with no Set-Cookie, and stops at its limit with the limit's sentence;
  3. /api/tools/calculators/pdf returns a one-page PDF (base64) for a good email, refuses a bad one in a sentence, answers a
     machine (the trap box) as if it worked with no file, and stops at its own limit;
  4. no call writes an audit row or moves db.data_version (the kept bulletin and CLP draft survive a calculator press);
  5. the figures sent decide the answer: a cookie-less call reads nothing of the demo's plan.

NOT covered: PostgreSQL (SQLite only), a browser (the UI audit walks the page), Render's proxy (the edge's address header
is sent by hand).
"""
import base64
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
except Exception as e:  # the stubbed sandbox
    print(f"smoke_tools_calculators.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_toolcalc_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY", "MAP_GATE", "SMTP_USER", "SMTP_PASSWORD", "DEMO_LEADS",
          "OS_MAPS_KEY", "LANDING_URL"):
    os.environ.pop(v, None)
os.environ.update({
    "ADMIN_TOKEN": "adm-token-toolcalc",
    "PLANNER_CODE": "plan-code-toolcalc",
    "IPT1_CODE": "north-code-toolcalc",
    "MAP_PASSWORD": "map-pass-toolcalc",
    "GATE_SECRET": "gate-secret-for-tests-only",
    "WAYSCOPE_WARM_CACHE": "0",
})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "toolcalc.db")
import main  # noqa: E402
import security_headers  # noqa: E402
import tools_calculators as tc  # noqa: E402
import tools_public  # noqa: E402
from portable import pdf_text  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  {extra}"[:600])


BASE = "https://testserver"
SEC = [k for k in security_headers.HEADERS]
HDR = {"X-Wayscope": "1", "CF-Connecting-IP": "203.0.113.77"}
FLAT = "Artic Flatbed (44t)"
SUM = "/api/tools/calculators/sum"
PDF = "/api/tools/calculators/pdf"
GOOD = {
    "lorries": dict(tonnes="2,500", lorry="Artic Flatbed (44t)", working_days="22", round_trips="6"),
    "carbon": dict(loads="90", miles="9.2", lorry="Artic Flatbed (44t)", way_back="Empty"),
    "surcharge": dict(diesel_then="140.0", diesel_now="154.0", share="30", rate="180.00"),
}


def clean(resp):
    return all(k.lower() in (h.lower() for h in resp.headers.keys()) for k in SEC) and "set-cookie" not in resp.headers


def post(c, path, body, ip=None):
    h = dict(HDR)
    if ip:
        h["CF-Connecting-IP"] = ip
    return c.post(path, json=body, headers=h)


with TestClient(main.app, base_url=BASE) as anon:
    ok("0. the outsider holds no cookie", not anon.cookies)

    # ---- 1. the page and its script -------------------------------------------------------------------------------- #
    r = anon.get("/tools/calculators")
    ok("1. ⭐ /tools/calculators answers an outsider with no cookie, the gate ON", r.status_code == 200
       and r.content == (ROOT / "frontend/tools/calculators.html").read_bytes(), str(r.status_code))
    ok("1. ...HTML, no-cache, every security header, no cookie set", r.headers.get("content-type", "").startswith("text/html")
       and r.headers.get("cache-control") == "no-cache" and clean(r), str(dict(r.headers)))
    ok("1. 🔴 no demo bar on the page", "DEMO" not in r.text and "Fictional" not in r.text and "demo-bar" not in r.text.lower())
    r = anon.get("/tools/calculators.js")
    ok("1. /tools/calculators.js is served as a script, with every header, no cookie", r.status_code == 200
       and r.headers.get("content-type", "").startswith("text/javascript") and clean(r)
       and r.content == (ROOT / "frontend/tools/calculators.js").read_bytes())
    ok("1. the page's CSP lets its own script run and no outside one (script-src 'self'-style header kept)",
       "script-src" in anon.get("/tools/calculators").headers.get("content-security-policy", "script-src"))

    ver0 = db.data_version()
    # ---- 2. the sums ------------------------------------------------------------------------------------------------ #
    want = {"lorries": ("1 lorry", "90 loads · about 4 loads a day"),
            "carbon": ("1.16 t CO₂e", "12.8 kg a trip · transport only · a planning estimate"),
            "surcharge": ("3.0 % surcharge", "£185.40 a load")}
    for which, (ans, det) in want.items():
        r = post(anon, SUM, {"which": which, "figures": GOOD[which]})
        j = r.json() if r.status_code == 200 else {}
        ok(f"2. ⭐ {which}: the open call answers card 2's figures, '{ans}'", r.status_code == 200 and j.get("answer") == ans and j.get("detail") == det, r.text[:200])
        ok(f"2. {which}: nothing but which, answer and detail comes back (no figure of the platform)", set(j) == {"which", "answer", "detail"}, str(set(j)))
        ok(f"2. {which}: no-store, every header, no Set-Cookie", "no-store" in r.headers.get("cache-control", "") and clean(r), str(dict(r.headers)))
    r = post(anon, SUM, {"which": "carbon", "figures": dict(GOOD["carbon"], way_back="Loaded")})
    ok("2. 'Loaded' reads 16.0 kg a trip through the open call", "16.0 kg a trip" in r.json().get("detail", ""), r.text[:200])
    r = post(anon, SUM, {"which": "lorries", "figures": {}})
    ok("2. 🔴 a missing figure is a 400 with one plain sentence under detail.say", r.status_code == 400 and r.json() == {"detail": {"say": "Type the tonnes to move."}}, r.text[:200])
    r = post(anon, SUM, {"which": "flying", "figures": {}})
    ok("2. 🔴 an unknown calculator is a 400 and a sentence", r.status_code == 400 and r.json()["detail"]["say"] == "Pick one of the three calculators.", r.text[:200])
    for junk in ("not json", "[1,2]", ""):
        r = anon.post(SUM, content=junk, headers=dict(HDR, **{"Content-Type": "application/json"}))
        ok(f"2. 🔴 a body that is not an object ({junk!r}) is a sentence, never a crash", r.status_code == 400 and "say" in r.json().get("detail", {}), f"{r.status_code} {r.text[:120]}")
    r = anon.post(SUM, json={"which": "lorries", "figures": GOOD["lorries"]}, headers={"X-Wayscope": "1"})
    ok("2. a call with no address header still answers (the guard reads the peer)", r.status_code == 200)
    # the limit
    tc.SUM_LIMIT.reset()
    codes = [post(anon, SUM, {"which": "lorries", "figures": GOOD["lorries"]}, ip="198.51.100.200").status_code for _ in range(tc.SUM_LIMIT.most + 2)]
    ok("2. ⭐ the 300th call from one address answers and the 301st is a 429", codes[:300] == [200] * 300 and codes[300:] == [429, 429], str(codes[298:303]))
    r = post(anon, SUM, {"which": "lorries", "figures": GOOD["lorries"]}, ip="198.51.100.200")
    ok("2. ...with the limit's own sentence and nothing else", r.status_code == 429 and r.json() == {"detail": {"say": tc.SUM_LIMIT.say}}
       and r.json()["detail"]["say"] == "Too many checks from this connection. Please try again in an hour.", r.text[:200])
    r = post(anon, SUM, {"which": "lorries", "figures": GOOD["lorries"]}, ip="198.51.100.201")
    ok("2. ...another address is not held up", r.status_code == 200)
    # one address cannot dodge the limit with a made-up forwarded-for entry
    r = anon.post(SUM, json={"which": "lorries", "figures": GOOD["lorries"]},
                  headers={"X-Wayscope": "1", "CF-Connecting-IP": "198.51.100.200", "X-Forwarded-For": "192.0.2.99"})
    ok("2. 🔴 a made-up forwarded-for entry does not escape the limit (the edge's own header counts)", r.status_code == 429, str(r.status_code))
    tc.SUM_LIMIT.reset()

    # ---- 3. the PDF ------------------------------------------------------------------------------------------------- #
    tc.PDF_LIMIT.reset()
    r = post(anon, PDF, {"which": "carbon", "figures": GOOD["carbon"], "email": "name@example.co.uk", "news": False, "website": ""})
    j = r.json() if r.status_code == 200 else {}
    raw = base64.b64decode(j.get("pdf", "")) if j else b""
    ok("3. ⭐ a good email: the PDF comes back at once (base64, named for its calculator)", r.status_code == 200 and raw[:5] == b"%PDF-"
       and j.get("filename") == "wayscope-carbon.pdf" and j.get("ok") is True, r.text[:200])
    txt = pdf_text(raw)
    ok("3. ...one page, the answer, 'A planning estimate', no organisation, no demo notice", txt.count("\f") == 1 and "1.16 t CO₂e" in txt
       and "A planning estimate" in txt and "DEMO" not in txt and "Fictional" not in txt and "Wolds" not in txt, txt[:300])
    ok("3. ...no-store, every header, no cookie", "no-store" in r.headers.get("cache-control", "") and clean(r))
    kept = db.query("SELECT * FROM tool_leads")
    ok("3. ⭐ ...and one row is kept: 'calculator-pdf', the tick 0, the address only as a hash", len(kept) == 1 and kept[0]["kind"] == "calculator-pdf"
       and kept[0]["news"] == 0 and kept[0]["email"] == "name@example.co.uk" and "203.0.113.77" not in str(kept[0])
       and kept[0]["ip_hash"] == tools_public.address_hash("203.0.113.77"), str(kept))
    ok("3. 🔴 ...and the row reads 'kept', not 'queued' (nothing is sent for a download)", kept[0]["status"] == "kept", str(kept[0]["status"]))
    r = post(anon, PDF, {"which": "carbon", "figures": GOOD["carbon"], "email": "nobody"})
    ok("3. 🔴 a bad email is a sentence", r.status_code == 400 and r.json() == {"detail": {"say": "That email does not look right. Check it and try again."}}, r.text[:200])
    r = post(anon, PDF, {"which": "carbon", "figures": GOOD["carbon"], "email": ""})
    ok("3. 🔴 no email is a sentence", r.status_code == 400 and r.json()["detail"]["say"] == "Type your email to download the PDF.", r.text[:200])
    r = post(anon, PDF, {"which": "carbon", "figures": GOOD["carbon"], "email": "a@b.co", "website": "http://spam.example"})
    ok("3. 🔴 the trap box filled: answered as if it worked, no file", r.status_code == 200 and r.json() == {"ok": True}, r.text[:200])
    ok("3. 🔴 ...and nothing kept for it, nor for the refusals before it", db.query("SELECT COUNT(*) AS n FROM tool_leads")[0]["n"] == 1)
    for which in ("lorries", "surcharge"):
        r = post(anon, PDF, {"which": which, "figures": GOOD[which], "email": "name@example.co.uk"})
        ok(f"3. the {which} PDF too", r.status_code == 200 and base64.b64decode(r.json()["pdf"])[:5] == b"%PDF-")
    r = post(anon, PDF, {"which": "lorries", "figures": {"tonnes": ""}, "email": "name@example.co.uk"})
    ok("3. figures that do not work: the sum's sentence, no file", r.status_code == 400 and r.json()["detail"]["say"] == "Type the tonnes to move.", r.text[:200])
    tc.PDF_LIMIT.reset()
    codes = [post(anon, PDF, {"which": "lorries", "figures": GOOD["lorries"], "email": "a@b.co"}, ip="198.51.100.210").status_code for _ in range(tc.PDF_LIMIT.most + 1)]
    ok("3. ⭐ the PDF's limit: 20 answer, the 21st is a 429 with the sentence", codes[:20] == [200] * 20 and codes[20] == 429, str(codes[18:]))
    tc.PDF_LIMIT.reset()

    # ---- 3b. odd values: an answer or one plain sentence, never an uncaught error -------------------------------------- #
    tc.SUM_LIMIT.reset(); tc.PDF_LIMIT.reset()
    ODD = [[1], {}, "x", None, True, "1e999", "inf", "-inf", "nan", -1, 0, "", "  ", "1e-320", 1e308, "9" * 400, {"a": 1}, [[]], "\u0000", "é"]
    bad = []
    for which in ("lorries", "carbon", "surcharge", [1], {}, None, "x"):
        for odd in ODD:
            for body in ({"which": which, "figures": odd}, {"which": which, "figures": {k: odd for k in
                         ("tonnes", "lorry", "working_days", "round_trips", "loads", "miles", "way_back", "diesel_then", "diesel_now", "share", "rate")}}):
                tc.SUM_LIMIT.reset()
                r = post(anon, SUM, body)
                if not (r.status_code == 200 or (r.status_code == 400 and isinstance(r.json().get("detail", {}).get("say"), str))):
                    bad.append((str(body)[:80], r.status_code, r.text[:80]))
    ok("3b. ⭐ odd values at the sum call: an answer or one plain sentence, never an error", not bad, str(bad[:3]))
    bad = []
    spread = dict(GOOD["lorries"])
    for em in (["a@b.co"], {"a": 1}, 5, True, None, "a@b.co" * 100, "a@b.co\n", "  a@b.co  "):
        for news in ("yes", [1], {}, None, 0, True):
            for which in ("lorries", [1], {}, None, "x"):
                tc.PDF_LIMIT.reset()
                r = post(anon, PDF, {"which": which, "figures": GOOD["lorries"], "email": em, "news": news})
                if not (r.status_code in (200, 400) and (r.status_code == 200 or isinstance(r.json().get("detail", {}).get("say"), str))):
                    bad.append((str(em)[:30], str(news), str(which), r.status_code, r.text[:80]))
    for fig in ("x", [1], {}, None, 5, {"tonnes": [1], "lorry": {}}):
        for web in (None, [], {}, 0, ""):
            tc.PDF_LIMIT.reset()
            r = post(anon, PDF, {"which": "lorries", "figures": fig, "email": "a@b.co", "website": web})
            if r.status_code not in (200, 400):
                bad.append(("figures", str(fig)[:30], str(web), r.status_code, r.text[:80]))
    ok("3b. ⭐ odd values at the PDF call: an answer or one plain sentence, never an error", not bad, str(bad[:3]))
    tc.SUM_LIMIT.reset(); tc.PDF_LIMIT.reset()

    # ---- 4. nothing written, nothing emptied ------------------------------------------------------------------------ #
    ok("4. 🔴 no calculator call moved db.data_version (the kept reads survive a press)", db.data_version() == ver0, f"{ver0} -> {db.data_version()}")
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM audit_log")
        n = cur.fetchone()[0]
    finally:
        db.put_conn(conn) if hasattr(db, "put_conn") else conn.close()
    ok("4. 🔴 no calculator call wrote an audit row", n == 0, str(n))

    # ---- 5. an outsider's other doors stay shut --------------------------------------------------------------------- #
    for path in ("/api/tools/calculators", "/api/tools/calculators/other"):
        r = anon.post(path, json={}, headers=HDR)
        ok(f"5. {path} is not a route", r.status_code in (404, 405))
    r = anon.get("/api/tools/calculators/sum", headers=HDR)
    ok("5. the sum is a POST only (a GET with figures in the address is not answered)", r.status_code == 405, str(r.status_code))
    r = anon.get("/api/admin/demo-requests.csv")
    ok("5. a staff call still refuses an outsider", r.status_code in (401, 403))

print(f"smoke_tools_calculators: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)

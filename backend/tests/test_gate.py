"""
The /map/ and /help/ gate, 2026-09-14.

WHAT IS ASSERTED
----------------
The whole policy, because the whole policy is one pure function. Every combination of
(scope, valid code, cookie level, password configured, gate on/off) is walked; the
cookie is round-tripped, forged, expired, tampered with and re-keyed; and the decision
that matters most — no password configured means CLOSED, not open — is asserted
directly, because that is where ADMIN_TOKEN got it wrong (open question C11).

Then, at source level: that main.py actually calls it, that a staff sign-in sets the
cookie the iframe needs, and that the refusal pages are NOT filed under map/ or
frontend/help/ — a password page inside the thing it guards could never be shown.

WHAT THIS DOES NOT PROVE
------------------------
  * The HTTP layer is stubbed. The middleware is never executed, no real request is
    routed, `response.set_cookie` is never called and no `Set-Cookie` header is ever
    produced. Everything below reads main.py as TEXT for that half.
  * Nothing in a browser. The password page's fetch() has never run.
  * Nothing proves Render sends the cookie back over HTTPS — `secure: True` is asserted
    as a value in a dict, not observed on a wire.

Run:  python3 backend/tests/test_gate.py
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

import gate  # noqa: E402  — stdlib only, no stubbing needed

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def env(**kw):
    """Set or clear env vars. gate.py reads os.environ on every call — nothing caches,
    which is what lets a password rotation invalidate live cookies."""
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def clean(password="corridor-2026", admin="tok", gate_on=True, secret=None):
    env(MAP_PASSWORD=password, ADMIN_TOKEN=admin, GATE_SECRET=secret,
        MAP_GATE=None if gate_on else "off")


# ---------------------------------------------------------------- 1. scope_for
clean()
for p in ("/map", "/map/", "/map/index.html", "/map/data/alignment.js", "/map/?v=123"):
    ok(f"scope_for({p!r}) is the map", gate.scope_for(p) == "map")
for p in ("/help", "/help/", "/help/index.html", "/help/media/S04.png"):
    ok(f"scope_for({p!r}) is help", gate.scope_for(p) == "help")
for p in ("/api/public/month-kpis", "/api/public/route-forecasts?from=1&to=4",
          "/api/zones", "/api/restrictions/layers", "/api/routes/restrictions",
          "/api/streetview", "/api/streetview/meta"):
    ok(f"scope_for({p!r}) is map — the map's DATA is gated, not just its page",
       gate.scope_for(p) == "map")

# 12 Oct 2026 (map review D18): the tenant's NETWORK. Twelve data reads needed no credential at
# all; now they are the map's, readable with a valid code or the map cookie and nothing without.
for p in ("/api/routes/status", "/api/routes/summary", "/api/routes/geojson?profile=Artic",
          "/api/routes/R001/geometries", "/api/routes/R001/analysis",
          "/api/routes/analysis-batch?route_ids=R001,R002", "/api/locations/geojson",
          "/api/gates", "/api/gates?location_id=L001", "/api/haul-roads",
          "/api/routes/R001/haul-roads", "/api/routes/R001/restrictions",
          "/api/routes/restrictions?include_expired=1", "/api/public/whoami"):
    ok(f"🔴 D18: scope_for({p!r}) is map — the network is readable only with a code or the map cookie",
       gate.scope_for(p) == "map", repr(gate.scope_for(p)))
ok("D18: the four network prefixes are declared in MAP_DATA_PREFIXES",
   all(x in gate.MAP_DATA_PREFIXES for x in ("/api/routes/", "/api/locations/", "/api/gates/", "/api/haul-roads/")))
# the two staff WRITES under those prefixes are wrapped by the same prefix match: a valid code
# ALLOWs them unchanged (the body's own approver / admin check still runs); with no code the
# refusal is the map's 401 before the body is reached
for p in ("/api/routes/R001/status", "/api/locations/L001/capacity"):
    ok(f"D18: the staff write {p!r} sits under a map prefix — a valid code passes unchanged, nothing without one reaches its body",
       gate.scope_for(p) == "map" and gate.decide(p, has_valid_code=True) == gate.ALLOW
       and gate.decide(p) == gate.NEED_MAP_PASSWORD)
for p in ("/api/gatesx", "/api/haul-roadsy", "/api/routesz", "/api/locationsq"):
    ok(f"D18: {p!r} is not under a prefix — each prefix is a path segment, not a substring",
       gate.scope_for(p) is None, repr(gate.scope_for(p)))
for p in ("/api/admin/routes", "/api/admin/routes/R001", "/api/admin/gates", "/api/admin/locations",
          "/api/admin/bake-routes", "/api/admin/haul-roads/refresh-temp-km", "/api/admin/clear-geometry"):
    ok(f"D18: {p!r} is NOT the map's — the admin writes stay keyed on ADMIN_TOKEN alone",
       gate.scope_for(p) is None, repr(gate.scope_for(p)))

ok("🔴 /api/meta is NOT gated — the staff app fetches it on mount, before sign-in; "
   "gating it would empty the login screen (12 Oct 2026, D31: it answers two SHAPES instead — see §6 below)",
   gate.scope_for("/api/meta") is None)
ok("🔴 /api/health is NOT gated — Render polls it", gate.scope_for("/api/health") is None)
# 8 Oct 2026 (H9): the demo-request form on wayscope.co.uk posts here from a visitor who
# has no password yet. Exactly this path is open; the rest of /api/public/ stays the map's.
ok("🔴 /api/public/demo-request is NOT gated — the form posts from a visitor with no password",
   gate.scope_for("/api/public/demo-request") is None and "/api/public/demo-request" in gate.OPEN_PATHS)
ok("...with a query string too", gate.scope_for("/api/public/demo-request?x=1") is None)
ok("...and decide() ALLOWs it with no cookie and no code",
   gate.decide("/api/public/demo-request", has_valid_code=False, cookie=None) == gate.ALLOW)
ok("...while its neighbours under /api/public/ are still the map's data",
   gate.scope_for("/api/public/demo-requests") == "map" and gate.scope_for("/api/public/demo-request/x") == "map"
   and gate.scope_for("/api/public/route-forecasts") == "map")
for p in ("/", "/api/auth", "/api/map-auth", "/api/forecasts", "/api/costing/lines",
          "/api/lookahead", "/mapping", "/helper", "/api/metadata"):
    ok(f"scope_for({p!r}) is ungated", gate.scope_for(p) is None,
       f"got {gate.scope_for(p)!r}")
# 12 Oct 2026 (C4): the monthly bulletin's HTML page is the staff's, like the guide (D10)
for p in ("/bulletin", "/bulletin/", "/bulletin/?month=10", "/bulletin/index.html"):
    ok(f"⭐ scope_for({p!r}) is bulletin — the monthly bulletin is staff-only", gate.scope_for(p) == "bulletin",
       repr(gate.scope_for(p)))
ok("...while /bulletinx and the bulletin's API paths are not this gate's (the API bodies check staff themselves)",
   gate.scope_for("/bulletinx") is None and gate.scope_for("/api/bulletin/month") is None
   and gate.scope_for("/api/bulletin/month.pdf") is None and gate.is_document("/bulletin/"))
ok("a path without a leading slash still resolves", gate.scope_for("map/index.html") == "map")
ok("scope_for(None) and scope_for('') are safe",
   gate.scope_for(None) is None and gate.scope_for("") is None)

# ---------------------------------------------------------------- 2. sign / verify
clean()
for lvl in (gate.LEVEL_STAFF, gate.LEVEL_MAP):
    tok = gate.sign(lvl)
    ok(f"a fresh {lvl} cookie verifies as {lvl}", gate.verify(tok) == lvl)
    ok(f"the {lvl} cookie is level.expiry.signature", len(tok.split(".")) == 3)

tok = gate.sign(gate.LEVEL_MAP)
lvl, exp, sig = tok.split(".")
ok("a forged signature is refused", gate.verify(f"{lvl}.{exp}.{'0' * len(sig)}") is None)
ok("🔴 the expiry cannot be extended — it is inside the signature",
   gate.verify(f"{lvl}.{int(exp) + 86400}.{sig}") is None)
ok("🔴 the level cannot be upgraded map -> staff",
   gate.verify(f"staff.{exp}.{sig}") is None)
ok("an expired cookie is refused",
   gate.verify(gate.sign(gate.LEVEL_MAP, now=time.time() - 10, ttl_s=5)) is None)
ok("a cookie expiring exactly now is refused (not >=)",
   gate.verify(gate.sign(gate.LEVEL_MAP, now=1000, ttl_s=0), now=1000) is None)
for junk in (None, "", "garbage", "a.b", "a.b.c.d", "staff.notanumber.ff", 12345, []):
    ok(f"malformed cookie {junk!r} is refused", gate.verify(junk) is None)
ok("an unknown level is refused", gate.verify("admin.9999999999.ff") is None)
try:
    gate.sign("admin")
    ok("sign() refuses an unknown level", False)
except ValueError:
    ok("sign() refuses an unknown level", True)

# rotation
tok_before = gate.sign(gate.LEVEL_MAP)
clean(password="a-new-password")
ok("🔴 rotating MAP_PASSWORD invalidates every cookie issued under the old one — "
   "that is how you revoke someone", gate.verify(tok_before) is None)
clean()
ok("...and restoring the old password makes it valid again (same derivation, no state)",
   gate.verify(tok_before) == gate.LEVEL_MAP)

env(GATE_SECRET="an-explicit-secret")
ok("GATE_SECRET overrides the derived key", gate.verify(tok_before) is None)
tok_secret = gate.sign(gate.LEVEL_MAP)
env(MAP_PASSWORD="anything-else")
ok("...and with GATE_SECRET set, rotating the password does NOT sign people out",
   gate.verify(tok_secret) == gate.LEVEL_MAP)

env(GATE_SECRET=None, MAP_PASSWORD=None, ADMIN_TOKEN=None)
ok("🔴 with nothing configured there is no key, so sign() yields nothing and no cookie "
   "can ever satisfy the gate", gate.sign(gate.LEVEL_MAP) == "" and gate.verify("x.1.y") is None)

# ---------------------------------------------------------------- 3. password_ok
clean(password="corridor-2026")
ok("the right password is accepted", gate.password_ok("corridor-2026"))
ok("surrounding whitespace is tolerated", gate.password_ok("  corridor-2026 "))
ok("the wrong password is refused", not gate.password_ok("corridor-2025"))
ok("a prefix of the password is refused", not gate.password_ok("corridor"))
ok("an empty attempt is refused", not gate.password_ok("") and not gate.password_ok(None))
clean(password=None)
ok("🔴 with no password configured, NOTHING matches — an unset password is not a "
   "password that matches everything",
   not gate.password_ok("") and not gate.password_ok("anything"))

# ---------------------------------------------------------------- 4. decide()
clean()
staff_c = gate.sign(gate.LEVEL_STAFF)
map_c = gate.sign(gate.LEVEL_MAP)

ok("ungated path: allowed with nothing at all",
   gate.decide("/api/costing/lines") == gate.ALLOW)

# the map
ok("map, no credential of any kind -> the password page",
   gate.decide("/map/") == gate.NEED_MAP_PASSWORD)
ok("map, valid access code (the staff app's own fetches) -> allowed",
   gate.decide("/map/", has_valid_code=True) == gate.ALLOW)
ok("⭐ map, STAFF cookie -> allowed. This is the iframe on the staff dashboard: a "
   "document request carries cookies but not the X-Access-Code header",
   gate.decide("/map/", cookie=staff_c) == gate.ALLOW)
ok("map, MAP cookie -> allowed", gate.decide("/map/", cookie=map_c) == gate.ALLOW)
ok("map data endpoint behaves the same as the map page",
   gate.decide("/api/public/month-kpis", cookie=map_c) == gate.ALLOW
   and gate.decide("/api/public/month-kpis") == gate.NEED_MAP_PASSWORD)
ok("🔴 D18: the network behaves the same — nothing: the password page; map cookie, staff cookie or a code: allowed",
   gate.decide("/api/gates") == gate.NEED_MAP_PASSWORD and gate.decide("/api/haul-roads") == gate.NEED_MAP_PASSWORD
   and gate.decide("/api/routes/status") == gate.NEED_MAP_PASSWORD
   and gate.decide("/api/locations/geojson") == gate.NEED_MAP_PASSWORD
   and gate.decide("/api/gates", cookie=map_c) == gate.ALLOW
   and gate.decide("/api/routes/R001/geometries", cookie=staff_c) == gate.ALLOW
   and gate.decide("/api/locations/geojson", has_valid_code=True) == gate.ALLOW)
ok("D18: the view flag /api/public/whoami is reached only with a credential — a visitor with none learns nothing",
   gate.decide("/api/public/whoami") == gate.NEED_MAP_PASSWORD
   and gate.decide("/api/public/whoami", cookie=map_c) == gate.ALLOW
   and gate.decide("/api/public/whoami", cookie=staff_c) == gate.ALLOW)

# help
ok("🔴 help, MAP cookie -> refused. The map password does not open the staff guide",
   gate.decide("/help/", cookie=map_c) == gate.NEED_STAFF)
ok("help, no credential -> refused", gate.decide("/help/") == gate.NEED_STAFF)
ok("help, STAFF cookie -> allowed", gate.decide("/help/", cookie=staff_c) == gate.ALLOW)
ok("help, valid access code -> allowed",
   gate.decide("/help/", has_valid_code=True) == gate.ALLOW)
# 12 Oct 2026 (C4): the bulletin, the same rule as the guide
ok("🔴 bulletin, MAP cookie -> refused. The map password does not open the staff's monthly bulletin",
   gate.decide("/bulletin/?month=10", cookie=map_c) == gate.NEED_STAFF)
ok("🔴 bulletin, no credential -> refused", gate.decide("/bulletin/") == gate.NEED_STAFF)
ok("⭐ bulletin, STAFF cookie -> allowed (the Dashboard's link opens it in a new tab with no header)",
   gate.decide("/bulletin/?month=10", cookie=staff_c) == gate.ALLOW)
ok("bulletin, valid access code -> allowed", gate.decide("/bulletin/", has_valid_code=True) == gate.ALLOW)

# failing closed
clean(password=None)
ok("🔴 THE ONE THAT MATTERS: gate on, no MAP_PASSWORD, no credential -> CLOSED, not "
   "open. ADMIN_TOKEN failed the other way until 12 Oct 2026 (C11, now closed in main._check_admin — §6)",
   gate.decide("/map/") == gate.UNCONFIGURED)
ok("...and the same for the map's data", gate.decide("/api/zones") == gate.UNCONFIGURED)
ok("D18: ...and for the network — closed to outsiders, open to a code",
   gate.decide("/api/gates") == gate.UNCONFIGURED and gate.decide("/api/routes/status") == gate.UNCONFIGURED
   and gate.decide("/api/routes/status", has_valid_code=True) == gate.ALLOW)
ok("⭐ ...but a signed-in staff member still gets the map with no password configured — "
   "a forgotten MAP_PASSWORD costs you outside viewers, never your own team",
   gate.decide("/map/", has_valid_code=True) == gate.ALLOW)
ok("...and help is unaffected by the map password being unset",
   gate.decide("/help/", has_valid_code=True) == gate.ALLOW
   and gate.decide("/help/") == gate.NEED_STAFF)
ok("...and so is the bulletin: staff only, never UNCONFIGURED",
   gate.decide("/bulletin/", has_valid_code=True) == gate.ALLOW and gate.decide("/bulletin/") == gate.NEED_STAFF)

# the escape hatch
clean(gate_on=False)
ok("MAP_GATE=off reopens the map", gate.decide("/map/") == gate.ALLOW)
ok("MAP_GATE=off reopens help too (documented: local development only)",
   gate.decide("/help/") == gate.ALLOW)
ok("MAP_GATE=off reopens the bulletin page too (local development only; its body still checks staff)",
   gate.decide("/bulletin/") == gate.ALLOW)
for v in ("off", "OFF", "0", "false", "no"):
    env(MAP_GATE=v)
    ok(f"MAP_GATE={v!r} is off", not gate.gate_enabled())
for v in ("on", "", "yes", "1", "anything"):
    env(MAP_GATE=v)
    ok(f"MAP_GATE={v!r} is ON — only an explicit off switches it off", gate.gate_enabled())
env(MAP_GATE=None)
ok("MAP_GATE unset is ON", gate.gate_enabled())

# ---------------------------------------------------------------- 5. cookie_kwargs
clean()
for lvl, ttl in ((gate.LEVEL_STAFF, gate.STAFF_TTL_S), (gate.LEVEL_MAP, gate.MAP_TTL_S)):
    kw = gate.cookie_kwargs(lvl)
    ok(f"{lvl} cookie: name, path, ttl",
       kw["key"] == gate.COOKIE and kw["path"] == "/" and kw["max_age"] == ttl)
    ok(f"{lvl} cookie: httponly, secure, samesite=lax",
       kw["httponly"] is True and kw["secure"] is True and kw["samesite"] == "lax")
    ok(f"{lvl} cookie: the value verifies back to {lvl}", gate.verify(kw["value"]) == lvl)
ok("the staff cookie is shorter-lived than the map one — a working day against a month",
   gate.STAFF_TTL_S < gate.MAP_TTL_S)

ok("is_document: pages yes, api no",
   gate.is_document("/map/") and gate.is_document("/help/index.html")
   and not gate.is_document("/api/public/month-kpis")
   and not gate.is_document("/api/zones?x=1"))

# ---------------------------------------------------------------- 6. the wiring, read as text
MAIN = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("main.py imports gate", re.search(r"^import gate\b", MAIN, re.M) is not None)
ok("the middleware calls gate.decide with the path, the resolved code and the cookie",
   "gate.decide(" in MAIN and "request.cookies.get(gate.COOKIE)" in MAIN
   and "has_valid_code=bool(access.current())" in MAIN)
ok("a refusal short-circuits before call_next — the gated thing is never served",
   re.search(r"if decision != gate\.ALLOW:\s*\n\s*return _gate_refusal", MAIN) is not None)
ok("⭐ a successful /api/auth sets the STAFF cookie (this is what keeps the iframe working)",
   re.search(r'path == "/api/auth":\s*\n\s*response\.set_cookie\(\*\*gate\.cookie_kwargs\(gate\.LEVEL_STAFF\)\)', MAIN) is not None)
ok("a successful /api/map-auth sets the MAP cookie",
   re.search(r'path == "/api/map-auth":\s*\n\s*response\.set_cookie\(\*\*gate\.cookie_kwargs\(gate\.LEVEL_MAP\)\)', MAIN) is not None)
ok("cookies are only set on a 200", 'getattr(response, "status_code", None) == 200' in MAIN)
ok("/api/map-auth exists and checks the password through gate.password_ok",
   '@app.post("/api/map-auth")' in MAIN and "gate.password_ok(body.password)" in MAIN)
ok("a wrong password is a 401", re.search(r"password_ok\(body\.password\):\s*\n\s*raise HTTPException\(401", MAIN) is not None)
ok("all three refusal pages exist and are reachable from _gate_refusal",
   all(k in MAIN for k in ("_MAP_PASSWORD_PAGE", "_HELP_SIGNIN_PAGE", "_MAP_UNCONFIGURED_PAGE"))
   and "def _gate_refusal" in MAIN)
ok("a refused document gets HTML, a refused fetch gets JSON",
   "gate.is_document(path)" in MAIN and "_HTML(" in MAIN and "_JSON(" in MAIN)
ok("the password page posts to /api/map-auth and reloads on success",
   "'/api/map-auth'" in MAIN and "location.reload()" in MAIN)

ok("🔴 the refusal pages are NOT files under map/ or frontend/help/ — a password page "
   "inside the directory it guards could never be shown",
   not os.path.exists(os.path.join(ROOT, "map", "gate.html"))
   and not os.path.exists(os.path.join(ROOT, "frontend", "help", "gate.html")))

_gate_src = open(os.path.join(BACKEND, "gate.py"), encoding="utf-8").read()
ok("gate.py imports no framework and no database — it is pure policy",
   not re.search(r"^\s*(import|from)\s+(fastapi|db|starlette)\b", _gate_src, re.M))
ok("🔴 main.py never reads the password itself — only gate.password_ok() sees it, and "
   "it compares in constant time",
   not re.search(r"environ[^\n]*MAP_PASSWORD", MAIN) and "password_ok" in MAIN)
ok("no refusal page echoes the supplied password back",
   not re.search(r"(body\.password|supplied)[^\n]{0,40}(_HTML|_JSON|return)", MAIN))
ok("gate.password_ok uses a constant-time comparison",
   "hmac.compare_digest" in _gate_src)

ok("env.example documents MAP_PASSWORD, MAP_GATE and GATE_SECRET",
   all(k in open(os.path.join(ROOT, "env.example"), encoding="utf-8").read()
       for k in ("MAP_PASSWORD", "MAP_GATE", "GATE_SECRET")))


# ---------------------------------------------------------------- 7. 12 Oct 2026 — C11, D31, whoami (source level)
def _body(name):
    """The text of one function in main.py, up to the next top-level decorator, def or class."""
    rest = MAIN.split(f"def {name}(", 1)[1]
    cut = min(i for i in (rest.find("\n@app."), rest.find("\ndef "), rest.find("\nclass "), len(rest)) if i >= 0)
    return rest[:cut]


ok("🔴 C11 CLOSED: _check_admin refuses when ADMIN_TOKEN is unset — the admin surface fails closed like the gate",
   re.search(r"def _check_admin\(token\):[\s\S]{0,1200}?if not admin_token:\s*\n\s*raise HTTPException\(403", MAIN) is not None
   and "if admin_token and token != admin_token" not in MAIN)
ok("C11: the token is compared in constant time", "hmac.compare_digest(admin_token" in MAIN)
ok("C11: bake-routes and clear-geometry go through _check_admin like every other admin write — no private check left",
   "_check_admin(token)" in _body("bake_routes") and "_check_admin(token)" in _body("clear_geometry")
   and "admin_token" not in _body("bake_routes") and "admin_token" not in _body("clear_geometry"))
ok("D31: /api/meta takes the request, reads the STAFF cookie through gate.verify, and answers two shapes",
   "def meta(request: Request = None)" in MAIN
   and "gate.verify(cookies.get(gate.COOKIE)) == gate.LEVEL_STAFF" in _body("_staff_request")
   and '"scope": "staff" if staff else "public"' in _body("meta")
   and '"routes": network.meta_routes() if staff else []' in _body("meta")
   and '"ipts": taxonomy.list_ipts() if staff else []' in _body("meta")
   and '"work_sections": taxonomy.list_work_sections(in_scope_only=True) if staff else []' in _body("meta"))
ok("D31: the public shape keeps what the sign-in screen and the public map read — units, vehicles, labels, tenant, factors, seasonal windows",
   all(s in _body("meta") for s in ('"units": conversions.UNITS', '"vehicles": conversions.vehicle_names(factors)',
                                     '"vehicle_labels": conversions.vehicle_labels(factors)',
                                     '"tenant": config.tenant_settings(conversions)',
                                     '"factors": conversions.flat_factors(factors)',
                                     '"seasonal_restrictions": factors.get("seasonal_restrictions", [])'))
   and not re.search(r'"(units|vehicles|vehicle_labels|tenant|factors|seasonal_restrictions)":[^\n]*if staff', _body("meta")))
ok("whoami: GET /api/public/whoami exists under the gated prefix, reads the cookie level and the header, returns level + team_label only",
   '@app.get("/api/public/whoami")' in MAIN and "def public_whoami(request: Request = None)" in MAIN
   and "gate.verify(cookies.get(gate.COOKIE))" in _body("public_whoami")
   and 'return {"level": level, "team_label": team}' in _body("public_whoami"))
ok("🔴 whoami never returns a code or a team id: the label falls back to '<team word> n' when the slot is unnamed, "
   "and the body reads no environment and no code variable",
   "access.canonical_ipt(team) == acc[\"ipt\"]" in _body("public_whoami")
   and not re.search(r"environ|_CODE|X-Access-Code|body\.code", _body("public_whoami").split('"""')[2]))


# ---------------------------------------------------------------- 8. 12 Oct 2026 — the review and fix pass
# non-ASCII: hmac.compare_digest raises TypeError on a str with a non-ASCII character, which made ?token=é a 500
clean()
try:
    ok("🔴 a password with a non-ASCII character is refused (False), never a TypeError (a 500)",
       gate.password_ok("corridor-2026é") is False and gate.password_ok("é") is False)
except TypeError as e:
    ok("🔴 a password with a non-ASCII character is refused (False), never a TypeError (a 500)", False, repr(e))
env(MAP_PASSWORD="corrédor")
ok("...and a non-ASCII password itself still matches exactly", gate.password_ok("corrédor") is True
   and gate.password_ok("corredor") is False)
clean()
ok("C11: _check_admin compares BYTES, so a non-ASCII token is a 403, not a 500",
   "hmac.compare_digest(admin_token.encode(\"utf-8\"), str(token).strip().encode(\"utf-8\"))" in _body("_check_admin"))

# Sign out on a shared machine: the 12-hour STAFF cookie is swapped for a MAP cookie that ends no later
clean()
_now = 1_800_000_000
_staff = gate.sign(gate.LEVEL_STAFF, now=_now)
_kw = gate.downgrade_kwargs(_staff, now=_now + 3600)
ok("⭐ downgrade_kwargs turns a valid STAFF cookie into a MAP cookie (the public map still opens, the staff surface does not)",
   _kw is not None and _kw["key"] == gate.COOKIE and gate.verify(_kw["value"], now=_now + 3600) == gate.LEVEL_MAP
   and _kw["httponly"] is True and _kw["path"] == "/", str(_kw))
ok("⭐ ...expiring when the staff cookie would have, never later (11 h left of 12, not the map's 30 days)",
   _kw["max_age"] == gate.STAFF_TTL_S - 3600
   and gate.verify(_kw["value"], now=_now + gate.STAFF_TTL_S + 1) is None, str(_kw.get("max_age")))
ok("...a MAP cookie, a forged one, an expired one or none is left alone (None)",
   gate.downgrade_kwargs(gate.sign(gate.LEVEL_MAP, now=_now), now=_now) is None
   and gate.downgrade_kwargs("staff.9999999999.forged", now=_now) is None
   and gate.downgrade_kwargs(_staff, now=_now + gate.STAFF_TTL_S + 5) is None
   and gate.downgrade_kwargs(None) is None and gate.downgrade_kwargs("") is None)
ok("/api/gate-signout?keep=map sets the downgraded cookie; without keep it drops the cookie as before",
   "def gate_signout(request: Request = None, keep: Optional[str] = None)" in MAIN
   and "gate.downgrade_kwargs(cookies.get(gate.COOKIE))" in _body("gate_signout")
   and "r.delete_cookie(gate.COOKIE, path=\"/\")" in _body("gate_signout"))

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

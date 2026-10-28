"""
28 Oct 2026 — task 8b (`claude/os-zoomstack`): the OS map and a tenant's own aerial imagery as public-map basemaps. The
backend half: the imagery fields on the tenant block (validated on Save), the OS key setting, and the ONE place both reach
the map — /api/public/alignment (never /api/meta, which is read before anybody signs in).

Run from the repo root:  python backend/tests/test_os_basemap.py

What this proves, on a scratch SQLite database (FastAPI stubbed, so the endpoint body runs as a plain function):
  1. the address rule: https only, a site named, no spaces, at most 600 characters, and a tile address ({z}/{x}/{y}) or a WMS
     address ({bbox-epsg-3857}); every refusal is one plain sentence;
  2. imagery_settings: None without an address or with a bad one; the name defaults to "Client imagery" and is cut at 40, the
     credit at 160;
  3. os_maps_key: the OS_MAPS_KEY setting, only when it is key-shaped (letters, digits, - _ ; 16 to 80 characters);
  4. config.validate (the Save check) names a bad address, a too-long name and a non-text credit, and passes a good block;
  5. /api/public/alignment carries tenant.imagery and tenant.os_maps_key; /api/meta carries NEITHER (and so neither does any
     other reader of tenant_settings); the ETag changes when the key or the address changes, so a browser never keeps an old one;
  6. the key is never a screen word: no template of the staff app or the map prints OS_MAPS_KEY.

What it does not prove: OS's own service (it needs a key; checked by hand), the map page itself (parse_map.js runs its block against a
fake map), the Config card (parse_frontend.js), Postgres.
"""
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


def _passthrough_decorator(*a, **k):
    def wrap(fn):
        return fn
    return wrap


class _App:
    def __init__(self, *a, **k):
        pass

    def get(self, *a, **k):
        return _passthrough_decorator()

    post = put = delete = patch = get

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


class _HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = lambda default=None, **k: default


class _Client:
    host = "203.0.113.50"


class _Request:
    def __init__(self, headers=None, cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = dict(cookies or {})
        self.client = _Client()


_fa.Request = _Request
sys.modules.setdefault("fastapi", _fa)
_mw = types.ModuleType("fastapi.middleware")
_cors = types.ModuleType("fastapi.middleware.cors")
_cors.CORSMiddleware = object
_mw.cors = _cors
sys.modules.setdefault("fastapi.middleware", _mw)
sys.modules.setdefault("fastapi.middleware.cors", _cors)
_resp = types.ModuleType("fastapi.responses")
_resp.FileResponse = lambda *a, **k: None


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None, background=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type
        self.background = background

    def set_cookie(self, **kw):
        pass

    def delete_cookie(self, key, **kw):
        pass


class _JSONResponse(_Response):
    pass


_resp.Response = _Response
_resp.JSONResponse = _JSONResponse
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)
_st = types.ModuleType("starlette")
_stbg = types.ModuleType("starlette.background")


class _BackgroundTask:
    def __init__(self, fn, *a, **k):
        self.fn, self.a, self.k = fn, a, k


_stbg.BackgroundTask = _BackgroundTask
_st.background = _stbg
sys.modules.setdefault("starlette", _st)
sys.modules.setdefault("starlette.background", _stbg)

TMP = tempfile.mkdtemp(prefix="wayscope_osbase_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
for v in ("DATABASE_URL", "SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY", "LANDING_URL", "APP_URL",
          "DEMO_TEAM_CODE_VAR", "DEMO_REPLY_TO", "ALLOW_DEMO_CODES", "MAP_GATE", "TENANT_ID", "IPT1_CODE",
          "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE", "OS_MAPS_KEY"):
    os.environ.pop(v, None)
os.environ.update({"ADMIN_TOKEN": "adm-token-for-tests", "MAP_PASSWORD": "map-pass-abc",
                   "GATE_SECRET": "gate-secret-for-tests"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import config  # noqa: E402
import conversions  # noqa: E402
import main  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_config_db()

# =========================================================================== #
#  1. the address rule                                                        #
# =========================================================================== #
GOOD_XYZ = "https://tiles.example.org/aerial/{z}/{x}/{y}.jpg"
GOOD_WMS = "https://wms.example.org/service?SERVICE=WMS&REQUEST=GetMap&SRS=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256"
ok("1: a tile address with {z}/{x}/{y} is good", config.imagery_url_problem(GOOD_XYZ) is None)
ok("1: the three tokens in any order are good (a {z}/{y}/{x} service)", config.imagery_url_problem("https://a.example.org/{z}/{y}/{x}.png") is None)
ok("1: a WMS address with {bbox-epsg-3857} is good", config.imagery_url_problem(GOOD_WMS) is None)
ok("1: empty or not text asks for an address", config.imagery_url_problem("") == "Type an address."
   and config.imagery_url_problem(None) == "Type an address." and config.imagery_url_problem("   ") == "Type an address.")
ok("1: http (not https) is refused in words", "https://" in (config.imagery_url_problem("http://tiles.example.org/{z}/{x}/{y}.png") or ""))
ok("1: no site named is refused", config.imagery_url_problem("https:///{z}/{x}/{y}") is not None
   and config.imagery_url_problem("https://") is not None)
ok("1: a space in the address is refused", "space" in (config.imagery_url_problem("https://x.example.org/a b/{z}/{x}/{y}") or ""))
ok("1: an address with neither pattern says how to write one",
   config.imagery_url_problem("https://x.example.org/map.png") == "Use an address with {z}/{x}/{y} or {bbox-epsg-3857}."
   and config.imagery_url_problem("https://x.example.org/{z}/{x}") is not None)
ok("1: longer than 600 characters is refused", "600" in (config.imagery_url_problem("https://x.example.org/" + "a" * 590 + "/{z}/{x}/{y}") or ""))

# =========================================================================== #
#  2. imagery_settings                                                        #
# =========================================================================== #
ok("2: no tenant block, or no address: None", config.imagery_settings(doc={}) is None
   and config.imagery_settings(doc={"tenant": {}}) is None and config.imagery_settings(doc={"tenant": {"imagery_url": ""}}) is None)
ok("2: a bad address is None (never drawn)", config.imagery_settings(doc={"tenant": {"imagery_url": "http://x.example.org/{z}/{x}/{y}"}}) is None)
im = config.imagery_settings(doc={"tenant": {"imagery_url": "  " + GOOD_XYZ + " "}})
ok("2: a good address gives the name default and an empty credit, the address trimmed",
   im == {"name": "Client imagery", "url": GOOD_XYZ, "credit": ""}, str(im))
im = config.imagery_settings(doc={"tenant": {"imagery_url": GOOD_WMS, "imagery_name": "Council aerial 2025", "imagery_credit": "© Example Council 2025"}})
ok("2: the typed name and credit are kept", im and im["name"] == "Council aerial 2025" and im["credit"] == "© Example Council 2025", str(im))
im = config.imagery_settings(doc={"tenant": {"imagery_url": GOOD_XYZ, "imagery_name": "N" * 60, "imagery_credit": "C" * 300}})
ok("2: the name is cut at 40 and the credit at 160", im and len(im["name"]) == 40 and len(im["credit"]) == 160, str(im)[:120])

# =========================================================================== #
#  3. the OS key                                                              #
# =========================================================================== #
ok("3: no OS_MAPS_KEY: None", config.os_maps_key() is None)
os.environ["OS_MAPS_KEY"] = "  abcdEFGH12345678abcdEFGH_-xy  "
ok("3: a key-shaped value is read, trimmed", config.os_maps_key() == "abcdEFGH12345678abcdEFGH_-xy")
for bad in ("short", "has space in it 1234567890", "a" * 81, "key=with&odd?chars1234567890", ""):
    os.environ["OS_MAPS_KEY"] = bad
    ok(f"3: {bad[:20]!r} is not key-shaped: None (nothing odd goes into a request address)", config.os_maps_key() is None)
os.environ["OS_MAPS_KEY"] = "abcdEFGH12345678abcdEFGH"

# =========================================================================== #
#  4. the Save check                                                          #
# =========================================================================== #
base = json.loads(json.dumps(config.load(conversions)))


def problems_with(tenant_extra):
    d = json.loads(json.dumps(base))
    d["tenant"] = dict(d.get("tenant") or {})
    d["tenant"].update(tenant_extra)
    return config.validate(d)


ok("4: a good imagery block passes the Save check",
   not [p for p in problems_with({"imagery_url": GOOD_XYZ, "imagery_name": "Council aerial", "imagery_credit": "© X"}) if "imagery" in p])
pr = problems_with({"imagery_url": "https://x.example.org/map.png"})
ok("4: a bad address is named, with the sentence", any(p.startswith("tenant.imagery_url: Use an address with") for p in pr), str(pr)[:200])
ok("4: a blank address is no problem (the line is simply hidden)", not [p for p in problems_with({"imagery_url": ""}) if "imagery" in p])
ok("4: a 41-character name is a problem", any("imagery_name" in p for p in problems_with({"imagery_name": "N" * 41})))
ok("4: a 161-character credit is a problem", any("imagery_credit" in p for p in problems_with({"imagery_credit": "C" * 161})))
ok("4: a name that is not text is a problem", any("imagery_name" in p for p in problems_with({"imagery_name": 5})))

# =========================================================================== #
#  5. where they reach the map                                                #
# =========================================================================== #
saved = json.loads(json.dumps(base))
saved["tenant"] = dict(saved.get("tenant") or {})
saved["tenant"].update({"imagery_url": GOOD_XYZ, "imagery_name": "Council aerial 2025", "imagery_credit": "© Example Council 2025"})
res = config.save(saved, by="test")
ok("5: the block saves", res["ok"], str(res)[:200])
config.invalidate()
r1 = main.public_alignment(_Request())
a1 = json.loads(r1.body)
ok("5: /api/public/alignment carries the tenant's imagery (name, address, credit)",
   a1["tenant"]["imagery"] == {"name": "Council aerial 2025", "url": GOOD_XYZ, "credit": "© Example Council 2025"}, str(a1["tenant"].get("imagery")))
ok("5: ...and the OS key the deployment holds", a1["tenant"]["os_maps_key"] == "abcdEFGH12345678abcdEFGH")
meta_t = main.meta()["tenant"]
ok("5: /api/meta (read before anybody signs in) carries NEITHER", "imagery" not in meta_t and "os_maps_key" not in meta_t
   and "imagery_url" not in json.dumps(meta_t) and "abcdEFGH" not in json.dumps(meta_t))
ts = config.tenant_settings(conversions)
ok("5: nor does tenant_settings, which every other reader uses", "imagery" not in ts and "os_maps_key" not in ts and "imagery_url" not in ts)
r2 = main.public_alignment(_Request())
ok("5: the same data gives the same ETag, and a matching If-None-Match is a 304",
   r2.headers["ETag"] == r1.headers["ETag"] and main.public_alignment(_Request({"If-None-Match": r1.headers["ETag"]})).status_code == 304)
os.environ["OS_MAPS_KEY"] = "ZZZZyyyy12345678ZZZZyyyy"
r3 = main.public_alignment(_Request())
ok("5: a changed OS key changes the ETag, so a browser never keeps the old key", r3.headers["ETag"] != r1.headers["ETag"]
   and json.loads(r3.body)["tenant"]["os_maps_key"] == "ZZZZyyyy12345678ZZZZyyyy")
saved2 = json.loads(json.dumps(saved))
saved2["tenant"]["imagery_url"] = "https://other.example.org/{z}/{x}/{y}.png"
config.save(saved2, by="test"); config.invalidate()
r4 = main.public_alignment(_Request())
ok("5: a changed imagery address changes the ETag", r4.headers["ETag"] != r3.headers["ETag"])
os.environ.pop("OS_MAPS_KEY", None)
a5 = json.loads(main.public_alignment(_Request()).body)
ok("5: no key set: os_maps_key is null, imagery still there", a5["tenant"]["os_maps_key"] is None and a5["tenant"]["imagery"] is not None)
saved3 = json.loads(json.dumps(base)); config.save(saved3, by="test"); config.invalidate()
a6 = json.loads(main.public_alignment(_Request()).body)
ok("5: a tenant that types nothing has imagery null (the map hides the line)", a6["tenant"]["imagery"] is None)

# =========================================================================== #
#  6. the key is never a screen word                                          #
# =========================================================================== #
fe = read("frontend/index.html")
mp = read("map/index.html")
ok("6: no screen of the staff app or the map prints the setting's name", "OS_MAPS_KEY" not in fe and "OS_MAPS_KEY" not in mp)
ok("6: the map reads the key only to add it to a request to OS (osKeyedUrl), never to print it",
   "TENANT.os_maps_key" in mp and "textContent = TENANT.os_maps_key" not in mp and "innerHTML" not in mp.split("function osKeyedUrl", 1)[1].split("function osTransformRequest", 1)[0])
ok("6: the Config card has the three fields and no key field", all(k in fe for k in ("cfg-imagery-name", "cfg-imagery-url", "cfg-imagery-credit"))
   and "cfg-os" not in fe)

print(f"\ntest_os_basemap: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)

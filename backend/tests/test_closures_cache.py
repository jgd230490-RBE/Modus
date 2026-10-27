"""
Group 2a (27 Oct 2026): the public map's /api/routes/restrictions no longer fetches National Highways and matches
every route against every closure on every page load.

What is asserted (National Highways is NEVER called: restrictions._nh_page is a fixture):
  1. the feed is fetched once per CACHE_TTL_S and a second look costs no fetch;
  2. the stored route check (read_cache) is built once and served after that, and is rebuilt when the feed is
     replaced, when a route is written (the data version) and when the day turns;
  3. a failed fetch, a fetch with an error on any page, and an EMPTY answer (what National Highways' own service
     gave on 27 Oct 2026) keep the last good copy, marked stale, for at most STALE_MAX_S, and retry after
     STALE_RETRY_S; past STALE_MAX_S the empty answer is accepted;
  4. the admin refresh keeps the last good copy; the scheduled refresh fetches now whatever the age;
  5. the same object comes back while the feed is unchanged, so restrictions.serialised() serves its stored body;
  6. source-level: the thread is started from main.lifespan behind WAYSCOPE_WARM_CACHE, the warmer is registered,
     the technical guide says how stale a closure can get, and no screen carries the words.

Not tested: the live National Highways service, a second process, the scheduled thread's sleep loop (the refresh it
calls is).

Run:  python backend/tests/test_closures_cache.py
"""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

TMP = tempfile.mkdtemp(prefix="rbe_closcache_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import restrictions  # noqa: E402
import read_cache  # noqa: E402
import network  # noqa: E402

restrictions.COUNTRY_OVERRIDE = "GB"

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


remove_scratch_db(db, TMP)
db.init_network_db()
db.init_zones_db()
db.init_gates_db()

_DAY = 86400000
_NOW_MS = int(time.time() * 1000)

_pages = []          # offsets asked of the fixture
_mode = {"m": "good"}


def _feat(oid, ev, a, b, start=-2, end=5):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [a, b]},
            "properties": {"OBJECTID": oid, "description": "Lane closure", "road_number": "A46",
                           "eventtype": "Lane closure", "natureofworks": "Barrier works", "formattedeventnumber": ev,
                           "scheduledplannedstartdate": _NOW_MS + start * _DAY,
                           "scheduledplannedenddate": _NOW_MS + end * _DAY}}


def _fake_nh_page(offset, count=restrictions.NH_PAGE, timeout=None):
    _pages.append(offset)
    m = _mode["m"]
    if m == "down":
        raise OSError("connection refused")
    if m == "empty":
        return {"type": "FeatureCollection", "features": []}
    if offset:
        if m == "page2-error":
            raise OSError("HTTP 500")
        return {"type": "FeatureCollection", "features": [_feat(3, "NH-0003", [-1.2, 52.7], [-1.19, 52.71])]}
    out = {"type": "FeatureCollection",
           "features": [_feat(2, "NH-0002", [-0.9, 52.5], [-0.89, 52.51])]}
    out["exceededTransferLimit"] = True      # two pages: this one and the one at offset 1
    return out


restrictions._nh_page = _fake_nh_page


def _route(rid, line):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, origin_temp_km) VALUES (?,?,?,0)", (rid, "L1", "L2"))
    network._upsert_geom(rid, "Rigid 8-wheeler (32t)", json.dumps(line), 2.0, 0.1, None, leg="loaded", alt_index=0)


db.execute("INSERT INTO locations (id, name, lat, lon) VALUES ('L1','W',52.5,-0.9)")
db.execute("INSERT INTO locations (id, name, lat, lon) VALUES ('L2','E',52.51,-0.89)")
_route("R1", [[-0.905, 52.499], [-0.8955, 52.5052], [-0.885, 52.515]])      # along the closure
_route("R2", [[-1.5, 52.9], [-1.45, 52.95]])                                 # nowhere near


def fresh():
    restrictions.clear_cache(everything=True)
    read_cache.clear()
    _pages.clear()
    _mode["m"] = "good"


# --- the matching is counted, so "built once" is a measured thing ----------------------------------------------
_builds = []
_real_build = restrictions._check_all_build


def _counting_build(fc, profile, current_only):
    _builds.append(1)
    return _real_build(fc, profile, current_only)


restrictions._check_all_build = _counting_build

# =========================================================================== #
#  1. The feed is fetched once                                                 #
# =========================================================================== #
fresh()
a = restrictions.check_all(current_only=False)
ok("the route check works against the fixture: R1 has a hit, R2 none",
   a["route_count"] == 1 and list(a["routes"]) == ["R1"] and a["features_checked"] == 1 + 1 and not a["stale"],
   str(a)[:200])
n_first = len(_pages)
ok("the first look pages the feed (offset 0, then 1)", _pages == [0, 1], str(_pages))
for _ in range(5):
    restrictions.check_all(current_only=False)
ok("five more looks fetch nothing", len(_pages) == n_first, str(_pages))
ok("...and match the routes once, not six times", len(_builds) == 1, str(len(_builds)))
b = restrictions.check_all(current_only=False)
ok("the answer is the same object while nothing changed", a is b)

# =========================================================================== #
#  2. The stored check is rebuilt when it must be                              #
# =========================================================================== #
before = len(_builds)
db.execute("UPDATE routes SET origin_temp_km = 1 WHERE id = 'R2'")        # any committed write moves the data version
restrictions.check_all(current_only=False)
ok("a write (the data version) rebuilds the check", len(_builds) == before + 1, str(len(_builds) - before))
restrictions.check_all(current_only=False)
ok("...and only once", len(_builds) == before + 1)
before = len(_builds)
restrictions.check_all(current_only=True)
ok("a different variant (current only) is its own entry", len(_builds) == before + 1)
restrictions.check_all(current_only=False)
ok("...and does not push the other one out", len(_builds) == before + 1)
before = len(_builds)
restrictions.refresh_feed()
restrictions.check_all(current_only=False)
ok("a replaced feed rebuilds the check", len(_builds) == before + 1)
before = len(_builds)
_real_dt = restrictions.datetime


class _Tomorrow:
    @staticmethod
    def now(tz=None):
        return _real_dt.now(tz) + __import__("datetime").timedelta(days=1)


restrictions.datetime = _Tomorrow
try:
    restrictions.check_all(current_only=False)
finally:
    restrictions.datetime = _real_dt
ok("the day turning rebuilds the check (a closure ends at midnight)", len(_builds) == before + 1)

# =========================================================================== #
#  3. A bad fetch keeps the last good copy                                     #
# =========================================================================== #
def age_feed(seconds):
    """Make the cached feed and the last good copy `seconds` older (no sleeping)."""
    h = restrictions._cache["lyr:nh_closures"]
    restrictions._cache["lyr:nh_closures"] = (h[0] - seconds, h[1])
    g = restrictions._NH_GOOD
    restrictions._NH_GOOD = (g[0] - seconds, g[1])


for mode, label in (("down", "the provider is down"), ("empty", "the provider answers with no closures"),
                    ("page2-error", "page 2 fails")):
    fresh()
    restrictions.check_all(current_only=False)
    age_feed(restrictions.CACHE_TTL_S + 1)            # the cached copy has run out
    _mode["m"] = mode
    _pages.clear()
    c = restrictions.check_all(current_only=False)
    ok(f"{label}: the last good copy answers, marked stale", c["stale"] is True and c["route_count"] == 1
       and c["features_checked"] == 2, str(c)[:240])
    ok(f"{label}: the provider was asked", len(_pages) >= 1)
    fa = restrictions.fetch_all(current_only=False)
    ok(f"{label}: fetch_all carries the stale flag and no error", fa.get("stale") is True and not fa["errors"]
       and len(fa["features"]) == 2)
    _pages.clear()
    restrictions.check_all(current_only=False)
    ok(f"{label}: and is not asked again straight away", _pages == [], str(_pages))
    # five minutes later it is asked again; the provider is back
    h = restrictions._cache["lyr:nh_closures"]
    restrictions._cache["lyr:nh_closures"] = (h[0] - restrictions.STALE_RETRY_S - 1, h[1])
    _mode["m"] = "good"
    d = restrictions.check_all(current_only=False)
    ok(f"{label}: after the retry time a recovered provider replaces the stale copy",
       d["stale"] is False and d["route_count"] == 1, str(d)[:200])
    ok(f"{label}: ...and the good copy is renewed", restrictions.feed_state()["stale"] is False)

fresh()
_mode["m"] = "empty"
e = restrictions.check_all(current_only=False)
ok("an empty answer with NO good copy yet is accepted as it is (nothing to fall back to)",
   e["route_count"] == 0 and e["features_checked"] == 0 and e["stale"] is False, str(e)[:200])

fresh()
restrictions.check_all(current_only=False)
age_feed(restrictions.STALE_MAX_S + 10)
_mode["m"] = "down"
f = restrictions.check_all(current_only=False)
ok("a good copy older than STALE_MAX_S is NOT served for ever: with the provider still down the check has no data",
   f.get("error") or (f.get("route_count") == 0 and f.get("stale") is False), str(f)[:200])

fresh()
restrictions.check_all(current_only=False)
age_feed(restrictions.STALE_MAX_S + 10)
_mode["m"] = "empty"
g = restrictions.check_all(current_only=False)
ok("...and past STALE_MAX_S an empty answer is accepted", g["route_count"] == 0 and g["stale"] is False, str(g)[:200])

# =========================================================================== #
#  4. The admin refresh and the scheduled refresh                              #
# =========================================================================== #
fresh()
restrictions.check_all(current_only=False)
restrictions.clear_cache()
ok("the admin refresh empties the cache but keeps the last good copy", "lyr:nh_closures" not in restrictions._cache
   and restrictions._NH_GOOD is not None)
_mode["m"] = "down"
h = restrictions.check_all(current_only=False)
ok("...so a provider that is down at that moment still leaves the map its closures", h["stale"] is True
   and h["route_count"] == 1, str(h)[:200])
fresh()
restrictions.check_all(current_only=False)
_pages.clear()
res = restrictions.refresh_feed()
ok("the scheduled refresh fetches now, whatever the age", res["refreshed"] is True and _pages == [0, 1], str(res) + str(_pages))
ok("...and reports how current the feed is", res["feed"]["features"] == 2 and res["feed"]["stale"] is False
   and res["feed"]["data_age_s"] <= 2, str(res))
_mode["m"] = "down"
res = restrictions.refresh_feed()
ok("...and a refresh that fails does not raise and leaves the stale copy serving",
   res["refreshed"] is True and res["feed"]["stale"] is True and restrictions.feed_state()["features"] == 2, str(res))
ok("diagnostics carry the feed state", "feed" in restrictions.diagnostics(probe=False))

# =========================================================================== #
#  5. The same object, so the serialised body is stored                        #
# =========================================================================== #
fresh()
x = restrictions.fetch_all(current_only=True)
y = restrictions.fetch_all(current_only=True)
ok("fetch_all returns the same collection while the feed is unchanged", x is y)
s1 = restrictions.serialised(x, None, True)
s2 = restrictions.serialised(y, None, True)
ok("...so the serialised body is the stored string, not built again", s1 is s2)
restrictions.refresh_feed()
z = restrictions.fetch_all(current_only=True)
ok("a replaced feed is a new collection (and a new body)", z is not x and restrictions.serialised(z, None, True) is not s1)

# =========================================================================== #
#  6. Source level                                                             #
# =========================================================================== #
main_src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
life = main_src[main_src.index("async def lifespan") if "async def lifespan" in main_src else main_src.index("def lifespan"):]
life = life[:life.index("app = FastAPI")]
ok("the refresher is started from lifespan, behind WAYSCOPE_WARM_CACHE", "restrictions.start_refresher(" in life
   and life.index("WAYSCOPE_WARM_CACHE") < life.index("restrictions.start_refresher("))
ok("the stored check is registered as a warmer", 'read_cache.WARMERS["restrictions_check"]' in main_src)
ok("the endpoint still passes include_expired through", "restrictions.check_all(profile=profile, current_only=not include_expired)" in main_src)
tg = open(os.path.join(ROOT, "frontend", "help", "technical", "index.html"), encoding="utf-8").read()
ok("the technical guide says how stale a closure can get (the 20 minute refresh, the 30 minute copy, the 24 hour fallback)",
   "closures" in tg.lower() and "20 minutes" in tg and "24 hours" in tg and "stale" in tg.lower())
ok("the refresh interval stays inside the cache time", restrictions.REFRESH_EVERY_S < restrictions.CACHE_TTL_S)
screens = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read() + \
    open(os.path.join(ROOT, "map", "index.html"), encoding="utf-8").read()
ok("no screen mentions the closures cache (the technical guide only)",
   "last good copy" not in screens and "STALE_MAX" not in screens and "closures-refresher" not in screens)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)

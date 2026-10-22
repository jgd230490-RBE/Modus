"""
22 Oct 2026 (the follow-up to PR #113: "the very first council view on live still waits ~7-11 s").

A whole read kept in memory, per tenant, until the next write. /api/public/areas/months took 7.4 s
on Render (19 Oct, timed in the user's Chrome; 0.4-0.9 s on the laptop: 90 queries, half the time in
working out which routes the map draws, a third in the carbon lines, the rest the months' roll-up).
The answer is the same for every viewer until somebody changes the data, so it is built once and
served from memory after that.

NEVER STALE. An entry is served only while db.data_version() is the number it was built under, and
that number goes up after every committed write that could change a figure (db.note_write in
db._run / db.execute_atomic; writers on their own connection call db.bump_data_version(); the
middleware bumps after every audited /api/ write as a second net). A build notes the version BEFORE
it reads anything and is kept only if the version has not moved by the time it finishes, so a write
that lands mid-build can never leave the older figures behind.

Single-flight: two first viewers at once do not build it twice; the second waits for the first's
answer (the build runs inside one of heavy_reads' slots, so a cold read still cannot pile up).

warm() / start_warmer(): after start-up, and again once writes have stopped for WARM_QUIET_S, the
background warmer builds what is missing, so the first viewer after a deploy or an edit does not
wait either. It only ever calls the same builder a viewer would.

WHAT THIS DOES NOT DO: share entries between processes (Render runs one; see db.py), hold more than
one entry per name and tenant, or keep anything across a restart.
"""
import json
import threading
import time

import db

#: (name, tenant) -> (key, version, value)
_STORE = {}
_LOCK = threading.Lock()
#: (name, tenant) -> threading.Lock, so one build at a time per entry
_BUILDING = {}
#: counters the tests and the log read: hits, builds, and builds thrown away because a write landed mid-build
STATS = {"hits": 0, "builds": 0, "discarded": 0}


def _entry_lock(slot):
    with _LOCK:
        lk = _BUILDING.get(slot)
        if lk is None:
            lk = _BUILDING[slot] = threading.Lock()
        return lk


def peek(name, key):
    """The stored value if it is still current for this tenant, else None. Builds nothing."""
    slot = (name, db.current_tenant())
    hit = _STORE.get(slot)
    if hit and hit[0] == key and hit[1] == db.data_version():
        return hit[2]
    return None


def cached(name, key, build):
    """
    The value of build() for this tenant and `key`, built at most once per data version. `key` is
    whatever else the answer depends on (working days, the horizon, the day). build() takes no
    arguments and returns the value to keep (read_cache keeps it as it is; callers keep bytes).
    """
    slot = (name, db.current_tenant())
    hit = peek(name, key)
    if hit is not None:
        STATS["hits"] += 1
        return hit
    with _entry_lock(slot):
        hit = peek(name, key)                 # the viewer we waited behind may have built it
        if hit is not None:
            STATS["hits"] += 1
            return hit
        version = db.data_version()           # noted BEFORE any read
        value = build()
        STATS["builds"] += 1
        with _LOCK:
            if db.data_version() == version:
                _STORE[slot] = (key, version, value)
            else:
                STATS["discarded"] += 1        # a write landed mid-build: serve it to this viewer, keep nothing
                _STORE.pop(slot, None)
        return value


def clear():
    """Forget every entry (tests; nothing in the app needs it — the version does the work)."""
    with _LOCK:
        _STORE.clear()


def json_bytes(value):
    """The body FastAPI's JSONResponse would send for `value` (same separators, UTF-8, no NaN)."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=None,
                      separators=(",", ":")).encode("utf-8")


# --------------------------------------------------------------------------- #
#  The warmer                                                                  #
# --------------------------------------------------------------------------- #
#: seconds after start-up before the first warm-up (let the health check and first pages through)
WARM_FIRST_S = 5.0
#: a warm-up waits until no write has landed for this long (a Route all or an import is many writes)
WARM_QUIET_S = 30.0
#: how often the warmer looks
WARM_TICK_S = 10.0
#: name -> function that warms that entry for the current tenant (registered by main.py)
WARMERS = {}


def warm(tenant):
    """Run every registered warmer for `tenant`, once. Never raises; returns {name: "ok" | error}."""
    out = {}
    token = db.set_current_tenant(tenant)
    try:
        for name, fn in list(WARMERS.items()):
            try:
                fn()
                out[name] = "ok"
            except Exception as e:  # noqa: BLE001 — a warm-up must never take the app down
                out[name] = f"{e.__class__.__name__}: {str(e)[:200]}"
                print(f"⚠️  read cache: warming {name} failed: {out[name]}")
    finally:
        db.reset_current_tenant(token)
    return out


def start_warmer(tenant):
    """One daemon thread: warm after start-up, then again whenever writes have been quiet for WARM_QUIET_S
    and an entry has gone out of date. Called from main.lifespan only, never by an import."""
    def run():
        time.sleep(WARM_FIRST_S)
        warmed_at = None
        seen, quiet_since = db.data_version(), time.monotonic()
        while True:
            v = db.data_version()
            if v != seen:
                seen, quiet_since = v, time.monotonic()
            if warmed_at != v and (warmed_at is None or time.monotonic() - quiet_since >= WARM_QUIET_S):
                t0 = time.monotonic()
                res = warm(tenant)
                print(f"🧮 read cache: warmed {', '.join(f'{k} {r}' for k, r in res.items())} "
                      f"in {time.monotonic() - t0:.1f} s (data version {v})")
                warmed_at = v
            time.sleep(WARM_TICK_S)

    threading.Thread(target=run, name="read-cache-warmer", daemon=True).start()

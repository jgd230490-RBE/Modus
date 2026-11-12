"""
11 Nov 2026 (X-F1, John's yes to the "Everything left" page): a request WAITS a short, capped time for a
pooled Postgres connection instead of opening a fresh one the moment the pool is lent out.

Why: psycopg2's ThreadedConnectionPool raises at once when every connection is lent out, and db.get_conn()
then opened a brand-new connection for that one statement (~190 ms on the deployment, db.py's 9 Sep note).
One carbon build is ~300 statements; several heavy reads at once paid a fresh connection on every statement
and stacked to minutes (the CLOCS-meeting live check, 11 Nov).

What this harness covers (SQLite laptop, no Postgres): db.get_conn()'s Postgres branch with a STAND-IN pool
and a stand-in psycopg2.connect, real threads and a real threading.BoundedSemaphore:
  * a free connection is lent at once; with all lent, a request waits and is served from the pool when one
    comes back; when the wait runs out it opens its own connection (never hangs past the limit);
  * the slot goes back exactly once on close() and on discard() (a double close never over-releases);
  * a pool that fails to lend gives the slot straight back;
  * DB_POOL_WAIT_S=0 is the old behaviour (no wait); the limit is clamped to 0..30 s;
  * many overlapping "builds" on a small pool use the pool only (no fresh connection), where the old code
    opened fresh ones;
  * the existing retry on a dead pooled connection still works through the slots.
NOT covered: a real Postgres server (none on this laptop): connection set-up time, the server's own limit,
psycopg2's pool internals. Watched on live after the merge (session-1111-db-pool-wait.md).
"""
import os
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

os.environ.pop("DATABASE_URL", None)
import db  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL.append(f"{label} {extra}".strip())
        print(f"  FAIL {label} {extra}".rstrip())


class FakeConn:
    def __init__(self, n):
        self.n, self.closed = n, False

    def get_transaction_status(self):
        return 0

    def rollback(self):
        pass

    def commit(self):
        pass

    def close(self):
        self.closed = True

    def cursor(self, **k):
        class _Cur:
            def execute(self_, sql, params=()):
                time.sleep(0.002)          # a statement takes a moment, as on a real server

            def fetchall(self_):
                return [{"n": 1}]
        return _Cur()


class FakePool:
    """Like psycopg2's ThreadedConnectionPool: lends up to `size`, raises at once when all are lent."""
    def __init__(self, size):
        self.size, self.lent, self.lock, self.made, self.fail_next = size, 0, threading.Lock(), 0, False
        self.most_lent = 0

    def getconn(self):
        with self.lock:
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("pool broke")
            if self.lent >= self.size:
                raise RuntimeError("connection pool exhausted")
            self.lent += 1
            self.most_lent = max(self.most_lent, self.lent)
            self.made += 1
            return FakeConn(self.made)

    def putconn(self, conn, close=False):
        with self.lock:
            self.lent -= 1


FRESH = []


def fake_connect(url):
    FRESH.append(time.monotonic())
    return FakeConn(-len(FRESH))


def setup(size, wait):
    """Point db at a stand-in pool of `size` with a DB_POOL_WAIT_S of `wait`."""
    pool = FakePool(size)
    db._PG_POOL = pool
    db._POOL_SLOTS = threading.BoundedSemaphore(size)
    os.environ["DB_POOL_WAIT_S"] = str(wait)
    for k in db.POOL_STATS:
        db.POOL_STATS[k] = 0
    FRESH.clear()
    return pool


_orig = (db.IS_PG, getattr(db, "psycopg2", None), db._PG_POOL, db._POOL_SLOTS, os.environ.get("DB_POOL_WAIT_S"))
db.IS_PG = True
db.psycopg2 = types.SimpleNamespace(connect=fake_connect)
try:
    # ------------------------------------------------------------------ #
    #  1. Lent at once while free; with all lent, a request waits         #
    # ------------------------------------------------------------------ #
    pool = setup(2, 3)
    a, b = db.get_conn(), db.get_conn()
    ok("a free pooled connection is lent at once (no wait counted, no fresh connection)",
       isinstance(a, db._PooledConn) and isinstance(b, db._PooledConn) and db.POOL_STATS["waited"] == 0 and not FRESH)
    got = {}

    def third():
        t0 = time.monotonic()
        c = db.get_conn()
        got["c"], got["t"] = c, time.monotonic() - t0
    th = threading.Thread(target=third)
    th.start()
    time.sleep(0.3)
    ok("...with both lent, a third request WAITS (it has no connection yet)", "c" not in got)
    a.close()
    th.join(5)
    ok("⭐ ...and is served from the POOL as soon as one comes back (not a fresh connection)",
       isinstance(got.get("c"), db._PooledConn) and not FRESH and 0.25 <= got["t"] < 2.0 and db.POOL_STATS["waited"] == 1,
       f"{got} {db.POOL_STATS}")
    got["c"].close(); b.close()
    ok("every slot is back after the three are returned (the pool lends two again at once)",
       db._POOL_SLOTS.acquire(blocking=False) and db._POOL_SLOTS.acquire(blocking=False)
       and not db._POOL_SLOTS.acquire(blocking=False))
    db._POOL_SLOTS.release(); db._POOL_SLOTS.release()

    # ------------------------------------------------------------------ #
    #  2. The wait has a limit: then a fresh connection, as before        #
    # ------------------------------------------------------------------ #
    pool = setup(2, 0.4)
    a, b = db.get_conn(), db.get_conn()
    other = {}

    def other_thread():                      # another request (not this thread, which holds both)
        t0_ = time.monotonic()
        other["c"] = db.get_conn()
        other["took"] = time.monotonic() - t0_
    th = threading.Thread(target=other_thread)
    th.start(); th.join(5)
    c, took = other["c"], other["took"]
    ok("🔴 when the wait runs out (nothing came back) the request opens its own connection and goes on",
       not isinstance(c, db._PooledConn) and len(FRESH) == 1 and 0.35 <= took < 1.5
       and db.POOL_STATS["wait_ran_out"] == 1 and db.POOL_STATS["fresh"] == 1, f"{took:.2f}s {db.POOL_STATS}")
    c.close(); a.close(); b.close()

    # ------------------------------------------------------------------ #
    #  3. The slot goes back exactly once                                  #
    # ------------------------------------------------------------------ #
    pool = setup(2, 0.2)
    a = db.get_conn()
    a.close()
    try:
        a.close()
        ok("⭐ a second close() of the same connection gives nothing back twice (no over-release)", True)
    except ValueError:
        ok("⭐ a second close() of the same connection gives nothing back twice (no over-release)", False)
    d = db.get_conn()
    d.discard()
    d.discard()
    ok("...discard() (a dead connection) gives its slot back once too",
       db._POOL_SLOTS.acquire(blocking=False) and db._POOL_SLOTS.acquire(blocking=False)
       and not db._POOL_SLOTS.acquire(blocking=False) and pool.lent == 0)
    db._POOL_SLOTS.release(); db._POOL_SLOTS.release()
    pool.fail_next = True
    e = db.get_conn()
    ok("a pool that fails to lend gives the slot straight back and the request opens its own connection",
       not isinstance(e, db._PooledConn) and len(FRESH) == 1
       and db._POOL_SLOTS.acquire(blocking=False) and db._POOL_SLOTS.acquire(blocking=False))
    db._POOL_SLOTS.release(); db._POOL_SLOTS.release()

    # a thread that already holds a pooled connection never waits for a second (it could wait on itself)
    pool = setup(1, 3)
    a = db.get_conn()
    t0 = time.monotonic()
    n = db.get_conn()
    ok("🔴 a nested borrow (this thread already holds the only pooled connection) does not wait: it opens its own",
       not isinstance(n, db._PooledConn) and time.monotonic() - t0 < 0.2 and len(FRESH) == 1, f"{db.POOL_STATS}")
    n.close(); a.close()
    ok("...and once this thread has given its connection back, it borrows from the pool again",
       isinstance(db.get_conn(), db._PooledConn))

    # ------------------------------------------------------------------ #
    #  4. DB_POOL_WAIT_S                                                   #
    # ------------------------------------------------------------------ #
    pool = setup(1, 0)
    a = db.get_conn()
    t0 = time.monotonic()
    c = db.get_conn()
    ok("DB_POOL_WAIT_S=0 keeps the old behaviour: no wait, a fresh connection at once",
       not isinstance(c, db._PooledConn) and time.monotonic() - t0 < 0.1 and len(FRESH) == 1)
    a.close()
    for raw, want in (("3", 3.0), ("", 3.0), ("abc", 3.0), ("-2", 0.0), ("999", 30.0), ("1.5", 1.5)):
        os.environ["DB_POOL_WAIT_S"] = raw
        if db._pool_wait_s() != want:
            ok(f"DB_POOL_WAIT_S={raw!r} reads as {want}", False, str(db._pool_wait_s()))
            break
    else:
        ok("DB_POOL_WAIT_S defaults to 3 s, a bad value reads as 3, and it is held to 0..30 s", True)

    # ------------------------------------------------------------------ #
    #  5. Overlapping heavy builds stay on the pool                        #
    # ------------------------------------------------------------------ #
    pool = setup(3, 3)
    db.IS_PG = False          # the SQLite cursor path in _run (no psycopg2.extras here); get_conn stubbed below
    _real_get = db.get_conn

    def pg_get():
        db.IS_PG = True
        try:
            return _real_get()
        finally:
            db.IS_PG = False
    db.get_conn = pg_get
    errs = []

    def build():
        try:
            for _ in range(60):
                db.query("SELECT 1")
        except Exception as ex:        # noqa: BLE001
            errs.append(repr(ex))
    t0 = time.monotonic()
    ths = [threading.Thread(target=build) for _ in range(8)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(30)
    wall = time.monotonic() - t0
    db.get_conn = _real_get
    ok("⭐ eight overlapping builds of 60 statements on a pool of 3: every statement on a pooled connection "
       "(none opened its own), none failed", not FRESH and not errs and pool.most_lent <= 3 and pool.lent == 0,
       f"fresh={len(FRESH)} errs={errs[:2]} most_lent={pool.most_lent} {db.POOL_STATS}")
    ok("...and they took about the statements' own time (no wait ran out)",
       db.POOL_STATS["wait_ran_out"] == 0 and wall < 10, f"{wall:.2f}s {db.POOL_STATS}")

    # the same load with the OLD behaviour (no wait) opens fresh connections: what this change removes
    pool = setup(3, 0)
    db.get_conn = pg_get
    ths = [threading.Thread(target=build) for _ in range(8)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(30)
    db.get_conn = _real_get
    ok("...where the old no-wait behaviour (DB_POOL_WAIT_S=0) opens fresh connections under the same load",
       len(FRESH) > 0, f"fresh={len(FRESH)}")
finally:
    db.IS_PG, _psy, db._PG_POOL, db._POOL_SLOTS, _w = _orig
    if _psy is None:
        db.__dict__.pop("psycopg2", None)
    else:
        db.psycopg2 = _psy
    if _w is None:
        os.environ.pop("DB_POOL_WAIT_S", None)
    else:
        os.environ["DB_POOL_WAIT_S"] = _w

# ---------------------------------------------------------------------- #
#  6. At source                                                            #
# ---------------------------------------------------------------------- #
src = open(os.path.join(BACKEND, "db.py"), encoding="utf-8").read()
ok("at source: get_conn takes a slot before borrowing and hands it to the _PooledConn",
   "if pool is not None and _take_slot():" in src and "return _PooledConn(pool, conn, slots)" in src
   and "slots.acquire(timeout=wait)" in src)
ok("...the semaphore is the pool's size and is set before the pool is seen by other threads",
   "_POOL_SLOTS = threading.BoundedSemaphore(size)" in src
   and src.index("_POOL_SLOTS = threading.BoundedSemaphore(size)") < src.index("_PG_POOL = built"))
tg = open(os.path.join(ROOT, "frontend", "help", "technical", "index.html"), encoding="utf-8").read()
ok("the technical guide names DB_POOL_WAIT_S with its default beside DB_POOL_MAX",
   "<code>DB_POOL_WAIT_S</code>" in tg and "default 3 s" in tg)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

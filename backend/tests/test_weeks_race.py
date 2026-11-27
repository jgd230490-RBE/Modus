"""
26 Nov 2026 — the Look-ahead's weeks fill race (`claude/weeks-fill-race`).

The Look-ahead's first reads arrive together: the Dashboard's week (`/api/lookahead?restrictions_on=0`), the page itself
(`/api/lookahead`), the Lorry plan and the supplier orders (both build the page's read), the warm-up thread at start-up.
Each is its own kept read, so each runs `weeks.list_weeks` -> `materialise_window`, which READS which weeks exist and
then INSERTS the missing ones. Two requests that read before either wrote both inserted the same week, and the second
hit the table's key: sqlite3.IntegrityError (UNIQUE constraint failed: forecast_weeks...), a 500, and a page stuck on
"Loading the commit week…". Reproduced on a fresh demo database through the real app (four reads at once: two 500s).
`days.materialise_week_days` (the commit week's days, on the same read) has the same read-then-insert shape.

This harness forces the interleave instead of hoping for it: both fills are held after their read until both have
read, then both write. On `main`'s code (ad152be) it fails; with the fix:
  * two fills of the same window / line at once raise nothing and leave exactly one row a week;
  * the counts stay truthful: a week another request wrote is "kept" here, never "created" twice;
  * an edited week and a confirmed week are left EXACTLY as they were (figures, status, parent_qty, stamps);
  * a refresh working from a read taken before a planner's edit does not write the ÷n share over that edit;
  * a fill that met only existing rows writes nothing and says so (db.execute's rows changed);
  * the same for the days of the commit week.
Stubs nothing: db, weeks and days on a scratch SQLite database. Postgres is NOT exercised here.
"""
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)
os.environ.pop("DATABASE_URL", None)

import db  # noqa: E402
TMP = tempfile.mkdtemp(prefix="weeks_race_")
db._SQLITE_PATH = os.path.join(TMP, "race.db")
import weeks  # noqa: E402
import days  # noqa: E402
from portable import remove_scratch_db  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  ok  ", label)
    else:
        FAIL.append(f"{label} {extra}".strip())
        print("  FAIL", label, extra)


LINES = [("R1", "earthworks", "WS1", 120.0), ("R2", "concrete", "WS2", 75.0)]
MONTHS = (1, 2, 3)
EXPECT = len(LINES) * sum(weeks.weeks_in_month(m) for m in MONTHS)
KEY = "route_id, month_index, discipline, section_id, week_index"


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db()
    db.init_weeks_db()
    db.init_lookahead_db()
    db.init_tenant()
    for i, (r, d, s, q) in enumerate(LINES):
        for m in MONTHS:
            db.execute("INSERT INTO forecasts (id, route_id, month_index, discipline, section_id, quantity, unit, "
                       "vehicle_type, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (f"F{i}-{m}", r, m, d, s, q, "t", "Rigid 8-wheeler (32t)", "Approved"))


def week_rows():
    return db.query(f"SELECT * FROM forecast_weeks WHERE tenant_id = ? ORDER BY {KEY}", (db.current_tenant(),))


def dupes(table, key):
    return db.query(f"SELECT {key}, COUNT(*) AS n FROM {table} WHERE tenant_id = ? GROUP BY {key} HAVING COUNT(*) > 1",
                    (db.current_tenant(),))


def held_together(match, n=2):
    """Wrap db.query so the first `n` reads whose SQL contains `match` each wait, after reading, until all `n` have
    read: every fill then works from a read taken before any of them wrote, the interleave seen on 26 Nov."""
    real = db.query
    gate = threading.Barrier(n, timeout=20)
    left = [n]
    lock = threading.Lock()

    def q(sql, params=()):
        rows = real(sql, params)
        if match in sql:
            with lock:
                mine = left[0] > 0
                left[0] -= 1
            if mine:
                gate.wait()
        return rows
    return real, q


def run_together(fns):
    out, errs = [None] * len(fns), [None] * len(fns)

    def one(i):
        try:
            out[i] = fns[i]()
        except Exception as e:                       # the IntegrityError on main's code
            errs[i] = f"{e.__class__.__name__}: {e}"
    ts = [threading.Thread(target=one, args=(i,)) for i in range(len(fns))]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    return out, errs


# =========================================================================== #
#  A. Two fills of the same window at once (materialise_window, the page's read)
# =========================================================================== #
print("A. two fills of one window at once")
reset_db()
real, q = held_together("FROM forecast_weeks WHERE tenant_id = ? AND month_index BETWEEN")
db.query = q
try:
    out, errs = run_together([lambda: weeks.materialise_window(1, 3), lambda: weeks.materialise_window(1, 3)])
finally:
    db.query = real
ok("⭐ A: two fills of the same window at once raise nothing (main: UNIQUE constraint failed on forecast_weeks)",
   errs == [None, None], str(errs)[:300])
rows = week_rows()
ok("⭐ A: exactly one row a week afterwards", len(rows) == EXPECT and not dupes("forecast_weeks", KEY),
   f"{len(rows)} rows, {EXPECT} expected")
got = [o for o in out if o]
ok("⭐ A: between them the two fills CREATED each week once; the one that met the other's rows counts them kept",
   len(got) == 2 and sum(o["created"] for o in got) == EXPECT
   and all(o["created"] + o["refreshed"] + o["kept"] == EXPECT for o in got), str(out))
ok("A: every week written is derived, its share and parent_qty from its own line",
   all(r["status"] == "derived" and abs(r["planned_qty"] * weeks.weeks_in_month(r["month_index"])
                                         - dict((l[0], l[3]) for l in LINES)[r["route_id"]]) < 1e-6
       and abs(r["parent_qty"] - dict((l[0], l[3]) for l in LINES)[r["route_id"]]) < 1e-9 for r in rows))

# four at once, unforced (the page, the Dashboard, the Lorry plan, the warm-up): nothing raises, one row a week
reset_db()
out, errs = run_together([lambda: weeks.list_weeks(1, 3) for _ in range(4)])
ok("A: four first reads at once (list_weeks, unforced) raise nothing", errs == [None] * 4, str(errs)[:300])
ok("A: ... and leave one row a week", len(week_rows()) == EXPECT and not dupes("forecast_weeks", KEY))

# =========================================================================== #
#  B. Two fills of one line at once (materialise_line, the approve path and the re-approve)
# =========================================================================== #
print("B. two fills of one line at once")
reset_db()
real, q = held_together("SELECT week_index, status, planned_qty, unit, parent_qty FROM forecast_weeks")
db.query = q
try:
    out, errs = run_together([lambda: weeks.materialise_line("R1", "earthworks", "WS1", 1),
                              lambda: weeks.materialise_line("R1", "earthworks", "WS1", 1)])
finally:
    db.query = real
n1 = weeks.weeks_in_month(1)
ok("⭐ B: two fills of the same line at once raise nothing", errs == [None, None], str(errs)[:300])
ok("⭐ B: one row a week, the line's month only", len(week_rows()) == n1 and not dupes("forecast_weeks", KEY),
   str(len(week_rows())))
ok("⭐ B: the weeks are created once between them, kept by the other",
   all(out) and sum(o["created"] for o in out) == n1 and sum(o["kept"] for o in out) == n1, str(out))

# =========================================================================== #
#  C. Edited and confirmed weeks are left EXACTLY as they are
# =========================================================================== #
print("C. an edited and a confirmed week")
reset_db()
weeks.materialise_window(1, 3)
r_ed = weeks.set_week("R1", 1, "earthworks", "WS1", 2, planned_qty=999.0, by="planner")
ok("C: the edit is taken (the week goes to edited)", (r_ed.get("week") or {}).get("status") == "edited", str(r_ed)[:200])
db.execute("UPDATE forecast_weeks SET status = 'confirmed', confirmed_by = 'planner', confirmed_at = '2026-01-05', "
           "planned_qty = 31.0 WHERE tenant_id = ? AND route_id = 'R1' AND month_index = 1 AND week_index = 3",
           (db.current_tenant(),))
# the parent month moves, so every derived week of R1 / month 1 needs a refresh, and two of its weeks are missing
db.execute("UPDATE forecasts SET quantity = 200.0 WHERE route_id = 'R1' AND month_index = 1")
db.execute("DELETE FROM forecast_weeks WHERE tenant_id = ? AND route_id = 'R1' AND month_index = 1 AND week_index IN (1, 4)",
           (db.current_tenant(),))


def held_rows():
    return {(r["route_id"], r["month_index"], r["week_index"]): r for r in week_rows()
            if r["status"] in ("edited", "confirmed")}


before = held_rows()
real, q = held_together("FROM forecast_weeks WHERE tenant_id = ? AND month_index BETWEEN")
db.query = q
try:
    out, errs = run_together([lambda: weeks.materialise_window(1, 3), lambda: weeks.materialise_window(1, 3)])
finally:
    db.query = real
ok("⭐ C: the two fills over an edited and a confirmed week raise nothing", errs == [None, None], str(errs)[:300])
ok("⭐ C: the edited and the confirmed week are left exactly as they were, parent_qty and stamps included",
   held_rows() == before and len(before) == 2, str(sorted(before)))
ok("C: the two missing weeks are back once each, at the new month's share",
   sorted(r["week_index"] for r in week_rows() if r["route_id"] == "R1" and r["month_index"] == 1) == list(range(1, n1 + 1))
   and all(abs(r["planned_qty"] - 200.0 / n1) < 1e-9 for r in week_rows()
           if r["route_id"] == "R1" and r["month_index"] == 1 and r["status"] == "derived"))
ok("C: across both fills the edited and the confirmed week are only ever kept (2 a fill), the gap created once",
   all(out) and sum(o["created"] for o in out) == 2, str(out))

# a refresh working from a read taken BEFORE a planner's edit (the edit landed in between) must not write over it
reset_db()
weeks.materialise_window(1, 1)
p = dict(weeks._parent_of("R1", 1, "earthworks", "WS1"), route_id="R1", month_index=1, discipline="earthworks",
         section_id="WS1")
stale = {r["week_index"]: r for r in db.query(
    "SELECT week_index, status, planned_qty, unit, parent_qty FROM forecast_weeks WHERE route_id = 'R1' AND month_index = 1")}
weeks.set_week("R1", 1, "earthworks", "WS1", 1, planned_qty=7.0, by="planner")       # lands after the read
p["quantity"] = 400.0                                                               # and the parent moved too
c, r, k = weeks._materialise_parent(p, stale)
w1 = weeks.get_week("R1", 1, "earthworks", "WS1", 1)
ok("⭐ C: a refresh from a stale read leaves a week edited since untouched (main: the ÷n share wrote over the edit)",
   w1["status"] == "edited" and abs(w1["planned_qty"] - 7.0) < 1e-9 and abs(w1["parent_qty"] - 120.0) < 1e-9,
   str({k2: w1[k2] for k2 in ("status", "planned_qty", "parent_qty")}))
ok("C: ... and counts it kept, the other weeks refreshed", (c, r, k) == (0, n1 - 1, 1), str((c, r, k)))

# =========================================================================== #
#  D. A fill that met only rows already there writes nothing; db.execute says how many rows a write changed
# =========================================================================== #
print("D. a fill that met only rows already there")
reset_db()
weeks.materialise_window(1, 1)
before_d = week_rows()
res = weeks._materialise_parent(dict(weeks._parent_of("R1", 1, "earthworks", "WS1"), route_id="R1", month_index=1,
                                     discipline="earthworks", section_id="WS1"), {})      # as if it read nothing
ok("⭐ D: a fill that read nothing but found every week already written raises nothing and counts them kept",
   res == (0, 0, n1), str(res))
ok("D: ... and leaves every row exactly as it was", week_rows() == before_d)
v1 = db.data_version()
ok("D: db.execute gives the rows a write changed (an UPDATE of one month's weeks, then of none)",
   db.execute("UPDATE forecast_weeks SET planned_qty = planned_qty WHERE route_id = 'R1' AND month_index = 1") == n1
   and db.execute("UPDATE forecast_weeks SET planned_qty = planned_qty WHERE route_id = 'nobody'") == 0)
ok("D: it moves the data version as before, even for no row (a rebuild too many, never a stale figure)",
   db.data_version() >= v1 + 2)

# =========================================================================== #
#  E. The days of the commit week: the same race
# =========================================================================== #
print("E. the days of the commit week")
reset_db()
weeks.materialise_window(1, 1)
wk = weeks.get_week("R1", 1, "earthworks", "WS1", 2)
nd = len(days.bucket_dates(1, 2))
real, q = held_together("FROM forecast_days WHERE tenant_id = ? AND route_id = ?")
db.query = q
try:
    out, errs = run_together([lambda: days.materialise_week_days("R1", 1, "earthworks", "WS1", 2, week=wk, pour_days={}),
                              lambda: days.materialise_week_days("R1", 1, "earthworks", "WS1", 2, week=wk, pour_days={})])
finally:
    db.query = real
DKEY = "route_id, month_index, discipline, section_id, day_date"
drows = db.query("SELECT * FROM forecast_days WHERE tenant_id = ?", (db.current_tenant(),))
ok("⭐ E: two fills of the same week's days at once raise nothing (main: UNIQUE constraint failed on forecast_days)",
   errs == [None, None], str(errs)[:300])
ok("⭐ E: one row a day, each created once between them",
   len(drows) == nd and not dupes("forecast_days", DKEY) and all(out)
   and sum(o["created"] for o in out) == nd and sum(o["kept"] for o in out) == nd, f"{len(drows)} rows; {out}")
# a stale read again: a day edited after the read is left alone
stale_days = days._days_of("R1", 1, "earthworks", "WS1", 2)
d0 = stale_days[0]["day_date"]
db.execute("UPDATE forecast_days SET status = 'edited', planned_qty = 3.0 WHERE day_date = ?", (d0,))
wk2 = dict(wk, planned_qty=float(wk["planned_qty"]) * 2)                              # the week moved
days.materialise_week_days("R1", 1, "earthworks", "WS1", 2, week=wk2, day_rows=stale_days, pour_days={})
dd = db.query("SELECT status, planned_qty FROM forecast_days WHERE day_date = ?", (d0,))[0]
ok("⭐ E: a day refresh from a stale read leaves a day edited since untouched",
   dd["status"] == "edited" and abs(dd["planned_qty"] - 3.0) < 1e-9, str(dd))

# =========================================================================== #
#  F. Source: the inserts and the refreshes say so
# =========================================================================== #
src_w = open(os.path.join(BACKEND, "weeks.py"), encoding="utf-8").read()
src_d = open(os.path.join(BACKEND, "days.py"), encoding="utf-8").read()
ok("F: both fills insert with ON CONFLICT DO NOTHING and count what db.execute says it wrote",
   src_w.count("ON CONFLICT DO NOTHING") == 1 and src_d.count("ON CONFLICT DO NOTHING") == 1
   and "return bool(db.execute(" in src_w and "return bool(db.execute(" in src_d
   and "if db.execute(" in src_w and "if db.execute(" in src_d)
ok("F: both refreshes write a row only while it is still derived",
   "AND section_id = ? AND week_index = ? AND status = 'derived'" in src_w
   and "AND day_date = ? \"\n                    \"AND status = 'derived'" in src_d)

remove_scratch_db(db, TMP)
print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  -", f)
sys.exit(1 if FAIL else 0)

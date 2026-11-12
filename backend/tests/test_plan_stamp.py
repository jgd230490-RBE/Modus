"""
"Approved plan · updated 31 Oct" (10 Nov 2026, branch claude/map-first-view, frontier check Idea 3, John's F2):
backend/plan_stamp.py, the date the public map prints in its title block.

What is asserted: no audit row = None (a date is never made up); each of the four plan writes counts (a line's status,
a line saved, lines withdrawn, the organisation file); everything else in the audit trail does not (a look-ahead week,
a zone, a sign-in, a page open, a failed write, a GET); the newest wins; another scheme's writes are never read; the
date is the UK day (a write at 23:30 UTC in summer is the next day); the read binds the tenant; main sends the date
with the forecast matrix; the map reads it.

WHAT THIS DOES NOT PROVE
------------------------
  * SQLite only (Postgres: `at` is TEXT on both, ISO UTC, so ORDER BY at sorts the same; not run here).
  * The middleware writing the audit row for a real request: http_smoke.py checks the date after a real import over HTTP.
  * What live reads: on 10 Nov 2026 live's newest plan write was the 31 Oct re-import (read in John's Chrome, admin audit).

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_plan_stamp.py
"""
import datetime
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

for v in ("DATABASE_URL", "TENANT_ID"):
    os.environ.pop(v, None)

TMP = tempfile.mkdtemp(prefix="wayscope_planstamp_")
from portable import remove_scratch_db   # noqa: E402
import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
remove_scratch_db(db, TMP)
db.init_db(); db.init_users_db()
import users  # noqa: E402
import plan_stamp  # noqa: E402

PASS, FAIL = 0, []


def ok(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name}  {detail}")


def at(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def write(when, method, path, status=200, kind="write"):
    users.audit(kind, method=method, path=path, status=status, now=at(when), actor=("user", "u1", "Test <t@x>"))


def wipe():
    db.execute("DELETE FROM audit_log WHERE tenant_id = ?", (db.current_tenant(),))


# ---- nothing
wipe()
ok("⭐ no audit row: None, never a made-up date", plan_stamp.last_change() is None)

# ---- writes that do not change the plan
write("2026-11-05T10:00:00Z", "PUT", "/api/forecast-weeks")
write("2026-11-05T10:01:00Z", "POST", "/api/forecast-weeks/confirm")
write("2026-11-05T10:02:00Z", "PUT", "/api/zones/Z001")
write("2026-11-05T10:03:00Z", "PUT", "/api/routes/R001/status", status=403)
write("2026-11-05T10:04:00Z", "GET", "/api/forecasts")
write("2026-11-05T10:05:00Z", "POST", "/api/admin/tenant/import", status=400)
users.audit("page", target="/api/forecasts", now=at("2026-11-05T10:06:00Z"))
users.audit("signin", now=at("2026-11-05T10:07:00Z"))
write("2026-11-05T10:08:00Z", "POST", "/api/admin/limits/import")
write("2026-11-05T10:09:00Z", "PUT", "/api/routes/R001")
ok("⭐ only plan writes count: a look-ahead week, a zone, a refused or failed write, a GET, a page, a sign-in, another import, a route edit do not",
   plan_stamp.last_change() is None, str(plan_stamp.last_change()))

# ---- each plan write counts
for path, method in (("/api/routes/R001/status", "PUT"), ("/api/forecasts/bulk", "POST"),
                     ("/api/forecasts/R001", "DELETE"), ("/api/admin/tenant/import", "POST")):
    wipe()
    write("2026-10-31T09:15:43Z", method, path)
    ok(f"⭐ {method} {path} counts", plan_stamp.last_change() == "2026-10-31", str(plan_stamp.last_change()))

# ---- the newest wins
wipe()
write("2026-10-31T09:15:43Z", "POST", "/api/admin/tenant/import")
write("2026-11-03T14:00:00Z", "PUT", "/api/routes/R009/status")
write("2026-11-02T08:00:00Z", "POST", "/api/forecasts/bulk")
write("2026-11-09T08:00:00Z", "PUT", "/api/forecast-weeks")
ok("⭐ the newest plan write wins (a later non-plan write does not)", plan_stamp.last_change() == "2026-11-03", str(plan_stamp.last_change()))

# ---- the UK day
wipe()
write("2026-07-14T23:30:00Z", "PUT", "/api/routes/R001/status")
ok("⭐ the UK day: 23:30 UTC in July is 00:30 BST the next day", plan_stamp.last_change() == "2026-07-15", str(plan_stamp.last_change()))
wipe()
write("2026-12-14T23:30:00Z", "PUT", "/api/routes/R001/status")
ok("the UK day: 23:30 UTC in December is the same day (GMT)", plan_stamp.last_change() == "2026-12-14", str(plan_stamp.last_change()))
ok("_london_date: a bad value is None, a bare date passes", plan_stamp._london_date("") is None
   and plan_stamp._london_date("nonsense") is None and plan_stamp._london_date("2026-10-31") == "2026-10-31")

# ---- another scheme
wipe()
write("2026-10-31T09:15:43Z", "POST", "/api/admin/tenant/import")
tok = db.set_current_tenant("other-scheme") if hasattr(db, "set_current_tenant") else None
if tok is None:
    tok = db._TENANT.set("other-scheme")
try:
    ok("⭐ another scheme never sees this one's date", plan_stamp.last_change() is None, str(plan_stamp.last_change()))
    write("2026-11-08T09:00:00Z", "PUT", "/api/routes/R001/status")
    ok("...and has its own", plan_stamp.last_change() == "2026-11-08")
finally:
    db._TENANT.reset(tok)
ok("...and its write does not move this one's", plan_stamp.last_change() == "2026-10-31", str(plan_stamp.last_change()))

# ---- source
src = open(os.path.join(BACKEND, "plan_stamp.py"), encoding="utf-8").read()
ok("the read binds the tenant (a name containing 'tenant') and is one LIMIT 1 on audit_log",
   "db.query(PLAN_WRITES_SQL, (tenant_id,))" in src and "WHERE tenant_id = ?" in plan_stamp.PLAN_WRITES_SQL
   and plan_stamp.PLAN_WRITES_SQL.rstrip().endswith("LIMIT 1"))
ok("no BOOLEAN compared with 1, no cache (the audit row lands after the version bump)",
   not re.search(r"=\s*1\b", plan_stamp.PLAN_WRITES_SQL) and "read_cache" not in src.split('"""', 2)[2])
main_src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("⭐ main sends the date with the forecast matrix", 'res["plan_updated"] = plan_stamp.last_change()' in main_src
   and "import plan_stamp" in main_src)
map_src = open(os.path.join(ROOT, "map", "index.html"), encoding="utf-8").read()
ok("⭐ the map reads it", "j.plan_updated" in map_src and "Approved plan \\u00b7 updated " in map_src)

remove_scratch_db(db, TMP)
print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

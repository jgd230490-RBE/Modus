"""
portable.pin_today's clock runs forward across midnight (12 Nov 2026).

On 11 Nov a whole-suite run crossed midnight UTC and http_smoke failed three G3 checks it passes alone: the audit
trail's newest row was not first (two checks) and a lead's 14-day login read as 15 days. pin_today put the pinned day on
every datetime.now() reading but kept the real time of day, so at real midnight the backend's clock jumped from
26 Nov 23:59:59 back to 26 Nov 00:00:00. now() is now shifted, not frozen: the first reading is the pinned day at the
real time, later readings run on by the real clock.

WHAT THIS PROVES (a fake real clock, portable._REAL_NOW, stepped from 23:59:58 to 00:00:02 the next day)
  * the first now() reads the pinned day at the real time of day, with and without a time zone;
  * across midnight now() moves FORWARD by the real 4 seconds onto the next day, never back;
  * date.today() stays the pinned day;
  * the backend's own clock (users._now, read through the pin) and its ISO stamps sort in time order across midnight,
    and a 14-day login made just before midnight has under 14 days left just after it.

WHAT THIS DOES NOT PROVE
  * a real midnight run of the whole suite (http_smoke's three checks are the real case; they read this clock).

Run:  python backend/tests/test_pin_today.py
"""
import datetime
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

for _v in ("DATABASE_URL", "TENANT_ID"):
    os.environ.pop(_v, None)
TMP = tempfile.mkdtemp(prefix="wayscope_pintoday_")

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import users  # noqa: E402
import portable  # noqa: E402

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


UTC = datetime.timezone.utc
RealDT = datetime.datetime
CLOCK = {"t": RealDT(2026, 11, 11, 23, 59, 58, tzinfo=UTC)}


def fake_now(tz=None):
    t = CLOCK["t"]
    return t.astimezone(tz) if tz is not None else t.replace(tzinfo=None)


portable._REAL_NOW = fake_now
DAY = datetime.date(2026, 11, 26)
pinned = portable.pin_today(DAY, extra=("users",))
ok("pin_today returns the pinned day", pinned == DAY)

DT = sys.modules["datetime"].datetime
D = sys.modules["datetime"].date

# ---- before midnight
a_utc = DT.now(UTC)
a_naive = DT.now()
u_a = users._now()
ok("the first now() in UTC is the pinned day at the real time of day",
   (a_utc.date(), a_utc.hour, a_utc.minute, a_utc.second) == (DAY, 23, 59, 58), str(a_utc))
ok("...and without a time zone the same", (a_naive.date(), a_naive.hour, a_naive.second) == (DAY, 23, 58), str(a_naive))
ok("the backend's own clock (users._now) reads the pin", u_a.date() == DAY and u_a.hour == 23, str(u_a))
login_expires = u_a + datetime.timedelta(days=users.DEMO_DAYS)

# ---- the real clock crosses midnight
CLOCK["t"] = RealDT(2026, 11, 12, 0, 0, 2, tzinfo=UTC)
b_utc = DT.now(UTC)
b_naive = DT.now()
u_b = users._now()
ok("across midnight now() moves FORWARD by the real 4 seconds, onto the next day (was: back 24 hours)",
   b_utc - a_utc == datetime.timedelta(seconds=4) and b_utc.date() == DAY + datetime.timedelta(days=1), str(b_utc))
ok("...without a time zone too", b_naive - a_naive == datetime.timedelta(seconds=4), str(b_naive))
ok("date.today() stays the pinned day", D.today() == DAY, str(D.today()))
ok("the backend's ISO stamps sort in time order across midnight (the audit trail's newest row first)",
   users._iso(u_b) > users._iso(u_a) and sorted([users._iso(u_b), users._iso(u_a)], reverse=True)[0] == users._iso(u_b),
   f"{users._iso(u_a)} {users._iso(u_b)}")
left = int((login_expires - u_b).total_seconds())
ok("a 14-day login made just before midnight has under 14 days left just after it (http_smoke HU14's Max-Age=1209…)",
   0 < left <= users.DEMO_DAYS * 86400 and str(left).startswith("1209"), str(left))

portable._REAL_NOW = None
print(f"\n{PASS} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print("  -", f)
    sys.exit(1)

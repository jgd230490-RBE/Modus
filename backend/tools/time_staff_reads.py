"""
tools/time_staff_reads.py — time the staff screens' heavy reads on a COPY of a database, in-process (28 Oct 2026, the
demo narrative's F1). Prints each read's time, how often it ran, and whether the read itself moved db.data_version()
(a read that writes would empty read_cache's entries every time it runs).

    python backend/tools/time_staff_reads.py <copy-of-a-database.db> [tenant] [repeat]

Never point it at a database you care about: some reads create the week rows they show.
"""
import datetime
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

DB_PATH = sys.argv[1]
TENANT = sys.argv[2] if len(sys.argv) > 2 else "wolds-link-demo"
REPEAT = int(sys.argv[3]) if len(sys.argv) > 3 else 2
for v in ("DATABASE_URL", "HERE_API_KEY", "MAPBOX_TOKEN"):
    os.environ.pop(v, None)
os.environ["TENANT_ID"] = TENANT
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = DB_PATH
import access  # noqa: E402
import main  # noqa: E402

ADMIN = {"role": "admin", "label": "Admin", "ipt": None, "via": "login", "kind": "staff"}
access._ACCESS.set(ADMIN)
month = main.weeks.month_index_of(datetime.date.today())
lo, hi = max(1, month - 6), min(main.MONTH_COUNT, month + 6)

READS = [
    ("costing lines (Dashboard range)", lambda: main.costing_lines(from_=lo, to=hi, status=None)),
    ("look-ahead (commit)", lambda: main.lookahead_page(bucket="commit")),
    ("gate arrivals (this month)", lambda: main.gate_arrivals_month(month=None)),
    ("CLP monitoring (this month)", lambda: main.clp_monitoring(month=None)),
    ("routes status", lambda: main.routes_status()),
    ("routes summary", lambda: main.routes_summary()),
    ("routes diversions", lambda: main.routes_diversions(route_id=None)),
    ("carbon scenario (Approved)", lambda: main.carbon_scenario(main.CarbonScenarioIn())),
]

for name, fn in READS:
    for i in range(REPEAT):
        v0 = db.data_version()
        t0 = time.perf_counter()
        try:
            fn()
            err = ""
        except Exception as e:      # a read the stubs cannot run is reported, not fatal
            err = f"  ERROR {type(e).__name__}: {str(e)[:80]}"
        dt = time.perf_counter() - t0
        moved = db.data_version() - v0
        print(f"{name:34s} run {i + 1}: {dt:6.2f} s  data_version +{moved}{err}")

"""
The hand-over check from the inside (28 Oct 2026, pilot readiness phase 3, F3 a). Someone signed in to Render runs,
in the service's Shell tab:

    python backend/check_deployment.py

It prints which settings are set (names only, never a value), what the database holds for this organisation (admin
logins and their two-step sign-in, the data loaded) and every problem `deployment.problems()` finds. Exit 0 when
nothing must be fixed, 1 otherwise. It reads only; it changes nothing. Its outside twin is
`backend/tools/check_pilot.py <address>`, run from a laptop.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _count(db, sql, args=()):
    try:
        return int(db.query(sql, args)[0]["n"])
    except Exception:  # noqa: BLE001 — a table a new deployment has not made yet reads as none
        return 0


def database_facts():
    """{database, admins, admins_two_step, staff_logins, locations, routes}."""
    import db
    import users
    t = db.current_tenant()
    try:
        rows = db.query("SELECT role, kind, disabled, totp_secret FROM users WHERE tenant_id = ?", (t,))
    except Exception:  # noqa: BLE001 — a deployment that has never started has no users table: no logins
        rows = []
    live = [r for r in rows if not r.get("disabled")]
    admins = [r for r in live if r.get("role") == "admin"]
    return {
        "database": "postgres" if db.IS_PG else "sqlite (a file)",
        "admins": len(admins),
        "admins_two_step": sum(1 for r in admins if users.two_step_on(r)),
        "staff_logins": sum(1 for r in live if (r.get("kind") or "staff") != "demo"),
        "locations": _count(db, "SELECT COUNT(*) AS n FROM locations WHERE tenant_id = ?", (t,)),
        "routes": _count(db, "SELECT COUNT(*) AS n FROM routes WHERE tenant_id = ?", (t,)),
    }


def lines(env=None, facts=None):
    import deployment
    env = os.environ if env is None else env
    facts = database_facts() if facts is None else facts
    out = deployment.report_lines(env, admins=facts["admins"])
    out.insert(1, f"database: {facts['database']} · admin logins {facts['admins']} "
                  f"({facts['admins_two_step']} with two-step on) · staff logins {facts['staff_logins']} · "
                  f"locations {facts['locations']} · routes {facts['routes']}")
    if deployment.kind(env) == "organisation" and facts["admins"] > facts["admins_two_step"]:
        out.append("deployment ⚠ An admin has not set up two-step sign-in yet (it is asked at their next sign-in).")
    return out


def main(argv):
    out = lines()
    print("\n".join(out))
    return 1 if any(l.startswith("deployment ✗") for l in out) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

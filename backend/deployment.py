"""
What this deployment is set up with, and what an organisation's own deployment must fix before it is handed
over (28 Oct 2026, pilot readiness phase 3, F3 a).

Names only, NEVER a value: the report says "GATE_SECRET set", not what it is. TENANT_ID and APP_URL are not
secrets and are shown as they are.

Two kinds of deployment:
  demo           DEMO_LEADS is on (the landing form makes logins). Fictional data; the shared codes and the
                 admin token are allowed while they are being retired.
  organisation   everything else on the hosting. Real data: no standing admin secret, no shared code, its own
                 address in every link, its own map-cookie key, a way in for its first admin.
Off the hosting (no RENDER variable: a laptop, the harnesses) the kind is "local" and nothing is a problem.

Used at start-up (one "deployment:" line in the service log, plus one line per problem) and by
`python backend/check_deployment.py` in the hosting's shell, which adds what only the database knows.
"""
import os

KINDS = ("local", "demo", "organisation")
MUST, SHOULD = "must", "should"

CODE_VARS = tuple(f"IPT{i}_CODE" for i in range(1, 7)) + ("PLANNER_CODE", "ADMIN_CODE")
MAIL_VARS = ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM")
# the settings the report names as set / not set (values never read out)
LISTED = ("DATABASE_URL", "TENANT_ID", "APP_URL", "FIRST_ADMIN_EMAIL", "GATE_SECRET", "MAP_PASSWORD",
          "HERE_API_KEY", "MAPBOX_TOKEN") + MAIL_VARS + ("DEMO_LEADS", "ADMIN_TOKEN") + CODE_VARS + (
          "ALLOW_DEMO_CODES", "MAP_GATE")
DEMO_ADDRESSES = ("app.wayscope.co.uk", "modus-web.onrender.com")


def _get(env, name):
    return (env.get(name) or "").strip()


def _truthy(env, name):
    return _get(env, name).lower() in ("1", "true", "yes", "on")


def _gate_off(env):
    v = _get(env, "MAP_GATE").lower()
    return bool(v) and v in ("off", "0", "false", "no")


def kind(env=None):
    env = os.environ if env is None else env
    if not _get(env, "RENDER"):
        return "local"
    return "demo" if _truthy(env, "DEMO_LEADS") else "organisation"


def problems(env=None, admins=None):
    """[(level, words)]. `admins` is the number of admin logins when the caller knows it (None = not looked)."""
    env = os.environ if env is None else env
    k = kind(env)
    if k == "local":
        return []
    out = []
    if not _get(env, "DATABASE_URL"):
        out.append((MUST, "DATABASE_URL is not set: the data sits in a file the next deploy throws away."))
    if _truthy(env, "ALLOW_DEMO_CODES"):
        out.append((MUST, "ALLOW_DEMO_CODES is on: the well-known demo codes could sign in. Delete it."))
    if _gate_off(env):
        out.append((MUST, "MAP_GATE is off: the map and the guides are open to anyone. Delete it."))
    if k == "demo":
        return out
    if _get(env, "ADMIN_TOKEN"):
        out.append((MUST, "ADMIN_TOKEN is set: an organisation's deployment keeps no standing admin secret. Delete it."))
    codes = [v for v in CODE_VARS if _get(env, v)]
    if codes:
        out.append((MUST, "Shared codes are set (" + ", ".join(codes) + "): people sign in with their own logins. "
                    "Delete them."))
    url = _get(env, "APP_URL").rstrip("/")
    if not url:
        out.append((MUST, "APP_URL is not set: invite and reset links would point at the demo."))
    elif not url.startswith("https://"):
        out.append((MUST, "APP_URL must start with https://."))
    elif any(a in url.lower() for a in DEMO_ADDRESSES):
        out.append((MUST, "APP_URL is the demo's address: links would send people to the demo."))
    if not _get(env, "GATE_SECRET"):
        out.append((MUST, "GATE_SECRET is not set: give this deployment its own fresh value."))
    if admins == 0 and not _get(env, "FIRST_ADMIN_EMAIL"):
        out.append((MUST, "No admin login and no FIRST_ADMIN_EMAIL: nobody can sign in to set this up."))
    if not _get(env, "TENANT_ID") or _get(env, "TENANT_ID").lower() == "default":
        out.append((SHOULD, "TENANT_ID is not set: name the organisation (its short name)."))
    if not all(_get(env, v) for v in MAIL_VARS):
        out.append((SHOULD, "Email is not set up (SMTP_USER, SMTP_PASSWORD, DEMO_FROM): invites and resets go to "
                    "the service log only."))
    if not _get(env, "MAP_PASSWORD"):
        out.append((SHOULD, "MAP_PASSWORD is not set: outside viewers cannot open the map (staff can)."))
    if not _get(env, "HERE_API_KEY"):
        out.append((SHOULD, "HERE_API_KEY is not set: routes cannot be drawn."))
    if not _get(env, "MAPBOX_TOKEN"):
        out.append((SHOULD, "MAPBOX_TOKEN is not set: the staff maps and the PDF maps have no basemap."))
    return out


def summary(env=None):
    """{kind, tenant, app_url, set, unset} — names only."""
    env = os.environ if env is None else env
    return {
        "kind": kind(env),
        "tenant": _get(env, "TENANT_ID") or "default",
        "app_url": _get(env, "APP_URL").rstrip("/") or "(not set)",
        "set": [n for n in LISTED if _get(env, n)],
        "unset": [n for n in LISTED if not _get(env, n)],
    }


def report_lines(env=None, admins=None):
    """The lines for the service log and the shell check. The first is always the 'deployment:' line."""
    s = summary(env)
    lines = [f"deployment: {s['kind']} · tenant {s['tenant']} · links {s['app_url']} · set: "
             + (", ".join(s["set"]) or "nothing")]
    for level, words in problems(env, admins):
        lines.append(("deployment ✗ " if level == MUST else "deployment ⚠ ") + words)
    if s["kind"] != "local" and not any(l.startswith("deployment ✗") for l in lines):
        lines.append("deployment ✓ nothing that must be fixed")
    return lines

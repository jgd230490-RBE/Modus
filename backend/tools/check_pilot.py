"""
The hand-over check from the outside (28 Oct 2026, pilot readiness phase 3, F3 a). From a laptop, before an
organisation's deployment is handed over, and again after any change to its settings:

    python backend/tools/check_pilot.py https://acme.wayscope.co.uk
    python backend/tools/check_pilot.py https://app.wayscope.co.uk --demo      (the demo: the form and token allowed)

It asks the deployment what anyone on the internet can ask, and nothing more: it signs in to nothing, sends no
password, creates nothing. The lead form is tried with only its hidden trap field filled in, which the app answers
without storing anything whether the form is on or off. Exit 0 when every check passes, 1 otherwise.
Standard library only. Its inside twin is `python backend/check_deployment.py` in the hosting's shell.
"""
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

HEADERS = ("strict-transport-security", "content-security-policy", "x-content-type-options", "x-frame-options",
           "referrer-policy", "permissions-policy")
PASS, FAIL, NOTE = "pass", "FAIL", "note"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def http_fetch(method, url, data=None, headers=None, timeout=30):
    """(status, {header-lower: value}, body text). Never follows a redirect; an HTTP error is an answer, not a raise."""
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    req.add_header("User-Agent", "wayscope-check-pilot/1")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        r = opener.open(req, timeout=timeout)
        status, hdrs, body = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        status, hdrs, body = e.code, e.headers, e.read()
    return status, {k.lower(): v for k, v in hdrs.items()}, body.decode("utf-8", "replace")


def checks(base, fetch=http_fetch, demo=False):
    """[(result, what)] for the deployment at `base` (https://host, no path)."""
    base = base.rstrip("/")
    out = []

    def add(ok, what, note=False):
        out.append((NOTE if note else (PASS if ok else FAIL), what))

    if not base.startswith("https://"):
        add(False, "The address must start with https://")
        return out
    try:
        s, h, b = fetch("GET", base + "/api/health")
    except Exception as e:  # noqa: BLE001 — no answer at all (DNS, certificate, timeout)
        add(False, f"No answer from {base}: {e.__class__.__name__}: {str(e)[:160]}")
        return out
    add(s == 200, f"Health: {s}")

    host = urllib.parse.urlsplit(base).hostname
    try:
        s, h, b = fetch("GET", "http://" + host + "/api/health")
        add(s in (301, 302, 307, 308) and h.get("location", "").startswith("https://"),
            f"Plain http goes to https: {s}")
    except Exception as e:  # noqa: BLE001
        add(False, f"Plain http: no answer ({e.__class__.__name__})")

    s, h, b = fetch("GET", base + "/")
    add(s == 200, f"Sign-in page: {s}")
    missing = [n for n in HEADERS if not h.get(n)]
    add(not missing, "Security headers on the app page" + (": missing " + ", ".join(missing) if missing else ""))
    add("frame-ancestors" in h.get("content-security-policy", ""), "The page refuses to be framed by another site")

    s, h, b = fetch("GET", base + "/api/auth/me")
    add("no-store" in h.get("cache-control", ""), "Sign-in answers are never cached")

    s, h, b = fetch("GET", base + "/api/admin/users")
    if s in (401, 403) and "not configured" in b:
        add(True, f"Admin calls refused without an admin login ({s}); no admin token is set")
    elif s in (401, 403):
        add(demo, f"Admin calls refused without an admin login ({s}), but an admin token IS set"
            + (" (allowed on the demo)" if demo else ": delete ADMIN_TOKEN"), note=demo)
    else:
        add(False, f"Admin calls answer without an admin login: {s}")

    s, h, b = fetch("POST", base + "/api/public/demo-request", data=b"website=check-pilot",
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    loc = h.get("location", "")
    if s == 303 and loc.endswith("/error.html"):
        add(not demo, "The landing form is off here" + (": the demo needs DEMO_LEADS=1" if demo else ""))
    elif s == 303 and loc.endswith("/thanks.html"):
        add(demo, "The landing form is ON here" + ("" if demo else ": it would give a stranger a login. "
                                                   "Delete DEMO_LEADS"))
    else:
        add(False, f"The landing form answered {s} {loc}")

    s, h, b = fetch("GET", base + "/map/", headers={"Accept": "text/html"})
    if s == 401:
        add(True, "The public map asks for its password")
    elif s == 503:
        add(True, "The public map has no password set: outside viewers are refused (staff can open it)", note=True)
    else:
        add(False, f"The public map opened without a password: {s}")

    s, h, b = fetch("GET", base + "/help/", headers={"Accept": "text/html"})
    add(s == 401, f"The guides ask for a staff sign-in: {s}")

    try:
        name, aliases, _ = socket.gethostbyname_ex(host)
        chain = [a for a in aliases + [name] if a != host]
        add(True, "Address points at: " + (" -> ".join(chain) if chain else name), note=True)
    except Exception as e:  # noqa: BLE001
        add(True, f"Address lookup: {e.__class__.__name__}", note=True)
    return out


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print("Usage: python backend/tools/check_pilot.py https://acme.wayscope.co.uk [--demo]")
        return 2
    rows = checks(args[0], demo="--demo" in argv)
    for result, what in rows:
        print(f"{result:4}  {what}")
    failed = sum(1 for r, _ in rows if r == FAIL)
    print(f"\n{len(rows) - failed} of {len(rows)} without a failure." if not failed else f"\n{failed} FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

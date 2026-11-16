"""
16 Nov 2026 (claude/tools-shell) — the public tool pages and their open calls.

John's order of 16 Nov ("start the first opening"): three free calculators, the abnormal load adviser's free check and a
route check by request, each a page anyone can open at app.wayscope.co.uk/tools/<page>, with no demo bar, no sign-in and no
balance. This module is the frame they share; each tool adds its own page and its own calls on top of it.

WHERE THE PAGES LIVE
--------------------
`frontend/tools/<page>.html` is served at `/tools/<page>` (no ".html" in the address), with the shared `tools.css` and
`tools.js` at `/tools/tools.css` and `/tools/tools.js`. `page_file()` decides: a lower-case name of letters, digits and
dashes that names an existing page, or one of the shared files by its exact name. Everything else under /tools, and /tools
and /tools/ themselves, is a 404: the Tools index is a plain page on the LANDING site (wayscope.co.uk/tools), not here.

The gate (gate.scope_for) polices /map, /help, /bulletin and the map's data prefixes only, so /tools and /api/tools are open
without a gate change; smoke_tools_pages.py proves it with the gate on and no cookie.

A page names the landing site as https://wayscope.co.uk; `page_bytes()` swaps in LANDING_URL where that is set (the same
setting the demo form's redirects read, demo_request.landing_url).

THE OPEN-CALL RULE (/api/tools/…)
---------------------------------
1. JSON in, JSON out. POST for a call that works something out (the body can be long); never a query string with a
   person's details in it.
2. No cookie needed and none read: the shared script sends none (`credentials: "omit"`), and a call must not look at
   access.current(). Nothing of any organisation's plan goes in or comes out: a tool works on the figures typed and on
   the shipped defaults (backend/factors.json), never on the tenant's Config.
3. Every call takes `guard(request, LIMIT)` first, with a Limit of its own (a count per hashed address in a window, the
   landing form's pattern, demo_request.PER_IP_PER_HOUR). A refusal is `refuse(status, sentence)`: the answer is
   {"detail": {"say": "<one plain sentence>"}} and the shared script shows that sentence and nothing else.
4. A form that a person types into carries the hidden trap box (`TRAP`, the landing form's "website"); `trapped(body)`
   is true when a machine filled it, and the call then answers as if it worked and does nothing.
5. The route is added to OPEN_ROUTES below, so the reviewer-wall sweep knows it is open on purpose
   (smoke_reviewer_wall.py, its last block, fails on any /api/tools route not listed).
6. /api/tools/ is in main.AUDIT_SKIP_PREFIXES: an open call writes no audit row and empties no kept read (otherwise every
   calculator press on the demo would throw away the CLP draft and the bulletin the demo opens on). It is also in
   security_headers.NO_STORE_PREFIXES: no browser or proxy keeps a tool's answer.

THE LIMIT IS IN MEMORY, per process. The app runs one process (no second worker: read_cache), so the count is the whole
app's; a restart (every merge) starts it again. That is enough to stop a script hammering a calculator; it is not a quota,
and a paid tool's count (N11, "a run is counted on the server") belongs in the database, with its own table.
"""
import hashlib
import os
import re
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "frontend" / "tools"

#: the shared files every tool page loads, by their exact names, and their types
SHARED_FILES = {"tools.css": "text/css; charset=utf-8", "tools.js": "text/javascript; charset=utf-8"}
#: a tool page's name in its address: /tools/calculators, /tools/abnormal-load, /tools/route-check
_PAGE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
#: never served as a page, whatever is in the folder (the index lives on the landing site)
NOT_PAGES = ("index",)

#: how a page names the landing site; page_bytes() swaps in LANDING_URL
LANDING_DEFAULT = "https://wayscope.co.uk"

#: every open /api/tools route, by its path as FastAPI registers it. A tool session adds its own here, and the
#: reviewer-wall sweep fails on any /api/tools route missing from this list.
OPEN_ROUTES = ()

#: the hidden box only a machine fills in (the landing form's trap, demo_request.HONEYPOT)
TRAP = "website"


# --------------------------------------------------------------------------- the pages

def page_file(name):
    """(path, media type) for /tools/<name>, or None (the caller answers 404)."""
    if not isinstance(name, str) or not name or len(name) > 60:
        return None
    if name in SHARED_FILES:
        p = TOOLS_DIR / name
        return (p, SHARED_FILES[name]) if p.is_file() else None
    if not _PAGE_NAME.match(name) or name in NOT_PAGES:
        return None
    p = TOOLS_DIR / (name + ".html")
    return (p, "text/html; charset=utf-8") if p.is_file() else None


def pages():
    """The tool pages in the folder, by their address names (the UI audit and the harness walk these)."""
    if not TOOLS_DIR.is_dir():
        return []
    return sorted(p.stem for p in TOOLS_DIR.glob("*.html") if _PAGE_NAME.match(p.stem) and p.stem not in NOT_PAGES)


def landing_url():
    return (os.getenv("LANDING_URL") or LANDING_DEFAULT).strip().rstrip("/")


def page_bytes(path):
    """A page's bytes with the landing site's address set; the shared files as they are."""
    data = Path(path).read_bytes()
    if str(path).endswith(".html"):
        lu = landing_url()
        if lu != LANDING_DEFAULT:
            data = data.replace(('href="' + LANDING_DEFAULT).encode("utf-8"), ('href="' + lu).encode("utf-8"))
    return data


# --------------------------------------------------------------------------- the limit

def address_hash(ip):
    """The address is never kept as typed: a salted hash, as the demo form keeps it (demo_request.ip_hash)."""
    salt = (os.getenv("GATE_SECRET") or os.getenv("ADMIN_TOKEN") or "wayscope").strip()
    return hashlib.sha256(("tools|" + salt + "|" + (ip or "")).encode("utf-8")).hexdigest()[:32]


def client_ip(request):
    """The visitor's address behind Render's proxy (the first X-Forwarded-For entry), as the demo form reads it."""
    try:
        import demo_request
        return demo_request.client_ip(request.headers.get("x-forwarded-for"),
                                      request.client.host if getattr(request, "client", None) else "")
    except Exception:
        return ""


def _window_words(window_s):
    if window_s >= 3600 and window_s % 3600 == 0:
        n = window_s // 3600
        return "an hour" if n == 1 else f"{n} hours"
    n = max(1, int(round(window_s / 60.0)))
    return "a minute" if n == 1 else f"{n} minutes"


class Limit:
    """At most `most` calls per hashed address in any `window_s` seconds. In memory; see the module's note."""

    #: addresses kept at most; past it the oldest-touched are dropped (a flood of addresses cannot grow memory)
    MAX_KEYS = 20000

    def __init__(self, name, most, window_s):
        if not name or int(most) < 1 or int(window_s) < 1:
            raise ValueError("a limit needs a name, a count of at least 1 and a window")
        self.name = name
        self.most = int(most)
        self.window_s = int(window_s)
        self._hits = {}
        self._lock = threading.Lock()

    @property
    def say(self):
        """The refusal sentence: plain words, no number of calls, no status."""
        return f"Too many checks from this connection. Please try again in {_window_words(self.window_s)}."

    def hit(self, ip, now=None):
        """Count one call from this address. True when it is allowed; False (and nothing counted) when over."""
        now = time.time() if now is None else float(now)
        key = address_hash(ip)
        with self._lock:
            kept = [t for t in self._hits.get(key, ()) if now - t < self.window_s]
            if len(kept) >= self.most:
                self._hits[key] = kept
                return False
            kept.append(now)
            self._hits.pop(key, None)          # re-insert: the dict's order is the touch order
            self._hits[key] = kept
            if len(self._hits) > self.MAX_KEYS:
                for k in list(self._hits)[: len(self._hits) - self.MAX_KEYS]:
                    self._hits.pop(k, None)
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()


# --------------------------------------------------------------------------- refusals

def _http_exception():
    try:
        from fastapi import HTTPException
        return HTTPException
    except Exception:          # the stubbed sandbox
        return None


class Refused(Exception):
    """Raised where FastAPI is not importable; carries the same status and sentence."""

    def __init__(self, status_code, detail):
        super().__init__(detail.get("say", ""))
        self.status_code = status_code
        self.detail = detail


def refuse(status, say):
    """Raise the open-call refusal: status `status`, body {"detail": {"say": say}}. One plain sentence."""
    exc = _http_exception() or Refused
    raise exc(status_code=int(status), detail={"say": str(say)})


def guard(request, limit):
    """The first line of every open call: refuse with 429 and the limit's sentence when this address is over."""
    if not limit.hit(client_ip(request)):
        refuse(429, limit.say)


def trapped(body):
    """True when the hidden trap box came back filled in (a machine): answer as if it worked and do nothing."""
    try:
        return bool(str((body or {}).get(TRAP) or "").strip())
    except Exception:
        return False

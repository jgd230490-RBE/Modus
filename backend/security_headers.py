"""
Pilot readiness phase 2 (27 Oct 2026, F3 e) — the security headers every answer of the app carries.

One middleware in main.py adds HEADERS to every response (pages, the map, the guides, the bulletin, the API and the
gate's refusal pages), and NO_STORE_PREFIXES add `Cache-Control: no-store` to the sign-in calls (a set-up answer holds
an authenticator key and recovery codes; nothing of that may sit in a cache).

THE CONTENT SECURITY POLICY, and its honest limit
-------------------------------------------------
The pages compile their own React in the browser (Babel, no build step: a standing constraint), so scripts need
'unsafe-inline' and 'unsafe-eval'. The policy therefore does not stop injected inline script; what it does is name
every place code, styles, fonts, frames and data may come from, refuse plugins (`object-src 'none'`), pin `<base>`
and form targets to this site, and refuse to be framed by another site (`frame-ancestors 'self'`: the staff app frames
the public map, same origin). A strict policy needs a build step.

Adding a new outside host to a page (a basemap's tiles, a script) means adding it here too:
backend/tests/test_hardening.py fails on any https host a page names that the policy does not allow.
"""

import re

#: where each kind of thing may be loaded from
CSP_SOURCES = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'unsafe-inline'", "'unsafe-eval'", "https://unpkg.com", "https://cdn.jsdelivr.net",
                   "https://api.mapbox.com"],
    "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://api.mapbox.com"],
    "font-src": ["'self'", "data:", "https://fonts.gstatic.com"],
    # map tiles, sprites, Street View pictures and the bulletin's static maps are images from several services
    "img-src": ["'self'", "data:", "blob:", "https:"],
    # Mapbox GL fetches styles, tiles, glyphs and its event pings; the Estonian ortho tiles for an EE tenant; OS's own web
    # service for the OS map (28 Oct 2026, 8b: its style, tiles, fonts and sprites). A tenant's OWN imagery host is not
    # listed here: it is typed on Config, so csp(extra_connect) adds that one host to the MAP page's policy only. Google Fonts'
    # CSS too: accessibility checkers (axe, which the UI audit runs) re-read every stylesheet with fetch(), and the policy
    # refused it on every page (UI audit run 2026-10-27_230343); it serves font CSS only.
    # blob: (31 Oct 2026, task 4c PR 3): a pinned picture read by the app for a code sign-in (its code goes in a header,
    # which the map's own image read cannot send) is handed to the map as a copy in this browser, which the map fetches
    "connect-src": ["'self'", "blob:", "https://api.mapbox.com", "https://*.tiles.mapbox.com", "https://events.mapbox.com",
                    "https://tiles.maaamet.ee", "https://api.os.uk", "https://fonts.googleapis.com"],
    # Mapbox GL runs its workers from blob: URLs
    "worker-src": ["'self'", "blob:"],
    "child-src": ["'self'", "blob:"],
    "frame-src": ["'self'"],
    "frame-ancestors": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
}


def csp(extra_connect=()):
    """The policy as one header value. `extra_connect` = origins added to connect-src for this answer (a tenant's imagery host
    on the map page); each must be a plain https origin, anything else is dropped, so a typed address cannot add a directive."""
    src = dict(CSP_SOURCES)
    extra = [o for o in (extra_connect or ()) if isinstance(o, str) and _ORIGIN_RE.match(o)]
    if extra:
        src["connect-src"] = src["connect-src"] + [o for i, o in enumerate(extra) if o not in src["connect-src"] and o not in extra[:i]]
    return "; ".join(f"{k} {' '.join(v)}" for k, v in src.items())


_ORIGIN_RE = re.compile(r"^https://[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::[0-9]{1,5})?$")

HEADERS = {
    # HTTPS only for a year. No includeSubDomains: the rule would bind every *.wayscope.co.uk, decided per subdomain.
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Content-Security-Policy": csp(),
}

#: answers that must never be kept by a browser or a proxy
NO_STORE_PREFIXES = ("/api/auth/", "/api/admin/users")


def apply(path, headers, extra_connect=()):
    """Set the headers on a response's header mapping (Starlette's MutableHeaders or a plain dict). A header the
    endpoint already set is kept, except Cache-Control on a NO_STORE path, which becomes no-store. `extra_connect`: see csp()."""
    for k, v in HEADERS.items():
        if k not in headers:
            headers[k] = csp(extra_connect) if k == "Content-Security-Policy" and extra_connect else v
    if any((path or "").startswith(p) for p in NO_STORE_PREFIXES):
        headers["Cache-Control"] = "no-store"
    return headers

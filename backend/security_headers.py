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

#: where each kind of thing may be loaded from
CSP_SOURCES = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'unsafe-inline'", "'unsafe-eval'", "https://unpkg.com", "https://cdn.jsdelivr.net",
                   "https://api.mapbox.com"],
    "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://api.mapbox.com"],
    "font-src": ["'self'", "data:", "https://fonts.gstatic.com"],
    # map tiles, sprites, Street View pictures and the bulletin's static maps are images from several services
    "img-src": ["'self'", "data:", "blob:", "https:"],
    # Mapbox GL fetches styles, tiles, glyphs and its event pings; the Estonian ortho tiles for an EE tenant
    "connect-src": ["'self'", "https://api.mapbox.com", "https://*.tiles.mapbox.com", "https://events.mapbox.com",
                    "https://tiles.maaamet.ee"],
    # Mapbox GL runs its workers from blob: URLs
    "worker-src": ["'self'", "blob:"],
    "child-src": ["'self'", "blob:"],
    "frame-src": ["'self'"],
    "frame-ancestors": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
}


def csp():
    return "; ".join(f"{k} {' '.join(v)}" for k, v in CSP_SOURCES.items())


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


def apply(path, headers):
    """Set the headers on a response's header mapping (Starlette's MutableHeaders or a plain dict). A header the
    endpoint already set is kept, except Cache-Control on a NO_STORE path, which becomes no-store."""
    for k, v in HEADERS.items():
        if k not in headers:
            headers[k] = v
    if any((path or "").startswith(p) for p in NO_STORE_PREFIXES):
        headers["Cache-Control"] = "no-store"
    return headers

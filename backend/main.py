"""
Wayscope — backend.

Serves three things from one process:
  1. The forecasting API under /api/*
  2. The React forecasting app at /
  3. The Mapbox route map at /map/

The Public Route Map reads /api/public/route-forecasts, so the map and the
forecasting app are always in sync — no CSV files to keep up to date.
"""
import hashlib
import hmac
import json
import os
from html import escape as _html_escape
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import conversions
import db
import network
import here_routing
import taxonomy
import zones
import haul          # Phase 4 — temporary haul roads
import restrictions  # Phase 2.5a Tark Tee; H1 (29 Sep) a provider per country (NH closures for GB)
import streetview    # Phase 2.5a — Google Street View proxy (key stays server-side)
import gates         # Phase 5a — multiple gates per location, with a direction on each
import weeks         # Week 1 — the 4-week look-ahead and typed actuals (Tasks C, D)
import days         # Look-ahead v2 slice 1 (2026-09-09) — the commit week by day
import derived      # Look-ahead v2 slice 2 (2026-09-09) — trips / vehicles / km / t·km on read
import lookahead    # Look-ahead v2 slices 3-6 — the page's read model, clashes, account, horizon
import export       # Look-ahead v2 slice 4 — XLSX + PDF of the commit week
import stockpiles    # Week 1 — stockpile capacity and typed consumption (Task D2)
import access        # 2026-09-02 — IPT access codes (Task F)
import gate          # 2026-09-14 — the /map/ password and the /help/ staff gate
import config        # 2.5b — the editable copy of factors.json; G2 — the tenant settings block
import tenant_package  # G2, 16 Sep — a tenant as one JSON document; the map overlay
import costing       # 10 Sep evening — target rates + fuel settings (config key 'costing'), BAF
import fuel          # 10 Sep evening — the EU Weekly Oil Bulletin diesel index, fetched server-side
import costlines     # 11 Sep — one read of every forecast line's volume, haul and cost figures (Dashboard, Forecasts)
import demo_request  # H9, 8 Oct — the landing page's demo-request form: store, email or show the access details
import users         # G3, 14 Oct 2026 — per-person logins, sessions, reset links, the audit trail
import carbon        # 10 Oct 2026 — the carbon planner: baseline vs alternatives, drivers ranked by tCO2e moved
import carbon_target  # 11 Oct 2026 — the programme's carbon target (config key 'carbon_target'), all-in tCO2e
import road_sections  # 12 Oct 2026 — shared road sections (public map review §2.2d): the index and the month read
import areas         # 12 Oct 2026 — movements and carbon per council (public map review §2.2b, D27)
import limits        # 13 Oct 2026 — lorry limits (weight / height / width) from OpenStreetMap and HERE
import bulletin      # 12 Oct 2026 — the monthly bulletin's server half: the map bar's month roll-up + the conditions of the month
import route_map_export  # 14 Oct 2026 — the route map export (backlog item 2): the map as filtered, as a PDF
import bulletin_doc  # 12 Oct 2026 (C4) — the bulletin as people read it: one view model, the HTML page and the PDF
import gate_arrivals  # 11 Oct 2026 — the staff Dashboard's "Gate arrivals" panel: lorries a day per gate, every team summed

ROOT = Path(__file__).resolve().parent.parent          # repo root
HERE = Path(__file__).resolve().parent                 # backend/

START_YEAR = 2026          # month_index 1 == Jan 2026
MONTH_COUNT = 60           # 5-year horizon

# One definition of the epoch, not two. stockpiles.py needs it for the public-map
# popup and cannot import main (circular), so it carries a default that this
# overwrites at import time — and test_week1.py asserts the two agree.
stockpiles.START_YEAR = START_YEAR
days.START_YEAR = START_YEAR        # Look-ahead v2 slice 1: the day layer reads the same origin
weeks.START_YEAR = START_YEAR       # 10 Sep: calendar weeks need the month's year to count them


# ------------------------------------------------------------------ startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # NOTE: forecast seeding is gone, and since G2 (16 Sep) so is every other seed of
    # project data — the product boots an EMPTY tenant and a tenant arrives as a package
    # (tenant_package.py). Only the generic disciplines and the factors row are seeded.
    try:
        db.init_network_db()
        db.init_taxonomy_db()
        db.init_zones_db()          # Phase 3. No seed — zones are drawn, never shipped.
        db.init_gates_db()          # Phase 5a. Table + the two gate columns on routes.
        # Week 1. forecast_weeks + stockpile_weeks, and the three capacity columns on
        # locations. Must sit HERE — after init_network_db(), which creates the table
        # those columns are ALTERed onto, and before init_tenant(), which rebuilds it.
        db.init_weeks_db()
        db.init_lookahead_db()      # Look-ahead v2 slices 3-5. ALTERs only; after weeks, before tenant.
        db.init_config_db()         # 2.5b. No ALTERs, so its position only needs to precede the seed.
        db.init_costing_db()        # 10 Sep evening. The GLOBAL fuel_index table (untenanted, by design).
        db.init_demo_requests_db()  # H9, 8 Oct. The GLOBAL demo_requests table (untenanted, by design).
        db.init_users_db()          # G3, 14 Oct. Logins, sessions, links, audit, attempts: account data, not package data.
        limits.init_db()            # 13 Oct. The GLOBAL road_limits table (untenanted, by design: public road facts).
        # Phase 4.5. Must sit exactly here: init_tenant() migrates a pre-4.5 database by
        # rebuilding each table, copying the columns the table actually has — several of
        # which the init_* calls above add by ALTER. Run it before them and those columns
        # are silently dropped; run it after the seeds below and the seeds write rows into
        # a table that has not got its tenant key yet.
        db.init_tenant()
        # Phase 5a. AFTER init_tenant(), because it inserts rows and every insert
        # filters on the tenant key the migration has just put in place. Idempotent:
        # a location that already has a gate row is skipped, so a restart cannot mint
        # a second 'Main gate'.
        try:
            gates.migrate_legacy_gates()
        except Exception as e:
            print("⚠️  Phase 5a: legacy gate migration failed:", e)
        # G2, 16 Sep: the product boots to an EMPTY tenant. No network, no teams, no
        # sections are seeded here — a tenant package is imported instead
        # (POST /api/admin/tenant/import). The backfills below are idempotent and
        # touch only rows that exist, so on an empty tenant they do nothing.
        network.backfill_location_roles()
        filled = network.backfill_supplies_receives().get("filled", 0)
        if filled:
            print(f"Backfilled supplies/receives on {filled} location(s) from the route network.")
        counts = taxonomy.seed_taxonomy()
        if any(counts.values()):
            print("Seeded taxonomy:", counts)
        # 2.5b: factors.json becomes the seed of the config row. From this boot on, the
        # ROW is what every payload, density and cycle time reads.
        if config.seed_from_file(conversions).get("seeded"):
            print("2.5b: config.factors seeded from backend/factors.json — the file is now the "
                  "seed, not the live copy. Edit on the Config page.")
        # Task F: lines written before `ipt` existed. Filled ONLY where the route names
        # exactly one team ("IPT5"); a shared route ("IPT3 / IPT6") tells us nothing
        # about which of the two a line belongs to, and those stay NULL for a planner
        # to set. Idempotent — touches only NULLs.
        back = network.backfill_forecast_ipt()
        if back.get("filled"):
            print(f"Task F: ipt filled on {back['filled']} line(s) from single-IPT routes; "
                  f"{back.get('left', 0)} left NULL (shared or unknown route IPT).")
    except Exception as e:
        print("Network seed skipped:", e)
    yield


app = FastAPI(title="Wayscope", lifespan=lifespan)
# G3 (14 Oct 2026): no other origin may call the API. Until today every origin was allowed
# with credentials, and Starlette answers such a request with the caller's own origin echoed
# back — harmless while the only credential was a header code no other site holds, NOT
# harmless once a session cookie signs people in. Every caller is same-origin: the app and
# the map fetch "/api", and the landing page's form is a plain form POST, which CORS does not
# touch. The middleware stays registered with nothing allowed, so a cross-origin request gets
# no CORS headers and the browser keeps the answer from the calling page.
app.add_middleware(
    CORSMiddleware, allow_origins=[], allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=[],
)


# ------------------------------------------------------------------ gate pages (2026-09-14)
# Served when the gate refuses. They are string constants rather than files under map/
# or frontend/help/ ON PURPOSE: anything inside those directories is itself behind the
# gate, so a password page living there could never be shown to the person who needs it.
# Wayscope theme (29 Sep 2026): ink background, white box, blue for the control, the
# stacked logo above the box. Orange appears only in the logo itself.
_GATE_CSS = """
  /* 11 Oct 2026 — the finalised theme (the staff app's shell): ink page, white box, warm neutrals,
     the orange action button with white text, 14 px labels above the inputs, an orange focus ring. */
  :root { color-scheme: light; }
  body { margin:0; min-height:100vh; display:flex; flex-direction:column; align-items:center;
         justify-content:center; gap:22px; background:#1F2024; color:#fff;
         font:15px/1.5 Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  .logo { width:min(60vw,150px); height:auto; display:block; }
  .box { width:min(92vw,380px); box-sizing:border-box; background:#fff; color:#1F2024; border-radius:10px;
         padding:28px 26px; box-shadow:0 10px 40px rgba(0,0,0,.45); }
  h1 { margin:0 0 4px; font-size:20px; font-weight:600; color:#1F2024; }
  p  { margin:0 0 20px; font-size:14px; color:#78716C; }
  label { display:block; font-size:14px; font-weight:500; color:#1F2024; margin-bottom:6px; }
  input { width:100%; box-sizing:border-box; padding:10px 12px; font:inherit; font-size:15px; color:#1F2024;
          background:#fff; border:1px solid #D6D3D1; border-radius:6px; }
  input:focus { outline:2px solid #C2410C; outline-offset:1px; border-color:#C2410C; }
  button { margin-top:16px; width:100%; padding:11px; font:inherit; font-size:15px; font-weight:600;
           color:#fff; background:#C2410C; border:0; border-radius:6px; cursor:pointer; }
  button:hover { background:#9A3412; }
  button:focus-visible { outline:2px solid #C2410C; outline-offset:2px; }
  .pw-wrap { position:relative; }
  .pw-wrap input { padding-right:46px; }
  .pw-eye { position:absolute; right:4px; top:50%; transform:translateY(-50%); width:38px; height:38px;
            margin:0; padding:0; display:grid; place-items:center; color:#78716C; background:none; border-radius:6px; }
  .pw-eye:hover { background:#F5F5F4; color:#1F2024; }
  .err { display:none; margin-top:12px; font-size:13px; color:#DC2626; }
  .foot { margin-top:18px; font-size:13px; color:#78716C; }
  a { color:#2563EB; }
  .demo-notice { max-width:92vw; box-sizing:border-box; padding:5px 12px; border-radius:999px;
                 background:#F1F5F9; color:#B91C1C; border:1px solid #DC2626; text-align:center;
                 font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; }
  /* 13 Oct 2026 (D45, Option A): the app's demo bar colours, with the red DEMO tag */
  .demo-notice::before { content:"DEMO"; content:"DEMO" / ""; display:inline-block; margin-right:8px; padding:0 6px;
                         border-radius:3px; background:#B91C1C; color:#FFFFFF; letter-spacing:.08em; }
"""
_GATE_HEAD = """<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#1F2024">"""
_GATE_LOGO = """<img class="logo" src="/brand/logo-stacked-on-dark.svg" alt="Wayscope" draggable="false">"""

_MAP_PASSWORD_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wayscope — map access</title>%s<style>%s</style>
<!--demo-notice-->
%s
<div class="box">
  <h1>Public map</h1>
  <p>This map is shared by password. Enter the one you were given.</p>
  <form id="f" autocomplete="off">
    <label for="p">Password</label>
    <div class="pw-wrap">
      <input id="p" name="p" type="password" autofocus>
      <button type="button" class="pw-eye" id="eye" aria-label="Show password" aria-pressed="false" title="Show password"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg></button>
    </div>
    <button type="submit">Open the map</button>
    <div class="err" id="e">That password was not recognised.</div>
  </form>
  <div class="foot">Staff: sign in to the app at <a href="/">the main page</a> and
  the map opens with it.</div>
</div>
<script>
// 11 Oct 2026: show / hide the password (the eye in the box)
var EYE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>', EYE_OFF = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-3.2 4.2"/><path d="M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
document.getElementById('eye').addEventListener('click', function () {
  var p = document.getElementById('p'), show = p.type === 'password';
  p.type = show ? 'text' : 'password';
  this.innerHTML = show ? EYE_OFF : EYE;
  this.setAttribute('aria-pressed', show ? 'true' : 'false');
  this.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  this.title = show ? 'Hide password' : 'Show password';
  p.focus();
});
document.getElementById('f').addEventListener('submit', async function (ev) {
  ev.preventDefault();
  var e = document.getElementById('e'); e.style.display = 'none';
  var r = await fetch('/api/map-auth', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: document.getElementById('p').value })
  });
  if (r.ok) { location.reload(); } else { e.style.display = 'block'; }
});
</script></html>""" % (_GATE_HEAD, _GATE_CSS, _GATE_LOGO)


def _map_password_page(embedded=False):
    """The password page with the tenant's demo notice above the logo, when it has one.

    11 Oct 2026: a visitor without the map password saw no "fictional demo scheme" anywhere,
    because the app's header badge hides while the embedded map is on screen (PR #20) and the
    map's own strip sits behind this page. A real tenant has no notice, so the slot is empty.

    11 Oct 2026 (the demo bar): inside the app (the iframe asks for /map/?embed=1) the app's demo
    bar above the iframe carries the notice, so it is not repeated here (the user: "not needed
    twice"). /map/ opened on its own has no bar above it and keeps the notice."""
    try:
        dn = config.tenant_settings(conversions).get("demo_notice")
    except Exception:
        dn = None
    note = '<div class="demo-notice">%s</div>' % _html_escape(dn) if (dn and not embedded) else ""
    return _MAP_PASSWORD_PAGE.replace("<!--demo-notice-->", note, 1)


def _embedded_request(request):
    """True when the request is the app's iframe asking for the map: the embed=1 flag the app's MAP_URL
    carries (map/index.html reads the same flag), and NOT a top-level page load. A browser sends
    Sec-Fetch-Dest: document for an address typed or followed in the tab, iframe for a frame; so
    /map/?embed=1 typed into the address bar keeps the notice, like the map's own EMBED check
    (the flag AND a frame). 11 Oct 2026 (the demo bar)."""
    return (request.query_params.get("embed") == "1"
            and (request.headers.get("sec-fetch-dest") or "").lower() != "document")

_HELP_SIGNIN_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wayscope — user guide</title>%s<style>%s</style>
%s
<div class="box">
  <h1>The user guide is for signed-in staff</h1>
  <p>It documents every staff screen, so it sits behind the same sign-in.</p>
  <button onclick="location.href='/'">Go to the app and sign in</button>
  <div class="foot">Once you are signed in, come back to <code>/help/</code> — or use
  User guide at the foot of the app's menu on the left.</div>
</div></html>""" % (_GATE_HEAD, _GATE_CSS, _GATE_LOGO)

# 12 Oct 2026 (C4): the monthly bulletin at /bulletin/ is staff-only like the guide (D10); its refusal
# says what it guards and where to come back to.
_BULLETIN_SIGNIN_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wayscope — monthly bulletin</title>%s<style>%s</style>
%s
<div class="box">
  <h1>The monthly bulletin is for signed-in staff</h1>
  <p>It is issued by the scheme's staff, so it sits behind the same sign-in.</p>
  <button onclick="location.href='/'">Go to the app and sign in</button>
  <div class="foot">Once you are signed in, open it from Monthly bulletin on the Dashboard, or come back
  to <code>/bulletin/</code>.</div>
</div></html>""" % (_GATE_HEAD, _GATE_CSS, _GATE_LOGO)

_MAP_UNCONFIGURED_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wayscope — map closed</title>%s<style>%s</style>
%s
<div class="box">
  <h1>The map is closed</h1>
  <p>No map password has been configured on this deployment, so the map cannot be opened
  to anyone without a staff sign-in. This is the safe state, not a fault.</p>
  <div class="foot">Set <code>MAP_PASSWORD</code> in the environment to open it. Staff can
  still see the map by signing in at <a href="/">the main page</a>.</div>
</div></html>""" % (_GATE_HEAD, _GATE_CSS, _GATE_LOGO)


# ------------------------------------------------------------------ access (Task F)
# The X-Access-Code header is resolved ONCE per request into a contextvar, the same
# shape the tenant uses, so no endpoint takes a code argument — each one asks
# access.current(). Registered only when the real FastAPI is present: the test
# harnesses stub the app class, run endpoint bodies directly, and set the contextvar
# themselves. That is the "HTTP layer is stubbed" caveat every test file carries, and
# it now covers this too — nothing here proves the header is actually read.
try:
    from fastapi import Request as _Request
except Exception:      # stubbed fastapi in the sandbox harnesses
    _Request = None

if _Request is not None and hasattr(app, "middleware"):
    from fastapi.responses import HTMLResponse as _HTML, JSONResponse as _JSON

    # 2026-09-14 — the gate for /map/ and /help/. The policy lives in gate.decide(),
    # which is pure and fully asserted in the sandbox; everything here is the wiring
    # that turns a decision into a response, and the wiring is what the harness cannot
    # run. Registered on the SAME middleware as the access contextvar so the gate can
    # see whether the X-Access-Code resolved.
    def _gate_refusal(decision, path, embedded=False):
        doc = gate.is_document(path)
        if decision == gate.NEED_MAP_PASSWORD:
            return _HTML(_map_password_page(embedded), status_code=401) if doc else _JSON(
                {"detail": "the map is password protected"}, status_code=401)
        if decision == gate.NEED_STAFF:
            if gate.scope_for(path) == "bulletin":
                return _HTML(_BULLETIN_SIGNIN_PAGE, status_code=401) if doc else _JSON(
                    {"detail": "sign in to the app to read the bulletin"}, status_code=401)
            return _HTML(_HELP_SIGNIN_PAGE, status_code=401) if doc else _JSON(
                {"detail": "sign in to the app to read the guide"}, status_code=401)
        # UNCONFIGURED — nobody set MAP_PASSWORD. Closed, and says why. Staff are
        # unaffected: a valid code or a staff cookie never reaches this branch.
        return _HTML(_MAP_UNCONFIGURED_PAGE, status_code=503) if doc else _JSON(
            {"detail": "map access is not configured"}, status_code=503)

    @app.middleware("http")
    async def _access_middleware(request, call_next):
        # G3 (14 Oct 2026): the session cookie resolves too (access.resolve_request), so a
        # signed-in person passes the gate, the line filters and /api/meta's staff shape
        # exactly as a code did.
        token = access.set_current(request.headers.get(access.HEADER),
                                   request.cookies.get(users.SESSION_COOKIE))
        try:
            path = request.url.path
            decision = gate.decide(
                path,
                has_valid_code=bool(access.current()),
                cookie=request.cookies.get(gate.COOKIE),
            )
            if decision != gate.ALLOW:
                return _gate_refusal(decision, path, embedded=_embedded_request(request))

            method = request.method.upper()
            write = method not in ("GET", "HEAD", "OPTIONS") and path.startswith("/api/")
            # G3 (plan §4.6): a write that a session COOKIE authenticates must carry the app's own
            # header. A form on another site cannot add a header, and a script on another site
            # cannot send one without a CORS preflight, which now fails. A code (a header) and the
            # admin token (a query value) are not sent by the browser on its own, so they need
            # nothing more. The new /api/auth/* calls always need it (no signing a person in or
            # out from another page).
            acc_now = access.current()
            if write and request.headers.get(GUARD_HEADER) != "1" and (
                    (acc_now and acc_now.get("via") == "login") or path.startswith("/api/auth/")):
                return _JSON({"detail": "refused: this request did not come from the Wayscope app"},
                             status_code=403)

            body = None
            if write and _audited(path):
                try:
                    body = await request.body()
                except Exception:
                    body = None

            response = await call_next(request)

            # G3 (D55): every write that worked, with who did it and what was sent (secrets removed).
            # One place, so a new endpoint cannot forget it.
            if write and _audited(path) and 200 <= getattr(response, "status_code", 0) < 300:
                _audit_write(request, path, method, response.status_code, body)

            # The cookie is set HERE rather than in the endpoint so that auth() and
            # map_auth() stay plain functions the harness can call directly. A staff
            # sign-in opens the map as well, which is what keeps the iframe on the
            # staff dashboard working without a second credential.
            if getattr(response, "status_code", None) == 200:
                if path == "/api/auth":
                    response.set_cookie(**gate.cookie_kwargs(gate.LEVEL_STAFF))
                elif path == "/api/map-auth":
                    response.set_cookie(**gate.cookie_kwargs(gate.LEVEL_MAP))
            return response
        finally:
            access.reset_current(token)


#: G3 (plan §4.6): the header the app's fetch wrapper adds to every API call. A session-cookie
#: write without it is refused by the middleware.
GUARD_HEADER = "X-Wayscope"

#: POSTs that change nothing (they compute an answer or a file from the body), and the paths that
#: write their own audit rows (sign-in, the lead form, page opens). Everything else that writes is
#: logged by the middleware.
AUDIT_SKIP = ("/api/costing/preview", "/api/carbon/scenario", "/api/carbon/summary.pdf",
              "/api/public/demo-request", "/api/map-auth", "/api/gate-signout", "/api/auth",
              "/api/activity")
AUDIT_SKIP_PREFIXES = ("/api/auth/",)


def _audited(path):
    return path not in AUDIT_SKIP and not path.startswith(AUDIT_SKIP_PREFIXES)


def _client_ip(request):
    try:
        return demo_request.client_ip(request.headers.get("x-forwarded-for"),
                                      request.client.host if request.client else "")
    except Exception:
        return ""


def _audit_write(request, path, method, status, body):
    """One audit row for a write that worked. The query string and the JSON body go in the
    detail with every secret removed (users.scrub); a body that is not JSON is recorded by its
    size only. Never raises."""
    try:
        detail = {}
        q = dict(request.query_params)
        if q:
            detail["query"] = q
        if body:
            ctype = (request.headers.get("content-type") or "").lower()
            if "json" in ctype and len(body) <= 1_000_000:
                try:
                    detail["body"] = json.loads(body.decode("utf-8"))
                except Exception:
                    detail["body_bytes"] = len(body)
            else:
                detail["body_bytes"] = len(body)
        acc = access.current()
        # the token counts only where a LOGIN did not already pass _check_admin
        token_used = bool(q.get("token")) and not (acc and acc.get("via") == "login")
        users.audit("write", acc=acc, method=method, path=path, status=status,
                    detail=detail or None, ip=_client_ip(request), token_used=token_used)
    except Exception as e:  # noqa: BLE001
        print(f"audit: {method} {path} not recorded: {e.__class__.__name__}: {str(e)[:200]}")


def _by(supplied=None):
    """
    G3 (14 Oct 2026): the name every "by" column records. A signed-in person is recorded by the
    name on their login, whatever the browser sent; on a shared code the typed name is all there
    is, as before (and the audit row says it came from a code).
    """
    acc = access.current()
    if acc and acc.get("via") == "login":
        return acc.get("name")
    return supplied


def _require_access():
    """Any valid code or a signed-in login. 401 otherwise."""
    acc = access.current()
    if not acc:
        raise HTTPException(401, "sign in — a valid access code is required")
    return acc


def _require_approver():
    acc = _require_access()
    if not access.can_approve(acc):
        raise HTTPException(403, f"{acc['label']} cannot approve or reject")
    return acc


def _require_line(route_id, month_index, discipline, section_id):
    """The line must exist AND be visible to this code. 404 either way — an IPT code
    must not learn that another IPT's line exists."""
    acc = _require_access()
    row = {"ipt": access.line_ipt(route_id, month_index, discipline, section_id)}
    if not access.line_visible(row, acc):
        raise HTTPException(404, "no such forecast line")
    return acc


class AuthIn(BaseModel):
    code: str


@app.post("/api/auth")
def auth(body: AuthIn):
    """
    Turn a code into a role. The frontend keeps the code and sends it on every
    request; this only tells it what it got. Nothing is stored server-side.
    """
    acc = access.resolve(body.code)
    if not acc:
        raise HTTPException(401, "unknown access code")
    acc["via"] = "code"
    # G3 (D49): a sign-in with a shared code is recorded, as the code — there is nobody else to name
    users.audit("signin-code", actor=users.actor_of(acc))
    return access.describe(acc)


class MapAuthIn(BaseModel):
    password: str


@app.post("/api/map-auth")
def map_auth(body: MapAuthIn):
    """
    The shared password for the public map. On 200 the middleware attaches the `map`
    cookie; this returns nothing but the fact that it worked.

    Deliberately says the same thing on a wrong password as on an unset one — an
    unconfigured map is not a map whose password is empty.
    """
    if not gate.password_ok(body.password):
        raise HTTPException(401, "wrong password")
    return {"ok": True, "opens": "/map/"}


@app.post("/api/gate-signout")
def gate_signout(request: Request = None, keep: Optional[str] = None):
    """
    Drop the gate cookie — for testing the gate, and for a shared machine.

    12 Oct 2026 (the review and fix pass): `keep=map` is what the app's Sign out sends. A
    STAFF cookie is replaced by a MAP cookie that expires no later than the staff one did
    (gate.downgrade_kwargs), so the public map still opens on that machine and the staff
    surface (the full /api/meta, the network reads, /help/) does not. Any other cookie is
    left as it is under keep=map; without `keep` the cookie is dropped, as before.
    """
    from fastapi.responses import JSONResponse as _J
    r = _J({"ok": True})
    if keep == "map":
        cookies = getattr(request, "cookies", None) or {}
        kw = gate.downgrade_kwargs(cookies.get(gate.COOKIE))
        if kw:
            r.set_cookie(**kw)
        return r
    r.delete_cookie(gate.COOKIE, path="/")
    return r


# ------------------------------------------------------------------ G3: per-person logins (14 Oct 2026)
# The plan and the decisions D46–D57: notes\g3-plan.md. The logic is in users.py, where the
# stubbed harness (test_users.py) drives every branch; these are the HTTP shells, which
# http_smoke.py drives through the real app. Every /api/auth/* POST needs the app's header
# (the middleware refuses one without it).
class SignInIn(BaseModel):
    email: str
    password: str
    remember: bool = False


class EmailIn(BaseModel):
    email: str


class TokenIn(BaseModel):
    token: str


class ResetIn(BaseModel):
    token: str
    password: str
    remember: bool = False


class PasswordIn(BaseModel):
    current: str
    new: str


class ActivityIn(BaseModel):
    page: str


#: what every refusal of a link says — never which of used, expired or unknown it was
LINK_REFUSED = "This link has expired or has already been used. Ask for a new one."


def _ua(request):
    return ((getattr(request, "headers", None) or {}).get("user-agent") or "")[:120]


def _session_answer(user, request, remember=False, payload_extra=None):
    """A JSONResponse carrying the new session cookie and what the person can do (access.describe)."""
    from fastapi.responses import JSONResponse as _J
    raw, ttl = users.create_session(user["id"], remember=remember, ip=_client_ip(request), ua=_ua(request))
    acc, _u = users.resolve_session(raw)
    payload = access.describe(acc)
    if payload_extra:
        payload.update(payload_extra)
    r = _J(payload)
    r.set_cookie(**users.cookie_kwargs(raw, ttl))
    return r


@app.post("/api/auth/signin")
def auth_signin(body: SignInIn, request: Request = None):
    """Email and password → a session cookie. One refusal message for every reason (users.sign_in);
    429 after five failures for an address in 15 minutes, or 30 tries from one address."""
    user, err, status = users.sign_in(body.email, body.password, ip=_client_ip(request))
    if not user:
        raise HTTPException(status, err)
    return _session_answer(user, request, remember=bool(body.remember))


@app.get("/api/auth/me")
def auth_me():
    """Who this browser is signed in as, and whether the shared codes are still on (D49) — the
    sign-in screen offers the code form only while they work."""
    acc = access.current()
    return {"signed_in": bool(acc), "access": access.describe(acc) if acc else None,
            "codes": users.codes_enabled()}


@app.post("/api/auth/signout")
def auth_signout(request: Request = None):
    """
    End this browser's session (the row is deleted, so the cookie is dead everywhere it was
    copied) and drop the cookie. The public map stays open on this machine until the session
    would have ended, never longer than the map password's month — the rule gate_signout(keep=map)
    applies to a code's staff cookie, which is downgraded here too.
    """
    from fastapi.responses import JSONResponse as _J
    cookies = getattr(request, "cookies", None) or {}
    raw = cookies.get(users.SESSION_COOKIE)
    r = _J({"ok": True})
    map_kw = gate.downgrade_kwargs(cookies.get(gate.COOKIE))
    if raw:
        acc = access.current()
        exp = users.session_expiry(raw)
        users.end_session(raw)
        if acc and acc.get("via") == "login":
            users.audit_event("signout", user=users.get_user(acc["user_id"]), ip=_client_ip(request))
        if exp and not map_kw:
            ttl = min(max(1, int((exp - users._now()).total_seconds())), gate.MAP_TTL_S)
            value = gate.sign(gate.LEVEL_MAP, ttl_s=ttl)
            if value:
                map_kw = {"key": gate.COOKIE, "value": value, "max_age": ttl, "path": "/", "httponly": True,
                          "samesite": "lax", "secure": True}
    r.delete_cookie(users.SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    if map_kw:
        r.set_cookie(**map_kw)
    return r


def _send_reset(email, ip):
    """The background half of /api/auth/forgot: only an enabled, unexpired STAFF login with an
    address gets a link. A demo login gets a fresh personal link instead (they have no password)."""
    user = users.find_by_email(email)
    if not users.usable(user):
        return "nobody"
    if user.get("kind") == "demo":
        raw = users.issue_token(user["id"], "demo", expires_at=user["expires_at"])
        c = {"status": "renewed", "link": users.link("demo", raw), "expires_on": users.nice_date(user["expires_at"]),
             "sign_in": users.app_url() + "/"}
        s = demo_request.smtp_settings()
        if s is None:
            return "unsent"
        try:
            demo_request.send(demo_request.build_message(user["email"], user["name"], c, s), s)
        except Exception as e:  # noqa: BLE001
            print(f"forgot: demo link email FAILED {e.__class__.__name__}")
            return "failed"
        users.audit_event("reset-asked", user=user, ip=ip, detail={"sent": "demo link"})
        return "sent"
    purpose = "reset" if user.get("password_hash") else "invite"
    raw = users.issue_token(user["id"], purpose)
    sent = users.send_account_email(purpose, user, users.link(purpose, raw))
    users.audit_event("reset-asked", user=user, ip=ip, detail={"email": sent})
    return sent


@app.post("/api/auth/forgot")
def auth_forgot(body: EmailIn, request: Request = None):
    """
    Always the same answer, whether or not the address has a login, and the email is sent in the
    background so the answer takes the same time either way. 429 after three requests for one
    address in an hour, or ten from one IP.
    """
    from fastapi.responses import JSONResponse as _J
    from starlette.background import BackgroundTask as _BT
    ip = _client_ip(request)
    email = users.norm_email(body.email)
    if users.reset_blocked(email, ip):
        raise HTTPException(429, "Too many requests. Try again in an hour.")
    users.note_reset_request(email, ip)
    answer = {"ok": True, "message": "If that address has a Wayscope login, we have sent it a link. "
                                     "It works once and for 60 minutes."}
    if not users.email_ok(email):
        return answer
    return _J(answer, background=_BT(_send_reset, email, ip))


@app.post("/api/auth/check")
def auth_check(body: TokenIn):
    """What a set-password or reset link is for, without using it up: the screen greets the person
    by name. Refused links all read the same."""
    t, user = users.peek_token(body.token, ("invite", "reset"))
    if not t:
        raise HTTPException(410, LINK_REFUSED)
    return {"purpose": t["purpose"], "name": user["name"], "email": user["email"]}


@app.post("/api/auth/reset")
def auth_reset(body: ResetIn, request: Request = None):
    """Set a password from an invite or reset link and sign in. The password is checked BEFORE the
    link is used, so a too-short password does not burn the link. Every other session of the person
    ends (users.set_password)."""
    t, user = users.peek_token(body.token, ("invite", "reset"))
    if not t:
        raise HTTPException(410, LINK_REFUSED)
    problem = users.password_problem(body.password, user["email"])
    if problem:
        raise HTTPException(400, problem)
    t, user = users.use_token(body.token, ("invite", "reset"))
    if not t:
        raise HTTPException(410, LINK_REFUSED)
    ok_, err = users.set_password(user["id"], body.password)
    if not ok_:
        raise HTTPException(400, err)
    users.audit_event("password-set", user=user, ip=_client_ip(request), detail={"via": t["purpose"]})
    return _session_answer(users.get_user(user["id"]), request, remember=bool(body.remember))


@app.post("/api/auth/link")
def auth_link(body: TokenIn, request: Request = None):
    """HU14 / D50: a lead's personal link signs them in. It stays live until their login expires
    (each use is counted); the session never outlives the login."""
    t, user = users.use_token(body.token, ("demo",))
    if not t:
        raise HTTPException(410, "This demo link has expired. Ask for the demo again at wayscope.co.uk "
                                 "and we will send you a new one.")
    users.audit_event("demo-link", user=user, ip=_client_ip(request))
    return _session_answer(user, request, remember=True)


@app.post("/api/auth/password")
def auth_password(body: PasswordIn, request: Request = None):
    """Change your own password. A wrong current password counts towards the sign-in limit. Every
    other browser is signed out; this one gets a fresh session."""
    acc = access.current()
    if not acc or acc.get("via") != "login":
        raise HTTPException(401, "Sign in with your email first.")
    user = users.get_user(acc["user_id"])
    ip = _client_ip(request)
    if users.signin_blocked(user["email"], ip):
        raise HTTPException(429, users.SIGNIN_LOCKED)
    if not users.verify_password(body.current, user.get("password_hash")):
        users.record_attempt("signin-email", users._attempt_key("signin-email", user["email"]), False)
        raise HTTPException(400, "Your current password isn't right.")
    ok_, err = users.set_password(user["id"], body.new)
    if not ok_:
        raise HTTPException(400, err)
    users.audit_event("password-changed", user=user, ip=ip)
    return _session_answer(users.get_user(user["id"]), request)


@app.post("/api/activity")
def activity(body: ActivityIn):
    """D51: a demo login's page open (HU14, the leads CSV's `pages`). Anyone else: nothing recorded."""
    return {"ok": True, "recorded": users.record_page(access.current(), body.page)}


# ---- Config → Users (admins: an admin login, or the admin token for the first admin, D47/D57)
class UserIn(BaseModel):
    email: str
    name: str
    role: str
    team: Optional[str] = None


class UserPatch(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    team: Optional[str] = None
    disabled: Optional[bool] = None
    extend_days: Optional[int] = None


def _admin_actor():
    acc = access.current()
    if acc and acc.get("via") == "login":
        return users.actor_of(acc)
    return users.actor_of(None, token_used=True)


def _me_id():
    acc = access.current()
    return acc.get("user_id") if acc and acc.get("via") == "login" else None


def _invite_or_reset(user):
    """Send a staff login its link: an invite (no password yet) or a reset. When there is no sender,
    or the send fails, the link comes back so the admin can pass it on — nobody is locked out by a
    mail problem (plan §6)."""
    purpose = "reset" if user.get("password_hash") else "invite"
    raw = users.issue_token(user["id"], purpose)
    url = users.link(purpose, raw)
    sent = users.send_account_email(purpose, user, url)
    out = {"email": sent, "purpose": purpose}
    if sent != "sent":
        out["link"] = url
    return out


def _send_demo_link(user):
    """A demo login's personal link, emailed (or returned when it cannot be)."""
    raw = users.issue_token(user["id"], "demo", expires_at=user["expires_at"])
    url = users.link("demo", raw)
    c = {"status": "renewed", "link": url, "expires_on": users.nice_date(user["expires_at"]),
         "sign_in": users.app_url() + "/"}
    s = demo_request.smtp_settings()
    sent = "unsent"
    if s is not None:
        try:
            demo_request.send(demo_request.build_message(user["email"], user["name"], c, s), s)
            sent = "sent"
        except Exception as e:  # noqa: BLE001
            sent = "failed: " + e.__class__.__name__
    out = {"email": sent, "purpose": "demo"}
    if sent != "sent":
        out["link"] = url
    return out


def _teams():
    return [{"id": i, "label": users.team_label(i)} for i in access.tenant_team_ids()]


@app.get("/api/admin/users")
def admin_users(token: Optional[str] = None):
    """Every login of this tenant (no password hashes), the teams by NAME, whether the shared codes
    are still on and whether email can be sent."""
    _check_admin(token)
    return {"users": [users.public(u) for u in users.list_users()], "teams": _teams(),
            "codes": users.codes_enabled(), "mail": users.mail_settings() is not None, "me": _me_id()}


@app.post("/api/admin/users")
def admin_user_add(body: UserIn, token: Optional[str] = None):
    """Add a staff login and send its invite (a set-your-password link, 72 hours, single use). An address
    that holds a lead's DEMO login is turned into a staff login (users.promote_demo): a lead who becomes
    a customer keeps their history in the activity log."""
    _check_admin(token)
    label = _admin_actor()[2]
    existing = users.find_by_email(body.email)
    if existing and existing.get("kind") == "demo":
        user, err = users.promote_demo(existing["id"], body.name, body.role, body.team)
        converted = True
    else:
        user, err = users.create_user(body.email, body.name, body.role, body.team, created_by=label)
        converted = False
    if err:
        raise HTTPException(400, err)
    return {"user": users.public(user), "converted": converted, **_invite_or_reset(user)}


@app.patch("/api/admin/users/{user_id}")
def admin_user_change(user_id: str, body: UserPatch, token: Optional[str] = None):
    """Change a login's name, team or role, disable or enable it, or give a demo login more days."""
    _check_admin(token)
    fields = {k: getattr(body, k) for k in ("name", "role", "team", "disabled") if getattr(body, k) is not None}
    if body.role is not None and body.role != "team":
        fields["team"] = None
    if body.extend_days is not None:
        u = users.get_user(user_id)
        if not u or u.get("kind") != "demo":
            raise HTTPException(400, "Only a demo login has an end date.")
        days_ = max(1, min(int(body.extend_days), 90))
        base = max(users._now(), users._parse(u.get("expires_at")) or users._now())
        fields["expires_at"] = users._later(days_ * 86400, base)
    user, err = users.update_user(user_id, fields, by_user_id=_me_id())
    if err:
        raise HTTPException(404 if err == "No such login." else 400, err)
    return {"user": users.public(user)}


@app.post("/api/admin/users/{user_id}/reset")
def admin_user_reset(user_id: str, token: Optional[str] = None):
    """Send a staff login a reset (or its invite again), or a demo login a fresh personal link."""
    _check_admin(token)
    user = users.get_user(user_id)
    if not user:
        raise HTTPException(404, "No such login.")
    if not users.usable(user):
        raise HTTPException(400, "This login is disabled or has expired. Enable or extend it first.")
    return _send_demo_link(user) if user.get("kind") == "demo" else _invite_or_reset(user)


@app.get("/api/admin/leads")
def admin_leads(token: Optional[str] = None):
    """The demo requests with each lead's login (HU14), for the Users page."""
    _check_admin(token)
    return {"leads": demo_request.leads()}


@app.post("/api/admin/leads/{request_id}/login")
def admin_lead_login(request_id: str, token: Optional[str] = None):
    """D56: give a lead who asked before 14 Oct (and so got the shared code) a personal login, and
    email its link. Pressed by an admin, one lead at a time — never a bulk send."""
    _check_admin(token)
    row = demo_request.get(request_id)
    if not row:
        raise HTTPException(404, "No such demo request.")
    got = users.demo_login(row["email"], row["name"], request_id)
    if got["status"] in ("staff", "disabled", "error"):
        raise HTTPException(400, {"staff": "That address already has a staff login.",
                                  "disabled": "This lead's login is disabled. Enable it on the Users list first.",
                                  "error": got.get("error") or "Could not make the login."}[got["status"]])
    return {"status": got["status"], **_send_demo_link(got["user"]), "user": users.public(got["user"])}


@app.get("/api/admin/audit")
def admin_audit(token: Optional[str] = None, user: Optional[str] = None, kind: Optional[str] = None,
                since: Optional[str] = None, limit: int = 500):
    """The audit trail, newest first: every write, every sign-in event, demo page opens."""
    _check_admin(token)
    return {"rows": users.audit_rows(actor_id=user, kind=kind, since=since, limit=limit)}


@app.get("/api/admin/audit.csv")
def admin_audit_csv(token: Optional[str] = None, user: Optional[str] = None, kind: Optional[str] = None,
                    since: Optional[str] = None):
    _check_admin(token)
    return Response(content=users.audit_csv(actor_id=user, kind=kind, since=since), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="wayscope-activity.csv"',
                             "Cache-Control": "no-store"})


# ------------------------------------------------------------------ schemas
class Cell(BaseModel):
    month_index: int                # 1..60
    quantity: float


class MatrixRow(BaseModel):
    """
    One forecast LINE: a route, a discipline, a section, one material, ONE vehicle.

    vehicle_type_2 and split_pct are gone. A load split across two vehicles is now two
    lines, which the widened key makes storable and which keeps each line's cycle time
    honest -- an Artic Flatbed turns round in 45 minutes against a Tipper's 24, and
    blending them into one payload figure hid that.

    discipline and section_id join the UNIQUE key, so they are never None on the way in:
    '' is the unassigned sentinel. A NULL here would leave the row unconstrained and
    ON CONFLICT would silently stop firing.

    Phase 4.5 widened that UNIQUE key again, to
    (tenant_id, route_id, month_index, discipline, section_id). The same failure mode
    applies to the new column: the ON CONFLICT target in save_matrix_row() must name
    tenant_id too, or it no longer matches any constraint, the upsert stops firing, and
    re-saving a matrix row inserts a duplicate instead of updating the row already there.
    """
    route_id: str
    discipline: str = ""                       # '' = unassigned
    section_id: str = ""                       # '' = unassigned
    material_type: str                         # category, e.g. "Small aggregate"
    material_description: Optional[str] = None # free-text detail
    vehicle_type: str
    submitted_by: Optional[str] = None         # lightweight submitter identity
    unit: str                                  # 'm3' | 't' | 'vehicles'
    cells: List[Cell]
    status: str = "Pending"
    # Task F: which IPT this line belongs to. Forced to the caller's IPT for an IPT
    # code; required from a planner; see access.ipt_for_save().
    ipt: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str                     # 'Approved' | 'Rejected' | 'Pending'
    reject_reason: Optional[str] = None


# ------------------------------------------------------------------ helpers
# --- _load_routes() removed in Phase 2 ---
# It read seed_data/routes.json: 69 legacy routes with no distance_km key on any row, so
# /api/meta handed the UI routes with no distance and the dashboard's km, truck-km, CO2
# and intensity all read zero. Routes now come from the live network via
# network.meta_routes(). Nothing else in the codebase reads that file.


def _material_list(factors):
    return conversions.material_names(factors)


def _vehicle_list(factors):
    return conversions.vehicle_names(factors)


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health():
    return {"ok": True, "backend": "postgres" if db.IS_PG else "sqlite"}


def _staff_request(request=None):
    """
    Is this caller staff? True on a valid X-Access-Code (the middleware resolved it into
    access.current()) or a STAFF gate cookie (the app's iframe and a signed-in tab send the
    cookie but no header). The MAP cookie is not staff. Pure read: no I/O.
    """
    if access.current():
        return True
    cookies = getattr(request, "cookies", None) or {}
    try:
        return gate.verify(cookies.get(gate.COOKIE)) == gate.LEVEL_STAFF
    except Exception:
        return False


@app.get("/api/meta")
def meta(request: Request = None):
    """
    Everything the UI needs to build its dropdowns — kept in sync with factors.json.

    12 Oct 2026 (map review D31) — TWO SHAPES, one path, still ungated (test_gate pins that:
    the sign-in screen and the public map read this before anyone has a credential):

        public   no valid code and no staff cookie: units, materials, vehicles and their
                 labels, the tenant's words, the months, the flat factors and the seasonal
                 windows — what the sign-in screen and the public map read. `routes`, `ipts`
                 and `work_sections` are EMPTY LISTS: the tenant's network, its team names
                 and its section names are not for a visitor who has not signed in.
        staff    a valid X-Access-Code or a staff cookie: unchanged — `routes`
                 (network.meta_routes) feeds the submission matrix, `ipts` the team pickers.

    `scope` says which shape this is, so a client that fetched before signing in knows to
    fetch again (frontend/index.html does, in App). Keys are the same in both shapes.
    """
    staff = _staff_request(request)
    factors = conversions.load_factors()
    strip = lambda d: {k: v for k, v in d.items() if not k.startswith("_")}
    return {
        "scope": "staff" if staff else "public",
        "units": conversions.UNITS,
        "materials": conversions.material_names(factors),
        # every vehicle in the live document, unchanged and in its own order: baked
        # geometry is keyed on vehicle_profile and every saved line names a vehicle, so a
        # list that dropped one would strand those routes and lines.
        "vehicles": conversions.vehicle_names(factors),
        # ...and which of them to lead with (the country's lead list, else the document's
        # planning vehicles; never empty while a vehicle is usable — 11 Oct 2026). A NAME
        # LIST, not a re-ordering of `vehicles` — the map, the dashboard and every saved
        # forecast index into `vehicles` and `factors.vehicle_payload_t` by name, so the
        # full set has to stay complete and in its existing order.
        "planning_vehicles": conversions.planning_vehicle_names(factors),
        # H1 (29 Sep 2026): the names the pickers do NOT offer this tenant (its country's
        # `vehicle_sets[..].hide` — Rigid 7.5t for GB). Still in `vehicles`.
        "hidden_vehicles": conversions.hidden_vehicle_names(factors),
        # 2026-09-02: the vehicle-name labels. Labels only — vehicle_type on a forecast
        # line stays the canonical key. `langs` (11 Oct 2026) is the languages offered
        # to this tenant: English, plus any other label language a vehicle it is offered
        # still carries. Every offered slot is filled, a missing one with the key itself,
        # and `fallbacks` says which.
        "vehicle_labels": conversions.vehicle_labels(factors),
        # rich taxonomy for the new submission matrix (Commit 2)
        "material_categories": strip(factors.get("material_categories", {})),
        "vehicle_details": strip(factors.get("vehicles", {})),
        # live network, not the retired legacy file — carries real distances. Staff only
        # (D31): the public shape carries an empty list.
        "routes": network.meta_routes() if staff else [],
        # Phase 2 taxonomy for the discipline / section pickers.
        # work_sections is empty until the tenant's package or admin supplies rows;
        # the UI must cope with an empty list rather than assume rows exist. The
        # disciplines are the generic seed (Earthworks, Drainage…) and stay in both shapes;
        # the sections name the scheme's geography and the teams its contractors — staff.
        "disciplines": taxonomy.list_disciplines(),
        "work_sections": taxonomy.list_work_sections(in_scope_only=True) if staff else [],
        "ipts": taxonomy.list_ipts() if staff else [],
        # G2: the tenant's own words and units — name, team_label, currency (+ symbol),
        # country, and which country-specific providers that switches on. Read BEFORE
        # sign-in by the app, so the sign-in screen already carries the tenant's name.
        "tenant": config.tenant_settings(conversions),
        "months": {
            "start_year": START_YEAR,
            "count": MONTH_COUNT,
            "years": [START_YEAR + i for i in range(MONTH_COUNT // 12)],
        },
        # flat maps kept for the map + dashboard, derived from the taxonomy
        "factors": conversions.flat_factors(factors),
        "seasonal_restrictions": factors.get("seasonal_restrictions", []),
        "mapbox_token": config.mapbox_token(),
    }


@app.get("/api/convert")
def convert(quantity: float, from_unit: str, to_unit: str,
            material: str = "", vehicle: str = ""):
    try:
        val = conversions.convert(quantity, from_unit, to_unit, material, vehicle)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"value": conversions.round_for_unit(val, to_unit), "unit": to_unit}


# ------------------------------------------------------------------ forecasts (staff)
@app.get("/api/forecasts")
def list_forecasts(submitted_by: Optional[str] = None, route_id: Optional[str] = None):
    """
    Forecast rows, optionally scoped.

    route_id was added because the submission matrix reloads its cells whenever the
    route, year, discipline OR section changes, and it was pulling the entire forecasts
    table each time to find twelve of them. Four times the reload frequency on a
    whole-table read is not a shape that ages well.
    """
    clauses, params = [], []
    if submitted_by:
        clauses.append("submitted_by = ?"); params.append(submitted_by)
    if route_id:
        clauses.append("route_id = ?"); params.append(route_id)
    # tenant_id is written into the literal rather than pushed through `clauses`, so the
    # filter is in the SQL text on every branch (there is no longer a no-WHERE branch) and
    # its ? is always first — which is why db.current_tenant() leads the params tuple.
    where = "".join(" AND " + c for c in clauses)
    acc = _require_access()
    return access.filter_lines(db.query(
        f"SELECT * FROM forecasts WHERE tenant_id = ?{where} ORDER BY route_id, month_index",
        tuple([db.current_tenant()] + params)), acc)


@app.delete("/api/forecasts/{route_id}")
def withdraw_route(route_id: str, submitted_by: Optional[str] = None,
                   from_: Optional[int] = Query(None, alias="from"),
                   to: Optional[int] = None,
                   discipline: Optional[str] = None,
                   section_id: Optional[str] = None):
    """
    Withdraw a forecast, optionally scoped to a month range, a submitter, and a line.

    Pass discipline and section_id to withdraw ONE line. Without them this deletes every
    line on the route in range -- which, now that a route can carry several disciplines,
    means withdrawing a substructure forecast would take a superstructure one with it.
    The My-submissions view sends the line keys.
    """
    clauses, params = ["route_id = ?"], [route_id]
    # Task F: an IPT code can only withdraw its own lines. Added as a predicate rather
    # than checked afterwards, so the DELETE itself cannot reach another IPT's rows.
    acc = _require_access()
    if access.ipt_scope(acc):
        clauses.append("ipt = ?"); params.append(access.ipt_scope(acc))
    if submitted_by:
        clauses.append("submitted_by = ?"); params.append(submitted_by)
    if from_ is not None and to is not None:
        clauses.append("month_index BETWEEN ? AND ?"); params += [min(from_, to), max(from_, to)]
    if discipline is not None:
        clauses.append("discipline = ?"); params.append(discipline or "")
    if section_id is not None:
        clauses.append("section_id = ?"); params.append(section_id or "")
    where = " AND ".join(clauses)
    # tenant_id leads the literal WHERE on both statements, so db.current_tenant() leads
    # the params tuple ahead of everything `clauses` accumulated.
    n = db.query(f"SELECT COUNT(*) AS n FROM forecasts WHERE tenant_id = ? AND {where}",
                 tuple([db.current_tenant()] + params))[0]["n"]
    db.execute(f"DELETE FROM forecasts WHERE tenant_id = ? AND {where}",
               tuple([db.current_tenant()] + params))
    return {"status": "success", "route_id": route_id, "deleted": n,
            "scoped_to_line": discipline is not None or section_id is not None}


@app.get("/api/forecasts/summary")
def forecasts_summary():
    """One row per route: status, span, and window total in vehicles — for the ledger/approvals view."""
    rows = access.filter_lines(
        db.query("SELECT * FROM forecasts WHERE tenant_id = ?", (db.current_tenant(),)),
        _require_access())
    factors = conversions.load_factors()
    by_line = {}
    for r in rows:
        # grouped per LINE, not per route. Grouping on route_id alone would merge a
        # substructure line and a superstructure line on the same route into one ledger
        # row, silently summing two disciplines' traffic under one material and vehicle.
        key = (r["route_id"], r.get("discipline") or "", r.get("section_id") or "")
        g = by_line.setdefault(key, {
            "route_id": r["route_id"],
            "discipline": r.get("discipline") or "",
            "section_id": r.get("section_id") or "",
            "months": [], "statuses": set(),
            "unit": r["unit"], "material_type": r["material_type"],
            "vehicle_type": r["vehicle_type"], "submitted_by": r.get("submitted_by"),
            "ipt": r.get("ipt"),
            # the rejection reason was being written and then never read by anything,
            # so a submitter saw "Rejected" and no explanation
            "reject_reason": None,
            "total_vehicles": 0.0,
        })
        g["months"].append(r["month_index"])
        g["statuses"].add(r["status"])
        if r.get("reject_reason") and not g["reject_reason"]:
            g["reject_reason"] = r["reject_reason"]
        g["total_vehicles"] += conversions.convert_row(r, "vehicles", factors)

    out = []
    for g in by_line.values():
        statuses = g.pop("statuses")
        g["status"] = next(iter(statuses)) if len(statuses) == 1 else "Mixed"
        months = sorted(g["months"])
        g["span"] = f"M{months[0]}\u2013M{months[-1]}" if months else "-"
        g["month_count"] = len(months)
        g.pop("months")
        g["total_vehicles"] = int(round(g["total_vehicles"]))
        out.append(g)
    out.sort(key=lambda x: (x["route_id"], x["discipline"], x["section_id"]))
    return out


def _line_id(route_id, month_index, discipline, section_id):
    """
    Primary key for one forecast line.

    Every part is non-empty-or-'' rather than None. The old form was
    f"{route_id}::{month_index}"; adding nullable parts would have produced
    'route::3::None::None' for two different rows and collided them.
    """
    return f"{route_id}::{month_index}::{discipline or ''}::{section_id or ''}"


@app.post("/api/forecasts/bulk")
def save_matrix_row(row: MatrixRow):
    """
    Upsert one forecast line across a year. Cells at 0 are cleared.

    Both the conflict target and the delete clause carry the full widened key. The delete
    matters as much as the insert: scoped to (route_id, month_index) alone, a submitter
    typing 0 into the superstructure line would have deleted the substructure line for
    that month too.
    """
    if row.unit not in conversions.UNITS:
        raise HTTPException(400, f"unit must be one of {conversions.UNITS}")

    disc = row.discipline or ""
    sect = row.section_id or ""
    # Task F. The IPT written on the line is decided HERE, not trusted from the body:
    # an IPT code's own IPT, or a planner's explicit choice, never a silent default.
    acc = _require_access()
    ipt, err = access.ipt_for_save(row.ipt, acc)
    if err:
        raise HTTPException(400, err)
    # ...and an IPT code cannot overwrite a line that belongs to another IPT. The line
    # key is (route, discipline, section) across the cells; one check covers them all.
    if access.ipt_scope(acc):
        owner = db.query(
            "SELECT DISTINCT ipt FROM forecasts WHERE tenant_id = ? AND route_id = ? "
            "AND discipline = ? AND section_id = ?",
            (db.current_tenant(), row.route_id, disc, sect))
        foreign = [o["ipt"] for o in owner if access.canonical_ipt(o["ipt"]) != ipt]
        if foreign:
            raise HTTPException(404, "no such forecast line")
    touched = 0

    for c in row.cells:
        if not (1 <= c.month_index <= MONTH_COUNT):
            continue
        rid = _line_id(row.route_id, c.month_index, disc, sect)
        if c.quantity and c.quantity > 0:
            db.execute(
                """
                INSERT INTO forecasts
                    (tenant_id, id, route_id, month_index, discipline, section_id,
                     quantity, unit,
                     material_type, material_description, vehicle_type, submitted_by,
                     status, reject_reason, ipt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                -- must match the widened UNIQUE key exactly; see MatrixRow's docstring
                ON CONFLICT (tenant_id, route_id, month_index, discipline, section_id)
                DO UPDATE SET
                    quantity             = EXCLUDED.quantity,
                    unit                 = EXCLUDED.unit,
                    material_type        = EXCLUDED.material_type,
                    material_description = EXCLUDED.material_description,
                    vehicle_type         = EXCLUDED.vehicle_type,
                    submitted_by         = EXCLUDED.submitted_by,
                    status               = EXCLUDED.status,
                    reject_reason        = NULL,
                    ipt                  = COALESCE(EXCLUDED.ipt, forecasts.ipt)
                """,
                (db.current_tenant(),
                 rid, row.route_id, c.month_index, disc, sect, float(c.quantity), row.unit,
                 row.material_type, row.material_description, row.vehicle_type,
                 _by(row.submitted_by), row.status, None, ipt),
            )
            touched += 1
        else:
            db.execute(
                "DELETE FROM forecasts WHERE tenant_id = ? AND route_id = ? "
                "AND month_index = ? AND discipline = ? AND section_id = ?",
                (db.current_tenant(), row.route_id, c.month_index, disc, sect),
            )

    return {"status": "success", "route_id": row.route_id,
            "discipline": disc, "section_id": sect, "months_saved": touched,
            "caution": _coexisting_lines(row.route_id, disc, sect)}


def _coexisting_lines(route_id, discipline, section_id):
    """
    Other disciplines already forecasting on this route in the same months.

    Not an error -- ballast and fill to one destination in one month under different
    disciplines is the case the whole taxonomy exists for. But two people filling in the
    matrix independently can double-count the same lorry movements without ever seeing
    each other's line, so the save says so.
    """
    rows = db.query(
        "SELECT DISTINCT discipline, section_id, submitted_by, COUNT(*) AS months "
        "FROM forecasts WHERE tenant_id = ? AND route_id = ? "
        "AND NOT (discipline = ? AND section_id = ?) "
        "GROUP BY discipline, section_id, submitted_by",
        (db.current_tenant(), route_id, discipline or "", section_id or ""),
    )
    if not rows:
        return None
    others = [{"discipline": r["discipline"] or "(unassigned)",
               "section_id": r["section_id"] or "(unassigned)",
               "submitted_by": r.get("submitted_by"),
               "months": r["months"]} for r in rows]
    return {
        "message": (f"{len(others)} other forecast line(s) already exist on {route_id}. "
                    "Check you are not double-counting the same vehicle movements."),
        "lines": others,
    }


@app.put("/api/routes/{route_id}/status")
def set_route_status(route_id: str, req: StatusUpdate,
                     discipline: Optional[str] = None,
                     section_id: Optional[str] = None):
    """
    Approve / reject / reopen a forecast.

    Pass discipline and section_id to act on ONE line. Omit them and every line on the
    route is updated -- which is the old behaviour, kept so nothing breaks, but it now
    means approving another discipline's forecast as a side effect. The Approvals view
    should send the line keys.
    """
    _require_approver()
    clauses, params = ["route_id = ?"], [route_id]
    scoped = discipline is not None or section_id is not None
    if scoped:
        clauses.append("discipline = ?"); params.append(discipline or "")
        clauses.append("section_id = ?"); params.append(section_id or "")
    where = " AND ".join(clauses)

    existing = db.query(f"SELECT COUNT(*) AS n FROM forecasts WHERE tenant_id = ? AND {where}",
                        tuple([db.current_tenant()] + params))
    if existing[0]["n"] == 0:
        raise HTTPException(404, "No forecast for that route.")
    # tenant_id goes in the WHERE, never the SET — an UPDATE with no tenant predicate
    # rewrites every tenant's rows. The two SET placeholders come first in the params,
    # then the tenant, then whatever `clauses` accumulated.
    db.execute(f"UPDATE forecasts SET status = ?, reject_reason = ? "
               f"WHERE tenant_id = ? AND {where}",
               tuple([req.status, req.reject_reason, db.current_tenant()] + params))

    # Week 1, Task C: approving a month line is what materialises its four weeks.
    #
    # Driven off the rows that are now Approved rather than off the request, because
    # an unscoped call updates every line on the route and each of them needs its own
    # four weeks. A re-approval refreshes the `derived` weeks and leaves `edited` and
    # `confirmed` ones alone — see weeks.materialise_line().
    #
    # ⚠️ Rejecting or reopening deletes NOTHING. A confirmed week with an actual typed
    # against it is a record of what happened on site; dropping it because a planner
    # reopened the month would destroy that.
    materialised = None
    if req.status == "Approved":
        try:
            done = {"created": 0, "refreshed": 0, "kept": 0}
            lines = db.query(
                "SELECT DISTINCT discipline, section_id FROM forecasts "
                "WHERE tenant_id = ? AND route_id = ? AND status = 'Approved'",
                (db.current_tenant(), route_id))
            for l in lines:
                r = weeks.materialise_line(route_id, l["discipline"], l["section_id"])
                for k in done:
                    done[k] += r[k]
            materialised = done
        except Exception as e:
            # a failure here must not undo an approval that has already committed
            print("⚠️  Week 1: week materialisation failed for", route_id, e)

    return {"status": "success", "route_id": route_id, "new_status": req.status,
            "scoped_to_line": scoped, "rows": existing[0]["n"],
            "weeks": materialised}


# ------------------------------------------------ look-ahead (Week 1, Tasks C + D)
#
# NOT under /api/admin. Until Task F lands, visibility is exactly the same as
# /api/forecasts — everyone on staff sees every line — and these endpoints inherit
# that rather than inventing a narrower rule that Task F would then have to undo.
# ⚠️ That means anyone who can reach the staff app can confirm a week and type an
# actual. Task F is what scopes it; do not describe this as access-controlled.
class WeekKey(BaseModel):
    """The forecast LINE plus a week. Same shape every write below takes."""
    route_id: str
    month_index: int
    discipline: str = ""
    section_id: str = ""
    week_index: int


class WeekEdit(WeekKey):
    planned_qty: Optional[float] = None
    # the four flags are free text and every one may be empty
    weather: Optional[str] = None
    wetness: Optional[str] = None
    traffic: Optional[str] = None
    other: Optional[str] = None
    edited_by: Optional[str] = None


class WeekConfirm(WeekEdit):
    confirmed_by: Optional[str] = None


class WeekActual(WeekKey):
    actual_qty: Optional[float] = None
    actual_note: Optional[str] = None
    actual_by: Optional[str] = None
    # Look-ahead v2 slices 3-5: the confirmed cost of the week, typed beside the actual.
    # Written only when the field is SENT; an absent field leaves the stored cost alone.
    actual_cost_eur: Optional[float] = None


class WeekReopen(WeekKey):
    reopened_by: Optional[str] = None


class WeekCalibrate(WeekKey):
    # a typed figure INSTEAD of the variance formula, not on top of it
    override_qty: Optional[float] = None
    by: Optional[str] = None
    # Look-ahead v2: opt-in, default OFF. Spread the applied delta over the commit
    # week's remaining weekdays. spread_from is an ISO date; today when omitted.
    spread: bool = False
    spread_from: Optional[str] = None


def _flags_of(body):
    """Only the flag fields the client actually sent — an absent one is not a blank."""
    sent = set(_fields_set(body))
    return {k: getattr(body, k) for k in weeks.FLAG_FIELDS if k in sent}


@app.get("/api/forecast-weeks")
def list_forecast_weeks(from_month: int = Query(1, ge=1, le=MONTH_COUNT),
                        to_month: int = Query(MONTH_COUNT, ge=1, le=MONTH_COUNT),
                        route_id: Optional[str] = None):
    """
    The week rows in a month window, plus what the UI needs to label them.

    Reading materialises: a line approved before this shipped has no week rows, and an
    empty Look-ahead for an approved line reads as a broken feature rather than a
    missing migration. See weeks.list_weeks().
    """
    acc = _require_access()
    rows = access.filter_lines(weeks.list_weeks(from_month, to_month, route_id=route_id), acc)
    nm, nw = weeks.editable_week(START_YEAR)
    return {"from": min(from_month, to_month), "to": max(from_month, to_month),
            "weeks": rows,
            # which cell the UI lets you edit and confirm. Computed server-side so the
            # browser's clock and time zone cannot move it.
            "next_week": {"month_index": nm, "week_index": nw},
            # Look-ahead v2: the same bucket under the name the UI now uses. The brief
            # says keep `next_week` rather than churn the backend name — so both.
            "commit_week": {"month_index": nm, "week_index": nw},
            "statuses": list(weeks.WEEK_STATUSES),
            "flag_fields": list(weeks.FLAG_FIELDS),
            "summary": weeks.summary()}


@app.put("/api/forecast-weeks")
def edit_forecast_week(body: WeekEdit):
    """Edit one week's planned quantity and/or flags. Sets status `edited`."""
    _require_line(body.route_id, body.month_index, body.discipline, body.section_id)
    res = weeks.set_week(body.route_id, body.month_index, body.discipline,
                         body.section_id, body.week_index,
                         planned_qty=body.planned_qty, flags=_flags_of(body),
                         by=_by(body.edited_by))
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@app.post("/api/forecast-weeks/confirm")
def confirm_forecast_week(body: WeekConfirm):
    """Confirm one week, with the four optional flags. Sets status `confirmed`."""
    _require_line(body.route_id, body.month_index, body.discipline, body.section_id)
    # Look-ahead v2 (L6): confirm is whole-week and ONE act. days.confirm_week() calls
    # weeks.confirm_week() and then stamps every day in the bucket `confirmed`; a week
    # outside the commit bucket has no days and confirms exactly as before.
    res = days.confirm_week(body.route_id, body.month_index, body.discipline,
                            body.section_id, body.week_index,
                            by=_by(body.confirmed_by), flags=_flags_of(body))
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@app.put("/api/forecast-weeks/actual")
def set_forecast_week_actual(body: WeekActual):
    """
    Type what actually moved in one week.

    ⭐ Does NOT calibrate. Variance appears immediately; next week's plan does not
    move until /api/forecast-weeks/calibrate is called.
    """
    _require_line(body.route_id, body.month_index, body.discipline, body.section_id)
    res = weeks.set_actual(body.route_id, body.month_index, body.discipline,
                           body.section_id, body.week_index,
                           actual_qty=body.actual_qty, actual_note=body.actual_note,
                           by=_by(body.actual_by), actual_cost_eur=body.actual_cost_eur,
                           cost_given=("actual_cost_eur" in set(_fields_set(body))))
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@app.post("/api/forecast-weeks/reopen")
def reopen_forecast_week(body: WeekReopen):
    """
    Look-ahead v2: take a confirmed week back to `edited`. Its days follow. Nothing is
    deleted — the mocks' footer promises "re-open the week in Look-ahead to change the
    plan", and this is that.
    """
    _require_line(body.route_id, body.month_index, body.discipline, body.section_id)
    res = days.reopen_week(body.route_id, body.month_index, body.discipline,
                           body.section_id, body.week_index, by=_by(body.reopened_by))
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@app.post("/api/forecast-weeks/calibrate")
def calibrate_forecast_week(body: WeekCalibrate):
    """
    Carry this week's variance into next week — and only next week.

    400 when next week is already confirmed. The response's `blocked_by` says so, so
    the UI can disable the button rather than discovering it on click.
    """
    _require_line(body.route_id, body.month_index, body.discipline, body.section_id)
    res = days.calibrate(body.route_id, body.month_index, body.discipline,
                         body.section_id, body.week_index,
                         override_qty=body.override_qty, by=_by(body.by),
                         spread=bool(body.spread), spread_from=body.spread_from)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


# --------------------------------------------- forecast days (Look-ahead v2, slice 1)
#
# The commit week — the bucket that contains today — day by day. Days exist for that
# bucket only and for Approved lines only; see days.py's rules. Visibility is the parent
# line's ipt, exactly as the week endpoints. No CSV import, no file body.
class DayKey(BaseModel):
    route_id: str
    month_index: int
    discipline: str = ""
    section_id: str = ""
    day_date: str                          # ISO date, YYYY-MM-DD


class DayEdit(DayKey):
    planned_qty: float
    edited_by: Optional[str] = None


class DayActual(DayKey):
    actual_qty: Optional[float] = None
    actual_note: Optional[str] = None
    actual_by: Optional[str] = None


@app.get("/api/forecast-days")
def list_forecast_days(from_date: Optional[str] = Query(None, alias="from"),
                       to_date: Optional[str] = Query(None, alias="to"),
                       route_id: Optional[str] = None,
                       bucket: str = "commit"):
    """
    The commit week's days, grouped by forecast line, with the sum-rule flag per line.

    `from` / `to` (ISO dates) clip what is returned; the default is the whole bucket.
    They never widen it — there are no days outside the commit week. Reading
    materialises, as the week endpoint does.

    Slice 2: every line also carries `context` (origin→dest, IPT, WS, material,
    vehicle, payload, baked state, cycle, flags) and `week_derived`; every day carries
    `derived` (tonnes, trips, vehicles, km_day, km_per_vehicle, tonne_km); the response
    carries `totals` for the KPI strip. See derived.py for the formulas (brief §4).
    """
    acc = _require_access()
    # `bucket=next` reads (and materialises) the week AFTER the commit week — the
    # Thursday process: next week's look-ahead confirmed for next week's deliveries.
    res = days.list_days(from_date, to_date, route_id=route_id,
                         bucket=("next" if bucket == "next" else "commit"))
    res["lines"] = access.filter_lines(res["lines"], acc)
    # Look-ahead v2 slice 2: context chips and the derived columns, computed on read
    # from the SAME route_analysis() path analysis-batch and month-kpis use. After the
    # access filter, so `totals` is for the lines this caller can see. Unbaked lines
    # get trips and tonnes only, and the UNBAKED flag — no distance is invented.
    derived.decorate(res)
    res["statuses"] = list(days.DAY_STATUSES)
    res["summary"] = days.summary()
    return res


@app.get("/api/lookahead")
def lookahead_page(bucket: str = "commit", route_id: Optional[str] = None,
                   restrictions_on: int = 1, tark_tee: Optional[int] = None):
    """
    Look-ahead v2 slices 3-6: everything the page's three views need in one read —
    commit (days + derived + totals), account (last week), horizon (roles), stock and
    the clash rail. `bucket=next` is the Thursday process.

    🔴 The road-restriction source here is the STORED per-route check (a DB read), never
    the live fetch — the live fetch froze the page on 09 Sep. `sources.restrictions` says
    how current it is; POST /api/forecast-weeks/restrictions/refresh re-checks in the
    background. `tark_tee=` is the pre-H1 name of `restrictions_on=` and still works.
    """
    acc = _require_access()
    on = bool(restrictions_on) if tark_tee is None else bool(tark_tee)
    return lookahead.page(bucket=("next" if bucket == "next" else "commit"),
                          route_id=route_id, acc=acc, with_restrictions=on)


@app.get("/api/lookahead/geometry")
def lookahead_geometry(ids: str = "", vehicles: str = ""):
    """
    10 Sep — the Commit view's week map. `ids` = comma-separated route ids (the lines the
    caller already sees), `vehicles` = the matching vehicle types, aligned by position and
    optional. Returns each route's baked loaded geometry and both ends with coordinates;
    an unbaked route comes back with geometry null. Any staff code. Deliberately NOT a
    page read — the map must never make the grid slower.
    """
    _require_access()
    id_list = [x.strip() for x in ids.split(",") if x.strip()]
    veh_list = [x.strip() for x in vehicles.split(",")] if vehicles else []
    veh = {rid: v for rid, v in zip(id_list, veh_list) if v}
    return {"routes": lookahead.week_geometry(id_list, veh)}


@app.get("/api/forecast-weeks/restrictions")
@app.get("/api/forecast-weeks/tark-tee", include_in_schema=False)     # pre-H1 path
def forecast_week_restrictions(bucket: str = "commit", route_id: Optional[str] = None):
    """
    The STORED road-restriction flags for the page's routes in this bucket's week, how
    old they are, which routes have never been checked, and whether a refresh is
    running. Instant — a DB read. The page polls this while a refresh runs. The provider
    (Tark Tee / National Highways) and its flag word come back with it.
    """
    acc = _require_access()
    return lookahead.restriction_status(bucket=("next" if bucket == "next" else "commit"),
                                        route_id=route_id, acc=acc)


@app.post("/api/forecast-weeks/restrictions/refresh")
@app.post("/api/forecast-weeks/tark-tee/refresh", include_in_schema=False)   # pre-H1 path
def forecast_week_restrictions_refresh(sync: int = 0):
    """
    Re-check every baked route against the country's live provider and store the result.
    Runs in a background thread (30 s+ on a cold cache); returns at once with the refresh
    state. `sync=1` waits. Any signed-in staff code may call it — it reads public road
    data and writes only the stored check.
    """
    _require_access()
    try:                                  # 13 Oct 2026: the lorry-limits check is a DB read; re-run it too
        limits.store_checks()
    except Exception as e:
        print("limits: route check not stored:", str(e)[:120])
    return restrictions.refresh_async(sync=bool(sync))


@app.get("/api/forecast-weeks/clashes")
def forecast_week_clashes(bucket: str = "commit", route_id: Optional[str] = None,
                          restrictions_on: int = 0, tark_tee: Optional[int] = None):
    """The rail alone (brief §6), for a caller that already has the grid."""
    acc = _require_access()
    on = bool(restrictions_on) if tark_tee is None else bool(tark_tee)
    pg = lookahead.page(bucket=("next" if bucket == "next" else "commit"),
                        route_id=route_id, acc=acc, with_restrictions=on)
    out = dict(pg["clashes"])
    out["stock"] = pg["stock"]
    out["commit_week"] = pg["commit_week"]
    return out


@app.get("/api/forecast-weeks/export")
def forecast_week_export(format: str = "xlsx", bucket: str = "commit",
                         route_id: Optional[str] = None, restrictions_on: int = 1,
                         tark_tee: Optional[int] = None):
    # the export reads the same STORED restriction check the page does — instant
    """
    Browser download of the commit week — xlsx (day × line, stock, clashes) or the PDF
    one-pager. No email, no upload. Built from the same read the page shows.
    """
    from fastapi.responses import Response       # not in the test stub; imported here
    acc = _require_access()
    on = bool(restrictions_on) if tark_tee is None else bool(tark_tee)
    pg = lookahead.page(bucket=("next" if bucket == "next" else "commit"),
                        route_id=route_id, acc=acc, with_restrictions=on)
    cw = pg.get("commit_week") or {}
    stem = f"lookahead-{cw.get('from', 'week')}"
    try:
        if format == "pdf":
            data, mime, ext = export.build_pdf(pg), "application/pdf", "pdf"
        else:
            data, mime, ext = (export.build_xlsx(pg),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               "xlsx")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{stem}.{ext}"'})


@app.get("/api/forecast-weeks/day-sheet")
def forecast_week_day_sheet(day: str, bucket: str = "commit", route_id: Optional[str] = None):
    """
    14 Oct 2026 (D9, the mobile shell): the Day sheet, one weekday of the open week as a one-page A4 PDF (the phone's
    Look-ahead button; mockup 10). Any staff code, scoped like the page (a team code sees its own lines only), built
    from the same read the page shows, with the stored restriction check. `day` must be a weekday of that week.
    """
    from fastapi.responses import Response       # not in the test stub; imported here
    acc = _require_access()
    try:
        import datetime as _dt
        d = _dt.date.fromisoformat(day)
    except (TypeError, ValueError):
        raise HTTPException(400, "day must be a date, YYYY-MM-DD")
    pg = lookahead.page(bucket=("next" if bucket == "next" else "commit"), route_id=route_id, acc=acc,
                        with_restrictions=True)
    cw = pg.get("commit_week") or {}
    if not (cw.get("from") and cw.get("to") and cw["from"] <= day <= cw["to"]) or d.weekday() > 4:
        raise HTTPException(400, f"{day} is not a weekday of the week {cw.get('from')} to {cw.get('to')}")
    try:
        data = export.build_day_sheet_pdf(pg, day)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="day-sheet-{day}.pdf"'})


@app.put("/api/forecast-days")
def edit_forecast_day(body: DayEdit):
    """Type one day's planned quantity. The day and (if it was derived) its week go `edited`."""
    _require_line(body.route_id, body.month_index, body.discipline, body.section_id)
    res = days.set_day(body.route_id, body.month_index, body.discipline,
                       body.section_id, body.day_date, body.planned_qty, by=_by(body.edited_by))
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@app.put("/api/forecast-days/actual")
def set_forecast_day_actual(body: DayActual):
    """
    Type what actually moved on one day.

    ⭐ Does NOT calibrate. The week actual becomes the running sum of the day actuals
    ONLY while no clerk has typed a week figure — a typed week actual is never overwritten.
    """
    _require_line(body.route_id, body.month_index, body.discipline, body.section_id)
    res = days.set_day_actual(body.route_id, body.month_index, body.discipline,
                              body.section_id, body.day_date,
                              actual_qty=body.actual_qty, actual_note=body.actual_note,
                              by=_by(body.actual_by))
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


# --------------------------------------------- stockpiles (Week 1, Task D2)
class CapacityIn(BaseModel):
    # None CLEARS the capacity — "we do not know how big this stockpile is" is a real state
    # and is not zero. See stockpiles.set_capacity().
    capacity_qty: Optional[float] = None
    capacity_unit: Optional[str] = None
    opening_qty: Optional[float] = None


class ConsumeIn(BaseModel):
    location_id: str
    month_index: int
    week_index: int
    consumed_qty: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None
    updated_by: Optional[str] = None


@app.put("/api/locations/{location_id}/capacity")
def set_location_capacity(location_id: str, body: CapacityIn,
                          token: Optional[str] = None):
    """Max live stock, its unit, and the opening figure. Admin-gated like every other
    write to master data."""
    _check_admin(token)
    res = stockpiles.set_capacity(location_id, capacity_qty=body.capacity_qty,
                                  capacity_unit=body.capacity_unit,
                                  opening_qty=body.opening_qty)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    return res


@app.get("/api/stockpiles")
def list_stockpiles(from_month: int = Query(1, ge=1, le=MONTH_COUNT),
                    to_month: int = Query(MONTH_COUNT, ge=1, le=MONTH_COUNT),
                    location_id: Optional[str] = None):
    """
    Per-week stock for every location that can hold it.

    A read model — nothing here is stored. Inbound comes from typed week ACTUALS, so a
    week nobody has reported shows inbound 0 rather than a quarter of the forecast.
    """
    # Task F: any valid code. ⚠️ NOT filtered by IPT — a stockpile has no IPT, and inferring
    # one from the routes that feed it would be a guess. An IPT code sees every stockpile.
    _require_access()
    out = stockpiles.balances(from_month, to_month, location_id=location_id)
    out["storage_types"] = list(stockpiles.STORAGE_TYPES)
    out["capacity_units"] = list(stockpiles.CAPACITY_UNITS)
    return out


@app.put("/api/stockpiles/consume")
def consume_stockpile(body: ConsumeIn):
    """One week's typed consumption. There is no file and no importer."""
    _require_access()
    res = stockpiles.consume(body.location_id, body.month_index, body.week_index,
                             consumed_qty=body.consumed_qty, unit=body.unit,
                             note=body.note, by=_by(body.updated_by))
    if res.get("error"):
        raise HTTPException(404, res["error"])
    return res


# ------------------------------------------------------- config (2.5b)
class FactorsIn(BaseModel):
    doc: dict
    updated_by: Optional[str] = None


@app.get("/api/config/factors")
def get_factors_config():
    """The live document, where it came from, and whether the file has drifted.
    Readable by any signed-in user; only admins write."""
    _require_access()
    return {"doc": conversions.load_factors(), "status": config.status(conversions),
            "file": conversions.load_factors_file()}


@app.put("/api/admin/config/factors")
def put_factors_config(body: FactorsIn, token: Optional[str] = None):
    """
    Replace the live document. Refused with the list of problems if it fails
    config.validate() — a bad document here changes every number in the system.
    """
    _check_admin(token)
    res = config.save(body.doc, by=_by(body.updated_by), network=network)
    if not res["ok"]:
        raise HTTPException(400, "; ".join(res["problems"]))
    return {"ok": True, "status": config.status(conversions)}


@app.post("/api/admin/config/factors/reset")
def reset_factors_config(updated_by: Optional[str] = None, token: Optional[str] = None):
    """Overwrite the live document with backend/factors.json. Refused, with the problems,
    when the file would remove a vehicle the network is baked for (11 Oct 2026: the same
    check a Save makes)."""
    _check_admin(token)
    res = config.reset_to_file(conversions, by=_by(updated_by), network=network)
    if not res["ok"]:
        raise HTTPException(400, "; ".join(res["problems"]))
    return {"ok": True, "status": config.status(conversions)}


# ------------------------------------------------- costing + fuel index (10 Sep evening)
class TargetRatesIn(BaseModel):
    rate_eur_per_load: Optional[float] = None
    rate_eur_per_t: Optional[float] = None
    rate_eur_per_km: Optional[float] = None
    updated_by: Optional[str] = None


class FuelSettingsIn(BaseModel):
    yard_eur_per_l: Optional[float] = None
    share_pct: Optional[float] = None
    country: Optional[str] = None
    updated_by: Optional[str] = None


class ManualIndexIn(BaseModel):
    eur_per_l: float
    bulletin_date: str
    updated_by: Optional[str] = None


def _costing_payload():
    s = costing.settings(use_cache=False)
    country = fuel.norm_country(s["fuel"].get("country"))
    idx = fuel.get_index(country)
    out = {"target": s["target"], "fuel": s["fuel"], "index": fuel.state(country),
           "summary": costing.summary(idx)}
    return out


@app.get("/api/costing")
def get_costing():
    """The tenant's target rates, fuel settings, the stored diesel index and the BAF
    they give. Any signed-in code. Never fetches."""
    _require_access()
    return _costing_payload()


@app.put("/api/admin/costing/target")
def put_costing_target(body: TargetRatesIn, token: Optional[str] = None):
    """
    Type the TARGET rates (€/load, €/t, €/km) — the Planned € for every route that has
    no rate of its own. Only the fields sent are written; a sent null clears one.
    Admin token: a target changes every unpriced line's € at once. Nothing is seeded.
    """
    _check_admin(token)
    fields = {k: getattr(body, k) for k in costing.TARGET_FIELDS if k in _fields_set(body)}
    res = costing.set_target(fields, by=_by(body.updated_by))
    if not res["ok"]:
        raise HTTPException(400, "; ".join(res["problems"]))
    return _costing_payload()


@app.get("/api/fuel-index")
def get_fuel_index(lazy: int = 1, sync: int = 0):
    """
    The widget's read: the stored diesel row for the tenant's country (the EU Weekly Oil
    Bulletin for EU-27, DESNZ weekly road fuel prices for GB, a typed row elsewhere),
    its staleness, the tenant's fuel settings and the BAF. Returns the STORED row at
    once; when the last attempt is older than 12 h it starts one background refresh
    (`lazy=0` to suppress; `sync=1` waits — tests and diagnostics). Never on the page
    read's path: /api/lookahead reads the row only.
    """
    _require_access()
    if lazy:
        s = costing.settings()
        fuel.ensure_fresh(fuel.norm_country(s["fuel"].get("country")), sync=bool(sync))
    return _costing_payload()


@app.post("/api/admin/fuel-index/refresh")
def refresh_fuel_index(sync: int = 0, token: Optional[str] = None):
    """Fetch the feed now (admin). `sync=1` waits for the outcome."""
    _check_admin(token)
    s = costing.settings()
    fuel.refresh(fuel.norm_country(s["fuel"].get("country")), sync=bool(sync))
    return _costing_payload()


@app.put("/api/fuel-index/settings")
def put_fuel_settings(body: FuelSettingsIn):
    """
    Type the yard €/L (optional, cost-plus later) and the fuel share % (empty = no BAF
    line). Planner or admin. Never touches the bulletin row or the locked base.
    """
    _require_approver()
    fields = {k: getattr(body, k) for k in costing.FUEL_FIELDS if k in _fields_set(body)}
    res = costing.set_fuel(fields, by=_by(body.updated_by))
    if not res["ok"]:
        raise HTTPException(400, "; ".join(res["problems"]))
    return _costing_payload()


@app.put("/api/admin/fuel-index/manual")
def put_fuel_manual(body: ManualIndexIn, token: Optional[str] = None):
    """Type the index when the feed is down (admin). Writes the same row, source 'manual'."""
    _check_admin(token)
    s = costing.settings()
    res = fuel.set_manual(body.eur_per_l, body.bulletin_date, by=_by(body.updated_by),
                          country=fuel.norm_country(s["fuel"].get("country")))
    if not res["ok"]:
        raise HTTPException(400, "; ".join(res["problems"]))
    return _costing_payload()


@app.post("/api/admin/fuel-index/reset-base")
def reset_fuel_base(updated_by: Optional[str] = None, token: Optional[str] = None):
    """Clear the locked BAF base (admin). The next Confirm week locks a fresh one."""
    _check_admin(token)
    costing.reset_baf_base(by=_by(updated_by))
    return _costing_payload()


class CostPreview(BaseModel):
    route_id: str
    vehicle_type: str
    material_type: Optional[str] = None
    unit: str = "t"
    cells: List[Cell] = []


@app.post("/api/costing/preview")
def costing_preview(body: CostPreview):
    """
    11 Sep pm — the Submit-forecast matrix's price while typing: the body's cells priced
    as the saved line will be (same functions as /api/costing/lines). A read that takes a
    body; it stores nothing. Any signed-in code.
    """
    _require_access()
    return costlines.preview(body.route_id, body.vehicle_type, body.material_type, body.unit,
                             [c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in body.cells])


@app.get("/api/costing/lines")
def costing_lines(from_: Optional[int] = Query(None, alias="from"), to: Optional[int] = None,
                  status: Optional[str] = None):
    """
    11 Sep — every visible forecast line × month with volume, haul, carbon and the three
    prices (planned / fair) each in € · €/t · €/trip · €/km, from the Look-ahead's own
    functions. The Dashboard and the Forecasts page read THIS and derive nothing.
    `status` = Approved | Pending | Rejected | All (default All). Any signed-in code;
    the access filter is the same as /api/forecasts.
    """
    acc = _require_access()
    return costlines.lines(acc, from_month=from_, to_month=to, status=status)


# ------------------------------------------------------------------ carbon planner (10 Oct 2026)
class CarbonAlternative(BaseModel):
    name: Optional[str] = None
    levers: List[dict] = []


class CarbonScenarioIn(BaseModel):
    from_month: Optional[int] = None
    to_month: Optional[int] = None
    status: str = "Approved"
    baseline: List[dict] = []                 # levers that describe today's plan (e.g. a known recycled share)
    alternatives: List[CarbonAlternative] = []
    spend_gbp_m: Optional[float] = None       # typed programme spend, for tCO2e per £m (NH's own KPI)
    allocation: Optional[dict] = None         # {category: {Fencing: %, ...}} — over 100 % is refused


CARBON_STATUSES = ("Approved", "Pending", "Rejected", "All")
CARBON_MAX_ALTERNATIVES = 6


@app.post("/api/carbon/scenario")
def carbon_scenario(body: CarbonScenarioIn):
    """
    10 Oct 2026 — the Carbon page's one read: the baseline (the caller's visible forecast lines,
    Approved by default) and up to six alternatives, each with its totals, the delta, and the
    per-driver deltas RANKED by tCO2e moved; benchmarks; diesel-vs-electric fleet counts; every
    factor's source, year and status. A read that takes a body: it stores nothing. Any
    signed-in code — a team code sees only its own lines, the same filter as /api/costing/lines.
    Planning estimates, not a National Highways Carbon Tool return. 400 for a lever the rules
    refuse (allocation over 100 %, an EPD with no source, an unknown vehicle).
    """
    acc = _require_access()
    if body.status not in CARBON_STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(CARBON_STATUSES)}")
    if len(body.alternatives) > CARBON_MAX_ALTERNATIVES:
        raise HTTPException(400, f"at most {CARBON_MAX_ALTERNATIVES} alternatives at a time")
    alts = [a.model_dump() if hasattr(a, "model_dump") else a.dict() for a in body.alternatives]
    try:
        return carbon.scenario(acc, alternatives=alts, baseline_levers=body.baseline,
                               from_month=body.from_month, to_month=body.to_month, status=body.status,
                               spend_m=body.spend_gbp_m, allocation=body.allocation)
    except carbon.CarbonError as e:
        raise HTTPException(400, str(e))


class CarbonSummaryIn(CarbonScenarioIn):
    commentary: Optional[str] = None          # printed on the summary as typed; never stored


CARBON_COMMENTARY_MAX = 1500


@app.post("/api/carbon/summary.pdf")
def carbon_summary_pdf(body: CarbonSummaryIn):
    """
    After the show (11 Oct 2026, notes/carbon-ui-1011 item 11): the Carbon page's one-page summary
    as a PDF, from the SAME read as /api/carbon/scenario: the approved plan beside the page's one
    alternative, the decisions in words and ranked, what the figures count, and the typed
    Commentary. Stamped "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures",
    and the tenant's demo notice when set. Stores nothing: the commentary is printed, not saved.
    """
    from fastapi.responses import Response       # not in every test stub; imported here
    acc = _require_access()
    if body.status not in CARBON_STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(CARBON_STATUSES)}")
    if len(body.alternatives) > 1:
        raise HTTPException(400, "the summary prints the approved plan and one alternative")
    if body.commentary is not None and len(body.commentary) > CARBON_COMMENTARY_MAX:
        raise HTTPException(400, f"the commentary is at most {CARBON_COMMENTARY_MAX} characters")
    alts = [a.model_dump() if hasattr(a, "model_dump") else a.dict() for a in body.alternatives]
    try:
        sc = carbon.scenario(acc, alternatives=alts, baseline_levers=body.baseline,
                             from_month=body.from_month, to_month=body.to_month, status=body.status,
                             spend_m=body.spend_gbp_m, allocation=body.allocation)
    except carbon.CarbonError as e:
        raise HTTPException(400, str(e))
    try:
        data = export.build_carbon_pdf(sc, commentary=body.commentary)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="carbon-summary.pdf"'})


# ------------------------------------------------------------------ carbon target (11 Oct 2026)
class CarbonTargetIn(BaseModel):
    mode: Optional[str] = None                # "pct" (% below the approved plan) or "cap" (a fixed tCO2e cap)
    levers: Optional[List[dict]] = None       # the agreed decisions; absent = switch how the target is held
    ui_state: Optional[dict] = None           # the Carbon page's own state, stored as sent (at most 20 000 characters)
    updated_by: Optional[str] = None          # the name typed at sign-in, as for the costing target (no identity until G3)


@app.get("/api/carbon/target")
def get_carbon_target():
    """
    11 Oct 2026 — the programme's carbon target and the progress against it, ALL-IN tCO2e (making the
    material, transport and waste disposal). Any signed-in code. `status` is measured on the lines the
    code can see: scope "scheme" for planner, admin and the demo submitter, "team" for a team code. Both
    are null when no target is set. Stored decisions that no longer apply give status.invalid, never an
    error. 11 Oct 2026: the server says whether each figure is on target (status.on_target_as_forecast /
    on_target_with_decisions, within carbon_target.ON_TARGET_TOL_T); the target is the scheme's, so a team
    code's target_t, gaps and on_target flags are null in both modes, and its GET never carries the stored
    decisions or the page state (only the words of decisions that name no route).
    """
    acc = _require_access()
    return carbon_target.payload(acc)


@app.put("/api/carbon/target")
def put_carbon_target(body: CarbonTargetIn):
    """
    Set the carbon target (planner or admin). With `levers`, the server runs carbon.scenario over the
    approved plan with them as the one alternative and stores what that gives; the browser sends no
    figure. Without `levers`, `mode` switches how an existing target is held, keeping every number.
    400 with a plain sentence when the rules refuse it. Returns the same payload as GET.
    """
    acc = _require_approver()
    try:
        if body.levers is not None:
            carbon_target.set_from_levers(acc, body.mode, body.levers, body.ui_state, by=_by(body.updated_by))
        else:
            carbon_target.set_mode(body.mode, by=_by(body.updated_by))
    except carbon_target.TargetError as e:
        raise HTTPException(400, str(e))
    return carbon_target.payload(acc)


@app.delete("/api/carbon/target")
def delete_carbon_target():
    """Clear the carbon target (planner or admin). Returns the GET payload, target null."""
    acc = _require_approver()
    carbon_target.clear()
    return carbon_target.payload(acc)


# ------------------------------------------------------------------ the monthly bulletin (B4, 12 Oct 2026)
@app.get("/api/bulletin/month")
def bulletin_month(month: int = Query(..., ge=1, le=MONTH_COUNT)):
    """
    The monthly bulletin's figures as JSON (review §2.6; the HTML / PDF composition is another
    track). Staff only — any valid code. `rollup` is the public map bar's month roll-up
    reproduced on the server from the same per-line payload `/api/public/month-kpis` serves,
    whole scheme, no map filters (bulletin.rollup_payloads carries the bar's eleven rules);
    `conditions` is what the map's Conditions panel assembles, read from what is STORED:
    restriction hits overlapping the calendar month ("never checked" where no check is stored),
    stockpiles over at month end, the seasonal windows for the month, and typed caps exceeded
    (a "planning flag", never a block). A team code gets the scheme's figures (they are the
    public map's), every team's row included (D37, 12 Oct 2026).
    """
    acc = _require_access()
    return bulletin.month_page(month, acc)


def _bulletin_month_default():
    """The calendar month today, inside the programme's horizon."""
    import datetime as _dt
    mi = weeks.month_index_of(_dt.datetime.now(_dt.timezone.utc).date())
    return max(1, min(MONTH_COUNT, mi))


@app.get("/api/bulletin/month.pdf")
def bulletin_month_pdf(month: int = Query(..., ge=1, le=MONTH_COUNT), request: Request = None):
    """
    12 Oct 2026 (C4, review §2.6, mockup 9) — the monthly bulletin as an A4 PDF, two pages, from
    bulletin_doc.sheet(): the SAME view model the HTML page at /bulletin/ renders, which is
    bulletin.month_page() formatted, so the PDF, the page and the JSON cannot disagree. Staff only
    (D10): a valid code (the Dashboard's button sends it) or the staff cookie (the HTML page's
    Download link sends only that). The map is Mapbox's static image, or the schematic when it
    cannot be had; the tenant's demo notice is on every page. Stores nothing.
    """
    from fastapi.responses import Response       # not in every test stub; imported here
    if not _staff_request(request):
        raise HTTPException(401, "sign in — a valid access code is required")
    sheet = bulletin_doc.sheet(month, access.current())
    try:
        data = export.build_bulletin_pdf(sheet)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    y, m = weeks._month_of(month)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="bulletin-{y}-{m:02d}.pdf"',
                             "Cache-Control": "no-store"})


@app.get("/api/bulletin/leaflet.pdf")
def bulletin_leaflet_pdf(month: int = Query(..., ge=1, le=MONTH_COUNT), request: Request = None):
    """
    13 Oct 2026 (D43) — the one-page LEAFLET (residents, the working group) as an A4 PDF, from the SAME view model as
    the newsletter and the page (bulletin_doc.sheet). Staff only, the bulletin's rule (D10). Stores nothing.
    """
    from fastapi.responses import Response       # not in every test stub; imported here
    if not _staff_request(request):
        raise HTTPException(401, "sign in — a valid access code is required")
    sheet = bulletin_doc.sheet(month, access.current())
    try:
        data = export.build_bulletin_leaflet_pdf(sheet)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    y, m = weeks._month_of(month)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="leaflet-{y}-{m:02d}.pdf"',
                             "Cache-Control": "no-store"})


@app.get("/bulletin/leaflet/")
def bulletin_leaflet_page(month: Optional[int] = Query(None, ge=1, le=MONTH_COUNT), request: Request = None):
    """13 Oct 2026 (D43) — the leaflet as an HTML page; staff-gated like /bulletin/ (gate.scope_for: "bulletin")."""
    from fastapi.responses import Response       # not in every test stub; imported here
    if not _staff_request(request):
        return Response(content=_BULLETIN_SIGNIN_PAGE, status_code=401, media_type="text/html; charset=utf-8")
    mi = month if month is not None else _bulletin_month_default()
    return Response(content=bulletin_doc.leaflet_html(bulletin_doc.sheet(mi, access.current())),
                    media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


@app.get("/bulletin/")
def bulletin_page(month: Optional[int] = Query(None, ge=1, le=MONTH_COUNT), request: Request = None):
    """
    12 Oct 2026 (C4) — the monthly bulletin as an HTML page (GOV.UK: HTML first, the PDF
    alongside), from the same view model as the PDF; one column on a phone, a print stylesheet.
    Staff-gated like /help/: gate.scope_for() calls /bulletin "bulletin" and the middleware refuses
    anything but a valid code or the STAFF cookie (the map password does not open it). The body
    checks again, so the harnesses that stub the middleware see the same rule. No month: this
    calendar month, inside the programme.
    """
    from fastapi.responses import Response       # not in every test stub; imported here
    if not _staff_request(request):
        return Response(content=_BULLETIN_SIGNIN_PAGE, status_code=401, media_type="text/html; charset=utf-8")
    mi = month if month is not None else _bulletin_month_default()
    return Response(content=bulletin_doc.html(bulletin_doc.sheet(mi, access.current())),
                    media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ public feed (map)
def _working_days(factors):
    """
    Working days in a planning month, from factors.json.

    ⭐ 2026-09-15 — ONE reader for this figure. It was read inline in
    `public_month_kpis` and nowhere else; the map's route label now needs it too, and
    lesson 25 ("one config value, one reader") is in the notes precisely because a
    second inline read of MAPBOX_TOKEN hid a missing Render variable for a month.
    Every public endpoint that divides by a day count divides by THIS.
    """
    plan = (factors or {}).get("planning", {}) or {}
    try:
        wd = float(plan.get("working_days_per_month") or 22)
    except (TypeError, ValueError):
        wd = 22.0
    # a zero or negative in a hand-edited factors.json must not produce a division by
    # zero on a public endpoint
    return wd if wd > 0 else 22.0


@app.get("/api/public/route-forecasts")
def public_route_forecasts(
    from_: int = Query(1, alias="from", ge=1, le=MONTH_COUNT),
    to: int = Query(MONTH_COUNT, ge=1, le=MONTH_COUNT),
    unit: str = Query("vehicles"),
):
    """
    Approved forecasts only, aggregated per route over [from, to], returned in
    the requested unit. This is what the map paints. Shape:
        { "hr-ew-...": {"avg": .., "per_day": .., "peak": .., "total": ..,
                        "unit": .., "working_days": ..}, ... }

    ⭐ 2026-09-15 — `per_day` is new and it is what the route label on the map now
    prints. `avg` is a MONTHLY average over the window; the label read as a rate and
    was one, just the wrong one — "2221 Two-way" on a route doing about a hundred
    movements a day. Divided here rather than in the map so the divisor has ONE reader
    (lesson 25, and the same reason the Dashboard's client arithmetic was retired):
    `working_days_per_month` from factors.json, the same figure `/api/public/month-kpis`
    already hands the KPI cards.
    """
    if unit not in conversions.UNITS:
        raise HTTPException(400, f"unit must be one of {conversions.UNITS}")
    lo, hi = min(from_, to), max(from_, to)
    rows = db.query(
        "SELECT * FROM forecasts WHERE tenant_id = ? AND status = 'Approved' "
        "AND month_index BETWEEN ? AND ?",
        (db.current_tenant(), lo, hi),
    )
    factors = conversions.load_factors()
    agg = {}
    for r in rows:
        v = conversions.convert_row(r, unit, factors)
        a = agg.setdefault(r["route_id"], {"total": 0.0, "peak": 0.0, "months": 0})
        a["total"] += v
        a["peak"] = max(a["peak"], v)
        a["months"] += 1

    wd = _working_days(factors)
    out = {}
    for rid, a in agg.items():
        months = a["months"] or 1
        out[rid] = {
            "avg": conversions.round_for_unit(a["total"] / months, unit),
            # the rate a reader of the map label is actually after: one month's worth
            # spread over that month's working days
            "per_day": conversions.round_for_unit(a["total"] / months / wd, unit),
            "peak": conversions.round_for_unit(a["peak"], unit),
            "peak_per_day": conversions.round_for_unit(a["peak"] / wd, unit),
            "total": conversions.round_for_unit(a["total"], unit),
            "unit": unit,
            "working_days": wd,
        }
    return out


@app.get("/api/public/month-kpis")
def public_month_kpis(month: int = Query(..., ge=1, le=MONTH_COUNT),
                      unit: str = Query("vehicles")):
    """
    2026-09-02 (§9). One month of APPROVED forecast, per LINE, with every figure the
    map's KPI cards need already converted — so the map aggregates after its own
    filters and never guesses a payload.

    Per line: the typed quantity in the map unit, in tonnes, and in vehicle-loads.
    Vehicle-loads = tonnes ÷ that line's payload; a vehicle_type factors.json does not
    know falls back to the first PLANNING vehicle (in the seed, Rigid 8-wheeler (32t),
    20 t, since 11 Oct 2026) and says so in `payload_fallback`, rather than to the
    anonymous _default. The pair comes from derived.payload_for(), the Look-ahead's own
    rule, so the two cannot drift.

    ⭐ 2026-09-03, the human's correction: vehicles and movements are DIFFERENT
    numbers. A MOVEMENT (trip) is one load carried one way. How many movements one
    VEHICLE can make in a day is a property of the ROUTE — the baked HERE cycle time
    for that vehicle profile, `route_analysis()`'s `trips_per_day` — so the vehicles
    needed are movements/day ÷ that figure, rounded UP. That figure rides along here as
    `trips_per_vehicle_day`; it is None where the route is not baked for that vehicle,
    and the map must show "not baked" rather than a fleet size.

    Approved only. Never actuals — those stay off the public map.
    """
    if unit not in conversions.UNITS:
        raise HTTPException(400, f"unit must be one of {conversions.UNITS}")
    factors = conversions.load_factors()
    wd = _working_days(factors)          # 15 Sep: shared with the two forecast feeds
    vs = factors.get("vehicles", {}) or {}
    # 11 Oct 2026: one rule for the fallback — the Look-ahead's (it was a copy of it here,
    # with its own literal 18 t, the payload of a vehicle the seed no longer carries)
    fb_payload, fb_name = derived.payload_for(None, factors)
    rows = db.query(
        "SELECT * FROM forecasts WHERE tenant_id = ? AND status = 'Approved' "
        "AND month_index = ? ORDER BY route_id, discipline, section_id",
        (db.current_tenant(), int(month)))
    # one route_analysis() per (route, vehicle) rather than per line
    _tpv_cache = {}

    def trips_per_vehicle_day(route_id, vehicle):
        key = (route_id, vehicle)
        if key not in _tpv_cache:
            tpv = None
            try:
                res = network.route_analysis(route_id, profiles=[vehicle] if vehicle else None)
                for row in res.get("rows", []):
                    if row.get("alt_index") == 0 and (not vehicle or row.get("profile") == vehicle):
                        tpv = row.get("trips_per_day")
                        break
            except Exception:
                tpv = None
            _tpv_cache[key] = tpv
        return _tpv_cache[key]

    lines = []
    for r in rows:
        v = r.get("vehicle_type")
        known = bool(v and vs.get(v) and (vs.get(v) or {}).get("payload_t"))
        payload = float(vs[v]["payload_t"]) if known else fb_payload
        t = conversions.to_tonnes(r["quantity"], r["unit"], r.get("material_type"), v, factors)
        lines.append({
            "route_id": r["route_id"], "discipline": r.get("discipline") or "",
            "section_id": r.get("section_id") or "", "ipt": r.get("ipt"),
            "material_type": r.get("material_type") or "",
            "vehicle_type": v, "unit": r["unit"],
            "qty_unit": conversions.round_for_unit(conversions.convert_row(r, unit, factors), unit),
            "qty_t": round(t, 3),
            "vehicle_loads": round(t / payload, 3) if payload else 0.0,
            "payload_t": payload, "payload_fallback": (None if known else fb_name),
            # movements one vehicle can make per day on THIS route, or None if unbaked
            "trips_per_vehicle_day": trips_per_vehicle_day(r["route_id"], v),
        })
    # 6 Oct 2026 (map redesign) — CO2e, the same figure the costlines read gives the
    # Dashboard: km x the vehicle's kg CO2e/km from factors.json, per line, for the month.
    # `co2_t` rides on each line (None where the route is not baked for that vehicle: no
    # km, no carbon, and the map says "excludes N unbaked" rather than counting zero).
    # `co2_to_date` is the same per-line figure summed over months 1..month, keyed the way
    # the map filters (route, discipline, section), so "CO2e to date" follows the sidebar
    # filters exactly as the month figures do. Approved only; never actuals.
    # 12 Oct 2026 (B2): the read is _approved_co2(); when it fails the response SAYS so in
    # `co2_error` and every co2_t is None — until today the except blanked every carbon
    # figure silently (a null factor saved on Config was one trigger) and the map showed
    # the month with no carbon and no reason.
    table, co2_error = _approved_co2(factors, 1, int(month))
    co2_by_key, to_date, unbaked_to_date = {}, {}, 0
    for (rid, disc, sec, mi), co2 in table.items():
        if mi == int(month):
            co2_by_key[(rid, disc, sec)] = co2
        if co2 is None:
            unbaked_to_date += 1
            continue
        to_date[(rid, disc, sec)] = to_date.get((rid, disc, sec), 0.0) + float(co2)
    for l in lines:
        l["co2_t"] = co2_by_key.get((l["route_id"], l["discipline"], l["section_id"]))
    co2_to_date = [{"route_id": k[0], "discipline": k[1], "section_id": k[2], "co2_t": round(v, 3)}
                   for k, v in sorted(to_date.items())]
    out = {"month": int(month), "unit": unit, "working_days": wd,
           "payload_fallback_vehicle": fb_name, "lines": lines,
           "co2_to_date": co2_to_date, "co2_to_date_unbaked_lines": unbaked_to_date}
    if co2_error:
        out["co2_error"] = co2_error
    return out


def _approved_co2(factors, from_month, to_month):
    """
    12 Oct 2026 (B2). The public map's carbon, per APPROVED line-month, from the ONE costlines
    read the Dashboard uses (km × the vehicle's kg CO2e/km ÷ 1000, both legs): a table
    {(route_id, discipline, section_id, month_index): co2_t}, co2_t None where the route is
    not baked for the line's vehicle (no km, no carbon — never a zero dressed as a figure).

    Returns (table, error). NEVER raises: on any failure the table is empty and `error` is
    a fixed sentence naming the exception's class, so the two feeds that read it
    (/api/public/month-kpis and /api/public/forecast-matrix) can set every co2_t to None
    AND carry `co2_error`, instead of a month that silently shows no carbon. `error` is
    None on the happy path and the feeds then carry no `co2_error` key at all.

    12 Oct 2026 (the review and fix pass): the exception's MESSAGE is logged here and never
    put in the feed. Both feeds sit under /api/public/, which anyone with the shared map
    password reads, and a database error's text can carry SQL fragments (a KeyError names
    internal keys).
    """
    try:
        table = {}
        for cl in costlines.lines(acc={"role": "planner"}, from_month=int(from_month),
                                  to_month=int(to_month), status="Approved", factors=factors)["lines"]:
            table[(cl["route_id"], cl["discipline"] or "", cl["section_id"] or "",
                   int(cl["month_index"]))] = cl["co2_t"]
        return table, None
    except Exception as e:                       # noqa: BLE001 — the feed must answer
        print(f"⚠️  carbon read failed (months {from_month}-{to_month}): "
              f"{e.__class__.__name__}: {str(e).strip()[:500]}")
        return {}, CO2_ERROR_SENTENCE.format(cls=e.__class__.__name__)[:200]


#: what a person reads when the carbon read fails — never the exception's own text
CO2_ERROR_SENTENCE = "The carbon figures could not be read ({cls})."


@app.get("/api/public/stockpile-timeline")
def public_stockpile_timeline(from_: int = Query(1, alias="from", ge=1, le=MONTH_COUNT),
                              to: int = Query(MONTH_COUNT, ge=1, le=MONTH_COUNT)):
    """
    2026-09-02 (§8). Per location, per month: is the stockpile over capacity at the END of
    that month, and by how much. Read from the same balance read model the Look-ahead
    uses; nothing stored, nothing new computed. Only stockpiles with a recorded capacity can
    be over, so only those appear. No week detail — the public map stays monthly.
    """
    lo, hi = min(from_, to), max(from_, to)
    out = []
    for sp in stockpiles.balances(lo, hi)["stockpiles"]:
        if sp["capacity_qty"] is None:
            continue
        months = {}
        for w in sp["weeks"]:
            months[w["month_index"]] = w      # the last week of each month wins
        out.append({
            "location_id": sp["location_id"], "name": sp["name"],
            "capacity_qty": sp["capacity_qty"], "unit": sp["capacity_unit"],
            "months": {str(m): {"balance_end": w["balance_end"], "over": w["over"],
                                "remaining": w["remaining"]}
                       for m, w in months.items()},
        })
    return {"from": lo, "to": hi, "stockpiles": out}


@app.get("/api/public/forecast-matrix")
def public_forecast_matrix(
    from_: int = Query(1, alias="from", ge=1, le=MONTH_COUNT),
    to: int = Query(MONTH_COUNT, ge=1, le=MONTH_COUNT),
    unit: str = Query("vehicles"),
    sections: int = Query(0),
):
    """
    Approved forecasts as a month-by-month grid (for the map's detail table).
    Returns a list, one entry per route, each with a {month_index: quantity} map
    in the requested unit, plus the route's material and vehicle.
    """
    if unit not in conversions.UNITS:
        raise HTTPException(400, f"unit must be one of {conversions.UNITS}")
    lo, hi = min(from_, to), max(from_, to)
    rows = db.query(
        "SELECT * FROM forecasts WHERE tenant_id = ? AND status = 'Approved' "
        "AND month_index BETWEEN ? AND ? ORDER BY route_id, month_index",
        (db.current_tenant(), lo, hi),
    )
    factors = conversions.load_factors()
    by_line = {}
    for r in rows:
        # one entry per LINE — a route carrying two disciplines is two rows in the
        # detail table, not one row with both disciplines' tonnage silently added up
        key = (r["route_id"], r.get("discipline") or "", r.get("section_id") or "")
        g = by_line.setdefault(key, {
            "route_id": r["route_id"],
            "discipline": r.get("discipline") or "",
            "section_id": r.get("section_id") or "",
            "material_type": r["material_type"],
            "material_description": r.get("material_description"),
            "vehicle_type": r["vehicle_type"],
            "monthly": {}, "total": 0.0,
        })
        v = conversions.convert_row(r, unit, factors)
        g["monthly"][str(r["month_index"])] = conversions.round_for_unit(v, unit)
        g["total"] += v
    out = list(by_line.values())
    for g in out:
        g["total"] = conversions.round_for_unit(g["total"], unit)
    out.sort(key=lambda x: x["total"], reverse=True)
    # 12 Oct 2026 (B2): carbon per line per month rides along — `co2_t` is a {month_index:
    # t CO2e} map keyed exactly as `monthly`, None where the route is not baked for the
    # line's vehicle — from the SAME costlines figure month-kpis and the Dashboard carry, so
    # the map's timeline has one call for a carbon paint and its KPI prefetch, and the route
    # drawer reads the server's figure instead of working out its own. Every other key is
    # unchanged. When the read fails, every co2_t is None and `co2_error` says why.
    table, co2_error = _approved_co2(factors, lo, hi)
    for g in out:
        g["co2_t"] = {m: table.get((g["route_id"], g["discipline"], g["section_id"], int(m)))
                      for m in g["monthly"]}
    # ⭐ 2026-09-15 — `working_days` rides along so the timeline can print a DAILY rate on
    # the route label instead of the month's total. One divisor, one source: factors.json.
    # 12 Oct 2026 (the review and fix pass): the Carbon page's planning-estimate stamp rides
    # along, so the route drawer prints it under its CO2e card from the server's own words
    res = {"unit": unit, "from": lo, "to": hi, "working_days": _working_days(factors),
           "routes": out, "carbon_stamp": carbon.SUMMARY_STAMP}
    if co2_error:
        res["co2_error"] = co2_error
    # 12 Oct 2026 (Track C review): sections=1 (the timeline asks) adds the programme's largest
    # SECTION-month of CO2e over the window, so the carbon ramp on the shared sections has stops
    # from what a section carries, not from a whole route's month. None when there is no figure.
    if sections:
        route_month = {}
        if not co2_error:
            for g in out:
                for m, c in (g.get("co2_t") or {}).items():
                    if c is not None:
                        rm = route_month.setdefault(g["route_id"], {})
                        rm[int(m)] = rm.get(int(m), 0.0) + float(c)
        try:
            res["section_co2_max"] = (None if co2_error else road_sections.section_co2_max(route_month))
        except Exception as e:                   # noqa: BLE001 — the matrix must answer
            print(f"⚠️  section carbon maximum not worked out: {e.__class__.__name__}: {str(e)[:300]}")
            res["section_co2_max"] = None
    return res


# ------------------------------------------------------------------ routing network (Phase 0)
@app.get("/api/routes/status")
def routes_status():
    return network.routes_status()


@app.get("/api/routes/summary")
def routes_summary():
    return network.summary()


@app.get("/api/routes/map-export.pdf")
def route_map_export_pdf(month: int = Query(..., ge=1, le=MONTH_COUNT), origin: Optional[str] = None,
                         dest: Optional[str] = None, discipline: Optional[str] = None, team: Optional[str] = None,
                         routes: Optional[str] = None, carbon_tool: int = 0, map_only: int = 0, request: Request = None):
    """
    14 Oct 2026 (backlog item 2, replaces the per-route sheet) — the map as it is filtered, as an A4 landscape PDF
    drawn here (basemap.py + the bulletin's route drawing), never a screenshot. STAFF ONLY (the user, 14 Oct): a valid
    code or the staff cookie (the map's iframe in the app sends the cookie); the map password's cookie gets 401.
    The filters are the public map's Route filtering (origin, dest, discipline, team: the slot id or the team's name)
    and `routes` (comma-separated ids, the Routes page's list). Options: `carbon_tool=1` adds the NH Carbon Tool
    transport rows (H3), `map_only=1` is one page with the legend inside the map (and no tables). A team code gets its
    own team's routes whatever it asks for. Approved lines only (D11). Stores nothing.
    """
    from fastapi.responses import Response       # not in every test stub; imported here
    if not _staff_request(request):
        raise HTTPException(401, "sign in — the route map export is for staff")
    ids = [x.strip() for x in (routes or "").split(",") if x.strip()] or None
    S = route_map_export.sheet(month, route_ids=ids, team=team, acc=access.current(), origin=origin, dest=dest,
                               discipline=discipline, carbon_tool=bool(carbon_tool) and not map_only,
                               map_only=bool(map_only))
    try:
        data = export.build_route_map_pdf(S)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    y, m = weeks._month_of(month)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="route-map-{y}-{m:02d}{"-map" if map_only else ""}.pdf"',
                             "Cache-Control": "no-store"})


@app.get("/api/public/route-alternatives")
def public_route_alternatives(profile: Optional[str] = None):
    """Every non-primary baked option, for the public map's grey underlay.

    A SEPARATE endpoint from /api/public/map-data on purpose — see the docstring
    on network.route_alternatives_geojson() for the five things that walk that
    FeatureCollection and would be corrupted by alternatives appearing in it."""
    return network.route_alternatives_geojson(profile)


@app.get("/api/routes/geojson")
def routes_geojson(profile: str = network.DEFAULT_PROFILE,
                   leg: str = "loaded", alt_index: int = 0):
    """
    Map source. A route holds several geometries per profile after Step B (laden and
    unladen legs, each with HERE alternatives), so the caller picks which one to draw.
    """
    return network.routes_geojson(profile, leg=leg, alt_index=alt_index)


@app.get("/api/routes/{route_id}/geometries")
def route_geometries(route_id: str, profile: Optional[str] = None,
                     leg: Optional[str] = None):
    """
    Every cached geometry for one route, one feature per (profile, leg, alternative).
    Used to draw a selected route's alternatives alongside the chosen line.
    """
    return network.route_geometries(route_id, profile=profile, leg=leg)


@app.post("/api/admin/routes/{route_id}/promote-alt")
def promote_alt(route_id: str, profile: str = network.DEFAULT_PROFILE,
                alt_index: int = Query(..., ge=1, le=10),
                leg: str = "loaded", token: Optional[str] = None):
    """
    Make one of HERE's alternatives the primary route for this vehicle and direction —
    a planner overruling the router's ranking. Swaps with the current primary, which
    stays available. Re-baking the route restores HERE's own ordering.
    """
    _check_admin(token)
    if leg not in network.LEGS:
        raise HTTPException(400, f"leg must be one of {list(network.LEGS)}")
    return network.promote_alternative(route_id, profile, alt_index, leg=leg)


@app.get("/api/routes/{route_id}/analysis")
def route_analysis(route_id: str, profile: Optional[str] = None):
    """
    Haul-cycle analysis for one route: cycle time, trips/day, tonnes and CO2 per vehicle
    profile x alternative. Derived from cached geometry plus factors.json planning
    constants — no HERE calls, so it is cheap to open per row.
    """
    return network.route_analysis(route_id, profiles=[profile] if profile else None)


@app.get("/api/public/whoami")
def public_whoami(request: Request = None):
    """
    What the gate makes of this caller, for the public map's view flag (map review §1,
    option A — one file, two views). Under the existing /api/public/ prefix, so a visitor
    with no credential never reaches it: the gate's 401 comes first.

        level        "staff"  a valid X-Access-Code, or a staff gate cookie (the app's
                              iframe sends the cookie and no header)
                     "map"    the shared map password's cookie
                     null     nothing recognised (only with MAP_GATE=off, which lets the
                              call through at all)
        team_label   the team's NAME as a person reads it, when the header carries a team
                     code; null for a planner, an admin, a cookie-only staff caller and the
                     map. Never a code and never a team id: a slot the tenant has not named
                     reads "<team word> <n>", the way the app prints it.
    """
    acc = access.current()
    cookies = getattr(request, "cookies", None) or {}
    level = gate.LEVEL_STAFF if acc else gate.verify(cookies.get(gate.COOKIE))
    team = None
    if acc and acc.get("ipt"):
        team = acc.get("label") or ""
        if not team or access.canonical_ipt(team) == acc["ipt"]:
            word = (config.tenant_settings(conversions).get("team_label") or "Team").strip()
            team = f"{word} {acc['ipt'][3:]}"
    return {"level": level, "team_label": team}


@app.get("/api/public/map-data")
def public_map_data(profile: Optional[str] = None):
    """
    Everything the public route map draws: route lines both directions, plus location
    markers. Replaces the 4 MB static map/data/a1_data.js.

    Unbaked routes are omitted rather than drawn as straight lines. On the admin map a
    dashed straight line usefully says 'HERE could not route this'; on a public map it
    would just look like a road that isn't there.
    """
    return network.public_map_data(profile=profile)


@app.get("/api/public/road-load")
def public_road_load(month: int = Query(..., ge=1, le=MONTH_COUNT), leg: str = Query("loaded")):
    """
    12 Oct 2026 (public map review §2.2d). The month's approved volume per SHARED road
    section: one entry per run of road two or more routes have in common, with two-way
    movements a day (one load = one two-way movement, the routes' Approved trips in the
    month ÷ working days, summed over the routes that share the run), vehicles, the
    month's CO2e share by length, the routes and their team names, and the run's
    polyline. The loaded leg by default; leg=return serves the same loads running back
    empty, separately and never added. Behind the map gate like the rest of /api/public/.

    Working days come from _working_days(), the one reader of that figure.
    """
    if leg not in road_sections.LEGS:
        raise HTTPException(400, road_sections.leg_error())
    factors = conversions.load_factors()
    return road_sections.road_load(int(month), factors=factors,
                                   working_days=_working_days(factors), leg=leg)


@app.post("/api/admin/road-sections/rebuild")
def road_sections_rebuild(token: Optional[str] = None):
    """Rebuild the shared-section index from the stored geometry. No external call."""
    _check_admin(token)
    return road_sections.rebuild()


@app.get("/api/admin/road-sections/status")
def road_sections_status(token: Optional[str] = None):
    """Counts: routes indexed, runs, vertices shared — per leg — and whether the stored index is stale."""
    _check_admin(token)
    return road_sections.status()


@app.get("/api/admin/diagnostics/road-sections")
def diagnostics_road_sections(top: int = Query(10, ge=1, le=100), leg: str = Query("loaded"),
                              token: Optional[str] = None):
    """Read-only: the status and the longest stored runs with their route sets."""
    _check_admin(token)
    if leg not in road_sections.LEGS:
        raise HTTPException(400, road_sections.leg_error())
    return road_sections.diagnostics(top=int(top), leg=leg)


@app.get("/api/public/limits")
def public_limits(bbox: Optional[str] = None):
    """
    13 Oct 2026. Lorry limits (weight, height, width, axle weight) in the tenant's extent, from
    OpenStreetMap and HERE (limits.py), as GeoJSON: each with its value, the sign's legend, the
    road's name, "except for access" where tagged, the source and fetch date, and `breaches`,
    the routes whose baked vehicle is over it (from the stored check). Advisory, and the
    collection says so. Behind the map gate like the rest of /api/public/. `bbox`
    ('w,s,e,n') narrows it; without it, the tenant's extent.
    """
    box = None
    if bbox:
        box = restrictions.parse_bbox(bbox)
        if box is None:
            raise HTTPException(400, "bbox must be 'west,south,east,north' in degrees")
    return limits.feature_collection(box)


@app.get("/api/routes/{route_id}/limits")
def route_limits(route_id: str):
    """13 Oct 2026. The stored lorry-limits check for one route (every baked vehicle and leg)."""
    _require_access()
    st = limits.stored_checks([route_id]).get(route_id) or {"hits": [], "checked_at": None, "status": None}
    return dict(st, route_id=route_id)


@app.post("/api/admin/limits/import")
def limits_import(source: str = "osm", sync: int = 0, token: Optional[str] = None):
    """
    13 Oct 2026. Import lorry limits for the tenant's extent from `source` = osm | here, in
    a background thread, then re-check every route. Returns the import state at once
    (`sync=1` waits). Any failed tile or call replaces NOTHING. HERE: read
    /api/admin/diagnostics/limits?source=here&probe=true first — that path is unverified.
    """
    _check_admin(token)
    if source not in limits.SOURCES:
        raise HTTPException(400, f"source must be one of {sorted(limits.SOURCES)}")
    return limits.import_async(source, sync=bool(sync))


@app.get("/api/admin/limits/status")
def limits_status(token: Optional[str] = None):
    """The running or last import, and what is stored per source and kind."""
    _check_admin(token)
    d = limits.diagnostics(probe=False)
    return {"import": d["import"], "stored": d["stored"], "extent": d["extent"]}


@app.post("/api/admin/limits/recheck")
def limits_recheck(token: Optional[str] = None):
    """Re-check every route against the stored limits (no external call)."""
    _check_admin(token)
    return limits.store_checks()


@app.get("/api/admin/diagnostics/limits")
def diagnostics_limits(source: str = "osm", probe: bool = False, token: Optional[str] = None):
    """
    What the limits import would ask for, what is stored, and with probe=true one small live
    read: OSM = a ~10 km box at the extent's centre through Overpass; HERE = one level-12 tile
    of TRUCK_RESTR_FC4 + ROAD_GEOM_FC4 with the raw answer (key redacted) and what parsed.
    """
    _check_admin(token)
    return limits.diagnostics(source=source, probe=probe)


@app.get("/api/public/areas/shapes")
def public_area_shapes():
    """
    12 Oct 2026 (Track C review). The council polygons, their label points and licence lines,
    with no month roll-up: the map reads this ONCE to learn whether the tenant has areas and
    to draw them, then reads each month's figures with geometry=0. Behind the map gate.
    """
    return areas.shapes()


@app.get("/api/public/areas")
def public_areas(month: int = Query(..., ge=1, le=MONTH_COUNT), geometry: int = Query(1)):
    """
    12 Oct 2026 (public map review §2.2b, D27). The month per council area: two-way movements
    a day (the approved loads of the routes whose LADEN leg enters the area ÷ working days —
    one load = one two-way movement, never doubled), lorry-km inside, the month's CO2e split
    by the km inside each area (the DESNZ method), the sites inside, the polygon and the
    licence lines the map prints beside it. Behind the map gate like the rest of /api/public/.

    Working days come from _working_days(), the one reader of that figure. geometry=0 leaves
    out the polygons (the map has them from /api/public/areas/shapes).
    """
    factors = conversions.load_factors()
    return areas.area_load(int(month), working_days=_working_days(factors), geometry=bool(geometry))


@app.post("/api/admin/areas/import")
def areas_import(body: dict, replace: int = 0, token: Optional[str] = None):
    """
    Load council boundaries for the current tenant from a GeoJSON FeatureCollection (WGS84
    Polygons / MultiPolygons, each with an id, a name and a tier, and the dataset's licence
    lines in `attribution`), then re-clip every route. An area with the same id is replaced;
    replace=1 clears every area first. No external call: the file is the source.
    """
    _check_admin(token)
    try:
        return areas.import_collection(body, replace=bool(replace))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/areas")
def areas_list(token: Optional[str] = None):
    """The tenant's council areas (no geometry) with the clip counts and which routes' laden legs enter each."""
    _check_admin(token)
    return areas.list_areas()


# --------------------------------------------------------------------------- #
#  G2, 16 Sep 2026 — the overlay and the tenant package                        #
# --------------------------------------------------------------------------- #
@app.get("/api/public/alignment")
def public_alignment(request: Request):
    """
    The map's overlay package: alignment, chainage, package bands, boundaries, an
    existing railway, the opening view — plus the tenant's words (name, team_label,
    country, currency) so the map can label itself. Stored as the config row `overlay`;
    tenants without one get an empty object and the map draws no alignment.

    Same gate as the rest of /api/public/ (the map password or a staff session). The
    row can be large (a surveyed 200 km alignment is ~9 MB), so it carries an ETag and
    answers 304 to a matching If-None-Match.

    13 Oct 2026: the ETag covers everything the body carries — the overlay row's updated_at
    AND a short hash of the tenant block and the team names. Before, it was updated_at alone,
    so after a Config save (distance unit, demo notice, team label...) or a team rename a
    browser holding the old copy kept getting 304 and the map showed the old words. The 304
    path reads updated_at only, never the overlay value.
    """
    stamp = tenant_package.get_overlay_stamp()
    tenant = config.tenant_settings(conversions)
    # the tenant's names for its team slots, so the map shows "North Team", not an id
    teams = [{"id": r["id"], "label": r.get("label") or r["id"]}
             for r in taxonomy.list_ipts(active_only=False)]
    words = hashlib.sha1(json.dumps({"tenant": tenant, "teams": teams}, sort_keys=True, ensure_ascii=False,
                                    default=str).encode("utf-8")).hexdigest()[:12]
    tag = '"' + str(stamp or "none") + "-" + words + '"'
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"ETag": tag})
    row = tenant_package.get_overlay_row() if stamp else None
    doc = {}
    if row:
        try:
            doc = json.loads(row["value"])
        except Exception:
            doc = {}
    doc["tenant"] = tenant
    doc["teams"] = teams
    return Response(content=json.dumps(doc, ensure_ascii=False), media_type="application/json",
                    headers={"ETag": tag, "Cache-Control": "no-cache"})


@app.put("/api/admin/overlay")
def put_overlay(body: dict, token: Optional[str] = None):
    """Store (or replace) the tenant's map overlay. See map/overlay.js for the shape."""
    _check_admin(token)
    res = tenant_package.set_overlay(body, by="admin")
    if not res["ok"]:
        raise HTTPException(400, "; ".join(res["problems"]))
    return {"ok": True}


@app.get("/api/admin/tenant/status")
def tenant_status(token: Optional[str] = None):
    """Is this tenant empty (importable), and how many rows does each table hold?"""
    _check_admin(token)
    counts = {}
    for t in tenant_package.ORDER:
        try:
            counts[t] = db.query(f"SELECT COUNT(*) AS n FROM {t} WHERE tenant_id = ?",
                                 (db.current_tenant(),))[0]["n"]
        except Exception:
            counts[t] = None
    return {"tenant_id": db.current_tenant(), "empty": tenant_package.is_empty(),
            "counts": counts, "tenant": config.tenant_settings(conversions)}


@app.get("/api/admin/tenant/export")
def tenant_export(token: Optional[str] = None):
    """
    The whole current tenant as one JSON document — every tenanted table including
    baked geometry, and the config rows (factors, costing, overlay). Download it, keep
    it, import it into an empty tenant elsewhere. tenant_package.py has the format.
    """
    _check_admin(token)
    pkg = tenant_package.export_tenant(app_version="modus-g2")
    name = f"modus-tenant-{db.current_tenant()}-{pkg['exported_at'][:10]}.json"
    return Response(content=json.dumps(pkg, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/admin/tenant/import")
def tenant_import(body: dict, replace: int = 0, token: Optional[str] = None):
    """
    Import a package into the CURRENT tenant. Refused unless the tenant is empty —
    pass replace=1 to wipe it first. Whole-tenant, not a merge. Baked geometry in the
    package is kept, so the routes need no re-bake; routes without geometry read
    UNBAKED until the network is baked here.
    """
    _check_admin(token)
    try:
        res = tenant_package.import_tenant(body, replace=bool(replace))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        # 29 Sep 2026: the first import on Render died inside the transaction (a
        # Postgres type mismatch) and the caller saw a bare "Internal Server Error";
        # the reason was only in the Render log. The import is rolled back whole, so
        # name the error here — the admin who holds the token is the one who has to
        # fix the package or the schema.
        raise HTTPException(500, f"import failed and was rolled back: {type(e).__name__}: {e}")
    config.invalidate()
    return res


@app.get("/api/routes/analysis-batch")
def routes_analysis_batch(route_ids: Optional[str] = None, profile: Optional[str] = None):
    """
    Primary-option haul-cycle figures for many routes at once, keyed route_id -> profile.

    This exists so the dashboard can stop computing its own cycle time. It had
    `round / 45 km/h + (12 + 8) / 60` against the backend's real HERE leg durations and
    per-vehicle turnaround, and the two disagreed by up to 47% on speed alone and 125% on
    turnaround for an Artic Flatbed. Converging them by making the dashboard call the
    backend is the point; a per-route request for every route on screen was the only
    reason not to, and this removes it.

    Only alt_index 0 is returned — the primary route, which is what a forecast's distance
    follows. Routes with no baked geometry are simply absent from the result rather than
    present with zeros; a caller must show that as 'not baked', not as nothing moving.
    """
    ids = [r.strip() for r in (route_ids or "").split(",") if r.strip()]
    if not ids:
        ids = [r["id"] for r in db.query(
            "SELECT id FROM routes WHERE tenant_id = ? ORDER BY id",
            (db.current_tenant(),))]

    profs = [profile] if profile else None
    out, missing = {}, []
    for rid in ids:
        res = network.route_analysis(rid, profiles=profs)
        rows = [r for r in res.get("rows", []) if r.get("alt_index") == 0]
        if not rows:
            missing.append(rid)
            continue
        out[rid] = {r["profile"]: r for r in rows}

    return {"analysis": out, "not_baked": missing,
            "planning": conversions.load_factors().get("planning", {}),
            "count": len(out)}


@app.get("/api/locations/geojson")
def locations_geojson():
    return network.locations_geojson()


@app.post("/api/admin/bake-routes")
def bake_routes(profile: str = network.DEFAULT_PROFILE,
                limit: int = Query(25, ge=1, le=60),
                legs: Optional[str] = None,
                token: Optional[str] = None):
    """
    Compute + cache HERE truck geometry for a batch of routes. Call repeatedly
    until 'remaining' is 0. Protected by ADMIN_TOKEN — and refused when that env var is
    unset (12 Oct 2026, C11): a bake spends HERE calls, so it is never open.

    'limit' counts legs rather than routes — each leg is one HERE call. Pass
    legs='loaded' to skip the unladen return and halve the call count.
    """
    _check_admin(token)
    want = tuple(l.strip() for l in legs.split(",") if l.strip() in network.LEGS) if legs else network.LEGS
    return network.bake_batch(profile=profile, limit=limit, legs=want or network.LEGS)


@app.post("/api/admin/clear-geometry")
def clear_geometry(profile: Optional[str] = None, leg: Optional[str] = None,
                   route_id: Optional[str] = None, token: Optional[str] = None):
    """
    Clear cached geometry (a profile and/or leg and/or route, or all) for re-baking.

    ⚠️ `route_id` narrows this to one route and is what makes "drop this vehicle from
    this route" possible; without it the only delete was network-wide. Every parameter
    is optional and omitting all three still means ALL geometry for the tenant, which is
    what "Clear all routes" wants -- so a caller that means one route must say so.
    """
    _check_admin(token)
    network.clear_geometry(profile, leg=leg, route_id=route_id)
    return {"status": "cleared", "profile": profile or "all", "leg": leg or "all",
            "route_id": route_id or "all"}


class LocationIn(BaseModel):
    name: str
    role: str = "both"                     # 'origin' | 'destination' | 'both'
    materials: List[str] = []              # legacy: kept in sync with supplies
    supplies: List[str] = []               # categories an origin/both can provide
    receives: List[str] = []               # categories a destination/both can accept
    lat: float
    lon: float
    loc_type: Optional[str] = None
    # access/egress gate — the point HERE actually routes to when it differs from the
    # marker. Null (or omitted) means no gate surveyed yet; routing uses lat/lon.
    gate_lat: Optional[float] = None
    gate_lon: Optional[float] = None
    # operator / free-text detail. Salvaged out of a1_data.js, where the quarry operator
    # was the only copy anywhere, and editable in the Locations panel since.
    vendor: Optional[str] = None
    detail: Optional[str] = None


def _fields_set(model):
    """Which fields the client actually sent (pydantic v1 and v2 spell this differently)."""
    return getattr(model, "model_fields_set", None) or getattr(model, "__fields_set__", set())


def _check_admin(token):
    """
    Every /api/admin/* call and every write to master data. 403 unless the supplied token
    matches ADMIN_TOKEN.

    12 Oct 2026 — C11 closed: with NO ADMIN_TOKEN configured this REFUSES. Until then the
    check only ran when a token was configured, so an unset token opened every admin
    endpoint — the one place the product failed open while gate.py failed closed on an
    unset MAP_PASSWORD.
    A deployment whose ADMIN_TOKEN has gone missing now loses its admin surface, never its
    data — the same choice access.resolve() makes for the access codes.
    """
    # G3 (14 Oct 2026, D53): a signed-in ADMIN LOGIN passes without the token, so a Config save is
    # attributed to a person. Never the shared ADMIN_CODE (via "code"): that boundary is unchanged.
    acc = access.current()
    if acc and acc.get("via") == "login" and acc.get("role") == "admin":
        return
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()
    if not admin_token:
        raise HTTPException(403, "admin access is not configured — set ADMIN_TOKEN")
    # bytes, not str (12 Oct 2026): hmac.compare_digest raises TypeError on a str holding a
    # non-ASCII character, so ?token=é answered 500 instead of 403
    if not token or not hmac.compare_digest(admin_token.encode("utf-8"), str(token).strip().encode("utf-8")):
        raise HTTPException(403, "bad or missing admin token")


@app.post("/api/admin/locations")
def create_location(body: LocationIn, token: Optional[str] = None):
    _check_admin(token)
    return network.create_location(body.name, body.role, body.materials, body.lat, body.lon,
                                   body.loc_type, supplies=body.supplies, receives=body.receives,
                                   gate_lat=body.gate_lat, gate_lon=body.gate_lon,
                                   vendor=body.vendor, detail=body.detail)


@app.put("/api/admin/locations/{location_id}")
def update_location(location_id: str, body: LocationIn, token: Optional[str] = None):
    _check_admin(token)
    # only touch the gate if the client mentioned it — otherwise a caller that doesn't
    # know about gates (or an older client) would silently wipe one that was set
    gate_given = bool({"gate_lat", "gate_lon"} & set(_fields_set(body)))
    meta_given = bool({"vendor", "detail"} & set(_fields_set(body)))
    return network.update_location(location_id, body.name, body.role, body.materials,
                                   body.lat, body.lon, body.loc_type,
                                   supplies=body.supplies, receives=body.receives,
                                   gate_lat=body.gate_lat, gate_lon=body.gate_lon,
                                   gate_given=gate_given,
                                   vendor=body.vendor, detail=body.detail,
                                   meta_given=meta_given)


@app.delete("/api/admin/locations/{location_id}")
def delete_location(location_id: str, token: Optional[str] = None):
    _check_admin(token)
    return network.delete_location(location_id)


# ------------------------------------------------------------------ Phase 5a: gates
#
# The gate endpoints are admin-only for the same reason Locations and Zones are: a gate
# moves where HERE routes to, so writing one invalidates cached geometry and spends
# calls on the re-bake. ⚠️ ADMIN_TOKEN is set on Render (verified 2026-08-28), but the
# LOGINS dict in the frontend is still client-side with plaintext passwords, so this is
# an API boundary and not yet a user-permission one. Phase 6.
class GateIn(BaseModel):
    location_id: str
    name: str
    lat: float
    lon: float
    direction: str = "both"                 # 'access' | 'egress' | 'both'
    # B3: induction is per gate and applies to whatever arrives. No per-vehicle
    # override — offered and declined; the fix if it ever matters is a nullable
    # column plus a COALESCE, not a rebuild.
    safety_minutes: Optional[float] = None
    # B5(c): the FLAT fallback, used only where no drawn haul road already carries
    # these minutes in route_geometry.duration_hr. See network.INTERNAL_TRAVEL_SOURCES.
    internal_travel_minutes: Optional[float] = None
    is_default: bool = False
    active: bool = True
    note: Optional[str] = None
    gate_id: Optional[str] = None


class GatePatch(BaseModel):
    name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    direction: Optional[str] = None
    safety_minutes: Optional[float] = None
    internal_travel_minutes: Optional[float] = None
    is_default: Optional[bool] = None
    active: Optional[bool] = None
    note: Optional[str] = None


class RouteGatesIn(BaseModel):
    origin_gate_id: Optional[str] = None
    dest_gate_id: Optional[str] = None


@app.get("/api/gates")
def list_gates(location_id: Optional[str] = None, include_inactive: bool = True):
    """Readable without a token — the map and the route panels need it, and a gate
    coordinate is no more sensitive than the location marker already published."""
    return {"gates": gates.list_gates(location_id, include_inactive=include_inactive)}


@app.get("/api/gates/arrivals")
def gate_arrivals_month(month: Optional[int] = None):
    """
    11 Oct 2026 — lorries a day at each gate for one month, every team summed: laden arrivals at the
    destination's entry gate plus empty arrivals (coming to load) at the origin's entry gate, approved
    lines only, ÷ working days; the average gap is the shift's minutes ÷ arrivals, flagged red only
    when it is shorter than the gate's typed check-in. Any signed-in code; a team code gets the totals
    and the team names, never another team's figure (gate_arrivals.arrivals masks per_team from acc).
    Reads only. No hourly peak exists in the data, so every figure says "if arrivals are spread evenly".
    """
    acc = _require_access()
    if month is None:
        import datetime as _dt
        month = max(1, min(MONTH_COUNT, weeks.month_index_of(_dt.date.today())))
    if not (1 <= int(month) <= MONTH_COUNT):
        raise HTTPException(400, f"month must be 1..{MONTH_COUNT}")
    factors = conversions.load_factors()
    return gate_arrivals.arrivals(int(month), acc, factors=factors, working_days=_working_days(factors))


@app.post("/api/admin/gates")
def create_gate(body: GateIn, token: Optional[str] = None):
    _check_admin(token)
    return gates.create_gate(body.location_id, body.name, body.lat, body.lon,
                             direction=body.direction,
                             safety_minutes=body.safety_minutes,
                             internal_travel_minutes=body.internal_travel_minutes,
                             is_default=body.is_default, active=body.active,
                             note=body.note, gate_id=body.gate_id)


@app.patch("/api/admin/gates/{gate_id}")
def update_gate(gate_id: str, body: GatePatch, token: Optional[str] = None):
    _check_admin(token)
    # only the fields the client actually sent are written. A PATCH that toggles
    # `active` must not blank a safety time it knows nothing about — the same trap the
    # Locations PUT hit when a node drag started wiping salvaged vendor names.
    sent = set(_fields_set(body))
    fields = {k: getattr(body, k) for k in sent}
    out = gates.update_gate(gate_id, **fields)
    if not out.get("error"):
        # moving a gate moves the point HERE routed to, so any cached geometry on a
        # route that uses it is stale. The re-bake is NOT run here — its cost is quoted
        # in the UI first, as zone and haul-road writes already do.
        moved = bool({"lat", "lon", "direction", "active"} & sent)
        out["rebake_needed"] = moved
        out["routes_affected"] = gates.routes_using(gate_id) if moved else []
    return out


@app.delete("/api/admin/gates/{gate_id}")
def delete_gate(gate_id: str, token: Optional[str] = None):
    _check_admin(token)
    return gates.delete_gate(gate_id)


@app.put("/api/admin/routes/{route_id}/gates")
def set_route_gates(route_id: str, body: RouteGatesIn, token: Optional[str] = None):
    _check_admin(token)
    sent = set(_fields_set(body))
    return gates.set_route_gates(route_id,
                                 origin_gate_id=body.origin_gate_id,
                                 dest_gate_id=body.dest_gate_id,
                                 origin_given="origin_gate_id" in sent,
                                 dest_given="dest_gate_id" in sent)


class RouteIn(BaseModel):
    origin_id: str
    dest_id: str
    material_category: Optional[str] = None
    route_id: Optional[str] = None          # optional manual id; auto R00n if blank
    ipt: Optional[str] = None


@app.post("/api/admin/routes")
def create_route(body: RouteIn, token: Optional[str] = None):
    _check_admin(token)
    return network.create_route(body.origin_id, body.dest_id, body.material_category,
                                route_id=body.route_id, ipt=body.ipt)


class RoutePatch(BaseModel):
    origin_id: Optional[str] = None
    dest_id: Optional[str] = None
    material_category: Optional[str] = None
    ipt: Optional[str] = None


@app.get("/api/admin/routes/{route_id}/impact")
def route_impact(route_id: str, token: Optional[str] = None):
    """What an endpoint edit would touch — forecasts, weeks, baked profiles, haul
    roads. Read before the edit so the UI can say it."""
    _check_admin(token)
    if not db.query("SELECT id FROM routes WHERE tenant_id = ? AND id = ?",
                    (db.current_tenant(), route_id)):
        raise HTTPException(404, "route not found")
    return network.route_edit_impact(route_id)


@app.patch("/api/admin/routes/{route_id}")
def update_route(route_id: str, body: RoutePatch, token: Optional[str] = None):
    """
    2.5b: edit a route in place. Only the fields the client actually sent are written.
    Moving an endpoint clears the baked geometry (profiles returned for the re-bake)
    and that end's gate selection; forecasts, weeks and haul links are left alone.
    """
    _check_admin(token)
    sent = set(_fields_set(body))
    res = network.update_route(route_id, origin_id=body.origin_id, dest_id=body.dest_id,
                               material_category=body.material_category, ipt=body.ipt,
                               given=sent)
    if res.get("error"):
        raise HTTPException(404 if res["error"] == "route not found" else 400, res["error"])
    return res


class RoutePlanning(BaseModel):
    max_vehicles_per_day: Optional[int] = None
    rate_eur_per_load: Optional[float] = None
    rate_eur_per_t: Optional[float] = None
    rate_eur_per_km: Optional[float] = None
    km_basis: Optional[str] = None


@app.put("/api/admin/routes/{route_id}/planning")
def set_route_planning(route_id: str, body: RoutePlanning, token: Optional[str] = None):
    """
    Look-ahead v2 slices 3-5: the typed planning cap and the three contract rates on one
    route, plus the km basis they use. Only sent fields are written; a null clears.
    Never seeded. The cap is a flag on the Look-ahead, never a block.
    """
    _check_admin(token)
    sent = set(_fields_set(body))
    res = network.set_route_planning(route_id, sent, **{k: getattr(body, k) for k in sent})
    if res.get("error"):
        raise HTTPException(404 if res["error"] == "route not found" else 400, res["error"])
    return res


@app.delete("/api/admin/routes/{route_id}")
def delete_route(route_id: str, token: Optional[str] = None):
    _check_admin(token)
    return network.delete_route(route_id)


@app.post("/api/admin/clear-routes")
def clear_routes(token: Optional[str] = None):
    _check_admin(token)
    return network.clear_routes()


# ------------------------------------------------------------------ diagnostics
@app.get("/api/admin/diagnostics/fuel-index")
def diagnostics_fuel_index(probe: bool = False, country: Optional[str] = None,
                           token: Optional[str] = None):
    """
    H1 (29 Sep 2026). What the diesel-index provider for the tenant's country (or
    `country=`) would fetch, and with probe=true what the live source actually returns:
    for GB the gov.uk content API document → the resolved CSV URL → the CSV's head and
    tail → the parsed row; for EU-27 the EuroOilWatch payload's bulletin date and label.
    ⚠️ gov.uk is not reachable from the build sandbox, so the DESNZ path has only ever
    run against fixtures — this endpoint is how the first real run is seen. Runs inline
    (15 s timeout), writes NOTHING: the stored row is untouched whatever comes back.
    """
    _check_admin(token)
    s = costing.settings(use_cache=False)
    c = fuel.norm_country(country or s["fuel"].get("country"))
    out = {"country": c, "no_country": c == fuel.NO_COUNTRY,
           "provider": fuel.provider_public(c), "stored": fuel.state(c),
           "urls": ([fuel.DESNZ_CONTENT_API] if (fuel.provider_for(c) or {}).get("key") == "desnz"
                    else [fuel.FEED_URL] if fuel.provider_for(c) else []),
           "probe": None,
           "unverified": ["gov.uk (DESNZ) has never been called from the build sandbox — "
                          "the CSV column names are matched by header TEXT and may need adjusting "
                          "after the first real run; read `probe.detail.csv_head`"]}
    if not probe:
        return out
    if not fuel.provider_for(c):
        out["probe"] = {"skipped": "no automatic series for this country — typed only"}
        return out
    try:
        res = fuel.fetch_and_parse(c, timeout=15)
        out["probe"] = {"ok": not res.get("error"), "parsed": {k: v for k, v in res.items() if k != "detail"},
                        "detail": res.get("detail")}
    except Exception as e:
        out["probe"] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}
    return out


@app.get("/api/admin/diagnostics/factors")
def diagnostics_factors(token: Optional[str] = None):
    """
    How each vehicle profile resolves against factors.json. Read this first when the
    analysis table reports the same payload or CO2 for different vehicles — a profile
    with in_factors=false has fallen through to _default and every such profile will
    report identical figures.
    """
    _check_admin(token)
    return network.factors_diagnostics()


@app.get("/api/admin/diagnostics/route/{route_id}")
def diagnostics_route(route_id: str, profile: str = network.DEFAULT_PROFILE,
                      probe: bool = False, token: Optional[str] = None):
    """
    What is cached for a route, which coordinates it routes to (gate or marker), and
    optionally a live HERE call showing exactly what was sent and returned.

    probe=true spends two HERE requests. It is the only way to see whether HERE
    declined an alternatives request or whether truck dimensions reached it at all.
    """
    _check_admin(token)
    return network.route_diagnostics(route_id, profile, probe=probe)


@app.get("/api/admin/diagnostics/departure/{route_id}")
def diagnostics_departure(route_id: str, profile: str = network.DEFAULT_PROFILE,
                          leg: str = "loaded", times: Optional[str] = None,
                          token: Optional[str] = None):
    """
    Does HERE's answer for this leg depend on a departure time we never send?

    Replays the identical request across several `departureTime` values, bracketed by two
    controls that send none at all, and reports distance, duration, section count and a
    geometry FINGERPRINT for each — because two different roads can come back the same
    length, and distance alone would read that as "no change".

    `times` is an optional comma-separated list of ISO-8601 timestamps (or the literal
    `any`). Omit it and four default times on the next weekday are used; the response says
    which timezone source produced them.

    ⚠️ Costs one HERE request per time plus two controls — six by default. Writes nothing,
    and does NOT pin anything: no bake sends a departureTime. Read `experiment.reads_as`
    last, not first.
    """
    _check_admin(token)
    want = [t.strip() for t in times.split(",") if t.strip()] if times else None
    return network.departure_diagnostics(route_id, profile=profile, leg=leg, times=want)


@app.get("/api/admin/diagnostics/road-class/{route_id}")
def diagnostics_road_class(route_id: str, profile: str = network.DEFAULT_PROFILE, leg: str = "loaded",
                           token: Optional[str] = None):
    """
    13 Oct 2026 (bundle C, decision 2a). Does HERE tell us which road class a route's miles are on?
    One HERE request for this leg with `spans=functionalClass,routeNumbers,length`; the answer is
    reported as it came back (or HERE's error if it refuses a span name). Nothing is stored or read
    from it: the bulletin compares with all of a district's roads until this has been run on the
    deployment and its answer looked at. ⚠️ Costs one HERE request.
    """
    _check_admin(token)
    return network.road_class_diagnostics(route_id, profile=profile, leg=leg)


@app.get("/api/admin/diagnostics/compare/{route_id}")
def diagnostics_compare(route_id: str, probe: bool = False, token: Optional[str] = None):
    """
    Route one pair for every vehicle profile and report whether anything differs.
    Distinguishes 'the network offers no alternative' from 'the vehicle never reached
    HERE'. probe=true spends one HERE request per profile.
    """
    _check_admin(token)
    return network.compare_profiles(route_id, probe=probe)


@app.post("/api/admin/bake-route")
def bake_route(route_id: str, profile: str = network.DEFAULT_PROFILE,
               legs: Optional[str] = None, token: Optional[str] = None):
    """Bake one route. Both legs by default; pass legs='loaded' for the outbound only."""
    _check_admin(token)
    want = tuple(l.strip() for l in legs.split(",") if l.strip() in network.LEGS) if legs else None
    return network.bake_route(route_id, profile, legs=want)


@app.get("/api/admin/diagnostics/zones")
def diagnostics_zones(route_id: Optional[str] = None,
                      profile: str = network.DEFAULT_PROFILE,
                      probe: bool = False, token: Optional[str] = None):
    """
    What the zone layer sends HERE, and with probe=true what HERE does with it.

    Read this before believing anything about how many avoid[areas] the API tolerates —
    that limit is not enforced in this codebase and has never been checked against the
    live service. probe=true spends two HERE requests: the same route with and without
    the current zone set, so a difference is attributable.
    """
    _check_admin(token)
    return network.zones_diagnostics(route_id=route_id, profile=profile, probe=probe)


# ------------------------------------------------------------------ zones (Phase 3)
class ZoneIn(BaseModel):
    """
    A drawn zone. Geometry is a GeoJSON *geometry* (Polygon or LineString), not a
    Feature — Mapbox Draw hands back Features, so the client sends feature.geometry.

    affects_routing is the whole point of merging Phases 3 and 3.5 into one table:
    TRUE and the bbox goes to HERE and baked routes crossing it are re-routed; FALSE and
    it is drawn on the maps and the router never hears about it.
    """
    name: str
    geometry: dict
    kind: Optional[str] = "other"
    affects_routing: bool = True
    starts_on: Optional[str] = None          # 'YYYY-MM-DD' or null for open-ended
    ends_on: Optional[str] = None
    note: Optional[str] = None
    active: bool = True
    # Phase 4, haul roads only. speed_kph null means "no assigned speed" and leaves
    # HERE's own timing alone — it is NOT a default speed. haul_mode null means the
    # module default, which is 'splice'; see haul.py for why that is the safe one.
    speed_kph: Optional[float] = None
    haul_mode: Optional[str] = None


def _zone_write_result(zone, inval):
    """Shape shared by create/update/delete: the zone, plus what it just invalidated."""
    return {"zone": zone, "invalidated": inval,
            "rebake_required": inval.get("leg_count", 0) > 0,
            "here_calls": inval.get("here_calls", 0)}


@app.get("/api/zones")
def list_zones(on: Optional[str] = None, include_inactive: bool = True):
    """
    Every zone, for the admin table and both maps.

    Deliberately NOT under /api/admin: the public map draws disruptions and has no
    token. Nothing here is sensitive — a zone is a shape, a name and a date range.
    Pass on='YYYY-MM-DD' to get only those in force that day, which is how the public
    map's timeline filters them.
    """
    return {"zones": zones.list_zones(include_inactive=include_inactive, on=on),
            "summary": zones.summary(),
            "kinds": list(zones.KINDS),
            # Phase 4: the zone table needs to show which routes use each haul road, and
            # a haul road attached to nothing is the commonest reason one "does nothing"
            "haul_modes": list(haul.MODES),
            "haul_default_mode": haul.DEFAULT_MODE,
            "haul_kind": zones.HAUL_KIND,
            "haul_links": haul.link_counts()}


@app.get("/api/zones/{zone_id}")
def get_zone(zone_id: str):
    z = zones.get_zone(zone_id)
    if not z:
        raise HTTPException(404, "zone not found")
    return z


@app.post("/api/admin/zones")
def create_zone(body: ZoneIn, token: Optional[str] = None):
    """
    Create a zone and immediately clear the baked geometry it invalidates.

    Clearing is not the same as re-baking. This endpoint does NOT call HERE: it reports
    how many legs must be re-routed and the client drives /api/admin/bake-routes until
    'remaining' is 0, the same loop the bulk-bake button already uses. Doing the HERE
    calls inline would block one HTTP request on dozens of round trips and time out on
    Render long before it finished.
    """
    _check_admin(token)
    z = zones.create_zone(
        body.name, body.geometry, kind=body.kind, affects_routing=body.affects_routing,
        starts_on=body.starts_on, ends_on=body.ends_on, note=body.note, active=body.active,
        speed_kph=body.speed_kph, haul_mode=body.haul_mode)
    if z.get("error"):
        raise HTTPException(400, z["error"])
    if z["kind"] == zones.HAUL_KIND:
        # A brand-new haul road is attached to nothing, so it invalidates nothing — it
        # cannot change a route until someone puts it on one. That is the whole reason
        # attachment is explicit: drawing a road near a route does not silently re-bake
        # it. Routing zones invalidate on creation; haul roads invalidate on attach.
        return _zone_write_result(z, haul.invalidate_for_zone(z["id"]))
    # a zone that does not affect routing invalidates nothing — it is drawn, not routed
    inval = (zones.invalidate(new_geometry=z["geometry"])
             if (z["affects_routing"] and z["active"] and zones.applies_on(z))
             else zones.invalidate(dry_run=True))
    return _zone_write_result(z, inval)


@app.put("/api/admin/zones/{zone_id}")
def update_zone(zone_id: str, body: ZoneIn, token: Optional[str] = None):
    """
    Edit a zone and clear what the edit makes wrong.

    An edit is two invalidations at once — routes that now cross the new shape, and
    routes that were baked while the OLD shape was avoided. Both are passed to
    zones.invalidate(), which is why the previous geometry is read before the write.

    Only fields the client actually sent are written; see zones.update_zone().
    """
    _check_admin(token)
    before = zones.get_zone(zone_id)
    if not before:
        raise HTTPException(404, "zone not found")

    sent = set(_fields_set(body))
    fields = {k: getattr(body, k) for k in
              ("name", "geometry", "kind", "affects_routing", "starts_on", "ends_on",
               "note", "active", "speed_kph", "haul_mode") if k in sent}
    z = zones.update_zone(zone_id, **fields)
    if z.get("error"):
        raise HTTPException(400, z["error"])

    # A haul road edit is exact — see haul.invalidate_for_zone(). It covers the case
    # where a zone was a haul road and has just stopped being one, because the legs baked
    # through it still carry its id in haul_zones and are cleared on that record, not on
    # what the zone happens to be now.
    if z["kind"] == zones.HAUL_KIND or before["kind"] == zones.HAUL_KIND:
        inval = haul.invalidate_for_zone(zone_id)
        haul.refresh_origin_temp_km()
        return _zone_write_result(z, inval)

    now_routes = z["affects_routing"] and z["active"] and zones.applies_on(z)
    was_routes = (before["affects_routing"] and before["active"]
                  and zones.applies_on(before))
    inval = zones.invalidate(
        zone_id=zone_id,
        new_geometry=(z["geometry"] if now_routes else None),
        # the old shape only matters if it was actually steering the router before
        old_geometry=(before["geometry"] if was_routes else None),
    )
    return _zone_write_result(z, inval)


@app.delete("/api/admin/zones/{zone_id}")
def delete_zone(zone_id: str, token: Optional[str] = None):
    """
    Delete a zone and clear geometry that was routed around it.

    Consider deactivating instead (PUT with active=false). A deleted zone takes with it
    the record of why a past bake went the way it did; a deactivated one stops steering
    the router and stays explainable.
    """
    _check_admin(token)
    before = zones.get_zone(zone_id)
    if not before:
        raise HTTPException(404, "zone not found")

    if before["kind"] == zones.HAUL_KIND:
        # Order matters: work out what to clear while the links still exist, then drop
        # them, then delete the zone. Deleting first would leave invalidate_for_zone()
        # with nothing to find and the affected legs baked through a road that is gone.
        inval = haul.invalidate_for_zone(zone_id)
        detached = haul.clear_links_for_zone(zone_id)
        res = zones.delete_zone(zone_id)
        if res.get("error"):
            raise HTTPException(404, res["error"])
        haul.refresh_origin_temp_km()
        out = _zone_write_result({"deleted": zone_id, "was": before}, inval)
        out["detached_from_routes"] = detached
        return out

    was_routes = (before["affects_routing"] and before["active"]
                  and zones.applies_on(before))
    res = zones.delete_zone(zone_id)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    inval = zones.invalidate(
        zone_id=zone_id,
        old_geometry=(before["geometry"] if was_routes else None),
    )
    return _zone_write_result({"deleted": zone_id, "was": before}, inval)


@app.get("/api/admin/zones/{zone_id}/impact")
def zone_impact(zone_id: str, token: Optional[str] = None):
    """
    Dry run: what deleting or moving this zone would invalidate, without touching
    anything. Use it to see the HERE bill before agreeing to it.
    """
    _check_admin(token)
    z = zones.get_zone(zone_id)
    if not z:
        raise HTTPException(404, "zone not found")
    if z["kind"] == zones.HAUL_KIND:
        return {"zone": z,
                "routes_attached": haul.routes_for_zone(zone_id),
                "would_invalidate": haul.invalidate_for_zone(zone_id, dry_run=True)}
    return {"zone": z,
            "would_invalidate": zones.invalidate(
                zone_id=zone_id, new_geometry=z["geometry"],
                old_geometry=z["geometry"], dry_run=True)}


# ------------------------------------------------------- haul roads (Phase 4)
class HaulLinkIn(BaseModel):
    """Attach a haul road to a route. seq null appends to the end of the order."""
    zone_id: str
    seq: Optional[int] = None


class HaulOrderIn(BaseModel):
    """The full traversal order for one route's haul roads, loaded-leg direction."""
    zone_ids: List[str]


def _haul_write_result(route_id, inval, extra=None):
    """
    Same shape the zone writes return, so the frontend's existing re-bake loop drives
    this too. The one difference worth reading is here_calls: a spliced leg is more than
    one HERE request, and this counts the splices — see haul._here_calls_for().
    """
    out = {"route_id": route_id, "invalidated": inval,
           "rebake_required": inval.get("leg_count", 0) > 0,
           "here_calls": inval.get("here_calls", 0),
           "haul_roads": haul.links_for_route(route_id)}
    out.update(extra or {})
    return out


@app.get("/api/haul-roads")
def list_haul_roads(on: Optional[str] = None):
    """
    Haul roads and their route links, for the admin table and the public map.

    Not under /api/admin for the same reason /api/zones is not: the public map draws
    these, has no token, and a drawn road with a speed on it is not sensitive.
    """
    return {"haul_roads": zones.haul_roads(on=on, include_inactive=True,
                                           require_geometry=False),
            "links": db.query("SELECT * FROM route_haul_roads WHERE tenant_id = ? "
                              "ORDER BY route_id, seq", (db.current_tenant(),)),
            "summary": haul.summary()}


@app.get("/api/routes/{route_id}/haul-roads")
def route_haul_roads(route_id: str):
    """
    The haul roads on one route, plus the plan for each leg — entry and exit points,
    traversal direction, drawn length and the duration the assigned speed implies.

    No HERE calls. This is what the route panel shows before anything is baked, so a
    planner can see that the loaded leg enters a road at one end and the return leg at
    the other without spending a request to find out.
    """
    if not db.query("SELECT id FROM routes WHERE tenant_id = ? AND id = ?",
                    (db.current_tenant(), route_id)):
        raise HTTPException(404, "route not found")
    return haul.diagnostics(route_id=route_id, probe=False)


@app.post("/api/admin/routes/{route_id}/haul-roads")
def attach_haul_road(route_id: str, body: HaulLinkIn, token: Optional[str] = None):
    """
    Put a haul road on a route — the Phase 4 requirement that this is edited ON the
    route, not as a free-floating drawing.

    Clears the route's baked geometry, because every leg of it now routes differently.
    Does NOT call HERE: the client drives /api/admin/bake-routes afterwards, the same
    loop the zone writes use.
    """
    _check_admin(token)
    res = haul.attach(route_id, body.zone_id, seq=body.seq)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    inval = haul.invalidate_for_route(route_id)
    haul.refresh_origin_temp_km(route_id)
    return _haul_write_result(route_id, inval, {"attached": res["attached"]})


@app.delete("/api/admin/routes/{route_id}/haul-roads/{zone_id}")
def detach_haul_road(route_id: str, zone_id: str, token: Optional[str] = None):
    """Take a haul road off a route and clear the geometry baked through it."""
    _check_admin(token)
    res = haul.detach(route_id, zone_id)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    inval = haul.invalidate_for_route(route_id)
    haul.refresh_origin_temp_km(route_id)
    return _haul_write_result(route_id, inval, {"detached": res["detached"]})


@app.put("/api/admin/routes/{route_id}/haul-roads/order")
def order_haul_roads(route_id: str, body: HaulOrderIn, token: Optional[str] = None):
    """
    Set the order a route enters its haul roads in, going out. The return leg reverses
    it. Order changes the spliced geometry, so this clears and re-bakes like any other
    haul change.
    """
    _check_admin(token)
    res = haul.reorder(route_id, body.zone_ids)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    inval = haul.invalidate_for_route(route_id)
    haul.refresh_origin_temp_km(route_id)
    return _haul_write_result(route_id, inval, {"order": res["order"]})


@app.post("/api/admin/haul-roads/refresh-temp-km")
def refresh_temp_km(route_id: Optional[str] = None, token: Optional[str] = None):
    """
    Recompute routes.origin_temp_km from the drawn haul roads.

    Phase 4 made that column derived — it was seeded from V2 and computed with nowhere.
    Every attach, detach, reorder and haul-road edit refreshes it already; this is the
    manual backstop for a database whose links predate the change.
    """
    _check_admin(token)
    return haul.refresh_origin_temp_km(route_id)


@app.get("/api/admin/diagnostics/haul-roads")
def diagnostics_haul_roads(route_id: Optional[str] = None,
                           zone_id: Optional[str] = None,
                           profile: Optional[str] = None,
                           probe: bool = False, token: Optional[str] = None):
    """
    What Phase 4 would send HERE, and with probe=true what HERE does with it.

    ⚠️ Read this before believing either of the two claims Phase 4 was designed around.
    Both are inherited from a code comment and neither has been checked against the live
    service from this codebase:

      * that HERE ignores 'alternatives' when via-waypoints are present
      * that a stopover via splits the response into per-leg sections

    The second is load-bearing: 'via' mode's assigned-speed substitution only works if
    HERE isolates the haul stretch as its own section. If it does not, via mode silently
    falls back to HERE's own timing and says so in the response.

    probe=true needs route_id and spends up to three HERE calls on one route.
    """
    _check_admin(token)
    return haul.diagnostics(zone_id=zone_id, route_id=route_id,
                            profile=profile, probe=probe)


# ------------------------------------- Road restrictions (Phase 2.5a Tark Tee; H1 a provider per country)
@app.get("/api/restrictions")
def get_restrictions(layers: Optional[str] = None, include_expired: bool = False,
                     bbox: Optional[str] = None):
    """
    The tenant's country's road-restriction layers as WGS84 GeoJSON — Tark Tee's six
    for EE, National Highways' planned closures for GB, an empty collection with a note
    for a country without a provider. The rest of this docstring is Tark Tee's.

    12 Oct 2026 (map review §2.3): `bbox=w,s,e,n` (degrees) keeps only the features whose
    own bounding box intersects it and reports how many were `clipped`. The National
    Highways feed is national (~8 MB, 2,900 closures) and a corridor needs a few dozen of
    them. Four comma-separated numbers, west < east and south < north, or 400. The clipped
    body is built per request, not cached: the cache below is for the whole collection.

    Proxied rather than fetched from the browser for three reasons, in order: it is
    somebody else's public service and this caches it to one request per layer per half
    hour however many people are looking; **the coordinates have to be corrected before
    anything can draw them** (the service declares WKID 4326 and returns L-EST97 metres);
    and CORS then never matters.

    Not under /api/admin — the public map draws these and has no token, and a bridge
    weight limit is not sensitive.

    ⚠️ Expired records are excluded by default. The live layers carry roadworks from 2017,
    and drawing those as current would be worse than not having the layer. Pass
    include_expired=true to see everything; the response always reports how many were
    dropped.
    """
    keys = [k.strip() for k in (layers or "").split(",") if k.strip()] or None
    box = None
    if bbox is not None and str(bbox).strip():
        box = restrictions.parse_bbox(bbox)
        if box is None:
            raise HTTPException(400, "bbox must be west,south,east,north in degrees, west < east and south < north")
    fc = restrictions.fetch_all(keys, current_only=not include_expired)
    if box is not None:
        # built per request — a clipped body is one visitor's window, not the collection
        return Response(content=json.dumps(restrictions.clip_bbox(fc, box), ensure_ascii=False,
                                           separators=(",", ":")),
                        media_type="application/json")
    # 30 Sep 2026: serialised here, not by FastAPI's encoder. The National Highways feed
    # is ~8 MB of GeoJSON (2,920 closures, 170,000 vertices); jsonable_encoder walks
    # every vertex in Python (~4 s of the starter's half CPU per map load) before
    # json.dumps runs. One dumps is a fifth of that. The body is cached beside the
    # feature collection so a second map load costs nothing.
    return Response(content=restrictions.serialised(fc, keys, not include_expired),
                    media_type="application/json")


@app.get("/api/restrictions/layers")
def restriction_layers():
    """
    The layer catalogue — label, severity, colour and which vehicle dimension (if any) a
    limit on that layer can be compared against.

    The COLOUR is served from here so the map's legend and its layers cannot drift apart.
    That has already had to be fixed once on this map.
    """
    prov = restrictions.provider()
    if not prov:
        # a tenant without a provider: nothing to list, and the map hides the panel on
        # `provider: null` rather than showing an empty one
        return {"layers": [], "match_m": restrictions.match_m(), "provider": None,
                "attribution": None, "note": restrictions.NO_PROVIDER_NOTE}
    return {"layers": [dict(v, key=k) for k, v in restrictions.layers().items()],
            "match_m": restrictions.match_m(),
            "provider": prov,
            "attribution": prov["attribution"]}


@app.get("/api/routes/{route_id}/restrictions")
def route_restrictions(route_id: str, profile: Optional[str] = None):
    """
    Which restrictions the baked geometry of one route passes through.

    ⚠️ Reports, never blocks, and makes **no tonnage judgement** about a weak bridge:
    `nominal_load` is a class like 'N-13/NG-60', not tonnes, and the mapping has never
    been established here. The class and the vehicle's gross weight are both returned and
    `needs_interpretation` is set. See restrictions.check_route().
    """
    if not db.query("SELECT id FROM routes WHERE tenant_id = ? AND id = ?",
                    (db.current_tenant(), route_id)):
        raise HTTPException(404, "route not found")
    return restrictions.check_route(route_id, profile=profile)


@app.get("/api/routes/restrictions")
def all_route_restrictions(profile: Optional[str] = None, include_expired: bool = False):
    """
    Every baked route checked in one pass, sharing a single fetch. Only routes with a hit
    are returned — a clean route is the normal case and listing all 107 buries the ones
    that matter.

    12 Oct 2026 (map review §2.2c (c)): `include_expired=1` keeps closures that have
    already ENDED in the check, so the public map's timeline can list, for a past month,
    the closures that applied then. The default drops them, as before — every hit carries
    `from` / `to`, and the caller filters by month.
    """
    return restrictions.check_all(profile=profile, current_only=not include_expired)


@app.get("/api/admin/diagnostics/restrictions")
def diagnostics_restrictions(layer: Optional[str] = None, probe: bool = False,
                             token: Optional[str] = None):
    """
    What this asks the tenant's provider (Tark Tee / National Highways) for, and with
    probe=true what comes back — for Tark Tee including the raw
    coordinate next to the converted one, so the WKID mislabelling is visible rather than
    taken on trust. Spends no HERE calls and no Google quota.
    """
    _check_admin(token)
    return restrictions.diagnostics(layer=layer, probe=probe)


@app.post("/api/admin/restrictions/refresh")
def refresh_restrictions(token: Optional[str] = None):
    """Drop the cache so the next request re-fetches from the provider."""
    _check_admin(token)
    return restrictions.clear_cache()


# ------------------------------------------ Street View (Phase 2.5a)
@app.get("/api/streetview/meta")
def streetview_meta(lat: float, lon: float, radius: int = streetview.DEFAULT_RADIUS_M):
    """
    Does Google have street-level imagery near this point? **Free** — Google consumes no
    quota for metadata, only for images. The UI calls this first and asks for a picture
    only when the answer is yes, so a quarry down a private track costs nothing and shows
    nothing instead of spending a billable request on a grey tile.

    Also returns `offset_m`: how far Google had to move to find a panorama. A large offset
    means the picture is of somewhere else, which matters for a gate on a long approach.
    """
    return streetview.metadata(lat, lon, radius)


@app.get("/api/streetview")
def streetview_image(lat: float, lon: float, size: str = "480x300",
                     heading: Optional[int] = None, pitch: int = 0, fov: int = 80,
                     radius: int = streetview.DEFAULT_RADIUS_M):
    """
    A Street View still, proxied so the Google key never reaches the browser.

    ⚠️ **This costs a billable Google request.** It checks the free metadata endpoint
    first and returns 404 rather than spending one when there is no imagery. Nothing is
    written to disk or to the database — Google's terms restrict storing Maps content.
    """
    from fastapi.responses import Response
    data, ctype = streetview.fetch_image(lat, lon, size=size, heading=heading,
                                         pitch=pitch, fov=fov, radius=radius)
    if data is None:
        raise HTTPException(404, ctype)
    # short cache only: enough to stop a re-render costing a second request, not storage
    return Response(content=data, media_type=ctype,
                    headers={"Cache-Control": "private, max-age=900"})


@app.get("/api/admin/diagnostics/streetview")
def diagnostics_streetview(lat: Optional[float] = None, lon: Optional[float] = None,
                           probe: bool = False, token: Optional[str] = None):
    """
    Whether Street View is wired up and how many billable requests this process has made.
    probe=true calls metadata only, which is free.
    """
    _check_admin(token)
    return streetview.diagnostics(lat=lat, lon=lon, probe=probe)


# ------------------------------------------------------------------ static
class NoCacheStatic(StaticFiles):
    """StaticFiles that revalidates instead of trusting the browser's guess.

    Same fault as GET / had, and the same fix. Starlette sends an ETag and no
    Cache-Control, so Chrome applies its own freshness heuristic and can serve a
    stale map/index.html or overlay.js straight through a hard refresh —
    which once looked exactly like a failed deploy for an hour, and on the map
    specifically produced a HALF-upgraded pair: new index.html, old JS.

    `no-cache`, NOT `no-store`. The browser still revalidates with its ETag and
    still gets a 304 when nothing changed, so a large static file is re-downloaded
    only when it has actually changed. no-store would re-fetch it on every page load.
    (The alignment itself is no longer a static file: /api/public/alignment carries
    its own ETag.)

    ⚠️ This does NOT replace the ?v= cache-buster on overlay.js. That guards the
    same failure one layer up and costs nothing; belt and braces is the right
    number of mechanisms for a bug that has bitten twice.
    """

    # get_response() is the documented override point and has been stable across
    # Starlette versions. `file_response()` is the more obvious hook and is the
    # WRONG one to use here: it is internal, its signature has changed, and a
    # subclass that overrides a method the installed version no longer calls adds
    # no header and raises no error — it fails exactly as silently as the bug it
    # is meant to fix.
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        try:
            resp.headers["Cache-Control"] = "no-cache"
        except Exception:
            pass          # never let a header failure 500 the map
        return resp

    async def check_config(self):
        # 29 Sep 2026: Starlette's check raises on the FIRST REQUEST when the mounted
        # folder is missing (a 500, forever). A missing folder must be a 404 instead —
        # the brand folder could arrive in a later delivery than this file.
        if self.directory is not None and not os.path.isdir(str(self.directory)):
            return
        await super().check_config()


# Map (Mapbox app) at /map/ ; must be mounted before the catch-all "/".
app.mount("/map", NoCacheStatic(directory=str(ROOT / "map"), html=True), name="map")
# The user guide at /help/ (frontend/help/, landed on the repo on 10 Sep afternoon by
# another session; its main.py mount had been lost under the costing zip). Same
# no-cache static class, after /map, before the catch-all "/". test_help.py pins it.
app.mount("/help", NoCacheStatic(directory=str(ROOT / "frontend" / "help"), html=True), name="help")
# --------------------------------------------------------------------------- #
#  H9 (8 Oct 2026) — demo requests from the landing page                       #
# --------------------------------------------------------------------------- #
# The form on wayscope.co.uk is plain HTML (no script) and posts form-encoded data here.
# gate.OPEN_PATHS lets an outsider reach exactly this path. The body is parsed by hand
# (urllib) so no form-parsing dependency is added. Every outcome is a 303 to a page on the
# landing site, except the on-screen access page when no sender is configured — see
# demo_request.handle(). The send runs AFTER the redirect, as a background task.
import urllib.parse as _urlparse
try:
    from fastapi.responses import HTMLResponse as _DRHtml, RedirectResponse as _DRRedirect
    from starlette.background import BackgroundTask as _DRTask
except Exception:      # the stubbed fastapi of the sandbox harnesses has neither; the endpoint never runs there
    _DRHtml = _DRRedirect = _DRTask = None


@app.post("/api/public/demo-request")
async def demo_request_submit(request: Request):
    raw = (await request.body()).decode("utf-8", "replace")
    form = {k: v[0] for k, v in _urlparse.parse_qs(raw, keep_blank_values=True).items()}
    ip = demo_request.client_ip(request.headers.get("x-forwarded-for"),
                                request.client.host if request.client else "")
    result = demo_request.handle(form, ip)
    lu = demo_request.landing_url()
    if result["outcome"] == "screen":
        return _DRHtml(demo_request.access_page(result["name"], result["access"]),
                       headers={"Cache-Control": "no-store"})
    if result["outcome"] == "error":
        return _DRRedirect(lu + "/error.html", status_code=303)
    if result["outcome"] == "queued":
        return _DRRedirect(lu + "/thanks.html", status_code=303,
                           background=_DRTask(demo_request.deliver, result["request_id"]))
    return _DRRedirect(lu + "/thanks.html", status_code=303)


@app.get("/api/admin/diagnostics/smtp")
def demo_smtp_probe(token: Optional[str] = None):
    """H9 probe: connect + STARTTLS + login to the configured sender, send nothing, report the step that failed."""
    _check_admin(token)
    return demo_request.smtp_probe()


@app.get("/api/admin/demo-requests.csv")
def demo_requests_csv(token: Optional[str] = None):
    """The leads, newest first. Behind ADMIN_TOKEN like every /api/admin/* call."""
    _check_admin(token)
    return Response(demo_request.csv_export(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="demo-requests.csv"',
                             "Cache-Control": "no-store"})


# 6 Oct 2026 (H5) — the public landing page at /landing/ for PREVIEW on this service. The
# page lives in landing/ at the repo root so the same folder deploys as a Render static
# site on the root domain once the app has moved to app. (H0's open decision). Not gated:
# it is the public page. check_dir=False for the same reason as /brand below.
app.mount("/landing", NoCacheStatic(directory=str(ROOT / "landing"), html=True, check_dir=False), name="landing")
# 29 Sep 2026 — the Wayscope brand files (logos, favicon set, theme tokens) at /brand/.
# Not gated: gate.scope_for() polices /map, /help, /bulletin and the map's data prefixes only, so a
# refused visitor still sees the logo on the password page. Mounted before the "/" route.
# check_dir=False: Starlette otherwise REFUSES TO BOOT when the folder is missing, which
# would take the whole deployment down if the brand files were ever deployed separately
# from this file. Without the folder the brand paths 404 and nothing else changes.
BRAND_DIR = ROOT / "frontend" / "brand"
app.mount("/brand", NoCacheStatic(directory=str(BRAND_DIR), check_dir=False), name="brand")

# Browsers and iOS request these at the ROOT, whatever the page says, and the manifest's
# icon paths are root-relative — so each one is a root route onto the brand folder.
ROOT_BRAND_FILES = {
    "favicon.ico": "image/x-icon",
    "favicon.svg": "image/svg+xml",
    "apple-touch-icon.png": "image/png",
    "site.webmanifest": "application/manifest+json",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "icon-512-maskable.png": "image/png",
}


def _brand_file(name):
    path = BRAND_DIR / name
    if name not in ROOT_BRAND_FILES or not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(path), media_type=ROOT_BRAND_FILES[name],
                        headers={"Cache-Control": "no-cache"})


for _name in list(ROOT_BRAND_FILES):
    app.get("/" + _name, include_in_schema=False)(
        (lambda n: (lambda: _brand_file(n)))(_name))


@app.get("/")
def frontend_index():
    # no-cache, NOT no-store: the browser still revalidates with its ETag and still gets
    # a 304 when nothing has changed, so a normal load costs the same as before. Without
    # it Starlette sends an ETag with no Cache-Control, Chrome applies its own freshness
    # heuristic, and a deployed index.html can stay invisible behind a cached copy that
    # survives Ctrl+Shift+R. That cost an hour on 2026-08-30 and looked exactly like a
    # failed deploy: the new API answered, the new page did not appear, and the repo,
    # the build and the commit were all correct.
    return FileResponse(str(ROOT / "frontend" / "index.html"),
                        headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

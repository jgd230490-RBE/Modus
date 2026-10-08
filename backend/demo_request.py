"""
H9 (8 Oct 2026) — demo requests from the landing page.

The form on wayscope.co.uk POSTs (plain HTML, form-encoded, no script) to
/api/public/demo-request on the app. This module does everything except the HTTP:

    handle(form, ip)    validate → honeypot → rate limits → store → decide the outcome
    deliver(request_id) the background send: the visitor's email + a notification copy
    access_page(...)    the on-screen fallback when no sender is configured
    csv_export()        the leads, for GET /api/admin/demo-requests.csv

Two delivery modes, chosen by the environment at request time:

  * SMTP configured (SMTP_USER, SMTP_PASSWORD, DEMO_FROM, DEMO_NOTIFY all set): the row is
    stored, the visitor is sent to {LANDING_URL}/thanks.html, and a background task emails
    the demo link + the two shared codes through Google Workspace SMTP (STARTTLS, 587).
  * SMTP not configured: the row is stored and the app answers with a page that SHOWS the
    link and the codes — the same words the email would carry. No visitor ever sees an
    error because a variable is missing. The CSV marks these rows "shown on screen".

The codes are MAP_PASSWORD and the team code named by DEMO_TEAM_CODE_VAR (default
IPT1_CODE), read from the environment at send time. They never enter the repository, the
landing page or the database. The planner and admin codes are never sent.

Abuse limits — a limit, not security (G3 is after 15 Oct): a honeypot field ("website") a
person never sees; at most PER_IP_PER_HOUR requests per hashed IP per hour; one email per
PER_EMAIL_MINUTES in email mode (a repeat inside that window is answered with the thanks
page; nothing is stored or re-sent); length caps on every field; a basic email-shape check. The IP
is stored only as a salted SHA-256 hash.
"""
import csv
import datetime
import hashlib
import html
import io
import os
import re
import smtplib
import uuid
from email.message import EmailMessage

import db

DEMO_URL = "https://app.wayscope.co.uk/"
DEFAULT_LANDING_URL = "https://wayscope.co.uk"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
PER_IP_PER_HOUR = 5
PER_EMAIL_MINUTES = 10
MAX_LEN = {"name": 120, "email": 200, "organisation": 160, "role": 80, "wants": 300}
ROLES = ("Client or highway authority", "Principal contractor", "Logistics or site management",
         "Haulier or fleet operator", "Local authority officer", "Consultant", "Other")
HONEYPOT = "website"
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

STATUS_QUEUED = "queued"
STATUS_SENT = "sent"
STATUS_SCREEN = "shown on screen (SMTP not configured)"
STATUS_FAILED = "failed: "


# --------------------------------------------------------------------------- settings

def landing_url():
    return (os.getenv("LANDING_URL") or DEFAULT_LANDING_URL).strip().rstrip("/")


def smtp_settings():
    """The four variables that make email possible, or None if any is missing."""
    s = {k: (os.getenv(k) or "").strip() for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY")}
    if not all(s.values()):
        return None
    s["host"], s["port"] = SMTP_HOST, SMTP_PORT
    s["reply_to"] = (os.getenv("DEMO_REPLY_TO") or s["DEMO_NOTIFY"]).strip()
    return s


def codes():
    """The two shared codes a visitor gets. Read at call time; never cached, never stored."""
    var = (os.getenv("DEMO_TEAM_CODE_VAR") or "IPT1_CODE").strip()
    return {"map": (os.getenv("MAP_PASSWORD") or "").strip(),
            "team": (os.getenv(var) or "").strip(),
            "team_var": var}


def ip_hash(ip):
    salt = (os.getenv("GATE_SECRET") or os.getenv("ADMIN_TOKEN") or "wayscope").strip()
    return hashlib.sha256((salt + "|" + (ip or "")).encode("utf-8")).hexdigest()[:32]


def client_ip(forwarded_for, peer):
    """Render terminates TLS and forwards; the first X-Forwarded-For entry is the visitor."""
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return (peer or "").strip()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- validation

def validate(form):
    """
    form: {field: str}. Returns (clean, error). clean is None on error. error is
    "honeypot" when the hidden field was filled (the caller stores nothing and says thanks).
    """
    f = {k: (v if isinstance(v, str) else (v[0] if v else "")) for k, v in (form or {}).items()}
    if (f.get(HONEYPOT) or "").strip():
        return None, "honeypot"
    clean = {}
    for k, cap in MAX_LEN.items():
        v = (f.get(k) or "").strip()
        if len(v) > cap:
            return None, f"{k} too long"
        clean[k] = v
    for k in ("name", "email", "organisation", "role"):
        if not clean[k]:
            return None, f"{k} missing"
    if not EMAIL_RX.match(clean["email"]):
        return None, "email malformed"
    if clean["role"] not in ROLES:
        return None, "role unknown"
    clean["email"] = clean["email"].lower()
    clean["updates_opt_in"] = (f.get("updates") or "").strip().lower() in ("yes", "on", "1", "true")
    return clean, None


# --------------------------------------------------------------------------- storage

def _count_since(where, params, minutes, now):
    since = _iso(now - datetime.timedelta(minutes=minutes))
    rows = db.query(f"SELECT COUNT(*) AS n FROM demo_requests WHERE {where} AND created_at >= ?",
                    tuple(params) + (since,))
    return int(rows[0]["n"]) if rows else 0


def ip_over_limit(iph, now=None):
    return _count_since("ip_hash = ?", (iph,), 60, now or _now()) >= PER_IP_PER_HOUR


def email_recent(email, now=None):
    return _count_since("email = ?", (email,), PER_EMAIL_MINUTES, now or _now()) > 0


def store(clean, iph, status, now=None):
    rid = uuid.uuid4().hex
    db.execute(
        "INSERT INTO demo_requests (id, created_at, name, email, organisation, role, wants, "
        "updates_opt_in, ip_hash, email_status, email_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, _iso(now or _now()), clean["name"], clean["email"], clean["organisation"], clean["role"],
         clean["wants"], 1 if clean["updates_opt_in"] else 0, iph, status, ""))
    return rid


def set_status(rid, status, error=""):
    db.execute("UPDATE demo_requests SET email_status = ?, email_error = ? WHERE id = ?",
               (status, (error or "")[:400], rid))


def get(rid):
    rows = db.query("SELECT * FROM demo_requests WHERE id = ?", (rid,))
    return rows[0] if rows else None


# --------------------------------------------------------------------------- the decision

def handle(form, ip, now=None):
    """
    The whole policy for one POST. Returns a dict:
      {"outcome": "thanks"}                         → 303 to thanks.html, nothing more
      {"outcome": "error", "reason": ...}           → 303 to error.html
      {"outcome": "queued", "request_id": ...}      → 303 to thanks.html + deliver() in the background
      {"outcome": "screen", "request_id": ..., "name": ..., "codes": {...}}
                                                    → 200 with access_page()
    """
    now = now or _now()
    clean, err = validate(form)
    if err == "honeypot":
        return {"outcome": "thanks", "reason": "honeypot"}
    if err:
        return {"outcome": "error", "reason": err}
    iph = ip_hash(ip)
    if ip_over_limit(iph, now):
        return {"outcome": "error", "reason": "too many requests from this address"}
    if smtp_settings() is None:
        rid = store(clean, iph, STATUS_SCREEN, now)
        return {"outcome": "screen", "request_id": rid, "name": clean["name"], "codes": codes()}
    if email_recent(clean["email"], now):
        # Not stored: the lead exists already, and a stored repeat would itself count as
        # "recent" and push the window along for ever.
        return {"outcome": "thanks", "reason": "repeat"}
    rid = store(clean, iph, STATUS_QUEUED, now)
    return {"outcome": "queued", "request_id": rid}


# --------------------------------------------------------------------------- the email

def _first_name(name):
    return (name or "").strip().split(" ")[0] or "there"


def email_text(name, c):
    return f"""Hello {_first_name(name)},

Thanks for asking to see Wayscope. Here's everything you need for the demo.

Open the demo: {DEMO_URL}

Corridor map password: {c['map']}
Team access code: {c['team']}

The demo is a fictional highways scheme, and nothing in it is a real project. The access details are shared with everyone viewing the demo, so please don't enter real data.

Three things to try:
1. Dashboard: today's tonnes, trips and vehicles, and this week against plan.
2. Look-ahead: next week committed by route and by day, with closures and route caps flagged.
3. Corridor map: press Play to watch a month of haul unfold.

A short guide opens on each page the first time you visit. You can replay it any time from "Guide" in the corner.

If you'd like a walkthrough of approving a week as a planner, just reply to this email.

John Davis
Wayscope · wayscope.co.uk

You're receiving this because you requested a demo at wayscope.co.uk. Privacy notice: {landing_url()}/privacy.html
"""


def email_html(name, c):
    e = html.escape
    return f"""<!doctype html><html lang="en-GB"><body style="font-family:'IBM Plex Sans',Segoe UI,system-ui,sans-serif;color:#1F2024;line-height:1.55;max-width:600px;margin:0 auto;padding:24px">
<p>Hello {e(_first_name(name))},</p>
<p>Thanks for asking to see Wayscope. Here's everything you need for the demo.</p>
<p><b>Open the demo:</b> <a href="{DEMO_URL}">{DEMO_URL}</a></p>
<p><b>Corridor map password:</b> {e(c['map'])}<br><b>Team access code:</b> {e(c['team'])}</p>
<p>The demo is a fictional highways scheme, and nothing in it is a real project. The access details are shared with everyone viewing the demo, so please don't enter real data.</p>
<p>Three things to try:</p>
<ol>
<li><b>Dashboard:</b> today's tonnes, trips and vehicles, and this week against plan.</li>
<li><b>Look-ahead:</b> next week committed by route and by day, with closures and route caps flagged.</li>
<li><b>Corridor map:</b> press Play to watch a month of haul unfold.</li>
</ol>
<p>A short guide opens on each page the first time you visit. You can replay it any time from "Guide" in the corner.</p>
<p>If you'd like a walkthrough of approving a week as a planner, just reply to this email.</p>
<p>John Davis<br>Wayscope · <a href="{landing_url()}/">wayscope.co.uk</a></p>
<p style="font-size:12px;color:#5B6470">You're receiving this because you requested a demo at wayscope.co.uk. <a href="{landing_url()}/privacy.html">Privacy notice</a></p>
</body></html>"""


def build_message(to, name, c, settings):
    msg = EmailMessage()
    msg["Subject"] = "Your Wayscope demo access"
    msg["From"] = settings["DEMO_FROM"]
    msg["To"] = to
    msg["Reply-To"] = settings["reply_to"]
    msg.set_content(email_text(name, c))
    msg.add_alternative(email_html(name, c), subtype="html")
    return msg


def notify_message(row, settings):
    msg = EmailMessage()
    msg["Subject"] = f"Demo request: {row['name']}, {row['organisation']}"
    msg["From"] = settings["DEMO_FROM"]
    msg["To"] = settings["DEMO_NOTIFY"]
    msg.set_content(
        f"Demo request: {row['name']}, {row['organisation']}, {row['role']}, {row['email']}. "
        f"Wants to see: {row.get('wants') or '-'}. Updates: {'yes' if row.get('updates_opt_in') else 'no'}.\n")
    return msg


def send(msg, settings):
    """One SMTP session: STARTTLS, login with the app password, send. Raises on failure."""
    with smtplib.SMTP(settings["host"], settings["port"], timeout=20) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(settings["SMTP_USER"], settings["SMTP_PASSWORD"])
        s.send_message(msg)


def deliver(request_id):
    """
    The background task behind a "queued" outcome. Sends the visitor's email, then the
    notification copy; records the result on the row. Never raises — a failure is a status.
    """
    row = get(request_id)
    if not row:
        return "missing"
    settings = smtp_settings()
    if settings is None:
        set_status(request_id, "unsent: SMTP not configured")
        return "unsent"
    try:
        send(build_message(row["email"], row["name"], codes(), settings), settings)
    except Exception as e:  # noqa: BLE001 — recorded, never raised into the request
        set_status(request_id, STATUS_FAILED + e.__class__.__name__, str(e))
        print(f"demo_request: {request_id} visitor email FAILED {e.__class__.__name__}: {str(e)[:200]}")
        return "failed"
    set_status(request_id, STATUS_SENT)
    print(f"demo_request: {request_id} visitor email sent")
    try:
        send(notify_message(row, settings), settings)
        print(f"demo_request: {request_id} notification sent")
    except Exception as e:  # noqa: BLE001 — the visitor has theirs; note the miss
        set_status(request_id, STATUS_SENT + "; notification failed: " + e.__class__.__name__, str(e))
        print(f"demo_request: {request_id} notification FAILED {e.__class__.__name__}: {str(e)[:200]}")
    return "sent"


# --------------------------------------------------------------------------- the probe

def smtp_probe():
    """
    GET /api/admin/diagnostics/smtp: one SMTP session to the configured host — connect,
    STARTTLS, login — and nothing sent. Says which step failed and the server's words, so a
    bad app password (535), a blocked port or a slow route is visible without a lead. Never
    returns the password or a code; the user name is shown because it is the From address.
    """
    import time
    s = smtp_settings()
    out = {"configured": s is not None, "host": SMTP_HOST, "port": SMTP_PORT,
           "user": (os.getenv("SMTP_USER") or "").strip() or None,
           "missing": [k for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY") if not (os.getenv(k) or "").strip()],
           "step": None, "ok": False, "error_class": None, "error": None, "elapsed_ms": None}
    if s is None:
        out["step"] = "settings"
        out["error"] = "not configured: " + ", ".join(out["missing"])
        return out
    t0 = time.time()
    try:
        out["step"] = "connect"
        with smtplib.SMTP(s["host"], s["port"], timeout=20) as c:
            out["step"] = "ehlo"; c.ehlo()
            out["step"] = "starttls"; c.starttls(); c.ehlo()
            out["step"] = "login"; c.login(s["SMTP_USER"], s["SMTP_PASSWORD"])
            out["step"] = "done"; out["ok"] = True
    except Exception as e:  # noqa: BLE001 — the whole point is to report it
        out["error_class"] = e.__class__.__name__
        out["error"] = str(e)[:300]
    out["elapsed_ms"] = int((time.time() - t0) * 1000)
    return out


# --------------------------------------------------------------------------- the on-screen page

def access_page(name, c):
    """The fallback for a deployment with no sender: the same words as the email, on screen."""
    e = html.escape
    lu = landing_url()
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wayscope — your demo access</title>
<meta name="robots" content="noindex">
<style>
  :root{{--ink:#1F2024;--ink-2:#3D4552;--muted:#5B6470;--line:#E3E6EA;--paper:#FFFFFF;--orange:#FF8C14;--orange-text:#C75F06;--orange-tint:#FFF3E3}}
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:'IBM Plex Sans',system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--paper);line-height:1.6;-webkit-font-smoothing:antialiased}}
  a{{color:inherit}}a:hover{{color:var(--orange-text)}}
  h1{{font-weight:600;letter-spacing:-.02em;margin:0;line-height:1.15;font-size:clamp(28px,4vw,38px)}}
  .wrap{{max-width:640px;margin:0 auto;padding:0 24px}}
  header{{padding:22px 0;font-weight:600;font-size:18px}}
  main{{padding:24px 0 96px}}
  p{{font-size:17px;color:var(--ink-2);margin:16px 0 0}}
  .codes{{margin-top:24px;border:1px solid var(--line);border-radius:14px;padding:20px 22px;display:grid;gap:14px}}
  .codes div{{display:flex;flex-direction:column;gap:2px}}
  .codes .k{{font-size:13px;color:var(--muted)}}
  .codes .v{{font-size:22px;font-weight:500;letter-spacing:.04em;word-break:break-all}}
  .btn{{display:inline-flex;align-items:center;margin-top:20px;text-decoration:none;border-radius:999px;padding:14px 24px;font-weight:500;background:var(--orange);color:var(--ink)}}
  ol{{padding-left:22px;color:var(--ink-2);font-size:16px}}
  .fine{{font-size:13px;color:var(--muted);margin-top:32px}}
</style>
</head>
<body>
<header class="wrap"><a href="{lu}/" style="text-decoration:none">Wayscope</a></header>
<main class="wrap">
  <h1>Hello {e(_first_name(name))}, here's your demo access.</h1>
  <p>Thanks for asking to see Wayscope. Everything you need is below. Keep this page open, or write the two codes down.</p>
  <div class="codes">
    <div><span class="k">Corridor map password</span><span class="v">{e(c['map'])}</span></div>
    <div><span class="k">Team access code</span><span class="v">{e(c['team'])}</span></div>
  </div>
  <a class="btn" href="{DEMO_URL}">Open the demo</a>
  <p>The demo is a fictional highways scheme, and nothing in it is a real project. The access details are shared with everyone viewing the demo, so please don't enter real data.</p>
  <p>Three things to try:</p>
  <ol>
    <li><b>Dashboard:</b> today's tonnes, trips and vehicles, and this week against plan.</li>
    <li><b>Look-ahead:</b> next week committed by route and by day, with closures and route caps flagged.</li>
    <li><b>Corridor map:</b> press Play to watch a month of haul unfold.</li>
  </ol>
  <p>If you'd like a walkthrough of approving a week as a planner, email <a href="mailto:JDavis@wayscope.co.uk">JDavis@wayscope.co.uk</a>.</p>
  <p class="fine">You asked for this at wayscope.co.uk. <a href="{lu}/privacy.html">Privacy notice</a> · <a href="{lu}/">Back to Wayscope</a></p>
</main>
</body>
</html>"""


# --------------------------------------------------------------------------- the leads

CSV_COLUMNS = ("created_at", "name", "email", "organisation", "role", "wants", "updates_opt_in",
               "email_status", "email_error", "id")


def csv_export():
    rows = db.query("SELECT * FROM demo_requests ORDER BY created_at DESC")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for r in rows:
        w.writerow([("yes" if r.get(k) else "no") if k == "updates_opt_in" else (r.get(k) or "") for k in CSV_COLUMNS])
    return buf.getvalue()

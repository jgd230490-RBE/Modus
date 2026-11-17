"""
16 Nov 2026 (claude/tools-route-check-request) — the ONE store for a person's details that the public tools share.

One table, `tool_leads` (db.init_tool_leads_db): a route check request (kind "route-check") and, once the calculators
wire it, an email given for a calculator's PDF (kind "calculator-pdf"). It is not plan data and not tenanted: a lead
belongs to the company running the deployment, as demo_requests does. It is in db.NO_DATA_TABLES (a public send must not
empty the kept reads), is not in the organisation file and is never wiped by a package import. It is NOT in
make_demo_tenant's LIVE_TABLES: those copy tenanted tables out of a live export, and a refresh never touches an
untenanted table, so a demo refresh keeps it already.

The visitor's address is kept only as a salted hash (tools_public.address_hash); nothing else about the visitor is kept.
`news` is 0 / 1 and is never compared with 1 in SQL.
"""
import csv
import datetime
import io
import json
import re
import uuid

import db
import tools_public

KINDS = ("route-check", "calculator-pdf")
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MAX_EMAIL = 200
STATUS_QUEUED = "queued"
STATUS_SENT = "sent"
CSV_COLUMNS = ("created_at", "kind", "name", "email", "company", "news", "details", "status", "id")


def email_ok(email):
    """A plain shape check, as the landing form's: one @, a dot after it, no spaces, at most 200 characters."""
    e = email.strip() if isinstance(email, str) else ""
    return bool(e) and len(e) <= MAX_EMAIL and bool(EMAIL_RX.match(e))


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def keep(kind, email, name="", company="", news=False, details=None, ip=""):
    """Store one row and return its id. The address `ip` is hashed here; `details` (a dict) is kept as JSON text."""
    if kind not in KINDS:
        raise ValueError("unknown kind")
    if not email_ok(email):
        raise ValueError("email")
    rid = uuid.uuid4().hex
    db.execute(
        "INSERT INTO tool_leads (id, kind, created_at, email, name, company, news, details, ip_hash, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, kind, _now().strftime("%Y-%m-%dT%H:%M:%SZ"), email.strip().lower(), (name or "").strip(),
         (company or "").strip(), 1 if news else 0, json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
         tools_public.address_hash(ip) if ip else "", STATUS_QUEUED))
    return rid


def set_status(rid, status):
    db.execute("UPDATE tool_leads SET status = ? WHERE id = ?", ((status or "")[:200], rid))


def get(rid):
    rows = db.query("SELECT * FROM tool_leads WHERE id = ?", (rid,))
    return rows[0] if rows else None


def csv_export():
    """Every row, newest first, as CSV text (the admin read). The address hash is not in it."""
    rows = db.query("SELECT * FROM tool_leads ORDER BY created_at DESC")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    import users       # 17 Nov 2026: csv_cell, so a typed "=…" is shown by a spreadsheet and not run
    for r in rows:
        w.writerow([("yes" if r.get(k) else "no") if k == "news" else users.csv_cell(r.get(k) or "") for k in CSV_COLUMNS])
    return buf.getvalue()

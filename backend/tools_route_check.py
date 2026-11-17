"""
16 Nov 2026 (claude/tools-route-check-request) — the route check REQUEST: the open call behind /tools/route-check.

A request form only. It keeps the typed details (tools_leads) and tells John by one plain email; nothing is worked out,
no route is read and no report goes out here. No email goes to the person who asked. England only is a line on the page,
not a check here (From and To are typed words, never looked up).

Open-call rule (tools_public header): the route takes tools_public.guard first with LIMIT, a machine that filled the
hidden box is told it worked and nothing is kept, every refusal is one plain sentence, lengths are capped.
"""
import json
import re
from email.message import EmailMessage
from pathlib import Path

import conversions
import demo_request
import tools_leads
import tools_public

#: five an hour for one address, as the landing form's (demo_request.PER_IP_PER_HOUR)
LIMIT = tools_public.Limit("route-check", 5, 3600)
MAX_LEN = {"from": 200, "to": 200, "name": 120, "email": 200, "company": 160, "note": 300}
MAX_LOADS = 100000
SUBJECT = "Route check request"
TOO_LONG = {"from": "The start is too long.", "to": "The end is too long.", "name": "The name is too long.",
            "email": "Type an email address we can write to.", "company": "The company is too long.",
            "note": "The note is too long."}


def lorry_labels():
    """The planning lorries as a person reads them, in the shipped order (factors.json), never a key."""
    f = json.loads((Path(__file__).resolve().parent / "factors.json").read_text(encoding="utf-8"))
    return [conversions.vehicle_label(f, k) for k in (f.get("planning_vehicles") or [])]


def _text(body, k):
    v = body.get(k)
    return v.strip() if isinstance(v, str) else ""


def validate(body):
    """(clean, None) or (None, one plain sentence). The first missing box is the one named."""
    if not isinstance(body, dict):
        return None, "That did not work. Please try again in a minute."
    t = {k: _text(body, k) for k in MAX_LEN}
    for k in ("from", "to", "name", "company", "note", "email"):
        if len(t[k]) > MAX_LEN[k]:
            return None, TOO_LONG[k]
    if not t["from"]:
        return None, "Type where the load starts."
    if not t["to"]:
        return None, "Type where the load ends."
    lorry = _text(body, "lorry")
    if lorry not in lorry_labels():
        return None, "Pick the lorry."
    raw = body.get("loads")
    if isinstance(raw, bool):
        raw = "x"
    elif isinstance(raw, (int, float)):
        raw = str(int(raw)) if float(raw) == int(raw) else "x"
    raw = raw.strip().replace(",", "") if isinstance(raw, str) else ""
    loads = None
    if raw:
        if not re.fullmatch(r"\d{1,6}", raw) or not (1 <= int(raw) <= MAX_LOADS):
            return None, "Type the loads as a whole number, or leave it empty."
        loads = int(raw)
    if not t["name"]:
        return None, "Type your name."
    if not tools_leads.email_ok(t["email"]):
        return None, "Type an email address we can write to."
    return {"from": t["from"], "to": t["to"], "lorry": lorry, "loads": loads, "name": t["name"],
            "email": t["email"].lower(), "company": t["company"], "note": t["note"]}, None


def handle(body, ip):
    """Keep one request. {"ok": True, "request_id": id}; a machine's gets request_id None. A bad box raises the refusal."""
    if tools_public.trapped(body):
        return {"ok": True, "request_id": None}
    clean, say = validate(body)
    if say:
        tools_public.refuse(400, say)
    rid = tools_leads.keep("route-check", clean["email"], name=clean["name"], company=clean["company"], news=False,
                           details={"from": clean["from"], "to": clean["to"], "lorry": clean["lorry"],
                                    "loads": clean["loads"], "note": clean["note"]}, ip=ip)
    return {"ok": True, "request_id": rid}


def notify_message(row, settings):
    """The one email, to John only: what was typed. No secret, no address hash."""
    d = json.loads(row.get("details") or "{}")
    msg = EmailMessage()
    msg["Subject"] = SUBJECT
    msg["From"] = settings["DEMO_FROM"]
    msg["To"] = settings["DEMO_NOTIFY"]
    msg["Reply-To"] = row["email"]
    loads = d.get("loads")
    msg.set_content(
        "Route check request\n\n"
        f"From: {d.get('from', '')}\nTo: {d.get('to', '')}\nLorry: {d.get('lorry', '')}\n"
        f"Loads: {loads if loads is not None else '-'}\n\n"
        f"Name: {row.get('name', '')}\nEmail: {row.get('email', '')}\nCompany: {row.get('company') or '-'}\n"
        f"Note: {d.get('note') or '-'}\n")
    return msg


def deliver(request_id):
    """The background task: email John after the answer has gone. Never raises; a miss is the row's status."""
    row = tools_leads.get(request_id)
    if not row:
        return "missing"
    settings = demo_request.smtp_settings()
    if settings is None:
        tools_leads.set_status(request_id, "unsent: SMTP not configured")
        return "unsent"
    try:
        demo_request.send(notify_message(row, settings), settings)
    except Exception as e:  # noqa: BLE001 — kept, marked, never raised into the request
        tools_leads.set_status(request_id, "failed: " + e.__class__.__name__)
        print(f"tools_route_check: {request_id} notification FAILED {e.__class__.__name__}")
        return "failed"
    tools_leads.set_status(request_id, tools_leads.STATUS_SENT)
    return "sent"

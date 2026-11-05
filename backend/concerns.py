"""
5 Nov 2026 (group 6: S6 / V6 + the complaints half of CLOCS C7; D64, D65) — concerns from the public, stored per scheme.

Mockup notes/report-concern-mockup-1105/ (John: "Yes, as recommended", Q1-Q14).

    submit(form, ip)        the public map's Report a concern: check -> limits -> store -> the reference
    add_by_staff(body, by)  one that came in by email, phone or in person, typed by a planner or admin
    listing(...) / one(id)  the staff page (planners and admins only: the record holds a member of the public's contact)
    reply / close / reopen / set_route / forget             what staff do with one; every step lands in its history
    sweep(now)              the clean-up (card 9): runs at most once an hour, from a submit, a staff read or start-up

WHO SEES WHAT
-------------
The public send answers with the new reference and nothing else: no endpoint under /api/public/ reads a concern back
(Q5). It is behind the map password like the rest of /api/public/ (Q1) and needs the app's X-Wayscope header and a JSON
body, so a form on another site cannot post one. The tenant is the deployment's, never the body's.

WHAT IS KEPT, AND FOR HOW LONG (card 9, Q8; the client sets the months on Config, default 12)
-----------------------------------------------------------------------------------------------
  * name, email, phone, the text, the registration, the time of day and the staff's reply notes: deleted `keep` months
    after the concern is closed (or at once with "Delete the personal details now"); the pin is rounded to 3 decimal
    places (about 100 m) at the same time;
  * a concern never closed: its name, email and phone 24 months after it came in (a safety stop);
  * closed as "Not a concern (spam)": the whole record 30 days after closing;
  * the hashed network address (the rate limit only): 30 days after it came in;
  * kept for the scheme's life: kind, date, route, site, council, the rounded place, status, outcome, reply and close dates.
Not legal advice: on a pilot the client is the controller and its own notice wins.

MISUSE (card 11) — a limit, not security: a hidden trap field; 5 an hour and 20 a day from one hashed network address,
300 a day for the scheme; length caps; no < or >, no web links; a pin within 10 km of the scheme's routes and sites;
no files. Everything is shown back as plain text.
"""
import datetime
import json
import math
import re

import db

#: the seven kinds (Q3), fixed in Wayscope: key -> what a person reads
KINDS = {
    "off_route": "Lorry off its route",
    "driving": "Driving or speed",
    "parked": "Parked or waiting on the road",
    "mud": "Mud or debris on the road",
    "noise": "Noise, dust or working hours",
    "damage": "Damage to a road, verge or property",
    "other": "Something else",
}
#: how a concern is closed (card 5)
OUTCOMES = {
    "action": "Our lorry: action taken",
    "no_action": "Our lorry: no action needed",
    "not_ours": "Not one of our lorries",
    "no_detail": "Not enough detail to act on",
    "duplicate": "Duplicate of another concern",
    "spam": "Not a concern (spam)",
}
#: how one came in: the map, or typed by staff from an email, a call or a visit
SOURCES = {"map": "the public map", "email": "email", "phone": "phone", "person": "in person"}
STATUSES = ("new", "answered", "closed")

MAX_LEN = {"words": 1000, "name": 120, "email": 200, "phone": 30, "registration": 10, "reply": 1000}
MAX_BODY = 8 * 1024
PER_IP_PER_HOUR = 5
PER_IP_PER_DAY = 20
PER_TENANT_PER_DAY = 300
BOX_M = 10_000                 # a pin within 10 km of the scheme's routes and sites
NEAR_ROUTE_M = 500             # the route a pin is put on, if one is this close
KEEP_DEFAULT = 12              # months after closing (Config; 1-72)
KEEP_MIN, KEEP_MAX = 1, 72
OPEN_STOP_MONTHS = 24          # a concern never closed: its contact goes after this
SPAM_DAYS = 30
IP_DAYS = 30
SWEEP_EVERY_S = 3600
HONEYPOT = "website"
DEMO_PRIVACY_URL = "https://wayscope.co.uk/privacy.html#concerns"

EMAIL_RX = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]{2,}$")
PHONE_RX = re.compile(r"^[0-9+()\- ]{6,30}$")
REG_RX = re.compile(r"^[A-Za-z0-9 ]{1,10}$")
LINK_RX = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|net|org|info|ru|xyz|top|io)\b)", re.I)
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RX = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class Refused(Exception):
    """A send or a staff step refused, with the sentence a person reads, and the HTTP status."""

    def __init__(self, words, status=422):
        super().__init__(words)
        self.words = words
        self.status = status


# --------------------------------------------------------------------------- time

def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _iso(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(v):
    if not v:
        return None
    try:
        d = datetime.datetime.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            d = datetime.datetime.strptime(str(v)[:16], "%Y-%m-%dT%H:%M")
        except ValueError:
            return None
    return d.replace(tzinfo=datetime.timezone.utc)


def add_months(dt, months):
    """dt plus whole calendar months (the day clipped to the month's last)."""
    y, m = divmod(dt.month - 1 + int(months), 12)
    y += dt.year
    m += 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.replace(year=y, month=m, day=min(dt.day, last))


def working_days(a, b):
    """Days between two times, Saturdays and Sundays left out (bank holidays are not), one decimal. None if either is
    missing. The KPI clock for a first reply and for closing."""
    a, b = (_parse(a) if isinstance(a, str) else a), (_parse(b) if isinstance(b, str) else b)
    if a is None or b is None or b <= a:
        return None if (a is None or b is None) else 0.0
    secs = 0.0
    cur = a
    while cur < b:
        nxt = min(b, (cur + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0))
        if cur.weekday() < 5:
            secs += (nxt - cur).total_seconds()
        cur = nxt
    return round(secs / 86400.0, 1)


# --------------------------------------------------------------------------- settings (Config, card 8)

def settings(conversions=None):
    """The scheme's concern settings, with the demo's defaults. `form` = the form shows on the public map."""
    import config
    if conversions is None:
        import conversions as _c
        conversions = _c
    t = config.tenant_settings(conversions)
    demo = bool(t.get("demo_notice"))
    privacy = t.get("concern_privacy_url") or (DEMO_PRIVACY_URL if demo else None)
    return {"on": bool(t.get("concerns_on")), "privacy_url": privacy, "demo": demo,
            "keep_months": t.get("concern_keep_months") or KEEP_DEFAULT, "reply_days": t.get("concern_reply_days"),
            "email": t.get("concern_email"),
            "form": bool(t.get("concerns_on")) and bool(privacy)}


# --------------------------------------------------------------------------- the scheme's box and nearest route

_INDEX = {"version": None, "index": None, "box": None, "areas": None}


def _index():
    """The routes / sites index (collisions.RouteIndex, 500 m), the 10 km box and the districts, kept until a write."""
    if _INDEX["version"] == db.data_version() and _INDEX["index"] is not None:
        return _INDEX
    import collisions
    base = collisions.index_from_db()
    idx = collisions.RouteIndex(base.lines, base.sites, route_m=NEAR_ROUTE_M, site_m=NEAR_ROUTE_M)
    pts = [c for _, l in idx.lines for c in l] + [(s[2], s[3]) for s in idx.sites]
    box = None
    if pts:
        lat0 = sum(p[1] for p in pts) / len(pts)
        dx, dy = BOX_M / (111320.0 * math.cos(math.radians(lat0))), BOX_M / 110574.0
        box = (min(p[0] for p in pts) - dx, min(p[1] for p in pts) - dy,
               max(p[0] for p in pts) + dx, max(p[1] for p in pts) + dy)
    areas = []
    try:
        import areas as _areas
        for a in _areas.stored_areas():
            if a.get("tier") == "district" or not areas:
                areas.append((a["name"], _areas.Area(a["area_id"], a["geometry"]), a.get("tier")))
    except Exception:
        areas = []
    _INDEX.update(version=db.data_version(), index=idx, box=box, areas=areas)
    return _INDEX


def place_of(lon, lat):
    """(route_id or None, site_id or None, district name or None) for a pin."""
    ix = _index()
    routes, sites = ix["index"].near(lon, lat)
    route = None
    if routes:
        best = sorted(routes.items(), key=lambda kv: (kv[1], "@" in kv[0], kv[0]))
        route = best[0][0].split("@")[0]
        if not db.query("SELECT id FROM routes WHERE tenant_id = ? AND id = ?", (db.current_tenant(), route)):
            route = None            # an abnormal load's line, not a route
    site = min(sites.items(), key=lambda kv: kv[1])[0] if sites else None
    area = None
    for name, a, tier in ix["areas"] or []:
        if tier == "district" and a.contains(lon, lat):
            area = name
            break
    return route, site, area


def in_scheme(lon, lat):
    box = _index()["box"]
    return box is None or (box[0] <= lon <= box[2] and box[1] <= lat <= box[3])


# --------------------------------------------------------------------------- checking what is sent

def _text(v, key, required=False):
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise Refused("Something in the form could not be read. Please try again.")
    t = _CTRL.sub("", v).strip()
    if key != "words" and key != "reply":
        t = t.replace("\n", " ").replace("\r", " ")
    if required and not t:
        raise Refused({"words": "Please say what happened.", "reply": "Type what was said."}.get(key, "Please fill this in."))
    if len(t) > MAX_LEN[key]:
        raise Refused(f"Please keep this to {MAX_LEN[key]:,} characters.")
    if "<" in t or ">" in t:
        raise Refused("Please leave out the < and > signs.")
    return t


def _checked(form, staff=False, today=None):
    """The concern's fields, checked. Raises Refused with a sentence a person reads."""
    f = form if isinstance(form, dict) else {}
    kind = f.get("kind")
    if kind not in KINDS:
        raise Refused("Please pick what kind of concern it is.")
    words = _text(f.get("words"), "words", required=True)
    if LINK_RX.search(words):
        raise Refused("Please leave out web links.")
    today = today or _now().date()
    d = (f.get("happened_on") or "").strip() if isinstance(f.get("happened_on"), str) else ""
    if not DATE_RX.match(d):
        raise Refused("Please give the date it happened.")
    try:
        day = datetime.date.fromisoformat(d)
    except ValueError:
        raise Refused("Please give the date it happened.")
    if day > today + datetime.timedelta(days=1):
        raise Refused("The date is in the future.")
    if day < today - datetime.timedelta(days=366):
        raise Refused("Please report something from the last 12 months.")
    tm = f.get("happened_time") or ""
    if tm and (not isinstance(tm, str) or not TIME_RX.match(tm.strip())):
        raise Refused("Please give the time as hh:mm, or leave it empty.")
    reg = _text(f.get("registration"), "registration")
    if reg and not REG_RX.match(reg):
        raise Refused("A registration has only letters, numbers and spaces.")
    lat, lon = f.get("lat"), f.get("lon")
    route = f.get("route_id") or None
    if lat is not None or lon is not None:
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            raise Refused("The pin could not be read. Please place it again.")
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise Refused("The pin could not be read. Please place it again.")
        if not in_scheme(lon, lat):
            raise Refused("The pin is too far from the scheme's routes. Please place it where it happened.")
    if route is not None:
        if not isinstance(route, str) or not db.query("SELECT id FROM routes WHERE tenant_id = ? AND id = ?",
                                                      (db.current_tenant(), route)):
            raise Refused("That route is not on the map.")
    if lat is None and route is None:
        raise Refused("Please place a pin on the map where it happened.")
    wants = bool(f.get("wants_reply"))
    name = _text(f.get("name"), "name")
    email = _text(f.get("email"), "email").lower()
    phone = _text(f.get("phone"), "phone")
    if email and not EMAIL_RX.match(email):
        raise Refused("The email address does not look right.")
    if phone and not PHONE_RX.match(phone):
        raise Refused("The phone number does not look right.")
    if wants and not (email or phone):
        raise Refused("To get a reply, give an email address or a phone number.")
    if not wants:
        name = email = phone = ""      # Q (card 2): contact details only when a reply is asked for
    source = f.get("source") if staff else "map"
    if staff and source not in ("email", "phone", "person"):
        raise Refused("Say how it came in: email, phone or in person.")
    return {"kind": kind, "words": words, "happened_on": d, "happened_time": tm.strip() if tm else None,
            "registration": reg.upper() or None, "lat": lat, "lon": lon, "route_id": route, "wants_reply": 1 if wants else 0,
            "name": name or None, "email": email or None, "phone": phone or None, "source": source}


# --------------------------------------------------------------------------- storing

def _count(where, params):
    rows = db.query("SELECT COUNT(*) AS n FROM concerns WHERE tenant_id = ? AND " + where,
                    (db.current_tenant(),) + tuple(params))
    return int(rows[0]["n"]) if rows else 0


def over_limit(iph, now=None):
    """The sentence to answer with when a limit is reached, else None."""
    now = now or _now()
    hour, day = _iso(now - datetime.timedelta(hours=1)), _iso(now - datetime.timedelta(days=1))
    if iph and (_count("ip_hash = ? AND received_at >= ?", (iph, hour)) >= PER_IP_PER_HOUR
                or _count("ip_hash = ? AND received_at >= ?", (iph, day)) >= PER_IP_PER_DAY):
        return "Too many reports from here today."
    if _count("source = 'map' AND received_at >= ?", (day,)) >= PER_TENANT_PER_DAY:
        return "The form is busy just now."
    return None


def _next_id():
    rows = db.query("SELECT id FROM concerns WHERE tenant_id = ?", (db.current_tenant(),))
    n = 0
    for r in rows:
        m = re.match(r"^C-(\d+)$", str(r["id"]))
        if m:
            n = max(n, int(m.group(1)))
    return f"C-{n + 1:04d}"


def _event(at, by, what, words=None):
    e = {"at": at, "by": by, "what": what}
    if words:
        e["words"] = words
    return e


def _insert(c, now, by, iph=None, fictional=0):
    route, site, area = (None, None, None)
    if c["lat"] is not None:
        route, site, area = place_of(c["lon"], c["lat"])
    if c["route_id"]:
        route = c["route_id"]
    at = _iso(now)
    history = [_event(at, by, "received" if c["source"] == "map" else f"added from {SOURCES[c['source']]}")]
    for attempt in range(3):
        cid = _next_id()
        try:
            db.execute(
                "INSERT INTO concerns (tenant_id, id, received_at, source, kind, happened_on, happened_time, lat, lon, "
                "route_id, route_set_by, location_id, area_name, words, registration, wants_reply, name, email, phone, "
                "ip_hash, status, history_json, fictional, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (db.current_tenant(), cid, at, c["source"], c["kind"], c["happened_on"], c["happened_time"],
                 c["lat"], c["lon"], route, "pin" if route and not c["route_id"] else ("form" if route else None), site,
                 area, c["words"], c["registration"], c["wants_reply"], c["name"], c["email"], c["phone"], iph, "new",
                 json.dumps(history), int(fictional), at))
            return cid
        except Exception:
            if attempt == 2:
                raise
    return None


def submit(form, ip_hash, now=None):
    """
    The public map's send. Returns {"ok": True, "ref": "C-0042"} — or {"ok": True, "ref": None} for the trap field
    (thanked, nothing stored). Raises Refused (the sentence, 422 / 429 / 404).
    """
    now = now or _now()
    st = settings()
    if not st["form"]:
        raise Refused("This scheme does not take concerns on the map. Please use the email address.", 404)
    f = form if isinstance(form, dict) else {}
    maybe_sweep(now)
    hp = f.get(HONEYPOT)
    if hp and (not isinstance(hp, str) or hp.strip()):
        return {"ok": True, "ref": None}
    c = _checked(f, today=now.date())
    # Q12: outside the demo the form carries the privacy notice's tick, and the server holds it to that
    if not st["demo"] and f.get("privacy_ok") is not True:
        raise Refused("Please tick that you have read the privacy notice.")
    msg = over_limit(ip_hash, now)
    if msg:
        raise Refused(msg + (f" Please email {st['email']}." if st["email"] else ""), 429)
    cid = _insert(c, now, "the public map", iph=ip_hash)
    return {"ok": True, "ref": cid}


def add_by_staff(body, by, now=None):
    """One that came in by email, phone or in person, typed by a planner or admin."""
    now = now or _now()
    c = _checked(body, staff=True, today=now.date())
    return _insert(c, now, by)


# --------------------------------------------------------------------------- reading (staff)

COLS = ("id, received_at, source, kind, happened_on, happened_time, lat, lon, route_id, route_set_by, location_id, "
        "area_name, words, registration, wants_reply, name, email, phone, status, first_reply_at, closed_at, outcome, "
        "personal_deleted_at, contact_deleted_at, history_json, fictional, updated_at")


def _row(r, reply_days=None):
    h = []
    try:
        h = json.loads(r.get("history_json") or "[]")
    except (TypeError, ValueError):
        h = []
    first = working_days(r.get("received_at"), r.get("first_reply_at"))
    waited = working_days(r.get("received_at"), _iso(_now())) if r.get("status") == "new" else None
    late = bool(reply_days and r.get("wants_reply") and not r.get("first_reply_at") and r.get("status") != "closed"
                and waited is not None and waited > float(reply_days))
    return {
        "id": r["id"], "received_at": r["received_at"], "source": r["source"], "source_text": SOURCES.get(r["source"], r["source"]),
        "kind": r["kind"], "kind_text": KINDS.get(r["kind"], r["kind"]),
        "happened_on": r["happened_on"], "happened_time": r.get("happened_time"),
        "lat": r.get("lat"), "lon": r.get("lon"), "route_id": r.get("route_id"), "route_set_by": r.get("route_set_by"),
        "location_id": r.get("location_id"), "area_name": r.get("area_name"),
        "words": r.get("words"), "registration": r.get("registration"), "wants_reply": bool(r.get("wants_reply")),
        "name": r.get("name"), "email": r.get("email"), "phone": r.get("phone"),
        "status": r["status"], "first_reply_at": r.get("first_reply_at"), "closed_at": r.get("closed_at"),
        "outcome": r.get("outcome"), "outcome_text": OUTCOMES.get(r.get("outcome") or "", None),
        "first_reply_days": first, "close_days": working_days(r.get("received_at"), r.get("closed_at")),
        "waiting_days": waited, "late": late,
        "personal_deleted_at": r.get("personal_deleted_at"), "contact_deleted_at": r.get("contact_deleted_at"),
        "history": h, "fictional": bool(r.get("fictional")),
    }


def one(cid):
    rows = db.query(f"SELECT {COLS} FROM concerns WHERE tenant_id = ? AND id = ?", (db.current_tenant(), cid))
    if not rows:
        raise Refused("That concern is not here.", 404)
    return _row(rows[0], settings()["reply_days"])


def listing(status=None, kind=None, route=None, month=None, now=None):
    """The staff list, newest first, and the counts the page heads with."""
    maybe_sweep(now)
    clauses, params = [], []
    if status == "open":
        clauses.append("status != 'closed'")
    elif status in STATUSES:
        clauses.append("status = ?"); params.append(status)
    if kind in KINDS:
        clauses.append("kind = ?"); params.append(kind)
    if route:
        clauses.append("route_id = ?"); params.append(route)
    if month and re.match(r"^\d{4}-\d{2}$", str(month)):
        clauses.append("received_at LIKE ?"); params.append(f"{month}%")
    sql = f"SELECT {COLS} FROM concerns WHERE tenant_id = ?" + "".join(" AND " + c for c in clauses) + \
        " ORDER BY received_at DESC, id DESC"
    st = settings()
    rows = [_row(r, st["reply_days"]) for r in db.query(sql, (db.current_tenant(),) + tuple(params))]
    return {"concerns": rows, "new": new_count(), "kinds": KINDS, "outcomes": OUTCOMES, "settings": st,
            "routes": route_names()}


def route_names():
    """Every route as {id, words: "Origin → Destination"} for the page's route picker and its Where column."""
    names = {r["id"]: r["name"] for r in db.query("SELECT id, name FROM locations WHERE tenant_id = ?", (db.current_tenant(),))}
    rows = db.query("SELECT id, origin_id, dest_id FROM routes WHERE tenant_id = ?", (db.current_tenant(),))
    out = [{"id": r["id"], "words": f"{names.get(r['origin_id'], r['origin_id'])} → {names.get(r['dest_id'], r['dest_id'])}"}
           for r in rows]
    return sorted(out, key=lambda x: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(x["id"]))])


def new_count():
    return _count("status = 'new'", ())


# --------------------------------------------------------------------------- what staff do

def _load(cid):
    rows = db.query("SELECT * FROM concerns WHERE tenant_id = ? AND id = ?", (db.current_tenant(), cid))
    if not rows:
        raise Refused("That concern is not here.", 404)
    r = rows[0]
    try:
        r["history"] = json.loads(r.get("history_json") or "[]")
    except (TypeError, ValueError):
        r["history"] = []
    return r


def _save(cid, sets, history, now):
    cols = ", ".join(f"{k} = ?" for k in sets)
    db.execute("UPDATE concerns SET {}, history_json = ?, updated_at = ? WHERE tenant_id = ? AND id = ?".format(cols),
               tuple(sets.values()) + (json.dumps(history), _iso(now), db.current_tenant(), cid))


def reply(cid, words, at, by, now=None):
    """Record what was said and when. The first one sets the KPI clock and the status to Answered."""
    now = now or _now()
    r = _load(cid)
    if r["status"] == "closed":
        raise Refused("Reopen the concern to record a reply.", 409)
    words = _text(words, "reply", required=True)
    when = _parse(at) if at else now
    if when is None:
        raise Refused("Give the date and time of the reply.")
    rec = _parse(r["received_at"])
    if when > now + datetime.timedelta(minutes=5):
        raise Refused("The reply time is in the future.")
    if rec and when < rec:
        raise Refused("The reply time is before the concern came in.")
    h = r["history"] + [_event(_iso(when), by, "reply", words)]
    sets = {"status": "answered"}
    if not r.get("first_reply_at") or _parse(r["first_reply_at"]) > when:
        sets["first_reply_at"] = _iso(when)
    _save(cid, sets, h, now)
    return one(cid)


def close(cid, outcome, by, now=None):
    now = now or _now()
    if outcome not in OUTCOMES:
        raise Refused("Pick how the concern was closed.")
    r = _load(cid)
    if r["status"] == "closed":
        raise Refused("The concern is closed already.", 409)
    h = r["history"] + [_event(_iso(now), by, "closed", OUTCOMES[outcome])]
    _save(cid, {"status": "closed", "closed_at": _iso(now), "outcome": outcome}, h, now)
    return one(cid)


def reopen(cid, by, now=None):
    now = now or _now()
    r = _load(cid)
    if r["status"] != "closed":
        raise Refused("The concern is open already.", 409)
    if r.get("personal_deleted_at"):
        raise Refused("Its personal details are deleted; it cannot be reopened.", 409)
    h = r["history"] + [_event(_iso(now), by, "reopened")]
    _save(cid, {"status": "answered" if r.get("first_reply_at") else "new", "closed_at": None, "outcome": None}, h, now)
    return one(cid)


def set_route(cid, route_id, by, now=None):
    now = now or _now()
    r = _load(cid)
    if route_id and not db.query("SELECT id FROM routes WHERE tenant_id = ? AND id = ?", (db.current_tenant(), route_id)):
        raise Refused("That route is not on the map.")
    h = r["history"] + [_event(_iso(now), by, f"route set to {route_id}" if route_id else "route cleared")]
    _save(cid, {"route_id": route_id or None, "route_set_by": "staff" if route_id else None}, h, now)
    return one(cid)


def _forget_sets():
    return {"name": None, "email": None, "phone": None, "words": None, "registration": None, "happened_time": None}


def _rounded(r):
    return {"lat": round(r["lat"], 3) if r.get("lat") is not None else None,
            "lon": round(r["lon"], 3) if r.get("lon") is not None else None}


def _scrub_history(h):
    return [{k: v for k, v in e.items() if k != "words"} for e in h]


def forget(cid, by, now=None):
    """"Delete the personal details now" (an erasure request): contact, text, registration, time of day and reply notes;
    the pin rounded. Kind, date, route, status and dates stay for the figures."""
    now = now or _now()
    r = _load(cid)
    if r.get("personal_deleted_at"):
        raise Refused("Its personal details are deleted already.", 409)
    h = _scrub_history(r["history"]) + [_event(_iso(now), by, "personal details deleted")]
    sets = dict(_forget_sets(), **_rounded(r), personal_deleted_at=_iso(now), contact_deleted_at=_iso(now))
    _save(cid, sets, h, now)
    return one(cid)


# --------------------------------------------------------------------------- the clean-up (card 9)

_SWEPT = {"at": None, "tenant": None}


def sweep(now=None):
    """Apply card 9 to every concern of this scheme. Returns what it did (counts). Safe to run any time."""
    now = now or _now()
    keep = settings()["keep_months"]
    tenant = db.current_tenant()
    done = {"personal": 0, "contact": 0, "spam": 0, "ip": 0}
    rows = db.query("SELECT id, status, outcome, received_at, closed_at, lat, lon, personal_deleted_at, contact_deleted_at, "
                    "ip_hash, history_json FROM concerns WHERE tenant_id = ?", (tenant,))
    for r in rows:
        rec, closed = _parse(r["received_at"]), _parse(r.get("closed_at"))
        if r["status"] == "closed" and r.get("outcome") == "spam" and closed and closed <= now - datetime.timedelta(days=SPAM_DAYS):
            db.execute("DELETE FROM concerns WHERE tenant_id = ? AND id = ?", (tenant, r["id"]))
            done["spam"] += 1
            continue
        if r.get("ip_hash") and rec and rec <= now - datetime.timedelta(days=IP_DAYS):
            db.execute("UPDATE concerns SET ip_hash = NULL WHERE tenant_id = ? AND id = ?", (tenant, r["id"]))
            done["ip"] += 1
        if (r["status"] == "closed" and closed and not r.get("personal_deleted_at")
                and add_months(closed, keep) <= now):
            try:
                h = _scrub_history(json.loads(r.get("history_json") or "[]"))
            except (TypeError, ValueError):
                h = []
            h.append(_event(_iso(now), "Wayscope", f"personal details deleted ({keep} months after closing)"))
            sets = dict(_forget_sets(), **_rounded(r), personal_deleted_at=_iso(now), contact_deleted_at=_iso(now))
            _save(r["id"], sets, h, now)
            done["personal"] += 1
        elif (r["status"] != "closed" and rec and not r.get("contact_deleted_at")
              and add_months(rec, OPEN_STOP_MONTHS) <= now):
            try:
                h = json.loads(r.get("history_json") or "[]")
            except (TypeError, ValueError):
                h = []
            h.append(_event(_iso(now), "Wayscope", f"contact details deleted ({OPEN_STOP_MONTHS} months open)"))
            _save(r["id"], {"name": None, "email": None, "phone": None, "contact_deleted_at": _iso(now)}, h, now)
            done["contact"] += 1
    _SWEPT.update(at=now, tenant=tenant)
    return done


def maybe_sweep(now=None):
    """sweep() at most once an hour per process and scheme. Never raises (a failed clean-up is logged and tried again)."""
    now = now or _now()
    if _SWEPT["tenant"] == db.current_tenant() and _SWEPT["at"] and (now - _SWEPT["at"]).total_seconds() < SWEEP_EVERY_S:
        return None
    try:
        return sweep(now)
    except Exception as e:  # noqa: BLE001
        print(f"🧹 concerns clean-up failed: {e.__class__.__name__}: {str(e)[:200]}")
        return None


# --------------------------------------------------------------------------- the staff alert (Q7)

def alert_message(cid, settings_mail, now=None):
    """The email to the scheme's report address for a new concern: kind, route, reference, a link. Nothing personal."""
    from email.message import EmailMessage
    import users
    st = settings()
    if not st["email"]:
        return None
    rows = db.query("SELECT kind, route_id, source FROM concerns WHERE tenant_id = ? AND id = ?", (db.current_tenant(), cid))
    if not rows:
        return None
    r = rows[0]
    where = f" on route {r['route_id']}" if r.get("route_id") else ""
    msg = EmailMessage()
    msg["Subject"] = f"New concern {cid}: {KINDS.get(r['kind'], 'a concern')}"
    msg["From"] = settings_mail["DEMO_FROM"]
    msg["To"] = st["email"]
    msg["Reply-To"] = settings_mail["reply_to"]
    msg.set_content(f"A new concern came in on {SOURCES.get(r['source'], 'the public map')}: {cid}, "
                    f"{KINDS.get(r['kind'], 'a concern')}{where}.\n\nOpen it in Wayscope: {users.app_url()}/#concerns\n\n"
                    "This email carries no personal details.\n\nWayscope\n")
    return msg


def send_alert(cid):
    """The background send. Never raises."""
    try:
        import demo_request
        import users
        s = users.mail_settings()
        if not s:
            return False
        msg = alert_message(cid, s)
        if msg is None:
            return False
        demo_request.send(msg, s)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"📮 concern alert {cid} not sent: {e.__class__.__name__}: {str(e)[:200]}")
        return False

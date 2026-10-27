"""
abnormal.py — the ABNORMAL LOADS a tenant plans: the store, the settings and the read model. Wayscope, 22 Oct 2026
(S16 / B5 / P11; the rules themselves are abnormal_rules.py; the research is notes/abnormal-loads-research-1016.md).

WHAT AN ABNORMAL LOAD IS HERE (D66a)
------------------------------------
Its own planned movement, never a forecast line: one item with its own typed size (width, height, length, projections,
gross weight, heaviest axle, axle count), its own window (two dates and a day / night band), its own route (phase 2:
HERE at the typed size, D67) and its own status — pending → approved → notified → moved, or withdrawn (D68: the public
map shows approved-or-later movements only). A planner types it on Plan → Abnormal loads; a team login may plan its own
team's; a planner or an admin approves, like a forecast line.

WHAT IS WORKED OUT, AND HOW FIRM (D69)
--------------------------------------
Every read decorates a movement with abnormal_rules.advice(): the class, the permission (VR1 / Special Order) and its
lead time, the notices and the "notify by" date on the right calendar with the bank holidays, the attendant, the
markers, the speeds, the escort the National Highways code expects, the height warnings, and the rail flags
(NOTICE_DUE, NOTICE_LATE, SO_LEAD_TIME). All of it is ADVICE labelled "check with the haulier"; nothing here says a
movement meets the rules or is approved by anyone outside this scheme. Nothing derived is stored.

COUNTED APART (D70, D71): an abnormal load is never added to the lorry counts, the CLP caps, the gate capacity or the
carbon totals. The screens that show it say so.

THE SETTINGS
------------
* The bank holidays (D74): the gov.uk feed (https://www.gov.uk/bank-holidays.json, OGL) — a copy shipped in
  backend/data/bank_holidays.json (fetched 22 Oct 2026, dates to Dec 2028) and, once a planner presses "Fetch now",
  the live feed stored in the tenant's config row `bank_holidays` (so it travels in the package and needs no network
  on a page read). Never fetched on a page view.
* The police time bans (D72): a per-tenant table a planner types (force, days, hours, note), config row
  `police_time_bans`, EMPTY by default — forces differ and only two were confirmed from a primary source, so none is
  built in. A typed ban that touches a movement's time band is said on the movement.
* The nation (planning.abnormal_nation, Config → Planning): whose bank holidays the C&U calendar leaves out
  (England and Wales unless set to Scotland). The STGO calendar leaves out every GB public holiday whatever this says.

Nothing here calls HERE, Mapbox or any external service except refresh_holidays(), which a planner presses.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.request

import abnormal_rules as rules
import access
import db
import gate_hours

HOLIDAYS_URL = "https://www.gov.uk/bank-holidays.json"
HOLIDAYS_SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bank_holidays.json")
HOLIDAYS_KEY = "bank_holidays"
TIME_BANS_KEY = "police_time_bans"
HOLIDAY_DIVISIONS = ("england-and-wales", "scotland", "northern-ireland")
MAX_TIME_BANS = 12
TEXT_MAX = 400

#: the fields a person types, in the order the form shows them (the validator reads this list; the columns match db.py)
TYPED_FIELDS = ("name", "ipt", "origin_id", "origin_gate_id", "dest_id", "dest_gate_id", "date_from", "date_to",
                "time_band", "movements", "return_abnormal", "width_m", "height_m", "length_m", "rigid_length_m",
                "proj_front_m", "proj_rear_m", "proj_side_m", "gross_t", "max_axle_t", "axle_driving", "axle_count",
                "axle_spacings_m", "vehicle_type", "cu_vehicle", "indivisible", "escort_planned", "esdal_ref",
                "vr1_ref", "so_ref", "applied_on", "notified_on", "note")
REQUIRED_FIGURES = ("width_m", "height_m", "length_m", "gross_t")
#: 22 Oct 2026: the scheme's staff view for a caller with no account to scope by — the map page's STAFF gate cookie
#: (a code sign-in sends no header there) and the public map's endpoint, which picks the approved-or-later movements itself
STAFF_VIEW = {"role": "planner", "ipt": None, "label": "Staff (map)"}
PUBLIC_STATUSES = ("approved", "notified", "moved")       # D68: what the public map may show
BOOL_FIELDS = ("return_abnormal", "axle_driving", "cu_vehicle", "indivisible")
NUMBER_FIELDS = ("width_m", "height_m", "length_m", "rigid_length_m", "proj_front_m", "proj_rear_m", "proj_side_m",
                 "gross_t", "max_axle_t")
DATE_FIELDS = ("date_from", "date_to", "applied_on", "notified_on")
TEXT_FIELDS = ("name", "esdal_ref", "vr1_ref", "so_ref", "note", "axle_spacings_m")
#: sane ceilings so a slipped decimal point is refused in words rather than classed as a Special Order
FIGURE_MAX = {"width_m": 12.0, "height_m": 10.0, "length_m": 120.0, "rigid_length_m": 120.0, "proj_front_m": 30.0,
              "proj_rear_m": 30.0, "proj_side_m": 5.0, "gross_t": 1000.0, "max_axle_t": 60.0}

#: who may move a movement to which status (abnormal_rules.STATUSES); approving and reopening are a planner's
TRANSITIONS = {
    "pending": ("approved", "withdrawn"),
    "approved": ("notified", "moved", "withdrawn", "pending"),
    "notified": ("moved", "withdrawn", "approved"),
    "moved": ("notified",),
    "withdrawn": ("pending",),
}
PLANNER_ONLY = {"approved", "pending"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _today(today=None):
    if isinstance(today, datetime.date):
        return today
    if today:
        try:
            return datetime.date.fromisoformat(str(today)[:10])
        except ValueError:
            pass
    return datetime.date.today()


# --------------------------------------------------------------------------- #
#  Settings: the bank holidays and the police time bans                        #
# --------------------------------------------------------------------------- #
def _config_row(key):
    rows = db.query("SELECT value, updated_by, updated_at FROM config WHERE tenant_id = ? AND key = ?",
                    (db.current_tenant(), key))
    return rows[0] if rows else None


def _config_set(key, value, by=None):
    val = json.dumps(value, ensure_ascii=False)
    if _config_row(key):
        db.execute("UPDATE config SET value = ?, updated_by = ?, updated_at = ? WHERE tenant_id = ? AND key = ?",
                   (val, by, _now(), db.current_tenant(), key))
    else:
        db.execute("INSERT INTO config (tenant_id, key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)",
                   (db.current_tenant(), key, val, by, _now()))


def feed_problems(feed):
    """Why a candidate bank-holiday feed cannot be used, as sentences. Empty = usable."""
    p = []
    if not isinstance(feed, dict):
        return ["the feed must be a JSON object of divisions"]
    for div in ("england-and-wales", "scotland"):
        ev = (feed.get(div) or {}).get("events") if isinstance(feed.get(div), dict) else None
        if not isinstance(ev, list) or not ev:
            p.append(f"the feed has no events for {div}")
            continue
        bad = [e for e in ev if not isinstance(e, dict) or rules._date(e.get("date")) is None]
        if bad:
            p.append(f"{div}: {len(bad)} event(s) without a date")
    return p


def seed_feed():
    with open(HOLIDAYS_SEED, encoding="utf-8") as fh:
        return json.load(fh)


def holiday_feed():
    """The stored gov.uk feed when a planner has fetched one, else the shipped copy. Never the network."""
    row = _config_row(HOLIDAYS_KEY)
    if row:
        try:
            doc = json.loads(row["value"])
            if not feed_problems(doc.get("feed")):
                return doc["feed"]
        except Exception:
            pass
    return seed_feed()


def holiday_status():
    """Where the holidays come from, when, and how far they run — what the settings card says."""
    row = _config_row(HOLIDAYS_KEY)
    source, fetched_at, by, feed = "seed", None, None, None
    if row:
        try:
            doc = json.loads(row["value"])
            if not feed_problems(doc.get("feed")):
                source, fetched_at, by, feed = "fetched", doc.get("fetched_at"), row.get("updated_by"), doc["feed"]
        except Exception:
            pass
    if feed is None:
        feed = seed_feed()
    dates = sorted(rules.holiday_dates(feed, ("england-and-wales", "scotland")))
    return {"source": source, "fetched_at": fetched_at, "by": by, "url": HOLIDAYS_URL,
            "seed_fetched_on": "2026-10-22",
            "from": dates[0].isoformat() if dates else None, "to": dates[-1].isoformat() if dates else None,
            "count": {d: len((feed.get(d) or {}).get("events") or []) for d in HOLIDAY_DIVISIONS if feed.get(d)},
            "words": ("GOV.UK bank holidays (Open Government Licence)" + (f", fetched {fetched_at[:10]}" if fetched_at else
                      ", the copy shipped with Wayscope (fetched 22 Oct 2026)")
                      + (f"; dates to {dates[-1].isoformat()}" if dates else ""))}


def refresh_holidays(by=None, fetch=None):
    """Fetch the gov.uk feed and store it for this tenant. `fetch` (tests) replaces the HTTP read. Never raises."""
    try:
        if fetch is not None:
            doc = fetch()
        else:
            req = urllib.request.Request(HOLIDAYS_URL, headers={"User-Agent": "Wayscope abnormal loads (bank holidays)"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                doc = json.load(resp)
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"gov.uk could not be read: {getattr(e, 'reason', e)}"}
    except Exception as e:  # noqa: BLE001 — the answer is the error, never a crash
        return {"ok": False, "error": f"gov.uk could not be read: {str(e)[:200]}"}
    probs = feed_problems(doc)
    if probs:
        return {"ok": False, "error": "the feed did not look like gov.uk's: " + "; ".join(probs)}
    _config_set(HOLIDAYS_KEY, {"fetched_at": _now(), "source": HOLIDAYS_URL, "feed": doc}, by=by)
    return {"ok": True, "status": holiday_status()}


def nation(factors=None):
    """planning.abnormal_nation, else England and Wales."""
    try:
        import config as _config
        import conversions as _conversions
        doc = factors if factors is not None else _config.load(_conversions)
        v = ((doc or {}).get("planning") or {}).get("abnormal_nation")
        return v if v in ("england-and-wales", "scotland") else "england-and-wales"
    except Exception:
        return "england-and-wales"


def time_bans():
    row = _config_row(TIME_BANS_KEY)
    if not row:
        return []
    try:
        v = json.loads(row["value"])
        return v if isinstance(v, list) else []
    except Exception:
        return []


def time_ban_problems(bans):
    """Why a typed list of police time bans cannot be saved. Empty = fine."""
    p = []
    if not isinstance(bans, list):
        return ["the time bans must be a list"]
    if len(bans) > MAX_TIME_BANS:
        p.append(f"at most {MAX_TIME_BANS} time bans")
    for i, b in enumerate(bans):
        n = i + 1
        if not isinstance(b, dict):
            p.append(f"ban {n}: not an object")
            continue
        if not str(b.get("force") or "").strip():
            p.append(f"ban {n}: name the police force")
        elif len(str(b.get("force"))) > TEXT_MAX:
            p.append(f"ban {n}: the force's name is too long")
        for k in ("from", "to"):
            hp = gate_hours.hhmm_problem(b.get(k))
            if hp:
                p.append(f"ban {n}: {k} {hp}")
        if gate_hours.minutes_of(b.get("from")) is not None and gate_hours.minutes_of(b.get("from")) == gate_hours.minutes_of(b.get("to")):
            p.append(f"ban {n}: from and to are the same time")
        dp = gate_hours.days_problem(b.get("days")) if b.get("days") not in (None, "") else None
        if dp:
            p.append(f"ban {n}: {dp}")
        if b.get("note") is not None and len(str(b.get("note"))) > TEXT_MAX:
            p.append(f"ban {n}: the note is too long")
    return p


def set_time_bans(bans, by=None):
    probs = time_ban_problems(bans)
    if probs:
        return {"ok": False, "problems": probs}
    clean = []
    for b in bans:
        clean.append({"force": str(b.get("force")).strip(), "days": gate_hours.clean_days(b.get("days")) or "1111100",
                      "from": str(b.get("from")).strip(), "to": str(b.get("to")).strip(),
                      "note": (str(b.get("note")).strip() or None) if b.get("note") is not None else None})
    _config_set(TIME_BANS_KEY, clean, by=by)
    return {"ok": True, "time_bans": clean}


def settings():
    """What the page's settings card shows."""
    return {"holidays": holiday_status(), "time_bans": time_bans(), "nation": nation(),
            "calendars": rules.CALENDAR_WORDS, "time_bands": rules.TIME_BANDS, "max_time_bans": MAX_TIME_BANS}


# --------------------------------------------------------------------------- #
#  The movements                                                               #
# --------------------------------------------------------------------------- #
def _next_id():
    existing = {r["id"] for r in db.query("SELECT id FROM abnormal_loads WHERE tenant_id = ?", (db.current_tenant(),))}
    i = 1
    while f"AL{i:03d}" in existing:
        i += 1
    return f"AL{i:03d}"


def _locations():
    return {l["id"]: l for l in db.query("SELECT id, name, loc_type, lat, lon FROM locations WHERE tenant_id = ?",
                                          (db.current_tenant(),))}


def _gates():
    try:
        return {g["id"]: g for g in db.query(
            "SELECT id, location_id, name, direction, active FROM location_gates WHERE tenant_id = ?", (db.current_tenant(),))}
    except Exception:
        return {}


def problems(payload, acc=None, existing=None):
    """Why a typed movement cannot be saved, as sentences a person reads. Empty = fine."""
    p = []
    v = dict(existing or {})
    v.update({k: payload[k] for k in TYPED_FIELDS if k in (payload or {})})
    if not str(v.get("name") or "").strip():
        p.append("say what the load is")
    for k in TEXT_FIELDS:
        if v.get(k) is not None and len(str(v.get(k))) > TEXT_MAX:
            p.append(f"{k.replace('_', ' ')} is too long (at most {TEXT_MAX} characters)")
    for k in REQUIRED_FIGURES:
        if rules._num(v.get(k)) is None:
            p.append(f"type the {k.replace('_m', '').replace('_t', '')} ({'metres' if k.endswith('_m') else 'tonnes'})")
    for k in NUMBER_FIELDS:
        x = v.get(k)
        if x in (None, ""):
            continue
        n = rules._num(x)
        if n is None:
            p.append(f"{k.replace('_m', '').replace('_t', '').replace('_', ' ')} must be a number, 0 or more")
        elif n > FIGURE_MAX[k]:
            p.append(f"{k.replace('_m', '').replace('_t', '').replace('_', ' ')} {n:g} is more than {FIGURE_MAX[k]:g}: check the figure")
    if v.get("axle_count") not in (None, "") and rules._int(v.get("axle_count")) is None:
        p.append("axle count must be a whole number, 1 or more")
    if v.get("axle_spacings_m") not in (None, ""):
        sp = rules.spacings_of(v.get("axle_spacings_m"))
        if not sp:
            p.append("axle spacings: a list of metres between adjacent axles, like 1.36, 1.36, 1.8")
        elif rules._int(v.get("axle_count")) and len(sp) != rules._int(v.get("axle_count")) - 1:
            p.append(f"axle spacings: {rules._int(v.get('axle_count'))} axles have {rules._int(v.get('axle_count')) - 1} spacings, not {len(sp)}")
    mv = v.get("movements")
    if mv not in (None, "") and rules._int(mv) is None:
        p.append("movements must be a whole number, 1 or more")
    if v.get("time_band") not in (None, "", "day", "night"):
        p.append("time band must be day or night")
    if v.get("vehicle_type") not in (None, "") and v.get("vehicle_type") not in rules.VEHICLE_TYPES:
        p.append("vehicle type must be one of " + ", ".join(rules.VEHICLE_TYPES))
    if v.get("escort_planned") not in (None, "") and v.get("escort_planned") not in rules.ESCORTS:
        p.append("escort planned must be one of " + ", ".join(rules.ESCORTS))
    for k in DATE_FIELDS:
        if v.get(k) not in (None, "") and rules._date(v.get(k)) is None:
            p.append(f"{k.replace('_', ' ')} must be a date (YYYY-MM-DD)")
    d_from, d_to = rules._date(v.get("date_from")), rules._date(v.get("date_to"))
    if not d_from:
        p.append("type the earliest move date")
    if d_from and d_to and d_to < d_from:
        p.append("the latest move date is before the earliest")
    locs = _locations()
    for k, word in (("origin_id", "from"), ("dest_id", "to")):
        if not v.get(k):
            p.append(f"pick where the load moves {word}")
        elif v.get(k) not in locs:
            p.append(f"the {word} location {v.get(k)!r} does not exist")
    if v.get("origin_id") and v.get("dest_id") and v.get("origin_id") == v.get("dest_id"):
        p.append("from and to are the same place")
    gates = _gates()
    for k, loc_key in (("origin_gate_id", "origin_id"), ("dest_gate_id", "dest_id")):
        gid = v.get(k)
        if gid in (None, ""):
            continue
        g = gates.get(gid)
        if not g:
            p.append(f"gate {gid!r} does not exist")
        elif v.get(loc_key) and g["location_id"] != v.get(loc_key):
            p.append(f"gate {g['name']} is not a gate of that location")
    return p


def _clean(payload, existing=None):
    """The typed fields, cleaned for the row: numbers as floats / ints, bools as bools, blanks as None."""
    out = {}
    for k in TYPED_FIELDS:
        if k not in (payload or {}):
            continue
        x = payload[k]
        if k in BOOL_FIELDS:
            out[k] = bool(x) if not isinstance(x, str) else x.strip().lower() in ("1", "true", "yes", "y", "on")
        elif k in NUMBER_FIELDS:
            out[k] = rules._num(x)
        elif k == "axle_count":
            out[k] = rules._int(x)
        elif k == "movements":
            out[k] = rules._int(x) or 1
        elif k == "axle_spacings_m":
            sp = rules.spacings_of(x)
            out[k] = ", ".join(f"{s:g}" for s in sp) if sp else None
        elif k in DATE_FIELDS:
            d = rules._date(x)
            out[k] = d.isoformat() if d else None
        elif k == "time_band":
            out[k] = x if x in ("day", "night") else "day"
        else:
            out[k] = (str(x).strip() or None) if x is not None else None
    return out


def get(movement_id):
    rows = db.query("SELECT * FROM abnormal_loads WHERE tenant_id = ? AND id = ?", (db.current_tenant(), movement_id))
    return rows[0] if rows else None


def _visible(row, acc):
    return access.line_visible({"ipt": row.get("ipt")}, acc)


def create(payload, acc, by=None):
    """A new movement, status pending. Returns {ok, movement} or {ok: False, problems}."""
    ipt, err = access.ipt_for_save((payload or {}).get("ipt"), acc)
    body = dict(payload or {})
    body["ipt"] = ipt
    probs = problems(body, acc)
    if err:
        # the access module's words name the slot; a person reads "team" (taxonomy's rule)
        probs.insert(0, "pick which team the movement belongs to" if "required" in err else err)
    if probs:
        return {"ok": False, "problems": probs}
    row = _clean(body)
    row["id"] = _next_id()
    row["status"] = "pending"
    row["created_by"] = row["updated_by"] = by
    row["created_at"] = row["updated_at"] = _now()
    cols = list(row.keys())
    db.execute(f"INSERT INTO abnormal_loads (tenant_id, {', '.join(cols)}) VALUES (?, {', '.join('?' for _ in cols)})",
               [db.current_tenant()] + [row[c] for c in cols])
    return {"ok": True, "movement": decorate(get(row["id"]))}


def update(movement_id, payload, acc, by=None):
    """Change the typed fields that were sent. A team login may change its own team's movements; its team is never
    changed by it. Returns {ok, movement} or {ok: False, problems} or {ok: False, error}."""
    row = get(movement_id)
    if not row or not _visible(row, acc):
        return {"ok": False, "error": "no such abnormal load"}
    body = {k: v for k, v in (payload or {}).items() if k in TYPED_FIELDS}
    if "ipt" in body:
        if access.ipt_scope(acc):
            body["ipt"] = access.ipt_scope(acc)
        else:
            got = access.canonical_ipt(body["ipt"])
            if not got:
                return {"ok": False, "problems": ["pick which team the movement belongs to"]}
            body["ipt"] = got
    probs = problems(body, acc, existing=row)
    if probs:
        return {"ok": False, "problems": probs}
    vals = _clean(body)
    if not vals:
        return {"ok": True, "movement": decorate(row)}
    merged = {k: row.get(k) for k in TYPED_FIELDS}
    merged.update(vals)
    merged["updated_by"], merged["updated_at"] = by, _now()
    _write_typed(movement_id, merged)
    # 22 Oct 2026 (phase 2): a changed end, gate or size makes a stored line stale — it is dropped, never kept
    # under figures it was not drawn for (the typed pinch-point rows stay)
    import abnormal_route as _ar
    if row.get("geometry_json") and any(k in vals and vals[k] != row.get(k) for k in _ar.ROUTE_FIELDS):
        _ar.clear_route(movement_id, by=by)
    return {"ok": True, "movement": decorate(get(movement_id))}


# every typed column written whole (the row merged first), in ONE literal statement: the tenant audit reads the
# statement as text, and a SET list built at run time would hide the WHERE from it. _UPDATE_COLS is asserted below to
# be exactly the columns the literal names, in order.
_UPDATE_COLS = TYPED_FIELDS + ("updated_by", "updated_at")
_TYPED_UPDATE = (
    "UPDATE abnormal_loads SET name = ?, ipt = ?, origin_id = ?, origin_gate_id = ?, dest_id = ?, "
    "dest_gate_id = ?, date_from = ?, date_to = ?, time_band = ?, movements = ?, return_abnormal = ?, "
    "width_m = ?, height_m = ?, length_m = ?, rigid_length_m = ?, proj_front_m = ?, proj_rear_m = ?, "
    "proj_side_m = ?, gross_t = ?, max_axle_t = ?, axle_driving = ?, axle_count = ?, axle_spacings_m = ?, "
    "vehicle_type = ?, cu_vehicle = ?, indivisible = ?, escort_planned = ?, esdal_ref = ?, vr1_ref = ?, "
    "so_ref = ?, applied_on = ?, notified_on = ?, note = ?, updated_by = ?, "
    "updated_at = ? WHERE tenant_id = ? AND id = ?"
)
assert re.findall(r"(\w+) = \?", _TYPED_UPDATE) == list(_UPDATE_COLS) + ["tenant_id", "id"]


def _write_typed(movement_id, merged):
    db.execute(_TYPED_UPDATE, [merged.get(k) for k in _UPDATE_COLS] + [db.current_tenant(), movement_id])


def set_status(movement_id, status, acc, by=None, today=None):
    """Move a movement along pending → approved → notified → moved, or withdraw it. Approving (and reopening to
    pending) is a planner's or an admin's; the rest is the owning team's or a planner's."""
    row = get(movement_id)
    if not row or not _visible(row, acc):
        return {"ok": False, "error": "no such abnormal load"}
    if status not in rules.STATUSES:
        return {"ok": False, "error": "status must be one of " + ", ".join(rules.STATUSES)}
    if status not in TRANSITIONS.get(row["status"], ()):
        return {"ok": False, "error": f"a {rules.STATUS_WORDS[row['status']].lower()} movement cannot go to "
                                      f"{rules.STATUS_WORDS[status].lower()}"}
    if status in PLANNER_ONLY and not access.can_approve(acc):
        return {"ok": False, "error": "only a planner or an admin can approve or reopen an abnormal load", "forbidden": True}
    notified_on = row.get("notified_on")
    if status == "notified" and not notified_on:
        notified_on = _today(today).isoformat()
    db.execute("UPDATE abnormal_loads SET status = ?, notified_on = ?, updated_by = ?, updated_at = ? "
               "WHERE tenant_id = ? AND id = ?",
               (status, notified_on, by, _now(), db.current_tenant(), movement_id))
    return {"ok": True, "movement": decorate(get(movement_id), today=today)}


def delete(movement_id, acc):
    """A planner may delete any; a team login its own while still pending or withdrawn."""
    row = get(movement_id)
    if not row or not _visible(row, acc):
        return {"ok": False, "error": "no such abnormal load"}
    if not access.can_approve(acc) and row["status"] not in ("pending", "withdrawn"):
        return {"ok": False, "error": "an approved movement can only be withdrawn, or deleted by a planner", "forbidden": True}
    db.execute("DELETE FROM abnormal_loads WHERE tenant_id = ? AND id = ?", (db.current_tenant(), movement_id))
    return {"ok": True, "deleted": movement_id}


def rows(acc=None):
    """Every movement the caller may see, oldest window first."""
    out = [r for r in db.query("SELECT * FROM abnormal_loads WHERE tenant_id = ? ORDER BY date_from, id", (db.current_tenant(),))
           if _visible(r, acc)]
    return out


def decorate(row, today=None, feed=None, bans=None, locs=None, gates=None, labels=None, nat=None):
    """One movement as the page reads it: the typed row, the names, the advice and the flags."""
    import taxonomy
    d = dict(row)
    for k in BOOL_FIELDS:
        d[k] = bool(d.get(k))
    feed = feed if feed is not None else holiday_feed()
    bans = bans if bans is not None else time_bans()
    locs = locs if locs is not None else _locations()
    gates = gates if gates is not None else _gates()
    labels = labels if labels is not None else taxonomy.team_labels()
    nat = nat or nation()
    o, de = locs.get(d.get("origin_id")) or {}, locs.get(d.get("dest_id")) or {}
    d["origin_name"] = o.get("name") or d.get("origin_id")
    d["dest_name"] = de.get("name") or d.get("dest_id")
    d["origin_gate_name"] = (gates.get(d.get("origin_gate_id")) or {}).get("name")
    d["dest_gate_name"] = (gates.get(d.get("dest_gate_id")) or {}).get("name")
    d["team_name"] = taxonomy.team_name(d.get("ipt"), labels) if d.get("ipt") else None
    d["status_word"] = rules.STATUS_WORDS.get(d.get("status"), d.get("status"))
    d["vehicle_word"] = rules.VEHICLE_WORDS.get(d.get("vehicle_type")) if d.get("vehicle_type") else None
    d["advice"] = rules.advice(d, date_from=d.get("date_from"), date_to=d.get("date_to"), time_band=d.get("time_band"),
                               escort_planned=d.get("escort_planned"), applied_on=d.get("applied_on"),
                               notified_on=d.get("notified_on"), status=d.get("status"), today=today,
                               holidays_feed=feed, nation=nat, time_bans=bans)
    d["flags"] = d["advice"]["flags"]
    d["public"] = d.get("status") in ("approved", "notified", "moved")      # D68: approved-or-later reaches the public map
    for k in ("geometry_json", "return_geometry_json", "here_notices_json", "actions_json", "roads_json", "limits_hits_json",
              "pinch_json", "via_json"):
        v = d.pop(k, None)
        try:
            d[k[:-5]] = json.loads(v) if v else None
        except Exception:
            d[k[:-5]] = None
    d["routed"] = bool(d.get("geometry"))
    # 22 Oct 2026 (phase 2): the line's facts for the page and the map — the roads in words, HERE's notes (a size HERE
    # capped, a return leg not drawn), the candidates and the typed rows apart, the limit hits over the line
    if d["routed"]:
        import abnormal_route as _ar
        hn = d.get("here_notices") or {}
        d["roads_words"] = _ar.roads_sentence(d.get("roads") or [])
        d["route_notes"] = list(hn.get("notes") or [])
        d["has_motorway"] = bool(hn.get("has_motorway"))
        d["candidates"] = [c for c in (d.get("pinch") or []) if c.get("source") != "typed"]
        d["typed_points"] = [c for c in (d.get("pinch") or []) if c.get("source") == "typed"]
        d["limit_exceeds"] = [h for h in (d.get("limits_hits") or []) if h.get("verdict") == "exceeds"]
        if d["limit_exceeds"]:
            d["flags"] = list(d["flags"]) + [{"code": "AIL_ROAD_LIMIT",
                                             "text": f"{len(d['limit_exceeds'])} signed limit{'s' if len(d['limit_exceeds']) != 1 else ''} on the line the load is over: "
                                                     + "; ".join(h.get("headline") or "" for h in d["limit_exceeds"][:3])}]
        d["route_words"] = _ar.INDICATIVE_WORDS
    else:
        d["candidates"], d["typed_points"], d["limit_exceeds"], d["route_notes"] = [], [c for c in (d.get("pinch") or []) if c.get("source") == "typed"], [], []
    return d


def _structures_words():
    """22 Oct 2026 (phase 3): the sentence under the pinch-point table about OpenStreetMap's structures (abnormal_route's)."""
    try:
        import abnormal_route
        return abnormal_route.STRUCTURES_WORDS
    except Exception:       # noqa: BLE001
        return None


def page(acc=None, today=None):
    """The whole read for Plan → Abnormal loads: the movements (decorated), the settings, the words, the pickers."""
    import taxonomy
    feed, bans, locs, gates, labels, nat = holiday_feed(), time_bans(), _locations(), _gates(), taxonomy.team_labels(), nation()
    movements = [decorate(r, today=today, feed=feed, bans=bans, locs=locs, gates=gates, labels=labels, nat=nat) for r in rows(acc)]
    by_status = {}
    for m in movements:
        by_status[m["status"]] = by_status.get(m["status"], 0) + 1
    return {
        "movements": movements, "count": len(movements), "by_status": by_status,
        "flagged": sum(1 for m in movements if m["flags"]),
        "settings": {"holidays": holiday_status(), "time_bans": bans, "nation": nat},
        "words": {"advice": rules.ADVICE_WORDS, "not_modelled": rules.NOT_MODELLED_WORDS, "structures": _structures_words(),
                  # 27 Oct 2026 (the final UI pass): a screen never prints a decision code; the rule (D70, D71) is in the technical guide
                  "counted_apart": "Counted apart from the lorries' figures."},
        "choices": {"statuses": [{"key": k, "word": rules.STATUS_WORDS[k]} for k in rules.STATUSES],
                    "vehicle_types": [{"key": k, "word": rules.VEHICLE_WORDS[k]} for k in rules.VEHICLE_TYPES],
                    "escorts": list(rules.ESCORTS), "time_bands": list(rules.TIME_BANDS),
                    "locations": [{"id": l["id"], "name": l["name"], "loc_type": l.get("loc_type")} for l in
                                  sorted(locs.values(), key=lambda x: x["name"] or "")],
                    "gates": [{"id": g["id"], "location_id": g["location_id"], "name": g["name"], "direction": g.get("direction"),
                               "active": bool(g.get("active", True))} for g in gates.values()],
                    "transitions": TRANSITIONS, "planner_only": sorted(PLANNER_ONLY)},
        "today": _today(today).isoformat(),
    }


def preview(figures, **kw):
    """The advice for typed figures that are not saved yet (the form as it is typed)."""
    kw.setdefault("holidays_feed", holiday_feed())
    kw.setdefault("nation", nation())
    kw.setdefault("time_bans", time_bans())
    return rules.advice(figures, **kw)


# --------------------------------------------------------------------------- #
#  The reads the other screens take (phase 2, 22 Oct 2026): the Look-ahead's     #
#  week, the Dashboard's strip, the gate markers. Counted apart (D70): none of   #
#  these is a lorry figure, and none changes one.                                #
# --------------------------------------------------------------------------- #
def window_overlaps(m, d0, d1):
    """The movement's window touches the closed date range d0..d1 (dates)."""
    a = rules._date(m.get("date_from"))
    b = rules._date(m.get("date_to")) or a
    if not a:
        return False
    return a <= d1 and b >= d0


def public_ids_by_month(months):
    """23 Oct 2026 (the user: the abnormal loads on the public map's figures bar and in its animation): {month_index: [ids]}
    of the PUBLIC movements (approved, notified, moved — D68) whose window touches each calendar month asked, each load ONCE
    (a load counts 1, in and out alike; the user's answer 3). A load with no date typed is in no month. Ids only: the public
    feature already carries them, so the map joins on the id; counted apart from the lorries' figures (D70)."""
    import weeks as _weeks
    rows = db.query("SELECT id, date_from, date_to FROM abnormal_loads WHERE tenant_id = ? AND status IN (?, ?, ?) "
                    "ORDER BY date_from, id", (db.current_tenant(),) + tuple(PUBLIC_STATUSES))
    out = {}
    for m in months:
        d0, d1 = _weeks.month_span(int(m))
        out[int(m)] = [r["id"] for r in rows if window_overlaps(r, d0, d1)]
    return out


def brief(m):
    """One movement as the week block, the strip and the markers carry it (no advice lines, no geometry)."""
    adv = m.get("advice") or {}
    return {"id": m["id"], "name": m.get("name"), "ipt": m.get("ipt"), "team_name": m.get("team_name"),
            "origin_name": m.get("origin_name"), "dest_name": m.get("dest_name"), "dest_gate_name": m.get("dest_gate_name"),
            "origin_gate_name": m.get("origin_gate_name"),
            "date_from": m.get("date_from"), "date_to": m.get("date_to"), "time_band": m.get("time_band"),
            "movements": m.get("movements"), "return_abnormal": bool(m.get("return_abnormal")),
            "escort_planned": m.get("escort_planned") or "none", "status": m.get("status"), "status_word": m.get("status_word"),
            "summary": adv.get("summary"), "permission": adv.get("permission"), "category": adv.get("category"),
            "notify_by": adv.get("notify_by"), "apply_by": adv.get("apply_by"), "notified_on": m.get("notified_on"),
            "flags": list(m.get("flags") or []), "routed": bool(m.get("routed")), "distance_km": m.get("distance_km"),
            "candidates": len(m.get("candidates") or []), "limit_exceeds": len(m.get("limit_exceeds") or [])}


def week(dates, acc=None, today=None):
    """The movements whose window touches the week's dates — the Look-ahead's "Abnormal loads this week" block."""
    ds = [rules._date(d) for d in (dates or []) if rules._date(d)]
    if not ds:
        return {"movements": [], "count": 0, "from": None, "to": None, "words": None}
    d0, d1 = min(ds), max(ds)
    pg = page(acc, today=today)
    rows = [brief(m) for m in pg["movements"] if m.get("status") != "withdrawn" and window_overlaps(m, d0, d1)]
    return {"movements": rows, "count": len(rows), "from": d0.isoformat(), "to": d1.isoformat(),
            "flagged": sum(1 for r in rows if r["flags"]),
            "words": "Counted apart from the week's figures. What each needs is advice from its typed figures."}


def summary(acc=None, today=None, weeks_ahead=4):
    """The Dashboard's strip: loads in the next N weeks, notices due or late this week, permissions still to apply for."""
    t = _today(today)
    pg = page(acc, today=t)
    live = [m for m in pg["movements"] if m.get("status") in ("pending", "approved", "notified")]
    ahead = [m for m in live if window_overlaps(m, t, t + datetime.timedelta(days=7 * weeks_ahead))]
    due = [m for m in live if any(f.get("code") in ("NOTICE_DUE", "NOTICE_LATE") for f in m.get("flags") or [])]
    late = [m for m in due if any(f.get("code") == "NOTICE_LATE" for f in m.get("flags") or [])]
    to_apply = [m for m in live if any(f.get("code") == "SO_LEAD_TIME" for f in m.get("flags") or [])]
    road = [m for m in live if any(f.get("code") == "AIL_ROAD_LIMIT" for f in m.get("flags") or [])]
    return {"today": t.isoformat(), "weeks_ahead": weeks_ahead, "planned": len(pg["movements"]),
            "ahead": len(ahead), "ahead_names": [m["name"] for m in ahead][:4],
            "notices_due": len(due), "notices_late": len(late), "to_apply": len(to_apply), "road_limit": len(road),
            "words": "Counted apart from the lorries' figures."}


def gate_markers(month_index, acc=None, today=None):
    """{gate id: [brief + leaving]} — each movement arriving at a gate in the calendar month (the destination's entry gate),
    and leaving by one when the return leg is abnormal too (the origin's exit gate). Never a count of lorries."""
    import weeks as _weeks
    try:
        d0, d1 = _weeks.month_span(int(month_index))
    except Exception:
        return {}
    pg = page(acc, today=today)
    locs = _locations()
    gbl = gates_by_location()
    out = {}
    for m in pg["movements"]:
        if m.get("status") == "withdrawn" or not window_overlaps(m, d0, d1):
            continue
        b = brief(m)
        ends = [("dest_id", "dest_gate_id", "entry", False)]
        if m.get("return_abnormal"):
            ends.append(("origin_id", "origin_gate_id", "exit", True))
        for loc_key, gate_key, role, leaving in ends:
            loc = locs.get(m.get(loc_key))
            if not loc:
                continue
            try:
                import gates as _gates
                r = _gates.resolve(loc, role, m.get(gate_key), gates=gbl.get(loc["id"]))
            except Exception:
                continue
            gid = r.get("gate_id")
            if not gid:
                continue
            out.setdefault(gid, []).append(dict(b, leaving=leaving))
    return out


def gates_by_location():
    try:
        import gates as _gates
        return _gates.gates_by_location()
    except Exception:
        return {}


def month_index_of(iso_date):
    """The product's absolute month number for a date (weeks.month_index_of), for the tiles and the markers."""
    import weeks
    d = rules._date(iso_date)
    return weeks.month_index_of(d) if d else None

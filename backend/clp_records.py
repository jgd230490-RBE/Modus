"""
clp_records.py — the Construction Logistics Plans as records: which places, which team, the cover details, the
approval step and each approved issue. Wayscope, 31 Oct 2026 (task 4a, PR 3a). Mockup approved by John 31 Oct
(notes/clp-screens-mockup-1031/, Q1–Q11 as recommended): "each section only see their clp but planners and admins see
all and are able to edit and approve it"; the view is "per the login which will be by team".

WHAT A CLP IS
-------------
One or more locations and ONE TEAM OR EVERY TEAM. A team's CLP counts its own lines only (clp_doc.gather(team=)).
Two kinds of row:
  * listed by Wayscope by itself ("auto-<location>-all" / "auto-<location>-<team>"): for each compound, site and
    stockpile one CLP for every team, and one for each team with approved lorries there. It is WRITTEN the first time
    anyone edits, sends or approves it, so opening the page writes nothing; deleting one clears what was typed;
  * made with + New CLP by a planner or an admin ("clp-<hex>"): any set of places, one team or all.

WHO SEES WHAT (Q2–Q5)
--------------------
  * a planner or an admin: every CLP; makes one, changes its places and team, approves, asks for changes, deletes;
  * a team login: its own team's CLPs only — another team's, or an every-team CLP, answers "not found" exactly like a
    CLP that does not exist; it edits the cover details of its own and sends it for approval;
  * a login with no team that cannot approve (the demo's submitter): reads every CLP, changes nothing.

THE CHAIN (Q6)
--------------
draft -> sent (by the team, an optional note) -> approved as Issue N (a planner or an admin builds the file, which is
kept), or changes (a note required) -> back to the team. A planner or an admin may approve a CLP nobody sent. Editing an
approved CLP makes it a draft again; its issues are kept. Every write is in the audit trail (the middleware).

WHAT CHANGED (Q8)
-----------------
Each issue keeps a small summary (loads and months per stage, routes, places, the busiest month) and the next issue's
"What changed" is worked out against it, in words, with the team's and the approver's notes.

RULES
-----
* Every SQL literal carries the tenant predicate (test_tenant_audit). No team id is ever in a reply's words.
* The file of an issue is base64 text (clp_issues.file_b64): one column type on SQLite and Postgres.
"""
import base64
import datetime
import json
import secrets

import access
import conversions
import db
import gate_arrivals
import network
import taxonomy

import clp_doc

STATUSES = ("draft", "sent", "changes", "approved")
STATUS_WORDS = {"draft": "Draft", "sent": "Sent for approval", "changes": "Changes asked", "approved": "Approved"}
AUTO_TYPES = ("compound", "site", "stockpile")
COVER_KEYS = tuple(k for k, _l in clp_doc.COVER_FIELDS)
COVER_MAX = {"summary": 1200}
TEXT_MAX = 400
NOTE_MAX = 1000
NAME_MAX = 120
MAX_PLACES = 30

COLS = ("id, name, location_ids, team, impact, cover, status, sent_by, sent_at, sent_note, changes_by, changes_at, "
        "changes_note, created_by, created_at, updated_by, updated_at")


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _today():
    return datetime.date.today().isoformat()


def who(acc):
    """The name a write is recorded under: the person, else the team's name, else the role."""
    acc = acc or {}
    return acc.get("name") or acc.get("label") or acc.get("role") or ""


def team_of(acc):
    return access.canonical_ipt((acc or {}).get("ipt"))


def can_approve(acc):
    return access.can_approve(acc)


def visible(rec, acc):
    """A team login sees its own team's CLPs only; anyone else with access sees every CLP."""
    t = team_of(acc)
    if t:
        return access.canonical_ipt(rec.get("team")) == t
    return access.is_staff(acc)      # PR 3c: never a client reviewer (they read through clp_reviews only)


# --------------------------------------------------------------------------- #
#  Reading                                                                     #
# --------------------------------------------------------------------------- #
def _row(r):
    d = dict(r)
    try:
        d["location_ids"] = [str(x) for x in json.loads(d.get("location_ids") or "[]")]
    except (TypeError, ValueError):
        d["location_ids"] = []
    try:
        c = json.loads(d.get("cover") or "{}")
    except (TypeError, ValueError):
        c = {}
    d["cover"] = {k: str(c.get(k) or "") for k in COVER_KEYS if str(c.get(k) or "").strip()}
    d["team"] = access.canonical_ipt(d.get("team"))
    d["impact"] = d.get("impact") if d.get("impact") in clp_doc.IMPACT else "higher"
    d["status"] = d.get("status") if d.get("status") in STATUSES else "draft"
    d["saved"] = True
    return d


def _saved():
    return {r["id"]: _row(r) for r in db.query(f"SELECT {COLS} FROM clp_documents WHERE tenant_id = ?",
                                               (db.current_tenant(),))}


def _locations():
    return {l["id"]: l for l in db.query("SELECT id, name, loc_type FROM locations WHERE tenant_id = ?",
                                        (db.current_tenant(),))}


def _type_of(loc):
    return (network.canonical_loc_type((loc or {}).get("loc_type")) or "").strip()


def _team_months(factors):
    """{(location id, team or None): {month: trips}} for every location, from the approved lines (the CLP's own
    trips rule): what makes a team's row appear, and each row's busiest month."""
    tenant_id = db.current_tenant()
    routes = {r["id"]: r for r in db.query("SELECT id, origin_id, dest_id FROM routes WHERE tenant_id = ?", (tenant_id,))}
    out = {}
    for row in db.query("SELECT * FROM forecasts WHERE tenant_id = ? AND status = 'Approved'", (tenant_id,)):
        r = routes.get(row.get("route_id"))
        if not r:
            continue
        trips = gate_arrivals.trips_for(row, factors)
        if trips <= 0:
            continue
        team = access.canonical_ipt(row.get("ipt"))
        mi = int(row["month_index"])
        for loc in {r.get("origin_id"), r.get("dest_id")} - {None, ""}:
            for key in ([(loc, None), (loc, team)] if team else [(loc, None)]):
                m = out.setdefault(key, {})
                m[mi] = m.get(mi, 0) + trips
    return out


def auto_id(location_id, team):
    return f"auto-{location_id}-{team or 'all'}"


def _auto_rows(locs, months):
    out = {}
    for lid, loc in locs.items():
        if _type_of(loc).lower() not in AUTO_TYPES:
            continue
        teams = sorted({t for (l, t) in months if l == lid and t})
        for t in [None] + teams:
            rid = auto_id(lid, t)
            out[rid] = {"id": rid, "name": loc.get("name") or lid, "location_ids": [lid], "team": t,
                        "impact": "higher", "cover": {}, "status": "draft", "saved": False}
    return out


def _issues_by_clp():
    out = {}
    for r in db.query("SELECT clp_id, issue_no, approved_at, approved_by, sent_by, changes FROM clp_issues "
                      "WHERE tenant_id = ? ORDER BY clp_id, issue_no", (db.current_tenant(),)):
        out.setdefault(r["clp_id"], []).append(r)
    return out


def _peak(rec, months):
    agg = {}
    for lid in rec["location_ids"]:
        for m, v in (months.get((lid, rec["team"])) or {}).items():
            agg[m] = agg.get(m, 0) + v
    if not agg:
        return None
    return min(agg, key=lambda m: (-agg[m], m))


def _decorate(rec, locs, months, issues, labels):
    places = [{"id": lid, "name": (locs.get(lid) or {}).get("name") or lid, "type": _type_of(locs.get(lid))}
              for lid in rec["location_ids"]]
    iss = issues.get(rec["id"]) or []
    last = iss[-1] if iss else None
    pm = _peak(rec, months)
    cover = rec.get("cover") or {}
    out = {
        "id": rec["id"], "name": rec.get("name") or ", ".join(p["name"] for p in places),
        "auto": rec["id"].startswith("auto-"), "saved": bool(rec.get("saved")),
        "location_ids": list(rec["location_ids"]), "places": places,
        "types": sorted({p["type"] for p in places if p["type"]}),
        "team": rec["team"], "team_name": (taxonomy.team_name(rec["team"], labels) if rec["team"] else None),
        "impact": rec["impact"], "cover": dict(cover),
        "cover_typed": sum(1 for k in COVER_KEYS if str(cover.get(k) or "").strip()), "cover_total": len(COVER_KEYS),
        "status": rec["status"], "status_word": STATUS_WORDS[rec["status"]],
        "sent_by": rec.get("sent_by"), "sent_at": rec.get("sent_at"), "sent_note": rec.get("sent_note"),
        "changes_by": rec.get("changes_by"), "changes_at": rec.get("changes_at"), "changes_note": rec.get("changes_note"),
        "updated_at": rec.get("updated_at"),
        "busiest_month": pm, "busiest_label": (clp_doc.month_label(pm) if pm else None),
        "issues": len(iss),
        "last_issue": ({"no": last["issue_no"], "date": str(last["approved_at"])[:10], "by": last.get("approved_by")}
                       if last else None),
        "next_issue": (last["issue_no"] + 1) if last else 1,
    }
    return out


def _all(factors=None):
    factors = factors or conversions.load_factors()
    locs = _locations()
    months = _team_months(factors)
    rows = _auto_rows(locs, months)
    rows.update(_saved())
    return rows, locs, months


def list_for(acc, factors=None):
    """Every CLP this caller may see, the ones sent for approval first for an approver."""
    rows, locs, months = _all(factors)
    issues = _issues_by_clp()
    labels = taxonomy.team_labels()
    out = [_decorate(r, locs, months, issues, labels) for r in rows.values() if visible(r, acc)]
    import clp_notes
    tally = clp_notes.counts_for(acc)
    for d in out:
        t = tally.get(d["id"]) or {}
        d["tasks"] = {k: t.get(k, 0) for k in ("open", "overdue", "notes", "done", "mine_open")}
        d["tasks"]["next_due"] = t.get("next_due")
    # 31 Oct 2026 (PR 3c): where the last issue sent to each client group stands (With … / Accepted by … / Returned by …)
    import clp_reviews
    rv = clp_reviews.for_list({d["id"] for d in out})
    for d in out:
        d["reviews"] = rv.get(d["id"], [])
    sent_first = can_approve(acc)
    out.sort(key=lambda d: (not (sent_first and d["status"] == "sent"), d["name"].lower(),
                            d["team_name"] is not None, d["team_name"] or "", d["id"]))
    return {"clps": out, "can_approve": bool(can_approve(acc)), "team": team_of(acc),
            "team_name": (taxonomy.team_name(team_of(acc), labels) if team_of(acc) else None),
            "cover_fields": [{"key": k, "label": l} for k, l in clp_doc.COVER_FIELDS],
            "places": [{"id": lid, "name": l.get("name") or lid, "type": _type_of(l)}
                       for lid, l in sorted(locs.items(), key=lambda kv: (kv[1].get("name") or kv[0]).lower())],
            "teams": [{"id": t, "name": taxonomy.team_name(t, labels)} for t in _active_teams()],
            "statuses": [{"key": k, "word": STATUS_WORDS[k]} for k in STATUSES],
            "review_groups": (bool(clp_reviews.group_names()) if can_approve(acc) else False)}


def _active_teams():
    """The teams a CLP can be for: the tenant's active teams (Users → Teams)."""
    import teams as _teams
    return [access.canonical_ipt(r["id"]) for r in _teams._rows() if r["active"] and access.canonical_ipt(r["id"])]


def get(clp_id, acc, factors=None):
    """The decorated CLP, or None when it does not exist OR this caller may not see it (the same answer)."""
    rows, locs, months = _all(factors)
    rec = rows.get(str(clp_id or ""))
    if not rec or not visible(rec, acc):
        return None
    return _decorate(rec, locs, months, _issues_by_clp(), taxonomy.team_labels())


def _record(clp_id, acc, factors=None):
    rows, _locs, _m = _all(factors)
    rec = rows.get(str(clp_id or ""))
    if not rec or not visible(rec, acc):
        return None
    return rec


# --------------------------------------------------------------------------- #
#  Writing                                                                     #
# --------------------------------------------------------------------------- #
def _clean(v, most):
    v = str(v or "").strip()
    return v[:most]


def cover_problem(cover):
    if cover is None:
        return None
    if not isinstance(cover, dict):
        return "The cover details must be a block of fields."
    for k, v in cover.items():
        if k not in COVER_KEYS:
            return f"Unknown cover detail: {k}."
        if v is not None and not isinstance(v, (str, int, float)):
            return "Each cover detail is words."
        if len(str(v or "")) > COVER_MAX.get(k, TEXT_MAX):
            return f"{dict(clp_doc.COVER_FIELDS)[k]} is too long (at most {COVER_MAX.get(k, TEXT_MAX)} characters)."
    for w in clp_doc.banned_words(" ".join(str(v or "") for v in cover.values())):
        return f"Please do not use the word \"{w}\" on a CLP."
    return None


def _places_problem(ids, locs):
    if not isinstance(ids, list) or not ids:
        return "Pick at least one place."
    if len(ids) > MAX_PLACES:
        return f"At most {MAX_PLACES} places in one CLP."
    bad = [str(x) for x in ids if str(x) not in locs]
    if bad:
        return "That place is not set up here."
    return None


def _write(rec, by):
    now = _now()
    t = db.current_tenant()
    cover = json.dumps({k: v for k, v in (rec.get("cover") or {}).items() if str(v or "").strip()}, sort_keys=True)
    vals = (rec["name"], json.dumps(rec["location_ids"]), rec.get("team"), rec["impact"], cover, rec["status"],
            rec.get("sent_by"), rec.get("sent_at"), rec.get("sent_note"), rec.get("changes_by"), rec.get("changes_at"),
            rec.get("changes_note"))
    if rec.get("saved"):
        db.execute("UPDATE clp_documents SET name = ?, location_ids = ?, team = ?, impact = ?, cover = ?, status = ?, "
                   "sent_by = ?, sent_at = ?, sent_note = ?, changes_by = ?, changes_at = ?, changes_note = ?, "
                   "updated_by = ?, updated_at = ? WHERE tenant_id = ? AND id = ?", vals + (by, now, t, rec["id"]))
    else:
        db.execute(f"INSERT INTO clp_documents (tenant_id, {COLS}) VALUES ({', '.join(['?'] * 18)})",
                   (t, rec["id"]) + vals + (by, now, by, now))
    rec["saved"] = True


def create(body, acc, factors=None):
    """+ New CLP (a planner or an admin): {name, location_ids, team (slot or null), impact, cover}."""
    if not can_approve(acc):
        return {"error": "Only a planner or an admin makes a new CLP.", "status": 403}
    body = body or {}
    locs = _locations()
    ids = []
    for x in body.get("location_ids") or []:
        if str(x) not in ids:
            ids.append(str(x))
    p = _places_problem(ids, locs) or cover_problem(body.get("cover"))
    team = body.get("team")
    if not p and team not in (None, ""):
        team = access.canonical_ipt(team)
        if not team or team not in _active_teams():
            p = "That team is not set up here."
    if not p and body.get("impact", "higher") not in clp_doc.IMPACT:
        p = "Impact must be higher or medium."
    if p:
        return {"error": p, "status": 422}
    name = _clean(body.get("name"), NAME_MAX) or ", ".join((locs.get(i) or {}).get("name") or i for i in ids)
    rec = {"id": "clp-" + secrets.token_hex(4), "name": name, "location_ids": ids, "team": team or None,
           "impact": body.get("impact") or "higher",
           "cover": {k: _clean(v, COVER_MAX.get(k, TEXT_MAX)) for k, v in (body.get("cover") or {}).items()},
           "status": "draft", "saved": False}
    _write(rec, who(acc))
    return get(rec["id"], acc, factors)


def update(clp_id, body, acc, factors=None):
    """A planner or an admin: name, impact, cover, and (on a CLP made with + New CLP) its places and team. A team login:
    the cover details of its own CLP only. Editing an approved CLP makes it a draft again (its issues are kept)."""
    rec = _record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    body = body or {}
    appr = can_approve(acc)
    if not appr and not team_of(acc):
        return {"error": "This sign-in reads the CLPs and changes none.", "status": 403}
    if not appr and any(k in body for k in ("name", "location_ids", "team", "impact")):
        return {"error": "A planner or an admin sets a CLP's name, places, team and impact.", "status": 403}
    p = cover_problem(body.get("cover"))
    if p:
        return {"error": p, "status": 422}
    nxt = dict(rec)
    if "cover" in body:
        c = dict(rec.get("cover") or {})
        for k, v in (body.get("cover") or {}).items():
            c[k] = _clean(v, COVER_MAX.get(k, TEXT_MAX))
        nxt["cover"] = c
    if appr:
        if "name" in body:
            nxt["name"] = _clean(body.get("name"), NAME_MAX) or rec["name"]
        if "impact" in body:
            if body["impact"] not in clp_doc.IMPACT:
                return {"error": "Impact must be higher or medium.", "status": 422}
            nxt["impact"] = body["impact"]
        if ("location_ids" in body or "team" in body) and rec["id"].startswith("auto-"):
            return {"error": "Wayscope lists this CLP for its place and team. Use + New CLP for another set.", "status": 422}
        if "location_ids" in body:
            ids = []
            for x in body.get("location_ids") or []:
                if str(x) not in ids:
                    ids.append(str(x))
            p = _places_problem(ids, _locations())
            if p:
                return {"error": p, "status": 422}
            nxt["location_ids"] = ids
        if "team" in body:
            t = access.canonical_ipt(body.get("team")) if body.get("team") not in (None, "") else None
            if body.get("team") not in (None, "") and (not t or t not in _active_teams()):
                return {"error": "That team is not set up here.", "status": 422}
            nxt["team"] = t
    if nxt["status"] == "approved":
        nxt["status"] = "draft"
    _write(nxt, who(acc))
    return get(nxt["id"], acc, factors)


def delete(clp_id, acc, factors=None):
    """A planner or an admin, only while the CLP has no issue (Q7). A row Wayscope lists by itself is only cleared."""
    if not can_approve(acc):
        return {"error": "Only a planner or an admin deletes a CLP.", "status": 403}
    rec = _record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    if _issues_by_clp().get(rec["id"]):
        return {"error": "This CLP has an approved issue, so it is kept.", "status": 422}
    if rec.get("saved"):
        db.execute("DELETE FROM clp_documents WHERE tenant_id = ? AND id = ?", (db.current_tenant(), rec["id"]))
    if not rec["id"].startswith("auto-"):
        # 31 Oct 2026 (PR 3b, Q12): a CLP made with + New CLP goes with its notes and tasks; a listed row is only cleared
        # of its typed details and keeps them
        import clp_notes
        clp_notes.drop_all(rec["id"])
    return {"deleted": rec["id"], "cleared": rec["id"].startswith("auto-")}


def send(clp_id, note, acc, factors=None):
    """The team sends its CLP for approval, with an optional note (sending again replaces it)."""
    rec = _record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    if not team_of(acc) or can_approve(acc):
        return {"error": "A team sends its own CLP for approval; a planner or an admin approves it.", "status": 403}
    note = _clean(note, NOTE_MAX)
    for w in clp_doc.banned_words(note):
        return {"error": f"Please do not use the word \"{w}\" on a CLP.", "status": 422}
    nxt = dict(rec, status="sent", sent_by=who(acc), sent_at=_now(), sent_note=note or None)
    _write(nxt, who(acc))
    import clp_notes
    clp_notes.add_step(rec["id"], "sent", who(acc), nxt["sent_at"], note or None)
    return get(nxt["id"], acc, factors)


def ask_changes(clp_id, note, acc, factors=None, task=None):
    """A planner or an admin sends it back to the team, with a note (required). `task` = {"due": …} also adds the note
    as a task for the CLP's team (the planners and admins on an every-team CLP; PR 3b, Q9)."""
    if not can_approve(acc):
        return {"error": "Only a planner or an admin asks for changes.", "status": 403}
    rec = _record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    note = _clean(note, NOTE_MAX)
    if not note:
        return {"error": "Say what needs changing.", "status": 422}
    for w in clp_doc.banned_words(note):
        return {"error": f"Please do not use the word \"{w}\" on a CLP.", "status": 422}
    if task is not None:
        import clp_notes
        bad = clp_notes._due_problem((task or {}).get("due") or None)
        if bad:
            return {"error": bad, "status": 422}
    nxt = dict(rec, status="changes", changes_by=who(acc), changes_at=_now(), changes_note=note)
    _write(nxt, who(acc))
    import clp_notes
    clp_notes.add_step(rec["id"], "changes", who(acc), nxt["changes_at"], note)
    if task is not None:
        clp_notes.add_task(rec["id"], {"words": note, "for": "team" if rec.get("team") else "approvers",
                                       "due": (task or {}).get("due") or None}, acc, factors, mail=False)
    return get(nxt["id"], acc, factors)


# --------------------------------------------------------------------------- #
#  The document, its summary and what changed                                  #
# --------------------------------------------------------------------------- #
def gather_for(rec, factors, working_days, layers=False):
    """clp_doc.gather for this CLP: its places, its team, its name and cover details."""
    data = clp_doc.gather(rec["location_ids"], factors=factors, working_days=working_days, layers=layers,
                          team=rec.get("team"))
    data["title"] = rec.get("name") or data["name"]
    data["cover"] = dict(rec.get("cover") or {})
    return data


def summary(data):
    """The figures an issue keeps for the next one's "What changed"."""
    return {
        "stages": {s["name"]: {"loads": s["trips_total"], "first": s["first"], "last": s["last"]}
                   for s in data["stages"]},
        "routes": sorted(r["route_id"] for r in data["routes"]),
        "places": list(data["site_names"]),
        "peak_month": data["totals"]["peak_month"], "trips": data["totals"]["trips"],
    }


def changes(prev, cur):
    """Words for what changed between two summaries (newest last), Wayscope's own reading."""
    if not prev:
        return ["First issue."]
    out = []
    ml = clp_doc.month_label
    for name, s in cur["stages"].items():
        p = prev["stages"].get(name) or {"loads": 0, "first": None, "last": None}
        if s["loads"] != p["loads"]:
            out.append(f"{name}: {clp_doc.n(p['loads'])} → {clp_doc.n(s['loads'])} loads")
        if s["last"] and p["last"] and s["last"] != p["last"]:
            out.append(f"{name}: now ends {ml(s['last'])} (was {ml(p['last'])})")
        if s["first"] and p["first"] and s["first"] != p["first"]:
            out.append(f"{name}: now starts {ml(s['first'])} (was {ml(p['first'])})")
    for name in prev["stages"]:
        if name not in cur["stages"] and prev["stages"][name]["loads"]:
            out.append(f"{name}: no longer in the plan")
    added = [r for r in cur["routes"] if r not in prev["routes"]]
    gone = [r for r in prev["routes"] if r not in cur["routes"]]
    if added:
        out.append(f"Route{'s' if len(added) != 1 else ''} {', '.join(added)} added")
    if gone:
        out.append(f"Route{'s' if len(gone) != 1 else ''} {', '.join(gone)} no longer used")
    if cur["places"] != prev["places"]:
        out.append("Places now: " + ", ".join(cur["places"]))
    if cur["peak_month"] and prev.get("peak_month") and cur["peak_month"] != prev["peak_month"]:
        out.append(f"Busiest month now {ml(cur['peak_month'])} (was {ml(prev['peak_month'])})")
    return out or ["No change in the plan's figures."]


def _issue_rows(clp_id):
    return db.query("SELECT clp_id, issue_no, approved_at, approved_by, sent_by, sent_note, approver_note, changes, "
                    "summary, file_name, file_size FROM clp_issues WHERE tenant_id = ? AND clp_id = ? ORDER BY issue_no",
                    (db.current_tenant(), clp_id))


def _words_of(row):
    try:
        ch = json.loads(row.get("changes") or "[]")
    except (TypeError, ValueError):
        ch = []
    bits = ["; ".join(ch)] if ch else []
    for k in ("sent_note", "approver_note"):
        if (row.get(k) or "").strip():
            bits.append(row[k].strip())
    w = ". ".join(b.rstrip(".") for b in bits if b)
    return (w + ".") if w else ""


def history(clp_id, acc, factors=None):
    rec = _record(clp_id, acc, factors)
    if not rec:
        return None
    rows = _issue_rows(rec["id"])
    return {"id": rec["id"], "issues": [{
        "no": r["issue_no"], "date": str(r["approved_at"])[:10], "approved_by": r.get("approved_by"),
        "sent_by": r.get("sent_by"), "sent_note": r.get("sent_note"), "approver_note": r.get("approver_note"),
        "changes": json.loads(r.get("changes") or "[]"), "words": _words_of(r),
        "file_name": r.get("file_name"), "file_size": r.get("file_size")} for r in reversed(rows)]}


def doc_history(clp_id, extra=None):
    """The Document history table the file prints: every issue newest first (+ the one being approved)."""
    import clp_reviews
    decided = {}
    for d in clp_reviews.history_rows(clp_id):     # PR 3c (Q10): each client group's decision under its issue
        decided.setdefault(d["no"], []).append(d)
    rows = []
    for r in _issue_rows(clp_id):
        rows.append({"no": r["issue_no"], "date": str(r["approved_at"])[:10], "by": r.get("approved_by"),
                     "words": _words_of(r)})
        rows += decided.get(r["issue_no"], [])
    if extra:
        rows.append(extra)
    return list(reversed(rows))


def preview(clp_id, acc, factors, working_days):
    """What the approve card shows: the next issue number, who sent it and their note, what changed since the last."""
    if not can_approve(acc):
        return {"error": "Only a planner or an admin approves a CLP.", "status": 403}
    rec = _record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    try:
        data = gather_for(rec, factors, working_days)
    except ValueError as e:
        return {"error": str(e), "status": 422}
    rows = _issue_rows(rec["id"])
    last = rows[-1] if rows else None
    prev = json.loads(last["summary"]) if last and last.get("summary") else None
    return {"id": rec["id"], "next_issue": (last["issue_no"] + 1) if last else 1,
            "last_issue": ({"no": last["issue_no"], "date": str(last["approved_at"])[:10]} if last else None),
            "sent": rec["status"] == "sent", "sent_by": rec.get("sent_by"), "sent_at": rec.get("sent_at"),
            "sent_note": rec.get("sent_note"), "changes": changes(prev, summary(data)),
            "tasks": __import__("clp_notes").open_summary(rec["id"]),
            # PR 3c: the approve card's "Send to the client's reviewers" ticks (a group that had the last issue ticked)
            "review_groups": __import__("clp_reviews").groups_for_send(rec["id"])}


def approve(clp_id, note, acc, factors, working_days, build):
    """Build the file as Issue N, keep it, record who and when. `build(data) -> bytes` is the caller's (it builds the
    layers and the pictures alone, heavy_reads.solo)."""
    if not can_approve(acc):
        return {"error": "Only a planner or an admin approves a CLP.", "status": 403}
    rec = _record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    note = _clean(note, NOTE_MAX)
    for w in clp_doc.banned_words(note):
        return {"error": f"Please do not use the word \"{w}\" on a CLP.", "status": 422}
    try:
        data = gather_for(rec, factors, working_days)
    except ValueError as e:
        return {"error": str(e), "status": 422}
    rows = _issue_rows(rec["id"])
    last = rows[-1] if rows else None
    no = (last["issue_no"] + 1) if last else 1
    prev = json.loads(last["summary"]) if last and last.get("summary") else None
    summ = summary(data)
    ch = changes(prev, summ)
    by = who(acc)
    today = _today()
    sent_note = rec.get("sent_note") if rec["status"] == "sent" else None
    sent_by = rec.get("sent_by") if rec["status"] == "sent" else None
    this = {"no": no, "date": today, "by": by,
            "words": _words_of({"changes": json.dumps(ch), "sent_note": sent_note, "approver_note": note})}
    data["issue"] = {"no": no, "date": today, "by": by}
    data["history"] = doc_history(rec["id"], extra=this)
    body = build(data, rec)
    name = clp_doc.file_name(data).replace(".docx", f" Issue {no}.docx")
    at = _now()
    db.execute("INSERT INTO clp_issues (tenant_id, clp_id, issue_no, approved_at, approved_by, sent_by, sent_note, "
               "approver_note, changes, summary, file_name, file_size, file_b64) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (db.current_tenant(), rec["id"], no, at, by, sent_by, sent_note, note or None, json.dumps(ch),
                json.dumps(summ), name, len(body), base64.b64encode(body).decode("ascii")))
    nxt = dict(rec, status="approved", changes_by=None, changes_at=None, changes_note=None)
    _write(nxt, by)
    import clp_notes
    clp_notes.add_step(rec["id"], "approved", by, at, note or None, issue_no=no)
    clp_notes.keep_lines(rec["id"], data.get("todos"))
    return get(rec["id"], acc, factors)


def issue_file(clp_id, issue_no, acc, factors=None):
    """(file name, bytes) of an approved issue exactly as approved, or None."""
    rec = _record(clp_id, acc, factors)
    if not rec:
        return None
    rows = db.query("SELECT file_name, file_b64 FROM clp_issues WHERE tenant_id = ? AND clp_id = ? AND issue_no = ?",
                    (db.current_tenant(), rec["id"], int(issue_no)))
    if not rows or not rows[0].get("file_b64"):
        return None
    return rows[0]["file_name"], base64.b64decode(rows[0]["file_b64"])


def draft_data(clp_id, acc, factors, working_days):
    """gather()'s data for a draft download of this CLP (no issue: DRAFT on every page), with the history so far."""
    rec = _record(clp_id, acc, factors)
    if not rec:
        return None, None
    data = gather_for(rec, factors, working_days)
    data["history"] = doc_history(rec["id"])
    return rec, data

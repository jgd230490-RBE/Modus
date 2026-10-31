"""
clp_reviews.py — the contractor's CLIENT reviewers (National Highways, HS2, a council) and the issued CLPs sent to them.
Wayscope, 31 Oct 2026 (task 4a, PR 3c). Mockup approved by John 31 Oct (notes/clp-reviewers-mockup-1031/, Q1–Q12 as
recommended): "finally we should give access to the contrators client such as national highways/ HS2 etc to view and
approve also."

WHO
---
  * an ADMIN keeps the reviewer groups (one per client organisation; stopped, never deleted once a CLP went to it) and the
    reviewer logins (users.py kind 'reviewer': own password from an invite, two-step from the first sign-in, the same
    lock-out and reset, an optional end date, never a code) — Users → Client reviewers;
  * a PLANNER or an ADMIN sends an ISSUED CLP to a group (the approve card's ticks, or ⋯ → Send Issue N to reviewers…);
  * a REVIEWER reads only the CLPs sent to their group, downloads the issue exactly as approved, comments, and accepts
    or returns the latest issue sent to the group. One decision per group per issue: the first reviewer's stands with
    their name; another reviewer in the group may change it while the issue is the CLP's latest; every decision is kept;
    a newer issue starts fresh.

THE WALL
--------
🔴 A reviewer's session never sets access.current() (users.resolve_session answers (None, None) for it; access.reviewer()
is a separate context). Every staff guard and read refuses them exactly as it refuses a visitor not signed in. The review
reads here take the REVIEWER dict and look a CLP up ONLY through that group's sends (`_sent_to`): a CLP not sent to the
group, a draft, an issue never sent to it, another group's CLP — all answer None (a 404), the same answer as a CLP that
does not exist. Nothing here builds a file: a download is the stored issue (clp_issues.file_b64).

TABLES
------
  * clp_review_groups — id, name, created / stopped (who, when);
  * clp_reviews       — kind 'sent' (an issue sent to a group: who, when) and kind 'decision' (accepted / returned, the
                        comment, who, when). Kept for good: the history on both sides and the next issue's Document history.
Both are NO_DATA_TABLES (no figure is built from them); a draft's kept file carries `marker()` in its key instead.
Reviewer COMMENTS and the send / decision lines are rows of clp_notes (review_group = the group), so they sit in the CLP's
thread; a contractor note reaches a group only when its writer ticks "Show to <group>" (clp_notes.review_group too).

EMAIL (Q7)
----------
One to each reviewer in the group when an issue is sent to it; one to the person who sent it when the group decides.
Comments send nothing; no file is ever attached.

RULES
-----
* Every SQL literal carries the tenant predicate (test_tenant_audit). No team id is ever in a reply's words.
"""
import base64
import datetime
import re
import secrets

import access
import db
import taxonomy

import clp_doc

DECISIONS = ("accepted", "returned")
DECISION_WORDS = {"accepted": "Accepted", "returned": "Returned"}
NAME_MAX = 80
WORDS_MAX = 1000
GROUP_COLS = "id, name, created_by, created_at, updated_at, stopped_by, stopped_at"
REVIEW_COLS = "id, clp_id, issue_no, group_id, kind, decision, words, by_name, by_user, at"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _tenant():
    return db.current_tenant()


def _clean(v, most):
    return str(v or "").strip()[:most]


def _banned(words):
    for w in clp_doc.banned_words(words or ""):
        return f"Please do not use the word \"{w}\" on a CLP."
    return None


def scheme_name():
    """The organisation's name, as on every screen (the header names the contractor to a reviewer)."""
    try:
        import config
        import conversions
        return config.tenant_settings(conversions).get("name") or "Wayscope"
    except Exception:  # noqa: BLE001
        return "Wayscope"


def _demo_notice():
    try:
        import config
        import conversions
        return config.tenant_settings(conversions).get("demo_notice")
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
#  Groups and reviewer logins (admins: main.py checks _check_admin)            #
# --------------------------------------------------------------------------- #
def _groups():
    return {r["id"]: r for r in db.query(f"SELECT {GROUP_COLS} FROM clp_review_groups WHERE tenant_id = ?", (_tenant(),))}


def group_names():
    return {gid: g.get("name") or "" for gid, g in _groups().items()}


def _reviewers():
    """Every reviewer login. A database with no login table yet (a harness's) has none."""
    import users
    try:
        rows = users.list_users()
    except Exception:  # noqa: BLE001 — no login table: nobody to list or email, nobody let in
        return []
    return [u for u in rows if users.is_reviewer(u)]


def _review_rows(clp_id=None, kind=None):
    if clp_id is None:
        rows = db.query(f"SELECT {REVIEW_COLS} FROM clp_reviews WHERE tenant_id = ? ORDER BY at, id", (_tenant(),))
    else:
        rows = db.query(f"SELECT {REVIEW_COLS} FROM clp_reviews WHERE tenant_id = ? AND clp_id = ? ORDER BY at, id",
                        (_tenant(), clp_id))
    return [r for r in rows if not kind or r.get("kind") == kind]


def _group_out(g, members, sent):
    return {"id": g["id"], "name": g.get("name") or "", "stopped": bool(g.get("stopped_at")),
            "stopped_at": g.get("stopped_at"), "stopped_by": g.get("stopped_by"),
            "reviewers": len(members.get(g["id"], [])),
            "active_reviewers": sum(1 for u in members.get(g["id"], []) if _usable(u)),
            "sent": len(sent.get(g["id"], set())), "can_delete": not sent.get(g["id"]) and not members.get(g["id"])}


def _usable(u):
    import users
    return users.usable(u)


def listing():
    """The Client reviewers tab: the groups (with their reviewers and how many CLP issues went to each) and the logins."""
    import users
    groups = _groups()
    revs = _reviewers()
    members = {}
    for u in revs:
        members.setdefault(u.get("review_group"), []).append(u)
    sent = {}
    for r in _review_rows(kind="sent"):
        sent.setdefault(r["group_id"], set()).add((r["clp_id"], r["issue_no"]))
    gl = sorted(groups.values(), key=lambda g: ((g.get("name") or "").lower(), g["id"]))
    out_r = []
    for u in sorted(revs, key=lambda u: ((u.get("name") or "").lower(), u["id"])):
        p = users.public(u)
        p["group_name"] = (groups.get(u.get("review_group")) or {}).get("name") or ""
        p["group_stopped"] = bool((groups.get(u.get("review_group")) or {}).get("stopped_at"))
        out_r.append(p)
    return {"groups": [_group_out(g, members, sent) for g in gl], "reviewers": out_r,
            "mail": users.mail_settings() is not None}


def _name_problem(name, skip_id=None):
    if not name:
        return "Enter the organisation's name."
    if len(name) > NAME_MAX:
        return f"At most {NAME_MAX} characters."
    p = _banned(name)
    if p:
        return p
    for g in _groups().values():
        if g["id"] != skip_id and (g.get("name") or "").strip().lower() == name.lower():
            return "There is already a group with that name."
    return None


def add_group(name, by):
    """(group, error)."""
    name = _clean(name, NAME_MAX + 1)
    p = _name_problem(name)
    if p:
        return None, p
    gid = "rg-" + secrets.token_hex(4)
    now = _now()
    db.execute(f"INSERT INTO clp_review_groups (tenant_id, {GROUP_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (_tenant(), gid, name, (by or "")[:200] or None, now, now, None, None))
    return _groups()[gid], None


def change_group(gid, name=None, stopped=None, by=None):
    """Rename, stop or start again. Stopping ends every reviewer of the group's sessions at once (users.usable refuses a
    stopped group's logins from then on)."""
    import users
    g = _groups().get(str(gid or ""))
    if not g:
        return None, "No such group."
    now = _now()
    if name is not None:
        name = _clean(name, NAME_MAX + 1)
        p = _name_problem(name, skip_id=g["id"])
        if p:
            return None, p
        db.execute("UPDATE clp_review_groups SET name = ?, updated_at = ? WHERE tenant_id = ? AND id = ?",
                   (name, now, _tenant(), g["id"]))
    if stopped is not None:
        if stopped and not g.get("stopped_at"):
            db.execute("UPDATE clp_review_groups SET stopped_at = ?, stopped_by = ?, updated_at = ? "
                       "WHERE tenant_id = ? AND id = ?", (now, (by or "")[:200] or None, now, _tenant(), g["id"]))
            for u in _reviewers():
                if u.get("review_group") == g["id"]:
                    users.end_all_sessions(u["id"])
        elif not stopped and g.get("stopped_at"):
            db.execute("UPDATE clp_review_groups SET stopped_at = NULL, stopped_by = NULL, updated_at = ? "
                       "WHERE tenant_id = ? AND id = ?", (now, _tenant(), g["id"]))
    return _groups()[g["id"]], None


def delete_group(gid):
    """Only a group no CLP was ever sent to and with no reviewer login (Q1: a group a CLP went to is stopped instead)."""
    g = _groups().get(str(gid or ""))
    if not g:
        return "No such group."
    if any(r["group_id"] == g["id"] for r in _review_rows(kind="sent")):
        return "A CLP was sent to this group, so it is kept. Stop it instead."
    if any(u.get("review_group") == g["id"] for u in _reviewers()):
        return "Delete or move this group's reviewers first."
    db.execute("DELETE FROM clp_review_groups WHERE tenant_id = ? AND id = ?", (_tenant(), g["id"]))
    return None


def ends_at(ends_on):
    """(expires_at, error) for an optional 'YYYY-MM-DD' end date: the login stops at the start of that day (UTC)."""
    if ends_on in (None, ""):
        return None, None
    if not isinstance(ends_on, str) or not _DATE.match(ends_on):
        return None, "The end date must be a date."
    try:
        d = datetime.date.fromisoformat(ends_on)
    except ValueError:
        return None, "The end date must be a date."
    if d <= datetime.datetime.utcnow().date():
        return None, "The end date must be after today."
    if d.year > 2100:
        return None, "The end date must be a date."
    return f"{d.isoformat()}T00:00:00Z", None


def add_reviewer(email, name, group_id, ends_on=None, by=None):
    """(user, error): a reviewer login in a live group. The caller sends the invite (main._invite_or_reset)."""
    import users
    g = _groups().get(str(group_id or ""))
    if not g:
        return None, "Pick the client's group."
    if g.get("stopped_at"):
        return None, "This group is stopped. Start it again first."
    exp, err = ends_at(ends_on)
    if err:
        return None, err
    return users.create_user(email, name, users.REVIEWER_ROLE, None, kind="reviewer", expires_at=exp,
                             created_by=by, review_group=g["id"])


def change_reviewer(user_id, fields, by_user_id=None):
    """Name, disabled, the group (a live one) and the end date of a REVIEWER login only."""
    import users
    u = users.get_user(user_id)
    if not u or not users.is_reviewer(u):
        return None, "No such login."
    out = {}
    if "name" in fields:
        out["name"] = fields["name"]
    if "disabled" in fields:
        out["disabled"] = bool(fields["disabled"])
    if "ends_on" in fields:
        exp, err = ends_at(fields["ends_on"])
        if err:
            return None, err
        out["expires_at"] = exp
    user, err = users.update_user(user_id, out, by_user_id=by_user_id) if out else (u, None)
    if err:
        return None, err
    if "group_id" in fields and fields["group_id"] != u.get("review_group"):
        g = _groups().get(str(fields["group_id"] or ""))
        if not g or g.get("stopped_at"):
            return None, "Pick a group that is not stopped."
        db.execute("UPDATE users SET review_group = ? WHERE tenant_id = ? AND id = ?", (g["id"], _tenant(), user_id))
        users.end_all_sessions(user_id)
        user = users.get_user(user_id)
    return user, None


def delete_reviewer(user_id):
    """A reviewer login goes (their sessions and links with it). Their comments and decisions stay, under their name."""
    import users
    u = users.get_user(user_id)
    if not u or not users.is_reviewer(u):
        return "No such login."
    users.end_all_sessions(user_id)
    db.execute("DELETE FROM auth_tokens WHERE tenant_id = ? AND user_id = ?", (_tenant(), user_id))
    db.execute("DELETE FROM users WHERE tenant_id = ? AND id = ?", (_tenant(), user_id))
    return None


# --------------------------------------------------------------------------- #
#  Where each issue stands with each group (both sides)                        #
# --------------------------------------------------------------------------- #
def _standing(rows):
    """{(clp, issue, group): {'sent': first sent row, 'decision': the latest decision row or None, 'decisions': [...]}}"""
    out = {}
    for r in rows:
        k = (r["clp_id"], int(r["issue_no"] or 0), r["group_id"])
        s = out.setdefault(k, {"sent": None, "decision": None, "decisions": []})
        if r["kind"] == "sent":
            s["sent"] = s["sent"] or r
        elif r["kind"] == "decision":
            s["decisions"].append(r)
            s["decision"] = r
    return out


def _state_out(clp_id, issue_no, gid, s, names):
    d = s.get("decision")
    st = d["decision"] if d and d.get("decision") in DECISIONS else "waiting"
    sent = s.get("sent") or {}
    return {"group_id": gid, "group_name": names.get(gid, ""), "issue_no": issue_no, "state": st,
            "sent_at": sent.get("at"), "sent_by": sent.get("by_name"),
            "by": (d or {}).get("by_name"), "at": (d or {}).get("at"), "words": (d or {}).get("words")}


def for_list(clp_ids=None):
    """{clp id: [one line per group: the LAST issue sent to that group and where it stands]} for the contractor's list."""
    names = group_names()
    stand = _standing(_review_rows())
    last = {}
    for (cid, no, gid), s in stand.items():
        if not s["sent"]:
            continue
        if clp_ids is not None and cid not in clp_ids:
            continue
        if (cid, gid) not in last or no > last[(cid, gid)][0]:
            last[(cid, gid)] = (no, s)
    out = {}
    for (cid, gid), (no, s) in last.items():
        out.setdefault(cid, []).append(_state_out(cid, no, gid, s, names))
    for v in out.values():
        v.sort(key=lambda x: (x["group_name"].lower(), x["group_id"]))
    return out


def groups_for_send(clp_id, issue_no=None):
    """The live groups a planner can send this CLP's issue to: whether each had the LAST issue sent before (ticked by
    default), whether it already has this one, how many active reviewers it has."""
    groups = _groups()
    revs = _reviewers()
    members = {}
    for u in revs:
        if _usable(u):
            members[u.get("review_group")] = members.get(u.get("review_group"), 0) + 1
    rows = _review_rows(clp_id, "sent")
    had = {}
    for r in rows:
        had.setdefault(r["group_id"], set()).add(int(r["issue_no"]))
    out = []
    for g in sorted(groups.values(), key=lambda g: ((g.get("name") or "").lower(), g["id"])):
        if g.get("stopped_at"):
            continue
        nos = had.get(g["id"], set())
        out.append({"id": g["id"], "name": g.get("name") or "", "reviewers": members.get(g["id"], 0),
                    "had_issue": (max(nos) if nos else None),
                    "has_this": bool(issue_no and int(issue_no) in nos)})
    return out


def marker(clp_id):
    """What a kept draft of this CLP must change with: its group decisions (printed in the Document history)."""
    rows = _review_rows(clp_id, "decision")
    return f"{len(rows)}:{rows[-1]['id'] if rows else ''}"


def history_rows(clp_id):
    """The Document history's group lines (Q10): {no, date, by, words} for each group's standing decision on each issue,
    e.g. 'Returned by National Highways (Alex Example).'"""
    names = group_names()
    out = []
    for (cid, no, gid), s in sorted(_standing(_review_rows(clp_id)).items(), key=lambda kv: (kv[0][1], kv[0][2])):
        d = s.get("decision")
        if not d or d.get("decision") not in DECISIONS:
            continue
        out.append({"no": no, "date": str(d.get("at") or "")[:10], "by": "",
                    "words": f"{DECISION_WORDS[d['decision']]} by {names.get(gid) or 'the client'} ({d.get('by_name') or ''})."})
    return out


# --------------------------------------------------------------------------- #
#  Sending an issue (planners and admins)                                      #
# --------------------------------------------------------------------------- #
def _issue_row(clp_id, issue_no):
    rows = db.query("SELECT clp_id, issue_no, approved_at, approved_by, sent_note, approver_note, file_name FROM clp_issues "
                    "WHERE tenant_id = ? AND clp_id = ? AND issue_no = ?", (_tenant(), clp_id, int(issue_no)))
    return rows[0] if rows else None


def _latest_issue_no(clp_id):
    rows = db.query("SELECT issue_no FROM clp_issues WHERE tenant_id = ? AND clp_id = ?", (_tenant(), clp_id))
    return max((int(r["issue_no"]) for r in rows), default=0)


def _insert_review(row):
    row = dict(row)
    # time-ordered (as clp_notes.new_id): two decisions in the same second keep the order they were made in
    row.setdefault("id", "rv-" + __import__("clp_notes").new_id()[2:])
    row.setdefault("at", _now())
    cols = [c.strip() for c in REVIEW_COLS.split(",")]
    db.execute(f"INSERT INTO clp_reviews (tenant_id, {REVIEW_COLS}) VALUES ({', '.join(['?'] * (len(cols) + 1))})",
               tuple([_tenant()] + [row.get(c) for c in cols]))
    return row


def send_issue(clp_id, issue_no, group_ids, acc, factors=None):
    """Send an ISSUED CLP (the stored file) to one or more groups. Planners and admins only. A group that already has
    this issue is skipped. {"sent": [{group_id, group_name, email: {sent, unsent, failed}}], "skipped": [...]}"""
    import clp_records
    import clp_notes
    if not access.can_approve(acc):
        return {"error": "Only a planner or an admin sends a CLP to the client's reviewers.", "status": 403}
    rec = clp_records._record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    try:
        no = int(issue_no) if issue_no not in (None, "") else _latest_issue_no(rec["id"])
    except (TypeError, ValueError):
        return {"error": "No such issue.", "status": 404}
    issue = _issue_row(rec["id"], no) if no else None
    if not issue:
        return {"error": "Only an approved issue goes to the client's reviewers. Approve this CLP first.", "status": 422}
    ids = []
    for g in group_ids or []:
        if str(g) not in ids:
            ids.append(str(g))
    if not ids:
        return {"error": "Pick at least one group.", "status": 422}
    groups = _groups()
    for g in ids:
        if g not in groups or groups[g].get("stopped_at"):
            return {"error": "Pick a group that is not stopped.", "status": 422}
    had = {r["group_id"] for r in _review_rows(rec["id"], "sent") if int(r["issue_no"]) == no}
    by = clp_records.who(acc)
    out = {"sent": [], "skipped": [], "issue_no": no}
    for g in ids:
        if g in had:
            out["skipped"].append({"group_id": g, "group_name": groups[g].get("name") or ""})
            continue
        row = _insert_review({"clp_id": rec["id"], "issue_no": no, "group_id": g, "kind": "sent", "by_name": by,
                              "by_user": (acc or {}).get("user_id")})
        clp_notes.add_review_step(rec["id"], "review-sent", by, row["at"], g, no)
        out["sent"].append({"group_id": g, "group_name": groups[g].get("name") or "",
                            "email": email_reviewers(g, rec, issue, by)})
    return out


def send_message(user, rec, issue, by, settings, group_name, notice=None):
    from email.message import EmailMessage
    import users
    team = taxonomy.team_name(rec["team"]) if rec.get("team") else "All teams"
    place = rec.get("name") or "a site"
    msg = EmailMessage()
    msg["Subject"] = f"A CLP to review: {place}, Issue {issue['issue_no']}"
    msg["From"] = settings["DEMO_FROM"]
    msg["To"] = user["email"]
    msg["Reply-To"] = settings["reply_to"]
    note = (issue.get("approver_note") or issue.get("sent_note") or "").strip()
    body = (f"{by} of {scheme_name()} sent {group_name} Issue {issue['issue_no']} of the Construction Logistics Plan for "
            f"{place} ({team}) to review.\n\n")
    if note:
        body += f"\"{note}\"\n\n"
    body += f"Open it: {users.app_url()}/#review\n\n"
    if notice:
        body += f"DEMO · {notice}\n\n"
    msg.set_content(body + "Wayscope\n")
    return msg


def _send_mail(msg, settings):
    try:
        import demo_request
        demo_request.send(msg, settings)
        return "sent"
    except Exception as e:  # noqa: BLE001
        print(f"clp_reviews: email FAILED {e.__class__.__name__}: {str(e)[:200]}")
        return "failed"


def email_reviewers(group_id, rec, issue, by):
    """One email to each usable reviewer of the group. {'sent': n, 'unsent': n, 'failed': n}. Never raises."""
    import users
    tally = {"sent": 0, "unsent": 0, "failed": 0}
    revs = [u for u in _reviewers() if u.get("review_group") == group_id and _usable(u) and u.get("email")]
    settings = users.mail_settings()
    gname = (_groups().get(group_id) or {}).get("name") or ""
    notice = _demo_notice()
    for u in revs:
        if settings is None:
            tally["unsent"] += 1
            continue
        tally[_send_mail(send_message(u, rec, issue, by, settings, gname, notice), settings)] += 1
    return tally


def decided_message(sender, rec, issue_no, decision, words, rev, settings, notice=None):
    from email.message import EmailMessage
    import users
    team = taxonomy.team_name(rec["team"]) if rec.get("team") else "All teams"
    place = rec.get("name") or "a site"
    word = DECISION_WORDS[decision]
    msg = EmailMessage()
    msg["Subject"] = f"{word} by {rev['group_name']}: {place}, Issue {issue_no}"
    msg["From"] = settings["DEMO_FROM"]
    msg["To"] = sender["email"]
    msg["Reply-To"] = settings["reply_to"]
    body = (f"{rev['name']} of {rev['group_name']} {word.lower()} Issue {issue_no} of the CLP for {place} ({team})"
            + (f": \"{words}\"" if words else ".") + "\n\n"
            f"Open it: Plan → CLP documents, {users.app_url()}/#clp\n\n")
    if notice:
        body += f"DEMO · {notice}\n\n"
    msg.set_content(body + "Wayscope\n")
    return msg


def email_sender(sent_row, rec, issue_no, decision, words, rev):
    """'sent', 'unsent' (no sender set up, or it was sent from a shared code with no address) or 'failed'."""
    import users
    uid = (sent_row or {}).get("by_user")
    u = users.get_user(uid) if uid else None
    if not u or not u.get("email") or users.is_reviewer(u):
        return "unsent"
    settings = users.mail_settings()
    if settings is None:
        return "unsent"
    return _send_mail(decided_message(u, rec, issue_no, decision, words, rev, settings, _demo_notice()), settings)


# --------------------------------------------------------------------------- #
#  The reviewer's side (the REVIEWER dict only; never an access dict)          #
# --------------------------------------------------------------------------- #
def _rev_ok(rev):
    """A reviewer from access.reviewer(), still in a live group. Never an access dict."""
    if not rev or rev.get("via") != "reviewer" or not rev.get("group_id"):
        return False
    g = _groups().get(rev["group_id"])
    return bool(g) and not g.get("stopped_at")


def _sent_to(rev):
    """{clp id: sorted issue numbers sent to the reviewer's group}: the ONLY door to a CLP for a reviewer."""
    out = {}
    if not _rev_ok(rev):
        return out
    for r in _review_rows(kind="sent"):
        if r["group_id"] == rev["group_id"]:
            out.setdefault(r["clp_id"], set()).add(int(r["issue_no"]))
    return {k: sorted(v) for k, v in out.items()}


def _clp_record(clp_id):
    rows = db.query("SELECT id, name, team FROM clp_documents WHERE tenant_id = ? AND id = ?", (_tenant(), clp_id))
    return rows[0] if rows else None


def _rec_out(rec, labels=None):
    team = access.canonical_ipt(rec.get("team"))
    return {"id": rec["id"], "name": rec.get("name") or "",
            "team_name": (taxonomy.team_name(team, labels) if team else "All teams")}


def list_for_reviewer(rev):
    """CLPs for review: one row a CLP sent to the group, with its latest issue sent and the group's decision on it."""
    if not _rev_ok(rev):
        return None
    sent = _sent_to(rev)
    stand = _standing(_review_rows())
    names = group_names()
    labels = taxonomy.team_labels()
    out = []
    for cid, nos in sent.items():
        rec = _clp_record(cid)
        if not rec:
            continue
        no = nos[-1]
        s = stand.get((cid, no, rev["group_id"])) or {"sent": None, "decision": None}
        st = _state_out(cid, no, rev["group_id"], s, names)
        out.append(dict(_rec_out(rec, labels), issue_no=no, sent_at=st["sent_at"], sent_by=st["sent_by"],
                        state=st["state"], decided_by=st["by"], decided_at=st["at"]))
    out.sort(key=lambda d: d["sent_at"] or "", reverse=True)      # newest first, then the waiting ones on top
    out.sort(key=lambda d: d["state"] != "waiting")
    return {"group_name": rev.get("group_name") or "", "scheme": scheme_name(), "clps": out}


def clp_for_reviewer(clp_id, rev):
    """One CLP as a reviewer sees it, or None (not sent to the group / no such CLP: the same answer)."""
    sent = _sent_to(rev)
    cid = str(clp_id or "")
    if cid not in sent:
        return None
    rec = _clp_record(cid)
    if not rec:
        return None
    import clp_notes
    names = group_names()
    stand = _standing(_review_rows(cid))
    latest = _latest_issue_no(cid)
    issues = []
    for no in sent[cid]:
        s = stand.get((cid, no, rev["group_id"])) or {"sent": None, "decision": None, "decisions": []}
        st = _state_out(cid, no, rev["group_id"], s, names)
        row = _issue_row(cid, no) or {}
        issues.append({"no": no, "sent_at": st["sent_at"], "sent_by": st["sent_by"],
                       "note": (row.get("approver_note") or row.get("sent_note") or None),
                       "state": st["state"], "by": st["by"], "at": st["at"], "words": st["words"],
                       "decisions": [{"decision": d["decision"], "word": DECISION_WORDS.get(d["decision"], ""),
                                      "by": d.get("by_name"), "at": d.get("at"), "words": d.get("words")}
                                     for d in s.get("decisions", [])]})
    last = issues[-1]
    return dict(_rec_out(rec), group_name=rev.get("group_name") or "", scheme=scheme_name(),
                issues=list(reversed(issues)), latest=last,
                can_decide=(last["no"] == latest), thread=clp_notes.review_thread(cid, rev["group_id"], names))


def issue_file_for_reviewer(clp_id, issue_no, rev):
    """(file name, bytes) of an issue SENT to the group, exactly as approved (the stored file; nothing is built)."""
    sent = _sent_to(rev)
    cid = str(clp_id or "")
    try:
        no = int(issue_no)
    except (TypeError, ValueError):
        return None
    if no not in sent.get(cid, []):
        return None
    rows = db.query("SELECT file_name, file_b64 FROM clp_issues WHERE tenant_id = ? AND clp_id = ? AND issue_no = ?",
                    (_tenant(), cid, no))
    if not rows or not rows[0].get("file_b64"):
        return None
    return rows[0]["file_name"], base64.b64decode(rows[0]["file_b64"])


def comment(clp_id, words, rev):
    """A reviewer's comment: a note in the CLP's thread for the contractor and the group. Sends nothing (Q7)."""
    import clp_notes
    cid = str(clp_id or "")
    if cid not in _sent_to(rev):
        return {"error": "No such CLP.", "status": 404}
    words = _clean(words, WORDS_MAX)
    if not words:
        return {"error": "Write a comment first.", "status": 422}
    p = _banned(words)
    if p:
        return {"error": p, "status": 422}
    clp_notes.add_review_note(cid, words, rev)
    return clp_for_reviewer(cid, rev)


def decide(clp_id, issue_no, decision, words, rev):
    """Accept or return the latest issue sent to the group (the CLP's latest issue). Returned needs a comment. The decision
    is the group's; a later one by another reviewer in the group replaces it (both kept). Emails the person who sent it."""
    import clp_notes
    cid = str(clp_id or "")
    sent = _sent_to(rev)
    if cid not in sent:
        return {"error": "No such CLP.", "status": 404}
    if decision not in DECISIONS:
        return {"error": "Accept or return the issue.", "status": 422}
    try:
        no = int(issue_no)
    except (TypeError, ValueError):
        return {"error": "No such issue.", "status": 404}
    if no not in sent[cid]:
        return {"error": "No such issue.", "status": 404}
    if no != sent[cid][-1] or no != _latest_issue_no(cid):
        return {"error": f"Issue {no} is no longer the latest. Decide on the latest issue.", "status": 422}
    words = _clean(words, WORDS_MAX)
    if decision == "returned" and not words:
        return {"error": "Say what needs changing.", "status": 422}
    p = _banned(words)
    if p:
        return {"error": p, "status": 422}
    stand = (_standing(_review_rows(cid)).get((cid, no, rev["group_id"])) or {})
    prev = stand.get("decision")
    if prev and prev.get("decision") == decision and not words:
        return clp_for_reviewer(cid, rev)
    row = _insert_review({"clp_id": cid, "issue_no": no, "group_id": rev["group_id"], "kind": "decision",
                          "decision": decision, "words": words or None, "by_name": rev["name"],
                          "by_user": rev["user_id"]})
    if words:
        clp_notes.add_review_note(cid, words, rev, at=row["at"])
    clp_notes.add_review_step(cid, "review-" + decision, f"{rev['name']} ({rev.get('group_name') or ''})", row["at"],
                              rev["group_id"], no)
    rec = _clp_record(cid)
    email_sender(stand.get("sent"), rec, no, decision, words, rev)
    return clp_for_reviewer(cid, rev)

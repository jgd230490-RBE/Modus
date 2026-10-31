"""
clp_notes.py — notes and tasks on each Construction Logistics Plan. Wayscope, 31 Oct 2026 (task 4a, PR 3b). Mockup
approved by John 31 Oct (notes/clp-notes-mockup-1031/, Q1–Q12 as recommended): "everyone should be able to leave
notes/task for each clp".

WHO
---
Anyone who can see a CLP (clp_records.visible: a team its own team's CLPs, a planner or an admin every one, a sign-in
with no team that cannot approve every one) writes a note on it, adds a task and ticks a task done or back (Q3). A note is
deleted, never edited, by its writer, a planner or an admin; a task is edited or deleted by the same (Q5).

ONE TABLE, FOUR KINDS OF ROW (clp_notes)
-----------------------------------------
  * note  — words, who wrote them and when;
  * task  — words, For (the CLP's team / the planners and admins / one person who can see the CLP), an optional due date,
            the "To complete" line it started from, who ticked it done and when (Q4, Q7);
  * step  — the approval chain as it happens (sent, changes asked, approved as Issue N) with its note, so the thread tells
            the whole story (Q6). Steps from before 3b are read from the CLP and its issues (thread(): no row needed);
  * lines — the "Still to complete" list of the LAST draft or issue built for the CLP, one row a CLP, written by the build
            (keep_lines). Nothing is built just for this list (Q7). A task whose line is no longer in a later list says so;
            it is never ticked by itself (Q8).

RULES
-----
* Notes and tasks never print in the Word file (Q11). Deleting a CLP made with + New CLP removes them; clearing a listed
  row's typed details keeps them (Q12, clp_records.delete).
* clp_notes is a NO_DATA_TABLES table (db.py): no figure and no kept read is built from it, so a note, a tick or the kept
  lines never throw away the kept CLP drafts (each costs a heavy build) or any other kept read.
* One email, only when a task is given to one named person other than the writer (Q10); nothing else emails.
* Every SQL literal carries the tenant predicate (test_tenant_audit). No team id is ever in a reply's words.
"""
import datetime
import itertools
import json
import re
import secrets
import time

import access
import db
import taxonomy

import clp_doc
import clp_records

KINDS = ("note", "task", "step", "lines")
STEPS = {"sent": "Sent for approval", "changes": "Changes asked", "approved": "Approved"}
WORDS_MAX = 1000
LINE_MAX = 600
COLS = ("id, clp_id, kind, words, for_kind, for_team, for_user, due, from_line, done_by, done_at, step, issue_no, "
        "written_by, written_key, written_at, updated_at")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _today():
    return datetime.date.today().isoformat()


def key_of(acc):
    """Who a row belongs to: the person's login, else the sign-in's role and team (a shared code)."""
    acc = acc or {}
    if acc.get("user_id"):
        return f"u:{acc['user_id']}"
    return f"c:{acc.get('role') or ''}:{access.canonical_ipt(acc.get('ipt')) or ''}"


def _rows(clp_id=None, kinds=None):
    if clp_id is None:
        rows = db.query(f"SELECT {COLS} FROM clp_notes WHERE tenant_id = ? ORDER BY written_at, id", (db.current_tenant(),))
    else:
        rows = db.query(f"SELECT {COLS} FROM clp_notes WHERE tenant_id = ? AND clp_id = ? ORDER BY written_at, id",
                        (db.current_tenant(), clp_id))
    return [r for r in rows if not kinds or r.get("kind") in kinds]


_SEQ = itertools.count()


def new_id():
    """'n-' + the time in ms + a counter + a little random: rows written in the same second keep the order they were
    written in (the thread reads oldest first by time, then by id)."""
    return f"n-{int(time.time() * 1000):011x}{next(_SEQ) % 4096:03x}{secrets.token_hex(2)}"


def _insert(row):
    row = dict(row)
    row.setdefault("id", new_id())
    row.setdefault("written_at", _now())
    cols = [c.strip() for c in COLS.split(",")]
    db.execute(f"INSERT INTO clp_notes (tenant_id, {COLS}) VALUES ({', '.join(['?'] * (len(cols) + 1))})",
               tuple([db.current_tenant()] + [row.get(c) for c in cols]))
    return row["id"]


def _clean(v, most):
    return str(v or "").strip()[:most]


def _words_problem(words, what="a note"):
    if not words:
        return f"Write {what} first."
    for w in clp_doc.banned_words(words):
        return f"Please do not use the word \"{w}\" on a CLP."
    return None


# --------------------------------------------------------------------------- #
#  The people a task can be for                                               #
# --------------------------------------------------------------------------- #
def _logins():
    """Enabled, unexpired STAFF logins (never a demo lead's: a lead is not offered, and never sees, anyone's name)."""
    import users
    return [u for u in users.list_users() if users.usable(u) and (u.get("kind") or "staff") == "staff"]


def _sees(user, rec):
    """Can this login see the CLP? (clp_records.visible, for a login rather than a request.)"""
    if user.get("role") in ("planner", "admin"):
        return True
    if user.get("role") == "team":
        return bool(rec.get("team")) and access.canonical_ipt(user.get("team")) == access.canonical_ipt(rec.get("team"))
    return False


def for_options(rec, acc, labels=None):
    """What a task on this CLP can be For, in words: its team (a team CLP), the planners and admins, and each person who
    can see the CLP (none for a demo lead)."""
    labels = labels if labels is not None else taxonomy.team_labels()
    out = []
    if rec.get("team"):
        out.append({"key": "team", "word": taxonomy.team_name(rec["team"], labels)})
    out.append({"key": "approvers", "word": "Planners and admins"})
    if (acc or {}).get("kind") == "demo":
        return out
    for u in sorted(_logins(), key=lambda u: (u.get("name") or u.get("email") or "").lower()):
        if _sees(u, rec):
            out.append({"key": f"user:{u['id']}", "word": u.get("name") or u.get("email")})
    return out


def _for_word(row, rec, labels, names):
    k = row.get("for_kind")
    if k == "team":
        return taxonomy.team_name(row.get("for_team") or rec.get("team"), labels) or "The team"
    if k == "approvers":
        return "Planners and admins"
    if k == "person":
        return names.get(row.get("for_user")) or "A person no longer here"
    return ""


def _mine(row, acc):
    """Is this task given to the caller: by name, to their team, or to the planners and admins they are one of?"""
    k = row.get("for_kind")
    if k == "person":
        return bool((acc or {}).get("user_id")) and row.get("for_user") == acc.get("user_id")
    if k == "team":
        t = access.canonical_ipt((acc or {}).get("ipt"))
        return bool(t) and t == access.canonical_ipt(row.get("for_team"))
    if k == "approvers":
        return access.can_approve(acc)
    return False


# --------------------------------------------------------------------------- #
#  The kept "Still to complete" lines                                          #
# --------------------------------------------------------------------------- #
def keep_lines(clp_id, todos):
    """After a draft or an issue is built: keep its "Still to complete" list (one row a CLP; written only when it moved,
    so an unchanged rebuild writes nothing)."""
    items = [_clean(t, LINE_MAX) for t in (todos or []) if str(t or "").strip()]
    words = json.dumps(items, ensure_ascii=False)
    have = _rows(clp_id, ("lines",))
    if have and have[-1].get("words") == words:
        return False
    db.execute("DELETE FROM clp_notes WHERE tenant_id = ? AND clp_id = ? AND kind = 'lines'", (db.current_tenant(), clp_id))
    _insert({"clp_id": clp_id, "kind": "lines", "words": words, "written_by": "Wayscope", "written_key": "wayscope"})
    return True


def split_line(item):
    """'2.4.1: Melton BC: the code …' -> ('2.4.1', 'Melton BC: the code …'); the section is what Still to complete names."""
    where, _, what = str(item or "").partition(": ")
    if not what:
        where, what = "", str(item or "")
    return where, what[:1].upper() + what[1:]     # a task reads as a sentence: "Who owns the land …"


def _lines(rows):
    got = [r for r in rows if r.get("kind") == "lines"]
    if not got:
        return None
    try:
        items = json.loads(got[-1].get("words") or "[]")
    except (TypeError, ValueError):
        items = []
    return {"at": got[-1].get("written_at"), "items": [
        {"line": it, "section": split_line(it)[0], "words": split_line(it)[1]} for it in items]}


# --------------------------------------------------------------------------- #
#  Reading                                                                     #
# --------------------------------------------------------------------------- #
def _can_change(row, acc):
    return access.can_approve(acc) or row.get("written_key") == key_of(acc)


def _task_out(row, rec, acc, labels, names, lines, today):
    gone = None     # the line came from a kept list, so missing from the one kept now = a later build no longer has it
    if row.get("from_line") and lines and row["from_line"] not in {i["line"] for i in lines["items"]}:
        gone = lines["at"]
    due = row.get("due")
    done = bool(row.get("done_at"))
    return {"id": row["id"], "words": row.get("words") or "", "for": _for_key(row), "for_word": _for_word(row, rec, labels, names),
            "due": due, "overdue": bool(due and not done and due < today), "done": done,
            "done_by": row.get("done_by"), "done_at": row.get("done_at"),
            "from_line": row.get("from_line"), "from_section": (split_line(row["from_line"])[0] if row.get("from_line") else None),
            "line_gone_at": gone, "written_by": row.get("written_by"), "written_at": row.get("written_at"),
            "mine": _mine(row, acc), "can_change": _can_change(row, acc)}


def _for_key(row):
    k = row.get("for_kind")
    return f"user:{row.get('for_user')}" if k == "person" else (k or "")


def _steps_from_record(rec, issues):
    """The chain's steps that happened before 3b wrote them down: each issue, and the CLP's present sent / changes."""
    out = []
    for i in issues:
        out.append({"step": "approved", "issue_no": i["issue_no"], "at": str(i.get("approved_at") or ""),
                    "by": i.get("approved_by"), "words": i.get("approver_note")})
    if rec.get("sent_at"):
        out.append({"step": "sent", "issue_no": None, "at": rec["sent_at"], "by": rec.get("sent_by"),
                    "words": rec.get("sent_note")})
    if rec.get("changes_at"):
        out.append({"step": "changes", "issue_no": None, "at": rec["changes_at"], "by": rec.get("changes_by"),
                    "words": rec.get("changes_note")})
    return out


def thread(clp_id, acc, factors=None):
    """The panel: the tasks (open first, by due date; then done), the notes with the chain's steps in time order, the kept
    lines, what a task can be For. None when the CLP does not exist or this caller may not see it (the same answer)."""
    rec = clp_records._record(clp_id, acc, factors)
    if not rec:
        return None
    rows = _rows(rec["id"])
    labels = taxonomy.team_labels()
    names = {u["id"]: (u.get("name") or u.get("email")) for u in _all_users()}
    lines = _lines(rows)
    today = _today()
    tasks = [_task_out(r, rec, acc, labels, names, lines, today) for r in rows if r.get("kind") == "task"]
    tasks.sort(key=lambda t: (t["done"], t["done_at"] or "" if t["done"] else "", t["due"] or "9999", t["written_at"] or ""))
    items = []
    for r in rows:
        if r.get("kind") == "note":
            items.append({"kind": "note", "id": r["id"], "words": r.get("words") or "", "by": r.get("written_by"),
                          "at": r.get("written_at"), "can_delete": _can_change(r, acc)})
    written = {(r.get("step"), r.get("written_at")) for r in rows if r.get("kind") == "step"}
    written_issues = {r.get("issue_no") for r in rows if r.get("kind") == "step" and r.get("step") == "approved"}
    for r in rows:
        if r.get("kind") == "step":
            items.append({"kind": "step", "id": r["id"], "step": r.get("step"), "step_word": _step_word(r.get("step"), r.get("issue_no")),
                          "issue_no": r.get("issue_no"), "by": r.get("written_by"), "at": r.get("written_at"),
                          "words": r.get("words") or ""})
    for s in _steps_from_record(rec, clp_records._issue_rows(rec["id"])):
        if (s["step"], s["at"]) in written or (s["step"] == "approved" and s["issue_no"] in written_issues):
            continue
        items.append({"kind": "step", "step": s["step"], "step_word": _step_word(s["step"], s["issue_no"]),
                      "issue_no": s["issue_no"], "by": s["by"], "at": s["at"], "words": s["words"] or ""})
    items.sort(key=lambda i: (i["at"] or "", i.get("id") or ""))
    return {"id": rec["id"], "tasks": tasks, "notes": items, "lines": lines,
            "for_options": for_options(rec, acc, labels), "can_moderate": access.can_approve(acc), "today": today}


def _all_users():
    import users
    return users.list_users()


def _step_word(step, issue_no):
    if step == "approved":
        return f"Approved as Issue {issue_no}" if issue_no else "Approved"
    return STEPS.get(step, step or "")


def counts():
    """{clp id: {open, overdue, next_due, notes, mine_open}} for the list's Tasks column (one read for every CLP);
    `mine_open` needs the caller, so it is filled by counts_for()."""
    out = {}
    today = _today()
    for r in _rows(kinds=("note", "task")):
        c = out.setdefault(r["clp_id"], {"open": 0, "overdue": 0, "next_due": None, "notes": 0, "done": 0, "_open": []})
        if r["kind"] == "note":
            c["notes"] += 1
        elif r.get("done_at"):
            c["done"] += 1
        else:
            c["open"] += 1
            c["_open"].append(r)
            if r.get("due") and r["due"] < today:
                c["overdue"] += 1
            elif r.get("due") and (c["next_due"] is None or r["due"] < c["next_due"]):
                c["next_due"] = r["due"]
    return out


def counts_for(acc):
    out = counts()
    for c in out.values():
        c["mine_open"] = sum(1 for r in c.pop("_open") if _mine(r, acc))
    return out


def open_summary(clp_id):
    """What the approve card says about the tasks: how many open, how many overdue, the first overdue one's words."""
    today = _today()
    open_ = [r for r in _rows(clp_id, ("task",)) if not r.get("done_at")]
    over = sorted([r for r in open_ if r.get("due") and r["due"] < today], key=lambda r: r["due"])
    return {"open": len(open_), "overdue": len(over), "first_overdue": (over[0].get("words") if over else None)}


# --------------------------------------------------------------------------- #
#  Writing                                                                     #
# --------------------------------------------------------------------------- #
def add_note(clp_id, words, acc, factors=None):
    rec = clp_records._record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    words = _clean(words, WORDS_MAX)
    p = _words_problem(words)
    if p:
        return {"error": p, "status": 422}
    nid = _insert({"clp_id": rec["id"], "kind": "note", "words": words, "written_by": clp_records.who(acc),
                   "written_key": key_of(acc)})
    return {"id": nid, "thread": thread(rec["id"], acc, factors)}


def _for_problem(for_key, rec, acc):
    """(for_kind, for_team, for_user) for a For key, or an error string."""
    k = str(for_key or "").strip()
    if k == "team":
        if not rec.get("team"):
            return "This CLP covers every team: give the task to the planners and admins or to a person."
        return ("team", rec["team"], None)
    if k == "approvers":
        return ("approvers", None, None)
    if k.startswith("user:"):
        if (acc or {}).get("kind") == "demo":
            return "Give the task to the team or to the planners and admins."
        uid = k[5:]
        u = next((u for u in _logins() if str(u["id"]) == uid), None)
        if not u or not _sees(u, rec):
            return "That person cannot see this CLP."
        return ("person", None, u["id"])
    return "Say who the task is for."


def _due_problem(due):
    if due in (None, ""):
        return None
    if not isinstance(due, str) or not _DATE.match(due):
        return "The due date must be a date."
    try:
        d = datetime.date.fromisoformat(due)
    except ValueError:
        return "The due date must be a date."
    if not (2020 <= d.year <= 2100):
        return "The due date must be a date."
    return None


def add_task(clp_id, body, acc, factors=None, mail=True):
    """{words, for, due, from_line} -> the task, and whether its email went ('sent' / 'unsent' / 'failed' / None)."""
    rec = clp_records._record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    body = body or {}
    words = _clean(body.get("words"), WORDS_MAX)
    p = _words_problem(words, "the task")
    if p:
        return {"error": p, "status": 422}
    f = _for_problem(body.get("for"), rec, acc)
    if isinstance(f, str):
        return {"error": f, "status": 422}
    due = body.get("due") or None
    p = _due_problem(due)
    if p:
        return {"error": p, "status": 422}
    line = _clean(body.get("from_line"), LINE_MAX) or None
    nid = _insert({"clp_id": rec["id"], "kind": "task", "words": words, "for_kind": f[0], "for_team": f[1],
                   "for_user": f[2], "due": due, "from_line": line, "written_by": clp_records.who(acc),
                   "written_key": key_of(acc)})
    sent = None
    if mail and f[0] == "person" and str(f[2]) != str((acc or {}).get("user_id") or ""):
        sent = email_task(f[2], rec, words, due, clp_records.who(acc))
    return {"id": nid, "email": sent, "thread": thread(rec["id"], acc, factors)}


def change_task(clp_id, task_id, body, acc, factors=None, mail=True):
    """Tick done / back (anyone who can see the CLP); words, For and due (its writer, a planner or an admin)."""
    rec = clp_records._record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    rows = [r for r in _rows(rec["id"], ("task",)) if r["id"] == str(task_id)]
    if not rows:
        return {"error": "No such task.", "status": 404}
    row = rows[0]
    body = body or {}
    sets = {}
    if any(k in body for k in ("words", "for", "due")):
        if not _can_change(row, acc):
            return {"error": "The task's writer, a planner or an admin changes it.", "status": 403}
        if "words" in body:
            w = _clean(body.get("words"), WORDS_MAX)
            p = _words_problem(w, "the task")
            if p:
                return {"error": p, "status": 422}
            sets["words"] = w
        if "for" in body:
            f = _for_problem(body.get("for"), rec, acc)
            if isinstance(f, str):
                return {"error": f, "status": 422}
            sets.update({"for_kind": f[0], "for_team": f[1], "for_user": f[2]})
        if "due" in body:
            p = _due_problem(body.get("due") or None)
            if p:
                return {"error": p, "status": 422}
            sets["due"] = body.get("due") or None
    if "done" in body:
        if body["done"]:
            if not row.get("done_at"):
                sets.update({"done_by": clp_records.who(acc), "done_at": _now()})
        else:
            sets.update({"done_by": None, "done_at": None})
    if not sets:
        return {"thread": thread(rec["id"], acc, factors)}
    sets["updated_at"] = _now()
    cols = list(sets)
    db.execute("UPDATE clp_notes SET {} WHERE tenant_id = ? AND clp_id = ? AND id = ?".format(", ".join(c + " = ?" for c in cols)),
               tuple(sets[c] for c in cols) + (db.current_tenant(), rec["id"], row["id"]))
    sent = None
    if mail and sets.get("for_kind") == "person" and sets.get("for_user") != row.get("for_user") \
            and str(sets["for_user"]) != str((acc or {}).get("user_id") or ""):
        sent = email_task(sets["for_user"], rec, sets.get("words") or row.get("words"), sets.get("due", row.get("due")),
                          clp_records.who(acc))
    return {"email": sent, "thread": thread(rec["id"], acc, factors)}


def remove(clp_id, item_id, acc, factors=None):
    """Delete a note or a task: its writer, a planner or an admin. A step and the kept lines are never deleted here."""
    rec = clp_records._record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    rows = [r for r in _rows(rec["id"], ("note", "task")) if r["id"] == str(item_id)]
    if not rows:
        return {"error": "No such note or task.", "status": 404}
    if not _can_change(rows[0], acc):
        return {"error": "Its writer, a planner or an admin deletes it.", "status": 403}
    db.execute("DELETE FROM clp_notes WHERE tenant_id = ? AND clp_id = ? AND id = ?",
               (db.current_tenant(), rec["id"], rows[0]["id"]))
    return {"deleted": rows[0]["id"], "thread": thread(rec["id"], acc, factors)}


def add_step(clp_id, step, by, at, words=None, issue_no=None):
    """The chain writes its steps here as they happen (clp_records.send / ask_changes / approve)."""
    _insert({"clp_id": clp_id, "kind": "step", "step": step, "issue_no": issue_no, "words": (words or None),
             "written_by": by, "written_key": "step", "written_at": at})


def drop_all(clp_id):
    """A CLP made with + New CLP is deleted: its notes, tasks, steps and kept lines go with it (Q12)."""
    db.execute("DELETE FROM clp_notes WHERE tenant_id = ? AND clp_id = ?", (db.current_tenant(), clp_id))


# --------------------------------------------------------------------------- #
#  The one email (Q10)                                                         #
# --------------------------------------------------------------------------- #
def task_message(user, rec, words, due, by, settings, demo_notice=None):
    from email.message import EmailMessage
    import users
    team = taxonomy.team_name(rec["team"]) if rec.get("team") else "All teams"
    place = rec.get("name") or "a CLP"
    msg = EmailMessage()
    msg["Subject"] = f"A task on the CLP for {place}"
    msg["From"] = settings["DEMO_FROM"]
    msg["To"] = user["email"]
    msg["Reply-To"] = settings["reply_to"]
    due_words = ""
    if due:
        d = datetime.date.fromisoformat(due)
        due_words = f"Due {d.day} {clp_doc.MONTHS[d.month - 1]} {d.year}.\n\n"
    body = (f"{by} gave you a task on the CLP for {place} · {team}:\n\n{words}\n\n{due_words}"
            f"Open it: Plan → CLP documents, {users.app_url()}/#clp\n\n")
    if demo_notice:
        body += f"DEMO · {demo_notice}\n\n"
    msg.set_content(body + "Wayscope\n")
    return msg


def email_task(user_id, rec, words, due, by):
    """'sent', 'unsent' (no sender set up, or the login has no address) or 'failed'. Never raises."""
    import users
    u = users.get_user(user_id)
    if not u or not u.get("email"):
        return "unsent"
    settings = users.mail_settings()
    if settings is None:
        return "unsent"
    try:
        import config
        import conversions
        notice = ((config.load(conversions) or {}).get("tenant") or {}).get("demo_notice")
    except Exception:  # noqa: BLE001
        notice = None
    try:
        import demo_request
        demo_request.send(task_message(u, rec, words, due, by, settings, notice), settings)
        return "sent"
    except Exception as e:  # noqa: BLE001
        print(f"clp_notes: task email FAILED {e.__class__.__name__}: {str(e)[:200]}")
        return "failed"

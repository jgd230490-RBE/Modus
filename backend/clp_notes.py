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

THE CLIENT'S REVIEWERS (31 Oct 2026, PR 3c, clp_reviews.py)
-----------------------------------------------------------
A reviewer's COMMENT is a note with written_key 'r:<login>' and its group; the send / accept / return lines are steps
'review-sent' / 'review-accepted' / 'review-returned' with the group. A contractor never deletes a reviewer's words.

TWO THREADS (31 Oct 2026, PR 3d; mockup notes/clp-client-thread-mockup-1031/, John: "the client and admin/planner
should also have notes and task seperatly between each other", Q1–Q10 as recommended)
-------------------------------------------------------------------------------------------------------------------
`review_group` on a row says which thread it is in: NULL = the CONTRACTOR's thread (the team, the planners and admins,
as in 3b); a group id = that group's CLIENT thread (the group's reviewers + the planners and admins). A client thread
has notes AND tasks both ways:
  * For: 'approvers' (the planners and admins), 'person' (one planner or admin by name), 'group' (the whole group: any
    of its reviewers ticks it) or 'reviewer' (one reviewer by name, `for_user`);
  * each side ticks its own (the contractor 'approvers' / 'person', the client 'group' / 'reviewer'); each side edits
    and deletes only what its side wrote, and a reviewer only their own (Q5, Q10);
  * the TEAM never reads, counts or writes a client thread (Q4): every contractor read and write below treats a client
    row as missing for anyone who cannot approve;
  * Make a task from a client note lands in that client thread, For the planners and admins (Q6; `from_note`);
  * the Contractor thread keeps the send / decision lines (grey) and nothing else of the client's (Q3).
The "Show to <group>" tick is gone (Q2): `show_to` is now just another name for writing in that group's thread.
On the build every 3c reviewer comment, shown-to note and review step already carried its group, so it now sits in the
group's thread; nothing moved and nothing was deleted.

RULES
-----
* Notes and tasks never print in the Word file (Q11). Deleting a CLP made with + New CLP removes them; clearing a listed
  row's typed details keeps them (Q12, clp_records.delete).
* clp_notes is a NO_DATA_TABLES table (db.py): no figure and no kept read is built from it, so a note, a tick or the kept
  lines never throw away the kept CLP drafts (each costs a heavy build) or any other kept read.
* One email, only when a task is given to one named person other than the writer (Q10; PR 3d Q9: a planner, an admin
  or a reviewer by name — a reviewer's link opens CLPs for review); nothing else emails.
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
REVIEW_STEPS = ("review-sent", "review-accepted", "review-returned")
WORDS_MAX = 1000
LINE_MAX = 600
COLS = ("id, clp_id, kind, words, for_kind, for_team, for_user, due, from_line, done_by, done_at, step, issue_no, "
        "written_by, written_key, written_at, updated_at, review_group, from_note")
CLIENT_FOR = ("approvers", "person", "group", "reviewer")     # PR 3d: who a task in a client thread can be for
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
def _is_review_comment(row):
    return str(row.get("written_key") or "").startswith("r:")


def _can_change(row, acc):
    if _is_review_comment(row):
        return False        # PR 3c: the client's words stay as written
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
    all_rows = _rows(rec["id"])
    rows = [r for r in all_rows if not _client(r)]      # PR 3d: the contractor's thread; client rows are in `clients`
    labels = taxonomy.team_labels()
    names = {u["id"]: (u.get("name") or u.get("email")) for u in _all_users()}
    lines = _lines(all_rows)
    today = _today()
    tasks = [_task_out(r, rec, acc, labels, names, lines, today) for r in rows if r.get("kind") == "task"]
    _sort_tasks(tasks)
    groups = _group_names()
    appr = access.can_approve(acc)
    items = []
    for r in rows:
        if r.get("kind") == "note":
            items.append({"kind": "note", "id": r["id"], "words": r.get("words") or "", "by": r.get("written_by"),
                          "at": r.get("written_at"), "can_delete": _can_change(r, acc)})
    written = {(r.get("step"), r.get("written_at")) for r in all_rows if r.get("kind") == "step"}
    written_issues = {r.get("issue_no") for r in all_rows if r.get("kind") == "step" and r.get("step") == "approved"}
    for r in all_rows:
        if r.get("kind") == "step" and (not _client(r) or r.get("step") in REVIEW_STEPS):
            # PR 3d (Q3): a send / decision line stays here, grey; an approver's opens the group's tab (`group_id`)
            items.append({"kind": "step", "id": r["id"], "step": r.get("step"),
                          "step_word": _step_word(r.get("step"), r.get("issue_no"), groups.get(r.get("review_group"))),
                          "issue_no": r.get("issue_no"), "by": r.get("written_by"), "at": r.get("written_at"),
                          "words": r.get("words") or "", "group_id": (r.get("review_group") if appr else None)})
    for s in _steps_from_record(rec, clp_records._issue_rows(rec["id"])):
        if (s["step"], s["at"]) in written or (s["step"] == "approved" and s["issue_no"] in written_issues):
            continue
        items.append({"kind": "step", "step": s["step"], "step_word": _step_word(s["step"], s["issue_no"]),
                      "issue_no": s["issue_no"], "by": s["by"], "at": s["at"], "words": s["words"] or ""})
    items.sort(key=lambda i: (i["at"] or "", i.get("id") or ""))
    clients = [client_thread(rec, g, all_rows, "contractor", acc) for g in sent_groups(rec["id"])] if appr else []
    return {"id": rec["id"], "tasks": tasks, "notes": items, "lines": lines,
            "for_options": for_options(rec, acc, labels), "can_moderate": appr, "today": today,
            "clients": clients}


def _sort_tasks(tasks):
    tasks.sort(key=lambda t: (t["done"], t["done_at"] or "" if t["done"] else "", t["due"] or "9999", t["written_at"] or ""))


def _group_names():
    import clp_reviews
    return clp_reviews.group_names()


# --------------------------------------------------------------------------- #
#  PR 3d: the client threads (one a reviewer group the CLP was sent to)        #
# --------------------------------------------------------------------------- #
def _client(row):
    """The reviewer group whose thread a row is in; None = the contractor's thread."""
    return row.get("review_group") or None


def sent_groups(clp_id):
    """[{id, name, stopped}] — each group an issue of this CLP was sent to, first sent first (a stopped one stays readable)."""
    import clp_reviews
    groups = clp_reviews._groups()
    seen = []
    for r in clp_reviews._review_rows(clp_id, "sent"):
        if r["group_id"] in groups and r["group_id"] not in seen:
            seen.append(r["group_id"])
    return [{"id": g, "name": groups[g].get("name") or "", "stopped": bool(groups[g].get("stopped_at"))} for g in seen]


def _group_for_write(clp_id, group_id):
    """The client thread a planner or an admin writes in, or an error dict."""
    g = next((g for g in sent_groups(clp_id) if g["id"] == str(group_id)), None)
    if not g:
        return {"error": "This CLP was not sent to that group.", "status": 422}
    if g["stopped"]:
        return {"error": "That group is stopped: nothing new can be written to it.", "status": 422}
    return g


def _side_key(side, who):
    return f"r:{who['user_id']}" if side == "client" else key_of(who)


def _side_name(side, who):
    return who["name"] if side == "client" else clp_records.who(who)


def _client_for_key(row):
    k = row.get("for_kind")
    if k == "person":
        return f"user:{row.get('for_user')}"
    if k == "reviewer":
        return f"reviewer:{row.get('for_user')}"
    return k or ""


def _client_for_word(row, g, side, names):
    k = row.get("for_kind")
    if k == "approvers":
        return "Planners and admins" if side == "contractor" else "The contractor"
    if k == "group":
        return g["name"] if side == "contractor" else "Your group"
    if k in ("person", "reviewer"):
        return names.get(row.get("for_user")) or "A person no longer here"
    return ""


def _client_mine(row, side, who):
    k = row.get("for_kind")
    if side == "contractor":
        return k == "approvers" or (k == "person" and bool(who.get("user_id")) and row.get("for_user") == who["user_id"])
    return k == "group" or (k == "reviewer" and row.get("for_user") == who["user_id"])


def _client_can_tick(row, side, who):
    """Each side ticks its own (Q5): the contractor a task for the planners and admins or one of them, the client a task
    for the group or for the reviewer themself."""
    k = row.get("for_kind")
    if side == "contractor":
        return k in ("approvers", "person")
    return k == "group" or (k == "reviewer" and row.get("for_user") == who["user_id"])


def _client_can_change(row, side, who):
    """Q10: the contractor edits / deletes what the contractor wrote (only planners and admins write here); a reviewer
    only their own words; nobody the other side's."""
    if side == "contractor":
        return not _is_review_comment(row)
    if row.get("kind") == "note" and row.get("step") in REVIEW_STEPS:
        return False    # the note that went with an Accept or a Return stays as written (its decision is kept)
    return row.get("written_key") == f"r:{who['user_id']}"


def _group_reviewers(gid):
    import clp_reviews
    import users
    return [u for u in clp_reviews._reviewers() if u.get("review_group") == gid and users.usable(u)]


def _approver_logins():
    return [u for u in _logins() if u.get("role") in ("planner", "admin")]


def _by_name(us):
    return sorted(us, key=lambda u: ((u.get("name") or u.get("email") or "").lower(), u["id"]))


def client_for_options(g, side, who):
    """What a task in this client thread can be For. The contractor: the planners and admins, the group, each of its
    reviewers, each planner or admin. A reviewer: the contractor, the group, each other reviewer in the group."""
    if side == "contractor":
        out = [{"key": "approvers", "word": "Planners and admins"}, {"key": "group", "word": f"{g['name']} — all its reviewers"}]
        out += [{"key": f"reviewer:{u['id']}", "word": u.get("name") or u.get("email")} for u in _by_name(_group_reviewers(g["id"]))]
        out += [{"key": f"user:{u['id']}", "word": u.get("name") or u.get("email")} for u in _by_name(_approver_logins())]
        return out
    out = [{"key": "approvers", "word": "The contractor (planners and admins)"}, {"key": "group", "word": "Your group"}]
    out += [{"key": f"reviewer:{u['id']}", "word": u.get("name") or u.get("email")}
            for u in _by_name(_group_reviewers(g["id"])) if u["id"] != who.get("user_id")]
    return out


def _client_for_problem(for_key, g, side):
    """(for_kind, None, for_user) for a For key in a client thread, or an error string."""
    k = str(for_key or "").strip()
    if k in ("approvers", "group"):
        return (k, None, None)
    if k.startswith("reviewer:"):
        u = next((u for u in _group_reviewers(g["id"]) if str(u["id"]) == k[9:]), None)
        if not u:
            return "That person is not a reviewer in this group."
        return ("reviewer", None, u["id"])
    if k.startswith("user:") and side == "contractor":
        u = next((u for u in _approver_logins() if str(u["id"]) == k[5:]), None)
        if not u:
            return "Give a task in the client's tab to a planner, an admin or the client."
        return ("person", None, u["id"])
    if k.startswith("user:"):
        return "Give the task to the contractor, your group or one reviewer."
    return "Say who the task is for."


def _client_task_out(row, g, side, who, names, today, note_by):
    due = row.get("due")
    done = bool(row.get("done_at"))
    return {"id": row["id"], "words": row.get("words") or "", "for": _client_for_key(row),
            "for_word": _client_for_word(row, g, side, names),
            "for_side": ("contractor" if row.get("for_kind") in ("approvers", "person") else "client"),
            "due": due, "overdue": bool(due and not done and due < today), "done": done,
            "done_by": row.get("done_by"), "done_at": row.get("done_at"),
            "written_by": row.get("written_by"), "written_at": row.get("written_at"),
            "by_client": _is_review_comment(row), "from_note_by": note_by.get(row.get("from_note")),
            "mine": _client_mine(row, side, who), "can_tick": _client_can_tick(row, side, who),
            "can_change": _client_can_change(row, side, who)}


def client_thread(rec, g, rows, side, who):
    """One client thread as `side` ('contractor' = a planner or an admin, `who` their access; 'client' = a reviewer of
    the group, `who` the reviewer dict) reads it: tasks, then the notes with the group's send / decision lines."""
    import clp_reviews
    gid = g["id"]
    mine = [r for r in rows if r.get("review_group") == gid]
    names = {u["id"]: (u.get("name") or u.get("email")) for u in _all_users()}
    note_by = {r["id"]: r.get("written_by") for r in mine if r.get("kind") == "note"}
    today = _today()
    tasks = [_client_task_out(r, g, side, who, names, today, note_by) for r in mine if r.get("kind") == "task"]
    _sort_tasks(tasks)
    scheme = clp_reviews.scheme_name()
    notes = []
    for r in mine:
        if r.get("kind") == "note":
            rv = _is_review_comment(r)
            notes.append({"kind": "note", "id": r["id"], "words": r.get("words") or "", "by": r.get("written_by"),
                          "at": r.get("written_at"), "reviewer": rv, "org": (g["name"] if rv else scheme),
                          "can_delete": _client_can_change(r, side, who),
                          "can_task": bool(side == "contractor" and rv and not g["stopped"])})
        elif r.get("kind") == "step" and r.get("step") in REVIEW_STEPS:
            notes.append({"kind": "step", "id": r["id"], "step": r["step"],
                          "step_word": _step_word(r["step"], r.get("issue_no"), g["name"]),
                          "issue_no": r.get("issue_no"), "by": r.get("written_by"), "at": r.get("written_at")})
    notes.sort(key=lambda i: (i["at"] or "", i["id"]))
    open_ = [t for t in tasks if not t["done"]]
    return {"id": gid, "name": g["name"], "stopped": g["stopped"], "tasks": tasks, "notes": notes,
            "for_options": ([] if g["stopped"] else client_for_options(g, side, who)), "can_write": not g["stopped"],
            "open": len(open_), "overdue": sum(1 for t in open_ if t["overdue"]),
            "open_ours": sum(1 for t in open_ if t["for_side"] == ("contractor" if side == "contractor" else "client")),
            "today": today}


def review_thread(clp_id, group_id, names=None):
    """What a REVIEWER of `group_id` reads on this CLP: their group's thread's notes and lines (PR 3c), now with the
    contractor's notes written in that thread (PR 3d). Never the contractor's thread, the kept lines or another group's."""
    if not group_id:
        return []
    g = next((g for g in sent_groups(clp_id) if g["id"] == group_id), None)
    if not g:
        return []
    return client_thread({"id": clp_id}, g, _rows(clp_id), "client", {"user_id": None})["notes"]


def _all_users():
    import users
    return users.list_users()


def _step_word(step, issue_no, group_name=None):
    if step == "approved":
        return f"Approved as Issue {issue_no}" if issue_no else "Approved"
    if step == "review-sent":
        return f"Issue {issue_no} sent to {group_name or 'the client'}"
    if step == "review-accepted":
        return f"Issue {issue_no} accepted"
    if step == "review-returned":
        return f"Issue {issue_no} returned"
    return STEPS.get(step, step or "")


def counts():
    """{clp id: {open, overdue, next_due, notes, mine_open}} for the list's Tasks column (one read for every CLP);
    `mine_open` needs the caller, so it is filled by counts_for()."""
    out = {}
    today = _today()
    for r in _rows(kinds=("note", "task")):
        c = out.setdefault(r["clp_id"], {"open": 0, "overdue": 0, "next_due": None, "notes": 0, "done": 0, "_open": [],
                                         "client_open": 0, "client_overdue": 0, "_client_open": []})
        if _client(r):
            # PR 3d (Q8): a client thread's open tasks are counted apart (a planner's second line; never a team's)
            if r["kind"] == "task" and not r.get("done_at"):
                c["client_open"] += 1
                c["_client_open"].append(r)
                if r.get("due") and r["due"] < today:
                    c["client_overdue"] += 1
            continue
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
    appr = access.can_approve(acc)
    for c in out.values():
        c["mine_open"] = sum(1 for r in c.pop("_open") if _mine(r, acc))
        cl = c.pop("_client_open")
        if appr:
            c["client_mine_open"] = sum(1 for r in cl if _client_mine(r, "contractor", acc or {}))
        else:       # Q4: a team never counts the client's tasks
            c["client_open"] = c["client_overdue"] = c["client_mine_open"] = 0
    return out


def review_counts(group_id, user_id):
    """{clp id: open tasks in the group's thread for the group or for this reviewer} (the reviewer's list, Q8)."""
    out = {}
    for r in _rows(kinds=("task",)):
        if r.get("review_group") == group_id and not r.get("done_at") \
                and _client_mine(r, "client", {"user_id": user_id}):
            out[r["clp_id"]] = out.get(r["clp_id"], 0) + 1
    return out


def open_summary(clp_id):
    """What the approve card says about the tasks: how many open, how many overdue, the first overdue one's words (the
    contractor's thread), and how many are open in the client threads (PR 3d)."""
    today = _today()
    rows = [r for r in _rows(clp_id, ("task",)) if not r.get("done_at")]
    open_ = [r for r in rows if not _client(r)]
    over = sorted([r for r in open_ if r.get("due") and r["due"] < today], key=lambda r: r["due"])
    return {"open": len(open_), "overdue": len(over), "first_overdue": (over[0].get("words") if over else None),
            "client_open": sum(1 for r in rows if _client(r))}


# --------------------------------------------------------------------------- #
#  Writing                                                                     #
# --------------------------------------------------------------------------- #
def add_note(clp_id, words, acc, factors=None, show_to=None, group=None):
    """A note in the contractor's thread, or (`group`, PR 3d; `show_to` is the 3c name for it) in that group's client
    thread — planners and admins only, a group an issue of the CLP was sent to."""
    rec = clp_records._record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    group = group if group not in (None, "") else show_to
    words = _clean(words, WORDS_MAX)
    p = _words_problem(words)
    if p:
        return {"error": p, "status": 422}
    gid = None
    if group not in (None, ""):
        if not access.can_approve(acc):
            return {"error": "Only a planner or an admin writes to the client.", "status": 403}
        g = _group_for_write(rec["id"], group)
        if "error" in g:
            return g
        gid = g["id"]
    nid = _insert({"clp_id": rec["id"], "kind": "note", "words": words, "written_by": clp_records.who(acc),
                   "written_key": key_of(acc), "review_group": gid})
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
    group = body.get("group") or None
    from_note = None
    if body.get("from_note"):
        # PR 3c / 3d (Q6): Make a task from a reviewer's note (planners and admins): it lands in THAT client's thread
        if not access.can_approve(acc):
            return {"error": "A planner or an admin makes a task from the client's comment.", "status": 403}
        src = [r for r in _rows(rec["id"], ("note",)) if r["id"] == str(body["from_note"]) and _is_review_comment(r)]
        if not src:
            return {"error": "No such comment.", "status": 404}
        if group and str(group) != src[0].get("review_group"):
            return {"error": "That note is in another client's tab.", "status": 422}
        group, from_note = src[0].get("review_group"), src[0]["id"]
    if group:
        if not access.can_approve(acc):
            return {"error": "Only a planner or an admin writes to the client.", "status": 403}
        g = _group_for_write(rec["id"], group)
        if "error" in g:
            return g
        out = client_add_task(rec, g, dict(body, from_note=from_note), "contractor", acc, mail=mail)
        if "error" in out:
            return out
        return {"id": out["id"], "email": out["email"], "thread": thread(rec["id"], acc, factors)}
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


def client_add_task(rec, g, body, side, who, mail=True):
    """A task in client thread `g` written by `side` (the caller has checked who may write there). {id, email} or an error."""
    words = _clean(body.get("words"), WORDS_MAX)
    p = _words_problem(words, "the task")
    if p:
        return {"error": p, "status": 422}
    f = _client_for_problem(body.get("for"), g, side)
    if isinstance(f, str):
        return {"error": f, "status": 422}
    due = body.get("due") or None
    p = _due_problem(due)
    if p:
        return {"error": p, "status": 422}
    nid = _insert({"clp_id": rec["id"], "kind": "task", "words": words, "for_kind": f[0], "for_user": f[2], "due": due,
                   "written_by": _side_name(side, who), "written_key": _side_key(side, who), "review_group": g["id"],
                   "from_note": body.get("from_note") or None})
    return {"id": nid, "email": _client_mail(mail, f[0], f[2], who, rec, words, due, _side_name(side, who))}


def _client_mail(mail, kind, uid, who, rec, words, due, by):
    """Q9: one email when the task goes to one named person other than the writer; a reviewer's link opens CLPs for review."""
    if not mail or kind not in ("person", "reviewer") or str(uid) == str(who.get("user_id") or ""):
        return None
    return email_task(uid, rec, words, due, by, review=(kind == "reviewer"))


def client_change_task(rec, g, row, body, side, who, mail=True):
    """Tick (each side its own), or change the words / For / due (each side what it wrote). {email} or an error dict."""
    body = body or {}
    sets = {}
    if any(k in body for k in ("words", "for", "due")):
        if not _client_can_change(row, side, who):
            return {"error": ("Only the client changes what the client wrote." if side == "contractor"
                              else "Only its writer changes it."), "status": 403}
        if "words" in body:
            w = _clean(body.get("words"), WORDS_MAX)
            p = _words_problem(w, "the task")
            if p:
                return {"error": p, "status": 422}
            sets["words"] = w
        if "for" in body:
            f = _client_for_problem(body.get("for"), g, side)
            if isinstance(f, str):
                return {"error": f, "status": 422}
            sets.update({"for_kind": f[0], "for_team": None, "for_user": f[2]})
        if "due" in body:
            p = _due_problem(body.get("due") or None)
            if p:
                return {"error": p, "status": 422}
            sets["due"] = body.get("due") or None
    if "done" in body:
        probe = dict(row, **{k: v for k, v in sets.items() if k in ("for_kind", "for_user")})
        if not _client_can_tick(probe, side, who):
            return {"error": ("The client ticks a task given to the client." if side == "contractor"
                              else "The contractor ticks a task given to the contractor."), "status": 403}
        if body["done"]:
            if not row.get("done_at"):
                sets.update({"done_by": _side_name(side, who), "done_at": _now()})
        else:
            sets.update({"done_by": None, "done_at": None})
    if not sets:
        return {"email": None}
    sets["updated_at"] = _now()
    cols = list(sets)
    db.execute("UPDATE clp_notes SET {} WHERE tenant_id = ? AND clp_id = ? AND id = ?".format(", ".join(c + " = ?" for c in cols)),
               tuple(sets[c] for c in cols) + (db.current_tenant(), rec["id"], row["id"]))
    sent = None
    if "for_kind" in sets and (sets["for_kind"], sets["for_user"]) != (row.get("for_kind"), row.get("for_user")):
        sent = _client_mail(mail, sets["for_kind"], sets["for_user"], who, rec, sets.get("words") or row.get("words"),
                            sets.get("due", row.get("due")), _side_name(side, who))
    return {"email": sent}


def client_remove(rec, row, side, who):
    g = next((x for x in sent_groups(rec["id"]) if x["id"] == row["review_group"]),
             {"id": row["review_group"], "name": "", "stopped": True})
    if g["stopped"]:
        return {"error": "That group is stopped: nothing new can be written to it.", "status": 422}
    if not _client_can_change(row, side, who):
        return {"error": ("The client's words stay as written." if side == "contractor" else "Only its writer deletes it."),
                "status": 403}
    db.execute("DELETE FROM clp_notes WHERE tenant_id = ? AND clp_id = ? AND id = ?",
               (db.current_tenant(), rec["id"], row["id"]))
    return {"deleted": row["id"]}


def client_row(clp_id, item_id, group_id, kinds=("note", "task")):
    """A note or task of group `group_id`'s thread on this CLP, or None."""
    return next((r for r in _rows(clp_id, kinds) if r["id"] == str(item_id) and r.get("review_group") == group_id), None)


def change_task(clp_id, task_id, body, acc, factors=None, mail=True):
    """Tick done / back (anyone who can see the CLP); words, For and due (its writer, a planner or an admin)."""
    rec = clp_records._record(clp_id, acc, factors)
    if not rec:
        return {"error": "No such CLP.", "status": 404}
    rows = [r for r in _rows(rec["id"], ("task",)) if r["id"] == str(task_id)]
    if rows and _client(rows[0]) and not access.can_approve(acc):
        rows = []       # PR 3d (Q4): a client thread's task does not exist for a team
    if not rows:
        return {"error": "No such task.", "status": 404}
    row = rows[0]
    body = body or {}
    if _client(row):
        g = next((g for g in sent_groups(rec["id"]) if g["id"] == row["review_group"]),
                 {"id": row["review_group"], "name": "", "stopped": True})
        if g["stopped"]:
            return {"error": "That group is stopped: nothing new can be written to it.", "status": 422}
        out = client_change_task(rec, g, row, body, "contractor", acc, mail=mail)
        if "error" in out:
            return out
        return {"email": out["email"], "thread": thread(rec["id"], acc, factors)}
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
    if rows and _client(rows[0]) and not access.can_approve(acc):
        rows = []       # PR 3d (Q4): a client thread's note or task does not exist for a team
    if not rows:
        return {"error": "No such note or task.", "status": 404}
    if _client(rows[0]):
        out = client_remove(rec, rows[0], "contractor", acc)
        if "error" in out:
            return out
        return {"deleted": rows[0]["id"], "thread": thread(rec["id"], acc, factors)}
    if not _can_change(rows[0], acc):
        return {"error": "Its writer, a planner or an admin deletes it.", "status": 403}
    db.execute("DELETE FROM clp_notes WHERE tenant_id = ? AND clp_id = ? AND id = ?",
               (db.current_tenant(), rec["id"], rows[0]["id"]))
    return {"deleted": rows[0]["id"], "thread": thread(rec["id"], acc, factors)}


def add_step(clp_id, step, by, at, words=None, issue_no=None):
    """The chain writes its steps here as they happen (clp_records.send / ask_changes / approve)."""
    _insert({"clp_id": clp_id, "kind": "step", "step": step, "issue_no": issue_no, "words": (words or None),
             "written_by": by, "written_key": "step", "written_at": at})


def add_review_step(clp_id, step, by, at, group_id, issue_no):
    """PR 3c: a send / accept / return line, read by the contractor and by the group (review_thread)."""
    _insert({"clp_id": clp_id, "kind": "step", "step": step, "issue_no": issue_no, "words": None, "written_by": by,
             "written_key": "step", "written_at": at, "review_group": group_id})


def add_review_note(clp_id, words, rev, at=None, decision=None):
    """PR 3c: a reviewer's comment (clp_reviews.comment / decide checked the reviewer and the CLP). PR 3d: the note of a
    decision carries its step word (review-accepted / review-returned), so its writer cannot delete it."""
    row = {"clp_id": clp_id, "kind": "note", "words": words, "written_by": rev["name"],
           "written_key": f"r:{rev['user_id']}", "review_group": rev["group_id"]}
    if decision:
        row["step"] = "review-" + decision
    if at:
        row["written_at"] = at
    return _insert(row)


def drop_all(clp_id):
    """A CLP made with + New CLP is deleted: its notes, tasks, steps and kept lines go with it (Q12)."""
    db.execute("DELETE FROM clp_notes WHERE tenant_id = ? AND clp_id = ?", (db.current_tenant(), clp_id))


# --------------------------------------------------------------------------- #
#  The one email (Q10)                                                         #
# --------------------------------------------------------------------------- #
def task_message(user, rec, words, due, by, settings, demo_notice=None, review=False):
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
            + (f"Open it: CLPs for review, {users.app_url()}/#review\n\n" if review     # PR 3d: a reviewer's own page
               else f"Open it: Plan → CLP documents, {users.app_url()}/#clp\n\n"))
    if demo_notice:
        body += f"DEMO · {demo_notice}\n\n"
    msg.set_content(body + "Wayscope\n")
    return msg


def email_task(user_id, rec, words, due, by, review=False):
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
        demo_request.send(task_message(u, rec, words, due, by, settings, notice, review=review), settings)
        return "sent"
    except Exception as e:  # noqa: BLE001
        print(f"clp_notes: task email FAILED {e.__class__.__name__}: {str(e)[:200]}")
        return "failed"

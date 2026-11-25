"""
working.py — the "Working" list (23 Nov 2026, claude/working-list).

John's yes to the mockup notes/working-list-mockup-1121 (Option A, Q1 to Q8 as recommended): one place that says what long
job is running, lets a person leave the page, and stops two heavy jobs running at once. This module is the server's half:

  * the RECORD of what is running for the tenant (table working_jobs: what, how far, since when, who, its state);
  * the RULE, one long job at a time for everyone signed in to the tenant, and its one refusal sentence
    ("Busy-hour times are running. Route all can start when they finish.");
  * the LIST the page's chip reads (what is running, what stopped part-way, what ended in the last 30 minutes and has
    not been closed).

Nine kinds (KINDS). Who does the work does not change (Option A):

  page    Route all, Busy-hour times, a zone's re-route, Route again: the PAGE sends the batches as before. The page
          (or the zone write) starts a row; each batch endpoint moves it on (progress); the page ends it. A row with no
          batch for GAP reads "stopped": the tab was closed, the laptop slept, the service restarted.
  held    Make primary, the Organisation file's re-import: one request of this process (held()). A held row this
          process does not hold any more (it restarted mid-request) reads "stopped" at once.
  server  the community places fetch, the collision history fetch, the Look-ahead's road closures check: each already
          keeps its own state (community.run_state, collisions.run_state, restrictions.refresh_state). It is READ here,
          never copied; only "someone closed this finished line" is stored (a row with closed = 1).

The table is not package data (db.init_working_db) and is in db.NO_DATA_TABLES: a batch's progress write moves no data
version, so no kept read is emptied. Per process for the lock and the held set: the service runs one worker.

Every sentence a person reads about a job is made HERE (line, refusal): the page prints them and makes none.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import db
import fetch_guard

#: one lock for every "check, then mark as running" (the two fetches take the same one)
LOCK = fetch_guard.LOCK
#: a page-sent job with no batch for this long reads "stopped" (a batch stops itself after about 20 s and the page's
#: three tries after no answer wait 30, 60 and 90 s; a closed tab says so itself at once, see /api/working/<id>/end)
GAP = timedelta(minutes=5)
#: a finished line, and a server-run job that failed, stays in the list this long unless closed first (Q5)
KEEP = timedelta(minutes=30)
#: rows older than this are removed when a job starts
PRUNE = timedelta(days=7)
#: the refusal's HTTP status: used for nothing else, so the page can print the sentence alone
BUSY_STATUS = 423

# name: the job as the refusal names it; plural: "are running / they finish"; page: where it is pressed;
# may: who may start it (admin = an admin LOGIN, planner = a planner or an admin, staff = any staff sign-in);
# kept: what a stopped line says is kept
# 25 Nov 2026 (the Routes page rethink, Q9: "Make primary" is gone from what a person reads; the button is "Use Alt 1
# as the main route"): the "Working" list's name for that job, John's word (25 Nov 2026, about 09:40 UTC: "Yes, that
# name"). ONE constant (the line reads "R050: main route change stopped"). The key stays make_primary.
MAIN_ROUTE_JOB = "Main route change"

KINDS = {
    "route_all":    {"name": "Route all", "plural": False, "by": "page", "page": "routes", "may": "admin",
                     "kept": "the routes worked out are kept"},
    "hour_times":   {"name": "Busy-hour times", "plural": True, "by": "page", "page": "routes", "may": "admin",
                     "kept": "the times worked out are kept"},
    "zone_reroute": {"name": "Zone re-route", "plural": False, "by": "page", "page": "zones", "may": "admin",
                     "kept": "the routes worked out are kept"},
    "route_again":  {"name": "Route again", "plural": False, "by": "page", "page": "routes", "may": "admin",
                     "kept": "the routes worked out are kept"},
    "make_primary": {"name": MAIN_ROUTE_JOB, "plural": False, "by": "held", "page": "routes", "may": "admin", "kept": ""},
    "import":       {"name": "Replace from a file", "plural": False, "by": "held", "page": "config", "may": "admin",
                     "kept": ""},
    "community":    {"name": "The community places fetch", "plural": False, "by": "server", "page": "config",
                     "may": "planner", "kept": ""},
    "collisions":   {"name": "The collision history fetch", "plural": False, "by": "server", "page": "config",
                     "may": "planner", "kept": ""},
    "closures":     {"name": "The road closures check", "plural": False, "by": "server", "page": "lookahead",
                     "may": "staff", "kept": ""},
}
PAGE_KINDS = tuple(k for k, v in KINDS.items() if v["by"] == "page")
ORDER = {"running": 0, "stopped": 1, "done": 2}

#: ids of the held jobs THIS process is running (one worker: test_areas pins no --workers)
_HELD = set()


class Busy(Exception):
    """Another long job is running. `sentence` is what the person reads."""

    def __init__(self, sentence):
        super().__init__(sentence)
        self.sentence = sentence


# --------------------------------------------------------------------------- #
#  Time                                                                        #
# --------------------------------------------------------------------------- #
def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _at(text):
    """An ISO time as the other modules write it ("…Z" or "+00:00") -> aware datetime, or None."""
    if not text:
        return None
    try:
        d = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _within(text, span, now):
    d = _at(text)
    return bool(d and now - d <= span)


# --------------------------------------------------------------------------- #
#  The words                                                                   #
# --------------------------------------------------------------------------- #
def _closures_label():
    """"Road closures" / "Road restrictions": the country's own check, without its provider's name."""
    try:
        import restrictions
        cur = restrictions.current() or {}
        return str(cur.get("ui_label") or "Road restrictions").split(" (")[0].strip() or "Road restrictions"
    except Exception:
        return "Road restrictions"


#: 24 Nov 2026: writes that are not long jobs (no row, no line in the list) but must not run under one: each is
#: refused in the one sentence while a job runs, under this name
ALSO = {"clear_routes": "Clear all routes"}


def name_of(kind):
    """The job as the refusal names it."""
    if kind == "closures":
        return "The " + _closures_label().lower() + " check"
    if kind in ALSO:
        return ALSO[kind]
    return KINDS[kind]["name"]


def sentence(running_kind, wanted_kind):
    """The one refusal: "<A> is running. <B> can start when it finishes." (are / they finish for a plural A)."""
    plural = KINDS[running_kind]["plural"]
    return (f"{name_of(running_kind)} {'are' if plural else 'is'} running. "
            f"{name_of(wanted_kind)} can start when {'they finish' if plural else 'it finishes'}.")


def _n_of(done, total, unit, unit_one=None):
    u = unit_one if (unit_one and total == 1) else unit
    if total is None:
        return f"{done} {u}".strip()
    return f"{done} of {total} {u}".strip()


def line(kind, state, done=0, total=None, subject=None, detail=None):
    """What the list's row and the page's own line both say (R6: the same words). One shape: the job, then how far."""
    done = int(done or 0)
    d = detail or {}
    if kind in ("route_all", "zone_reroute"):
        nm = KINDS[kind]["name"]
        if state == "stopped":
            return f"{nm} stopped at {_n_of(done, total, 'legs', 'leg')}"
        if state == "done":
            n = int(total) if total is not None else done
            return f"{nm}: {n} {'leg' if n == 1 else 'legs'}"
        return f"{nm}: {_n_of(done, total, 'legs', 'leg')}"
    if kind == "hour_times":
        if state == "stopped":
            return f"Busy-hour times stopped at {_n_of(done, total, '')}"
        if state == "done":
            return f"Busy-hour times: {total if total is not None else done} worked out"
        return f"Busy-hour times: {_n_of(done, total, 'worked out')}"
    if kind == "route_again":
        rid = subject or "Route"
        if state == "done":
            return f"{rid}: routed again"
        if state == "stopped":
            return f"{rid}: routing again stopped at {_n_of(done, total, 'lorry types', 'lorry type')}"
        cur = done + 1 if total is None else min(done + 1, max(int(total), 1))
        return f"{rid}: routing again, {_n_of(cur, total, 'lorry types', 'lorry type')}"
    if kind == "make_primary":
        rid, lab = subject or "Route", d.get("label") or "The alternative"
        if state == "done":
            return f"{rid}: {lab} made the main route"
        if state == "stopped":
            return f"{rid}: {MAIN_ROUTE_JOB[0].lower() + MAIN_ROUTE_JOB[1:]} stopped"
        return f"{rid}: making {lab} the main route"
    if kind == "import":
        return "Organisation file: " + {"done": "replaced", "stopped": "replace stopped"}.get(state, "replacing")
    if kind == "community":
        return "Community places: " + {"done": "fetched", "stopped": "fetch stopped"}.get(state, "fetching")
    if kind == "collisions":
        return "Collision history: " + {"done": "fetched", "stopped": "fetch stopped"}.get(state, "fetching")
    if kind == "closures":
        return _closures_label() + ": " + {"done": "checked", "stopped": "check stopped"}.get(state, "checking")
    return KINDS.get(kind, {}).get("name", kind)


# --------------------------------------------------------------------------- #
#  The record                                                                  #
# --------------------------------------------------------------------------- #
def _read(sql, params):
    """A read of the record. The table is made at start-up (main's lifespan: db.init_working_db); a database that
    never went through it (a harness's scratch file) gets it on the first read, so no job's endpoint fails for want of
    the list's table."""
    try:
        return db.query(sql, params)
    except Exception as e:
        if "working_jobs" not in str(e):
            raise
        db.init_working_db()
        return db.query(sql, params)


def _rows():
    return _read("SELECT * FROM working_jobs WHERE tenant_id = ? ORDER BY started_at", (db.current_tenant(),))


def _get(job_id):
    if not job_id:
        return None
    r = _read("SELECT * FROM working_jobs WHERE tenant_id = ? AND id = ?", (db.current_tenant(), str(job_id)))
    return r[0] if r else None


def _detail(row):
    try:
        return json.loads(row.get("detail") or "{}") or {}
    except Exception:
        return {}


def _reads(row, now):
    """A stored row's state as it READS now. A 'running' row is only running while its sender is alive: this process
    for a held job, a batch within GAP for a page-sent one."""
    st = row.get("state")
    if st != "running":
        return st
    if int(row.get("held") or 0):
        return "running" if row["id"] in _HELD else "stopped"
    if _within(row.get("beat_at") or row.get("started_at"), GAP, now):
        return "running"
    total = row.get("total")
    return "done" if (total is not None and int(row.get("done") or 0) >= int(total)) else "stopped"


def _server_states(now):
    """The three server-run jobs, each from its own state (never copied): [{kind, state, id, started_at, at, by}].
    `at` is when it finished or last showed life; `id` names that run, so a close sticks to it alone."""
    out = []
    try:
        import community
        import collisions
        mods = (("community", community), ("collisions", collisions))
    except Exception:
        mods = ()
    for kind, mod in mods:
        try:
            st = mod.run_state()
        except Exception:
            continue
        if st["state"] == "running":
            out.append({"kind": kind, "state": "running", "id": f"{kind}@{st['started_at']}",
                        "started_at": st["started_at"], "at": st["started_at"], "by": st.get("by")})
        elif st["state"] == "done" and _within(st.get("fetched_at"), KEEP, now):
            out.append({"kind": kind, "state": "done", "id": f"{kind}@{st['fetched_at']}",
                        "started_at": st["started_at"], "at": st["fetched_at"], "by": st.get("by")})
        elif st["state"] == "failed" and _within(st.get("last"), KEEP, now):
            out.append({"kind": kind, "state": "stopped", "id": f"{kind}@{st['last']}",
                        "started_at": st["started_at"], "at": st["last"], "by": st.get("by")})
    try:
        import restrictions
        r = restrictions.refresh_state()
    except Exception:
        r = {}
    if r.get("running"):
        out.append({"kind": "closures", "state": "running", "id": f"closures@{r.get('started_at')}",
                    "started_at": r.get("started_at"), "at": r.get("started_at"), "by": None})
    elif r.get("finished_at") and _within(r["finished_at"], KEEP, now):
        ok = r.get("status") in ("ok", "no_provider")
        out.append({"kind": "closures", "state": "done" if ok else "stopped", "id": f"closures@{r['finished_at']}",
                    "started_at": r.get("started_at"), "at": r["finished_at"], "by": None})
    return out


def running(now=None):
    """The one job running now for this tenant, or None: {kind, id, row?}. Reads the table and the three server-run
    states. Takes no lock (a start that must check and mark holds LOCK around it)."""
    now = now or _now()
    for row in _rows():
        if _reads(row, now) == "running":
            return {"kind": row["kind"], "id": row["id"], "row": row}
    for s in _server_states(now):
        if s["state"] == "running":
            return {"kind": s["kind"], "id": s["id"], "row": None}
    return None


def refusal(wanted, now=None):
    """The sentence to refuse `wanted` with while a job is running (the same kind included), else None."""
    cur = running(now)
    return sentence(cur["kind"], wanted) if cur else None


def check(wanted):
    """Raise Busy while a job is running."""
    s = refusal(wanted)
    if s:
        raise Busy(s)


def _insert(kind, by, total, subject, detail, held, done=0, now=None):
    now = now or _now()
    jid = uuid.uuid4().hex[:16]
    db.execute("INSERT INTO working_jobs (tenant_id, id, kind, subject, state, done, total, detail, by_whom, held, "
               "started_at, beat_at, ended_at, closed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0)",
               (db.current_tenant(), jid, kind, subject, "running", int(done or 0),
                None if total is None else int(total), json.dumps(detail or {}, ensure_ascii=False), by,
                1 if held else 0, _iso(now), _iso(now)))
    return jid


def _tidy(kind, subject, now):
    """A new run of a job replaces its own older lines that are not running (a stopped one it carries on, a done one);
    rows past PRUNE go too."""
    tenant = db.current_tenant()
    for row in _rows():
        old = not _within(row.get("started_at"), PRUNE, now)
        same = row["kind"] == kind and (row.get("subject") or "") == (subject or "")
        if (old or same) and _reads(row, now) != "running":
            db.execute("DELETE FROM working_jobs WHERE tenant_id = ? AND id = ?", (tenant, row["id"]))


def start(kind, by=None, total=None, subject=None, detail=None, carry=None, held=False):
    """
    Start a job's row, or raise Busy with the one sentence while any job is running for this tenant. `carry` is the id
    of the stopped row this run carries on: its count is kept, so the line goes on from "62 of 188", not from 0.
    Returns the row as the page reads it (view).
    """
    if kind not in KINDS or KINDS[kind]["by"] == "server":
        raise ValueError("not a job a row is kept for")
    with LOCK:
        now = _now()
        s = refusal(kind, now)
        if s:
            raise Busy(s)
        done0 = 0
        old = _get(carry) if carry else None
        if old and old["kind"] == kind and (old.get("subject") or "") == (subject or ""):
            done0 = int(old.get("done") or 0)
            if total is not None:
                total = int(total) + done0
            elif old.get("total") is not None:
                total = int(old["total"])
        _tidy(kind, subject, now)
        jid = _insert(kind, by, total, subject, detail, held, done=done0, now=now)
        if held:
            _HELD.add(jid)
    return view(_get(jid))


def batch(kinds, job_id=None, wanted=None):
    """
    A batch endpoint calls this before it works. Returns the stored row this batch belongs to (None when no row is
    kept: a call no page started), or raises Busy when ANOTHER job is running. A batch of the job already running is
    never refused: the running job being one of `kinds` is enough (the same work, whoever sent it).
    """
    now = _now()
    cur = running(now)
    if cur is None:
        row = _get(job_id)
        if not row or row["kind"] not in kinds or row.get("state") not in ("running", "stopped") or int(row.get("closed") or 0):
            return None
        # its own row read "stopped" (no batch for GAP, or its tab said it was going) and nothing else has started
        # since: a batch arriving now shows its sender is alive after all, so the row is running again
        db.execute("UPDATE working_jobs SET state = ?, beat_at = ?, ended_at = NULL WHERE tenant_id = ? AND id = ?",
                   ("running", _iso(now), db.current_tenant(), row["id"]))
        return _get(row["id"])
    if cur["kind"] in kinds and cur["row"] is not None:
        return cur["row"]
    raise Busy(sentence(cur["kind"], wanted or kinds[0]))


def progress(job_id, attempted=0, remaining=None):
    """After a batch: `attempted` more are done and the row has shown life. A row with no total yet takes it from the
    batch's own `remaining` (Busy-hour times: the count is only known once the run has begun). Returns the view."""
    row = _get(job_id)
    if not row:
        return None
    done = int(row.get("done") or 0) + int(attempted or 0)
    total = row.get("total")
    if total is None and remaining is not None:
        total = done + int(remaining)
    if total is not None:
        done = min(done, int(total))
    # the state is not touched here: a batch that finishes after its tab has gone still counts what it did, and the
    # row stays "stopped" (only the START of a batch revives a row, see batch())
    db.execute("UPDATE working_jobs SET done = ?, total = ?, beat_at = ? WHERE tenant_id = ? AND id = ?",
               (done, total, _iso(_now()), db.current_tenant(), row["id"]))
    return view(_get(row["id"]))


def end(job_id, state="done"):
    """The sender says its job ended ("done") or stopped part-way ("stopped"). A row already ended is left as it is."""
    row = _get(job_id)
    if not row:
        return None
    state = "done" if state == "done" else "stopped"
    if row.get("state") == "running":
        db.execute("UPDATE working_jobs SET state = ?, ended_at = ? WHERE tenant_id = ? AND id = ?",
                   (state, _iso(_now()), db.current_tenant(), row["id"]))
    _HELD.discard(row["id"])
    return view(_get(row["id"]))


def drop(job_id):
    """Remove a row whose job never happened (a held request the endpoint refused for its own reasons)."""
    if job_id:
        db.execute("DELETE FROM working_jobs WHERE tenant_id = ? AND id = ?", (db.current_tenant(), str(job_id)))
        _HELD.discard(str(job_id))


class held:
    """
    One request of this process as a job (Make primary, the re-import):

        with working.held("make_primary", by=..., subject="R050", detail={"label": "Alt 1"}) as job:
            ...the work...
            job.done()

    Raises Busy before the work when another job is running. Without done() (the work refused or failed and said so
    itself) the row is removed: nothing ran. A process that dies inside leaves the row, which then reads "stopped".
    """

    def __init__(self, kind, by=None, subject=None, detail=None):
        self.kind, self.by, self.subject, self.detail = kind, by, subject, detail
        self.id, self._done = None, False

    def __enter__(self):
        self.id = start(self.kind, by=self.by, subject=self.subject, detail=self.detail, held=True)["id"]
        return self

    def done(self):
        self._done = True

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._done and exc_type is None:
                end(self.id, "done")
            else:
                drop(self.id)
        finally:
            _HELD.discard(self.id)
        return False


def close(row_id, acc=None):
    """Close a finished or stopped line (it leaves everyone's list). A running job cannot be closed. A stopped line is
    closed only by someone who may start that job (it takes "Carry on" away). Returns True when it is closed now."""
    row_id = str(row_id or "")
    now = _now()
    row = _get(row_id)
    if row:
        st = _reads(row, now)
        if st == "running" or (st == "stopped" and not may_start(row["kind"], acc)):
            return False
        db.execute("UPDATE working_jobs SET closed = 1, state = ?, ended_at = COALESCE(ended_at, ?) "
                   "WHERE tenant_id = ? AND id = ?", (st, _iso(now), db.current_tenant(), row_id))
        return True
    for s in _server_states(now):
        if s["id"] == row_id and s["state"] != "running":
            if s["state"] == "stopped" and not may_start(s["kind"], acc):
                return False
            db.execute("INSERT INTO working_jobs (tenant_id, id, kind, subject, state, done, total, detail, by_whom, "
                       "held, started_at, beat_at, ended_at, closed) VALUES (?, ?, ?, NULL, ?, 0, NULL, NULL, NULL, 0, ?, "
                       "NULL, ?, 1)", (db.current_tenant(), row_id, s["kind"], s["state"], _iso(now), _iso(now)))
            return True
    return False


# --------------------------------------------------------------------------- #
#  The list                                                                    #
# --------------------------------------------------------------------------- #
def may_start(kind, acc):
    """May this caller start that job? (So: may they carry a stopped one on.) The same test the job's endpoint makes."""
    if not acc:
        return False
    need = KINDS[kind]["may"]
    if need == "admin":
        return acc.get("via") == "login" and acc.get("role") == "admin"
    if need == "planner":
        return acc.get("role") in ("planner", "admin")
    return True


def view(row, now=None, acc=None):
    """A stored row as the page reads it."""
    if not row:
        return None
    now = now or _now()
    st = _reads(row, now)
    kind = row["kind"]
    det = _detail(row)
    ended = row.get("ended_at") or (row.get("beat_at") if st != "running" else None)
    by = KINDS[kind]["by"]
    # "Carry on" runs the same action again: a job the page sends has what that needs (its lorry types, its legs). A
    # held request cut short by a restart has not (Make primary again could swap the lines back; the re-import's file
    # is gone with the request): its line can only be closed, and leaves by itself after KEEP.
    carry = st == "stopped" and by == "page" and may_start(kind, acc)
    return {"id": row["id"], "kind": kind, "state": st, "subject": row.get("subject"),
            "line": line(kind, st, row.get("done"), row.get("total"), row.get("subject"), det),
            "done": int(row.get("done") or 0), "total": row.get("total"),
            "started_at": row.get("started_at"), "ended_at": ended, "by": row.get("by_whom"),
            "page": KINDS[kind]["page"], "kept": KINDS[kind]["kept"] if st == "stopped" else "",
            "sent_by": by, "can_carry": bool(carry),
            "can_close": st == "done" or (st == "stopped" and by == "held" and may_start(kind, acc)),
            "args": det.get("args") or {}}


def listing(acc=None):
    """
    What the chip and its list show: every job running, every one that stopped part-way, and every one that ended in
    the last KEEP and has not been closed; and `busy`, the refusal for each kind while something runs (the page shows
    it where a second job would be pressed, and makes no sentence itself).
    """
    now = _now()
    rows = _rows()
    closed = {r["id"] for r in rows if int(r.get("closed") or 0)}
    jobs = []
    for r in rows:
        if r["id"] in closed:
            continue
        v = view(r, now, acc)
        gone_by_itself = v["state"] == "done" or (v["state"] == "stopped" and v["sent_by"] == "held")
        if gone_by_itself and not _within(v["ended_at"] or r.get("started_at"), KEEP, now):
            continue
        if not _within(r.get("started_at"), PRUNE, now):
            continue
        jobs.append(v)
    for s in _server_states(now):
        if s["id"] in closed:
            continue
        kind, st = s["kind"], s["state"]
        jobs.append({"id": s["id"], "kind": kind, "state": st, "subject": None, "line": line(kind, st),
                     "done": 0, "total": None, "started_at": s["started_at"],
                     "ended_at": None if st == "running" else s["at"], "by": s.get("by"),
                     "page": KINDS[kind]["page"], "kept": "", "sent_by": "server",
                     "can_carry": st == "stopped" and may_start(kind, acc), "can_close": st == "done", "args": {}})
    jobs.sort(key=lambda j: (ORDER.get(j["state"], 9), j.get("started_at") or ""))
    cur = next((j for j in jobs if j["state"] == "running"), None)
    busy = {k: sentence(cur["kind"], k) for k in KINDS} if cur else {}
    return {"jobs": jobs, "busy": busy, "running": cur["kind"] if cur else None}

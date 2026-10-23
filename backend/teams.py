"""
23 Oct 2026 — the Teams tab (Users → Teams): an admin adds a team, renames it, stops or resumes it.

WHY
---
Until now a team row (`ipts`) was written only by the organisation's package, and a package imports into an EMPTY
organisation. So an organisation that started with three teams could never get a fourth, and nobody could rename
one. John (23 Oct 2026): the limit stays SIX teams (`access.IPT_IDS`); admins only add a team.

THE RULES
---------
* A team is one of six internal slots with the organisation's NAME. A person reads the name only (taxonomy.team_text).
* Add: the lowest slot that has NEVER been used — no team row, no forecast line, no login carries it. A stopped
  team keeps its row, so its slot is never handed to a new contractor (who would otherwise see its old lines).
* A name: 1–60 characters, not another team's name (any case, stopped teams included), and not a slot id.
* Stop using: the team leaves every picker (`active` false); its lines, figures and history stay under its name.
  Refused while a login of the team can still sign in. A stopped team still counts towards the six.
* No delete: nothing here removes a row.

Every write here is a /api/admin/* write, so the middleware's audit row records it (who, when, the body).
"""
import re

import db

LABEL_MAX = 60
_SLOT = re.compile(r"IPT([1-9]\d?)")


def limit():
    """The most teams an organisation can have (John, 23 Oct 2026: six)."""
    import access
    return len(access.IPT_IDS)


def _tenant():
    return db.current_tenant()


def slot_number(team_id):
    m = _SLOT.fullmatch(str(team_id or "").strip().upper())
    return int(m.group(1)) if m else None


def sort_key(team_id):
    """Teams in number order (slot 2 before slot 10), anything else after them by its text."""
    n = slot_number(team_id)
    return (0, n, "") if n is not None else (1, 0, str(team_id or ""))


def _rows():
    rows = db.query("SELECT id, label, active FROM ipts WHERE tenant_id = ?", (_tenant(),))
    for r in rows:
        r["active"] = bool(r["active"])
    return sorted(rows, key=lambda r: sort_key(r["id"]))


def _usable_logins():
    """{slot: how many logins of that team can sign in now} (not disabled, not ended)."""
    import users
    out = {}
    for u in db.query("SELECT * FROM users WHERE tenant_id = ? AND role = 'team'", (_tenant(),)):
        if users.usable(u):
            k = (u.get("team") or "").upper()
            out[k] = out.get(k, 0) + 1
    return out


def _line_counts():
    import access
    out = {}
    for r in db.query("SELECT ipt, COUNT(*) AS n FROM forecasts WHERE tenant_id = ? AND ipt IS NOT NULL GROUP BY ipt",
                      (_tenant(),)):
        k = access.canonical_ipt(r["ipt"]) or r["ipt"]
        out[k] = out.get(k, 0) + int(r["n"])
    return out


def _used_numbers():
    """Every slot number anything carries: a team row, a forecast line, a login."""
    import access
    used = {slot_number(r["id"]) for r in db.query("SELECT id FROM ipts WHERE tenant_id = ?", (_tenant(),))}
    for r in db.query("SELECT DISTINCT ipt FROM forecasts WHERE tenant_id = ? AND ipt IS NOT NULL", (_tenant(),)):
        used.add(slot_number(access.canonical_ipt(r["ipt"])))
    for r in db.query("SELECT DISTINCT team FROM users WHERE tenant_id = ? AND team IS NOT NULL", (_tenant(),)):
        used.add(slot_number(r["team"]))
    used.discard(None)
    return used


def next_slot():
    """The slot a new team gets, or None when every one of the six has been used."""
    used = _used_numbers()
    for n in range(1, limit() + 1):
        if n not in used:
            return f"IPT{n}"
    return None


def listing():
    """What the Teams tab shows: every team by NAME (the id is a value for the page's own buttons, never shown)."""
    import taxonomy
    logins, lines = _usable_logins(), _line_counts()
    rows = _rows()
    return {
        "teams": [{"id": r["id"], "label": taxonomy.team_name(r["id"]), "named": bool((r.get("label") or "").strip()),
                   "active": r["active"], "logins": logins.get(r["id"], 0), "lines": lines.get(r["id"], 0)}
                  for r in rows],
        "used": len(rows), "max": limit(), "can_add": next_slot() is not None,
    }


def _name_problem(label, own_id=None):
    import access
    label = (label or "").strip()
    if not label or len(label) > LABEL_MAX:
        return label, f"Type the team's name (at most {LABEL_MAX} characters)."
    if access.canonical_ipt(label):
        return label, "Give the team a name a person will recognise."
    for r in _rows():
        if r["id"] != own_id and (r.get("label") or "").strip().lower() == label.lower():
            return label, "There is already a team with that name."
    return label, None


def _get(team_id):
    rows = db.query("SELECT id, label, active FROM ipts WHERE tenant_id = ? AND id = ?", (_tenant(), team_id))
    return rows[0] if rows else None


def add(label):
    """(team, error). The new team is in use at once."""
    label, err = _name_problem(label)
    if err:
        return None, err
    slot = next_slot()
    if not slot:
        return None, f"All {limit()} team places are used."
    try:
        db.execute("INSERT INTO ipts (tenant_id, id, label, manager, active, merged_into) VALUES (?, ?, ?, ?, ?, ?)",
                   (_tenant(), slot, label, None, True, None))
    except Exception as e:  # noqa: BLE001 — two admins at the same moment: the primary key refuses the second
        print(f"teams: add refused {e.__class__.__name__}: {str(e)[:200]}")
        return None, "Someone added a team at the same moment. Try again."
    return _get(slot), None


def rename(team_id, label):
    if not _get(team_id):
        return None, "No such team."
    label, err = _name_problem(label, own_id=team_id)
    if err:
        return None, err
    db.execute("UPDATE ipts SET label = ? WHERE tenant_id = ? AND id = ?", (label, _tenant(), team_id))
    return _get(team_id), None


def set_active(team_id, active):
    if not _get(team_id):
        return None, "No such team."
    if not active:
        n = _usable_logins().get(team_id, 0)
        if n:
            return None, f"Move or disable its {n} login{'' if n == 1 else 's'} first."
    db.execute("UPDATE ipts SET active = ? WHERE tenant_id = ? AND id = ?", (bool(active), _tenant(), team_id))
    return _get(team_id), None

"""
Carbon target, 11 Oct 2026 (before the freeze) — the programme's agreed carbon target, one per tenant.

WHAT IT STORES
--------------
One tenanted row in the existing `config` table, key 'carbon_target' (beside 'factors' and
'costing'; no new table, so no new tenant registration, and it travels in the tenant package
like every config row):
    {"mode":                 "pct" (% below the approved plan) or "cap" (a fixed tCO2e cap),
     "pct_below":            the agreed decisions' cut on the approved plan, in % (1 dp, above 0, below 100),
     "cap_t":                the approved plan WITH the decisions, in tCO2e (3 dp),
     "set_at_approved_t":    the approved plan when the target was set,
     "set_at_alternative_t": the plan with the decisions when it was set,
     "levers":               the decisions, as the Carbon page sends them to /api/carbon/scenario,
     "lever_words":          the same decisions in words (carbon._lever_words),
     "ui_state":             the Carbon page's own state, opaque here, at most 20 000 characters as JSON}
updated_by / updated_at sit in the row's own columns, as for the costing settings.

Every figure is ALL-IN: making the material, transport to site and back, and waste disposal (the
Carbon page's headline). It is never the transport-only figure the Dashboard's transport card and
the map show; a page that prints both says which is which.

WHO MAY WRITE
-------------
A planner or admin code (main.py: _require_approver; a team code gets 403, no code 401). Any
signed-in code may read it, and sees progress on the lines it can see. Access is a shared code
per role: there is no per-person identity until G3, so `updated_by` is the name the person typed
at sign-in, sent by the browser and not checked.

HOW IT IS SET
-------------
The browser never sends a figure. set_from_levers() runs carbon.scenario over the APPROVED plan
with the sent decisions as the one alternative and stores what that gives. A target held as a %
follows the approved plan as lines are approved; a cap stays put. set_mode() switches between the
two and keeps every number. status() measures progress: the approved plan as forecast, the same
plan with the stored decisions (re-run every read, because the decisions are not recorded on the
forecast lines), and what the lines waiting for approval would add.

carbon.py does every carbon sum and stays write-free; this module holds the one row.
"""
import datetime
import json
import time

import carbon
import db

KEY = "carbon_target"
MODES = ("pct", "cap")
MODE_WORDS = {"pct": "% below the approved plan", "cap": "Fixed tCO2e cap"}
UI_STATE_MAX = 20000          # characters of JSON
LEVERS_MAX = 20000            # characters of JSON
NAME_MAX = 120

_CACHE = {"row": None, "loaded": False, "at": 0.0, "tenant": None}
CACHE_TTL_S = 5.0


class TargetError(ValueError):
    """A request the rules refuse, in one plain sentence (main.py turns it into a 400)."""


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _num(v):
    try:
        f = float(v) if v is not None and v != "" and not isinstance(v, bool) else None
    except (TypeError, ValueError):
        return None
    return f if f is not None and f == f and f not in (float("inf"), float("-inf")) else None


def _r3(v):
    return None if v is None else round(float(v), 3) + 0.0


def _size(v):
    return len(json.dumps(v, ensure_ascii=False))


def _grp(n):
    """20000 -> '20 000' (the page's number style: a space between thousands)."""
    return f"{int(n):,}".replace(",", " ")


# --------------------------------------------------------------------------- #
#  The row                                                                     #
# --------------------------------------------------------------------------- #
def _normalise(doc):
    """A stored document with every key present, or None when the row cannot be read as a target."""
    if not isinstance(doc, dict) or doc.get("mode") not in MODES:
        return None
    pct, cap = _num(doc.get("pct_below")), _num(doc.get("cap_t"))
    if pct is None or cap is None or not (0.0 < pct < 100.0) or cap < 0:
        return None
    return {
        "mode": doc["mode"],
        "pct_below": round(pct, 1),
        "cap_t": _r3(cap),
        "set_at_approved_t": _r3(_num(doc.get("set_at_approved_t"))),
        "set_at_alternative_t": _r3(_num(doc.get("set_at_alternative_t"))),
        "levers": doc.get("levers") if isinstance(doc.get("levers"), list) else [],
        "lever_words": [str(w) for w in (doc.get("lever_words") or []) if w is not None],
        "ui_state": doc.get("ui_state") if isinstance(doc.get("ui_state"), dict) else {},
    }


def invalidate():
    _CACHE["row"], _CACHE["loaded"], _CACHE["at"], _CACHE["tenant"] = None, False, 0.0, None


def get_row():
    """{doc, updated_by, updated_at} for the current tenant, or None (no target, or an unreadable row)."""
    try:
        rows = db.query("SELECT value, updated_by, updated_at FROM config "
                        "WHERE tenant_id = ? AND key = ?", (db.current_tenant(), KEY))
    except Exception:
        return None
    if not rows:
        return None
    try:
        doc = _normalise(json.loads(rows[0]["value"]))
    except Exception:
        return None
    if doc is None:
        return None
    return {"doc": doc, "updated_by": rows[0]["updated_by"], "updated_at": rows[0]["updated_at"]}


def get(use_cache=True):
    """The tenant's target with its audit fields, or None. Cached 5 s per tenant, cleared on write."""
    t = db.current_tenant()
    if (use_cache and _CACHE["loaded"] and _CACHE["tenant"] == t
            and time.time() - _CACHE["at"] < CACHE_TTL_S):
        row = _CACHE["row"]
    else:
        row = get_row()
        _CACHE["row"], _CACHE["loaded"], _CACHE["at"], _CACHE["tenant"] = row, True, time.time(), t
    if row is None:
        return None
    return dict(json.loads(json.dumps(row["doc"])), updated_by=row["updated_by"], updated_at=row["updated_at"])


def _exists():
    try:
        return bool(db.query("SELECT key FROM config WHERE tenant_id = ? AND key = ?", (db.current_tenant(), KEY)))
    except Exception:
        return False


def _write(doc, by=None):
    payload = json.dumps(doc, ensure_ascii=False)
    by = (str(by).strip()[:NAME_MAX] or None) if by is not None else None
    if _exists():
        db.execute("UPDATE config SET value = ?, updated_by = ?, updated_at = ? "
                   "WHERE tenant_id = ? AND key = ?",
                   (payload, by, _now(), db.current_tenant(), KEY))
    else:
        db.execute("INSERT INTO config (tenant_id, key, value, updated_by, updated_at) "
                   "VALUES (?, ?, ?, ?, ?)", (db.current_tenant(), KEY, payload, by, _now()))
    invalidate()


def clear():
    """Remove the tenant's target. Returns True when there was one."""
    had = _exists()
    db.execute("DELETE FROM config WHERE tenant_id = ? AND key = ?", (db.current_tenant(), KEY))
    invalidate()
    return had


# --------------------------------------------------------------------------- #
#  Setting it                                                                  #
# --------------------------------------------------------------------------- #
def _check_mode(mode):
    if mode not in MODES:
        raise TargetError("Choose how to hold the target: % below the approved plan, or a fixed tCO2e cap.")


def set_from_levers(acc, mode, levers, ui_state=None, by=None, factors=None):
    """
    Set the target from the agreed decisions. The server works every number out: carbon.scenario
    over the APPROVED plan the caller sees (a planner or admin sees every line) with `levers` as
    the one alternative. Raises TargetError with a plain sentence. Returns the stored target.
    """
    _check_mode(mode)
    if not isinstance(levers, list) or not levers:
        raise TargetError("Choose at least one decision before setting a target.")
    if _size(levers) > LEVERS_MAX:
        raise TargetError(f"The decisions are too long to store (at most {_grp(LEVERS_MAX)} characters).")
    ui_state = ui_state if ui_state is not None else {}
    if not isinstance(ui_state, dict):
        raise TargetError("The page state must be an object.")
    if _size(ui_state) > UI_STATE_MAX:
        raise TargetError(f"The page state is too large to store (at most {_grp(UI_STATE_MAX)} characters).")
    try:
        sc = carbon.scenario(acc, alternatives=[{"name": "Target", "levers": levers}], status="Approved", factors=factors)
    except carbon.CarbonError as e:
        raise TargetError(f"These decisions cannot be worked out: {e}.")
    base = sc["baseline"]["totals"]["total_t"]
    alt = sc["alternatives"][0]
    if not base or base <= 0:
        raise TargetError("The approved plan has no carbon yet, so no target was set.")
    if alt["delta_t"] >= 0:
        raise TargetError("These decisions do not lower carbon, so no target was set.")
    # delta_pct is taken on the unrounded sums (carbon.scenario); the target is the cut, as a positive %
    pct = round(-float(alt["delta_pct"]), 1) + 0.0
    if pct < 0.1:
        raise TargetError("These decisions lower carbon by less than 0.1%, so no target was set.")
    if pct >= 100.0:
        raise TargetError("These decisions take the plan to almost no carbon, which cannot be held as a target: check them.")
    doc = {
        "mode": mode,
        "pct_below": pct,
        "cap_t": _r3(alt["totals"]["total_t"]),
        "set_at_approved_t": _r3(base),
        "set_at_alternative_t": _r3(alt["totals"]["total_t"]),
        "levers": json.loads(json.dumps(levers)),
        "lever_words": list(alt.get("lever_words") or []),
        "ui_state": json.loads(json.dumps(ui_state)),
    }
    _write(doc, by=by)
    return get(use_cache=False)


def set_mode(mode, by=None):
    """Switch how the target is held (pct <-> cap), keeping every stored number."""
    _check_mode(mode)
    t = get(use_cache=False)
    if t is None:
        raise TargetError("There is no target to change yet: set one on the Carbon page first.")
    doc = {k: t[k] for k in ("pct_below", "cap_t", "set_at_approved_t", "set_at_alternative_t",
                             "levers", "lever_words", "ui_state")}
    doc["mode"] = mode
    _write(doc, by=by)
    return get(use_cache=False)


# --------------------------------------------------------------------------- #
#  Progress                                                                    #
# --------------------------------------------------------------------------- #
def status(acc, target, factors=None):
    """
    Progress against `target` on the lines `acc` can see. One carbon.scenario on the approved plan
    with the stored decisions as its one alternative, one on the Pending lines. When the stored
    decisions no longer apply (a route or a vehicle gone), the plan with them is None and `invalid`
    says why in a sentence; it is never an error.
    """
    scope = "team" if (acc or {}).get("ipt") else "scheme"
    invalid = None
    alt = None
    try:
        sc = carbon.scenario(acc, alternatives=[{"name": "Target", "levers": target.get("levers") or []}],
                             status="Approved", factors=factors)
        alt = sc["alternatives"][0]
    except carbon.CarbonError as e:
        invalid = (f"The agreed decisions no longer fit the plan ({e}), so the plan with them cannot be "
                   f"worked out. Set the target again on the Carbon page.")
        sc = carbon.scenario(acc, status="Approved", factors=factors)
    pend = carbon.scenario(acc, status="Pending", factors=factors)
    approved = _r3(sc["baseline"]["totals"]["total_t"])
    with_dec = _r3(alt["totals"]["total_t"]) if alt is not None else None
    if target["mode"] == "pct":
        target_t = _r3(approved * (1.0 - float(target["pct_below"]) / 100.0))
    else:
        target_t = _r3(target["cap_t"]) if scope == "scheme" else None
    alt_month = {m["month_index"]: m["total_t"] for m in (alt or {}).get("by_month") or []}
    return {
        "scope": scope,
        "approved_t": approved,
        "with_decisions_t": with_dec,
        "target_t": target_t,
        "gap_as_forecast_t": _r3(approved - target_t) if target_t is not None else None,
        "gap_with_decisions_t": _r3(with_dec - target_t) if (target_t is not None and with_dec is not None) else None,
        "pending_t": _r3(pend["baseline"]["totals"]["total_t"]),
        "approved_transport_t": _r3(sc["baseline"]["totals"]["transport_t"]),
        "by_month": [{"month_index": m["month_index"], "approved_t": _r3(m["total_t"]),
                      "with_decisions_t": (_r3(alt_month.get(m["month_index"])) if alt is not None else None)}
                     for m in sc["baseline"]["by_month"]],
        "invalid": invalid,
    }


def payload(acc, factors=None):
    """What GET /api/carbon/target returns (and PUT / DELETE after their write)."""
    t = get()
    if t is None:
        return {"target": None, "status": None}
    return {"target": t, "status": status(acc, t, factors)}

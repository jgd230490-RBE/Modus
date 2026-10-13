"""
Carbon target, 11 Oct 2026 (before the freeze) — the programme's agreed carbon target, one per tenant.

WHAT IT STORES
--------------
One tenanted row in the existing `config` table, key 'carbon_target' (beside 'factors' and
'costing'; no new table, so no new tenant registration, and it travels in the tenant package
like every config row):
    {"mode":                 "pct" (% below the approved plan) or "cap" (a fixed tCO2e cap),
     "pct_below":            the agreed decisions' cut on the approved plan, in % (held to 6 dp, above 0,
                             below 100; the pages print it to 1 dp. 11 Oct 2026: it was held to 1 dp, which
                             put a % target up to 0.05% of the plan off the decisions the moment it was set),
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

ON TARGET (11 Oct 2026: one rule, decided here, used by all four pages)
---------
status() says whether each figure is on target: on_target_as_forecast and on_target_with_decisions
are True when the gap is within ON_TARGET_TOL_T (0.05 tCO2e) either way, False otherwise (the sign
of the gap then says over or under), and None when there is nothing to compare. The pages put
that into words ("on target" / "N tCO2e over the target" / "N tCO2e under the target") and work
out no margin of their own.

WHAT A TEAM CODE SEES (11 Oct 2026; REVERSED 13 Oct 2026, the user's 12 Oct decision)
---------------------
"Each team gets its own share of the carbon target; a team code sees its own share and verdict."
The share (13 Oct 2026, recommended and approved): the scheme's target × the team's plan WITH the
agreed decisions ÷ the scheme's plan with them — target_t is that share, and the gaps and the two
on_target flags are the team's own against it. The same rule for a % target and a cap; the shares
add up to the scheme's target exactly. It does NOT apply the scheme's % evenly (the 11 Oct
objection: that read the decisions as missing on every team they do not touch — a team the
decisions barely touch gets a share close to its own plan). When the decisions no longer fit the
plan there is no "plan with them", so no share: target_t is None and `invalid` says why.
`share_pct` is the team's share of the scheme's target; `share_rule` says the rule in words. A team code's GET never carries the stored decisions or the
page state (they name other teams' routes); it keeps the words only of decisions that name no
route (for_code()).

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
ON_TARGET_TOL_T = 0.05        # tCO2e: a gap this small either way reads "on target" (the one rule; see ON TARGET)
PCT_DP = 6                    # pct_below is held to 6 dp; the pages print it to 1 dp

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


def _json_ok(v):
    """True when `v` is plain JSON: no NaN or Infinity. 11 Oct 2026: a NaN stored in the row made every
    later GET a 500 (the response encoder refuses non-finite floats), so it is refused at the door."""
    try:
        json.dumps(v, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def _grp(n):
    """20000 -> '20 000' (the page's number style: a space between thousands)."""
    return f"{int(n):,}".replace(",", " ")


# --------------------------------------------------------------------------- #
#  The row                                                                     #
# --------------------------------------------------------------------------- #
def _normalise(doc):
    """A stored document with every key present, or None when the row cannot be read as a target."""
    if not isinstance(doc, dict) or doc.get("mode") not in MODES or not _json_ok(doc):
        return None
    pct, cap = _num(doc.get("pct_below")), _num(doc.get("cap_t"))
    if pct is None or cap is None or not (0.0 < pct < 100.0) or cap < 0:
        return None
    return {
        "mode": doc["mode"],
        "pct_below": round(pct, PCT_DP),
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
    payload = json.dumps(doc, ensure_ascii=False, allow_nan=False)
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
    if not _json_ok(levers):
        raise TargetError("The decisions hold a number that is not finite (NaN or Infinity), so they cannot be stored.")
    if not _json_ok(ui_state):
        raise TargetError("The page state holds a number that is not finite (NaN or Infinity), so it cannot be stored.")
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
    # 11 Oct 2026: the cut is worked out from the two totals status() reads back (both to 3 dp) and held to
    # 6 dp, so straight after a % target is set the plan with the decisions IS the target (gap 0). It was
    # carbon's delta_pct, already rounded to 1 dp, which put the target up to 0.05% of the plan off.
    # The refusals still read the cut as the pages print it (1 dp), so what is refused has not changed.
    alt_total = float(alt["totals"]["total_t"])
    pct = (float(base) - alt_total) * 100.0 / float(base)
    if round(pct, 1) < 0.1:
        raise TargetError("These decisions lower carbon by less than 0.1%, so no target was set.")
    if round(pct, 1) >= 100.0:
        raise TargetError("These decisions take the plan to almost no carbon, which cannot be held as a target: check them.")
    doc = {
        "mode": mode,
        "pct_below": round(pct, PCT_DP) + 0.0,
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
        raise TargetError("There is no target to change yet: set one on the Carbon planner first.")
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
    says why in a sentence; it is never an error. on_target_* is the one "on target" rule (ON TARGET).
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
                   f"worked out. A planner needs to set the target again on the Carbon planner.")
        sc = carbon.scenario(acc, status="Approved", factors=factors)
    pend = carbon.scenario(acc, status="Pending", factors=factors)
    approved = _r3(sc["baseline"]["totals"]["total_t"])
    with_dec = _r3(alt["totals"]["total_t"]) if alt is not None else None
    share_pct = None
    if scope == "team":
        # REVERSED 13 Oct 2026 (the user's 12 Oct decision): the team's share of the scheme's target, split by the
        # plan WITH the agreed decisions (see WHAT A TEAM CODE SEES). The scheme's figures come from the same two
        # scenarios on every line (the team limit lifted for this sum only; nothing of another team is returned).
        target_t = None
        if alt is not None:
            whole = dict(acc or {}, ipt=None)
            try:
                sw = carbon.scenario(whole, alternatives=[{"name": "Target", "levers": target.get("levers") or []}],
                                     status="Approved", factors=factors)
                s_approved = sw["baseline"]["totals"]["total_t"]
                s_with = sw["alternatives"][0]["totals"]["total_t"]
                s_target = (s_approved * (1.0 - float(target["pct_below"]) / 100.0) if target["mode"] == "pct"
                            else float(target["cap_t"]))
                if s_with and s_with > 0:
                    target_t = _r3(s_target * alt["totals"]["total_t"] / s_with)
                    share_pct = round(100.0 * alt["totals"]["total_t"] / s_with, 1)
            except carbon.CarbonError as e:
                invalid = (f"The agreed decisions no longer fit the plan ({e}), so your share of the target cannot be "
                           f"worked out. A planner needs to set the target again on the Carbon planner.")
    elif target["mode"] == "pct":
        target_t = _r3(approved * (1.0 - float(target["pct_below"]) / 100.0))
    else:
        target_t = _r3(target["cap_t"])
    gap_f = _r3(approved - target_t) if target_t is not None else None
    gap_d = _r3(with_dec - target_t) if (target_t is not None and with_dec is not None) else None
    alt_month = {m["month_index"]: m["total_t"] for m in (alt or {}).get("by_month") or []}
    return {
        "scope": scope,
        "approved_t": approved,
        "with_decisions_t": with_dec,
        "target_t": target_t,
        "gap_as_forecast_t": gap_f,
        "gap_with_decisions_t": gap_d,
        "on_target_as_forecast": on_target(gap_f),
        "on_target_with_decisions": on_target(gap_d),
        "pending_t": _r3(pend["baseline"]["totals"]["total_t"]),
        "approved_transport_t": _r3(sc["baseline"]["totals"]["transport_t"]),
        "by_month": [{"month_index": m["month_index"], "approved_t": _r3(m["total_t"]),
                      "with_decisions_t": (_r3(alt_month.get(m["month_index"])) if alt is not None else None)}
                     for m in sc["baseline"]["by_month"]],
        "invalid": invalid,
        # 13 Oct 2026: a team code's share of the scheme's target (None for the scheme, or with no share)
        "share_pct": share_pct,
        "share_rule": (SHARE_RULE if scope == "team" else None),
    }


SHARE_RULE = ("Your share of the scheme's target: the target × your lines' plan with the agreed decisions ÷ the "
              "scheme's plan with them. The shares of every team add up to the scheme's target.")


def on_target(gap):
    """The one "on target" rule: None when there is nothing to compare, else |gap| <= ON_TARGET_TOL_T."""
    if gap is None:
        return None
    return abs(float(gap)) <= ON_TARGET_TOL_T + 1e-9


def _names_a_route(lv):
    sc = (lv or {}).get("scope") if isinstance(lv, dict) else None
    return bool((isinstance(sc, dict) and sc.get("route_id")) or (isinstance(lv, dict) and lv.get("to_route")))


def for_code(acc, t):
    """
    What a code may read of the stored target. A planner, admin or the demo submitter (every line) reads
    it all. 11 Oct 2026: a team code never gets the stored decisions or the page state (they name other
    teams' routes), and keeps the words only of decisions that name no route (a material or every line).
    lever_words is one sentence per decision, in order (carbon.scenario); a row where the two lists do not
    line up gives a team code no words at all rather than a guess.
    """
    if t is None or not (acc or {}).get("ipt"):
        return t
    lv, words = t.get("levers") or [], t.get("lever_words") or []
    keep = [w for l, w in zip(lv, words) if not _names_a_route(l)] if len(lv) == len(words) else []
    out = {k: v for k, v in t.items() if k not in ("levers", "ui_state")}
    out["lever_words"] = keep
    return out


def payload(acc, factors=None):
    """What GET /api/carbon/target returns (and PUT / DELETE after their write)."""
    t = get()
    if t is None:
        return {"target": None, "status": None}
    return {"target": for_code(acc, t), "status": status(acc, t, factors)}

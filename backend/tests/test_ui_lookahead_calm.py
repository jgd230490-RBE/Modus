"""The 9 Nov 2026 UI critique, wave 3 (branch claude/ui-fix-lookahead-calm), the server's half of finding 5:
a line short last week is FLAGGED only past a share of its plan, and the shortfall is read in tonnes.

Run from the repo root:  python backend/tests/test_ui_lookahead_calm.py

What this proves: the share is the organisation's (Config → Planning, `planning.short_flag_pct`), 10 % when unset, a
nonsense value falls back to 10; `short_is_flagged` is "more than", not "at least"; per_line raises SHORTAGE only past
the share (and still never for a line inside the 98 % band or already carried); Config refuses a share outside 0–100 in
the field's own words; the seed carries 10. End to end on the shipped demo package (date pinned to its as-of week): every
Account row says whether it is flagged, the rail's SHORTAGE lines are exactly the flagged rows, `shortfall_t` adds a
concrete line's m³ at its density (2.4 t/m³) where `shortfall` still adds the line's own units, and moving the share on
Config moves the flags (0 % flags every miss outside the band, 50 % none of the demo's).

What it does not prove: how the screens draw it (ui_fix_lookahead_calm.js, the UI audit, a look in Chrome), or live's
figures (live's saved Config has no `short_flag_pct` until a Config save or a re-import: it reads the 10 % default).
"""
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)

for _v in ("DATABASE_URL", "HERE_API_KEY", "MAPBOX_TOKEN"):
    os.environ.pop(_v, None)
os.environ["TENANT_ID"] = "default"
TMP = tempfile.mkdtemp(prefix="ui_lookahead_calm_")

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "calm.db")
import conversions  # noqa: E402
import config  # noqa: E402
import clashes  # noqa: E402
import taxonomy  # noqa: E402
import tenant_package  # noqa: E402
import lookahead  # noqa: E402
from portable import pin_today, DEMO_AS_OF, remove_scratch_db  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- the rule, on its own
ok("⭐ 5: the share is 10 % when the organisation has none", clashes.short_flag_pct({"planning": {}}) == 10.0
   and clashes.SHORT_FLAG_PCT == 10.0)
ok("...an organisation's own share wins (5, 0, 100)", clashes.short_flag_pct({"planning": {"short_flag_pct": 5}}) == 5.0
   and clashes.short_flag_pct({"planning": {"short_flag_pct": 0}}) == 0.0 and clashes.short_flag_pct({"planning": {"short_flag_pct": 100}}) == 100.0)
ok("🔴 ...a nonsense share falls back to 10 (text, a boolean, below 0, over 100, null)",
   all(clashes.short_flag_pct({"planning": {"short_flag_pct": v}}) == 10.0 for v in ("ten", True, -1, 101, None)))
ok("⭐ short_is_flagged: 130 of 1,000 at 10 % flags; 45 of 675 (6.7 %) does not; exactly 10 % does not (more than, not at least)",
   clashes.short_is_flagged(130, 1000, 10) and not clashes.short_is_flagged(45, 675, 10) and not clashes.short_is_flagged(40, 400, 10))
ok("...nothing to carry, or no plan, never flags; 0 % flags any miss", not clashes.short_is_flagged(0, 100, 0)
   and not clashes.short_is_flagged(5, 0, 10) and clashes.short_is_flagged(0.5, 100, 0))


def _line(rid, sec, qty=100.0):
    return {"route_id": rid, "month_index": 11, "discipline": "earthworks", "section_id": sec, "ipt": "IPT1",
            "context": {"origin_name": "A", "dest_name": "B", "flags": []}, "week": {"planned_qty": qty}, "days": []}


def _acct(rid, sec, planned, actual, carried=None, unit="t"):
    return {"route_id": rid, "discipline": "earthworks", "section_id": sec, "planned_qty": planned, "actual_qty": actual,
            "calibrated_qty": carried, "unit": unit}


_lf = conversions.load_factors
try:
    conversions.load_factors = lambda: {"planning": {}}
    _fl = clashes.per_line([_line("R1", "A"), _line("R1", "B"), _line("R1", "C"), _line("R1", "D"), _line("R1", "E")],
                           [_acct("R1", "A", 1000, 870),          # 130 short: 13 %
                            _acct("R1", "B", 675, 630),           # 45 short: 6.7 %
                            _acct("R1", "C", 100, 99),            # inside the 98 % band
                            _acct("R1", "D", 1000, 800, 150),     # 200 short, 150 carried: 50 left = 5 %
                            _acct("R1", "E", 100, None)])         # not reported
    _sh = {f["section_id"]: f for f in _fl if f["code"] == "SHORTAGE"}
    ok("⭐ 5: per_line raises SHORTAGE only past the share: 130 of 1,000 yes; 45 of 675, the 98 % band, a mostly carried line, an "
       "unreported one no", set(_sh) == {"A"}, str(sorted(_sh)))
    ok("...its words still name the amount and the unit", "130 t short, not yet carried" in _sh.get("A", {}).get("text", "")
       and _sh.get("A", {}).get("short") == 130.0)
    conversions.load_factors = lambda: {"planning": {"short_flag_pct": 0}}
    _fl0 = {f["section_id"] for f in clashes.per_line([_line("R1", s) for s in "ABCDE"],
                                                      [_acct("R1", "A", 1000, 870), _acct("R1", "B", 675, 630),
                                                       _acct("R1", "C", 100, 99), _acct("R1", "D", 1000, 800, 150)])
            if f["code"] == "SHORTAGE"}
    ok("...at 0 % every miss outside the band flags (A, B, D), the band still holds (C)", _fl0 == {"A", "B", "D"}, str(sorted(_fl0)))
finally:
    conversions.load_factors = _lf

# --------------------------------------------------------------------------- Config and the seed
_seed = json.loads(read("backend/factors.json"))
ok("the seed carries short_flag_pct 10, with its note", _seed["planning"].get("short_flag_pct") == 10
   and "_short_flag_pct_note" in _seed["planning"])


def _probs(v):
    d = json.loads(json.dumps(_seed))
    if v is None:
        d["planning"].pop("short_flag_pct", None)
    else:
        d["planning"]["short_flag_pct"] = v
    return [p for p in config.validate(d) if "shortfall" in p]


ok("⭐ Config refuses a share outside 0–100, in the field's words", _probs(150) == ["Flag a shortfall over: a percentage from 0 to 100"]
   and _probs(-5) and _probs("x"), str(_probs(150)))
ok("...and takes 0, 10, 100 or none at all", not _probs(0) and not _probs(10) and not _probs(100) and not _probs(None))

# --------------------------------------------------------------------------- end to end: the demo package
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)
PKG = json.loads(read("demo/uk-corridor.package.json"))
_res = tenant_package.import_tenant(PKG, replace=True)
ok("the demo package imports", _res.get("ok") is True, str(_res)[:200])
config.invalidate()
_PIN = pin_today(DEMO_AS_OF)
_ACC = {"role": "planner", "ipt": None}


def _page():
    return lookahead.page(acc=_ACC, with_restrictions=False)


pg = _page()
A = pg["account"]
rows = A["rows"]
flagged = {(r["route_id"], r.get("discipline") or "", r.get("section_id") or "") for r in rows if r.get("short_flag")}
rail = {(f["route_id"], f["discipline"], f["section_id"]) for f in pg["clashes"]["flags"] if f["code"] == "SHORTAGE"}
ok("⭐ 5: every Account row says whether it is flagged, and the rail's SHORTAGE lines are exactly the flagged rows",
   all("short_flag" in r and "remaining_short_t" in r for r in rows) and flagged == rail and len(rail) >= 1,
   f"{sorted(flagged)} vs {sorted(rail)}")
ok("...a flagged row is one past 10 % of its plan; an unflagged row with something to carry is under it",
   all((r["remaining_short"] > 0.10 * r["planned_qty"]) == bool(r["short_flag"]) for r in rows if r["remaining_short"] > 1e-6))
ok("...the page says the share it used", A.get("short_flag_pct") == 10.0 and pg["clashes"].get("short_flag_pct") == 10.0
   and A.get("short_flagged") == len(flagged))
_exp_t = sum(r["remaining_short"] * (2.4 if r["unit"] == "m3" else 1.0) for r in rows)
ok("⭐ 5: shortfall_t is every line in tonnes (a concrete line's m³ × 2.4); shortfall still adds each line's own unit",
   abs(A["shortfall_t"] - round(_exp_t, 3)) < 1e-6 and abs(A["shortfall"] - round(sum(r["remaining_short"] for r in rows), 3)) < 1e-6,
   f'{A["shortfall_t"]} vs {_exp_t}')
_m3 = [r for r in rows if r["unit"] == "m3" and r["remaining_short"] > 1e-6]
ok("...a concrete line's remaining_short_t is its m³ × 2.4 (when the as-of week has one short)",
   all(abs(r["remaining_short_t"] - r["remaining_short"] * 2.4) < 1e-6 for r in _m3), f"{len(_m3)} m3 rows short")

# the share moves the flags
_doc = json.loads(json.dumps(config.load(conversions)))
_doc["planning"]["short_flag_pct"] = 0
_sv = config.save(_doc, by="test")
config.invalidate()
pg0 = _page()
spread = {(r["route_id"], r.get("discipline") or "", r.get("section_id") or "") for r in pg0["account"]["rows"] if r["action"] == "spread"}
rail0 = {(f["route_id"], f["discipline"], f["section_id"]) for f in pg0["clashes"]["flags"] if f["code"] == "SHORTAGE"}
ok("⭐ Config → Planning at 0 %: every line open to add (outside the 98 % band) is flagged again (the old rail)",
   _sv.get("ok") is True and rail0 == spread and len(rail0) >= len(rail), f"{_sv} {len(rail0)} vs {len(spread)}")
_doc["planning"]["short_flag_pct"] = 50
config.save(_doc, by="test")
config.invalidate()
pg50 = _page()
ok("...at 50 % none of the demo's shortfalls is flagged, and Account's count of lines open to add is unchanged",
   not any(f["code"] == "SHORTAGE" for f in pg50["clashes"]["flags"])
   and pg50["account"]["open_to_calibrate"] == pg0["account"]["open_to_calibrate"])

remove_scratch_db(db, TMP)
print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

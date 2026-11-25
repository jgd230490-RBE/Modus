"""
The best option after the live check and UI / UX review of 17 Nov 2026 (branch claude/ui-best-option-1117; John: "Yes,
as recommended" to Q1 to Q7 of notes/ux-best-option-1117). The rule's words, the record's figures, the press and the
Route analysis summary page. The card's side is ui_fix_best_option_1117.js.

WHAT IS ASSERTED (every check marked ⭐ fails on the code before this branch):
  1. Q1, a FAULT: an option's added lorry limits are ONE reason, road by road (R011's Alt 2 read 361 words, a clause a
     stored stretch): each road once, at most three named then "N more", unnamed roads last, the legs said once where
     every road shares them; 25 words or fewer for every shape tried (one limit, two kinds, three, four, long names);
     every stretch still in added_limits with its road and its short name;
  2. Q1's second guard: a summary page never draws text below its bottom margin, whatever the reasons' length (the
     answer's why and each note cut at four lines ending "… section A has the rest"; the notes take only the room the
     page's lower half leaves); the ordinary page is not moved;
  3. Q4: "No other option is clearly better." (it read "…clearly ahead on any head."); no "head" in a sentence a person
     reads;
  4. Q5: a suggestion that is LONGER opens with what it gains, "…, for N min longer a round trip."; a quicker one keeps
     the time first;
  5. Q6: `trade_also` names the other options that are trade-offs too;
  6. Q7 and finding 8: one rounding for a time difference (route_best.half_min, to the nearest half minute) in the rule's
     sentences and the record's trip; the record's sums use WHOLE loads that add up to the rounded total;
  7. Q2: one press moves every leg it names: every leg is checked BEFORE any is swapped, the record is read once and
     written once, the road sections and route choices rebuilt once, and the reply carries the route's new answer.

WHAT THIS DOES NOT PROVE: live's figures (R011's real limits: the words are run on typed stretches through the rule's own
functions); the press's time on live (the session note gives a local measure); Postgres.

Run:  python backend/tests/test_best_option_1117.py
"""
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

TMP = tempfile.mkdtemp(prefix="wayscope_best1117_")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import portable  # noqa: E402,F401  (keeps Mapbox out of any PDF build)
import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import collisions  # noqa: E402
import network  # noqa: E402
import route_best as RB  # noqa: E402
import route_choice  # noqa: E402
import route_record as REC  # noqa: E402
import route_analysis_render as RR  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  -> {str(extra)[:400]}")


def TRY(f, default=None):
    try:
        return f()
    except Exception as e:          # a missing function on the old code is a failed check, not a crash
        return default if default is not None else e


def words(s):
    return len(str(s).split())


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


# =========================================================================== #
#  1. Q1: added limits road by road                                            #
# =========================================================================== #
def A(road, ext, leg="return", short="7.5 t limit", exc=True, kind="weight"):
    return {"leg": leg, "source": "osm", "ext_id": ext, "kind": kind, "short": short, "road": road,
            "except_for_access": exc, "words": "Weight limit 7.5 t"}


# R011's Alt 2 as the 17 Nov review found it: 16 stretches on four named roads and unnamed ones, mostly the return leg
R011 = ([A("Syston Road", f"s{i}") for i in range(6)] + [A("Cossington Lane", f"c{i}") for i in range(4)]
        + [A("Valley Road", f"v{i}") for i in range(3)] + [A(None, f"u{i}") for i in range(2)]
        + [A("Syston Road", "s0", leg="loaded")])
aw = TRY(lambda: RB.added_words(R011))
ok("⭐ 1. R011's Alt 2: one reason, road by road, at most three roads named and the unnamed ones last",
   aw == "it adds 7.5 t limits, except for access, on Syston Road, Cossington Lane, Valley Road and unnamed roads", aw)
ok("⭐ 1. R011's Alt 2: 25 words or fewer (it was 361), each road once, 'except for access' once",
   isinstance(aw, str) and words(aw) <= 25 and aw.count("Syston Road") == 1 and aw.count("except for access") == 1,
   aw)
one = TRY(lambda: RB.added_words([A("Narborough Road South", "n1")]))
ok("⭐ 1. one limit: 'a 7.5 t limit', its leg once at the end",
   one == "it adds a 7.5 t limit, except for access, on Narborough Road South (return leg)", one)
both = TRY(lambda: RB.added_words([A("Back Lane", "b1", leg="loaded"), A("Back Lane", "b1", leg="return")]))
ok("⭐ 1. a road met on both legs: '(both legs)' once", both == "it adds a 7.5 t limit, except for access, on Back Lane "
   "(both legs)", both)
four = TRY(lambda: RB.added_words([A("Syston Road", "a"), A("Mill Lane", "b"), A("Valley Road", "c"),
                                   A("Station Road", "d")]))
ok("⭐ 1. four named roads: three named, then '1 more'",
   isinstance(four, str) and four.endswith("on Mill Lane, Station Road, Syston Road, 1 more (return leg)")
   or (isinstance(four, str) and "1 more" in four and words(four) <= 25), four)
mixed_legs = TRY(lambda: RB.added_words([A("Syston Road", "a", leg="loaded"), A("Mill Lane", "b", leg="return")]))
ok("⭐ 1. roads met on different legs: no leg said (each stretch's leg stays in added_limits)",
   isinstance(mixed_legs, str) and "leg" not in mixed_legs and "Syston Road" in mixed_legs and "Mill Lane" in mixed_legs,
   mixed_legs)
two_kinds = TRY(lambda: RB.added_words([A("Syston Road", "a", leg="loaded"),
                                        A("Mill Lane", "h", leg="loaded", short="4.2 m height limit", exc=False,
                                          kind="height")]))
ok("⭐ 1. two kinds: a clause each, the legs once",
   isinstance(two_kinds, str) and "a 7.5 t limit, except for access, on Syston Road" in two_kinds
   and "a 4.2 m height limit on Mill Lane" in two_kinds and two_kinds.endswith("(loaded leg)")
   and words(two_kinds) <= 25, two_kinds)
LONG = ["Upper Brook Street Industrial Estate Access Road", "Kilby Ridge Quarry Northern Haul Link",
        "Old Melton Road Service Road", "Sileby Road", "Ratcliffe Lane"]
shapes = {
    "three kinds": [A("Syston Road", "a"), A("Mill Lane", "h", short="4.2 m height limit", exc=False, kind="height"),
                    A("Station Road", "w", short="2.5 m width limit", exc=False, kind="width")],
    "four kinds, many roads": [A(r, f"{k}{i}", short=s, exc=e, kind=k)
                               for i, r in enumerate(LONG)
                               for k, s, e in (("weight", "18 t limit", False), ("weight", "7.5 t limit", True),
                                               ("height", "4.2 m height limit", False),
                                               ("axle", "10 t axle limit", False))],
    "long names": [A(r, f"l{i}") for i, r in enumerate(LONG)],
    "twenty unnamed stretches": [A(None, f"x{i}") for i in range(20)],
}
for name, added in shapes.items():
    s = TRY(lambda: RB.added_words(added))
    ok(f"⭐ 1. {name}: one reason of 25 words or fewer", isinstance(s, str) and s.startswith("it adds ")
       and words(s) <= 25, s)


class _Ctx:
    zones_on = []
    lims = [{"source": "osm", "ext_id": f"s{i}", "kind": "weight", "value": 7.5, "name": "Syston Road",
             "exceptions": "Except for access"} for i in range(3)] + [
            {"source": "osm", "ext_id": "u1", "kind": "weight", "value": 7.5, "name": None, "ref": None,
             "exceptions": "Except for access"}]


_real_below = route_choice._below_keys
route_choice._below_keys = lambda line, lorry, leg, lims: (
    {("osm", L["ext_id"], "weight") for L in lims} if line == "OPT" else set())
try:
    reasons, added = TRY(lambda: RB._ruled_out({"loaded": "OPT", "return": "OPT"}, {"loaded": "USE", "return": "USE"},
                                               "Artic Tipper (44t)", _Ctx), ([], []))
finally:
    route_choice._below_keys = _real_below
ok("⭐ 1. _ruled_out: ONE reason for all the added limits (it was a clause a stretch and a leg)",
   len(reasons) == 1 and reasons[0] == "it adds 7.5 t limits, except for access, on Syston Road and an unnamed road "
   "(both legs)", reasons)
ok("⭐ 1. _ruled_out: every stretch and leg still in added_limits, each with its road and short name (section A)",
   len(added) == 8 and all("road" in a and a.get("short") == "7.5 t limit" for a in added)
   and {a["road"] for a in added} == {"Syston Road", None}, added[:2])

# =========================================================================== #
#  2. Q1's second guard: nothing below a summary page's bottom margin          #
# =========================================================================== #
def cnt(col, left, places, mins, co2):
    return {"collisions": col, "goods": 0, "left_turns": left, "cycle_meets": 1, "cycle_beside_km": 0.1,
            "places": places, "shown": {"bus_stops": 3}, "cycle_min": mins, "trips": 4, "co2_kg": co2, "km": 40.0,
            "busy_min": {"08:00": mins, "17:00": mins + 5}}


def col(label, counts, in_use=False, ruled_out=None):
    return {"label": label, "in_use": in_use, "chosen": False, "traded": False, "ruled_out": ruled_out or [],
            "counts": counts, "pct": {"left_turns": -29, "cycle_meets": -40, "cycle_beside_km": -33, "places": -56},
            "head_words": {}}


def best(why, cols, held=None, counted=True, limits=()):
    return {"error": None, "answer": "Keep the route in use", "option": None, "why": why, "held_back": held,
            "lorry": "X", "lorry_text": "Artic Tipper (44t)", "lorry_basis": "approved loads",
            "others_text": ["Flatbed (44t)", "Concrete mixer (26t)", "Concrete mixer (32t)"], "history": "current",
            "counted": counted, "period": "2021–2025", "in_use_words": "the main route, both legs", "cols": cols,
            "busy_held": True, "cycle_held": True, "in_use_limits": list(limits)}


def page(B):
    """The summary page for one typed answer; every string drawn above the foot, with its y, and the page's bottom."""
    D = {"tenant": "Wolds Link", "made": "17 Nov 2026", "demo_notice": "Fictional scheme", "lorry": None, "unit": "mi",
         "routes": [{"id": "R011", "origin": "Kilby Ridge Quarry", "dest": "Brook Pit", "best": B}]}
    doc = RR.Doc(D)
    drawn, box = [], {"foot": False}
    for name in ("drawString", "drawRightString", "drawCentredString"):
        real = getattr(doc.c, name)

        def wrap(x, y, text, *a, _real=real, **k):
            if not box["foot"]:
                drawn.append((y, str(text)))
            return _real(x, y, text, *a, **k)
        setattr(doc.c, name, wrap)
    real_end = doc.end_page

    def end():
        box["foot"] = True
        real_end()
    doc.end_page = end
    RR.page_summary(doc, D["routes"][0], 1, 1, {})
    return drawn, doc.bottom()


STRETCH = "Weight limit 7.5 t · Syston Road (except for access: a lorry may use it to reach premises on it) (return leg)"
OLD = "it meets 16 road limits below this lorry that the route in use does not: " + "; ".join([STRETCH] * 16)
USE = col("In use", cnt(26, 17, 9, 120.0, 40.0), in_use=True)
NEW2 = "it adds 7.5 t limits, except for access, on Syston Road, Cossington Lane, Valley Road and unnamed roads"
NEW1 = "it adds 7.5 t limits, except for access, on unnamed roads (both legs)"
PAGES = {
    "R011 in the new words": best(f"Every other option is ruled out: Alt 1: {NEW1}; Alt 2: {NEW2}.",
                                  [USE, col("Alt 1", cnt(8, 2, 1, 90.0, 30.0), ruled_out=[NEW1]),
                                   col("Alt 2", cnt(9, 3, 1, 95.0, 31.0), ruled_out=[NEW2])]),
    "R011 in the OLD words (443 words of why)": best(f"Every other option is ruled out: Alt 1: {OLD}; Alt 2: {OLD}.",
                                                     [USE, col("Alt 1", cnt(8, 2, 1, 90.0, 30.0), ruled_out=[OLD]),
                                                      col("Alt 2", cnt(9, 3, 1, 95.0, 31.0), ruled_out=[OLD])]),
    "the longest typed: a long why, held back, not counted, three notes, two limits in use":
        best("Not suggested yet: " + OLD + ".",
             [USE] + [col(f"Alt {i}", cnt(8, 2, 1, 90.0, 30.0), ruled_out=[OLD]) for i in (1, 2, 3)],
             held=OLD + " held", counted=False,
             limits=[{"short": "7.5 t limit", "legs": "loaded"}, {"short": "7.5 t limit", "legs": "return"}]),
}
low = {}
for name, B in PAGES.items():
    drawn, bottom = TRY(lambda: page(B), ([], 0))
    lowest = min((y for y, _t in drawn), default=-1)
    low[name] = lowest
    ok(f"{'' if 'new words' in name else '⭐ '}2. {name}: no text drawn below the page's bottom margin ({bottom:.0f} pt)",
       drawn and lowest >= bottom, f"lowest {lowest:.1f}: {min(drawn, default=(0, ''))[1][:60]}")
    if "OLD" in name or "longest" in name:
        ok(f"⭐ 2. {name}: a cut reason ends '… section A has the rest'",
           any(t.endswith("section A has the rest") for _y, t in drawn), [t for _y, t in drawn][:4])
ok("⭐ 2. the guard is named: SUM_REASON_LINES 4, SUM_CUT, and the lower half measured before the notes are drawn",
   getattr(RR, "SUM_REASON_LINES", None) == 4 and getattr(RR, "SUM_CUT", "") == "… section A has the rest"
   and callable(getattr(RR, "_sum_lower_h", None)))
ok("2. the ordinary page (new words) keeps its room: its last line 30 pt or more above the margin",
   low.get("R011 in the new words", -1) >= 68 + 30, low)

# =========================================================================== #
#  3. Q4: no "head" a person reads                                             #
# =========================================================================== #
ok("⭐ 3. 'No other option is clearly better.'", getattr(RB, "NONE_BETTER_WORDS", "") == "No other option is clearly better.")
SRC = read("backend", "route_best.py")
CODE = "\n".join(l.split("#")[0] for l in SRC.splitlines())          # comments may quote the old words
ok("⭐ 3. the rule's sentences carry no 'head': 'clearly ahead on any head' and 'level on every head' are gone",
   # REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): the short line's empty case reads "the same on every measure" (it read "level on every
   # measure"; nothing says ahead or level now)
   "clearly ahead on any head" not in CODE and "level on every head" not in CODE and "the same on every measure" in CODE
   and "level on every measure" not in CODE)
HTML = read("frontend", "index.html")
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "clearly better on one measure and worse on none" (it read "clearly ahead … behind on none")
ok("⭐ 3. the card's 'i' box says 'measure', not 'head'",
   "clearly better on one measure and worse on none" in HTML and "ahead on one head" not in HTML
   and "clearly ahead on one measure" not in HTML)


# =========================================================================== #
#  4 and 5. Q5 gains first when longer; Q6 trade_also                          #
# =========================================================================== #
class Fake:
    lims = [1]
    community_all = True
    period = collisions.period_words([2021, 2025])


def M(col_, goods, lt, meets, beside, places, km, drive, cyc_min, trips, co2):
    return {"collisions": col_, "goods": goods, "left_turns": lt, "cycle_meets": meets, "cycle_beside_km": beside,
            "places": places, "km": km, "drive_min": drive, "cycle_min": cyc_min, "trips": trips, "co2_kg": co2,
            "busy_min": {h: None for h in RB.BUSY_HOURS}, "shown": {}}


def demo(use, alts):
    use = dict(use, busy_at={h: None for h in RB.BUSY_HOURS})
    out = {"options": [RB.option_entry(a, m, use, Fake, "current") for a, m in alts], "answer": RB.KEEP,
           "option": None, "trade": None, "why": None, "held_back": None, "sentences": []}
    RB._answer(out, use, Fake, "current")
    return out


# R014's Alt 1 (17 Nov live): 5 fewer left turns, 8.2 kg less carbon, 2.4 min LONGER a round trip
# (driving 90 min, so a 2.4 min gap is under the rule's 3 % and the time is "the same", as on live)
LONGER = demo(M(20, 0, 17, 3, 0.4, 3, 40.0, 90.0, 100.0, 5, 40.0),
              [(1, M(20, 0, 12, 3, 0.4, 3, 40.4, 91.0, 102.4, 5, 31.8))])
# REVERSED 24 Nov 2026 (the Routes page rethink, Q7 to Q9; John: "Yes, as recommended"): "left-hand turns" (it read "left turns")
ok("⭐ 4. a LONGER suggestion opens with what it gains: '5 fewer left-hand turns and 8.2 kg CO₂e less a trip, for 2.5 min "
   "longer a round trip.'", LONGER["answer"] == RB.SUGGESTED and LONGER["why"] ==
   "5 fewer left-hand turns and 8.2 kg CO₂e less a trip, for 2.5 min longer a round trip.", LONGER["why"])
QUICKER = demo(M(20, 0, 17, 3, 0.4, 3, 40.0, 50.0, 104.0, 5, 40.0),
               [(1, M(20, 0, 12, 3, 0.4, 3, 39.0, 46.0, 100.5, 5, 39.9))])
ok("4. a quicker suggestion keeps the time first, in halves: '3.5 min quicker a round trip, with 5 fewer left-hand turns.'",
   QUICKER["answer"] == RB.SUGGESTED and QUICKER["why"] == "3.5 min quicker a round trip, with 5 fewer left-hand turns.",
   QUICKER["why"])
# two trade-offs: Alt 1 fewer left turns but more carbon; Alt 2 the same kind of trade
TWO = demo(M(20, 0, 17, 3, 0.4, 3, 40.0, 50.0, 100.0, 5, 40.0),
           [(1, M(20, 0, 12, 3, 0.4, 3, 40.0, 50.0, 100.0, 5, 48.0)),
            (2, M(20, 0, 11, 3, 0.4, 3, 40.0, 50.0, 100.0, 5, 49.0))])
ok("⭐ 5. two trade-offs: the card's option is one, `trade_also` names the other ('Alt 2')",
   TWO["answer"] == RB.TRADE_OFF and TWO.get("trade_also") in (["Alt 2"], ["Alt 1"])
   and TWO["trade"].split(" has ")[0] not in TWO.get("trade_also", []), (TWO["answer"], TWO.get("trade_also")))
ONE_T = demo(M(20, 0, 17, 3, 0.4, 3, 40.0, 50.0, 100.0, 5, 40.0), [(1, M(20, 0, 12, 3, 0.4, 3, 40.0, 50.0, 100.0, 5, 48.0))])
ok("⭐ 5. one trade-off: `trade_also` is empty", ONE_T["answer"] == RB.TRADE_OFF and ONE_T.get("trade_also") == [],
   ONE_T.get("trade_also"))
ok("⭐ 5. the table row carries trade_also", '"trade_also": r.get("trade_also") or []' in SRC)

# =========================================================================== #
#  6. Q7 halves; finding 8 whole loads                                         #
# =========================================================================== #
hm = getattr(RB, "half_min", None)
ok("⭐ 6. half_min: the nearest half minute, signed (104 → 100.5 is -3.5; 100 → 102.4 is 2.5; 100 → 100.2 is 0)",
   hm is not None and hm(104, 100.5) == -3.5 and hm(100, 102.4) == 2.5 and hm(100, 100.2) == 0 and hm(100, 101.3) == 1.5,
   hm and (hm(104, 100.5), hm(100, 102.4), hm(100, 100.2), hm(100, 101.3)))
REC_SRC = read("backend", "route_record.py")
ok("⭐ 6. the record's trip carries 'min_half' from the rule's own rounding", '"min_half": half' in REC_SRC
   and "route_best.half_min" in REC_SRC.replace("half_min(", "route_best.half_min(") and "half_min" in REC_SRC)
wh = getattr(REC, "_whole", None)
ok("⭐ 6. _whole: shares as whole loads that add up to the rounded total, the largest remainder first",
   wh is not None and wh([45.45]) == [45] and wh([1.4, 1.4, 1.2]) == [2, 1, 1] and sum(wh([10.6, 20.6, 0.3])) == 32
   and wh([0.0]) == [0], wh and (wh([45.45]), wh([1.4, 1.4, 1.2]), wh([10.6, 20.6, 0.3])))
ok("⭐ 6. the record's Loads cell reads 'N planned' ('35 of 212 planned' on a busy-hours road), one form",
   'data-rc-loads="1">{r.kind === "busy" ? `${grp(Math.round(p.trips))} of ${grp(Math.round(p.of))}` : '
   'grp(Math.round(p.trips))} planned</td>' in HTML)

# =========================================================================== #
#  7. Q2: one press for every leg                                              #
# =========================================================================== #
calls = {"execute": [], "rebuild": 0, "choice": 0, "before": [], "after": 0, "card": 0}
saved = {}


def patch(mod, name, val):
    saved[(mod, name)] = getattr(mod, name, None)
    setattr(mod, name, val)


import holding  # noqa: E402
import road_sections  # noqa: E402


class _RecCtx:
    def __init__(self):
        self.reread_n = 0

    def reread(self):
        self.reread_n += 1


RCTX = _RecCtx()
patch(db, "execute", lambda sql, args=(): calls["execute"].append((sql, args)))
patch(road_sections, "_rebuild_quietly", lambda why: calls.__setitem__("rebuild", calls["rebuild"] + 1))
patch(route_choice, "refresh_quietly", lambda why: calls.__setitem__("choice", calls["choice"] + 1))
patch(holding, "mark_route", lambda rid: None)
patch(REC, "before_promote", lambda rid, prof, legs, alt: calls["before"].append(legs) or {"ctx": types.SimpleNamespace(get=lambda: RCTX)})
patch(REC, "after_promote", lambda rec, who=None: calls.__setitem__("after", calls["after"] + 1))
patch(RB, "card_answer", lambda rid, ctx: calls.__setitem__("card", calls["card"] + 1) or {"route": {"route": rid, "answer": RB.KEEP}})
try:
    # a leg that does not hold the option refuses the WHOLE press before anything is swapped
    patch(network, "_promote_refusal", lambda rid, prof, alt, leg: {"error": "no alternative 1"} if leg == "return" else None)
    r1 = TRY(lambda: network.promote_alternative("R050", "Artic Tipper (44t)", 1, leg="loaded", who="x",
                                                 legs=["loaded", "return"]), {})
    ok("⭐ 7. a leg without the option refuses the whole press: nothing swapped, nothing recorded",
       isinstance(r1, dict) and r1.get("error") and not calls["execute"] and not calls["before"], (r1, calls))
    setattr(network, "_promote_refusal", lambda rid, prof, alt, leg: None)
    r2 = TRY(lambda: network.promote_alternative("R050", "Artic Tipper (44t)", 1, leg="loaded", who="x",
                                                 legs=["loaded", "return"]), {})
    ok("⭐ 7. one press, both legs: three swap statements a leg, the record read once (both legs) and written once",
       len(calls["execute"]) == 6 and calls["before"] == [["loaded", "return"]] and calls["after"] == 1, calls)
    ok("⭐ 7. the road sections and the route choices are rebuilt ONCE for the press (it was once a leg)",
       calls["rebuild"] == 1 and calls["choice"] == 1, calls)
    ok("⭐ 7. the reply carries the route's new answer from the record's own Context, read again after the swap",
       isinstance(r2, dict) and (r2.get("best") or {}).get("route", {}).get("route") == "R050" and calls["card"] == 1
       and RCTX.reread_n == 1 and r2.get("legs") == ["loaded", "return"], (r2, RCTX.reread_n))
finally:
    for (mod, name), val in saved.items():
        setattr(mod, name, val)
MAIN = read("backend", "main.py")
ok("⭐ 7. the endpoint takes `legs` and passes them in one call",
   "legs: Optional[str] = None" in MAIN and
   "network.promote_alternative(route_id, profile, alt_index, leg=want[0], who=_by(), legs=want)" in MAIN)
ok("⭐ 7. the app's press is ONE request carrying every leg", 'legs: legs.join(",") });' in HTML
   and "for(const lg of (card ? card.legs" not in HTML)

# --------------------------------------------------------------------------- #
__import__("shutil").rmtree(TMP, ignore_errors=True)
print()
for f in FAIL:
    print("  FAIL", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

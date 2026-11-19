"""
Route option labels, the rule's side (branch claude/route-option-labels, 17 Nov 2026; John: "Yes, as recommended" to Q1
to Q8 of notes/route-option-labels-mockup-1117). While a route is open on Data -> Routes the map prints one short label
on each stored line of the card's lorry. The RULE writes the label (route_best.line_labels -> route["lines"]); the page
prints it and works nothing out. The page's side is ui_fix_route_option_labels.js.

WHAT IS ASSERTED (every check marked ⭐ fails on the code before this branch: the rule had no `lines`):
  1. the line in use reads "In use" + its round-trip time; a quicker option "N min quicker" and a slower one "N min
     longer", to the nearest half minute (route_best.half_min), from R050's figures on live (16 Nov);
  2. Q3: "similar" wherever the rule's time head is "same", also where the why prints the half-minute difference
     (R014: "for 2.5 min longer a round trip" and "similar" on the line);
  3. "ruled out" for an option the rule rules out, whatever its time;
  4. Q4: a busy-hours road in use reads "busy hours", not its time (R013's figures);
  5. a dated diversion in use: the diversion is the entry "In use" with its own option numbers, and option 0 is
     "Main route" (never "The main route": a label is 4 words at most);
  6. a stored line the rule does not judge reads "not compared" (a way round not in use; a line on the way back only);
  7. where the minutes round to nothing but a lorry fits a different number of trips a day, the trips are said;
  8. a route with no other option has the one entry;
  9. every label is 4 words or fewer with the option's name as one, 5 pieces at most, and one of seven states;
 10. evaluate() carries `lines` on every answer (the table, the card's read, a Make primary's reply), and the words sit
     in the rule's file beside its sentences.

WHAT THIS DOES NOT PROVE: live's lines (the figures are typed through the rule's own functions, as
test_best_option_1117.py does); the map (ui_fix_route_option_labels.js; a real browser for where a label sits).

Run:  python backend/tests/test_route_option_labels.py
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

TMP = tempfile.mkdtemp(prefix="wayscope_labels_")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import portable  # noqa: E402,F401
import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import collisions  # noqa: E402
import route_best as RB  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  -> {str(extra)[:400]}")


HAS = hasattr(RB, "line_labels")
L = "Artic Tipper (44t)"


class Fake:
    lims = [1]
    community_all = True
    period = collisions.period_words([2021, 2025])


def M(col_, goods, lt, meets, beside, places, km, drive, cyc_min, trips, co2, back=None):
    return {"collisions": col_, "goods": goods, "left_turns": lt, "cycle_meets": meets, "cycle_beside_km": beside,
            "places": places, "km": km, "drive_min": drive, "cycle_min": cyc_min, "trips": trips, "co2_kg": co2,
            "busy_min": {h: None for h in RB.BUSY_HOURS}, "shown": {}, "return_alt": back}


def stored(*alts, extra=()):
    """The route's stored lines for the lorry: both legs of each option number, plus any (leg, alt) in `extra`."""
    d = {}
    for a in alts:
        d[(L, "loaded", a)] = [[0, 0], [1, 1]]
        d[(L, "return", a)] = [[1, 1], [0, 0]]
    for leg, a in extra:
        d[(L, leg, a)] = [[0, 0], [1, 1]]
    d[("Rigid 8-wheeler (32t)", "loaded", 7)] = [[0, 0], [1, 1]]     # another lorry's line: never in the card's lines
    return d


def demo(use, alts, use_pair=(0, 0), lines=None, ruled=None, busy=None):
    """Typed figures through the rule's own option_entry, _answer and line_labels. ruled: {alt: [reasons]}."""
    use = dict(use, busy_at={h: None for h in RB.BUSY_HOURS})
    out = {"options": [RB.option_entry(a, dict(m, return_alt=(m.get("return_alt") if m.get("return_alt") is not None else a)),
                                       use, Fake, "current", (ruled or {}).get(a, ()))
                       for a, m in alts],
           "answer": RB.KEEP, "option": None, "trade": None, "why": None, "held_back": None, "sentences": [],
           "busy_roads": busy or []}
    RB._answer(out, use, Fake, "current")
    if lines is None:
        lines = stored(*sorted({use_pair[0], use_pair[1]} | {a for a, _ in alts}))
    out["lines"] = RB.line_labels(out, lines, L, use, use_pair) if HAS else []
    return out


def said(out):
    return [f"{x['name']} · {x['words']}" for x in out["lines"]]


# 1. R050 as live read it on 16 Nov (notes route-best-live-1116): in use 104 min, Alt 1 100.5, Alt 2 106.8
R050 = demo(M(39, 4, 10, 6, 0.24, 7, 66.65, 70.0, 104.0, 5, 57.7),
            [(1, M(39, 1, 9, 4, 0.17, 2, 64.71, 66.5, 100.5, 5, 56.0)),
             (2, M(36, 3, 14, 6, 1.94, 5, 67.6, 72.8, 106.8, 5, 58.5))])
ok("⭐ 1. R050: 'In use · 104 min', 'Alt 1 · 3.5 min quicker', 'Alt 2 · 3 min longer', the line in use first",
   said(R050) == ["In use · 104 min", "Alt 1 · 3.5 min quicker", "Alt 2 · 3 min longer"], said(R050))
ok("⭐ 1. each entry carries its option numbers (way out, way back) and a state",
   [(x["alt"], x["return_alt"], x["state"]) for x in R050["lines"]] == [(0, 0, "in_use"), (1, 1, "quicker"), (2, 2, "longer")],
   R050["lines"])
ok("1. the map and the card agree: the suggested option's why opens with the same half minutes",
   R050["answer"] == RB.SUGGESTED and R050["why"].startswith("3.5 min quicker a round trip"), R050["why"])

# 2. R014: 2.4 min longer on 80.3 min of driving is inside the rule's allowance (3 %): the time head is "same"
R014 = demo(M(49, 3, 21, 24, 12.6, 6, 71.9, 80.3, 114.3, 4, 53.4),
            [(1, M(53, 3, 16, 24, 12.56, 6, 72.47, 82.7, 116.7, 4, 45.2))])
ok("⭐ 2. Q3: R014's Alt 1 reads 'similar' on its line (the time head is 'same') while the why says 'for 2.5 min longer'",
   said(R014) == ["In use · 114.3 min", "Alt 1 · similar"] and R014["options"][0]["head_words"]["time"] == "same"
   and "for 2.5 min longer a round trip" in (R014["why"] or ""), (said(R014), R014["why"]))

# 3. ruled out, whatever its time (R021: Alt 1 is quicker and ruled out by the limit it adds)
R021 = demo(M(7, 0, 9, 7, 6.24, 2, 33.41, 44.7, 83.7, 6, 32.3),
            [(1, M(3, 0, 9, 2, 4.28, 0, 29.88, 43.0, 82.0, 6, 28.3)), (2, M(3, 0, 7, 2, 6.66, 0, 33.82, 46.2, 85.2, 6, 32.1))],
            ruled={1: ["it adds a 7.5 t limit, except for access, on an unnamed road (both legs)"],
                   2: ["it adds a 7.5 t limit, except for access, on an unnamed road (both legs)"]})
ok("⭐ 3. an option the rule rules out reads 'ruled out'", said(R021) == ["In use · 83.7 min", "Alt 1 · ruled out", "Alt 2 · ruled out"]
   and [x["state"] for x in R021["lines"]] == ["in_use", "ruled_out", "ruled_out"], said(R021))

# 4. R013: Alt 2 is in use in the evening busy hours; both alternatives are inside the time allowance
R013 = demo(M(51, 2, 16, 26, 9.9, 6, 80.29, 88.5, 127.5, 4, 54.7),
            [(1, M(62, 4, 14, 25, 9.29, 4, 89.6, 90.4, 129.4, 4, 60.5)), (2, M(25, 0, 21, 23, 10.93, 4, 71.18, 86.8, 125.8, 4, 48.4))],
            busy=[{"hour": "17:00", "pair": [2, 2], "label": "Alt 2"}])
ok("⭐ 4. Q4: a busy-hours road in use reads 'busy hours', not its time; the other alternative its own words",
   said(R013) == ["In use · 127.5 min", "Alt 1 · similar", "Alt 2 · busy hours"] and R013["lines"][2]["state"] == "busy", said(R013))
ok("4. a busy-hours road that is ALSO the line in use all day is the line in use, said once",
   said(demo(M(51, 2, 16, 26, 9.9, 6, 80.29, 88.5, 127.5, 4, 54.7), [], busy=[{"hour": "17:00", "pair": [0, 0], "label": "x"}]))
   == ["In use · 127.5 min"])

# 5. R027: Alt 2 is the line in use as a dated diversion; the main route and Alt 1 cross the closed area
ZONE = "it crosses A47 at the new Tilton junction, closed until 17 Dec 2027 (both legs)"
R027 = demo(M(101, 10, 14, 36, 14.9, 8, 92.21, 106.7, 147.7, 3, 62.8),
            [(0, M(151, 12, 12, 41, 19.13, 9, 73.6, 88.0, 129.0, 4, 53.5)), (1, M(196, 11, 15, 43, 19.83, 14, 82.68, 104.2, 145.1, 3, 56.3))],
            use_pair=(2, 2), ruled={0: [ZONE], 1: [ZONE]})
ok("⭐ 5. a diversion in use: 'In use · 147.7 min' on the diversion's own lines, 'Main route · ruled out', 'Alt 1 · ruled out'",
   said(R027) == ["In use · 147.7 min", "Main route · ruled out", "Alt 1 · ruled out"]
   and (R027["lines"][0]["alt"], R027["lines"][0]["return_alt"]) == (2, 2) and R027["lines"][1]["alt"] == 0, said(R027))
ok("⭐ 5. the main route's name on a line has no article (the rule's label() keeps 'The main route' for its sentences)",
   HAS and RB.line_name(0) == "Main route" and RB.label(0) == "The main route" and RB.line_name(2) == "Alt 2"
   and RB.line_name(10) == "Way round")
SPLIT = demo(M(10, 0, 5, 5, 1.0, 2, 30.0, 40.0, 80.0, 6, 30.0), [(0, M(10, 0, 5, 5, 1.0, 2, 30.0, 40.0, 80.0, 6, 30.0))],
             use_pair=(2, 0), lines=stored(0, extra=[("loaded", 2)]))
ok("5. a diversion on the way out only: the line in use is option 2 out and option 0 back, said once",
   [(x["name"], x["alt"], x["return_alt"]) for x in SPLIT["lines"]] == [("In use", 2, 0), ("Main route", 0, 0)], SPLIT["lines"])

# 6. not compared: a way round that is not in use, and a line stored on the way back only
NC = demo(M(39, 4, 10, 6, 0.24, 7, 66.65, 70.0, 104.0, 5, 57.7), [(1, M(39, 1, 9, 4, 0.17, 2, 64.71, 66.5, 100.5, 5, 56.0))],
          lines=stored(0, 1, 10, extra=[("return", 3)]))
ok("⭐ 6. a stored line the rule does not judge reads 'not compared': 'Way round · not compared', and a way back of its own",
   said(NC) == ["In use · 104 min", "Alt 1 · 3.5 min quicker", "Way round · not compared", "Alt 3 · not compared"]
   and (NC["lines"][2]["alt"], NC["lines"][2]["return_alt"]) == (10, 10)
   and (NC["lines"][3]["alt"], NC["lines"][3]["return_alt"]) == (None, 3), NC["lines"])
ok("6. another lorry's stored line is never in the card's lines", all(x["alt"] != 7 for x in NC["lines"]))

# 7. the minutes round to nothing, the trips differ
TR = demo(M(10, 0, 5, 5, 1.0, 2, 30.0, 40.0, 100.0, 5, 30.0), [(1, M(10, 0, 5, 5, 1.0, 2, 30.0, 40.0, 100.2, 4, 30.0)),
                                                                (2, M(10, 0, 5, 5, 1.0, 2, 30.0, 40.0, 99.8, 7, 30.0))])
ok("⭐ 7. where the minutes round to nothing but the trips a day differ, the trips are said ('1 trip fewer', '2 trips more')",
   said(TR) == ["In use · 100 min", "Alt 1 · 1 trip fewer", "Alt 2 · 2 trips more"], said(TR))

# 8. no other option
ONE = demo(M(10, 0, 5, 5, 1.0, 2, 30.0, 40.0, 96.0, 5, 30.0), [])
ok("⭐ 8. a route with no other option has the one entry, the line in use", said(ONE) == ["In use · 96 min"], said(ONE))

# 9. every label drawn above: 4 words or fewer with the name as one, 5 pieces at most, a known state
ALL = [x for o in (R050, R014, R021, R013, R027, SPLIT, NC, TR, ONE) for x in o["lines"]]
STATES = {"in_use", "quicker", "longer", "similar", "ruled_out", "busy", "not_compared"}
ok("⭐ 9. every label is 4 words or fewer with the option's name as one (5 pieces at most), and one of seven states",
   len(ALL) >= 20 and all(1 + len(x["words"].split()) <= 4 and len(x["name"].split()) + len(x["words"].split()) <= 5
                          and x["state"] in STATES for x in ALL),
   [x for x in ALL if 1 + len(x["words"].split()) > 4 or x["state"] not in STATES])
ok("9. no label says 'same', 'slower', 'not counted' or a supplier's word (the card's chip words are its own)",
   not any(w in f"{x['name']} {x['words']}".lower() for x in ALL for w in ("same", "slower", "not counted", "here", "osm")))

# 9b. the LONGEST a label can be (the mother session's rule of 17 Nov: a sentence the rule writes is checked at its
# longest before a screen is called done): three options, one ruled out, two ways round, a diversion in use, a
# three-figure half-minute difference and a four-figure round trip
LONG = demo(M(10, 0, 5, 5, 1.0, 2, 200.0, 300.0, 1447.7, 1, 30.0),
            [(0, M(10, 0, 5, 5, 1.0, 2, 200.0, 300.0, 1335.2, 1, 30.0)), (1, M(10, 0, 5, 5, 1.0, 2, 200.0, 300.0, 1560.4, 1, 30.0)),
             (3, M(10, 0, 5, 5, 1.0, 2, 200.0, 300.0, 1447.9, 1, 30.0))],
            use_pair=(2, 2), lines=stored(0, 1, 2, 3, 10, 11), ruled={3: [ZONE]})
ok("⭐ 9b. the longest labels: 'Main route · 112.5 min quicker' (30 letters), 'Way round 2 · not compared', a four-figure 'In use'",
   said(LONG) == ["In use · 1447.7 min", "Main route · 112.5 min quicker", "Alt 1 · 112.5 min longer", "Alt 3 · ruled out",
                  "Way round · not compared", "Way round 2 · not compared"], said(LONG))
ok("⭐ 9b. at its longest a label is 30 letters, 4 words with the name as one, 5 pieces",
   max(len(x) for x in said(LONG)) == 30 and all(1 + len(x["words"].split()) <= 4 and len(x["name"].split()) + len(x["words"].split()) <= 5
                                                  for x in LONG["lines"]), max(len(x) for x in said(LONG)) if HAS else "")

# 10. source: evaluate carries the lines; the words sit in the rule's file
SRC = open(os.path.join(BACKEND, "route_best.py"), encoding="utf-8").read()
EV = SRC.split("def evaluate(rid, ctx):")[1].split("\ndef ")[0]
ok("⭐ 10. evaluate() gives every answer its `lines` (an early answer an empty list), after the answer is decided",
   '"lines": []' in EV and EV.index("_answer(out, use, ctx, hist)") < EV.index('out["lines"] = line_labels(out, lines, lorry, use, use_pair)'))
ok("⭐ 10. the time difference on a line is half_min's and 'similar' is the time head's 'same' (nothing new is worked out)",
   HAS and 'o["heads"]["time"] == 0' in SRC.split("def line_words(")[1].split("\ndef ")[0]
   and 'half_min(use["cycle_min"], o["counts"]["cycle_min"])' in SRC.split("def line_words(")[1].split("\ndef ")[0])

__import__("shutil").rmtree(TMP, ignore_errors=True)
print()
for f in FAIL:
    print("  FAIL", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

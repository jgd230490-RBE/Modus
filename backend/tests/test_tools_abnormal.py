"""
test_tools_abnormal.py — the abnormal load adviser's free check (claude/tools-abnormal-adviser, 17 Nov 2026). No FastAPI
needed: backend/tools_abnormal.py, the page frontend/tools/abnormal-load.html and its script. The real app's side (the
open call, its limit, the trap, nothing stored) is smoke_tools_abnormal.py.

    python backend/tests/test_tools_abnormal.py

What it pins:
  1. card 3's worked example word for word (notes/tools-first-opening-mockup-1116, card 3);
  2. for a spread of loads, the public answer's class, dates and yes / no facts equal abnormal_rules.advice's own (the
     page may say less, never something different);
  3. the rules are called with the person's nation, the SHIPPED bank holidays, no police time bans and London's today;
     England and Wales against Scotland (the same under STGO, as the rules count every GB holiday; different only on the
     C&U calendar, which this form never reaches);
  4. every refusal sentence;
  5. nothing of an organisation read, nothing written (source pins);
  6. the page's words against card 3, and no statute reference, supplier or banned word in any answer.
"""
import ast
import datetime
import itertools
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

import abnormal_rules as R  # noqa: E402
import tools_abnormal as T  # noqa: E402
import tools_public  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  {extra}"[:700])


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


TODAY = datetime.date(2026, 11, 17)
WORKED = dict(width_m=4.2, length_m=27.0, height_m=4.6, gross_t=76, max_axle_t=11, axle_count=7, date="2026-12-10",
              band="day", where="england-and-wales", indivisible=True)


def W(**kw):
    d = dict(WORKED)
    d.update(kw)
    return d


def refused(body, today=TODAY):
    try:
        T.answer(body, today=today)
        return None
    except T.Bad as e:
        return e.say


# =========================================================================== #
#  1. card 3, word for word                                                    #
# =========================================================================== #
CARD3 = {
    "head": "STGO Category 2",
    "chips": [["warn", "Notify by Mon 7 Dec 2026"]],
    "over_line": "Over the normal limits: 76 t gross (44 t), 11 t on an axle (10 t), 4.2 m wide (2.9 m).",
    "rows": [
        ["Police", "2 clear working days' notice to every force on the route. Receive by 7 Dec."],
        ["Road and bridge authorities", "2 clear days' notice with an indemnity, to every authority on the route. Receive by 7 Dec."],
        ["Network Rail", "If the route crosses one of its bridges: 2 clear working days' notice with an indemnity."],
        ["Attendant", "Required: over 3.5 m wide and over 25.9 m long."],
        ["Markers", "Lit marker plates front and back (over 18.3 m long). Voluntary."],
        ["Speeds", "40 mph motorway, 35 dual carriageway, 30 other roads."],
        ["Escort", "Expected on roads other than motorways (over 4.1 m wide). The police decide."],
        ["Height", "Over 3 m: the travelling height is shown in the cab."],
    ],
    "fine": ["Axle spacings not typed: the limits for closely spaced axles are not tested."],
    "next": ["More than one load?", "Keep each load and its notices in one plan."],
    "last": ("Advice from the typed figures, not permission. The haulier, ESDAL, the police and the road and bridge "
             "authorities decide. Bridges and structures are not checked here."),
}
# Q2 (17 Nov, the session's recommendation; John's yes OUTSTANDING): the built last line adds "overhangs" (the form asks
# none); card 3's own line is kept above as drawn and the built one is card 3's with that one word added
BUILT_LAST = CARD3["last"].replace("Bridges and structures are", "Bridges, structures and overhangs are")
P = T.answer(WORKED, today=TODAY)["page"]
ok("⭐ card 3: the class", P["head"] == CARD3["head"], P["head"])
ok("⭐ card 3: the chip", P["chips"] == CARD3["chips"], str(P["chips"]))
ok("⭐ card 3: the over-the-limits line", "Over the normal limits: " + ", ".join(P["over"]) + "." == CARD3["over_line"], str(P["over"]))
ok("⭐ card 3: no note above the rows", P["notes"] == [], str(P["notes"]))
ok("⭐ card 3: the eight rows, word for word and in order", P["rows"] == CARD3["rows"], str(P["rows"]))
for i, (k, v) in enumerate(CARD3["rows"]):
    ok(f"card 3 row {i + 1} {k}", i < len(P["rows"]) and P["rows"][i] == [k, v], str(P["rows"][i:i + 1]))
ok("⭐ card 3: the spacing line", P["fine"] == CARD3["fine"], str(P["fine"]))
ok("⭐ card 3: the next strip", P["next"] == CARD3["next"])
ok("⭐ card 3: the last line, with Q2's 'overhangs' and nothing else changed",
   P["last"] == BUILT_LAST == T.LAST_LINE and BUILT_LAST != CARD3["last"], P["last"])
# the drawing's notes file, where this laptop has it (not in git; CI skips this one check)
_card = Path(r"C:\Users\Laptop\Wayscope\notes\tools-first-opening-mockup-1116\index.html")
if _card.is_file():
    _c = _card.read_text(encoding="utf-8")
    _c3 = _c[_c.find("3 ABNORMAL LOADS"):_c.find("4 ROUTE CHECK")]
    for k, v in CARD3["rows"]:
        ok(f"card 3 in the notes holds the row {k} as pinned", f"<li><b>{k}</b><span>{v}</span></li>" in _c3)
    ok("card 3 in the notes holds the class, chip, over line, spacing and last lines as pinned",
       CARD3["head"] in _c3 and "Notify by Mon 7 Dec 2026" in _c3 and CARD3["over_line"] in _c3
       and CARD3["fine"][0] in _c3 and CARD3["last"] in _c3)

# =========================================================================== #
#  2. a spread of loads: the page says less, never something different         #
# =========================================================================== #
DAY = {"Mon": 0}


def iso_of_short(s, year_hint):
    """'7 Dec' -> a date in the move's year or the one before."""
    d = datetime.datetime.strptime(f"{s} {year_hint}", "%d %b %Y").date()
    return d


def chip_date(words):
    m = re.search(r"by \w{3} (\d{1,2} \w{3} \d{4})", words)
    return datetime.datetime.strptime(m.group(1), "%d %b %Y").date().isoformat() if m else None


SPREAD = []
for w, ln, h, gross, n, date in itertools.product(
        (2.5, 2.95, 3.2, 4.2, 4.7, 5.5, 6.5), (16, 22, 27, 31), (4.0, 5.2, 6.2),
        (40, 46, 48, 60, 76, 100, 130, 160), (5, 6, 9, 12), ("2026-11-18", "2026-12-02", "2026-12-10", "2027-03-04")):
    axle = round(max(gross / n * 1.25, 8.0), 2)
    SPREAD.append(dict(width_m=w, length_m=ln, height_m=h, gross_t=gross, max_axle_t=axle, axle_count=n, date=date,
                       band="day", where="england-and-wales", indivisible=True))
SPREAD += [W(indivisible=False), W(axle_spacings_m="0.9, 1.36, 1.36, 1.36, 1.36, 1.36"),
           W(axle_spacings_m="1.2,1.2,1.2,1.2,1.2,1.2"), W(gross_t=60, max_axle_t=12, axle_count=5),
           W(width_m=2.5, length_m=16.5, height_m=4.0, gross_t=40, max_axle_t=9, axle_count=5),
           W(width_m=2.5, length_m=16.5, height_m=2.8, gross_t=40, max_axle_t=9, axle_count=5),
           # 17 Nov: long combinations within the normal weights and width (the rules: not abnormal, yet a police notice)
           W(width_m=2.5, length_m=28, height_m=4.0, gross_t=40, max_axle_t=9, axle_count=5, date="2026-12-10"),
           W(width_m=2.5, length_m=26.5, height_m=4.0, gross_t=40, max_axle_t=9, axle_count=5, date="2026-11-18"),
           W(width_m=2.5, length_m=20, height_m=4.0, gross_t=40, max_axle_t=9, axle_count=5)]
# 17 Nov, Q6 and Q7 (John's yes): the ordinary-lorry tick and the driving-axle tick, on a spread that reaches C&U (within
# 44 t and 4.3 m) and the C&U ceilings, each date
for w, ln, gross, axle, n, date in itertools.product(
        (2.5, 2.95, 3.2, 4.2, 4.5), (12, 19, 24, 28), (30, 40, 44, 46, 60), (8, 10.5, 11.5), (4, 5, 6),
        ("2026-11-18", "2026-12-01", "2027-03-30")):
    for cu, dr in ((True, False), (False, True), (True, True)):
        SPREAD.append(W(width_m=w, length_m=ln, height_m=4.0, gross_t=gross, max_axle_t=axle, axle_count=n, date=date,
                        cu_vehicle=cu, axle_driving=dr))

checked = 0
problems = []
seen_heads, seen_shapes = set(), set()
seen_ticked_but = 0
for body in SPREAD:
    try:
        r = T.answer(body, today=TODAY)
    except T.Bad as e:
        problems.append(("refused", body, e.say))
        continue
    a, p = r["advice"], r["page"]
    checked += 1
    rows = dict(p["rows"])
    nt = a["notices"]
    seen_heads.add(p["head"])
    seen_ticked_but += any(n.startswith("Ticked as an ordinary lorry, but ") for n in p["notes"])
    seen_shapes.add((a["abnormal"], a["category"], a["permission"], bool(nt["police_days"]), nt["rba_days"],
                     a["attendant"], a["escort_expected"], len(a["height"])))
    errs = []
    if not a["abnormal"] and a["permission"] == "none" and not nt["rba_days"]:
        # narrowed 17 Nov: a "not abnormal" load may still need what the rules give (a long combination): the page must
        # show each of those rows, and only those; before, it hid them
        if p["head"] != "Not an abnormal load" or p["over"]:
            errs.append("not abnormal")
        if [c[1] for c in p["chips"]] != ([f"Notify by {T._day(a['notify_by'])}"
                                           + (": passed" if any(f["code"] == "NOTICE_LATE" for f in a["flags"]) else "")]
                                          if a["notify_by"] else []):
            errs.append("not abnormal: notify chip")
        if bool(nt["police_days"]) != ("Police" in rows) or nt["rba_days"]:
            errs.append("not abnormal: police")
        if bool(a["attendant"]) != ("Attendant" in rows):
            errs.append("not abnormal: attendant")
        if bool(a["markers"]) != ("Markers" in rows):
            errs.append("not abnormal: markers")
        if (a["escort_expected"] != "none") != ("Escort" in rows):
            errs.append("not abnormal: escort")
        if bool(a["height"]) != ("Height" in rows):
            errs.append("height on a normal load")
    else:
        want = T.CU_HEAD if a["regime"] == "cu" else (T.CLASS_WORDS.get(a["category"]) or "No STGO category fits")
        if p["head"] != want:
            errs.append("head")
        if len(p["over"]) != len(a["reasons"]):
            errs.append("over count")
        cd = [chip_date(c[1]) for c in p["chips"]]
        if a["notify_by"] and a["notify_by"] not in cd:
            errs.append("notify chip")
        if not a["notify_by"] and any(c[1].startswith("Notify") for c in p["chips"]):
            errs.append("notify chip with no date")
        if a["apply_by"] and a["apply_by"] not in cd:
            errs.append("apply chip")
        late = any(f["code"] == "NOTICE_LATE" for f in a["flags"])
        if late != any(c[1].startswith("Notify") and c[1].endswith("passed") for c in p["chips"]):
            errs.append("late chip")
        pol = rows.get("Police", "")
        if nt["police_days"]:
            if not pol.startswith(f"{nt['police_days']} clear working days"):
                errs.append("police days")
            if nt["police_by"]:
                d = R._date(nt["police_by"])
                if f"Receive by {d.day} {d:%b}." not in pol:
                    errs.append("police date")
        elif pol != "No notice from these figures.":
            errs.append("police none")
        rba = rows.get("Road and bridge authorities", "")
        if nt["rba_days"]:
            if not rba.startswith(f"{nt['rba_days']} clear days' notice with an indemnity"):
                errs.append("rba days")
            d = R._date(nt["rba_by"])
            if nt["rba_by"] and f"Receive by {d.day} {d:%b}." not in rba:
                errs.append("rba date")
            nr = R.NR_DAYS_OVER_80 if a["notices"]["rba_days"] and (body["gross_t"] > R.RBA_WEIGHT_STEP_T) else R.NR_DAYS_UP_TO_80
            if f"{nr} clear working days" not in rows.get("Network Rail", ""):
                errs.append("network rail")
        elif rba != "No notice from these figures.":
            errs.append("rba none")
        att = rows.get("Attendant", "")
        if a["attendant"] != att.startswith("Required:") or (a["attendant"] and att.count(" over ") + att.count("overhang")
                                                                 < len(a["attendant_reasons"])):
            errs.append("attendant")
        sp = a["speeds_mph"]
        if a["regime"] == "cu":
            if "Speeds" in rows:
                errs.append("speeds on a C&U move")
        elif sp and rows.get("Speeds") != f"{sp[0]} mph motorway, {sp[1]} dual carriageway, {sp[2]} other roads.":
            errs.append("speeds")
        if not sp and "mph" in rows.get("Speeds", ""):
            errs.append("speeds none")
        esc = rows.get("Escort", "")
        where = {"all_roads": "on every road", "other_roads": "on roads other than motorways", "motorways": "on motorways",
                 "none": "Not expected"}[a["escort_expected"]]
        if where not in esc:
            errs.append("escort")
        hgt = rows.get("Height", "")
        for hl in a["height"]:
            lim = re.match(r"over ([\d.]+) m", hl).group(1)
            if f"Over {lim} m" not in hgt:
                errs.append("height " + lim)
        if not a["height"] and not hgt.endswith("nothing for the height."):
            errs.append("height none")
        if bool(a["markers"]) == (rows.get("Markers") == "None from these figures."):
            errs.append("markers")
        if (a["permission"] == "special_order") != ("Special Order" in rows):
            errs.append("SO row")
        if (a["permission"] == "vr1") != ("VR1" in rows):
            errs.append("VR1 row")
        spaced = any("not tested: type the axle spacings" in n for n in a["notes"])
        if spaced != (T.SPACINGS_NOT_TYPED in p["fine"]):
            errs.append("spacing line")
        if any(n.startswith("not declared indivisible") for n in a["notes"]) != any(n.startswith("Not ticked") for n in p["notes"]):
            errs.append("indivisible")
    # Q8, every load: the C&U calendar line exactly when the rules give a C&U date; the "ticked, but" sentence exactly when
    # the rules say the tick is set but STGO applies, and first
    if (a["regime"] == "cu" and bool(a["notify_by"])) != (T.CU_SATURDAY in p["fine"]):
        errs.append("saturday line")
    _rn = any(n.startswith("The C&U tick is set") for n in a["notes"])
    if _rn != bool(p["notes"] and p["notes"][0].startswith("Ticked as an ordinary lorry, but ")):
        errs.append("ticked-but sentence")
    if errs:
        problems.append(("differs", body, errs))
ok(f"⭐ the spread: {checked} loads answered, each page equal in class, dates and facts to the rules' own",
   checked > 300 and not [x for x in problems if x[0] == "differs"], str([x for x in problems if x[0] == "differs"][:4]))
ok("the spread's refusals are only the impossible ones (heaviest axle times axles under the gross)",
   all(x[2] == T.SAY["axles_short"] for x in problems if x[0] == "refused"), str([x for x in problems if x[0] == "refused"][:3]))
ok("the spread reaches every class the rules give (normal, Categories 1 to 3, none fits, Special Order)",
   {"Not an abnormal load", "STGO Category 1", "STGO Category 2", "STGO Category 3", "No STGO category fits",
    "Special Order"} <= seen_heads, str(seen_heads))
ok("⭐ the spread reaches C&U answers, both abnormal and not, and the 'ticked, but STGO' answer",
   {"Moves under C&U, not STGO"} <= seen_heads and any(not s[0] and s[3] for s in seen_shapes)
   and seen_ticked_but > 0, str(seen_heads))
ok("⭐🔴 the spread reaches a load the rules call not abnormal that still needs a police notice (and the page shows it)",
   any(not s[0] and s[3] for s in seen_shapes), str([s for s in seen_shapes if not s[0]][:6]))
_long = T.answer(W(width_m=2.5, length_m=28, height_m=4.0, gross_t=40, max_axle_t=9, axle_count=5, date="2026-12-10"),
                 today=TODAY)["page"]
ok("⭐🔴 2.5 m wide, 28 m long, 40 t: 'Not an abnormal load', and yet the police notice, attendant and marker plates shown",
   _long["head"] == "Not an abnormal load" and _long["chips"] == [["warn", "Notify by Mon 7 Dec 2026"]]
   and [k for k, _ in _long["rows"]] == ["Police", "Attendant", "Markers", "Height"]
   and _long["rows"][0][1] == "2 clear working days' notice to every force on the route. Receive by 7 Dec.", str(_long))
_so31 = T.answer(W(width_m=2.5, length_m=31, height_m=4.0, gross_t=40, max_axle_t=9, axle_count=5, date="2027-03-04"),
                 today=TODAY)["page"]
ok("⭐🔴 2.5 m wide, 31 m long, 40 t (not abnormal to the rules, a Special Order case): the Special Order answer, never "
   "'Not an abnormal load'", _so31["head"] == "Special Order" and _so31["rows"][0][0] == "Special Order", str(_so31)[:300])
ok("the spread reaches VR1, Special Order, both escort kinds and the late notice",
   any(s[2] == "vr1" for s in seen_shapes) and any(s[2] == "special_order" for s in seen_shapes)
   and any(s[6] == "all_roads" for s in seen_shapes) and any(s[6] == "other_roads" for s in seen_shapes))

# the page's words: no statute reference, no supplier, no staff note, no banned word, no raw ISO date
_tl = read("backend/tests/test_landing.py")
_m = re.search(r"\nBANNED = (\[.*?\n\])\n", _tl, re.S)
LANDING_BANNED = ast.literal_eval(_m.group(1)) if _m else []
_ar = read("backend/abnormal_route.py")
_m = re.search(r"SCREEN_BAN = re\.compile\((.*?)\)\n", _ar, re.S)
SCREEN_BAN = re.compile("".join(ast.literal_eval("(" + _m.group(1) + ",)")))
EXTRA = [r"\btruck", r"\bsafer\b", r"\bcompliant\b", r"\bbest\b", r"\bDEMO\b", r"Fictional scheme", r"sign in", r"credits?\b",
         r"\bVAT\b", r"Street View", r"guarantee", r"approved by", r"certified", r"endorsed", r"\bserver\b", r"endpoint",
         r"\bAPI\b", r"\btoken\b", r"\bcached\b", r"\bJSON\b", r"\bHTTP\b"]
STATUTE = re.compile(r"\bSch\b|\bart \d|\breg \d|\bpara\b|\bparas\b|NH code|code of practice|aide memoire|C&U|\bBE16\b|NPCC|"
                     r"\d{4}-\d{2}-\d{2}|No escort is planned|\(STGO\)")
texts = set()
for body in SPREAD[::7] + [W(indivisible=False), W(date="2026-11-18"), W(width_m=6.5, length_m=20, gross_t=60, max_axle_t=11, axle_count=8),
                           W(width_m=2.5, length_m=16.5, height_m=4.0, gross_t=40, max_axle_t=9, axle_count=5)]:
    try:
        p = T.answer(body, today=TODAY)["page"]
    except T.Bad:
        continue
    texts |= {p["head"], p["last"], *p["over"], *p["notes"], *p["fine"], *p["next"], *[c[1] for c in p["chips"]],
              *[x for r in p["rows"] for x in r]}
alltext = "\n".join(sorted(texts))
_hits = [n for pat, n in LANDING_BANNED if re.search(pat, alltext, re.I)] + [x for x in EXTRA if re.search(x, alltext, re.I)]
ok(f"🔴 no banned word in any answer ({len(texts)} distinct pieces)", not _hits, str(_hits))
ok("🔴 no supplier or back-end name in any answer", not SCREEN_BAN.search(alltext), str(SCREEN_BAN.findall(alltext)[:5]))
# narrowed 17 Nov (Q8, John's yes): "C&U" may appear in the one approved head and nowhere else
ok("Q8: 'C&U' appears only as the approved head", all("C&U" not in t or t == T.CU_HEAD for t in texts)
   and T.CU_HEAD == "Moves under C&U, not STGO" and T.CU_HEAD in texts)
alltext = "\n".join(sorted(t for t in texts if t != T.CU_HEAD))
ok("🔴 no statute reference, code-of-practice name, raw date or staff note in any answer", not STATUTE.search(alltext),
   str(STATUTE.findall(alltext)[:6]))
ok("🔴 'lorry' never 'truck'; and the answer never says permitted or meets the rules",
   not re.search(r"\bpermitted\b|meets the rules|\bcompliant\b", alltext, re.I))

# =========================================================================== #
#  3. what the rules are called with                                           #
# =========================================================================== #
_calls = []
_real_advice = R.advice


def _spy(*a, **kw):
    _calls.append(kw)
    return _real_advice(*a, **kw)


R.advice = _spy
try:
    T.answer(W(where="scotland", band="night"), today=TODAY)
finally:
    R.advice = _real_advice
kw = _calls[0] if _calls else {}
ok("⭐ the rules get the nation the person picked", kw.get("nation") == "scotland", str(kw.get("nation")))
ok("⭐ ...the SHIPPED bank holidays (backend/data/bank_holidays.json), not an organisation's copy",
   kw.get("holidays_feed") is T.holidays_feed() and T.HOLIDAYS_FILE.replace("\\", "/").endswith("backend/data/bank_holidays.json"))
ok("⭐ ...no police time bans, the time band picked, and today", kw.get("time_bans") is None and kw.get("time_band") == "night"
   and kw.get("today") == TODAY and kw.get("date_from") == "2026-12-10" and kw.get("date_to") is None)
ok("the shipped holidays run to 26 Dec 2028, so the last moving day taken is 31 Dec 2028",
   max(R.holiday_dates(T.holidays_feed(), ("england-and-wales", "scotland"))) == datetime.date(2028, 12, 26)
   and T.last_moving_day() == datetime.date(2028, 12, 31))
_f = T.read_form(W(), today=TODAY)[0]
ok("the form's figures reach the rules as the drawing reads them: overall length, no overhang; unticked: a non-driving axle, no C&U",
   _f["length_m"] == 27.0 and "rigid_length_m" not in _f and _f["axle_driving"] is False and _f["cu_vehicle"] is False
   and _f["indivisible"] is True and _f["axle_spacings_m"] == [])
ok("the tick reaches the rules only when it is really true (a string 'false' is not a tick)",
   T.read_form(W(indivisible="false"), today=TODAY)[0]["indivisible"] is False)
ok("Q6, Q7: the two new ticks reach the rules only when really true",
   T.read_form(W(cu_vehicle=True, axle_driving=True), today=TODAY)[0]["cu_vehicle"] is True
   and T.read_form(W(cu_vehicle=True, axle_driving=True), today=TODAY)[0]["axle_driving"] is True
   and T.read_form(W(cu_vehicle="true", axle_driving=1), today=TODAY)[0]["cu_vehicle"] is False
   and T.read_form(W(cu_vehicle="true", axle_driving=1), today=TODAY)[0]["axle_driving"] is False)

# England and Wales against Scotland: 30 Nov 2026 is St Andrew's Day (Scotland only)
_ew = T.answer(W(date="2026-12-02", where="england-and-wales"), today=TODAY)
_sc = T.answer(W(date="2026-12-02", where="scotland"), today=TODAY)
ok("St Andrew's Day 2026 is a Scottish bank holiday and not an English one in the shipped copy",
   datetime.date(2026, 11, 30) in R.holiday_dates(T.holidays_feed(), ("scotland",))
   and datetime.date(2026, 11, 30) not in R.holiday_dates(T.holidays_feed(), ("england-and-wales",)))
ok("⭐ under STGO the answer is the SAME for both nations (the rules count a holiday anywhere in Great Britain)",
   _ew["page"] == _sc["page"] and _ew["advice"]["notify_by"] == _sc["advice"]["notify_by"] == "2026-11-26")
_cu = dict(width_m=3.2, length_m=16, height_m=4, gross_t=40, max_axle_t=9, axle_count=5, indivisible=True, cu_vehicle=True)
_cu_ew = R.advice(_cu, date_from="2026-12-02", nation="england-and-wales", holidays_feed=T.holidays_feed(), today=TODAY)
_cu_sc = R.advice(_cu, date_from="2026-12-02", nation="scotland", holidays_feed=T.holidays_feed(), today=TODAY)
ok("...while the rules' C&U calendar does differ on that date (29 Nov against 27 Nov)",
   _cu_ew["notify_by"] == "2026-11-29" and _cu_sc["notify_by"] == "2026-11-27" and _ew["advice"]["regime"] == "stgo")
# narrowed 17 Nov (Q6): the form now sends a C&U load, so "Where" moves the page's date for one
_cuw = dict(width_m=3.2, length_m=12, height_m=4.0, gross_t=30, max_axle_t=8, axle_count=4, cu_vehicle=True, date="2026-12-01")
_pew = T.answer(W(**_cuw, where="england-and-wales"), today=TODAY)["page"]
_psc = T.answer(W(**_cuw, where="scotland"), today=TODAY)["page"]
ok("⭐ Q6: on the page, a C&U load moving Tue 1 Dec 2026: England and Wales notify by Fri 27 Nov, Scotland by Thu 26 Nov",
   _pew["chips"] == [["warn", "Notify by Fri 27 Nov 2026"]] and _psc["chips"] == [["warn", "Notify by Thu 26 Nov 2026"]],
   str((_pew["chips"], _psc["chips"])))
ok("by night gives the same answer as by day (no time bans on a public check)",
   T.answer(W(band="night"), today=TODAY)["page"] == P)

# card 17 of notes/tools-abnormal-adviser-mockup-1116 (John's yes, 17 Nov), word for word
def C17(**kw):
    return T.answer(W(height_m=4.0, date="2026-12-01", **kw), today=TODAY)["page"]


_A = C17(width_m=3.2, length_m=12, gross_t=30, max_axle_t=8, axle_count=4, cu_vehicle=True)
ok("⭐ card 17 A (C&U, wide only): the head, the chip, the police row, no road authority notice, no Speeds row, the Saturday line",
   _A["head"] == "Moves under C&U, not STGO" and _A["chips"] == [["warn", "Notify by Fri 27 Nov 2026"]]
   and _A["over"] == ["3.2 m wide (2.9 m)"] and _A["notes"] == []
   and dict(_A["rows"])["Police"] == "2 clear working days' notice to every force on the route. Receive by 27 Nov."
   and dict(_A["rows"])["Road and bridge authorities"] == "No notice from these figures."
   and "Speeds" not in dict(_A["rows"])
   and _A["fine"] == ["For an ordinary lorry a Saturday counts as a working day; Sundays and bank holidays do not."], str(_A))
_A0 = C17(width_m=3.2, length_m=12, gross_t=30, max_axle_t=8, axle_count=4)
ok("card 17 A0: the same load unticked is STGO, notify by Wed 25 Nov", _A0["chips"] == [["warn", "Notify by Wed 25 Nov 2026"]]
   and _A0["head"] == "No STGO category fits")
_B = C17(width_m=2.5, length_m=24, gross_t=30, max_axle_t=8, axle_count=4, cu_vehicle=True)
ok("⭐ card 17 B (C&U, long only): not abnormal, yet the police by 27 Nov, marker plates, the Saturday line",
   _B["head"] == "Not an abnormal load" and _B["chips"] == [["warn", "Notify by Fri 27 Nov 2026"]]
   and [k for k, _ in _B["rows"]] == ["Police", "Markers", "Height"] and T.CU_SATURDAY in _B["fine"], str(_B))
_C = C17(width_m=2.95, length_m=16.5, gross_t=40, max_axle_t=9, axle_count=5, cu_vehicle=True)
ok("card 17 C (C&U, 2.95 m): a police notice, and no STGO speeds although the rules give Category 1 speeds",
   _C["head"] == "Moves under C&U, not STGO" and "Police" in dict(_C["rows"]) and "Speeds" not in dict(_C["rows"])
   and T.answer(W(height_m=4.0, date="2026-12-01", width_m=2.95, length_m=16.5, gross_t=40, max_axle_t=9, axle_count=5,
                  cu_vehicle=True), today=TODAY)["advice"]["speeds_mph"] == [60, 50, 40], str(_C))
for _k, _f, _why in (("D", dict(width_m=4.5, length_m=16, gross_t=40, max_axle_t=9, axle_count=5), "over 4.3 m wide"),
                     ("E", dict(width_m=3.2, length_m=16, gross_t=60, max_axle_t=10, axle_count=6), "over the normal weights"),
                     ("F", dict(width_m=2.5, length_m=28, gross_t=40, max_axle_t=9, axle_count=5), "over 27.4 m long")):
    _p = C17(cu_vehicle=True, **_f)
    ok(f"⭐ card 17 {_k} (ticked, but {_why}): STGO, with the sentence first",
       _p["notes"][:1] == [f"Ticked as an ordinary lorry, but {_why}: it moves under STGO. Check with the haulier."]
       and _p["head"] != "Moves under C&U, not STGO" and T.CU_SATURDAY not in _p["fine"], str(_p))
_G = C17(width_m=2.5, length_m=16.5, gross_t=44, max_axle_t=11, axle_count=5, axle_driving=True)
_G0 = C17(width_m=2.5, length_m=16.5, gross_t=44, max_axle_t=11, axle_count=5)
ok("⭐ card 17 G (an 11 t DRIVING axle, ticked): not abnormal, the limits line naming 11.5 t a driving axle",
   _G["head"] == "Not an abnormal load" and _G["chips"] == [] and _G["notes"][0].startswith(
       "Within the normal limits on these figures: 44 t gross, 10 t an axle (11.5 t a driving axle), 2.9 m wide."), str(_G))
ok("card 17 G0 (the same, unticked): abnormal, no category, a road and bridge notice",
   _G0["head"] == "No STGO category fits" and dict(_G0["rows"])["Road and bridge authorities"].startswith("2 clear days"))

# =========================================================================== #
#  4. the refusals                                                             #
# =========================================================================== #
REF = [
    ("width blank", W(width_m=""), "Type the width in metres."),
    ("width missing", {k: v for k, v in WORKED.items() if k != "width_m"}, "Type the width in metres."),
    ("width words", W(width_m="wide"), "Type the width in metres."),
    ("width true", W(width_m=True), "Type the width in metres."),
    ("length blank", W(length_m=None), "Type the length in metres."),
    ("height blank", W(height_m=""), "Type the height in metres."),
    ("gross blank", W(gross_t=""), "Type the gross weight in tonnes."),
    ("axle blank", W(max_axle_t=""), "Type the heaviest axle in tonnes."),
    ("axles blank", W(axle_count=""), "Type the number of axles: 2 or more."),
    ("axles one", W(axle_count=1), "Type the number of axles: 2 or more."),
    ("axles 2.5", W(axle_count="2.5"), "Type the number of axles: 2 or more."),
    ("axles 500", W(axle_count=500), "Type the number of axles: 2 or more."),
    ("width 40", W(width_m=40), "A width of 0.5 to 12 m, please."),
    ("width 0", W(width_m=0), "A width of 0.5 to 12 m, please."),
    ("width -3", W(width_m=-3), "A width of 0.5 to 12 m, please."),
    ("width nan", W(width_m="nan"), "Type the width in metres."),
    ("length 500", W(length_m=500), "A length of 2 to 120 m, please."),
    ("height 20", W(height_m=20), "A height of 0.5 to 12 m, please."),
    ("gross 5000", W(gross_t=5000), "A gross weight of 1 to 3000 t, please."),
    ("axle 200", W(max_axle_t=200, gross_t=300), "A heaviest axle of 0.5 to 100 t, please."),
    ("axle over gross", W(max_axle_t=20, gross_t=15, axle_count=2), T.SAY["axle_over_gross"]),
    ("axles short", W(axle_count=3), "The heaviest axle times the number of axles is less than the gross weight. Check the figures."),
    ("spacings words", W(axle_spacings_m="a, b"), "Type the axle spacings in metres, with commas between them."),
    ("spacings count", W(axle_spacings_m="1.4,1.4,1.4,1.4,1.4"), "Type one spacing between each pair of axles: 6 for 7 axles."),
    ("spacing 0.1", W(axle_spacings_m="0.1,1.4,1.4,1.4,1.4,1.4"), "Each axle spacing from 0.3 to 30 m, please."),
    ("no date", W(date=""), "Pick the day it moves."),
    ("bad date", W(date="10/12/2026"), "Pick the day it moves."),
    ("date 31 Feb", W(date="2026-02-31"), "Pick the day it moves."),
    ("yesterday", W(date="2026-11-16"), "Pick a moving day from today on."),
    ("2029", W(date="2029-01-04"), "Pick a moving day up to 31 December 2028: the bank holidays held here end then."),
    ("where unknown", W(where="france"), "Pick England and Wales, or Scotland."),
    ("where wales", W(where="wales"), "Pick England and Wales, or Scotland."),
    ("band dusk", W(band="dusk"), "Pick by day or by night."),
    ("not a dict", [], "Type the width in metres."),
]
# Q1: the page sends no "Where" and no band; left out (or blank) they read as England and Wales, by day
_nowb = {k: v for k, v in W().items() if k not in ("where", "band")}
ok("⭐ Q1: no 'Where' and no band sent (another caller): the same answer as England and Wales by day",
   T.answer(_nowb, today=TODAY)["page"] == P and T.answer(W(where=""), today=TODAY)["page"] == P)
for label, body, say in REF:
    got = refused(body)
    ok(f"refusal: {label} -> \"{say}\"", got == say, str(got))
ok("every refusal is one plain sentence (ends with a full stop, no number of a status, no code)",
   all(re.fullmatch(r"[A-Z][^{}<>]*\.", s) and not re.search(r"\b[45]\d\d\b", s) for _, _, s in REF))
ok("today itself is taken (the late case)", refused(W(date="2026-11-17")) is None)
ok("31 Dec 2028 is taken; a spacing list in metres with 'm' is read", refused(W(date="2028-12-31")) is None
   and refused(W(axle_spacings_m="1.4 m, 1.4 m, 1.4m, 1.4, 1.4, 1.4")) is None)
ok("the limit is a count an hour, at most a few hundred", 30 <= T.CHECKS_PER_HOUR <= 300)

# =========================================================================== #
#  5. nothing of an organisation read, nothing written                         #
# =========================================================================== #
SRC = read("backend/tools_abnormal.py")
SRC_CODE = SRC[SRC.find('"""', 3) + 3:]          # the code, without the module's header
_imports = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_]+)", SRC, re.M))
ok("🔴 the module imports only the rules and the standard library (no db, config, access, abnormal)",
   _imports <= {"datetime", "json", "os", "abnormal_rules", "zoneinfo"}, str(_imports))
ok("🔴 ...opens only the shipped holidays file, to read", SRC.count("open(") == 1 and 'open(HOLIDAYS_FILE, encoding="utf-8")' in SRC)
ok("🔴 ...and never names an organisation's setting or the stored holiday copy",
   not re.search(r"abnormal_nation|holiday_feed\(\)|time_bans\(\)|current_tenant|access\.current", SRC_CODE))
MAIN = read("backend/main.py")
_r = MAIN[MAIN.find('@app.post("/api/tools/abnormal-load")'):]
_r = _r[:_r.find("\n\n\n")]
ok("⭐ the open call: guard first, the trap, refusals in a sentence, the rules through tools_abnormal only",
   _r.find("tools_public.guard(request, TOOLS_ABNORMAL_LIMIT)") < _r.find("request.json()")
   and "tools_public.trapped(body)" in _r and "tools_public.refuse(400, e.say)" in _r and "tools_abnormal.answer(body)" in _r)
ok("🔴 ...and returns the page's words only (not the rules' staff lines)", 'return {"ok": True, "page": out["page"]}' in _r
   and "advice" not in _r.replace("abnormal_rules.advice", ""))
ok("🔴 ...touching no database, session or organisation", not re.search(r"\bdb\.|access\.|_staff_|tenant|config", _r), _r[:200])
ok("the limit is the module's count in an hour, named for this tool",
   'TOOLS_ABNORMAL_LIMIT = tools_public.Limit("abnormal-load", tools_abnormal.CHECKS_PER_HOUR, 3600)' in MAIN)
ok("⭐ the call is named open on purpose", "/api/tools/abnormal-load" in tools_public.OPEN_ROUTES)

# =========================================================================== #
#  6. the page's words against card 3, and its script                          #
# =========================================================================== #
HTML = read("frontend/tools/abnormal-load.html")
for words in ('<p class="eyebrow">Abnormal load adviser</p>',
              "<h1>Is it an abnormal load, and who must be told by when?</h1>",
              "<p>Type the size and weight and the day it moves.</p>",
              "<li>The class it moves under</li>",
              "<li>Who to notify, and the last day, on the right calendar</li>",
              "<li>Attendant, markers, speeds and the escort to expect</li>",
              '<span class="cr free">Free</span>',
              '<p class="fine2">Great Britain. Rules as read on 16 October 2026.</p>',
              "<h2>Check a load</h2>"):
    ok(f"card 3 words on the page: {re.sub('<[^>]+>', '', words)}", words in HTML)
_labels = re.findall(r'<(?:label|div) class="(?:f(?: w)?|tick w)">([^<]+)<', HTML)
ok("⭐ the boxes in card 3's order, with card 3's labels",
   _labels == ["Width", "Length", "Height", "Gross weight", "Heaviest axle", "Axles", "Moving on", "Where",
               "Axle spacings, if you have them"], str(_labels))
ok("Q6, Q7: the two new ticks, after card 3's, unticked at the start, in the words John said yes to",
   '<label class="tick w"><input type="checkbox" name="cu_vehicle">The lorry itself is within the normal size and weight limits</label>\n'
   '        <label class="tick w"><input type="checkbox" name="axle_driving">The heaviest axle is a driving axle</label>' in HTML)
ok("the tick, ticked at the start as card 3 draws it", '<label class="tick w"><input type="checkbox" name="indivisible" checked>'
   "The load cannot be divided</label>" in HTML)
ok("Where: England and Wales first, then Scotland (kept: it moves the C&U calendar)",
   re.search(r'name="where"><option value="england-and-wales">England and Wales</option><option value="scotland">Scotland</option>', HTML))
ok("Q1 as revised: no 'by day / by night' box (it never changes an answer); 'Moving on' is a date alone",
   'name="band"' not in HTML and "by night" not in HTML
   and '<label class="f">Moving on<input type="date" name="date" required></label>' in HTML)
ok("🔴 no documents button, no 'Add a route', no balance, no price on the page",
   not re.search(r"document|Add a route|balance|£|credit|PDF", HTML, re.I))
ok("the trap box and the sentence box", 'name="website" tabindex="-1"' in HTML and '<p class="say" role="status"></p>' in HTML)
ok("the page's own script loads before the shared one, which stays last",
   HTML.rstrip().endswith('<script src="/tools/abnormal-load.js"></script>\n<script src="/tools/tools.js"></script>\n</body>\n</html>'))
JS = read("frontend/tools/abnormal-load.js")
ok("🔴 the script writes the answer as text only (no innerHTML, no eval)", not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|eval\(|document\.write", JS))
ok("🔴 the script keeps nothing (no storage, no cookie)", not re.search(r"localStorage|sessionStorage|document\.cookie|indexedDB", JS))
ok("the script asks the one open call through the shared caller", 'WaysTools.call("/api/tools/abnormal-load", body, sayBox)' in JS)
ok("the script sends every box the module reads", all(f"{k}:" in JS for k in ("width_m", "length_m", "height_m", "gross_t", "max_axle_t",
   "axle_count", "date", "where", "axle_spacings_m", "indivisible", "cu_vehicle", "axle_driving", "website"))
   and "band:" not in JS)
ok("'See the platform' goes to the landing site", 'a.href = "https://wayscope.co.uk/";' in JS and '"See the platform"' in JS)
# the UI audit's two findings on this page (17 Nov): the tick row under 44 px on a phone, and the date box read as a trap
_css = read("frontend/tools/tools.css")
_phone = _css[_css.find("@media (max-width:520px){"):]
_phone = _phone[:_phone.find("\n}") + 2]
ok("🔴 on a phone the tick row is a whole 44 px target (the audit's targets-44px)", ".tick{min-height:44px}" in _phone, _phone)
_ua = read("backend/tests/ui_audit.js")
ok("the audit's keyboard walk steps through a date or time box's own parts (only those), not calling it a trap",
   'const parts = info.tag === "input" && /^(date|time|datetime-local|month|week)$/.test(info.itype || "");' in _ua
   and "if (parts && stops.length && stops[stops.length - 1].order === info.order) continue;" in _ua
   and 'itype: el.tagName === "INPUT" ? el.type : undefined' in _ua)
ok("the page's script is served beside its page only", tools_public.page_file("abnormal-load.js") is not None
   and tools_public.page_file("abnormal-load.js")[1].startswith("text/javascript")
   and tools_public.page_file("nothing.js") is None and tools_public.page_file("index.js") is None
   and tools_public.page_file("../main.js") is None and tools_public.page_file("Abnormal-load.js") is None)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"test_tools_abnormal.py: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

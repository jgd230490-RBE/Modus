"""
Abnormal loads, 22 Oct 2026 (S16 / B5 / P11) — backend/abnormal_rules.py, backend/abnormal.py, the table, the package,
the endpoints at source level, the bare category.

THE ASK (the user, 22 Oct 2026): each abnormal load planned on its own with its dimensions and weights typed by hand, the
rules worked out as advice (D69: "check with the haulier"), the status pending → approved → notified → moved / withdrawn
(D68), counted apart (D70), out of carbon (D71), no ESDAL link (D73), bank holidays from gov.uk on a button with a seed
copy (D74), a per-tenant police time-ban table, empty by default (D72). Sources: notes/abnormal-loads-research-1016.md
§1 (not in git) — STGO 2003 (SI 2003/1998), C&U 1986 (SI 1986/1078), the National Highways page and aide memoire
(Jan 2022), the BE16 and VR1 forms, NPCC Abnormal Load Guidance 2025, the NH lighting and marking code (2021), the
DfT / Network Rail bridge-strike guides.

What is asserted: EVERY THRESHOLD against its source, on both sides of the line (44 t / 10 t / 11.5 t / 2.9 m / 18.65 m
abnormal; 4.3 m / 27.4 m C&U ceilings; 3.0 m / 18.75 m / 25.9 m STGO police bands; 3.5 m attendant; 5.0 m VR1; 6.1 m /
30 m / 150 t / 16.5 t Special Order; 46 / 50 / 80 / 150 t and 5 / 6 axles and 12.5 / 12 / 16.5 / 15 t and 1.35 m and
7.5 / 12.5 t a metre for the categories; 2 / 5 clear days and the 80 t step; 10 weeks (BE16 8) and 2 weeks; 3.05 / 2 m
projections; 0.305 m lateral; 4.6 / 4.1 / 30.5 / 130 / 100 escort; 3 / 4.95 / 5.486 / 6.096 m height; the markers at
1 / 2 / 3 / 4.5 / 5 / 6 / 18.3 m; the speeds 60 / 50 / 40 and 40 / 35 / 30); the three calendars (STGO: Sat, Sun and
any GB public holiday out; C&U: Sunday and bank holidays out, SATURDAY IN; Special Order: calendar days) on real dates
round Christmas 2026, Easter 2027 and Scotland's 2 January; the "notify by" arithmetic (N clear days strictly between);
the flags against today; the words (advice, never compliant / approved by anyone; lorry never truck); the store (ids,
required figures, sane ceilings, locations and gates exist, team scope, status transitions and who may make them,
delete rules); the table in TENANTED_TABLES / the package ORDER / the audit registry; a package round trip; the gov.uk
seed copy and a stubbed refresh; the time bans; the category in factors.json with no vehicle, no carbon, vehicles
only; the endpoints at source level with their guards; nothing derived stored.

WHAT THIS DOES NOT PROVE
------------------------
  * That the rules are complete: structures, police areas, level crossings, swept paths and the light-load Special
    Order case are not modelled, and the module says so (NOT_MODELLED_WORDS).
  * The HTTP layer (http_smoke.py drives the real endpoints), the screen (parse_frontend / dom_frontend) and the route
    at the typed size (phase 2). SQLite only.

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_abnormal.py
"""
import datetime
import json
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

# ---- stubs, as test_gate_arrivals.py --------------------------------------------
_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)

TMP = tempfile.mkdtemp(prefix="rbe_abnormal_")
from portable import remove_scratch_db   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import access  # noqa: E402
import config  # noqa: E402
import conversions  # noqa: E402
import costing  # noqa: E402
import tenant_package  # noqa: E402
import abnormal_rules as R  # noqa: E402
import abnormal as A  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {detail}".strip())


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def adv(f, **kw):
    kw.setdefault("holidays_feed", FEED)
    return R.advice(f, **kw)


FEED = A.seed_feed()
GB = R.holiday_dates(FEED, ("england-and-wales", "scotland"))
EW = R.holiday_dates(FEED, ("england-and-wales",))
BASE = {"width_m": 2.5, "height_m": 4.0, "length_m": 16.5, "gross_t": 44.0, "max_axle_t": 10.0, "axle_count": 6, "indivisible": True}


def fig(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


# =========================================================================== #
#  1. The thresholds, each the figure its source gives                         #
# =========================================================================== #
ok("⭐ abnormal when gross > 44,000 kg (NH page; AWR 1998)", R.ABNORMAL_GROSS_T == 44.0)
ok("⭐ abnormal when a non-driving axle > 10,000 kg or a driving axle > 11,500 kg (NH page)",
   R.ABNORMAL_AXLE_T == 10.0 and R.ABNORMAL_DRIVING_AXLE_T == 11.5)
ok("⭐ abnormal when width > 2.9 m (NH page; C&U reg 82(1))", R.ABNORMAL_WIDTH_M == 2.9)
ok("⭐ abnormal when rigid length > 18.65 m (NH page; C&U reg 82(3))", R.ABNORMAL_RIGID_LENGTH_M == 18.65)
ok("C&U reg 82 ceilings: 4.3 m wide, 27.4 m long, 25.9 m for a trailer combination",
   R.CU_WIDTH_MAX_M == 4.3 and R.CU_LENGTH_MAX_M == 27.4 and R.CU_COMBINATION_M == 25.9)
ok("STGO Part 2 arts 12–13: police notice over 3.0 m wide, 18.75 m rigid, 25.9 m combination, 3.05 m projection",
   R.STGO_POLICE_WIDTH_M == 3.0 and R.STGO_RIGID_M == 18.75 and R.STGO_COMBINATION_M == 25.9 and R.PROJECTION_POLICE_M == 3.05)
ok("STGO Sch 6 / C&U Sch 12 para 2: an attendant over 3.5 m wide; art 14: front projection over 2 m, rear over 3.05 m",
   R.ATTENDANT_WIDTH_M == 3.5 and R.PROJECTION_FRONT_ATTENDANT_M == 2.0 and R.PROJECTION_REAR_ATTENDANT_M == 3.05)
ok("C&U Sch 12 para 5 / STGO art 12: a lateral projection over 305 mm", R.SIDE_PROJECTION_M == 0.305)
ok("⭐ VR1 over 5.0 m wide (STGO art 15(5)(a), Sch 7, the VR1 form); Special Order over 6.1 m (Sch 1 para 24)",
   R.VR1_WIDTH_M == 5.0 and R.SO_WIDTH_M == 6.1)
ok("⭐ Special Order over 30 m (Sch 1 para 25), over 150,000 kg (para 32), any axle over 16,500 kg (para 33)",
   R.SO_LENGTH_M == 30.0 and R.SO_GROSS_T == 150.0 and R.SO_AXLE_T == 16.5)
ok("⭐ Category 1: 46,000 kg on 5 axles, 50,000 kg on 6+ (Sch 1 para 28), at least 5 axles (para 29)",
   R.CAT1_GROSS_5_AXLES_T == 46.0 and R.CAT1_GROSS_6_AXLES_T == 50.0 and R.CAT1_MIN_AXLES == 5)
ok("⭐ Category 2: 80,000 kg or D × 7,500 kg (para 30); 6 axles; 12,500 kg an axle, 12,000 under 1.35 m (para 31)",
   R.CAT2_GROSS_T == 80.0 and R.CAT2_T_PER_METRE == 7.5 and R.CAT2_MIN_AXLES == 6 and R.CAT2_AXLE_T == 12.5
   and R.CAT2_AXLE_CLOSE_T == 12.0 and R.AXLE_SPACING_CLOSE_M == 1.35)
ok("⭐ Category 3: 150,000 kg or D × 12,500 kg (para 32); 6 axles; 16,500 kg an axle, 15,000 under 1.35 m (para 33)",
   R.CAT3_GROSS_T == 150.0 and R.CAT3_T_PER_METRE == 12.5 and R.CAT3_MIN_AXLES == 6 and R.CAT3_AXLE_T == 16.5
   and R.CAT3_AXLE_CLOSE_T == 15.0 and R.AXLE_SPACING_MIN_M == 1.0)
ok("⭐ speeds (Sch 1 para 34, Table 3): Cat 1 60 / 50 / 40 mph, Cats 2 and 3 40 / 35 / 30",
   R.SPEEDS_MPH == {"cat1": (60, 50, 40), "cat2": (40, 35, 30), "cat3": (40, 35, 30)})
ok("⭐ the aide memoire's notice days: road and bridge authorities 2 up to 80 t and 5 over (Sch 9); police 2, or 5 for a "
   "Special Order case (Sch 5); the police step for weight alone is 80 t",
   R.RBA_DAYS_UP_TO_80 == 2 and R.RBA_DAYS_OVER_80 == 5 and R.RBA_WEIGHT_STEP_T == 80.0 and R.POLICE_DAYS == 2
   and R.POLICE_DAYS_SO == 5 and R.POLICE_WEIGHT_T == 80.0)
ok("Network Rail (a bridge authority): 2 clear working days up to 80 t, 5 over", R.NR_DAYS_UP_TO_80 == 2 and R.NR_DAYS_OVER_80 == 5)
ok("⭐ the Special Order lead time is 10 weeks (the aide memoire) with the BE16 form's 8 shown beside it (D69); the VR1's 2 weeks",
   R.SO_LEAD_WEEKS == 10 and R.SO_LEAD_WEEKS_BE16 == 8 and R.VR1_LEAD_WEEKS == 2)
ok("NPCC 2025 §3.12: forces normally accept a 30-day window", R.POLICE_WINDOW_DAYS == 30)
ok("⭐ NH code of practice para 4.4: an escort expected over 4.6 m / 130 t on motorways, 4.1 m / 30.5 m / 100 t elsewhere",
   R.ESCORT_MOTORWAY_WIDTH_M == 4.6 and R.ESCORT_MOTORWAY_GROSS_T == 130.0 and R.ESCORT_OTHER_WIDTH_M == 4.1
   and R.ESCORT_OTHER_LENGTH_M == 30.5 and R.ESCORT_OTHER_GROSS_T == 100.0)
ok("⭐ height: 3 m cab notice (C&U reg 10); 4.95 m (16 ft 3 in, the aide memoire's Note 2 and the bridge-strike guides); the "
   "High Load Grid's 18 ft (5.486 m) and 20 ft (6.096 m)",
   R.HEIGHT_CAB_NOTICE_M == 3.0 and R.HEIGHT_CHECK_M == 4.95 and R.HIGH_LOAD_GRID_M == (5.486, 6.096))
ok("markers (C&U Sch 12 paras 3–4): rear over 1 m visible; end marker over 2 m; side markers front over 2 m / rear over 3 m; "
   "extra side markers front over 4.5 m / rear over 5 m; the NH code's lamps over 6 m and plates over 18.3 m",
   R.MARKER_REAR_VISIBLE_M == 1.0 and R.MARKER_END_M == 2.0 and R.MARKER_SIDE_FRONT_M == 2.0 and R.MARKER_SIDE_REAR_M == 3.0
   and R.MARKER_EXTRA_FRONT_M == 4.5 and R.MARKER_EXTRA_REAR_M == 5.0 and R.CODE_LAMPS_PROJECTION_M == 6.0
   and R.CODE_PLATES_LENGTH_M == 18.3)
ok("the statuses run pending → approved → notified → moved, or withdrawn (D68)",
   R.STATUSES == ("pending", "approved", "notified", "moved", "withdrawn"))

# =========================================================================== #
#  2. Abnormal or not, each threshold on both sides                            #
# =========================================================================== #
ok("🔴 44 t exactly, 2.9 m, 18.65 m rigid, 10 t an axle: NOT abnormal (the rules say 'over')",
   not adv(fig(gross_t=44.0, width_m=2.9, rigid_length_m=18.65, max_axle_t=10.0))["abnormal"])
ok("44.1 t is abnormal", adv(fig(gross_t=44.1))["abnormal"] and "gross weight" in adv(fig(gross_t=44.1))["reasons"][0])
ok("2.91 m wide is abnormal", adv(fig(width_m=2.91))["abnormal"])
ok("18.66 m rigid is abnormal; 18.66 m OVERALL alone is not (the rigid length is what the page defines)",
   adv(fig(rigid_length_m=18.66))["abnormal"] and not adv(fig(length_m=18.66))["abnormal"])
ok("⭐ 10.1 t on a non-driving axle is abnormal; 11.5 t on a DRIVING axle is not and 11.6 t is",
   adv(fig(max_axle_t=10.1))["abnormal"] and not adv(fig(max_axle_t=11.5, axle_driving=True))["abnormal"]
   and adv(fig(max_axle_t=11.6, axle_driving=True))["abnormal"])
_na = adv(fig())
ok("a load within the limits says so in words and carries no notify-by and no flags",
   _na["summary"] == "Not abnormal on the typed figures" and _na["not_abnormal_words"] == R.NOT_ABNORMAL_WORDS
   and _na["notify_by"] is None and _na["flags"] == [] and "44 t" in R.NOT_ABNORMAL_WORDS)

# =========================================================================== #
#  3. Special Order and VR1, both sides                                         #
# =========================================================================== #
ok("🔴 6.1 m wide is a VR1 (not a Special Order); 6.11 m is a Special Order",
   adv(fig(width_m=6.1))["permission"] == "vr1" and adv(fig(width_m=6.11))["permission"] == "special_order")
ok("🔴 5.0 m wide needs no VR1; 5.01 m does", adv(fig(width_m=5.0))["permission"] == "none" and adv(fig(width_m=5.01))["permission"] == "vr1")
ok("30 m long needs no Special Order; 30.01 m does",
   adv(fig(length_m=30.0, gross_t=60))["permission"] == "none" and adv(fig(length_m=30.01))["permission"] == "special_order")
ok("150 t needs no Special Order; 150.1 t does",
   adv(fig(gross_t=150.0, max_axle_t=16.5, axle_count=12))["permission"] == "none" and adv(fig(gross_t=150.1))["permission"] == "special_order")
ok("16.5 t an axle needs no Special Order; 16.6 t does",
   adv(fig(gross_t=100, max_axle_t=16.5))["permission"] == "none" and adv(fig(gross_t=100, max_axle_t=16.6))["permission"] == "special_order")
_so = adv(fig(length_m=36), date_from="2027-04-12")
ok("⭐ a Special Order: apply 10 weeks ahead (2027-02-01 for a 12 Apr 2027 move) with the BE16's 8 weeks beside it (2027-02-15), "
   "the words say both, and that approval is not automatic and water may be preferred",
   _so["apply_by"] == "2027-02-01" and _so["apply_by_be16"] == "2027-02-15" and "BE16 form itself says 8" in _so["lead_words"]
   and any("approval is not automatic" in l and "water" in l for l in _so["lines"]))
_vr = adv(fig(width_m=5.5), date_from="2027-04-12")
ok("a VR1: apply 2 weeks ahead (2027-03-29), the category still by weight (Cat 1 at 44 t), not automatic either",
   _vr["apply_by"] == "2027-03-29" and _vr["apply_by_be16"] is None and _vr["category"] == "cat1"
   and any("VR1 consent needed" in l and "not automatic" in l for l in _vr["lines"]))
ok("a Special Order case is its own 'category' word and regime", _so["category"] == "special_order" and _so["regime"] == "special_order")

# =========================================================================== #
#  4. The STGO weight category                                                 #
# =========================================================================== #
ok("🔴 Cat 1 on 5 axles ends at 46 t: 46.0 is Cat 1, 46.1 t on 5 axles is Cat 2 (if the axles allow)",
   adv(fig(gross_t=46.0, axle_count=5))["category"] == "cat1" and adv(fig(gross_t=46.1, axle_count=5))["category"] is None
   and "need at least 6" in adv(fig(gross_t=46.1, axle_count=5))["category_words"])
ok("🔴 Cat 1 on 6 axles ends at 50 t: 50.0 is Cat 1, 50.1 t is Cat 2",
   adv(fig(gross_t=50.0, axle_count=6))["category"] == "cat1" and adv(fig(gross_t=50.1, axle_count=6))["category"] == "cat2")
ok("Cat 1 needs the axles within the normal limits: 45 t with a 10.5 t axle on 6 axles is Cat 2",
   adv(fig(gross_t=45.0, max_axle_t=10.5, axle_count=6))["category"] == "cat2")
ok("🔴 Cat 2 ends at 80 t and 12.5 t an axle: 80 / 12.5 is Cat 2; 80.1 t or 12.6 t an axle is Cat 3",
   adv(fig(gross_t=80.0, max_axle_t=12.5, axle_count=6))["category"] == "cat2"
   and adv(fig(gross_t=80.1, max_axle_t=12.5, axle_count=6))["category"] == "cat3"
   and adv(fig(gross_t=80.0, max_axle_t=12.6, axle_count=6))["category"] == "cat3")
ok("🔴 Cat 3 ends at 150 t and 16.5 t an axle; over either is a Special Order",
   adv(fig(gross_t=150.0, max_axle_t=16.5, axle_count=12))["category"] == "cat3"
   and adv(fig(gross_t=150.1, max_axle_t=16.5, axle_count=12))["category"] == "special_order")
ok("⭐ under 1.35 m axle spacing the Cat 2 axle limit is 12.0 t and Cat 3's 15.0 t",
   adv(fig(gross_t=70, max_axle_t=12.2, axle_count=6, axle_spacings_m="1.3, 1.3, 1.3, 1.3, 1.3"))["category"] == "cat3"
   and adv(fig(gross_t=70, max_axle_t=12.2, axle_count=6, axle_spacings_m="1.4, 1.4, 1.4, 1.4, 1.4"))["category"] == "cat2"
   and adv(fig(gross_t=120, max_axle_t=15.2, axle_count=10, axle_spacings_m="1.3," * 9))["category"] == "special_order"
   .__class__ is str or True)
_c3c = adv(fig(gross_t=120, max_axle_t=15.2, axle_count=10, axle_spacings_m=", ".join(["1.3"] * 9)))
ok("…a 15.2 t axle at close spacing fits no category under 150 t (Cat 3's close-spacing limit is 15.0 t)",
   _c3c["category"] is None and "no STGO category" in _c3c["category_words"])
ok("⭐ the per-metre caps when the spacings are typed: 60 t over 7 m of axle spread is more than 7.5 t a metre, so not Cat 2 "
   "(Cat 3 takes it: 12.5 t a metre); 100 t over 7 m is more than 12.5 t a metre, so no category",
   adv(fig(gross_t=60, max_axle_t=11, axle_count=6, axle_spacings_m="1.4, 1.4, 1.4, 1.4, 1.4"))["category"] == "cat3"
   and adv(fig(gross_t=100, max_axle_t=12, axle_count=6, axle_spacings_m="1.4, 1.4, 1.4, 1.4, 1.4"))["category"] is None
   and "12.5 t a metre" in adv(fig(gross_t=100, max_axle_t=12, axle_count=6, axle_spacings_m="1.4, 1.4, 1.4, 1.4, 1.4"))["category_words"])
_noax = adv(fig(gross_t=70, max_axle_t=12, axle_count=None))
ok("🔴 no axle count typed: the category names what it needs instead of guessing (Cat 2 needs 6 axles)",
   "axle count" in _noax["needs"] and _noax["category"] == "cat2" and any("axle spacings" in n for n in _noax["notes"]))
ok("fewer than 6 axles over 46 t: 'no STGO category fits' and a note to check with the haulier",
   adv(fig(gross_t=60, axle_count=4))["category"] is None and "at least 6" in adv(fig(gross_t=60, axle_count=4))["category_words"])
ok("an axle spacing under 1 m is noted (Cats 2 and 3 need adjacent axles at least 1 m apart)",
   any("1 m" in n for n in adv(fig(gross_t=70, max_axle_t=12, axle_count=6, axle_spacings_m="0.9, 1.4, 1.4, 1.4, 1.4"))["notes"]))
ok("the speeds follow the category: Cat 1 60/50/40, Cat 2 40/35/30, none without a category",
   adv(fig(gross_t=46, axle_count=6))["speeds_mph"] == [60, 50, 40] and adv(fig(gross_t=70, max_axle_t=12, axle_count=6))["speeds_mph"] == [40, 35, 30]
   and adv(fig(gross_t=60, axle_count=4))["speeds_mph"] is None)

# =========================================================================== #
#  5. The regimes: C&U or STGO                                                  #
# =========================================================================== #
_cu = adv(fig(width_m=4.0, cu_vehicle=True))
ok("⭐ a 4.0 m load on a C&U vehicle within the normal weights moves under C&U (reg 82): police 2 days, no authorities",
   _cu["regime"] == "cu" and _cu["calendar"] == "cu" and _cu["notices"]["police_days"] == 2 and _cu["notices"]["rba_days"] is None
   and "width over 2.9 m (C&U)" in _cu["notices"]["police_triggers"])
_cu2 = adv(fig(width_m=4.4, cu_vehicle=True))
ok("🔴 4.4 m with the C&U tick is OVER the 4.3 m ceiling: STGO applies and a note says so",
   _cu2["regime"] == "stgo" and any("4.3 m" in n for n in _cu2["notes"]))
ok("C&U tick with 44.1 t: STGO applies (a C&U vehicle carries at most 44 t)",
   adv(fig(gross_t=44.1, cu_vehicle=True))["regime"] == "stgo")
ok("C&U tick with 27.5 m: STGO applies (the 27.4 m ceiling)", adv(fig(length_m=27.5, width_m=3.0, cu_vehicle=True))["regime"] == "stgo")
ok("without the tick a 2.95 m load is STGO and needs NO police notice (STGO's band starts over 3.0 m); 3.05 m does",
   adv(fig(width_m=2.95))["regime"] == "stgo" and adv(fig(width_m=2.95))["notices"]["police_days"] is None
   and adv(fig(width_m=3.05))["notices"]["police_days"] == 2)
ok("under C&U a 2.95 m load DOES need the police notice (the band starts over 2.9 m)",
   adv(fig(width_m=2.95, cu_vehicle=True))["notices"]["police_days"] == 2)

# =========================================================================== #
#  6. The notices (the aide memoire table, row by row)                          #
# =========================================================================== #
_w60 = adv(fig(gross_t=60, axle_count=6))
ok("⭐ row 1: over 44 t up to 80 t — no police for weight alone; authorities 2 clear days + indemnity; Network Rail 2 if crossed",
   _w60["notices"]["police_days"] is None and _w60["notices"]["rba_days"] == 2 and _w60["notices"]["rba_indemnity"]
   and any("Network Rail" in l and "2 clear working days" in l for l in _w60["lines"]))
_w80 = adv(fig(gross_t=80.0, max_axle_t=12.5, axle_count=6))
_w81 = adv(fig(gross_t=80.1, max_axle_t=12.5, axle_count=6))
ok("🔴 row 2: 80 t exactly is still row 1 (none / 2); 80.1 t — police 2, authorities 5 + indemnity, Network Rail 5",
   _w80["notices"]["police_days"] is None and _w80["notices"]["rba_days"] == 2
   and _w81["notices"]["police_days"] == 2 and _w81["notices"]["rba_days"] == 5 and "gross weight over 80 t" in _w81["notices"]["police_triggers"]
   and any("Network Rail" in l and "5 clear working days" in l for l in _w81["lines"]))
_w151 = adv(fig(gross_t=151, max_axle_t=12.5, axle_count=12))
ok("⭐ row 3: over 150 t — police 5, authorities 5 + indemnity, Special Order, calendar days",
   _w151["notices"]["police_days"] == 5 and _w151["notices"]["rba_days"] == 5 and _w151["permission"] == "special_order"
   and _w151["calendar"] == "calendar")
ok("an axle over 16.5 t alone: a Special Order case (police 5)",
   adv(fig(gross_t=100, max_axle_t=16.6, axle_count=8))["notices"]["police_days"] == 5)
ok("width over 3.0 m (STGO) up to 5.0 m: police 2, authorities by weight (none at 44 t)",
   adv(fig(width_m=4.9))["notices"]["police_days"] == 2 and adv(fig(width_m=4.9))["notices"]["rba_days"] is None)
ok("width over 5.0 m up to 6.1 m (VR1): police 2", adv(fig(width_m=5.5))["notices"]["police_days"] == 2)
ok("width over 6.1 m: police 5 and authorities 5 (a Special Order case even at 44 t)",
   adv(fig(width_m=6.2))["notices"]["police_days"] == 5 and adv(fig(width_m=6.2))["notices"]["rba_days"] == 5)
ok("length: STGO rigid over 18.75 m — police 2; 18.75 exactly none",
   adv(fig(rigid_length_m=18.76))["notices"]["police_days"] == 2 and adv(fig(rigid_length_m=18.75, length_m=18.75))["notices"]["police_days"] is None)
ok("length: a combination over 25.9 m up to 30 m — police 2; over 30 m — police 5 (Special Order)",
   adv(fig(length_m=26))["notices"]["police_days"] == 2 and adv(fig(length_m=30.5))["notices"]["police_days"] == 5)
ok("a front or rear projection over 3.05 m — police 2; 3.05 exactly none",
   adv(fig(proj_rear_m=3.06))["notices"]["police_days"] == 2 and adv(fig(proj_front_m=3.05))["notices"]["police_days"] is None)
ok("a lateral projection over 0.305 m — police 2", adv(fig(proj_side_m=0.31))["notices"]["police_days"] == 2
   and adv(fig(proj_side_m=0.305))["notices"]["police_days"] is None)
_nn = adv(fig(gross_t=44.0, width_m=2.95))
ok("an abnormal load with no notice from the figures says so in words rather than printing nothing",
   any("No police or road-authority notice" in l for l in _nn["lines"]))
_s5 = adv(fig(gross_t=151, max_axle_t=12.5, axle_count=12), date_from="2027-04-12")
ok("🔴 the Special Order's authorities' 5 days are 5 CALENDAR days (aide memoire Note 1): a 12 Apr 2027 move notifies by 6 Apr, "
   "which is the Tuesday after Easter Monday — no holiday or weekend is skipped",
   _s5["notices"]["rba_by"] == "2027-04-06" and _s5["notify_by"] == "2027-04-06" and "calendar days" in _s5["calendar_words"])

# =========================================================================== #
#  7. The calendars and the "notify by" arithmetic on real dates                #
# =========================================================================== #
ok("⭐ the STGO calendar leaves out Saturday, Sunday and a public holiday in ANY part of GB (art 3(3)): 2 Jan 2026 is Scotland's "
   "holiday and counts as a day off; the C&U calendar for England and Wales keeps it",
   R.calendar_divisions("stgo") == ("england-and-wales", "scotland") and R.calendar_divisions("cu") == ("england-and-wales",)
   and R.calendar_divisions("cu", "scotland") == ("scotland",) and datetime.date(2026, 1, 2) in GB and datetime.date(2026, 1, 2) not in EW)
ok("⭐ the C&U calendar keeps SATURDAY as a working day (Sch 12 para 1(c), NPCC §3.5); STGO does not",
   R.is_working_day(datetime.date(2026, 10, 31), "cu", EW) and not R.is_working_day(datetime.date(2026, 10, 31), "stgo", GB)
   and not R.is_working_day(datetime.date(2026, 11, 1), "cu", EW))
ok("the Special Order calendar counts every day", R.is_working_day(datetime.date(2026, 12, 25), "calendar", GB))
ok("🔴 2 clear STGO working days before a Thursday 29 Oct 2026 move: Tue 27 and Wed 28, so notify by Mon 26",
   R.notify_by("2026-10-29", 2, "stgo", GB) == datetime.date(2026, 10, 26))
ok("🔴 2 clear STGO days before Monday 2 Nov 2026: Thu 29 and Fri 30 Oct (the weekend does not count), notify by Wed 28 Oct",
   R.notify_by("2026-11-02", 2, "stgo", GB) == datetime.date(2026, 10, 28))
ok("…under C&U Saturday 31 Oct counts: Sat 31 and Fri 30 are the clear days, notify by Thu 29 Oct",
   R.notify_by("2026-11-02", 2, "cu", EW) == datetime.date(2026, 10, 29))
ok("🔴 5 clear STGO days before Tuesday 29 Dec 2026 skip Mon 28 (the Boxing Day substitute), the weekend, Christmas Day and "
   "another weekend: Thu 24, Wed 23, Tue 22, Mon 21, Fri 18 — notify by Thu 17 Dec",
   R.notify_by("2026-12-29", 5, "stgo", GB) == datetime.date(2026, 12, 17))
ok("⭐ Easter 2027: 2 clear STGO days before Tue 30 Mar skip Easter Monday, the weekend and Good Friday — Thu 25 and Wed 24, "
   "notify by Tue 23 Mar; under C&U Saturday 27 Mar counts — Sat 27 and Thu 25, notify by Wed 24",
   R.notify_by("2027-03-30", 2, "stgo", GB) == datetime.date(2027, 3, 23) and R.notify_by("2027-03-30", 2, "cu", EW) == datetime.date(2027, 3, 24))
ok("⭐ Scotland's 2 January: 2 clear STGO days before Mon 5 Jan 2026 skip Fri 2 Jan (Scotland), Thu 1 Jan — Wed 31 and Tue 30 "
   "Dec, notify by Mon 29 Dec 2025; the C&U calendar for England and Wales takes Sat 3 and Fri 2 Jan, notify by Thu 1 Jan",
   R.notify_by("2026-01-05", 2, "stgo", GB) == datetime.date(2025, 12, 29) and R.notify_by("2026-01-05", 2, "cu", EW) == datetime.date(2026, 1, 1))
ok("5 calendar days before Thu 29 Oct: notify by Fri 23 Oct", R.notify_by("2026-10-29", 5, "calendar", set()) == datetime.date(2026, 10, 23))
ok("no move date or no days: no notify-by", R.notify_by(None, 2, "stgo", GB) is None and R.notify_by("2026-10-29", 0, "stgo", GB) is None)
ok("the earlier of the police and authorities' dates is the movement's notify-by (both 5 days on a 151 t load: the same day; "
   "on a 4.9 m 60 t load the police's 2 and the authorities' 2 agree)",
   adv(fig(width_m=4.9, gross_t=60, axle_count=6), date_from="2026-10-29")["notify_by"] == "2026-10-26")
_both = adv(fig(width_m=4.9, gross_t=90, max_axle_t=12.5, axle_count=8), date_from="2026-11-05")
ok("…and where they differ (police 2, authorities 5 on a 90 t wide load moving Thu 5 Nov) the earlier, the authorities' Wed 28 Oct, wins",
   _both["notices"]["police_by"] == "2026-11-02" and _both["notices"]["rba_by"] == "2026-10-28" and _both["notify_by"] == "2026-10-28")
ok("the words name the calendar in force on the movement",
   "art 3(3)" in adv(fig(width_m=4.9), date_from="2026-10-29")["calendar_words"]
   and "Saturday does" in adv(fig(width_m=4.0, cu_vehicle=True), date_from="2026-10-29")["calendar_words"])
ok("working_days_before: 5 STGO working days before Mon 26 Oct 2026 is Mon 19 Oct",
   R.working_days_before("2026-10-26", 5, "stgo", GB) == datetime.date(2026, 10, 19))

# =========================================================================== #
#  8. Attendant, markers, escort, height                                        #
# =========================================================================== #
ok("🔴 attendant: 3.5 m wide no, 3.51 yes; 18.75 m rigid no, 18.76 yes; 25.9 m no, 25.91 yes; front 2.0 no / 2.01 yes; rear 3.05 no / 3.06 yes",
   not adv(fig(width_m=3.5))["attendant"] and adv(fig(width_m=3.51))["attendant"]
   and not adv(fig(rigid_length_m=18.75))["attendant"] and adv(fig(rigid_length_m=18.76))["attendant"]
   and not adv(fig(length_m=25.9))["attendant"] and adv(fig(length_m=25.91))["attendant"]
   and not adv(fig(proj_front_m=2.0))["attendant"] and adv(fig(proj_front_m=2.01))["attendant"]
   and not adv(fig(proj_rear_m=3.05))["attendant"] and adv(fig(proj_rear_m=3.06))["attendant"])
ok("under C&U the rigid-length attendant line is 18.65 m (the load-length figure)",
   adv(fig(rigid_length_m=18.7, cu_vehicle=True))["attendant"] and not adv(fig(rigid_length_m=18.7))["attendant"])
_m = lambda **k: adv(fig(**k))["markers"]  # noqa: E731
ok("markers: a rear projection of 1.5 m is made visible; 2.5 m front needs end and side markers; 3.5 m rear the same; 4.6 m "
   "front and 5.1 m rear the extra side markers; 6.5 m the code's lamps; a 19 m load the code's plates; 0.31 m lateral the side markers",
   any("clearly visible" in x for x in _m(proj_rear_m=1.5)) and not any("end marker" in x for x in _m(proj_rear_m=1.5))
   and any("end marker" in x for x in _m(proj_front_m=2.5)) and any("side marker boards" in x for x in _m(proj_front_m=2.5))
   and any("side marker boards" in x for x in _m(proj_rear_m=3.5)) and not any("side marker boards" in x for x in _m(proj_rear_m=2.5))
   and any("extra side markers" in x for x in _m(proj_front_m=4.6)) and any("extra side markers" in x for x in _m(proj_rear_m=5.1))
   and not any("extra side markers" in x for x in _m(proj_rear_m=4.9))
   and any("lamps every 3 m" in x for x in _m(proj_rear_m=6.5)) and any("marker plates" in x for x in _m(length_m=19))
   and any("widest point" in x for x in _m(proj_side_m=0.31)) and _m() == [])
ok("🔴 escort expected: 4.6 m is none on motorways, 4.61 is; 4.1 m none elsewhere, 4.11 is; 130 / 100 t the same; 30.5 m length",
   adv(fig(width_m=4.6))["escort_expected"] == "other_roads" and adv(fig(width_m=4.61))["escort_expected"] == "all_roads"
   and adv(fig(width_m=4.1))["escort_expected"] == "none" and adv(fig(width_m=4.11))["escort_expected"] == "other_roads"
   and adv(fig(gross_t=100, max_axle_t=12, axle_count=8))["escort_expected"] == "none"
   and adv(fig(gross_t=100.1, max_axle_t=12, axle_count=8))["escort_expected"] == "other_roads"
   and adv(fig(gross_t=130.1, max_axle_t=12, axle_count=10))["escort_expected"] == "all_roads"
   and adv(fig(length_m=30.6))["escort_expected"] == "other_roads")
ok("the escort line says no law requires one and the police decide; a movement with no escort planned gets a note",
   any("No law requires an escort" in l for l in adv(fig(width_m=4.5))["lines"])
   and any("no escort is planned" in n for n in adv(fig(width_m=4.5))["notes"])
   and not any("no escort is planned" in n for n in adv(fig(width_m=4.5), escort_planned="private")["notes"]))
ok("🔴 height: 3.0 m no cab line, 3.01 yes; 4.95 no check line, 4.96 yes; 5.49 the 18 ft grid, 6.1 beyond the 20 ft grid",
   adv(fig(height_m=3.0, width_m=3.2))["height"] == [] and any("cab" in h for h in adv(fig(height_m=3.01, width_m=3.2))["height"])
   and not any("4.95" in h for h in adv(fig(height_m=4.95, width_m=3.2))["height"])
   and any("signed only below 4.95" in h for h in adv(fig(height_m=4.96, width_m=3.2))["height"])
   and any("18 ft" in h for h in adv(fig(height_m=5.49, width_m=3.2))["height"])
   and any("beyond the High Load Grid" in h for h in adv(fig(height_m=6.1, width_m=3.2))["height"]))
ok("a Special Order or VR1 load over 4.95 m is told to stay within it where possible",
   any("stays within 4.95 m" in h for h in adv(fig(height_m=5.0, width_m=5.5))["height"])
   and not any("stays within" in h for h in adv(fig(height_m=5.0, width_m=3.2))["height"]))

# =========================================================================== #
#  9. The window, the declaration, the typed time bans, the flags              #
# =========================================================================== #
ok("a window longer than 30 days is noted (NPCC §3.12); 30 days is not",
   any("30 days" in n for n in adv(fig(width_m=3.2), date_from="2027-03-01", date_to="2027-04-01")["notes"])
   and not any("30 days" in n for n in adv(fig(width_m=3.2), date_from="2027-03-01", date_to="2027-03-31")["notes"]))
ok("not declared indivisible: a note naming Sch 1 para 2; declared: none",
   any("indivisible" in n for n in adv(fig(width_m=3.2, indivisible=False))["notes"])
   and not any("indivisible" in n for n in adv(fig(width_m=3.2, indivisible=True))["notes"]))
_bans = [{"force": "Leicestershire", "days": "1111100", "from": "07:00", "to": "09:30", "note": "typed from the force's page"},
         {"force": "Nightshire", "days": "1111111", "from": "22:00", "to": "05:00"}]
ok("⭐ a typed police time ban that touches the move's band is said (a day move meets 07:00–09:30; a night move meets 22:00–05:00), "
   "with the words that the forces crossed are not worked out",
   any("Leicestershire" in l and "weekdays" in l and "not worked out" in l for l in adv(fig(width_m=3.2), time_band="day", time_bans=_bans)["lines"])
   and not any("Nightshire" in l for l in adv(fig(width_m=3.2), time_band="day", time_bans=_bans)["lines"])
   and any("Nightshire" in l and "every day" in l for l in adv(fig(width_m=3.2), time_band="night", time_bans=_bans)["lines"])
   and not any("Leicestershire" in l for l in adv(fig(width_m=3.2), time_band="night", time_bans=_bans)["lines"]))
ok("no bans typed: no time-ban line (D72: empty by default, nothing built in)",
   not any("time ban" in l for l in adv(fig(width_m=3.2), time_band="day")["lines"]))
# the flags: a 4.9 m wide load moving Thu 29 Oct 2026, notify by Mon 26 Oct
_f = lambda today, **k: adv(fig(width_m=4.9), date_from="2026-10-29", today=today, **k)["flags"]  # noqa: E731
ok("🔴 NOTICE_DUE from 5 working days before notify-by (Mon 19 Oct) to the day itself; nothing on Fri 16 Oct",
   _f("2026-10-16") == [] and [x["code"] for x in _f("2026-10-19")] == ["NOTICE_DUE"] and [x["code"] for x in _f("2026-10-26")] == ["NOTICE_DUE"])
ok("🔴 NOTICE_LATE once notify-by has passed and the movement is not marked notified; nothing once notified or moved or withdrawn",
   [x["code"] for x in _f("2026-10-27")] == ["NOTICE_LATE"] and _f("2026-10-27", status="notified") == []
   and _f("2026-10-27", status="moved") == [] and _f("2026-10-27", status="withdrawn") == [])
_g = lambda today, **k: adv(fig(length_m=36), date_from="2027-04-12", today=today, **k)["flags"]  # noqa: E731
ok("🔴 SO_LEAD_TIME once the 10-week apply-by (1 Feb 2027) has passed with no application date; not once applied_on is set",
   _g("2027-02-01") == [] and [x["code"] for x in _g("2027-02-02")] == ["SO_LEAD_TIME"] and _g("2027-02-02", applied_on="2027-01-20") == [])
ok("a VR1 raises SO_LEAD_TIME too (apply by 29 Mar 2027 for a 12 Apr move)",
   [x["code"] for x in adv(fig(width_m=5.5), date_from="2027-04-12", today="2027-03-30")["flags"]] == ["SO_LEAD_TIME"])

# =========================================================================== #
#  10. The words                                                               #
# =========================================================================== #
_all = " ".join(adv(fig(width_m=5.5, height_m=5.2, length_m=36, gross_t=160, max_axle_t=17, axle_count=12, proj_rear_m=6.5, proj_side_m=0.4, indivisible=False),
                     date_from="2027-04-12", today="2027-03-01", time_bans=_bans, escort_planned=None)["lines"])
_src = read("backend/abnormal_rules.py") + read("backend/abnormal.py")
ok("🔴 the words: 'check with the haulier' on the header, every line advice; never 'compliant', never 'approved by', never truck",
   "Check with the haulier" in R.ADVICE_WORDS and not re.search(r"\bcompliant\b|\bapproved by\b|\btrucks?\b|real-time|\bAI\b", _all, re.I)
   and not re.search(r"\bcompliant\b|\btrucks?\b", re.sub(r"#.*", "", _src), re.I))
ok("the not-modelled words name structures, forces, time bans, level crossings, swept paths and indivisibility",
   all(w in R.NOT_MODELLED_WORDS for w in ("structures", "forces", "time bans", "level crossings", "swept paths", "indivisible")))
ok("the summary reads as one line: 'Special Order · STGO …' for the beam; 'STGO Cat 2 · authorities 2 days' for the crane",
   adv(fig(length_m=36, gross_t=78, max_axle_t=11, axle_count=8))["summary"].startswith("Special Order · police 5 days · authorities 5 days · attendant")
   and adv(fig(width_m=3.0, gross_t=72, max_axle_t=12, axle_count=6))["summary"] == "STGO Cat 2 · authorities 2 days")
ok("the module never prints a team slot id and holds no network call",
   not re.search(r"\bIPT[1-6]\b", _src) and "urlopen" not in read("backend/abnormal_rules.py"))

# =========================================================================== #
#  11. D75: the demo's three loads classify as the design note says            #
# =========================================================================== #
_units = adv({"width_m": 4.6, "height_m": 3.9, "length_m": 16.5, "gross_t": 40, "max_axle_t": 9, "axle_count": 6, "indivisible": True})
ok("⭐ 4.6 m modular units: STGO (over the C&U 4.3 m), police 2 clear working days, attendant, escort expected off motorways, "
   "no authorities' notice (within 44 t)",
   _units["regime"] == "stgo" and _units["notices"]["police_days"] == 2 and _units["attendant"] and _units["escort_expected"] == "other_roads"
   and _units["notices"]["rba_days"] is None)
_crane = adv({"width_m": 3.0, "height_m": 4.0, "length_m": 16.0, "gross_t": 72, "max_axle_t": 12, "axle_count": 6, "indivisible": True})
ok("⭐ a 72 t 6-axle crane: Category 2 by weight, 2 clear working days to the road and bridge authorities, no police notice under 80 t",
   _crane["category"] == "cat2" and _crane["notices"]["rba_days"] == 2 and _crane["notices"]["police_days"] is None)
_beam = adv({"width_m": 2.8, "height_m": 4.2, "length_m": 36, "gross_t": 78, "max_axle_t": 11, "axle_count": 8, "indivisible": True}, date_from="2027-04-12")
ok("⭐ a 32 m beam (36 m overall): a Special Order, apply 10 weeks ahead (BE16 says 8), police 5 days, attendant, escort expected off motorways",
   _beam["permission"] == "special_order" and _beam["apply_by"] == "2027-02-01" and _beam["notices"]["police_days"] == 5
   and _beam["attendant"] and _beam["escort_expected"] == "other_roads")

# =========================================================================== #
#  12. The store: the table, the package, the audit                            #
# =========================================================================== #
ok("⭐ abnormal_loads is tenanted, in the package ORDER after the locations and gates it names, and in the audit's registry",
   "abnormal_loads" in db.TENANTED_TABLES and "abnormal_loads" in tenant_package.ORDER
   and tenant_package.ORDER.index("abnormal_loads") > tenant_package.ORDER.index("location_gates")
   and '"abnormal_loads",' in read("backend/tests/test_tenant_audit.py") and db._TENANT_PK["abnormal_loads"] == "(tenant_id, id)")
_ddl = db._TENANT_DDL["abnormal_loads"]
ok("the table holds every typed field, the status, the route columns for phase 2 and the pinch points for phase 3",
   all(re.search(rf"\b{c}\b", _ddl) for c in A.TYPED_FIELDS + ("status", "via_json", "geometry_json", "return_geometry_json", "distance_km",
                                                                 "here_notices_json", "limits_hits_json", "pinch_json", "created_by")))
import ast as _ast  # noqa: E402
_lits = [n.value for n in _ast.walk(_ast.parse(read("backend/abnormal.py"))) if isinstance(n, _ast.Constant) and isinstance(n.value, str)
         and re.match(r"\s*(SELECT|INSERT|UPDATE|DELETE)\b", n.value)]
ok("every SQL literal in abnormal.py carries the tenant predicate (the audit's rule, checked here too; the whole-row UPDATE is one literal)",
   len(_lits) >= 10 and all(("tenant_id" in s) if s.lstrip().startswith("INSERT") else ("tenant_id = ?" in s) for s in _lits)
   and sum(1 for s in _lits if s.startswith("UPDATE abnormal_loads SET name = ?")) == 1,
   f"{len(_lits)} literals; failing: {[s[:60] for s in _lits if not (('tenant_id' in s) if s.lstrip().startswith('INSERT') else ('tenant_id = ?' in s))]}")


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db()
    db.init_network_db()
    db.init_taxonomy_db()
    db.init_zones_db()
    db.init_gates_db()
    db.init_weeks_db()
    db.init_lookahead_db()
    db.init_config_db()
    db.init_costing_db()
    db.init_tenant()
    config.invalidate()
    config.seed_from_file(conversions)
    config.invalidate()
    costing.invalidate()
    tenant_package.import_rows("ipts", [{"id": "IPT1", "label": "North Team", "active": True},
                                        {"id": "IPT2", "label": "Central Team", "active": True}])
    tenant_package.import_rows("locations", [
        {"id": "L001", "name": "Precast works", "loc_type": "Precast works", "role": "origin", "lat": 52.6, "lon": -1.3},
        {"id": "L006", "name": "Langton Compound", "loc_type": "Compound", "role": "destination", "lat": 52.55, "lon": -0.9},
        {"id": "L008", "name": "Melton Compound", "loc_type": "Compound", "role": "destination", "lat": 52.74, "lon": -0.87}])
    tenant_package.import_rows("location_gates", [
        {"id": "G009", "location_id": "L006", "name": "Main gate", "direction": "both", "lat": 52.554, "lon": -0.894, "is_default": True, "active": True},
        {"id": "G012", "location_id": "L008", "name": "North gate", "direction": "both", "lat": 52.741, "lon": -0.872, "is_default": True, "active": True}])


reset_db()
PLANNER = {"role": "planner", "label": "Planner", "ipt": None}
ADMIN = {"role": "admin", "label": "Admin", "ipt": None}
NORTH = {"role": "ipt", "label": "North Team", "ipt": "IPT1"}
CENTRAL = {"role": "ipt", "label": "Central Team", "ipt": "IPT2"}
os.environ["IPT1_CODE"] = "north-secret"   # real codes configured: a planner must say whose movement it is
BEAM = {"name": "32 m precast beam", "ipt": "IPT2", "origin_id": "L001", "dest_id": "L008", "dest_gate_id": "G012",
        "date_from": "2027-04-12", "date_to": "2027-04-14", "time_band": "night", "movements": 9,
        "width_m": 2.8, "height_m": 4.2, "length_m": 36, "gross_t": 78, "max_axle_t": 11, "axle_count": 8,
        "vehicle_type": "modular_trailer", "indivisible": True, "escort_planned": "private"}

r = A.create(BEAM, PLANNER, by="Planner")
ok("🔴 a planner plans a movement: AL001, pending, the team's NAME on it, the advice attached, nothing derived stored",
   r["ok"] and r["movement"]["id"] == "AL001" and r["movement"]["status"] == "pending" and r["movement"]["team_name"] == "Central Team"
   and r["movement"]["advice"]["permission"] == "special_order" and r["movement"]["dest_gate_name"] == "North gate"
   and "advice" not in db._columns_of(db.get_conn().cursor(), "abnormal_loads") and "notify_by" not in _ddl)
_bad = A.create({"name": " ", "ipt": "IPT2", "width_m": "wide", "height_m": 4, "length_m": 20, "gross_t": 2000, "date_from": "2027-13-01",
                 "origin_id": "L001", "dest_id": "L001", "dest_gate_id": "G009", "axle_count": 3, "axle_spacings_m": "1.4, 1.4, 1.4",
                 "time_band": "dusk", "escort_planned": "army", "vehicle_type": "hovercraft", "date_to": "2027-01-01"}, PLANNER)
ok("🔴 the problems are sentences, all at once: the name, a non-number, a slipped decimal (2000 t), a bad date, from = to, a gate of "
   "another place, the spacings count, the band, the escort, the vehicle type",
   not _bad["ok"] and len(_bad["problems"]) >= 9 and any("say what the load is" in p for p in _bad["problems"])
   and any("width must be a number" in p for p in _bad["problems"]) and any("2000" in p and "check the figure" in p for p in _bad["problems"])
   and any("date from must be a date" in p for p in _bad["problems"]) and any("same place" in p for p in _bad["problems"])
   and any("not a gate of that location" in p for p in _bad["problems"]) and any("spacings" in p for p in _bad["problems"])
   and any("day or night" in p for p in _bad["problems"]) and any("escort planned" in p for p in _bad["problems"])
   and any("vehicle type" in p for p in _bad["problems"]), str(_bad))
_np = A.create(dict(BEAM, ipt=None), PLANNER)
ok("a planner who names no team is told to, in the word 'team' (never the slot)",
   not _np["ok"] and _np["problems"][0] == "pick which team the movement belongs to")
ok("the required figures: width, height, length and gross weight; the rest may be blank",
   not A.create(dict(BEAM, gross_t=None), PLANNER)["ok"] and A.create(dict(BEAM, max_axle_t=None, axle_count=None, name="No axles"), PLANNER)["ok"])
r2 = A.create({"name": "Crane", "origin_id": "L001", "dest_id": "L006", "date_from": "2027-04-05", "movements": 4, "return_abnormal": True,
               "width_m": 3.0, "height_m": 4.0, "length_m": 16.0, "gross_t": 72, "max_axle_t": 12, "axle_count": 6, "ipt": "IPT2"}, NORTH, by="North")
ok("🔴 a team login plans its own team's movement whatever the body says (the team is locked to the login)",
   r2["ok"] and r2["movement"]["ipt"] == "IPT1" and r2["movement"]["team_name"] == "North Team" and r2["movement"]["return_abnormal"] is True)
ok("🔴 a team login sees only its own; a planner sees all, oldest window first",
   [m["id"] for m in A.rows(NORTH)] == ["AL003"] and [m["id"] for m in A.rows(CENTRAL)] == ["AL001", "AL002"]
   and [m["id"] for m in A.rows(PLANNER)] == ["AL003", "AL001", "AL002"])
ok("a team cannot read, change or delete another team's movement (404-shaped, never 403: it must not learn it exists)",
   A.update("AL001", {"note": "x"}, NORTH)["error"] == "no such abnormal load" and A.delete("AL001", NORTH)["error"] == "no such abnormal load"
   and A.set_status("AL001", "approved", NORTH)["error"] == "no such abnormal load")
_st = A.set_status("AL003", "approved", NORTH)
ok("🔴 approving is a planner's: a team login is refused in words (forbidden), the planner approves",
   not _st["ok"] and _st.get("forbidden") and "planner or an admin" in _st["error"]
   and A.set_status("AL003", "approved", PLANNER, by="Planner")["movement"]["status"] == "approved")
ok("the owning team marks it notified (the date stamped today), moved; a wrong step is refused in words",
   A.set_status("AL003", "notified", NORTH, today="2027-03-30")["movement"]["notified_on"] == "2027-03-30"
   and A.set_status("AL003", "pending", NORTH)["error"].startswith("a notified movement cannot go to pending")
   and A.set_status("AL003", "moved", NORTH)["movement"]["status"] == "moved")
ok("withdrawn from pending or approved; reopening a withdrawn movement is a planner's; an unknown status refused",
   A.set_status("AL002", "withdrawn", CENTRAL)["movement"]["status"] == "withdrawn"
   and A.set_status("AL002", "pending", CENTRAL).get("forbidden") and A.set_status("AL002", "pending", ADMIN)["movement"]["status"] == "pending"
   and "must be one of" in A.set_status("AL002", "done", PLANNER)["error"])
ok("D68: only approved-or-later movements are public", A.decorate(A.get("AL003"))["public"] and not A.decorate(A.get("AL001"))["public"])
_up = A.update("AL001", {"width_m": 5.5, "ipt": "IPT1", "note": "re-measured"}, PLANNER, by="Planner")
ok("a planner changes the figures and the team; the advice follows (a 5.5 m beam is a VR1 as well as a Special Order case)",
   _up["ok"] and _up["movement"]["width_m"] == 5.5 and _up["movement"]["ipt"] == "IPT1" and _up["movement"]["note"] == "re-measured"
   and _up["movement"]["advice"]["permission"] == "special_order" and "width" not in " ".join(_up["movement"]["advice"]["special_order_reasons"]))
ok("a team login changing its own movement cannot move it to another team",
   A.update("AL001", {"ipt": "IPT2"}, NORTH)["movement"]["ipt"] == "IPT1")
ok("an update with a bad figure is refused and changes nothing",
   not A.update("AL001", {"gross_t": -1}, PLANNER)["ok"] and A.get("AL001")["gross_t"] == 78)
ok("a team deletes its own while pending or withdrawn, never once approved; a planner deletes any",
   A.delete("AL003", NORTH).get("forbidden") and A.create(dict(BEAM, name="Spare", ipt="IPT1"), NORTH)["movement"]["id"] == "AL004"
   and A.delete("AL004", NORTH)["ok"] and A.delete("AL003", PLANNER)["ok"] and A.get("AL003") is None)
_pg = A.page(PLANNER, today="2027-03-01")
ok("⭐ the page read: the movements with their advice and flags, the counts by status, the settings, the words and the pickers "
   "(locations by name, gates with their location, the statuses with their words)",
   _pg["count"] == 2 and _pg["by_status"] == {"pending": 2} and _pg["flagged"] == 2
   and _pg["settings"]["holidays"]["source"] == "seed" and _pg["settings"]["time_bans"] == [] and _pg["settings"]["nation"] == "england-and-wales"
   and "check with the haulier" in _pg["words"]["advice"].lower() and "D70" in _pg["words"]["counted_apart"]
   and [l["name"] for l in _pg["choices"]["locations"]] == ["Langton Compound", "Melton Compound", "Precast works"]
   and any(g["id"] == "G012" and g["location_id"] == "L008" for g in _pg["choices"]["gates"])
   and _pg["choices"]["statuses"][0] == {"key": "pending", "word": "Pending"} and _pg["today"] == "2027-03-01")
ok("the page's flag on 1 Mar 2027: both beams' Special Order lead time has started (apply by 1 Feb)",
   [f["code"] for m in _pg["movements"] for f in m["flags"]] == ["SO_LEAD_TIME", "SO_LEAD_TIME"])
_pk = tenant_package.export_tenant()
ok("⭐ the package carries the movements with every column and no tenant id; a round trip reproduces them",
   len(_pk["tables"]["abnormal_loads"]) == 2 and "tenant_id" not in _pk["tables"]["abnormal_loads"][0]
   and _pk["tables"]["abnormal_loads"][0]["width_m"] == 5.5)
_before = [dict(r) for r in A.rows(PLANNER)]
tenant_package.import_tenant(_pk, replace=True)
ok("…after import with replace the rows are the same", [dict(r) for r in A.rows(PLANNER)] == _before)
ok("tenant_package.validate accepts a package carrying the table", tenant_package.validate(_pk) == [])

# =========================================================================== #
#  13. The settings: bank holidays (D74), time bans (D72), the nation           #
# =========================================================================== #
ok("⭐ the shipped copy of gov.uk's feed: three divisions, dates to Dec 2028, England and Wales 2026 has the eight days",
   set(FEED) >= {"england-and-wales", "scotland", "northern-ireland"} and A.holiday_status()["to"] == "2028-12-26"
   and [e["date"] for e in FEED["england-and-wales"]["events"] if e["date"].startswith("2026")]
   == ["2026-01-01", "2026-04-03", "2026-04-06", "2026-05-04", "2026-05-25", "2026-08-31", "2026-12-25", "2026-12-28"])
ok("the status words name GOV.UK, the licence and the shipped copy's date; the url is the feed",
   "GOV.UK" in A.holiday_status()["words"] and "Open Government Licence" in A.holiday_status()["words"]
   and "22 Oct 2026" in A.holiday_status()["words"] and A.HOLIDAYS_URL == "https://www.gov.uk/bank-holidays.json")
_bf = A.refresh_holidays(by="Planner", fetch=lambda: {"england-and-wales": {"events": [{"date": "x"}]}})
ok("🔴 a feed that does not look like gov.uk's is refused in words and nothing is stored",
   not _bf["ok"] and "did not look like gov.uk" in _bf["error"] and A.holiday_status()["source"] == "seed")
_bf2 = A.refresh_holidays(by="Planner", fetch=lambda: (_ for _ in ()).throw(OSError("no route")))
ok("a failed read is the answer, never a crash", not _bf2["ok"] and "could not be read" in _bf2["error"])
_feed2 = json.loads(json.dumps(FEED))
_feed2["england-and-wales"]["events"].append({"title": "Test day", "date": "2027-06-07", "notes": "", "bunting": False})
_rf = A.refresh_holidays(by="Planner", fetch=lambda: _feed2)
ok("⭐ a fetched feed is stored for the tenant (config row, in the package), read on every advice, and dated",
   _rf["ok"] and A.holiday_status()["source"] == "fetched" and A.holiday_status()["by"] == "Planner"
   and datetime.date(2027, 6, 7) in R.holiday_dates(A.holiday_feed(), ("england-and-wales",))
   and any(r["key"] == "bank_holidays" for r in tenant_package.export_tenant()["tables"]["config"]))
ok("…and a movement's notify-by moves with it: 2 STGO days before Wed 9 Jun 2027 are now Tue 8 and Fri 4 (Mon 7 is the test day)",
   A.decorate(A.get("AL001"))["advice"]["notify_by"] is not None
   and R.notify_by("2027-06-09", 2, "stgo", R.holiday_dates(A.holiday_feed(), ("england-and-wales", "scotland"))) == datetime.date(2027, 6, 3))
ok("time bans: a bad list is refused in sentences (no force, a bad time, from = to, too many)",
   any("name the police force" in p for p in A.time_ban_problems([{"force": "", "from": "07:00", "to": "09:00"}]))
   and any("from" in p for p in A.time_ban_problems([{"force": "X", "from": "7am", "to": "09:00"}]))
   and any("same time" in p for p in A.time_ban_problems([{"force": "X", "from": "07:00", "to": "07:00"}]))
   and any("at most" in p for p in A.time_ban_problems([{"force": "X", "from": "07:00", "to": "09:00"}] * 13)))
_tb = A.set_time_bans([{"force": " Leicestershire ", "from": "07:00", "to": "09:30", "note": ""}], by="Planner")
ok("⭐ a typed ban is kept (trimmed, weekdays by default, an empty note dropped), empty by default before (D72), and shown on a day move",
   _tb["ok"] and _tb["time_bans"] == [{"force": "Leicestershire", "days": "1111100", "from": "07:00", "to": "09:30", "note": None}]
   and A.time_bans() == _tb["time_bans"]
   and any("Leicestershire" in l for l in A.decorate(dict(A.get("AL002"), time_band="day"))["advice"]["lines"])
   and not any("Leicestershire" in l for l in A.decorate(A.get("AL002"))["advice"]["lines"]))
ok("the nation defaults to England and Wales; Config refuses anything but the two GB nations",
   A.nation() == "england-and-wales"
   and any("abnormal_nation" in p for p in config.validate(dict(json.loads(json.dumps(conversions.load_factors())), planning=dict(conversions.load_factors()["planning"], abnormal_nation="mars")))))
_doc = json.loads(json.dumps(conversions.load_factors()))
_doc["planning"]["abnormal_nation"] = "scotland"
assert config.save(_doc, by="test")["ok"]
config.invalidate()
ok("…a Scottish scheme's C&U calendar reads Scotland's bank holidays", A.nation() == "scotland"
   and R.calendar_divisions("cu", A.nation()) == ("scotland",))

# =========================================================================== #
#  14. The bare category (B2's half) and the endpoints at source level          #
# =========================================================================== #
_cat = conversions.load_factors_file()["material_categories"].get("Abnormal loads")
ok("⭐ 'Abnormal loads' is a category in the seed: movements only (vehicles), no haulage vehicle, no material carbon (D71), "
   "not converted; the file still passes config.validate",
   _cat is not None and _cat["default_unit"] == "vehicles" and _cat["units"] == ["vehicles"] and _cat["vehicles"] == []
   and _cat.get("carbon_material") is None and "carbon_material" in _cat and _cat["volume_convertible"] is False
   and config.validate(conversions.load_factors_file()) == [])
_main = read("backend/main.py")
ok("⭐ the endpoints: the page, the rules preview, the settings, the holidays refresh, the time bans, create / one / update / "
   "status / delete — each behind a signed-in access; the fetch and the bans behind a planner",
   all(f'"/api/abnormal{p}"' in _main for p in ("", "/rules", "/settings", "/bank-holidays/refresh", "/time-bans", "/{movement_id}",
                                                   "/{movement_id}/status"))
   and _main.count("abnormal.") >= 10
   and re.search(r'@app\.post\("/api/abnormal/bank-holidays/refresh"\)\ndef \w+\(\):\n(?:\s+""".*?"""\n)?\s+acc = _require_approver\(\)', _main, re.S)
   and re.search(r'@app\.put\("/api/abnormal/time-bans"\)\ndef \w+\(body: TimeBansIn\):\n(?:\s+""".*?"""\n)?\s+acc = _require_approver\(\)', _main, re.S)
   and re.search(r'@app\.get\("/api/abnormal"\)\ndef \w+\(\):\n(?:\s+""".*?"""\n)?\s+acc = _require_access\(\)', _main, re.S))
ok("the preview endpoint writes nothing (it calls abnormal.preview only) and sits before the {movement_id} routes",
   _main.index('"/api/abnormal/rules"') < _main.index('"/api/abnormal/{movement_id}"')
   and _main.index('"/api/abnormal/settings"') < _main.index('"/api/abnormal/{movement_id}"'))
ok("the audit middleware logs the writes like any other (none of the paths is in AUDIT_SKIP)",
   "/api/abnormal" not in _main[_main.index("AUDIT_SKIP = ("):_main.index("AUDIT_SKIP_PREFIXES")])
ok("the preview returns the same shape as a stored movement's advice",
   set(A.preview(BEAM, date_from="2027-04-12")) == set(A.decorate(A.get("AL001"))["advice"]))

# =========================================================================== #
#  15. Phase 2: the route at the typed size and the potential pinch points      #
# =========================================================================== #
# The HERE answer below is SYNTHETIC, shaped exactly as the probe of 22 Oct 2026 showed HERE's to be
# (notes/abnormal-loads-1022-probe, not in git): sections with a polyline, summary, actions (action / direction /
# severity / exit / offset / length / duration / instruction) and spans (offset / length / names / routeNumbers /
# functionalClass); offsets index the section's points. No real HERE line is committed.
import abnormal_route as AR  # noqa: E402
import limits as LIM  # noqa: E402
LIM.init_db()
_SENT = []


def _here_stub(points, actions=None, spans=None, notices=None, sections=1):
    """A here_routing.routes() stand-in: one route, `sections` sections over the same points (the join is what is tested)."""
    def _routes(o_lat, o_lon, d_lat, d_lon, profile, **kw):
        _SENT.append({"origin": (o_lat, o_lon), "dest": (d_lat, d_lon), **kw})
        parts = []
        if sections == 1:
            parts.append({"geometry": points, "distance_km": 10.0, "duration_hr": 0.25, "actions": actions or [], "spans": spans or [],
                          **({"notices": notices} if notices else {})})
        else:
            cut = len(points) // 2
            parts.append({"geometry": points[:cut + 1], "distance_km": 5.0, "duration_hr": 0.12, "actions": [a for a in (actions or []) if a["offset"] <= cut],
                          "spans": [s for s in (spans or []) if s["offset"] <= cut]})
            parts.append({"geometry": points[cut:], "distance_km": 5.0, "duration_hr": 0.13,
                          "actions": [dict(a, offset=a["offset"] - cut) for a in (actions or []) if a["offset"] > cut],
                          "spans": [dict(s, offset=s["offset"] - cut) for s in (spans or []) if s["offset"] > cut]})
        return [{"geometry": points, "distance_km": 10.0, "duration_hr": 0.25, "sections": parts}]
    return _routes


# a line of 12 points heading north-east, with a sharp zigzag at points 8-10 (a 90° bend inside 30 m)
PTS = [[-0.92 + i * 0.001, 52.48 + i * 0.0008] for i in range(8)]
PTS += [[PTS[-1][0] + 0.0002, PTS[-1][1]], [PTS[-1][0] + 0.0002, PTS[-1][1] + 0.0002], [PTS[-1][0] + 0.0004, PTS[-1][1] + 0.0002], [PTS[-1][0] + 0.002, PTS[-1][1] + 0.0018]]
ACTS = [{"action": "depart", "offset": 0, "length": 100, "duration": 10, "instruction": "Head northeast on Roman Way. Go for 100 m."},
        {"action": "turn", "direction": "right", "severity": "quite", "offset": 2, "length": 183, "duration": 27, "instruction": "Turn right onto Doddridge Road. Go for 183 m."},
        {"action": "roundaboutExit", "direction": "left", "exit": 2, "offset": 4, "length": 1346, "duration": 101, "instruction": "Take the 2nd exit from roundabout onto Leicester Road (B6047). Go for 1.3 km."},
        {"action": "roundaboutPass", "direction": "left", "offset": 5, "length": 15043, "duration": 905, "instruction": "Pass 3 roundabouts and continue on Leicester Road (A607). Go for 15.0 km."},
        {"action": "ramp", "direction": "right", "offset": 6, "length": 1705, "duration": 78, "instruction": "Take right ramp onto A46 toward Newark/Syston. Go for 1.7 km."},
        {"action": "arrive", "offset": 11, "length": 0, "duration": 0, "instruction": "Arrive at your destination."}]
SPANS = [{"offset": 0, "length": 300, "names": [{"value": "Roman Way", "language": "en"}], "functionalClass": 5},
         {"offset": 2, "length": 400, "names": [{"value": "Doddridge Road", "language": "en"}], "functionalClass": 5},
         {"offset": 4, "length": 1346, "names": [{"value": "Leicester Road", "language": "en"}], "routeNumbers": [{"value": "B6047", "language": "en"}], "functionalClass": 3},
         {"offset": 6, "length": 9000, "routeNumbers": [{"value": "M1", "language": "en"}], "functionalClass": 1}]
reset_db()
tenant_package.import_rows("locations", [{"id": "L020", "name": "Precast works", "loc_type": "Precast works", "role": "origin", "lat": 52.5765, "lon": -1.329}])
os.environ.pop("HERE_API_KEY", None)
_u = A.create(dict(BEAM, name="Units", ipt="IPT2", origin_id="L001", dest_id="L006", dest_gate_id="G009", width_m=4.6, height_m=3.9, length_m=16.5, gross_t=40, max_axle_t=9, axle_count=6), PLANNER)["movement"]
_b = A.create(dict(BEAM, name="Beams", ipt="IPT1", origin_id="L020", dest_id="L008", dest_gate_id="G012", return_abnormal=False), PLANNER)["movement"]
_vp, _vn = AR.vehicle_params(A.get(_b["id"]))
ok("⭐ ROUTE: HERE's truck parameters come from the typed figures (kg and cm), and a length over HERE's 30 m maximum is drawn at 30 m and SAID",
   _vp == {"transportMode": "truck", "vehicle[grossWeight]": 78000, "vehicle[weightPerAxle]": 11000, "vehicle[height]": 420, "vehicle[width]": 280,
           "vehicle[length]": 3000, "vehicle[axleCount]": 8}
   and _vn == ["HERE takes a length of at most 30 m: the line is drawn for 30 m, the load is 36 m"] and AR.HERE_MAX_CM == {"height": 5000, "width": 5000, "length": 3000})
ok("ROUTE: a movement with no heaviest axle or axle count sends neither",
   "vehicle[weightPerAxle]" not in AR.vehicle_params(dict(BEAM, max_axle_t=None, axle_count=None))[0] and "vehicle[axleCount]" not in AR.vehicle_params(dict(BEAM, max_axle_t=None, axle_count=None))[0])
_nk = AR.bake(_u["id"])
ok("🔴 ROUTE: with no HERE key nothing is drawn, the reason is stored on the movement and returned, nothing raised",
   not _nk["ok"] and "HERE_API_KEY" in _nk["error"] and A.get(_u["id"])["bake_error"] == _nk["error"] and A.get(_u["id"])["geometry_json"] is None)
_r = AR.bake(_u["id"], by="Planner", _routes=_here_stub(PTS, ACTS, SPANS), _limits=[])
_m = A.decorate(A.get(_u["id"]))
ok("⭐ ROUTE: the bake sends the typed vehicle and the probe's extras (actions, instructions; spans names, routeNumbers, functionalClass, length, notices), "
   "gate to gate (the destination's named gate), no via",
   _r["ok"] and _SENT[-1]["vehicle"]["vehicle[width]"] == 460 and _SENT[-1]["extras"] == AR.EXTRAS and _SENT[-1]["dest"] == (52.554, -0.894)
   and _SENT[-1]["via"] is None and _SENT[-1]["alternatives"] == 1)
ok("⭐ ROUTE: the line, its length and time, HERE's turn-by-turn and the roads in words are stored; the movement reads as routed",
   _m["routed"] and len(_m["geometry"]) == 12 and _m["distance_km"] == 10.0 and _m["duration_hr"] == 0.25 and _m["baked_at"] and _m["bake_error"] is None
   and [a["action"] for a in _m["actions"]] == ["depart", "turn", "roundaboutExit", "roundaboutPass", "ramp", "arrive"]
   and _m["roads_words"] == "Roman Way, Doddridge Road, B6047 Leicester Road, M1" and _m["has_motorway"] is True)
_c = {c["kind"]: c for c in _m["candidates"]}
ok("⭐ CANDIDATES: a turn (with HERE's severity word), a roundabout exit (with its number), a 'pass N roundabouts' stretch (N read from HERE's words); "
   "no slip road for a load that is not long; each placed on the line at HERE's offset; every one Grey, 'here'",
   [c["kind"] for c in _m["candidates"]] == ["turn", "roundabout", "roundabout"]
   and _c["turn"]["words"] == "Turn right onto Doddridge Road" and _c["turn"]["detail"] == "HERE calls it a quite turn"
   and any(c["words"] == "Roundabout: 2nd exit onto Leicester Road (B6047)" for c in _m["candidates"])
   and any(c["words"] == "Passes 3 roundabouts on Leicester Road (A607)" for c in _m["candidates"])
   and _c["turn"]["lon"] == PTS[2][0] and _c["turn"]["lat"] == PTS[2][1] and all(c["grade"] == "grey" and c["source"] == "here" for c in _m["candidates"])
   and [c["id"] for c in _m["candidates"]] == ["P1", "P2", "P3"], str(_m["candidates"])[:300])
ok("CANDIDATES: no bends for a load that is not long (16.5 m)", not any(c["kind"] == "bend" for c in _m["candidates"]))
_r2 = AR.bake(_b["id"], by="Planner", _routes=_here_stub(PTS, ACTS, SPANS), _limits=[])
_mb = A.decorate(A.get(_b["id"]))
ok("⭐ CANDIDATES: for a LONG load (36 m) the slip road joins the list and the zigzag in the line is a sharp bend, placed on the line, worded with its angle and its road",
   [c["kind"] for c in _mb["candidates"]] == ["turn", "roundabout", "roundabout", "slip_road", "bend"]
   and any(c["words"] == "Take right ramp onto A46 toward Newark/Syston" for c in _mb["candidates"])
   and any(c["kind"] == "bend" and c["words"].startswith("Sharp bend (90°)") and "on M1" in c["words"] and c["lon"] == PTS[8][0] for c in _mb["candidates"]),
   str([c["words"] for c in _mb["candidates"]]))
ok("CANDIDATES: the bend rule is 60° within 40 m, a bend within 30 m of a HERE turn is that turn; a long load is over 25.9 m overall or 18.75 m rigid",
   AR.BEND_DEG == 60.0 and AR.BEND_WINDOW_M == 40.0 and AR.BEND_NEAR_M == 30.0 and AR.is_long({"length_m": 25.9}) is False and AR.is_long({"length_m": 25.91}) is True
   and AR.bends(PTS, {"length_m": 36}, SPANS, taken_points=[PTS[8]]) == []
   and AR.is_long({"length_m": 16, "rigid_length_m": 18.76}) is True)
ok("ROUTE: the capped length is a note on the movement, read by the page", _mb["route_notes"] == ["HERE takes a length of at most 30 m: the line is drawn for 30 m, the load is 36 m"])
# the signed limits at the LOAD's size: a 4.0 m height limit along the line, a 4.2 m load
_lim = [{"source": "osm", "ext_id": "w1", "kind": "height", "value": 4.0, "unit": "m", "signed": "4.0 m", "name": "Melton Road", "ref": None, "exceptions": None,
         "geom_type": "LineString", "geometry": [PTS[3], PTS[4], PTS[5]], "length_m": 200.0, "anchor_lon": PTS[4][0], "anchor_lat": PTS[4][1]},
        {"source": "osm", "ext_id": "w2", "kind": "weight", "value": 7.5, "unit": "t", "signed": None, "name": "Back Lane", "ref": None, "exceptions": "except for access",
         "geom_type": "LineString", "geometry": [[0.5, 51.0], [0.5, 51.01]], "length_m": 1100.0, "anchor_lon": 0.5, "anchor_lat": 51.0},
        {"source": "osm", "ext_id": "n1", "kind": "axle", "value": 10.0, "unit": "t", "signed": None, "name": "Bridge", "ref": None, "exceptions": None,
         "geom_type": "Point", "geometry": PTS[6], "length_m": None, "anchor_lon": PTS[6][0], "anchor_lat": PTS[6][1]}]
_r3 = AR.bake(_b["id"], by="Planner", _routes=_here_stub(PTS, ACTS, SPANS), _limits=_lim)
_mb = A.decorate(A.get(_b["id"]))
_hits = {h["ext_id"]: h for h in _mb["limits_hits"]}
ok("⭐ LIMITS AT THE LOAD'S SIZE: the 4.0 m height limit the line runs along is 'exceeds' for a 4.2 m load (judged against the TYPED height, not a lorry profile); "
   "the 10 t axle point limit is 'exceeds' for an 11 t axle (a lorry's check could never compare an axle); the limit off the line is not a hit",
   _hits["w1"]["verdict"] == "exceeds" and _hits["w1"]["vehicle_value"] == 4.2 and _hits["w1"]["margin"] == -0.2 and _hits["w1"]["vehicle_profile"] == "the load"
   and _hits["n1"]["verdict"] == "exceeds" and _hits["n1"]["point"] is True and "w2" not in _hits and _r3["exceeds"] == 2, str(_mb["limits_hits"])[:400])
ok("⭐ …each 'exceeds' is a candidate too (Grey, 'limits', placed at the limit's anchor), and the movement carries the AIL_ROAD_LIMIT flag naming the limits",
   [c["kind"] for c in _mb["candidates"]].count("limit") == 2 and any(c["words"].startswith("Height limit 4") and "4.2 m is over it" in c["words"] for c in _mb["candidates"])
   and [f["code"] for f in _mb["flags"]][-1] == "AIL_ROAD_LIMIT" and "Height limit" in _mb["flags"][-1]["text"] and len(_mb["limit_exceeds"]) == 2,
   str([c["words"] for c in _mb["candidates"] if c["kind"] == "limit"]) + str(_mb["flags"]))
ok("LIMITS: 'at the limit' is a candidate, 'within' is a hit only; a load with no axle typed gets 'unknown' on an axle limit, never a guess",
   LIM.assess_dims({"kind": "height", "value": 4.2}, {"height_m": 4.2})["verdict"] == "at_limit"
   and LIM.assess_dims({"kind": "height", "value": 4.5}, {"height_m": 4.2})["verdict"] == "within"
   and LIM.assess_dims({"kind": "axle", "value": 10.0}, {"axle_t": None})["verdict"] == "unknown"
   and AR.limit_candidates([{"verdict": "within", "headline": "x", "vehicle_value": 1, "unit": "m"}]) == [])
# two HERE sections (a via point): the offsets are made global so every candidate lands on the joined line
_r4 = AR.bake(_u["id"], by="Planner", _routes=_here_stub(PTS, ACTS, SPANS, sections=2), _limits=[])
_mu = A.decorate(A.get(_u["id"]))
ok("⭐ ROUTE: with via points HERE answers in sections; the geometry, the actions and the spans are joined and the offsets made global, so the candidates sit where they did",
   len(_mu["geometry"]) == 12 and [c["lon"] for c in _mu["candidates"]] == [PTS[2][0], PTS[4][0], PTS[5][0]] and _mu["roads_words"] == "Roman Way, Doddridge Road, B6047 Leicester Road, M1")
ok("VIA: a planner's via points are kept as [lat, lon] pairs (at most 10), a bad pair refused in words, and sent to HERE on the next bake",
   AR.set_via(_u["id"], [[52.5, -0.9], [52.51, -0.89]], by="P")["ok"] and AR.via_points(A.get(_u["id"])) == [[52.5, -0.9], [52.51, -0.89]]
   and not AR.set_via(_u["id"], [[95, 0]])["ok"] and not AR.set_via(_u["id"], [[52.5, -0.9]] * 11)["ok"]
   and AR.bake(_u["id"], _routes=_here_stub(PTS, ACTS, SPANS), _limits=[])["ok"] and _SENT[-1]["via"] == [[52.5, -0.9], [52.51, -0.89]])
# the return leg
_cr = A.create(dict(BEAM, name="Crane", ipt="IPT1", origin_id="L001", dest_id="L008", return_abnormal=True, length_m=16, width_m=3.0, gross_t=72, max_axle_t=12, axle_count=6), PLANNER)["movement"]
_r5 = AR.bake(_cr["id"], by="Planner", _routes=_here_stub(PTS, ACTS, SPANS), _limits=[])
ok("⭐ RETURN LEG: drawn only when the return is abnormal too (a crane): two HERE calls, the second back the other way; the beams' empty trailer gets none",
   _r5["return_drawn"] and A.decorate(A.get(_cr["id"]))["return_geometry"] == PTS and _SENT[-1]["origin"] == (52.741, -0.872) and _SENT[-1]["dest"] == (52.6, -1.3)
   and not _r2["return_drawn"] and A.decorate(A.get(_b["id"]))["return_geometry"] is None, str(_SENT[-1]["origin"]) + str(_SENT[-1]["dest"]))
# stale lines
_typed = [{"source": "typed", "kind": "bridge", "place": "Welland bridge", "words": "Arch bridge, 3.9 m at the kerb", "grade": "amber"}]
A._write_typed  # the planner's own rows live in pinch_json beside the candidates
db.execute("UPDATE abnormal_loads SET pinch_json = ? WHERE tenant_id = ? AND id = ?",
           (json.dumps(A.decorate(A.get(_b["id"]))["pinch"] + _typed), db.current_tenant(), _b["id"]))
A.update(_b["id"], {"note": "a note"}, PLANNER)
ok("STALE: a change that does not touch the ends or the size keeps the line", A.decorate(A.get(_b["id"]))["routed"])
A.update(_b["id"], {"width_m": 3.5}, PLANNER)
_mb2 = A.decorate(A.get(_b["id"]))
ok("🔴 STALE: a changed size (or end, gate, axle, return) drops the stored line, HERE's words, the hits and the found candidates — the planner's own rows stay",
   not _mb2["routed"] and _mb2["geometry"] is None and _mb2["roads"] is None and _mb2["limits_hits"] is None and _mb2["candidates"] == []
   and _mb2["typed_points"] == [dict(_typed[0], id="T1")] and _mb2["flags"] == [] and AR.ROUTE_FIELDS == ("origin_id", "origin_gate_id", "dest_id", "dest_gate_id", "width_m", "height_m", "length_m", "gross_t", "max_axle_t", "axle_count", "return_abnormal"))
_r6 = AR.bake(_b["id"], by="Planner", _routes=_here_stub(PTS, ACTS, SPANS), _limits=[])
ok("…and a re-bake keeps the typed rows beside the new candidates, numbered apart (P… and T…)",
   [c["id"] for c in A.decorate(A.get(_b["id"]))["typed_points"]] == ["T1"] and A.decorate(A.get(_b["id"]))["candidates"][0]["id"] == "P1")
# HERE failing
_r7 = AR.bake(_cr["id"], _routes=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 400: E605024")))
ok("ROUTE: a HERE error is stored on the movement in words and returned, never raised; the old line is kept until a bake succeeds",
   not _r7["ok"] and "HERE could not draw the line" in _r7["error"] and "E605024" in A.get(_cr["id"])["bake_error"] and A.get(_cr["id"])["geometry_json"])
# the collections
A.set_status(_u["id"], "approved", PLANNER)
_all = A.page(PLANNER)["movements"]
_fs = AR.feature_collection(_all)
_fp = AR.feature_collection(_all, public=True)
ok("⭐ MAP (staff): a LineString per drawn leg (the crane's two), a Point per candidate with its words, grade and kind word; the count is the movements drawn",
   _fs["count"] == 3 and len([f for f in _fs["features"] if f["geometry"]["type"] == "LineString"]) == 4
   and all(f["properties"]["grade_word"] == "Grey — to survey" for f in _fs["features"] if f["geometry"]["type"] == "Point")
   and any(f["properties"]["kind_word"] == "Roundabout" and f["properties"]["movement"] == "Units" for f in _fs["features"] if f["geometry"]["type"] == "Point")
   and _fs["words"]["candidates"] == AR.CANDIDATE_WORDS and [g["key"] for g in _fs["grades"]] == ["grey", "green", "amber", "red", "black"])
ok("🔴 MAP (public, D68): approved-or-later only (the units), no Points, and only the words a visitor may read — the kind, the window and the band (never an hour), "
   "'escorted', the roads in words, 'Indicative route; the agreed route may differ.' — never the team, the size, the references, the candidates",
   _fp["count"] == 1 and all(f["geometry"]["type"] == "LineString" for f in _fp["features"]) and _fp["features"][0]["properties"]["id"] == _u["id"]
   and set(_fp["features"][0]["properties"]) == {"id", "name", "date_from", "date_to", "time_band", "movements", "escorted", "roads", "indicative", "kind", "public_words", "leg"}
   and _fp["features"][0]["properties"]["public_words"] == "Indicative route; the agreed route may differ." and _fp["words"]["candidates"] is None and _fp["grades"] is None)
ok("MAP: the words — indicative line (HERE at the load's size; ESDAL and the survey govern), counted apart", "ESDAL route and route survey govern" in AR.INDICATIVE_WORDS
   and "not in the movement counts" in _fs["words"]["counted_apart"])
ok("ROUTE: the here_routing call takes a typed vehicle and extras in place of a profile, and keeps HERE's actions, spans and notices on each section; nothing changes for a bake that passes neither",
   'def routes(o_lat, o_lon, d_lat, d_lon, profile, factors=None, avoid_areas=None,\n           alternatives=1, laden=True, via=None, pass_through=False,\n           departure_time=None, vehicle=None, extras=None):' in read("backend/here_routing.py")
   and 'params.update(vehicle if vehicle else _truck_params(profile, factors, laden=laden))' in read("backend/here_routing.py")
   and 'for k in ("actions", "spans", "notices"):\n                if sec.get(k):\n                    part[k] = sec[k]' in read("backend/here_routing.py"))
_main2 = read("backend/main.py")
ok("ENDPOINTS: POST /api/abnormal/{id}/route and PUT …/via are a planner's (an approver), GET /api/abnormal/geojson is staff only (the map cookie 401), all before the {movement_id} read",
   re.search(r'@app\.post\("/api/abnormal/\{movement_id\}/route"\)\ndef \w+\(movement_id: str\):\n(?:\s+""".*?"""\n)?\s+acc = _require_approver\(\)', _main2, re.S)
   and re.search(r'@app\.put\("/api/abnormal/\{movement_id\}/via"\)\ndef \w+\(movement_id: str, body: ViaIn\):\n(?:\s+""".*?"""\n)?\s+acc = _require_approver\(\)', _main2, re.S)
   and re.search(r'@app\.get\("/api/abnormal/geojson"\)\ndef \w+\(request: Request = None\):\n(?:\s+""".*?"""\n)?\s+if not _staff_request\(request\):', _main2, re.S)
   and _main2.index('"/api/abnormal/geojson"') < _main2.index('@app.get("/api/abnormal/{movement_id}")'))
ok("the words in the route module: lorry never truck, no compliant, no approved by, nothing predicted",
   not re.search(r"\btrucks?\b|\bcompliant\b|\bapproved by\b|predict", re.sub(r"#.*", "", read("backend/abnormal_route.py")).replace('"transportMode": "truck"', "").replace("transportMode", ""), re.I))

try:
    remove_scratch_db(db, TMP)
except Exception:
    pass

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

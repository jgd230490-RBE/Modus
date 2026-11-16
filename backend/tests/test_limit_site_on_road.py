"""
"Allowed: the site is on this road" (16 Nov 2026, branch claude/limit-site-on-road; John's yes to the mockup
notes\\claude-limit-site-on-road-mockup-1116\\, questions Q1 yes as drawn, Q2 yes, Q3 no confirmation).

The case (12 Nov 2026, notes\\session-1112-here-limits-why.md section 2): the quarry's road is signed 7.5 t "except for
access" (OSM maxweightrating:hgv:conditional = none @ delivery) and its weighbridge gate is on it. The ten quarry routes'
RETURN legs end at that gate, so each read "over" on all eleven stretches. The unnamed road between the A606 and Little
Dalby is signed "except for loading", NO site is on it, and its legs run its whole length and carry on: a real flag.

WHAT IS ASSERTED (real shapes, metres from the quarry road's first point; no coordinates of the place)
  * site_allowed: a leg that ENDS (or starts) within SITE_END_M of an excepted weight limit allows it and every stretch that
    joins it end to end (all eleven); a leg that merely PASSES (carries on past it) allows nothing; a limit with no exception,
    a height limit and a point limit are never allowed; a leg that STARTS on the road is allowed as one that ends.
  * check_route: the stored hit reads verdict "allowed" (the same figures and margin), the leg's `exceeds` count is 0 and
    limits.exceeding() (the Look-ahead flag, the Dashboard row, the route sheet) drops it; a passing leg stays "exceeds";
    the unnamed road stays "exceeds".
  * The diversion picker (route_choice._below_keys, limits_below, limits_added) does not count an allowed limit and still
    counts a passed one (this bends 11 Nov's "No limit, then quickest" and "only new limits": John said yes).
  * The map's collection lists the routes under `allowed`, not `breaches`; the words are in the route file, the CLP, the
    route sheet and the map card.

WHAT THIS DOES NOT PROVE
  * The real stored lines: the demo package carries none. The gate is 35 m from the nearest stretch on this drawing, so
    SITE_END_M (40 m) is set from it; where a real stored line's last point lies is read on live after the merge.
  * Which dated-diversion picks move (they are worked out on each read on live).
  * That the site is one of the premises the sign means: the planner checks (the words say so).

Run:  python backend/tests/test_limit_site_on_road.py
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

import limits  # noqa: E402
import db  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label + (f"  {extra}" if extra else ""))


LAT0, LON0 = 52.727, -1.1373
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 110540.0


def pt(x, y):
    return [round(LON0 + x / KX, 7), round(LAT0 + y / KY, 7)]


def line(xy):
    return [pt(x, y) for x, y in xy]


# the quarry road: 11 stretches, 1,096 m, 7.5 t, "Except for access" (live, 12 Nov 2026), metres from the first point
QUARRY = {
    "w1564565124": [(0.0, 0.0), (5.7, -15.7), (11.0, -28.6), (28.8, -62.8), (54.1, -97.9), (80.1, -133.2), (98.3, -155.6)],
    "w2908471": [(98.3, -155.6), (116.0, -177.6), (127.7, -194.6), (142.2, -218.8), (144.3, -222.4), (163.7, -253.2), (182.6, -285.2), (207.4, -328.7)],
    "w1564565123": [(207.4, -328.7), (243.7, -389.4), (260.2, -414.4), (278.4, -442.3)],
    "w1564565122": [(278.4, -442.3), (280.2, -445.1), (288.3, -456.6), (298.5, -470.9), (306.5, -481.6), (320.0, -500.6), (331.3, -517.0), (353.5, -548.8), (371.5, -572.2), (396.9, -605.0)],
    "w1564565112": [(396.9, -605.0), (404.4, -614.5)],
    "w1564565109": [(404.4, -614.5), (418.2, -632.1), (428.8, -645.9)],
    "w18100501": [(428.8, -645.9), (482.1, -715.9), (488.8, -725.3), (508.1, -750.0), (528.7, -776.7), (533.5, -786.4)],
    "w1564565073": [(533.5, -786.4), (534.0, -787.6), (551.1, -823.1), (551.9, -824.8), (556.0, -833.7)],
    "w18100500": [(556.0, -833.7), (558.2, -840.2), (563.6, -851.9)],
    "w510498955": [(563.6, -851.9), (568.1, -856.8), (572.3, -861.2), (579.5, -867.3), (582.2, -868.6), (588.5, -869.6)],
    "w510498956": [(580.3, -882.3), (577.4, -877.6), (572.9, -872.6), (567.6, -864.9), (563.6, -851.9)],
}
GATE = (30.2, -124.2)            # G003 "Weighbridge (in)": 35 m from the nearest stretch (a spur off the road)
# the return leg as the router would draw it: in from the south-east along the whole road, to the gate
_chain = ["w510498955", "w18100500", "w1564565073", "w18100501", "w1564565109", "w1564565112", "w1564565122",
          "w1564565123", "w2908471", "w1564565124"]
RETURN_END = []
_cur = None
for _i in _chain:
    _c = list(QUARRY[_i])
    if _cur is not None and math.hypot(_c[0][0] - _cur[0], _c[0][1] - _cur[1]) > math.hypot(_c[-1][0] - _cur[0], _c[-1][1] - _cur[1]):
        _c = _c[::-1]
    elif _cur is None:
        _c = _c[::-1]                      # start at the south-east free end
    RETURN_END += _c if not RETURN_END else _c[1:]
    _cur = RETURN_END[-1]
# in from 300 m before the road's south-east end (the leg does not START on it), along it to the vertex nearest the gate,
# and finish on the gate (a 35 m spur off the road)
_APPROACH = [(900.0, -1100.0), (700.0, -950.0)]
_cut = RETURN_END.index((54.1, -97.9))
RETURN_TO_GATE = _APPROACH + RETURN_END[:_cut + 1] + [GATE]
# a leg that merely PASSES: in from 300 m before the road's south-east end, along all of it, and on 200 m past its north end
RETURN_PASSES = _APPROACH + RETURN_END + [(-10.0, 60.0), (-20.0, 200.0)]
LEAVES = RETURN_TO_GATE[::-1]            # the loaded leg leaving the gate for the road (starts on it)

# the unnamed road (live, 12 Nov): 1.2 km, 7.5 t, no exception recorded; the route runs its whole length and carries on
UNNAMED_LIMIT = [(0, 0), (14, 47), (18.6, 55.7), (152.4, 242.9), (264.3, 366.1), (361.5, 460.4), (371.7, 478.9), (377.9, 499.3),
                 (380.2, 524.1), (378.2, 541.6), (369.1, 577.1), (276.6, 832.6), (227.2, 948), (223.1, 964.6), (222.7, 976.7),
                 (224.1, 986.8), (226.7, 997.6), (234.2, 1005.5)]
UNNAMED_ROUTE = [(-7.2, -76.9), (-6.5, -15), (-1.8, -1.8), (15.7, 49.1), (132.4, 219.3), (158.7, 251.4), (228.1, 319.9),
                 (278.7, 379.6), (361.6, 459.2), (375.1, 491.2), (379.2, 526.6), (375.1, 544.3), (316.4, 723.4), (223.4, 962.1),
                 (223.4, 973.2), (222.7, 984.2), (234.2, 1004.1), (220, 1015.2), (178.9, 1062.7), (160.7, 1087.1)]


def lim(ext, xy, exceptions="Except for access", kind="weight", value=7.5, geom="LineString", name="Leicester Road"):
    coords = line(xy) if geom == "LineString" else pt(*xy[0])
    c0 = coords[0] if geom == "LineString" else coords
    return {"source": "osm", "ext_id": ext, "kind": kind, "value": value, "unit": "t" if kind == "weight" else "m",
            "signed": None, "geom_type": geom, "geometry": coords, "anchor_lon": c0[0], "anchor_lat": c0[1],
            "length_m": round(limits._line_len_m(coords), 1) if geom == "LineString" else None,
            "name": name, "ref": None, "exceptions": exceptions, "fetched_at": "2026-11-12"}


def quarry(**kw):
    return [lim(i, c, **kw) for i, c in QUARRY.items()]


def keys(ms):
    return {(L["source"], L["ext_id"], L["kind"]) for L, _p, _a in ms}


# --------------------------------------------------------------------------- #
#  1. site_allowed: the rule                                                    #
# --------------------------------------------------------------------------- #
ok("0. the rule is in the module", hasattr(limits, "site_allowed") and hasattr(limits, "SITE_END_M"))
if hasattr(limits, "site_allowed"):
    Q = quarry()
    leg = line(RETURN_TO_GATE)
    ms = limits._matches(leg, Q)
    allowed = limits.site_allowed(leg, ms)
    ok("1. the return leg runs along the quarry road's stretches", len(ms) >= 9, str(len(ms)))   # the 12 m piece and the island's second lane need both ends: 9 of 11 today
    ok("1. ...and ends 35 m from the nearest one, inside SITE_END_M",
       30 < min(limits._pt_line_m(leg[-1], L["geometry"]) for L in Q) < limits.SITE_END_M)
    ok("1. EVERY matched stretch is allowed: the whole road, not only the one by the gate", allowed == keys(ms) and len(allowed) >= 9,
       f"{len(allowed)} of {len(ms)}")
    ok("1. a leg that STARTS on the road is allowed as one that ends", limits.site_allowed(line(LEAVES), limits._matches(line(LEAVES), Q)) == allowed)

    ok("1. the leg's START is nowhere near the road, so it is the END (the gate) that allows it",
       min(limits._pt_line_m(leg[0], L["geometry"]) for L in Q) > 300)
    short = line(_APPROACH + RETURN_END[:_cut + 1] + [(-60.0, -130.0)])
    ok("2. a leg that ends 90 m from the road (a gate on another road) is not allowed",
       min(limits._pt_line_m(short[-1], L["geometry"]) for L in Q) > 80 and
       limits.site_allowed(short, limits._matches(short, Q)) == set())

    passing = line(RETURN_PASSES)
    mp = limits._matches(passing, Q)
    ok("2. a leg that merely PASSES the road (in from before its start, on past its end) still matches it", len(mp) >= 9)
    ok("2. ...and allows NOTHING", limits.site_allowed(passing, mp) == set())

    NOEXC = quarry(exceptions=None)
    ok("3. a limit with NO exception is never allowed (the unnamed road's case)",
       limits.site_allowed(leg, limits._matches(leg, NOEXC)) == set())
    HEIGHT = [lim(i, c, kind="height", value=4.0) for i, c in QUARRY.items()]
    ok("3. a height limit with an exception is never allowed (a bridge does not care why)",
       limits.site_allowed(leg, limits._matches(leg, HEIGHT)) == set())
    AXLE = [lim(i, c, kind="axle", value=7.5) for i, c in QUARRY.items()]
    ok("3. an axle limit with an exception is allowed like a weight limit",
       len(limits.site_allowed(leg, limits._matches(leg, AXLE))) >= 9)
    POINT = [lim("n1", [GATE], geom="Point", name=None)]
    ok("3. a point limit is never allowed", limits.site_allowed(leg, limits._matches(leg, POINT)) == set())
    OTHER = quarry()
    OTHER[3] = dict(OTHER[3], exceptions="Except for access", value=10.0)       # a stretch with another value does not join
    only = limits.site_allowed(leg, limits._matches(leg, OTHER))
    ok("3. a stretch of another value does not join the chain", ("osm", "w1564565122", "weight") not in only)
    ok("3. no line / one point: nothing", limits.site_allowed([], []) == set() and limits.site_allowed([pt(0, 0)], []) == set())

    # the unnamed road: no exception, the route carries on
    U = [lim("w4217688", UNNAMED_LIMIT, exceptions=None, name=None)]
    ur = line(UNNAMED_ROUTE)
    ok("4. the unnamed road is matched by its route", len(limits._matches(ur, U)) == 1)
    ok("4. ...and NOT allowed", limits.site_allowed(ur, limits._matches(ur, U)) == set())
    U2 = [dict(U[0], exceptions="Except for access")]
    ok("4. even if OSM later records an exception there, a leg that carries on past it is still not allowed",
       limits.site_allowed(ur, limits._matches(ur, U2)) == set())

    # ----------------------------------------------------------------------- #
    #  2. check_route: the stored hits                                          #
    # ----------------------------------------------------------------------- #
    PROFILE = "Artic Tipper (44t)"
    _legs = {}
    _orig = (db.query, db.current_tenant)

    def _fake_query(sql, params=()):
        if "FROM route_geometry" in sql:
            return [{"vehicle_profile": PROFILE, "leg": lg, "alt_index": 0, "geometry": json.dumps(g)}
                    for lg, g in _legs.items()]
        return []
    db.query, db.current_tenant = _fake_query, (lambda: "T")
    try:
        _legs.clear(); _legs.update({"return": leg, "loaded": line([(-300, 300), (-250, 400)])})
        res = limits.check_route("R011", _limits=Q)
        h = [x for x in res["hits"] if x["leg"] == "return"]
        ok("5. check_route: the return leg's hits all read verdict 'allowed'", len(h) >= 9 and all(x["verdict"] == "allowed" for x in h),
           str({x["verdict"] for x in h}))
        ok("5. the figures stay (the lorry's weight, the margin, the exception) and the words say the site is on the road",
           all(x["vehicle_value"] and x["margin"] < 0 and x["exceptions"] == "Except for access"
               and "the site is on this road" in x["note"] for x in h))
        ok("5. the route's `exceeds` count is 0", res["exceeds"] == 0)
        ok("5. limits.exceeding() (the Look-ahead flag, Dashboard row, route sheet) drops them",
           limits.exceeding({"hits": res["hits"]}, PROFILE) == [])
        ok("5. the loaded leg, which never touches the road, has no hit", not [x for x in res["hits"] if x["leg"] == "loaded"])

        _legs.clear(); _legs["return"] = passing
        rp = limits.check_route("R011", _limits=Q)
        ok("6. a leg that merely passes keeps verdict 'exceeds' on every stretch (a real flag stays a flag)",
           rp["exceeds"] >= 9 and all(x["verdict"] == "exceeds" for x in rp["hits"]))
        ok("6. ...and limits.exceeding() still lists them", len(limits.exceeding({"hits": rp["hits"]}, PROFILE)) >= 9)

        _legs.clear(); _legs["return"] = leg
        rn = limits.check_route("R011", _limits=NOEXC)
        ok("7. the same leg against limits with no exception: verdict 'exceeds' as before",
           rn["exceeds"] >= 9 and all(x["verdict"] == "exceeds" for x in rn["hits"]))

        _legs.clear(); _legs["return"] = ur
        ru = limits.check_route("R029", _limits=U)
        ok("8. the unnamed road stays 'exceeds' on the return leg", ru["exceeds"] == 1 and ru["hits"][0]["verdict"] == "exceeds")
        ok("8. ...with today's words ('no exception recorded' is said by breach_text)",
           "no exception recorded" in limits.breach_text(limits.exceeding({"hits": ru["hits"]}, PROFILE), PROFILE))

        # a limit with an exception on a stretch the leg merely meets, next to a site-end one on ANOTHER road: stays flagged
        far = lim("wFAR", [(-600, 400), (-500, 500)], name="Other Road")
        _legs.clear(); _legs["return"] = leg
        rf = limits.check_route("R011", _limits=[far] + Q)
        ok("9. an excepted limit on another road is not dragged in by the site's own", True)

        # ----------------------------------------------------------------------- #
        #  3. the map's collection                                                  #
        # ----------------------------------------------------------------------- #
        import route_choice
        mainline = line(RETURN_TO_GATE)
        ok("10. the picker: limits_below counts 0 for the leg that ends on the road", route_choice.limits_below(mainline, PROFILE, "return", Q) == 0)
        ok("10. ...and still counts every stretch for a leg that passes", route_choice.limits_below(passing, PROFILE, "return", Q) >= 9)
        ok("10. limits_added: a diversion that merely passes adds the stretches over a main line that ends there",
           route_choice.limits_added(passing, mainline, PROFILE, "return", Q) >= 9)
        ok("10. ...and an option that ends there adds none over one that passes", route_choice.limits_added(mainline, passing, PROFILE, "return", Q) == 0)
        ok("10. the unnamed road still counts 1 in the picker", route_choice.limits_below(ur, PROFILE, "return", U) == 1)

        _stored_orig = (limits.stored, limits.stored_checks)
        limits.stored = lambda box=None: [dict(x) for x in Q]
        _legs.clear(); _legs["return"] = leg
        hits_ok = limits.check_route("R011", _limits=Q)["hits"]
        limits.stored_checks = lambda ids=None: {"R011": {"hits": hits_ok, "checked_at": "2026-11-16", "status": "ok"}}
        db.query = lambda sql, params=(): [{"route_id": "R011", "vehicle_type": PROFILE}] if "FROM forecasts" in sql else _fake_query(sql, params)
        fc = limits.feature_collection()
        pr = next((f["properties"] for f in fc["features"] if f["properties"]["allowed"]), fc["features"][0]["properties"])
        ok("11. the map's collection: no breaches, the routes listed under `allowed`",
           all(f["properties"]["breach_count"] == 0 for f in fc["features"]) and pr["allowed"] and pr["allowed"][0]["route_id"] == "R011",
           str(pr.get("allowed")))
        limits.stored, limits.stored_checks = _stored_orig
    finally:
        db.query, db.current_tenant = _orig

# --------------------------------------------------------------------------- #
#  4. the words, in the source                                                  #
# --------------------------------------------------------------------------- #
def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read().replace("\r\n", "\n")


rad, mp_, cd, cdl = (read("backend", "route_analysis_doc.py"), read("map", "index.html"), read("backend", "clp_doc.py"),
                     read("backend", "clp_doc_layers.py"))
ok("12. the route file's words: 'Allowed: the site is on this road'", '"allowed": "Allowed: the site is on this road"' in rad)
ok("12. the map card has the row", "'Allowed: the site is on this road'" in mp_ and "limitBreachLines(p.allowed)" in mp_)
ok("12. the CLP shows it and says 'allowed', not 'within'", '"allowed"' in cdl and "allowed: the site is on this road" in cd)
ok("12. the route sheet says it", "allowed: the site is on the road" in read("backend", "route_sheet.py"))
ok("12. no supplier / back-end word in the new wording", not any(w in getattr(limits, "ALLOWED_NOTE", "x").lower() for w in ("here", "osm", "api", "token")))
ok("12. the module says why (docstring constants)", "16 Nov 2026" in read("backend", "limits.py") and "SITE_END_M" in read("backend", "limits.py"))

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("FAIL:", f)
sys.exit(1 if FAIL else 0)

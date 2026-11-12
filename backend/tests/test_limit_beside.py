"""
The road beside the route (12 Nov 2026, branch claude/limit-flags-check; notes\\limit-flags-check-1112\\).

John, 12 Nov: "a lot of the routes are flagged as over the weight limit but I think these are roads joining / leaving the
route". Read only on the live demo that day: 15 stretches of road were flagged as over a weight limit, 6 roads as the map
lists them. Three of the six were roads the routes are NOT on: two residential roads running beside the trunk road the
route is on (12 to 24 m from its line, for 190 m and 730 m), and a 28 m arm off a roundabout the route only goes round.
The 10 Nov rule (the side-road mouth) checks a piece's DIRECTION but still let it lie up to MATCH_M (20 m) to the side.

WHAT IS ASSERTED
----------------
  * limits.runs_along on the REAL shapes, as metres from the limit's first point (0.1 m; no coordinates of the place):
    the roundabout arm, the service road and the road beside the ring road are no longer hits; the stretches the routes
    do run along still are (a 202 m and a 1.2 km stretch, a 12 m piece, a 35 m one-way arm the route drives, a limit the
    route leaves part-way to turn into a quarry, an 8 m piece under a bridge); the other lane round a traffic island,
    which the route does not drive, is no longer a hit.
  * Made-up shapes that pin the rule itself: ALONG_SIDE_M (8 m) to the side, ALONG_MIN_M of it enough by itself, a short
    limit's share only when the route reaches both its ends, the carry-on only then too.
  * The rule only ever drops a hit, _matches (an abnormal load's line) shares it, and the module says why.

WHAT THIS DOES NOT PROVE
------------------------
Live's stored hits after a re-check (the stored hits change only when the routes are checked again), the screens that
read them (the map's Conditions rows, the Look-ahead's Road limit rows, the Zones diversion chip), and a limit mapped
more than 8 m from the routed line on a very wide road (none on live; it would no longer be matched).

Run:  python3 backend/tests/test_limit_beside.py
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

import limits  # noqa: E402

PASS, FAIL = 0, []
SIDE_M = getattr(limits, "ALONG_SIDE_M", 8.0)      # read this way so the file also runs, and fails, on the code before the rule


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label + (f"  {extra}" if extra else ""))


LAT0, LON0 = 52.62, -0.92
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 110540.0


def pt(x_m, y_m):
    """[lon, lat] x metres east, y metres north of (LON0, LAT0)."""
    return [round(LON0 + x_m / KX, 7), round(LAT0 + y_m / KY, 7)]


def line(xy):
    return [pt(x, y) for x, y in xy]


def counts(shape):
    idx = limits._LineIndex(line(shape["route"]), max(limits.MATCH_M, limits.POINT_M))
    return limits.runs_along(line(shape["limit"]), idx) is not None


def near_gate(shape):
    """The first gate, unchanged since 13 Oct: (metres with both ends within MATCH_M of the route, metres needed)."""
    co, rt = line(shape["limit"]), line(shape["route"])
    return limits.along_m(co, rt), min(limits.ALONG_MIN_M, limits.ALONG_SHARE * limits._line_len_m(co))


def side(shape):
    """How far each of the limit's points lies from the route's line, metres."""
    rt = line(shape["route"])
    return [limits._pt_line_m(c, rt) for c in line(shape["limit"])]


# --------------------------------------------------------------------------- #
#  The real shapes (live, 12 Nov 2026): metres from the limit's first point     #
# --------------------------------------------------------------------------- #
ARM = {  # a 28 m one-way arm off a roundabout; the route goes round the roundabout
    "limit": [(0, 0), (-4, -14.5), (-8.2, -27)],
    "route": [(104.9, 46.3), (68.5, 35.3), (41.5, 29.7), (26.7, 23.1), (2.4, 8.7), (-0.9, 1), (-5, -4.5), (-12.4, -10.1),
              (-23.9, -14.5), (-35.3, -13.4), (-44.1, -9), (-49.5, -4.5), (-53.6, 3.2), (-54.9, 8.7), (-73.8, 26.4), (-114.2, 56.3)],
}
SERVICE = {  # a 188 m residential road beside a trunk road, joined to it by a 19 m link; the route is on the trunk road
    "limit": [(0, 0), (0.7, -19), (27.9, -19.6), (53.2, -20.4), (73.8, -21.8), (94.3, -24), (123.8, -28.4), (138.2, -28), (169.2, -28.9)],
    "route": [(266.7, -16.7), (191, -10.1), (184.2, -10.1), (177.5, -10.1), (155.9, -7.8), (124.1, -5.6), (55.9, -1.2),
              (12.6, -0.1), (-0.9, -1.2), (-13, -1.2), (-34.7, -2.3), (-67.1, -3.4)],
}
BESIDE = {  # a 731 m residential road beside a ring road, 12 to 17 m from its line; the route is on the ring road
    "limit": [(0, 0), (-4.6, -2.3), (-13.5, -5.6), (-28.1, -11.3), (-42.8, -16.2), (-57.4, -20.8), (-72, -24.8), (-88.6, -29.6),
              (-105.5, -33.4), (-122.3, -36.7), (-141.1, -39.9), (-169.5, -44.3), (-193.9, -46.4), (-221.6, -48.2), (-249, -47.8),
              (-268.9, -47.4), (-293.9, -46.3), (-318.7, -45.8), (-331.5, -45.7), (-505.2, -41.5), (-515.4, -41.1), (-619.7, -38.8),
              (-706.4, -36.9), (-724.7, -36.6)],
    "route": [(-795.6, 21.8), (-770.6, 14), (-721.2, 1.9), (-696.2, -4.8), (-634, -20.2), (-505.5, -26.9), (-318.2, -33.5),
              (-295.9, -34.6), (-268.9, -35.7), (-239.8, -34.6), (-193.8, -32.4), (-146.5, -26.9), (-118.1, -21.3), (-83.6, -11.4),
              (-58.6, -4.8), (-4.5, 15.1), (20.6, 25.1), (39.5, 32.8), (69.9, 45)],
}
ALONG_LONG = {  # 202 m of the road the route is on
    "limit": [(0, 0), (1.8, -2.9), (10, -14.4), (20.2, -28.6), (28.1, -39.4), (41.6, -58.4), (52.9, -74.7), (75.1, -106.6),
              (93.2, -129.9), (118.5, -162.7)],
    "route": [(186.3, -249.4), (153.9, -207.4), (117.5, -160.9), (95.3, -133.3), (76.4, -109), (43.4, -62.6), (24.5, -36),
              (10.3, -15), (-1.1, 2.7), (-20.7, 32.5), (-34.9, 54.6), (-51, 80)],
}
ALONG_12M = {  # a 12 m piece of the road the route is on
    "limit": [(0, 0), (7.5, -9.5)],
    "route": [(67.8, -86.7), (35.4, -44.7), (-1, 1.8), (-23.3, 29.4), (-42.1, 53.7), (-75.2, 100.1)],
}
ALONG_ARM = {  # a 35 m one-way arm at a small roundabout that the route drives
    "limit": [(0, 0), (-2.9, 4.8), (-7.3, 9.7), (-12.7, 17.5), (-16.7, 30.4)],
    "route": [(80.6, -158.6), (44.8, -29.3), (38.1, -18.2), (32.7, -13.8), (21.2, -8.3), (16.5, -10.5), (7.1, -8.3), (3, -2.8),
              (2.4, 0.6), (-7.1, 9.4), (-16.5, 30.4), (-28, 58), (-35.4, 74.6), (-44.2, 90.1), (-70.5, 129.9)],
}
OTHER_LANE = {  # the 32 m arm on the other side of the island: the same road, the lane the route does not drive
    "limit": [(0, 0), (4.5, -4.9), (8.7, -9.3), (15.9, -15.4), (18.6, -16.7), (24.9, -17.7)],
    "route": [(97.2, -189), (61.5, -59.7), (54.8, -48.6), (49.4, -44.2), (37.9, -38.7), (33.2, -40.9), (23.7, -38.7), (19.7, -33.2),
              (19, -29.8), (9.6, -21), (0.1, 0), (-11.3, 27.6), (-18.7, 44.2), (-27.5, 59.7), (-53.8, 99.5)],
}
ROUTE_ENDS = {  # a 186 m limit the route runs along for 73 m and then leaves (it turns into a quarry)
    "limit": [(0, 0), (5.7, -15.7), (11, -28.6), (28.8, -62.8), (54.1, -97.9), (80.1, -133.2), (98.3, -155.6)],
    "route": [(157.9, -246.2), (130.2, -198.6), (118.1, -179.8), (101.3, -156.6), (79.7, -130.1), (59.8, -102.5), (58.2, -103.6),
              (30.2, -124.4)],
}
BRIDGE_8M = {  # an 8 m height limit under a bridge on the road the route is on
    "limit": [(0, 0), (-4.5, -7.1)],
    "route": [(-30.2, -80.1), (-16, -29.3), (-9.9, -14.9), (-1.8, -1.7), (5, 7.2), (8.4, 17.1), (10.4, 29.3), (11.8, 64.7)],
}
UNNAMED = {  # 1.2 km of an unnamed road the route is on, end to end
    "limit": [(0, 0), (14, 47), (18.6, 55.7), (152.4, 242.9), (264.3, 366.1), (361.5, 460.4), (371.7, 478.9), (377.9, 499.3),
              (380.2, 524.1), (378.2, 541.6), (369.1, 577.1), (276.6, 832.6), (227.2, 948), (223.1, 964.6), (222.7, 976.7),
              (224.1, 986.8), (226.7, 997.6), (234.2, 1005.5)],
    "route": [(-7.2, -76.9), (-6.5, -15), (-1.8, -1.8), (15.7, 49.1), (132.4, 219.3), (158.7, 251.4), (228.1, 319.9), (278.7, 379.6),
              (361.6, 459.2), (375.1, 491.2), (379.2, 526.6), (375.1, 544.3), (316.4, 723.4), (223.4, 962.1), (223.4, 973.2),
              (222.7, 984.2), (234.2, 1004.1), (220, 1015.2), (178.9, 1062.7), (160.7, 1087.1)],
}

ok("the constants: ALONG_SIDE_M is 8 m and sits beside the 10 Nov pair, which is unchanged",
   getattr(limits, "ALONG_SIDE_M", None) == 8.0 and limits.ALONG_ANGLE_DEG == 20.0 and limits.CARRY_ON_M == 40.0 and limits.MATCH_M == 20.0
   and limits.ALONG_MIN_M == 30.0 and limits.ALONG_SHARE == 0.6 and limits.POINT_M == 12.0)

# ---- the three roads the routes are not on ---------------------------------------------------------------------------
NOT_ON = {"the roundabout arm (28 m; the route goes round the roundabout)": ARM,
          "the service road beside the trunk road (188 m, 19 to 24 m to the side)": SERVICE,
          "the residential road beside the ring road (731 m, 12 to 17 m to the side)": BESIDE}
for name, shp in NOT_ON.items():
    a, need = near_gate(shp)
    ok(f"⭐ {name} is NOT a hit", not counts(shp), f"within 20 m: {a:.1f} m of it, needed {need:.1f}")
    ok(f"{name}: it does pass the 20 m gate (so it is the 12 Nov rule that drops it)", a >= need, f"{a:.1f} < {need:.1f}")
s = side(ARM)
ok("the roundabout arm starts on the route and ends well off it (the shape the far-end rule reads)",
   s[0] < 2.0 and s[-1] > 2 * SIDE_M, str([round(x, 1) for x in s]))
s = side(SERVICE)
ok("the service road: past its link every point lies more than ALONG_SIDE_M from the route, and most within MATCH_M",
   all(x > SIDE_M for x in s[1:]) and len([x for x in s[1:] if x <= limits.MATCH_M]) >= 4, str([round(x, 1) for x in s]))
s = side(BESIDE)
ok("the road beside the ring road: every point lies more than ALONG_SIDE_M from the route, 21 of 24 within MATCH_M",
   all(x > SIDE_M for x in s) and len([x for x in s if x <= limits.MATCH_M]) >= 21, str([round(x, 1) for x in s]))

# ---- the roads the routes do run along -------------------------------------------------------------------------------
ON = {"202 m of the route's own road": ALONG_LONG, "a 12 m piece of the route's own road": ALONG_12M,
      "a 35 m one-way arm the route drives": ALONG_ARM, "a limit the route leaves after 73 m to turn in": ROUTE_ENDS,
      "an 8 m piece under a bridge on the route's road": BRIDGE_8M, "1.2 km of the route's own road": UNNAMED}
for name, shp in ON.items():
    ok(f"⭐ {name} still counts", counts(shp), str([round(x, 1) for x in side(shp)]))
ok("the roads the routes run along lie within 5 m of the route's line wherever the route is on them (8 m leaves room)",
   all(max(side(shp)) < 5.0 for shp in (ALONG_LONG, ALONG_12M, ALONG_ARM, BRIDGE_8M, UNNAMED)),
   str([round(max(side(shp)), 1) for shp in (ALONG_LONG, ALONG_12M, ALONG_ARM, BRIDGE_8M, UNNAMED)]))
ok("the other lane round a traffic island (same road, not driven: its far end is 13 m off the route) is no longer a hit",
   not counts(OTHER_LANE) and side(OTHER_LANE)[-1] > SIDE_M, str([round(x, 1) for x in side(OTHER_LANE)]))

# ---- made-up shapes that pin the rule ---------------------------------------------------------------------------------
MAIN = [(-2000 + 50 * i, 0) for i in range(81)]             # a route W -> E, 4 km, a point every 50 m


def beside(offset, x0=-300, length=300, step=25):
    return {"limit": [(x0 + step * k, offset) for k in range(int(length / step) + 1)], "route": MAIN}


ok("a road 12 m beside the route for 300 m is not a hit", not counts(beside(12)))
ok("a road 8.5 m beside the route is not a hit; one 7.5 m beside it is (ALONG_SIDE_M)", not counts(beside(8.5)) and counts(beside(7.5)))
ok("a road 5 m off the route's line for 300 m is a hit (the two map sources never agree to the metre)", counts(beside(5)))
ok("both sides: 7.5 m to the south counts too, 12 m to the south does not", counts(beside(-7.5)) and not counts(beside(-12)))
# a short limit: its share is not enough unless the route reaches both its ends
HUG = {"limit": [(0, 0), (20, 0), (25, 8.7)], "route": MAIN}            # 30 m: 20 m on the route, then away at 60° to 8.7 m off
ok("a 30 m limit that follows the route for 20 m and ends 8.7 m off it is not a hit (its share, but the route never reaches its end)",
   not counts(HUG) and near_gate(HUG)[0] >= near_gate(HUG)[1])
HUG_IN = {"limit": [(0, 0), (20, 0), (29.8, 2)], "route": MAIN}         # the same, ending 2 m off: the route's own road, kinked
ok("the same limit ending 2 m off the route is a hit", counts(HUG_IN))
LONG_HUG = {"limit": [(0, 0), (32, 0), (37, 8.7)], "route": MAIN}       # 42 m: 32 m on the route, then away
ok("a 42 m limit the route runs along for 32 m counts though it ends off the route (ALONG_MIN_M is enough by itself)", counts(LONG_HUG))
# the carry-on (10 Nov) still answers a route that turns into the side road, and needs the far end reached
TURN = {"limit": [(50, 0), (50, 13)], "route": [(-2000 + 50 * i, 0) for i in range(42)] + [(50, 50 * k) for k in range(1, 8)]}
ok("a side road the route turns into and uses still counts (10 Nov), its far end being on the route", counts(TURN))
PAST = {"limit": [(0, 0), (6, 12)], "route": MAIN + [(4000, 0)]}
ok("a 13 m stub the route passes is not a hit (10 Nov)", not counts(PAST))
SWING = {"limit": [(0, 0), (0, 12)], "route": [(-200, 0), (100, 0), (100, 52), (-100, 52)]}   # the route doubles back 52 m north
ok("the carry-on needs the far end reached: a 12 m stub the route passes is not a hit though the route comes back 40 m beyond its end",
   not counts(SWING) and near_gate(SWING)[0] >= near_gate(SWING)[1])

# ---- the rule only ever drops a hit; _matches shares it; the module says why ------------------------------------------
every = list(NOT_ON.values()) + list(ON.values()) + [OTHER_LANE, beside(12), beside(7.5), beside(5), HUG, HUG_IN, LONG_HUG, TURN, PAST, SWING]
ok("the rule only ever drops a hit (nothing the 20 m gate refuses is counted)",
   all(near_gate(shp)[0] >= near_gate(shp)[1] - 1e-6 or not counts(shp) for shp in every))


def row(ext, shp):
    co = line(shp["limit"])
    a = limits.anchor_of("LineString", co)
    return {"source": "osm", "ext_id": ext, "kind": "weight", "value": 7.5, "unit": "t", "geom_type": "LineString", "geometry": co,
            "length_m": limits._line_len_m(co), "anchor_lon": a[0], "anchor_lat": a[1], "exceptions": "Except for access"}


got = {L["ext_id"] for L, _p, _a in limits._matches(line(SERVICE["route"]), [row("service", SERVICE)])}
got |= {L["ext_id"] for L, _p, _a in limits._matches(line(ALONG_LONG["route"]), [row("along", ALONG_LONG)])}
got |= {L["ext_id"] for L, _p, _a in limits._matches(line(ARM["route"]), [row("arm", ARM)])}
ok("⭐ _matches (an abnormal load's line) uses the same rule: the road it is on counts, the road beside it and the arm do not",
   got == {"along"}, str(got))
dims = {"mass_t": 44.0}
hits = limits.check_line(line(BESIDE["route"]), dims, _limits=[row("beside", BESIDE)])
hits2 = limits.check_line(line(UNNAMED["route"]), dims, _limits=[row("unnamed", UNNAMED)])
ok("check_line: no hit for the road beside the ring road; an 'exceeds' hit for the road the line runs along",
   hits == [] and len(hits2) == 1 and hits2[0]["verdict"] == "exceeds" and hits2[0]["along_m"] > 1000, f"{hits} {hits2}")
with open(os.path.join(BACKEND, "limits.py"), encoding="utf-8") as f:
    src = f.read().replace("\r\n", "\n")
body = src[src.index("def runs_along("):src.index("def _along(")]
ok("runs_along measures the side with ALONG_SIDE_M (MATCH_M stays for the first gate and the carry-on point)",
   "<= ALONG_SIDE_M for i in idx.candidates(mid))" in body and "<= MATCH_M for i in idx.candidates(mid)" not in body
   and "(d <= ALONG_SIDE_M or on_line(c)) for d, c in ((dist[0], first), (dist[-1], last))" in body and "idx.near(p, MATCH_M)" in body)
ok("check_route and _matches still share the one rule", src.count("runs_along(coords, idx, L.get(\"length_m\"))") == 2)
ok("the module's notes say why (the road beside the route, 3 of 6 on live), and keep the 10 Nov note",
   "THE ROAD BESIDE THE ROUTE (12 Nov 2026)" in src and "3 of the 6 roads flagged" in src and "THE SIDE-ROAD MOUTH (10 Nov 2026)" in src)
ok("the diagnostics read names every matching figure", all(k in src for k in ('"along_side_m": ALONG_SIDE_M', '"along_angle_deg": ALONG_ANGLE_DEG', '"carry_on_m": CARRY_ON_M')))
ok("the fixtures carry no coordinates of the place and name no map supplier",
   all(w not in open(__file__, encoding="utf-8").read().lower() for w in ("openstreet" + "map", "her" + "e maps", "overpas" + "s")))

print(f"test_limit_beside.py: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  ✗ " + f)
sys.exit(1 if FAIL else 0)

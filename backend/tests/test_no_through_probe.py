"""
The loading-only probe (12 Nov 2026). Two demo roads with a 7.5 t "except for loading" limit carried baked lorry lines
(notes/session-1112-here-limits-why.md). The router's guide says a loading-only ("no-through") restriction is never a
notice: it is reported only when the request asks with `return=noThroughRestrictions` and
`spans=noThroughRestrictions`. No request from this codebase had ever sent those names, so a new read-only admin
diagnostic sends them once for one leg and reports what comes back:

    GET /api/admin/diagnostics/no-through/{route_id}?profile=…&leg=loaded|return&via=lat,lon
      -> network.no_through_diagnostics() -> here_routing.no_through_probe()

WHAT IS ASSERTED
----------------
  * the request: the two new values, the bake's pinned departure time, the leg's truck parameters exactly as
    _truck_params builds them (the empty weight on the return leg), no alternatives, the bake's avoid areas, and at
    most one pass-through via, placed before the destination;
  * the ends are the ends of the BAKE's own router call (the road ends of the gates' access roads), on both legs of a
    one-way site, measured against a real _bake_leg run;
  * the API key is in no answer: a good one, a refusal whose body echoes it, a failure whose message carries it;
  * a refusal (HTTP 400) is reported with the provider's own body and the names sent, and nothing is retried;
  * a stubbed answer with a noThroughRestrictions entry and a violatedVehicleRestriction notice is passed through
    unchanged, the span that points at it is listed with its offset, length, names, start point and what it refers to;
  * the answer never raises on a malformed reply; no key means no call; a bad via, leg or route is refused in words
    with no call;
  * nothing is written (the routes and their stored lines identical before and after), and the source: the endpoint
    is admin-gated, the wrapper holds no write, and no bake path sends the new names.

WHAT THIS DOES NOT PROVE
------------------------
HERE is never called. Whether it accepts every name, where it puts the list and what one entry holds are exactly what
the diagnostic is for: the stub's shape is the one in HERE's guide (read 12 Nov 2026), not an answer seen on live.
No Postgres branch runs. The real FastAPI route is asked in smoke_reviewer_wall.py.

Run:  python backend/tests/test_no_through_probe.py
"""
import copy
import io
import json
import os
import sys
import tempfile
import types
import urllib.error
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# the polyline decoder, stubbed: a "line" here is "lat,lon;lat,lon;…" so a span's start point can be checked by eye
_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: [tuple(float(x) for x in p.split(",")) for p in s.split(";") if p]
_fp.encode = lambda pts: ";".join(f"{a},{b}" for a, b in pts)
sys.modules["flexpolyline"] = _fp

TMP = tempfile.mkdtemp(prefix="wayscope_nothrough_")
sys.path.insert(0, HERE)
from portable import remove_scratch_db   # noqa: E402
for _v in ("DATABASE_URL", "ADMIN_TOKEN", "TENANT_ID", "HERE_API_KEY"):
    os.environ.pop(_v, None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import gates  # noqa: E402
import haul  # noqa: E402
import zones  # noqa: E402
import here_routing  # noqa: E402
import limits  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def north(p, m):
    return [p[0], round(p[1] + m / 111320.0, 7)]


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

# =========================================================================== #
#  Fixture (test_departure_check's): a quarry (one gate both ways) and a       #
#  one-way site (in by the north, out by the south), each gate 35 m in from    #
#  its road, one permanent closure well away, and two places with no gate      #
# =========================================================================== #
ART = "Artic Tipper (44t)"
LAT = 52.5
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L1', 'Kelsey Quarry', ?, -1.0, 'Quarry')", (LAT,))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L2', 'Mill Compound', ?, -0.9, 'Compound')", (LAT,))
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L3', 'Top Yard', 52.6, -1.2, 'Compound')")
db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES ('L4', 'Low Yard', 52.61, -1.1, 'Compound')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R1', 'L1', 'L2', 'Small aggregate', 'IPT1')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R2', 'L1', 'L2', 'Small aggregate', 'IPT1')")
db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES ('R3', 'L3', 'L4', 'Small aggregate', 'IPT1')")
RQ = [-1.0, LAT + 0.002]
GQ = north(RQ, -35)
RIN = [-0.9, LAT + 0.002]
GIN = north(RIN, -35)
ROUT = [-0.9, LAT - 0.002]
GOUT = north(ROUT, 35)


def haul_zone(name, coords, **kw):
    z = zones.create_zone(name, {"type": "LineString", "coordinates": coords}, kind=zones.HAUL_KIND, affects_routing=True,
                          speed_kph=kw.pop("speed", 10), haul_mode="splice", **kw)
    assert "error" not in z, z
    return z["id"]


ZQ = haul_zone("Quarry access road", [RQ, GQ])
ZIN = haul_zone("Site in access road", [GIN, RIN])
ZOUT = haul_zone("Site out access road", [ROUT, GOUT])
zones.create_zone("Bridge closure", {"type": "Polygon", "coordinates": [[[-0.5, 52.0], [-0.5, 52.01],
                                                                         [-0.49, 52.01], [-0.5, 52.0]]]},
                  kind="closure", affects_routing=True)
gates.create_gate("L1", "Quarry gate", GQ[1], GQ[0], direction="both", is_default=True, access_zone_id=ZQ)
gates.create_gate("L2", "North gate (in)", GIN[1], GIN[0], direction="access", is_default=True, access_zone_id=ZIN)
gates.create_gate("L2", "South gate (out)", GOUT[1], GOUT[0], direction="egress", is_default=True, access_zone_id=ZOUT)
ZMID = haul_zone("Langton haul road", [[-0.96, LAT], [-0.94, LAT]], speed=20)
haul.attach("R2", ZMID)
AVOID, ZTAG = network.active_avoid()
ok("fixture: the permanent closure is an avoid area the bake sends", len(AVOID) == 1 and ZTAG, f"{AVOID} {ZTAG}")

FACT = conversions.load_factors()
BAKE_AT = here_routing.bake_departure_time()
KEY = "harness-secret-key-0123456789"
RET = "polyline,summary,noThroughRestrictions"
SPANS = "noThroughRestrictions,truckAttributes,notices,names,length"

# =========================================================================== #
#  The router, faked at the HTTP call                                          #
# =========================================================================== #
URLS = []
NEXT = {"body": None, "raise": None}


class _Resp:
    def __init__(self, body):
        self._b = body

    def read(self, *a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen(url, timeout=0):
    URLS.append(url)
    if NEXT["raise"] is not None:
        raise NEXT["raise"](url)
    return _Resp(json.dumps(NEXT["body"]).encode())


def sent(url):
    """The query of one call, as ordered pairs and as a dict (a repeated name keeps every value)."""
    pairs = urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query, keep_blank_values=True)
    d = {}
    for k, v in pairs:
        d.setdefault(k, []).append(v)
    return pairs, d


# HERE's guide's shape (read 12 Nov 2026): the list on the section, a span pointing at it by index
RESTRICTION = {"type": "restriction", "maxGrossWeight": 7500, "maxWeight": {"value": 7500, "type": "gross"}}
VIOLATED = {"title": "Violated vehicle restriction.", "code": "violatedVehicleRestriction", "severity": "critical",
            "details": [{"type": "restriction", "cause": "Route violates vehicle restriction: gross weight limit of 7500 kg",
                         "maxGrossWeight": 7500, "maxWeight": {"value": 7500, "type": "gross"}}]}
ANSWER = {"routes": [{"id": "r-1", "sections": [{
    "id": "s-1", "type": "vehicle",
    "polyline": "52.70,-0.80;52.71,-0.81;52.72,-0.82;52.73,-0.83;52.74,-0.84",
    "summary": {"length": 15940, "duration": 1500, "baseDuration": 1400},
    "transport": {"mode": "truck"},
    "notices": [VIOLATED],
    "noThroughRestrictions": [RESTRICTION],
    "spans": [
        {"offset": 0, "length": 3596, "names": [{"value": "A606", "language": "en"}], "truckAttributes": ["open"]},
        {"offset": 2, "length": 1176, "truckAttributes": ["open", "noThrough"], "noThroughRestrictions": [0], "notices": [0]},
        {"offset": 3, "length": 11168, "names": [{"value": "Pickwell Road", "language": "en"}], "truckAttributes": ["open"]},
    ]}]}]}

_real_uo = here_routing.urllib.request.urlopen
here_routing.urllib.request.urlopen = _urlopen
try:
    # ---- 1. no key: said, and nothing called ---------------------------------------------------------------------- #
    P0 = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    ok("🔴 1. no key: says so, calls nothing, and still shows what it would send",
       P0["error"] == "HERE_API_KEY is not set on the server" and URLS == [] and P0["here_calls"] == 0
       and P0["api_key_set"] is False and P0["params_sent"]["return"] == RET and P0["params_sent"]["spans"] == SPANS
       and "apiKey" not in P0["params_sent"])
    D0 = network.no_through_diagnostics("R1", profile=ART, leg="return")
    ok("🔴 1. the wrapper with no key: said in words, no probe, no call",
       D0["error"] == "HERE_API_KEY is not set on the server" and D0["here_configured"] is False and "probe" not in D0
       and URLS == [])

    os.environ["HERE_API_KEY"] = KEY

    # ---- 2. the request ------------------------------------------------------------------------------------------- #
    NEXT["body"] = copy.deepcopy(ANSWER)
    P = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    pairs, q = sent(URLS[-1])
    ok("⭐ 2. the request carries return=polyline,summary,noThroughRestrictions",
       q["return"] == [RET] and "return=polyline%2Csummary%2CnoThroughRestrictions" in URLS[-1], str(q.get("return")))
    ok("⭐ 2. ...and spans=noThroughRestrictions,truckAttributes,notices,names,length", q["spans"] == [SPANS], str(q.get("spans")))
    ok("⭐ 2. ...and the bake's pinned departure time (the next Tuesday, 10:00), never 'now'",
       q["departureTime"] == [BAKE_AT] and BAKE_AT[11:16] == "10:00", str(q.get("departureTime")))
    _truck = {k: [str(v)] for k, v in here_routing._truck_params(ART, FACT, laden=True).items()}
    ok("⭐ 2. the truck parameters are exactly _truck_params' (loaded: the gross weight)",
       {k: v for k, v in q.items() if k == "transportMode" or k.startswith("vehicle[")} == _truck
       and q["vehicle[grossWeight]"] == ["44000"], str({k: v for k, v in q.items() if k.startswith("vehicle[")}))
    ok("2. one route is asked for: no alternatives, no via, no avoid areas unless given, one call",
       "alternatives" not in q and "via" not in q and "avoid[areas]" not in q and len(URLS) == 1 and P["here_calls"] == 1)
    ok("2. the report repeats the request without the key, and lists the names it sent",
       P["params_sent"]["return"] == RET and P["params_sent"]["spans"] == SPANS and P["params_sent"]["departureTime"] == BAKE_AT
       and "apiKey" not in P["params_sent"] and P["names_sent"] == {"return": RET.split(","), "spans": SPANS.split(",")})
    URLS.clear()
    PR = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT, laden=False, departure_time="2026-12-01T10:00:00+00:00",
                                       avoid_areas=["bbox:1,2,3,4", "bbox:5,6,7,8"])
    _, q = sent(URLS[-1])
    ok("⭐ 2. the return leg sends the EMPTY weight as the bake does; a given time and the avoid areas go as given",
       q["vehicle[grossWeight]"] == [str(here_routing.tare_weight_kg(ART, FACT))] and q["vehicle[grossWeight]"] != ["44000"]
       and q["departureTime"] == ["2026-12-01T10:00:00+00:00"] and q["avoid[areas]"] == ["bbox:1,2,3,4|bbox:5,6,7,8"],
       str(q))
    URLS.clear()
    PV = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT, via=(52.724, -0.8436))
    pairs, q = sent(URLS[-1])
    _names = [k for k, _ in pairs]
    ok("⭐ 2. one pass-through via: sent once, as lat,lon!passThrough=true, before the destination",
       q["via"] == ["52.724,-0.8436!passThrough=true"] and _names.index("origin") < _names.index("via") < _names.index("destination")
       and PV["params_sent"]["via"] == ["52.724,-0.8436!passThrough=true"] and PV["via_pass_through"] == [52.724, -0.8436],
       str(q.get("via")))

    # ---- 3. the answer, passed through ---------------------------------------------------------------------------- #
    ok("⭐ 3. the noThroughRestrictions list is reported exactly as it came, with its section",
       P["no_through_restrictions"] == [{"section": 0, "restrictions": [RESTRICTION]}] and P["no_through_field_returned"] is True,
       str(P.get("no_through_restrictions")))
    ok("⭐ 3. the violatedVehicleRestriction notice is reported in full (code, title, severity, details), unchanged",
       P["notices"] == [{"level": "section", "section": 0, "notice": VIOLATED}]
       and P["notice_codes"] == ["violatedVehicleRestriction"], str(P.get("notices")))
    ok("3. the keys of the answer, the route and the sections are listed",
       P["response_keys"] == ["routes"] and P["route_keys"] == ["id", "sections"] and P["routes_returned"] == 1
       and P["sections"] == 1 and {"noThroughRestrictions", "notices", "spans", "polyline", "summary"} <= set(P["section_keys"]))
    _m = P["spans_marked_list"]
    ok("⭐ 3. the span that carries the no-through reference is listed as returned: offset, length, names (none), "
       "truck attributes", P["spans_marked"] == 1 and len(_m) == 1 and _m[0]["span"] == ANSWER["routes"][0]["sections"][0]["spans"][1]
       and _m[0]["section"] == 0 and P["spans_marked_truncated"] is False, str(_m))
    ok("⭐ 3. ...with where it starts on the line (lat, lon) and the entries its indexes point to",
       _m[0]["at"] == [52.72, -0.82] and _m[0]["refers_to"] == {"noThroughRestrictions": [RESTRICTION], "notices": [VIOLATED]},
       str(_m[0].get("at")) + " " + str(_m[0].get("refers_to")))
    ok("3. the truck attributes seen, with the spans and metres on each, the commonest marked",
       P["truck_attributes_seen"] == [
           {"truckAttributes": ["open"], "spans": 2, "length_m": 14764, "commonest": True},
           {"truckAttributes": ["open", "noThrough"], "spans": 1, "length_m": 1176, "commonest": False}]
       and P["spans_returned"] == 3 and {"offset", "length", "names", "truckAttributes"} <= set(P["span_keys"])
       and P["spans_sample"] == ANSWER["routes"][0]["sections"][0]["spans"], str(P.get("truck_attributes_seen")))
    ok("3. the route's length, as metres and km, and the time", (P["length_m"], P["distance_km"], P["duration_hr"]) == (15940, 15.94, 0.417),
       f"{P.get('length_m')} {P.get('distance_km')} {P.get('duration_hr')}")
    ok("3. the plain reading names what came back", P["reads_as"].startswith("The router listed 1 no-through restriction(s)")
       and "violatedVehicleRestriction" in P["reads_as"], P.get("reads_as", ""))
    ok("🔴 3. the key is nowhere in the answer", KEY not in json.dumps(P) and KEY not in json.dumps(PV) and KEY not in json.dumps(PR))

    # notices at the other two levels the reference names, and a second section's list
    two = copy.deepcopy(ANSWER)
    two["notices"] = [{"code": "noRouteFound", "title": "top"}]
    two["routes"][0]["notices"] = [{"code": "routeLevel"}]
    two["routes"][0]["sections"].append({"polyline": "52.74,-0.84;52.75,-0.85", "summary": {"length": 60, "duration": 36},
                                         "noThroughRestrictions": [{"type": "restriction", "maxGrossWeight": 18000}],
                                         "spans": [{"offset": 0, "length": 60, "noThroughRestrictions": [0, 7]}]})
    NEXT["body"] = two
    P2 = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    ok("3. notices at the answer's top level and on the route are collected beside the sections', each with its level",
       [(n["level"], n["notice"]["code"]) for n in P2["notices"]] == [("response", "noRouteFound"), ("route", "routeLevel"),
                                                                     ("section", "violatedVehicleRestriction")]
       and P2["notices"][2]["section"] == 0 and P2["response_keys"] == ["notices", "routes"], str(P2.get("notices")))
    ok("3. a second section's list is its own row; an index past the list's end is left out of refers_to, never a crash",
       [x["section"] for x in P2["no_through_restrictions"]] == [0, 1] and P2["spans_marked"] == 2
       and P2["spans_marked_list"][1]["refers_to"] == {"noThroughRestrictions": [{"type": "restriction", "maxGrossWeight": 18000}]}
       and P2["spans_marked_list"][1]["at"] == [52.74, -0.84] and P2["length_m"] == 16000
       and P2["reads_as"].startswith("The router listed 2 no-through restriction(s)"), str(P2.get("spans_marked_list")))

    # nothing held: the two honest readings
    none = copy.deepcopy(ANSWER)
    sec = none["routes"][0]["sections"][0]
    del sec["noThroughRestrictions"], sec["notices"]
    sec["spans"] = [{"offset": 0, "length": 15940, "truckAttributes": ["open"]}]
    NEXT["body"] = none
    P3 = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    ok("⭐ 3. no list in the answer: read as 'none on this line', and said NOT to be proof of it",
       P3["no_through_field_returned"] is False and P3["no_through_restrictions"] == [] and P3["notices"] == []
       and P3["spans_marked"] == 0 and "not proof" in P3["reads_as"] and "No notices at any level." in P3["reads_as"],
       P3.get("reads_as", ""))
    sec["noThroughRestrictions"] = []
    NEXT["body"] = none
    P4 = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    ok("3. an EMPTY list in the answer: the name was honoured and the router holds none on this line",
       P4["no_through_field_returned"] is True and P4["no_through_restrictions"] == [{"section": 0, "restrictions": []}]
       and "EMPTY noThroughRestrictions list" in P4["reads_as"], P4.get("reads_as", ""))
    many = copy.deepcopy(ANSWER)
    many["routes"][0]["sections"][0]["spans"] = [{"offset": 0, "length": 10, "noThroughRestrictions": [0]} for _ in range(95)]
    NEXT["body"] = many
    P5 = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    ok("3. a long answer is capped at 80 listed spans, and says it was cut", P5["spans_marked"] == 95
       and len(P5["spans_marked_list"]) == 80 and P5["spans_marked_truncated"] is True and len(P5["spans_sample"]) == 8)

    # ---- 4. a refusal, and failures: reported, never raised, nothing retried --------------------------------------- #
    BODY400 = {"title": "Malformed request", "status": 400, "code": "E605013",
               "cause": "Invalid return options: noThroughRestrictions", "action": "", "correlationId": "abc-123"}
    URLS.clear()
    NEXT["raise"] = lambda url: urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(
        json.dumps(dict(BODY400, action=f"see ?apiKey={KEY}")).encode()))
    E = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    ok("⭐ 4. HTTP 400: the provider's own body is reported, in words and as fields",
       E["error"].startswith("HTTP 400:") and "Invalid return options: noThroughRestrictions" in E["error"]
       and E["http_status"] == 400 and E["error_body"]["code"] == "E605013"
       and E["error_body"]["cause"] == BODY400["cause"] and E["refused"] is True, str(E.get("error")))
    ok("⭐ 4. ...nothing is retried (one call), and the names that were sent are listed",
       len(URLS) == 1 and E["retried"] is False and E["here_calls"] == 1
       and E["names_sent"] == {"return": RET.split(","), "spans": SPANS.split(",")}
       and RET in E["reads_as"] and SPANS in E["reads_as"] and "nothing was retried" in E["reads_as"], E.get("reads_as", ""))
    ok("🔴 4. a refusal that echoes the key back is reported with the key cut out",
       KEY not in json.dumps(E) and "[key removed]" in E["error"] and "[key removed]" in E["error_body"]["action"])
    NEXT["raise"] = lambda url: urllib.error.HTTPError(url, 429, "Too Many", {}, io.BytesIO(b"Rate limit reached, not JSON"))
    E2 = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    ok("4. a refusal that is not JSON: its text and status, no fields", E2["error"] == "HTTP 429: Rate limit reached, not JSON"
       and E2["http_status"] == 429 and E2["error_body"] is None and E2["retried"] is False)
    NEXT["raise"] = lambda url: OSError(f"could not reach {url}")
    URLS.clear()
    E3 = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
    ok("🔴 4. a failure whose message carries the whole address: reported with the key cut out, one call, no crash",
       E3["error"].startswith("could not reach") and KEY not in json.dumps(E3) and "[key removed]" in E3["error"]
       and len(URLS) == 1 and "routes_returned" not in E3, str(E3.get("error")))
    NEXT["raise"] = None
    for label, body in (("no routes", {"notices": [{"code": "noRouteFound"}]}),
                        ("a route with no sections", {"routes": [{}]}),
                        ("odd spans and no summary", {"routes": [{"sections": [{"spans": ["x", {"offset": "a", "notices": [0]}],
                                                                              "summary": None, "notices": ["text"]}]}]})):
        NEXT["body"] = body
        try:
            X = here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)
            good = isinstance(X.get("reads_as"), str) and "error" not in X and X["length_m"] == 0
        except Exception as e:      # the probe's promise is that it never raises
            good, X = False, {"raised": repr(e)}
        ok(f"4. a malformed answer ({label}) is still an answer, never a crash", good, str(X)[:200])
    NEXT["body"] = {"notices": [{"code": "noRouteFound"}]}
    ok("4. no route: said so, with the notice",
       here_routing.no_through_probe(52.5, -1.0, 52.6, -1.1, ART, FACT)["reads_as"].startswith("The router returned no route"))

    # ---- 5. the wrapper: the bake's own router call ---------------------------------------------------------------- #
    # what the bake really asks, both legs: here_routing.routes captured under a real _bake_leg
    BAKE_CALLS = []

    def _fake_routes(o_lat, o_lon, d_lat, d_lon, profile, factors=None, **kw):
        BAKE_CALLS.append({"o": (o_lat, o_lon), "d": (d_lat, d_lon), "laden": kw.get("laden", True),
                           "avoid": list(kw.get("avoid_areas") or []), "dep": kw.get("departure_time")})
        return [{"geometry": [[o_lon, o_lat], [d_lon, d_lat]], "distance_km": 10.0, "duration_hr": 0.25, "sections": []}]

    R = db.query("SELECT * FROM routes WHERE id = 'R1'")[0]
    L = {l["id"]: l for l in db.query("SELECT * FROM locations")}
    _real_routes = here_routing.routes
    here_routing.routes = _fake_routes
    BAKE = {}
    try:
        for leg in network.LEGS:
            BAKE_CALLS.clear()
            network._bake_leg(R, L["L1"], L["L2"], ART, leg, FACT)
            BAKE[leg] = list(BAKE_CALLS)
    finally:
        here_routing.routes = _real_routes
    ok("fixture: the bake makes one router call a leg", all(len(BAKE[l]) == 1 for l in network.LEGS), str(BAKE))

    def snapshot():
        return json.dumps([db.query("SELECT * FROM route_geometry ORDER BY route_id, vehicle_profile, leg, alt_index"),
                           db.query("SELECT * FROM routes ORDER BY id"), db.query("SELECT * FROM zones ORDER BY id")],
                          sort_keys=True, default=str)

    BEFORE = snapshot()
    NEXT["body"] = copy.deepcopy(ANSWER)
    W = {}
    for leg in network.LEGS:
        URLS.clear()
        W[leg] = network.no_through_diagnostics("R1", profile=ART, leg=leg)
        _, q = sent(URLS[-1])
        b = BAKE[leg][0]
        ok(f"⭐ 5. {leg}: one call, with the ends, avoid areas and pinned time of the bake's own router call",
           len(URLS) == 1 and q["origin"] == [f"{b['o'][0]},{b['o'][1]}"] and q["destination"] == [f"{b['d'][0]},{b['d'][1]}"]
           and q["avoid[areas]"] == ["|".join(b["avoid"])] and b["avoid"] == AVOID and q["departureTime"] == [b["dep"]] == [BAKE_AT],
           f"{q.get('origin')} {q.get('destination')} vs {b}")
        ok(f"5. {leg}: with the two new values", q["return"] == [RET] and q["spans"] == [SPANS])
    _, q = sent(URLS[-1])
    ok("⭐ 5. the one-way site: the return leg leaves by the SOUTH gate's road end and arrives at the quarry's, with the "
       "empty weight", W["return"]["from"] == [ROUT[1], ROUT[0]] and W["return"]["to"] == [RQ[1], RQ[0]]
       and W["loaded"]["from"] == [RQ[1], RQ[0]] and W["loaded"]["to"] == [RIN[1], RIN[0]]
       and q["vehicle[grossWeight]"] == [str(here_routing.tare_weight_kg(ART, FACT))]
       and W["return"]["probe"]["laden"] is False and W["loaded"]["probe"]["laden"] is True, f"{W['return']['from']} {W['return']['to']}")
    ok("5. the report gives the gates beside the points sent, the drawn roads, the zones in force and the time",
       W["return"]["gate_points"] == {"from": [GOUT[1], GOUT[0]], "to": [GQ[1], GQ[0]]}
       and [s["zone_id"] for s in W["return"]["steps"]] == [ZOUT, ZQ] and W["return"]["mid_leg_roads"] == []
       and W["return"]["same_request_as_bake"] is True and W["return"]["zones_in_force"] == ZTAG.split(",")
       and W["return"]["avoid_areas"] == AVOID and W["return"]["bake_time"] == BAKE_AT and W["return"]["via"] is None
       and W["return"]["profile_in_factors"] is True and "note" not in W["return"])
    ok("⭐ 5. the answer travels through the wrapper unchanged",
       W["return"]["probe"]["no_through_restrictions"] == [{"section": 0, "restrictions": [RESTRICTION]}]
       and W["return"]["probe"]["notices"][0]["notice"] == VIOLATED and W["return"]["probe"]["here_calls"] == 1)
    URLS.clear()
    V = network.no_through_diagnostics("R1", profile=ART, leg="return", via="52.7240,-0.8436")
    _, q = sent(URLS[-1])
    ok("⭐ 5. via=lat,lon as typed on the address: one pass-through point, and the report says this is not the bake's request",
       q["via"] == ["52.724,-0.8436!passThrough=true"] and V["via"] == [52.724, -0.8436] and V["same_request_as_bake"] is False
       and len(URLS) == 1, str(q.get("via")))
    URLS.clear()
    bad = [network.no_through_diagnostics("R1", profile=ART, leg="return", via=v)
           for v in ("52.7", "52.7,-0.8,1", "north,west", "95,0", "52,181", "nan,0")]
    ok("🔴 5. a via that is not one point on the globe is refused in words, with no call",
       all(x.get("error", "").startswith("via must be one point as lat,lon") for x in bad) and URLS == []
       and all("probe" not in x for x in bad), str([x.get("error") for x in bad]))
    ok("5. an unknown leg and route are refused in words, with no call",
       network.no_through_diagnostics("R1", leg="sideways")["error"].startswith("leg must be one of")
       and network.no_through_diagnostics("R999")["error"] == "route not found" and URLS == [])
    M = network.no_through_diagnostics("R2", profile=ART, leg="loaded")
    _, q = sent(URLS[-1])
    ok("⭐ 5. a leg with a haul road part way along: one call road end to road end, and the report says it is not the bake's",
       M["mid_leg_roads"] == [ZMID] and M["same_request_as_bake"] is False and "not the bake's" in M["note"]
       and q["origin"] == [f"{RQ[1]},{RQ[0]}"] and q["destination"] == [f"{RIN[1]},{RIN[0]}"] and len(URLS) == 1, str(M.get("note")))
    URLS.clear()
    N = network.no_through_diagnostics("R3", profile="No such lorry", leg="loaded")
    _, q = sent(URLS[-1])
    ok("5. places with no gate: the call runs marker to marker; an unknown vehicle is flagged (no vehicle figures went)",
       q["origin"] == ["52.6,-1.2"] and q["destination"] == ["52.61,-1.1"] and N["steps"] == []
       and N["profile_in_factors"] is False and not any(k.startswith("vehicle[") for k in q) and q["transportMode"] == ["truck"])
    ok("⭐ 5. the diagnostic wrote nothing: routes, stored lines and zones identical before and after", snapshot() == BEFORE)
    ok("🔴 5. the key is in no wrapper answer", KEY not in json.dumps([W, V, M, N, bad], default=str))
finally:
    here_routing.urllib.request.urlopen = _real_uo
    os.environ.pop("HERE_API_KEY", None)

# =========================================================================== #
#  6. Source                                                                   #
# =========================================================================== #
hr, net, mainsrc = read("backend/here_routing.py"), read("backend/network.py"), read("backend/main.py")
_probe = hr.split("def no_through_probe(")[1].split("\n# ----")[0]
_wrap = net.split("def no_through_diagnostics(")[1].split("\ndef ")[0]
_end = mainsrc.split('@app.get("/api/admin/diagnostics/no-through/{route_id}")')[1].split("\n@app")[0]
ok("⭐ 6. the endpoint is a GET behind the admin check, takes profile, leg and via, and says it costs one request",
   mainsrc.count('@app.get("/api/admin/diagnostics/no-through/{route_id}")') == 1 and _end.count("_check_admin(token)") == 1
   and _end.index("_check_admin(token)") < _end.index("network.no_through_diagnostics(")
   and "profile: str = network.DEFAULT_PROFILE" in _end and 'leg: str = "loaded"' in _end and "via: Optional[str] = None" in _end
   and "return network.no_through_diagnostics(route_id, profile=profile, leg=leg, via=via)" in _end
   and "Costs one HERE request" in _end and "Nothing is written or stored" in _end)
ok("🔴 6. the wrapper and the probe hold no write of any kind",
   not any(w in _wrap + _probe for w in ("db.execute", "INSERT ", "UPDATE ", "DELETE ", "_upsert_geom", "write(")))
ok("⭐ 6. the wrapper resolves the leg through the bake's own leg_request, avoid areas and pinned time",
   "leg_request(r, o, d, leg)" in _wrap and "active_avoid()" in _wrap and "here_routing.bake_departure_time()" in _wrap
   and 'laden=(leg == "loaded")' in _wrap)
ok("6. the probe makes ONE call and has no retry loop", _probe.count("urllib.request.urlopen(") == 1
   and "for attempt" not in _probe and "while " not in _probe)
ok("6. the values are fixed in code as asked", here_routing.NO_THROUGH_RETURN == RET and here_routing.NO_THROUGH_SPANS == SPANS)
_routes_fn = hr.split("def routes(")[1].split("\ndef route(")[0]
_bake = net.split("def _bake_leg(")[1].split("\ndef ")[0]
ok("🔴 6. no bake sends the new names: routes() still asks for the line and its summary, and nothing outside the "
   "diagnostic names them",
   '"return": "polyline,summary",' in _routes_fn and "noThrough" not in _routes_fn and "NO_THROUGH" not in _routes_fn
   and "noThrough" not in _bake and "no_through" not in _bake
   and all("noThrough" not in read(f) and "no_through" not in read(f) and "NO_THROUGH" not in read(f)
           for f in ("backend/haul.py", "backend/abnormal_route.py", "backend/limits.py", "backend/route_choice.py"))
   and net.count("no_through_probe(") == 1 and hr.count("def no_through_probe(") == 1 and mainsrc.count("no_through") == 2,
   f"{net.count('no_through_probe(')} {mainsrc.count('no_through')}")
ok("🔴 6. no screen or guide reads or names the diagnostic",
   all("no-through" not in read(f) and "no_through" not in read(f) and "noThrough" not in read(f)
       for f in ("frontend/index.html", "map/index.html", "frontend/help/index.html")))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
import shutil  # noqa: E402
remove_scratch_db(db, TMP)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)

"""
The Look-ahead's week by SITE (25 Nov 2026, the Look-ahead rethink, task A; card 1, John's "Yes, as recommended").

What this proves, on a scratch SQLite database with the shipped demo package imported (stubbed FastAPI, no network):
  1. the ONE rule (`la_sites.site_of`) on all 50 demo routes: 43 into one of the organisation's own places (a compound, a
     work site or a stockpile), 5 out of one (muck away, under the site they leave), 0 between two, 2 into the asphalt
     plant (under the plant); and on made-up ends: a line between two compounds goes under the one that RECEIVES it;
  2. the roll-up (`la_sites.roll_up`) on made-up decorated lines: a day's tonnes and loads add up, a day's lorries count
     routed lines only, the week's lorries are the busiest day, the out part is kept apart, the team only when one team's,
     the order of Data → Locations, a line with no place last;
  3. the page (`lookahead.page`) for the demo's commit week (pinned to 26 Nov 2026): every commit line, Account row and
     Horizon row carries `site`; `commit.sites` lists 7 sites in the order of Data → Locations, every line once, and the
     sites add up to the week's totals in tonnes and loads, day by day and for the week;
  4. a team login: its own lines only, its sites made of them, said once (`commit.team_only` = the team's name);
  5. the read is the tenant's own (one locations query with the tenant placeholder).

What this does NOT prove: the page in a browser (ui_fix_la_sites.js and Chrome); Postgres; live's routed lines (the
package carries no geometry, so every lorry figure here is 0 on the page: section 2 covers the lorry arithmetic).
"""
import datetime
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


class _HTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


class _App:
    def __init__(self, *a, **k):
        pass

    def _deco(self, *a, **k):
        return lambda f: f
    get = post = put = delete = patch = _deco

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


def _Query(default=None, **k):
    return default


class _Request:
    def __init__(self, headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = {}


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query
_fa.Request = _Request
sys.modules.setdefault("fastapi", _fa)
_mw = types.ModuleType("fastapi.middleware")
_cors = types.ModuleType("fastapi.middleware.cors")
_cors.CORSMiddleware = object
_mw.cors = _cors
sys.modules.setdefault("fastapi.middleware", _mw)
sys.modules.setdefault("fastapi.middleware.cors", _cors)
_resp = types.ModuleType("fastapi.responses")
_resp.FileResponse = lambda *a, **k: None
_resp.Response = _Response
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass

    async def get_response(self, path, scope):
        return None


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="wayscope_la_sites_")
from portable import remove_scratch_db, offline, pin_today   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
os.environ["WAYSCOPE_WARM_CACHE"] = "0"

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import config  # noqa: E402
import taxonomy  # noqa: E402
import costing  # noqa: E402
import tenant_package  # noqa: E402
import lookahead  # noqa: E402
import export  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import derived  # noqa: E402
import la_sites  # noqa: E402

access.set_current("planner123")
offline(export)
TODAY = pin_today(datetime.date(2026, 11, 26))      # the shipped demo's as-of Thursday: commit week Mon 23 – Sun 29 Nov

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


# --------------------------------------------------------------------------- the demo, imported
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
db.init_costing_db(); db.init_tenant()
taxonomy.seed_taxonomy()
config.seed_from_file(conversions)
config.invalidate(); costing.invalidate()
DEMO = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
res = tenant_package.import_tenant(DEMO, replace=True)
ok("0: the demo imports", res.get("ok") is True, str(res)[:200])
config.invalidate(); costing.invalidate()

# --------------------------------------------------------------------------- 1. the rule on all 50 routes
WHERE = la_sites.places()
ROUTES = derived._routes_and_names()
kinds = {"in": [], "out": [], "between": [], "neither": []}
for rid, r in sorted(ROUTES.items()):
    o, d = WHERE.get(r["origin_id"]), WHERE.get(r["dest_id"])
    k = ("between" if (o and d and o["own"] and d["own"]) else "out" if (o and o["own"]) else "in" if (d and d["own"]) else "neither")
    kinds[k].append(rid)
ok("1: the demo has 50 routes", len(ROUTES) == 50, str(len(ROUTES)))
ok("⭐ 1: 43 into one of the organisation's own places, 5 out of one, 0 between two, 2 into neither (the asphalt plant)",
   [len(kinds[k]) for k in ("in", "out", "between", "neither")] == [43, 5, 0, 2], str({k: len(v) for k, v in kinds.items()}))
SO = {rid: la_sites.site_of(r["origin_id"], r["dest_id"], WHERE) for rid, r in ROUTES.items()}
ok("1: every route gets a site (the demo's ends are all places)", all(SO.values()))
ok("⭐ 1: an IN route sits under its destination, direction in",
   all(SO[rid]["id"] == ROUTES[rid]["dest_id"] and SO[rid]["dir"] == "in" for rid in kinds["in"]))
ok("⭐ 1: an OUT route (muck away) sits under the own place it LEAVES, direction out: R019, R020, R025, R026, R050",
   kinds["out"] == ["R019", "R020", "R025", "R026", "R050"]
   and all(SO[rid]["id"] == ROUTES[rid]["origin_id"] and SO[rid]["dir"] == "out" for rid in kinds["out"]), str(kinds["out"]))
ok("1: the two asphalt plant routes (R027, R028) sit under the plant they deliver to, typed Asphalt plant",
   kinds["neither"] == ["R027", "R028"] and {SO[r]["name"] for r in kinds["neither"]} == {"Wolds Link Asphalt Plant"}
   and {SO[r]["type"] for r in kinds["neither"]} == {"Asphalt plant"} and all(SO[r]["dir"] == "in" for r in kinds["neither"]),
   str([SO[r] for r in kinds["neither"]]))
ok("1: OWN is a Compound, a Site or a Stockpile, read through the canonical type (network._role_for's three)",
   la_sites.OWN_TYPES == ("compound", "site", "stockpile")
   and all(p["own"] == (p["type"].lower() in ("compound", "site", "stockpile")) for p in WHERE.values()))
# made-up ends
W = {"C1": {"id": "C1", "name": "North Compound", "type": "Compound", "own": True, "order": 0},
     "C2": {"id": "C2", "name": "South Compound", "type": "Compound", "own": True, "order": 1},
     "Q1": {"id": "Q1", "name": "Hill Quarry", "type": "Quarry", "own": False, "order": 2},
     "S1": {"id": "S1", "name": "Bridge site", "type": "Site", "own": True, "order": 3}}
ok("⭐ 1: a made-up line BETWEEN two compounds goes under the one that receives it (listed once, never twice)",
   la_sites.site_of("C1", "C2", W) == {"id": "C2", "name": "South Compound", "type": "Compound", "dir": "in"}
   and la_sites.site_of("C2", "C1", W)["id"] == "C1" and la_sites.site_of("S1", "C2", W)["dir"] == "in")
ok("1: quarry to a site = under the site, in; a site to a quarry = under the site, out",
   la_sites.site_of("Q1", "S1", W) == {"id": "S1", "name": "Bridge site", "type": "Site", "dir": "in"}
   and la_sites.site_of("S1", "Q1", W) == {"id": "S1", "name": "Bridge site", "type": "Site", "dir": "out"})
ok("1: a destination no longer a place = under the origin as delivered (in); neither end a place = no site",
   la_sites.site_of("Q1", "GONE", W)["id"] == "Q1" and la_sites.site_of("Q1", "GONE", W)["dir"] == "in"
   and la_sites.site_of("GONE", "GONE2", W) is None and la_sites.site_of("S1", "GONE", W)["dir"] == "out")


# --------------------------------------------------------------------------- 2. the roll-up on made-up lines
def L(route, site, days, wk_t, wk_n, ipt="IPT1", baked=True, month=10):
    return {"route_id": route, "discipline": "Civils", "section_id": "WS1", "month_index": month, "site": site,
            "context": {"ipt": ipt, "baked": baked},
            "days": [{"day_date": iso, "derived": {"tonnes": t, "trips": n, "vehicles": v}} for iso, t, n, v in days],
            "week_derived": {"tonnes": wk_t, "trips": wk_n}}


D1, D2 = "2026-11-23", "2026-11-24"
sC2 = {"id": "C2", "name": "South Compound", "type": "Compound", "dir": "in"}
sS1i = {"id": "S1", "name": "Bridge site", "type": "Site", "dir": "in"}
sS1o = {"id": "S1", "name": "Bridge site", "type": "Site", "dir": "out"}
lines = [L("R1", sS1i, [(D1, 100.0, 5, 2), (D2, 50.0, 3, 1)], 150.0, 8),
         L("R2", sS1o, [(D1, 80.0, 4, 1), (D2, 80.0, 4, 1)], 160.0, 8),
         L("R3", sS1i, [(D1, 10.0, 1, 4), (D2, 0.0, 0, 0)], 10.0, 1, baked=False),
         L("R4", sC2, [(D1, 30.0, 2, 1), (D2, 30.0, 2, 1)], 60.0, 4, ipt="IPT2"),
         L("R5", None, [(D1, 5.0, 1, 1)], 5.0, 1)]
RU = la_sites.roll_up(lines, W)
ok("2: the order of Data → Locations (C2 before S1), a line with no place last (id None)",
   [x["id"] for x in RU] == ["C2", "S1", None], str([x["id"] for x in RU]))
s1 = RU[1]
ok("2: a site's line keys are the page's own key (route|discipline|section|month)",
   s1["lines"] == ["R1|Civils|WS1|10", "R2|Civils|WS1|10", "R3|Civils|WS1|10"], str(s1["lines"]))
ok("⭐ 2: a day's tonnes and loads add up over the site's lines, in and out together",
   s1["days"][D1]["t"] == 190.0 and s1["days"][D1]["loads"] == 10 and s1["days"][D2]["t"] == 130.0 and s1["days"][D2]["loads"] == 7,
   str(s1["days"]))
ok("⭐ 2: a day's lorries count ROUTED lines only (R3 not routed: its 4 left out)", s1["days"][D1]["lorries"] == 3 and s1["days"][D2]["lorries"] == 2)
ok("2: the week: tonnes and loads from the lines' week figures; lorries the busiest day",
   s1["week"] == {"t": 320.0, "loads": 17, "lorries": 3}, str(s1["week"]))
ok("⭐ 2: the out part kept apart: one out line, its tonnes, loads and lorries a day and for the week",
   s1["out_lines"] == 1 and s1["days"][D1]["out_t"] == 80.0 and s1["days"][D1]["out_loads"] == 4 and s1["days"][D1]["out_lorries"] == 1
   and s1["out_week"] == {"t": 160.0, "loads": 8, "lorries": 1}, str(s1["out_week"]))
ok("2: the team only when every line is one team's", s1["ipt"] == "IPT1" and RU[0]["ipt"] == "IPT2"
   and la_sites.roll_up([lines[0], dict(lines[2], context={"ipt": "IPT2", "baked": False})], W)[0]["ipt"] is None)
ok("2: the sites add up to the lines, day by day and for the week (tonnes, loads)",
   round(sum(x["week"]["t"] for x in RU), 3) == sum(l["week_derived"]["tonnes"] for l in lines)
   and sum(x["week"]["loads"] for x in RU) == sum(l["week_derived"]["trips"] for l in lines)
   and all(round(sum((x["days"].get(iso) or {}).get("t", 0) for x in RU), 3)
           == round(sum(d["derived"]["tonnes"] for l in lines for d in l["days"] if d["day_date"] == iso), 3) for iso in (D1, D2)))
ok("2: no line = no site", la_sites.roll_up([], W) == [])

# --------------------------------------------------------------------------- 3. the page, the demo's commit week
PLANNER = access.current()
PG = lookahead.page(bucket="commit", acc=PLANNER, with_restrictions=False)
C = PG["commit"]
CL = C["lines"]
ok("3: the commit week is 23–29 Nov 2026 with 22 lines", (PG.get("commit_week") or {}).get("from") == "2026-11-23" and len(CL) == 22,
   f'{PG.get("commit_week")} {len(CL)}')
ok("⭐ 3: every commit line, Account row and Horizon row carries its site (id, name, type, dir)",
   all(set((l.get("site") or {}).keys()) == {"id", "name", "type", "dir"} for l in CL)
   and all(r.get("site") for r in (PG.get("account") or {}).get("rows") or [] if r.get("route_id"))
   and all(r.get("site") for r in (PG.get("horizon") or {}).get("rows") or [] if r.get("route_id"))
   and len((PG.get("account") or {}).get("rows") or []) > 0 and len((PG.get("horizon") or {}).get("rows") or []) > 0)
SITES = C.get("sites") or []
ok("⭐ 3: seven sites in the order of Data → Locations",
   [s["name"] for s in SITES] == ["Harborough Compound", "Langton Compound", "Tilton Compound", "Melton Compound",
                                  "Stockpile Tilton", "Stockpile North", "Tilton Viaduct site"]
   and [WHERE[s["id"]]["order"] for s in SITES] == sorted(WHERE[s["id"]]["order"] for s in SITES), str([s["name"] for s in SITES]))
keys = [k for s in SITES for k in s["lines"]]
ok("3: every line under exactly one site, by the page's own key", sorted(keys) == sorted(la_sites._key(l) for l in CL) and len(set(keys)) == 22)
ok("3: a line's site is the site it is listed under", all(next(s for s in SITES if la_sites._key(l) in s["lines"])["id"] == l["site"]["id"] for l in CL))
T = C["totals"]
ok("⭐ 3: the sites add up to the week's totals: tonnes (planned_t) and loads (trips)",
   abs(sum(s["week"]["t"] for s in SITES) - T["planned_t"]) < 0.01 and sum(s["week"]["loads"] for s in SITES) == T["trips"],
   f'{sum(s["week"]["t"] for s in SITES)} / {T["planned_t"]}; {sum(s["week"]["loads"] for s in SITES)} / {T["trips"]}')
days = sorted({d["day_date"] for l in CL for d in l["days"]})
ok("⭐ 3: day by day the sites add up to the lines (tonnes, loads, lorries)",
   all(abs(sum((s["days"].get(iso) or {}).get("t", 0) for s in SITES) - sum((d.get("derived") or {}).get("tonnes") or 0 for l in CL for d in l["days"] if d["day_date"] == iso)) < 0.01
       and sum((s["days"].get(iso) or {}).get("loads", 0) for s in SITES) == sum((d.get("derived") or {}).get("trips") or 0 for l in CL for d in l["days"] if d["day_date"] == iso)
       and sum((s["days"].get(iso) or {}).get("lorries", 0) for s in SITES) == sum((d.get("derived") or {}).get("vehicles") or 0 for l in CL if (l.get("context") or {}).get("baked") for d in l["days"] if d["day_date"] == iso)
       for iso in days))
TV = next(s for s in SITES if s["name"] == "Tilton Viaduct site")
ok("⭐ 3: Tilton Viaduct site: 4 lines, ONE going out (to the inert landfill), its out part apart from the in",
   len(TV["lines"]) == 4 and TV["out_lines"] == 1 and TV["out_week"]["t"] > 0 and TV["out_week"]["t"] < TV["week"]["t"]
   and [l["site"]["dir"] for l in CL if la_sites._key(l) in TV["lines"]].count("out") == 1, str(TV["out_week"]))
ok("3: a site with one line (Tilton Compound) lists one key", len(next(s for s in SITES if s["name"] == "Tilton Compound")["lines"]) == 1)
ok("3: a planner's page says no team line", C.get("team_only") is None)

# --------------------------------------------------------------------------- 4. a team login
TEAM = {"role": "team", "ipt": "IPT1", "label": "North Team", "via": "code"}
PT = lookahead.page(bucket="commit", acc=TEAM, with_restrictions=False)
CT = PT["commit"]
ok("⭐ 4: a team's page: its own lines only, and its sites are made of them",
   len(CT["lines"]) > 0 and all(((l.get("context") or {}).get("ipt") or l.get("ipt")) == "IPT1" for l in CT["lines"])
   and sorted(k for s in CT["sites"] for k in s["lines"]) == sorted(la_sites._key(l) for l in CT["lines"])
   and len(CT["lines"]) < len(CL), f'{len(CT["lines"])} of {len(CL)}')
ok("⭐ 4: said once: commit.team_only is the team's NAME (never its slot id)", CT.get("team_only") == "North Team", str(CT.get("team_only")))
ok("4: the team's sites add up to its own totals", abs(sum(s["week"]["t"] for s in CT["sites"]) - CT["totals"]["planned_t"]) < 0.01)
ok("4: each of the team's sites is one team's (its ipt set)", all(s["ipt"] == "IPT1" for s in CT["sites"]))

# --------------------------------------------------------------------------- 5. the source
SRC = read("backend/la_sites.py")
LA = read("backend/lookahead.py")
ok("5: the locations read is the tenant's own, in the order of Data → Locations",
   'db.query("SELECT id, name, loc_type FROM locations WHERE tenant_id = ? ORDER BY id", (db.current_tenant(),))' in SRC)
ok("5: la_sites only reads: no write, no fetch", not any(w in SRC for w in ("db.execute(", "INSERT ", "UPDATE ", "DELETE ", "requests.", "urlopen")))
ok("5: the page stamps the lines, the Account and the Horizon rows and rolls the sites up once",
   "la_sites.stamp(visible, routes, where)" in LA and 'commit["sites"] = la_sites.roll_up(visible, where)' in LA
   and 'la_sites.stamp(acct["rows"], routes, where)' in LA and 'la_sites.stamp(hz["rows"], routes, where)' in LA
   and 'commit["team_only"] = _team_only(acc)' in LA)

remove_scratch_db(db, TMP)
print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)

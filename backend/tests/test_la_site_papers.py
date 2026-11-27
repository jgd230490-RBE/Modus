"""
test_la_site_papers.py — 25 Nov 2026, the Look-ahead rethink, task C2 (`claude/la-site-papers`).

The week's PDF, the week's XLSX and the Day sheet put their lines under their SITE (task A's rule, `la_sites`), in the
order of Data → Locations, with a ruled heading and a sub-total a site. Each file is built twice from the same page:
grouped, and with the site keys taken off (the older, ungrouped print), and the grand totals are compared word for word.
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

TMP = tempfile.mkdtemp(prefix="wayscope_la_papers_")
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


# --------------------------------------------------------------------------- helpers
import copy  # noqa: E402
import io  # noqa: E402
import re  # noqa: E402
import openpyxl  # noqa: E402
from portable import pdf_text  # noqa: E402

PLANNER = access.current()
PG = lookahead.page(bucket="commit", acc=PLANNER, with_restrictions=False)
CL = PG["commit"]["lines"]
SITES = PG["commit"]["sites"]
ORDER = [s["name"] for s in SITES]


def unsited(pg):
    """The same page with no `site` on any line: export's older path, the one list as it printed before 25 Nov."""
    q = copy.deepcopy(pg)
    for l in q["commit"]["lines"]:
        l.pop("site", None)
    return q


def words(b, raw=True):
    return " ".join(pdf_text(b, "", raw=raw).split())


ok("0: the demo's commit week: 22 lines in 7 sites", len(CL) == 22 and len(SITES) == 7, f"{len(CL)} {len(SITES)}")

# --------------------------------------------------------------------------- 1. the helper
G = export.site_groups(CL)
ok("⭐ 1: site_groups: the sites in the order of Data → Locations, every line once",
   [export.site_name(s) for s, _ in G] == ORDER and sorted(la_sites._key(l) for _, ls in G for l in ls) == sorted(la_sites._key(l) for l in CL),
   str([export.site_name(s) for s, _ in G]))
ok("⭐ 1: under each site its lines in, then its out lines LAST",
   all([export.site_is_out(l) for l in ls] == sorted(export.site_is_out(l) for l in ls) for _, ls in G))
ok("1: a page whose lines carry no site gives None (an older read prints as before)", export.site_groups(unsited(PG)["commit"]["lines"]) is None)
_mk = [dict(CL[0], site=None), dict(CL[1])]
_gm = export.site_groups(_mk)
ok("1: a line with no site goes last, under \"Other lines\"", _gm[-1][0] is None and export.site_name(_gm[-1][0]) == "Other lines")
ok("1: the heading's words: type · n lines · the team when every line is one team's",
   export.site_heading_words({"type": "Compound"}, [{"context": {"ipt": "IPT1"}}] * 2, lambda v: "North Team") == "Compound · 2 lines · North Team"
   and export.site_heading_words({"type": "Site"}, [{"context": {"ipt": "IPT1"}}, {"context": {"ipt": "IPT2"}}], lambda v: v) == "Site · 2 lines"
   and export.site_heading_words({"type": ""}, [{"context": {}}], lambda v: v) == "1 line")

# --------------------------------------------------------------------------- 2. the week's PDF
pb_new = export.build_pdf(PG)
pb_old = export.build_pdf(unsited(PG))
tn, to = words(pb_new), words(pb_old)
ok("2: the week's PDF builds both ways", pb_new[:5] == b"%PDF-" and pb_old[:5] == b"%PDF-")
ok("⭐ 2: the site headings print in the order of Data → Locations",
   all(n in tn for n in ORDER) and [tn.index(n + " ") for n in ORDER] == sorted(tn.index(n + " ") for n in ORDER), str(ORDER))


def tail(t, a, b):
    return t[t.rindex(a):t.index(b, t.rindex(a))] if a in t and b in t else ""


GT_N, GT_O = tail(tn, "TOTAL", "Flags (not a stop)"), tail(to, "TOTAL", "Flags (not a stop)")
ok("⭐ 2: the GRAND TOTAL row is the same to the last digit as the ungrouped sheet's (lines, tonnes, trips, tonne-miles, money)",
   GT_N and GT_N == GT_O and "22 line(s)" in GT_N, f"new {GT_N!r} old {GT_O!r}")
ok("2: a sub-total a site, each naming its site and its lines",
   all(re.search(re.escape(f"{s['name']} · {len(s['lines'])} line{'' if len(s['lines']) == 1 else 's'}"), tn) for s in SITES))
ok("⭐ 2: an out line reads \"Out, to <destination>\", the others \"From <origin>\"",
   "Out, to " in tn and tn.count("From ") >= 21 and "Out, to " not in to and "From " not in to.split("TOTAL")[0][-4000:].split("ROUTE")[-1])
TVS = next(s for s in SITES if s["name"] == "Tilton Viaduct site")
ok("⭐ 2: the site that sends something out says how much goes out in its sub-total (the screen's \"n t out\")",
   f"{export._n(TVS['out_week']['t'])} t out" in tn, export._n(TVS["out_week"]["t"]))
# the sub-totals, added from the printed rows, are the screen's own site totals (commit.sites)
for s in SITES:
    rows = [r for r in export._pdf_rows(PG) if la_sites._key(r["line"]) in s["lines"]]
    ok(f"2: {s['name']}: its sub-total's week tonnes are the screen's ({export._n(s['week']['t'])} t)",
       abs(sum(float(r["wk"].get("tonnes") or 0) for r in rows) - s["week"]["t"]) < 0.01)
ok("2: the sub-totals add up to the grand total (tonnes)",
   abs(sum(s["week"]["t"] for s in SITES) - sum(float((l.get("week_derived") or {}).get("tonnes") or 0) for l in CL)) < 0.01)
ok("2: no map picture added: the grouped PDF holds as many pictures as the ungrouped one",
   pb_new.count(b"/Subtype /Image") == pb_old.count(b"/Subtype /Image"), f"{pb_new.count(b'/Subtype /Image')} {pb_old.count(b'/Subtype /Image')}")

# --------------------------------------------------------------------------- 3. the week's XLSX
xb_new, xb_old = export.build_xlsx(PG), export.build_xlsx(unsited(PG))
WBN = openpyxl.load_workbook(io.BytesIO(xb_new))
wn, wo = WBN["Commit week"], openpyxl.load_workbook(io.BytesIO(xb_old))["Commit week"]
hd = [c.value for c in wn[1]]
ci = {h: i for i, h in enumerate(hd)}
rows_n = [[c.value for c in r] for r in wn.iter_rows(min_row=2)]
rows_o = [[c.value for c in r] for r in wo.iter_rows(min_row=2)]
ok("3: the supplier's sheet: the same headers, and every row is still a line (one a weekday a line, nothing added among them)",
   hd == [c.value for c in wo[1]] and all(r[ci["Route"]] for r in rows_n) and len(rows_n) == len(rows_o) == 22 * 5,
   f"{len(rows_n)} {len(rows_o)}")
ok("⭐ 3: the supplier's sheet holds the same rows, unchanged, only in site order",
   sorted(map(repr, rows_n)) == sorted(map(repr, rows_o)))
ok("⭐ 3: its grand total is unchanged to the last digit (the Tonnes and Trips columns' sums)",
   round(sum(float(r[ci["Tonnes"]] or 0) for r in rows_n), 6) == round(sum(float(r[ci["Tonnes"]] or 0) for r in rows_o), 6)
   and sum(int(r[ci["Trips"]] or 0) for r in rows_n) == sum(int(r[ci["Trips"]] or 0) for r in rows_o))
ok("3: five sheets: Commit week, By site, Fuel, Clashes, About; an ungrouped page has no By site sheet",
   WBN.sheetnames == ["Commit week", "By site", "Fuel", "Clashes", "About"]
   and openpyxl.load_workbook(io.BytesIO(xb_old)).sheetnames == ["Commit week", "Fuel", "Clashes", "About"], str(WBN.sheetnames))
wb_s = WBN["By site"]
hs = [c.value for c in wb_s[1]]
cs = {h: i for i, h in enumerate(hs)}
rows_s = [[c.value for c in r] for r in wb_s.iter_rows(min_row=2)]
kind = lambda r: ("sub" if str(r[0] or "").startswith("Sub-total") else "total" if str(r[0] or "").startswith("Total ·")
                  else "line" if r[cs["Route"]] else "site")
heads = [r for r in rows_s if kind(r) == "site"]
subs = [r for r in rows_s if kind(r) == "sub"]
lines_s = [r for r in rows_s if kind(r) == "line"]
tot = [r for r in rows_s if kind(r) == "total"]
ok("3: By site's columns: the site or line, the route and its ends, the week's figures (no Date: a row is a week)",
   hs[:4] == ["Site / line", "Route", "Origin", "Destination"] and "Date" not in hs and "Vehicles on the busiest day" in hs, str(hs))
ok("⭐ 3: By site: one heading and one sub-total a site, the headings in the order of Data → Locations, ONE row a line",
   len(heads) == len(subs) == 7 and [str(h[0]).split(" · ")[0] for h in heads] == ORDER and len(lines_s) == 22,
   str([h[0] for h in heads]))
ok("⭐ 3: By site: a line row reads \"From <origin>\" (the out line \"Out, to <destination>\", last under its site)",
   sum(1 for r in lines_s if str(r[0]).startswith("From ")) == 21
   and [str(r[0]) for r in lines_s if str(r[0]).startswith("Out, to ")] == ["Out, to " + str(r[cs["Destination"]]) for r in lines_s if str(r[0]).startswith("Out, to ")]
   and len([r for r in lines_s if str(r[0]).startswith("Out, to ")]) == 1)
_csum = lambda col, rs=rows_o: sum(float(r[ci[col]] or 0) for r in rs)
ok("⭐ 3: By site: ONE Total row at the foot, \"Total · 7 sites\"", len(tot) == 1 and rows_s[-1] is tot[0] and tot[0][0] == "Total · 7 sites", str(tot[:1]))
T = tot[0] if tot else [None] * len(hs)
for col, nd in (("Tonnes", 3), ("Trips", 0), (export.xlsx_cols()[16][0], 3), (export.xlsx_cols()[17][0], 2), (export.xlsx_cols()[19][0], 2)):
    ok(f"⭐ 3: By site's Total {col} is Commit week's column sum to the last digit",
       # a column no row fills (t·km and BAF with no fuel index here) is a blank Total over a blank column
       (T[cs[col]] is None and all(r[ci[col]] is None for r in rows_n))
       or (T[cs[col]] is not None and round(float(T[cs[col]]), nd) == round(_csum(col, rows_n), nd) == round(_csum(col), nd)),
       f"{T[cs[col]]} vs {round(_csum(col, rows_n), nd)}")
ok("⭐ 3: By site: each line's week figures add its own day rows on Commit week (tonnes, trips)",
   all(abs(float(r[cs["Tonnes"]] or 0) - sum(float(d[ci["Tonnes"]] or 0) for d in rows_n if d[ci["Route"]] == r[cs["Route"]]
       and d[ci["WS"]] == r[cs["WS"]] and d[ci["Material"]] == r[cs["Material"]] and d[ci["Origin"]] == r[cs["Origin"]])) < 0.01
       for r in lines_s if sum(1 for x in lines_s if (x[1], x[5], x[6], x[2]) == (r[1], r[5], r[6], r[2])) == 1))
ok("⭐ 3: By site: the sub-totals add to the Total (tonnes, trips) and each equals the screen's site week",
   abs(sum(float(s[cs["Tonnes"]] or 0) for s in subs) - float(T[cs["Tonnes"]] or 0)) < 0.01
   and sum(int(s[cs["Trips"]] or 0) for s in subs) == int(T[cs["Trips"]] or 0)
   and all(abs(float(sb[cs["Tonnes"]]) - s["week"]["t"]) < 0.01 for sb, s in zip(subs, SITES)))
ok("3: By site: a site's lines add up to its sub-total",
   all(abs(sum(float(x[cs["Tonnes"]] or 0) for x in rows_s[rows_s.index(h) + 1:rows_s.index(sb)]) - float(sb[cs["Tonnes"]] or 0)) < 0.01
       for h, sb in zip(heads, subs)))
ok("3: By site: Vehicles is the busiest day's (never more than the week's days added)",
   all(r[cs["Vehicles on the busiest day"]] is None or isinstance(r[cs["Vehicles on the busiest day"]], int) for r in lines_s + subs + tot))
ok("3: the out part is said on the sending site's sub-total", any(" t out" in str(s[0]) and "Tilton Viaduct site" in str(s[0]) for s in subs))
_rs = list(wb_s.iter_rows(min_row=2))
_hrow = next(r for r in _rs if kind([c.value for c in r]) == "site")
_srow = next(r for r in _rs if kind([c.value for c in r]) == "sub")
ok("3: a heading row is bold with a rule over it; a sub-total bold on its grey; the Total bold and ruled",
   _hrow[0].font.bold and _hrow[0].border.top.style == "medium" and _srow[0].font.bold and _srow[0].fill.fgColor.rgb.endswith(export.SITE_SUB_HEX)
   and _rs[-1][0].font.bold and _rs[-1][0].border.top.style == "medium")

# --------------------------------------------------------------------------- 4. the Day sheet
DAY = "2026-11-25"
dn, do = export.build_day_sheet_pdf(PG, DAY), export.build_day_sheet_pdf(unsited(PG), DAY)
tdn, tdo = words(dn), words(do)
rows_d = export.day_sheet_rows(PG, DAY)
ok("4: the Day sheet's rows are the same list, each with its site", len(rows_d) == len(export.day_sheet_rows(unsited(PG), DAY))
   and all("site" in r for r in rows_d) and not any("site" in r for r in export.day_sheet_rows(unsited(PG), DAY)))
ok("⭐ 4: the Day sheet's headings in the order of Data → Locations",
   [tdn.index(n + " ") for n in ORDER if n + " " in tdn] == sorted(tdn.index(n + " ") for n in ORDER if n + " " in tdn)
   and sum(1 for n in ORDER if n + " " in tdn) >= 6)
GD_N, GD_O = tail(tdn, "Total ·", "Flags (a flag"), tail(tdo, "Total ·", "Flags (a flag")
ok("⭐ 4: the Day sheet's TOTAL row is the same to the last digit (lines, tonnes, loads, lorries)",
   GD_N and GD_N == GD_O, f"{GD_N!r} / {GD_O!r}")
_fig = lambda t: t[:t.index("FROM / TO")] if "FROM / TO" in t else ""
ok("4: the day's figures line over the table is unchanged", _fig(tdn) and _fig(tdn) == _fig(tdo), _fig(tdn))
ok("4: the flags under the table keep their printed words (DAY_FLAG_WORD) and their count line",
   tail(tdn, "Flags (a flag", "Loads are loaded") == tail(tdo, "Flags (a flag", "Loads are loaded"))
dsg = export.site_groups(rows_d)
ok("⭐ 4: each site's sub-total adds its own rows (tonnes, loads) and the sub-totals add to the day's total",
   abs(sum(sum(r["tonnes"] or 0 for r in rs) for _, rs in dsg) - export.day_sheet_totals(rows_d)["tonnes"]) < 0.01
   and sum(sum(r["loads"] for r in rs) for _, rs in dsg) == export.day_sheet_totals(rows_d)["loads"])
ok("4: under a site a line reads \"From <origin>\" (an out line \"Out, to …\"), not \"<origin> to <destination>\"",
   "From " in tdn and not re.search(r"(?<!Out,) to Melton Compound", tdn.split("Flags (a flag")[0])
   and " to Melton Compound" in tdo.split("Flags (a flag")[0])

# --------------------------------------------------------------------------- 5. a team login
TEAM = {"role": "team", "ipt": "IPT1", "label": "North Team", "via": "code"}
PT = lookahead.page(bucket="commit", acc=TEAM, with_restrictions=False)
tt = words(export.build_pdf(PT))
ok("⭐ 5: a team's week PDF: only its own sites, and its grand total the same as its ungrouped sheet's",
   all((s["name"] + " ") in tt for s in PT["commit"]["sites"])
   and not any((n + " · ") in tt for n in ORDER if n not in [s["name"] for s in PT["commit"]["sites"]])
   and tail(tt, "TOTAL", "Flags (not a stop)") == tail(words(export.build_pdf(unsited(PT))), "TOTAL", "Flags (not a stop)"))

# --------------------------------------------------------------------------- 6. made-up: many lines, priced, unrouted
BIG = copy.deepcopy(PG)
BIG["commit"]["lines"] = [copy.deepcopy(CL[i % 22]) for i in range(60)]
tb, tbo = words(export.build_pdf(BIG)), words(export.build_pdf(unsited(BIG)))
ok("6: sixty lines over several pages: the grand total the same as ungrouped", tail(tb, "TOTAL", "Flags (not a stop)") == tail(tbo, "TOTAL", "Flags (not a stop)")
   and "60 line(s)" in tb)

# --------------------------------------------------------------------------- 7. the source
EXP = read("backend/export.py")
ok("7: the papers take the site from task A's rule and the order from la_sites.places(), never a rule of their own",
   "la_sites.places()" in EXP and "site_of(" not in EXP.split("def site_groups")[1].split("def _coord")[0]
   and "_role_for" not in EXP and "canonical_loc_type" not in EXP)
ok("7: no new fetch and no map picture in the week's and the day's functions",
   EXP.count("basemap.fetch(") == read("backend/export.py").count("basemap.fetch(")
   and "urlopen" not in EXP.split("def site_groups")[1].split("def _coord")[0])
ok("7: the Day sheet keeps DAY_FLAG_WORD for its flags (short capitals)", 'DAY_FLAG_WORD = {"LIMIT": "ROAD LIMIT"' in EXP)

remove_scratch_db(db, TMP)
print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)

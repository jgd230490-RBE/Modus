"""
Supplier orders (8 Nov 2026, v2.1 task 2.1-10; mockup notes/supplier-orders-mockup-1108, John: "Yes, as recommended",
Q1-Q12). One order sheet per supplier from the Look-ahead's commit week: PDF, XLSX, or every supplier in a zip.

WHAT IS ASSERTED
----------------
  * who is a supplier: a route's origin that is not one of the scheme's own places (Q5); confirmed lines only (Q2);
  * the shipped demo's week of 23 Nov 2026 read exactly: quantities, loads, gates, hours, closed days, site rules,
    holding area (Q9), the pour (Q7), lines merged by gate + material + unit + vehicle (Q6), m3 kept as m3 (Q3);
  * no price anywhere (Q4); a team sees its own lines and the sheet says so (Q1); weekend columns only when used (Q8);
  * the PDF's text, the XLSX's cells (numbers, not text), the zip's files (no route sheets, Q10);
  * the two endpoints (stubbed FastAPI): downloads, refusals, signed-out 401; the screen and the guides (source).

WHAT THIS DOES NOT PROVE
------------------------
The browser download itself (checked by hand in Chrome on a local copy), Postgres, and the live demo's own week.

Run:  python3 backend/tests/test_supplier_orders.py
"""
import copy
import datetime
import io
import json
import os
import re
import sys
import tempfile
import types
import zipfile

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

TMP = tempfile.mkdtemp(prefix="wayscope_supplier_orders_")
from portable import remove_scratch_db, pdf_text, offline, pin_today   # noqa: E402
os.environ.pop("DATABASE_URL", None)
os.environ.pop("TENANT_ID", None)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE", "ADMIN_TOKEN"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
os.environ["ADMIN_TOKEN"] = "supplier-orders-admin-token"
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
import supplier_orders as so  # noqa: E402

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

PLANNER = access.current()
PG = lookahead.page(bucket="commit", acc=PLANNER, with_restrictions=False)
ok("0: the pinned commit week is Mon 23 – Sun 29 Nov 2026",
   (PG["commit_week"] or {}).get("from") == "2026-11-23" and (PG["commit_week"] or {}).get("to") == "2026-11-29",
   str(PG.get("commit_week")))
PG_COPY = copy.deepcopy(PG)
D = so.orders(PG, acc=PLANNER)
ok("0: orders() leaves the page it was given unchanged (the page is the kept Look-ahead read)", PG == PG_COPY)
S = {s["location_id"]: s for s in D["suppliers"]}

# --------------------------------------------------------------------------- 1. who is a supplier (Q2, Q5)
ok("1: four suppliers that week: Northfield Quarry, the batching plant, Brook Pit, Harborough RFT",
   set(S) == {"L002", "L014", "L003", "L004"}, str(sorted(S)))
ok("1: heaviest first by the week's quantity", D["suppliers"][0]["location_id"] == "L002", D["suppliers"][0]["location_id"])
LO = D["left_out"]
ok("1 (Q2): the 4 lines not confirmed yet are left out and counted", LO["not_confirmed"] == 4, str(LO))
ok("1 (Q2): ...and their places named for the screen",
   set(LO["not_confirmed_places"]) == {"Kilby Ridge Quarry", "Harborough Rail Freight Terminal"}, str(LO))
ok("1 (Q2): Kilby Ridge Quarry (typed, not confirmed) gets no order", "L001" not in S)
ok("1 (Q5): the scheme's own site sending spoil to the landfill is left out and counted",
   LO["own"] == 1 and LO["own_places"] == ["Tilton Viaduct site"], str(LO))
ok("1 (Q5): the scheme's own place types", so.OWN_TYPES == ("Compound", "Site", "Stockpile", "Holding area"))
try:
    so.find(D, "L001")
    ok("1: find() refuses a place with no confirmed lines", False)
except so.OrderError as e:
    ok("1: find() refuses a place with no confirmed lines, in words", "no confirmed lines" in str(e), str(e))
unconf = copy.deepcopy(PG)
for l in unconf["commit"]["lines"]:
    if l.get("week"):
        l["week"]["status"] = "derived"
D0 = so.orders(unconf, acc=PLANNER)
ok("1 (Q2): a week with no confirmed line has no supplier order at all", D0["suppliers"] == [], str(len(D0["suppliers"])))
ok("1 (Q2): ...and says how many lines wait", D0["left_out"]["not_confirmed"] >= 20, str(D0["left_out"]))

# --------------------------------------------------------------------------- 2. Northfield Quarry's order
N = S["L002"]
ok("2: the supplier's company name typed on Locations", N["vendor"] == "Northfield Stone Co.", str(N["vendor"]))
ok("2: three deliveries", N["deliveries"] == 3 and len(N["rows"]) == 3)
R = {r["dest_name"]: r for r in N["rows"]}
ok("2: to Melton Compound, Stockpile North and Tilton Viaduct site",
   set(R) == {"Melton Compound", "Stockpile North", "Tilton Viaduct site"}, str(sorted(R)))
M = R["Melton Compound"]
ok("2: Melton Compound 395 t on each weekday", [M["qty"].get(d) for d in N["days"]] == [395.0] * 5, str(M["qty"]))
ok("2: ...14 loads a day", [M["loads"].get(d) for d in N["days"]] == [14] * 5, str(M["loads"]))
ok("2: ...1,975 t and 70 loads in the week", M["week_qty"] == 1975 and M["week_loads"] == 70)
ok("2: Stockpile North 200 t a day, Tilton Viaduct 60 t a day",
   R["Stockpile North"]["qty"]["2026-11-23"] == 200 and R["Tilton Viaduct site"]["qty"]["2026-11-27"] == 60)
ok("2: the week is 3,275 t of tonnes, 655 t each day",
   N["units"]["t"]["week"] == 3275 and all(v == 655 for v in N["units"]["t"]["day"].values()), str(N["units"]))
ok("2: 24 loads a day, 120 in the week", N["loads_day_max"] == 24 and N["week_loads"] == 120)
ok("2: the material and the vehicle a person reads", M["material"] == "Small aggregate" and M["vehicle"] == "Tipper (44t)",
   f"{M['material']} {M['vehicle']}")
ok("2: the route sheet named", M["route_ids"] == ["R011"], str(M["route_ids"]))
ok("2: the delivery gate and its hours", M["gate"] == "Compound gate" and M["open"] == "07:30–18:00", f"{M['gate']} {M['open']}")
ok("2: no deliveries in the scheme's peak bands", M["no_deliveries"].startswith("08:00–09:00"), M["no_deliveries"])
ok("2: closed days in plain words", M["closed"] == "Saturdays and Sundays", M["closed"])
ok("2: the site rules of the delivery site", (M["site_rules"] or "").startswith("Site speed 10 mph"), str(M["site_rules"]))
T = R["Tilton Viaduct site"]
ok("2: a site with a gate in and a gate out names both",
   T["gate"] == "South lane gate (in)" and T["exit_gate"] == "South lane gate (out)", f"{T['gate']} / {T['exit_gate']}")
ok("2 (Q9): a delivery that calls off through a holding area names it", T["holding"] == "Billesdon Lane holding area",
   str(T["holding"]))
ok("2 (Q9): ...and one that does not, does not", M["holding"] is None)
ok("2: lorries leave the quarry by its own gate, with its hours", N["leave_by"] == "A6 exit, 06:00–18:00, closed on Sundays",
   str(N["leave_by"]))
ok("2 (Q8): Saturday and Sunday are left off when nothing is on them", N["days"] == [
    "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27"], str(N["days"]))
ok("2 (Q11): the reference is the week and the place", N["reference"] == "SO-20261123-L002", N["reference"])
ok("2 (Q11): made by the signed-in role for a shared code", D["made_by"] == "Planner", D["made_by"])
ok("2 (Q11): a login is named by the person", so.made_by({"via": "login", "name": "Sam Planner", "label": "Planner"}) == "Sam Planner")
ok("2: the file name", N["file_stem"] == "supplier-order-2026-11-23-northfield-quarry", N["file_stem"])
ok("2: no team on a whole-scheme order", D["team_only"] is None)

# --------------------------------------------------------------------------- 3. the batching plant, m³, pours, merging
B = S["L014"]
ok("3 (Q3): concrete in its own unit, m³: 1,072.5 in the week", list(B["units"]) == ["m3"] and B["units"]["m3"]["week"] == 1072.5,
   str(B["units"]))
ok("3: an uneven day kept as it is (Thu 26 Nov 184.5 m³)", B["units"]["m3"]["day"]["2026-11-26"] == 184.5,
   str(B["units"]["m3"]["day"]))
BR = {r["dest_name"]: r for r in B["rows"]}
ok("3 (Q6): the three lines to Melton Compound are one row, summed (48 + 29 + 30.5 = 107.5 m³ a day)",
   BR["Melton Compound"]["qty"]["2026-11-23"] == 107.5 and BR["Melton Compound"]["route_ids"] == ["R022"],
   str(BR["Melton Compound"]["qty"]))
ok("3 (Q7): the plant's pour that week is on its order", any(p["date"] == "2026-11-26" and p["m3"] for p in B["pours"]),
   str(B["pours"]))
ok("3 (Q7): ...and only on the plant's", all(not S[k]["pours"] for k in ("L002", "L003", "L004")))
H = S["L004"]
HR = {(r["dest_name"], r["material"]): r for r in H["rows"]}
ok("3 (Q6): Harborough RFT's three team lines to Melton (5 t each) are one row of 15 t a day",
   HR[("Melton Compound", "General / imported")]["qty"]["2026-11-23"] == 15, str(sorted(HR)))
ok("3 (Q6): ...a different material to the same gate stays its own row",
   HR[("Melton Compound", "Precast / concrete")]["qty"]["2026-11-23"] == 25)
ok("3 (Q2): Harborough RFT's two unconfirmed lines are not on its order", H["units"]["t"]["week"] == 250, str(H["units"]))
ok("3 (Q6): no team id or name in any row", not any(k in r for s in D["suppliers"] for r in s["rows"] for k in ("ipt", "team")))

# --------------------------------------------------------------------------- 4. no price, ever (Q4)
def strings(o, out=None):
    out = out if out is not None else []
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(str(k)); strings(v, out)
    elif isinstance(o, (list, tuple)):
        for v in o:
            strings(v, out)
    elif isinstance(o, str):
        out.append(o)
    return out


ALL = " ".join(strings(D))
ok("4 (Q4): no price, rate or currency anywhere in the orders",
   not re.search(r"£|€|\bprice\b(?! *s\b)|\brate_set\b|\beur\b|\bbaf\b|\bfair\b|\bcost", ALL.replace("no prices", ""), re.I),
   re.findall(r"£|€|price|rate_set|eur|baf|fair|cost", ALL, re.I)[:5])

# --------------------------------------------------------------------------- 5. a team sees its own lines (Q1)
TEAM = {"role": "ipt", "ipt": "IPT1", "label": "North Team"}
PGT = lookahead.page(bucket="commit", acc=TEAM, with_restrictions=False)
DT = so.orders(PGT, acc=TEAM)
ok("5 (Q1): a team's orders say whose lines they are", DT["team_only"] == "North Team", str(DT["team_only"]))
team_routes = {l["route_id"] for l in PGT["commit"]["lines"]}
ok("5 (Q1): ...and carry only routes of the team's own lines",
   all(rid in team_routes for s in DT["suppliers"] for r in s["rows"] for rid in r["route_ids"]))
ok("5 (Q1): in the demo every confirmed line that week is North Team's, so its orders equal the whole scheme's",
   [x["location_id"] for x in DT["suppliers"]] == [x["location_id"] for x in D["suppliers"]])
CEN = {"role": "ipt", "ipt": "IPT2", "label": "Central Team"}
DC = so.orders(lookahead.page(bucket="commit", acc=CEN, with_restrictions=False), acc=CEN)
ok("5 (Q1): Central Team (no confirmed line) gets no order", DC["team_only"] == "Central Team" and DC["suppliers"] == [],
   str(DC["suppliers"])[:200])
ok("5 (Q1): ...and its left-out count is its own two lines, not the scheme's four", DC["left_out"]["not_confirmed"] == 2,
   str(DC["left_out"]))

# --------------------------------------------------------------------------- 6. the PDF
PDF = so.build_pdf(D, N)
ok("6: the PDF is a PDF", PDF[:5] == b"%PDF-", PDF[:8])
TXT = pdf_text(PDF) or ""
if TXT:
    ok("6: titled as a supplier order of the organisation", "Supplier order" in TXT and "Wolds Link dualling" in TXT, TXT[:200])
    ok("6: the supplier and the company", "Northfield Quarry" in TXT and "Northfield Stone Co." in TXT)
    ok("6: CONFIRMED, not a purchase order, no prices", "CONFIRMED" in TXT and "Not a purchase order" in TXT and "no prices" in TXT)
    ok("6: the demo notice", "Fictional scheme" in TXT)
    ok("6: the week", "Week of Mon 23 Nov 2026" in TXT)
    ok("6: the figures as on the Look-ahead", "395 t" in TXT and "1,975 t" in TXT and "3,275 t" in TXT and "14 loads" in TXT)
    ok("6: the gates' hours, no-delivery bands and closed days", "07:30–18:00" in TXT or "07:30" in TXT)
    ok("6: the holding area for the viaduct", "Billesdon Lane holding area" in TXT)
    ok("6: the route sheets named", "R011" in TXT and "R018" in TXT and "R045" in TXT)
    ok("6: the reference and who made it", "SO-20261123-L002" in TXT and "by Planner" in TXT)
    ok("6: sent by the organisation, Wayscope sends nothing", "not by Wayscope" in TXT and "Wayscope sends nothing" in TXT)
    ok("6 (Q4): no currency on the page", "£" not in TXT and "€" not in TXT)
    ok("6 (Q8): no weekend column", "SAT 28" not in TXT and "SUN 29" not in TXT)
    TXTB = pdf_text(so.build_pdf(D, B)) or ""
    ok("6 (Q7): the plant's pour block", "Pours this week" in TXTB and "Thu 26 Nov" in TXTB, TXTB[:400])
    ok("6 (Q3): concrete in m³", "107.5 m³" in TXTB or "107.5 m3" in TXTB)
    TXTT = pdf_text(so.build_pdf(DT, DT["suppliers"][0])) or ""
    ok("6 (Q1): a team's sheet says it is the team's lines only", "North Team's lines only" in TXTT, TXTT[:300])
else:
    ok("6: pdftotext is available to read the PDF", False, "pdftotext missing")

# --------------------------------------------------------------------------- 7. the XLSX
import openpyxl  # noqa: E402
wb = openpyxl.load_workbook(io.BytesIO(so.build_xlsx(D, N)))
ws = wb["Order"]
ok("7: one sheet, Order", wb.sheetnames == ["Order"], str(wb.sheetnames))
head = [c.value for c in ws[6]]
ok("7: the column headings", head[:8] == list(so.XLSX_COLS) and head[8] == "Mon 23 Nov" and head[12] == "Fri 27 Nov"
   and head[-3:] == ["Week", "Loads a day", "Route sheet"], str(head))
ok("7 (Q4): no price column", not any(re.search(r"price|rate|£|cost", str(h or ""), re.I) for h in head))
row = {ws.cell(row=i, column=1).value: [c.value for c in ws[i]] for i in range(7, 10)}
mel = row.get("Melton Compound") or []
ok("7: Melton Compound's days are numbers, not text", mel[8:13] == [395] * 5 and all(isinstance(v, int) for v in mel[8:13]),
   str(mel))
ok("7: ...the week, loads a day and the route sheet", mel[13] == 1975 and mel[14] == 14 and mel[15] == "R011", str(mel[13:]))
ok("7: the title row names the supplier and CONFIRMED", "Northfield Quarry" in str(ws["A1"].value) and "CONFIRMED" in str(ws["A1"].value))
ok("7: not a purchase order, sent by the organisation", "Not a purchase order" in str(ws["A2"].value)
   and "not by Wayscope" in str(ws["A2"].value))
ok("7: the reference", "SO-20261123-L002" in str(ws["B4"].value))
tot = [c.value for c in ws[10]]
ok("7: the each-day row sums the days", tot[0] == "Each day" and tot[8:14] == [655] * 5 + [3275], str(tot))
wbb = openpyxl.load_workbook(io.BytesIO(so.build_xlsx(D, B)))
vals = [c.value for r in wbb["Order"].iter_rows() for c in r]
ok("7 (Q3): m³ written as the unit, 107.5 a number", "m³" in vals and 107.5 in vals)
ok("7 (Q7): the plant's pours listed", "Pours this week" in vals)

# --------------------------------------------------------------------------- 8. the zip
ZB = so.build_zip(D)
z = zipfile.ZipFile(io.BytesIO(ZB))
names = sorted(z.namelist())
ok("8: a PDF and an XLSX for each of the four suppliers", len(names) == 8
   and "supplier-order-2026-11-23-northfield-quarry.pdf" in names
   and "supplier-order-2026-11-23-wolds-link-batching-plant.xlsx" in names, str(names))
ok("8: the zip's name", so.zip_name(D) == "supplier-orders-2026-11-23.zip")
ok("8 (Q10): no route sheet inside", not any("route-sheet" in n for n in names))

# --------------------------------------------------------------------------- 9. a weekend day with a quantity (Q8)
wk = copy.deepcopy(PG)
for l in wk["commit"]["lines"]:
    if l.get("route_id") == "R011":
        for d in l["days"]:
            if d["day_date"] == "2026-11-28":
                d["planned_qty"] = 100.0
                d.setdefault("derived", {})["trips"] = 4
DW = so.orders(wk, acc=PLANNER)
NW = so.find(DW, "L002")
ok("9 (Q8): a Saturday with a quantity gets its column", "2026-11-28" in NW["days"] and "2026-11-29" not in NW["days"],
   str(NW["days"]))
ok("9 (Q8): ...counted in the week", NW["units"]["t"]["week"] == 3375, str(NW["units"]["t"]["week"]))
ok("9 (Q8): ...on the PDF too", b"%PDF" in so.build_pdf(DW, NW)[:8])
ok("9 (Q8): ...and the other suppliers still Mon–Fri", len(so.find(DW, "L003")["days"]) == 5)

# --------------------------------------------------------------------------- 10. the endpoints (stubbed FastAPI)
SUM = main.forecast_week_supplier_orders(bucket="commit")
ok("10: the list reads the kept Look-ahead and names each supplier with its totals",
   [s["location_id"] for s in SUM["suppliers"]] == [s["location_id"] for s in D["suppliers"]]
   and SUM["suppliers"][0]["totals"] == [{"unit": "t", "qty": 3275.0}], str(SUM["suppliers"][:1]))
ok("10: the list carries no rows (a headline each) and says Wayscope sends nothing",
   "rows" not in SUM["suppliers"][0] and SUM["sends_nothing"] == so.SENDS_NOTHING)
ok("10: ...the m³ unit is written as a person reads it", SUM["suppliers"][1]["totals"][0]["unit"] == "m³")
r = main.forecast_week_supplier_order_file(format="pdf", location_id="L002", bucket="commit")
ok("10: the PDF download", r.media_type == "application/pdf" and r.body[:5] == b"%PDF-"
   and 'filename="supplier-order-2026-11-23-northfield-quarry.pdf"' in r.headers["Content-Disposition"], str(r.headers))
ok("10: ...made fresh each time (no-store)", r.headers.get("Cache-Control") == "no-store")
r = main.forecast_week_supplier_order_file(format="xlsx", location_id="L014", bucket="commit")
ok("10: the XLSX download", r.media_type.endswith("spreadsheetml.sheet") and r.body[:2] == b"PK")
r = main.forecast_week_supplier_order_file(format="zip", location_id=None, bucket="commit")
ok("10: the zip download", r.media_type == "application/zip" and "supplier-orders-2026-11-23.zip" in r.headers["Content-Disposition"])
for fmt, lid, code, why in (("doc", "L002", 400, "an unknown format"), ("pdf", None, 400, "no supplier"),
                            ("pdf", "L001", 404, "a place with no confirmed lines"),
                            ("pdf", "L999", 404, "no such place")):
    try:
        main.forecast_week_supplier_order_file(format=fmt, location_id=lid, bucket="commit")
        ok(f"10: refused: {why}", False)
    except Exception as e:      # the stub's HTTPException
        ok(f"10: refused: {why} ({code})", getattr(e, "status_code", None) == code, str(e))
access.set_current(None)
try:
    main.forecast_week_supplier_orders(bucket="commit")
    ok("10: signed out is refused", False)
except Exception as e:
    ok("10: signed out is refused (401)", getattr(e, "status_code", None) == 401, str(e))
access.set_current("planner123")

# --------------------------------------------------------------------------- 11. the source
MAIN = read("backend/main.py")
ok("11: two routes, the list and the download", '@app.get("/api/forecast-weeks/supplier-orders")' in MAIN
   and '@app.get("/api/forecast-weeks/supplier-orders/download")' in MAIN)
ok("11: built from the Look-ahead's own kept read, any staff, scoped like the page",
   'pg = _staff_json("lookahead", {"bucket": b, "route_id": None, "on": True},' in MAIN
   and "def _supplier_orders_data(bucket):\n" in MAIN and "    acc = _require_access()\n    b = \"next\" if bucket" in MAIN)
SO = read("backend/supplier_orders.py")
ok("11: Wayscope sends nothing: no mail or HTTP in the module",
   not re.search(r"smtplib|send_mail|urllib|requests\.|mailer", SO))
APP = read("frontend/index.html")
ok("11: the Supplier orders menu on the commit week, greyed out until a line is confirmed",
   "<SupplierOrdersMenu bucket={bucket} disabled={!anyConfirmed} />" in APP and "function SupplierOrdersMenu({ bucket, disabled })" in APP)
ok("11: it reads the list when it opens and downloads by format",
   "`${API}/forecast-weeks/supplier-orders?bucket=${bucket}`" in APP
   and "`${API}/forecast-weeks/supplier-orders/download?${q}`" in APP)
ok("11: the screen says Wayscope sends nothing", "Wayscope sends nothing: download and send them yourself." in APP)
ok("11: a failure says what did not happen, in words", 'errSay("The order was not made.", e)' in APP
   and 'errSay("The suppliers could not be read.", e)' in APP)
ok("11: the zip only with more than one supplier", "{sups.length > 1 && <button type=\"button\" className=\"so-all\"" in APP)
GUIDE = read("frontend/help/index.html")
ok("11: the user guide explains supplier orders", "Supplier orders" in GUIDE and "sends nothing" in GUIDE)
TECH = read("frontend/help/technical/index.html")
ok("11: the technical guide has the reference", 'id="t1-supplier-orders"' in TECH and "/api/forecast-weeks/supplier-orders" in TECH)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)

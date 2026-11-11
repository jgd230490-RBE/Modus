"""
CLOCS cards C-F1 and C-F2 (11 Nov 2026, John's yes to the "Everything left" page): one wording for a road limit, and
the Day sheet's lorry name and confirmation word.

C-F1  limits.breach_text — the ONE sentence the Look-ahead's ROAD LIMIT flag, the Day sheet, the Route sheet and the
      Dashboard / Forecasts rows print — says it in the public map's words (PR #253): no supplier in brackets, the
      sign's exception after a comma, or "no exception recorded: check the sign". The supplier's credit moves to the
      sheets' foot (limits.credit_for).
C-F2  The Day sheet names the lorry as the other sheets do ("Artic Tipper (44t)", not the chips' "Tipper (44t)"), and
      its corner says how much of the day is confirmed ("18 of 22 lines confirmed") instead of DRAFT for a day that is
      mostly confirmed.

WHAT THIS DOES NOT PROVE
------------------------
  * No database: the tenant's name, the team names, the vehicle names and the stored limit checks are stubbed here.
    test_limits.py / test_lookahead.py / test_route_sheet.py run the same functions over a scratch database.
  * How the Day sheet's flag box and the Route sheet's foot WRAP on paper is not measured; only that the words are
    in the file (pdftotext). Checked by eye in the PDF.
  * Nothing in a browser.

Run:  python backend/tests/test_clocs_c_words.py
"""
import datetime
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(tempfile.mkdtemp(prefix="clocs_c_words_"), "never_opened.db")   # nothing here reads it

import conversions  # noqa: E402
import limits  # noqa: E402
import export  # noqa: E402
from portable import pdf_text, offline  # noqa: E402

offline(export)

PASS = FAIL = 0


def ok(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f"\n       {str(detail)[:400]}" if detail else ""))


ART = "Artic Tipper (44t)"
FACTORS = {"vehicles": {ART: {"payload_t": 29, "labels": {"en": ART}}}}
conversions.load_factors = lambda: FACTORS
SUPPLIERS = re.compile(r"OpenStreetMap|\bOSM\b|\bHERE\b")


def hit(**k):
    h = {"source": "osm", "kind": "weight", "verdict": "exceeds", "vehicle_profile": ART, "vehicle_value": 44, "unit": "t",
         "leg": "loaded", "headline": "Weight limit 7.5 t · Glenhills Boulevard", "exceptions": "Except for access",
         "point": False}
    h.update(k)
    return h


print("C-F1 — one wording for a road limit")
t1 = limits.breach_text([hit(), hit(headline="Weight limit 7.5 t · Uppingham Road")], ART)
ok("⭐ the Look-ahead's example in the card's words: '<lorry>, 44 t loaded, is over the <limit · road>, except for access (+1 more)'",
   t1 == "Artic Tipper (44t), 44 t loaded, is over the Weight limit 7.5 t · Glenhills Boulevard, except for access (+1 more)", t1)
t2 = limits.breach_text([hit(leg="return", vehicle_value=15, exceptions=None, headline="Weight limit 7.5 t")], ART)
ok("⭐ no exception recorded: the map's ending, 'no exception recorded: check the sign'; the empty leg said in words",
   t2 == "Artic Tipper (44t), 15 t going back empty, is over the Weight limit 7.5 t · no exception recorded: check the sign", t2)
t3 = limits.breach_text([hit(source="here", point=True, exceptions="")], ART)
ok("a point limit keeps its warning, after the same '·'; an empty exception counts as none",
   t3.endswith("· no exception recorded: check the sign · a point limit: check whether the route passes it or crosses over or under it"), t3)
ok("⭐ no sentence names a supplier (OpenStreetMap, HERE): neither in brackets nor anywhere",
   not any(SUPPLIERS.search(x) for x in (t1, t2, t3)) and "(" + "OpenStreetMap" + ")" not in t1, [t1, t2, t3])
ok("the old forms are gone: no '(44 t, loaded)', no ' — except', no '(<source>)' after the headline",
   all("(44 t, loaded)" not in x and " — except" not in x and "(15 t, going back empty)" not in x for x in (t1, t2, t3)))
ok("NO_EXCEPTION is the public map's own words (map/index.html's Conditions row)",
   limits.NO_EXCEPTION == "no exception recorded: check the sign"
   and "no exception recorded: check the sign" in open(os.path.join(os.path.dirname(BACKEND), "map", "index.html"), encoding="utf-8").read())
_src = open(os.path.join(BACKEND, "limits.py"), encoding="utf-8").read()
_bt = _src[_src.index("def breach_text("):_src.index("def credit_for(")]
ok("source: breach_text no longer reads SOURCES' short name (the supplier's name cannot come back into the sentence)",
   "SOURCES" not in _bt.split('"""', 2)[2] and "'short'" not in _bt)

_stored = {"R001": {"hits": [hit(), hit(source="here")]}, "R002": {"hits": [hit()]}, "R003": {"hits": []}}
_calls = []


def _fake_checks(route_ids=None):
    _calls.append(route_ids)
    want = set(route_ids) if route_ids else None
    return {k: v for k, v in _stored.items() if want is None or k in want}


limits.stored_checks = _fake_checks
ok("⭐ credit_for: each source of the routes' stored limits, once, as its credit ('Road limits © … .')",
   limits.credit_for(["R002"]) == "Road limits © OpenStreetMap contributors (ODbL)."
   and limits.credit_for(["R001", "R002"]) == "Road limits © HERE; © OpenStreetMap contributors (ODbL).",
   [limits.credit_for(["R002"]), limits.credit_for(["R001", "R002"])])
_calls.clear()
ok("credit_for: no route or a route with no stored limit gives None, and no route never reads EVERY route",
   limits.credit_for([]) is None and limits.credit_for([None]) is None and limits.credit_for(["R003"]) is None
   and limits.credit_for(None) is None and None not in _calls and [] not in _calls, _calls)

_es = open(os.path.join(BACKEND, "export.py"), encoding="utf-8").read()
_rs_foot = _es[_es.index("    foot = [f\"From the scheme's routes as stored"):_es.index("    fy = m + footer_h - 8")]
ok("Route sheet: page 1's foot carries the limits' credit when the sheet prints limit lines (source)",
   "_limits.credit_for([S.get(\"route_id\")])" in _rs_foot and "if S.get(\"limits_lines\")" in _rs_foot)

print("C-F2 — the Day sheet: the lorry's name and how much is confirmed")
export._team_namer = lambda: (lambda ipt: {"IPT1": "South Team"}.get(ipt, ipt))   # other text passes through
export._tenant_name = lambda: "Wolds Link"
export._demo_notice = lambda: None
DAY = "2026-11-13"


def line(rid, status, codes=()):
    return {"route_id": rid, "month_index": 10, "discipline": "", "section_id": "", "unit": "t",
            "week": {"status": status},
            "context": {"origin_name": "Kilby Ridge Quarry", "dest_name": "Harborough Compound", "ipt": "IPT1",
                        "material_type": "Large aggregate / ballast", "vehicle_type": ART, "vehicle_short": "Tipper (44t)",
                        "baked": True},
            "days": [{"day_date": DAY, "planned_qty": 100, "derived": {"tonnes": 100, "trips": 4, "vehicles": 1}}]}


def page(statuses, limit_on=()):
    ls = [line(f"R{i + 1:03d}", s) for i, s in enumerate(statuses)]
    flags = [{"route_id": r, "month_index": 10, "discipline": "", "section_id": "", "code": "LIMIT",
              "text": "Kilby Ridge Quarry → Harborough Compound: " + limits.breach_text([hit()], ART)} for r in limit_on]
    return {"commit": {"lines": ls}, "clashes": {"flags": flags}, "today": DAY, "pours": []}


rows = export.day_sheet_rows(page(["confirmed"]), DAY)
ok("⭐ the Day sheet's vehicle is the lorry's NAME, 'Artic Tipper (44t)', not the chips' 'Tipper (44t)'",
   rows and rows[0]["vehicle"] == ART, rows[0]["vehicle"] if rows else rows)
ok("a line with no vehicle key keeps the short form, else '—'",
   export.day_sheet_rows({"commit": {"lines": [dict(line("R009", "confirmed"), context={"vehicle_short": "Mixer", "baked": True})]},
                          "clashes": {}}, DAY)[0]["vehicle"] == "Mixer")

part = export.day_sheet_totals(export.day_sheet_rows(page(["confirmed"] * 18 + ["draft"] * 4), DAY))
allc = export.day_sheet_totals(export.day_sheet_rows(page(["confirmed"] * 3), DAY))
none = export.day_sheet_totals(export.day_sheet_rows(page(["draft"] * 3), DAY))
one_left = export.day_sheet_totals(export.day_sheet_rows(page(["confirmed", "draft"]), DAY))
ok("⭐ the corner: '18 of 22 lines confirmed' (amber) for a part-confirmed day",
   export.day_sheet_stamp(part) == ("18 of 22 lines confirmed", export.WARN_TEXT_RGB) and part["n_confirmed"] == 18,
   export.day_sheet_stamp(part))
ok("the corner: 'CONFIRMED' (navy) when every line is, 'DRAFT - not confirmed' (red) when none is",
   export.day_sheet_stamp(allc) == ("CONFIRMED", export.NAVY_RGB)
   and export.day_sheet_stamp(none) == ("DRAFT - not confirmed", export.RED_RGB))
ok("the closing words: '4 lines are not confirmed yet: they can still change.'; one line in the singular; the old two kept",
   export.day_sheet_not_confirmed_words(part) == "4 lines are not confirmed yet: they can still change. "
   and export.day_sheet_not_confirmed_words(one_left) == "1 line is not confirmed yet: it can still change. "
   and export.day_sheet_not_confirmed_words(allc) == "This week is confirmed. "
   and export.day_sheet_not_confirmed_words(none) == "This week is not confirmed yet: the plan can still change. ")

pb = export.build_day_sheet_pdf(page(["confirmed"] * 18 + ["draft"] * 4, limit_on=["R001"]), DAY)
tx = " ".join(pdf_text(pb).split())
ok("⭐ DAY SHEET PDF: the corner, the lorry's name, the closing words and the limits' credit are in the file",
   pb[:5] == b"%PDF-" and "18 of 22 lines confirmed" in tx and "DRAFT" not in tx and "Artic Tipper (44t)" in tx
   and "4 lines are not confirmed yet" in tx and "Road limits © HERE; © OpenStreetMap contributors (ODbL)." in tx, tx[-700:])
ok("DAY SHEET PDF: the red limit line reads the new wording and names no supplier in brackets",
   "is over the Weight limit 7.5 t · Glenhills Boulevard, except for access" in tx and "(OpenStreetMap)" not in tx, tx[-900:])
tx0 = " ".join(pdf_text(export.build_day_sheet_pdf(page(["draft"] * 2), DAY)).split())
ok("DAY SHEET PDF: no limit flag on the day → no limits credit; an all-draft day keeps 'DRAFT - not confirmed'",
   "Road limits" not in tx0 and "DRAFT - not confirmed" in tx0, tx0[:300])

print("C-F2 — the week's PDF, its XLSX and the supplier orders name the lorry the same way (the mother session, 11 Nov)")
ok("⭐ export._vehicle_name: the lorry's NAME for a key ('Artic Tipper (44t)'); a line with no key keeps its short form",
   export._vehicle_name({"vehicle_type": ART, "vehicle_short": "Tipper (44t)"}) == ART
   and export._vehicle_name({"vehicle_short": "Mixer"}) == "Mixer" and export._vehicle_name({}) == "")
try:
    _xr = export._line_rows(page(["confirmed"]))
    _xv = _xr[0]["vehicle"] if _xr else None
except Exception as _e:   # the rows read the tenant's distance unit; a stub that cannot is reported, not hidden
    _xv = repr(_e)
ok("⭐ XLSX (the week's rows): the vehicle column reads 'Artic Tipper (44t)', not 'Tipper (44t)'", _xv == ART, str(_xv))
_ex = open(os.path.join(BACKEND, "export.py"), encoding="utf-8").read()
_so = open(os.path.join(BACKEND, "supplier_orders.py"), encoding="utf-8").read()
_old = re.compile(r"""c\.get\(["']vehicle_short["']\) or conversions\.vehicle_word_rule""")
ok("⭐ source: no sheet in export.py or supplier_orders.py prints the chips' short name first any more",
   not _old.search(_ex) and not _old.search(_so), str(_old.findall(_ex + _so)))
_wk = _ex[_ex.index("def build_pdf(page):"):_ex.index("def _line_key(")]
ok("the week's PDF: its vehicle cell goes through _vehicle_name (the not-baked note kept)",
   "P(f\"{E(_vehicle_name(c) or '—')}\"" in _wk and "not baked" in _wk)
import lookahead  # noqa: E402
_wg, _rg, _dm = lookahead.week_geometry, export.route_geometries, export.draw_route_map
lookahead.week_geometry = lambda *a, **k: []          # the stub page has no database: no route ends, no map
export.route_geometries = lambda *a, **k: []
export.draw_route_map = lambda *a, **k: None
try:
    _wp = export.build_pdf(dict(page(["confirmed"]), commit_week={"from": "2026-11-09", "to": "2026-11-15"}))
    _wt = " ".join(pdf_text(_wp, raw=True).split())
except Exception as _e:
    _wt = "BUILD FAILED " + repr(_e)
lookahead.week_geometry, export.route_geometries, export.draw_route_map = _wg, _rg, _dm
ok("⭐ the week's PDF, built: the vehicle cell reads 'Artic Tipper (44t)' (the short 'Tipper (44t)' never on its own)",
   ART in _wt and not re.search(r"(?<!Artic )Tipper \(44t\)", _wt), _wt[:600])
ok("supplier orders: the vehicle is conversions.vehicle_label of the line's key",
   'conversions.vehicle_label(factors, c.get("vehicle_type")) if c.get("vehicle_type") else c.get("vehicle_short")' in _so)

print(f"\ntest_clocs_c_words.py: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)

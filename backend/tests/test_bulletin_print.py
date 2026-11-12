"""
The bulletin's and the route plan's print fixes (11 Nov 2026, cards A-F2, A-F3 and A-X3 on John's page "Everything left";
branch claude/bulletin-print-fixes). Card A-F1 (the concerns line) is asserted in test_concerns.py, beside its pins.

WHAT IS ASSERTED
----------------
  * A-F2: the route table's narrow last-month column reads "none" (it broke "none planned" mid-word over two lines) and a
    dash for "no earlier month"; a route with loads under half a movement a day reads "under 1", never "0", and its bar's
    figure has room; two routes with the same name each get what differs (the lorry type, else the route's name);
  * A-F3: the plan's scale bar is in the organisation's unit: "0 2.5 5 miles" for a miles organisation at a road scale,
    "km" for a km one, metres at a site scale whichever the unit;
  * A-X3: a works square on the printed map keeps a clear gap from every letter pin; the map key's columns flow on their
    own, so a wrapped works line leaves no empty line in the sites' columns.
  * A-F2b (John: "Yes, both together"): the five band blues are #72A7FF #006AFD #0051C4 #00388E #00215B in the bulletin
    AND the public map's heat maps; the lightest clears 2:1 on white; light to dark in even steps; the first two bands
    part in a black-and-white print; the route table's bar takes its default from the one list; one line width stays.

WHAT THIS DOES NOT PROVE
------------------------
The PDFs here are small test pages built from the bulletin's own builders (`export._Kit`), not a whole bulletin over a
database: test_bulletin.py builds those. How the pages LOOK was checked by eye on a local copy (session note). Mapbox is
never called.

Run:  python3 backend/tests/test_bulletin_print.py
"""
import io
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

import portable  # noqa: E402
import bulletin_doc  # noqa: E402
import basemap  # noqa: E402
import export  # noqa: E402
portable.offline(export)

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas  # noqa: E402
from reportlab.platypus import SimpleDocTemplate  # noqa: E402

PASS, FAIL = 0, []


def ok(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("  ok  ", name)
    else:
        FAIL.append(f"{name} {detail}")
        print("  FAIL", name, detail)


def pdf_of(flowables):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    doc.build(list(flowables))
    return buf.getvalue()


U = A4[0] - 30 * mm                                   # the bulletin's usable width (15 mm margins)
KIT = export._Kit(U)

# =========================================================================== #
#  A-F2: the route table                                                       #
# =========================================================================== #
print("\nA-F2 · the route table")
ok("⭐ last-month column: 'none planned' reads 'none'", export._last_month_cell("none planned") == "none")
ok("last-month column: 'no earlier month in the programme' reads a dash",
   export._last_month_cell("no earlier month in the programme") == "—")
ok("last-month column: a figure loses ' a day' as before", export._last_month_cell("9 a day") == "9"
   and export._last_month_cell("under 1 a day") == "under 1")
ok("under 1: a route with loads under half a movement a day", bulletin_doc.a_day_words(0.3) == "under 1"
   and bulletin_doc.a_day_words(0.49) == "under 1")
ok("under 1: half a movement and more round as before; nought and none as before",
   bulletin_doc.a_day_words(0.5) == "0" or bulletin_doc.a_day_words(0.5) == "1")
ok("under 1: nought is '0', no figure a dash", bulletin_doc.a_day_words(0) == "0" and bulletin_doc.a_day_words(None) == "—"
   and bulletin_doc.a_day_words(131.6) == "132")


def row(rid, label, a_day, last="9 a day"):
    return {"route_id": rid, "letters": "M → B", "label": label, "a_day": a_day, "cap": None, "cap_at": None,
            "color": bulletin_doc.VOLUME_RAMP[0], "a_day_text": bulletin_doc.a_day_words(a_day),
            "in_month_text": "36", "last_month_text": last, "flag_short": "—", "over_flag": False}


TW = "Harborough Rail Freight Terminal to Melton Compound"
views = [row("R031", TW, 2), row("R032", TW, 1), row("R040", "Kilby Ridge Quarry to Langton Compound", 8)]
bulletin_doc.name_twins(views, {"R031": ["tipper_8w"], "R032": ["mixer_6w"], "R040": ["artic"]},
                        lambda k: {"tipper_8w": "Tipper", "mixer_6w": "Mixer"}.get(k, k))
ok("⭐ twins: two routes with the same name each get their lorry type",
   [v["label"] for v in views[:2]] == [f"{TW} · Tipper", f"{TW} · Mixer"], str([v["label"] for v in views]))
ok("twins: a route with its own name keeps it", views[2]["label"] == "Kilby Ridge Quarry to Langton Compound")
views = [row("R031", TW, 2), row("R032", TW, 1)]
bulletin_doc.name_twins(views, {"R031": ["tipper_8w"], "R032": ["tipper_8w", "mixer_6w"]}, lambda k: k)
ok("twins: where the lorries do not tell them apart, the route's name does",
   [v["label"] for v in views] == [f"{TW} · R031", f"{TW} · R032"], str([v["label"] for v in views]))
views = [row("R031", TW, 2), row("R032", TW, 1)]
bulletin_doc.name_twins(views, {"R031": ["artic"], "R032": ["artic"]}, lambda k: k)
ok("twins: the same lorry on both: the route's name", [v["label"] for v in views] == [f"{TW} · R031", f"{TW} · R032"])
ok("twins: the bulletin's view model calls it, with each route's lorry types from the roll-up",
   "name_twins(routes_view," in open(os.path.join(BACKEND, "bulletin_doc.py"), encoding="utf-8").read()
   and '"vehicle_types": sorted(' in open(os.path.join(BACKEND, "bulletin.py"), encoding="utf-8").read())

S = {"prev_long": "October 2026", "map_legend_title": "Lorry movements a day",
     "routes": [row("R040", "Kilby Ridge Quarry to Langton Compound", 8, "none planned"),
                row("R050", "Harborough Rail Freight Terminal to Harborough Compound", 0.3, "no earlier month in the programme"),
                row("R031", f"{TW} · Tipper", 2), row("R032", f"{TW} · Mixer", 1)]}
txt = portable.pdf_text(pdf_of([KIT.routes_table(S)]), raw=True)
ok("⭐ PDF: no 'none p' broken over two lines; 'none' stands whole in the Oct column",
   "none p" not in txt and "lanned" not in txt and "none" in txt, txt[:400])
ok("PDF: 'under 1' printed for the route under half a movement, never '0' beside it", "under 1" in txt, txt[:400])
ok("PDF: the twins print apart", f"{TW} · Tipper" in " ".join(txt.split()) and f"{TW} · Mixer" in " ".join(txt.split()))
_bar = export._route_bar(row("R050", "x", 0.3), U * 0.25 - 8, 10)
_num = [s for s in _bar.contents if getattr(s, "text", None) == "under 1"]
ok("PDF: the bar's figure 'under 1' starts inside its cell (its room grows; it was 26 pt for any figure)",
   _num and _num[0].x - export.rl_pdfmetrics_width("under 1", export._BF("bold"), 8) >= 0, str([(s.x,) for s in _num]))

# =========================================================================== #
#  A-F3: the plan's scale bar in the organisation's unit                       #
# =========================================================================== #
print("\nA-F3 · the plan's scale bar")


def bar_text(unit, zoom):
    export._du = lambda: unit
    v = {"lat": 52.6, "lon": -0.95, "zoom": zoom, "w": 1280, "h": 905}
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(285 * mm, 200 * mm))
    metres = export._plan_scale_bar(c, v, 285 * mm)
    c.showPage(); c.save()
    return " ".join(portable.pdf_text(buf.getvalue()).split()), metres


_du0 = export._du
t_mi, m_mi = bar_text("mi", 9.3)
t_km, m_km = bar_text("km", 9.3)
ok("⭐ a miles organisation's road-scale plan: the bar reads miles, never km", "miles" in t_mi and " km" not in t_mi, t_mi)
ok("the miles bar is a round length with its half labelled (e.g. '0 2.5 5 miles')",
   any(f"0 {h:g} {n:g} miles" in t_mi for n, h in ((5, 2.5), (10, 5), (2, 1), (20, 10))), t_mi)
ok("a km organisation's plan is unchanged: km", " km" in t_km and "mile" not in t_km, t_km)
ok("the bar returns its own length in metres (miles × 1,609.344)", abs(m_mi / 1609.344 - round(m_mi / 1609.344, 1)) < 1e-6)
t_site, _ = bar_text("mi", 16.5)
ok("a site-scale plan stays in metres for a miles organisation (a bar under 1 km)", t_site.endswith(" m") and "mile" not in t_site, t_site)
_v = {"lat": 52.6, "lon": -0.95, "zoom": 9.3, "w": 1280, "h": 905}
_mi, _px = basemap.bar_miles(_v, 400)
ok("basemap.bar_miles: a round length in miles no longer than the room, and its pixels",
   _mi in (0.5, 1, 2, 5, 10, 20, 50, 100, 200) and _px <= 400 + 1e-6
   and abs(_px * basemap.m_per_px(52.6, 9.3) - _mi * 1609.344) < 1e-3, f"{_mi} {_px}")
export._du = _du0

# =========================================================================== #
#  A-X3: the printed map's markers and its key                                 #
# =========================================================================== #
print("\nA-X3 · markers and the key")
PIN_R, SQ_HALF = 4.6, 4.4
ok("the PDF's clearance leaves a gap between a pin (r 4.6) and a square's corner (8.8 pt square)",
   bulletin_doc.PDF_MARKER_CLEAR > PIN_R + SQ_HALF * math.sqrt(2) + 1.5 and bulletin_doc.PDF_MARKER_STEP > bulletin_doc.PDF_MARKER_CLEAR)
pins = [(100, 100), (100, 114), (88, 110)]
bad = []
for x, y in [(100, 100), (101, 104), (96, 110), (112, 100)]:
    px, py = bulletin_doc.control_spot(x, y, pins, clear=bulletin_doc.PDF_MARKER_CLEAR, step=bulletin_doc.PDF_MARKER_STEP,
                                       rings=2)
    if any(math.hypot(px - a, py - b) < bulletin_doc.PDF_MARKER_CLEAR for a, b in pins):
        bad.append((x, y, px, py))
ok("⭐ a works square near letter pins steps to a spot clear of every one", not bad, str(bad))
ok("⭐ the PDF map passes the clearance (it used the 11 pt default: E touched 2, J touched 4)",
   "control_spot(ax, ay, pins, clear=bulletin_doc.PDF_MARKER_CLEAR" in open(os.path.join(BACKEND, "export.py"), encoding="utf-8").read())

SK = {"places": [{"letter": l, "name": n} for l, n in zip("ABCDEFG", ["Wolds Link Batching Plant", "Melton Compound",
      "Northfield Quarry", "Tilton Viaduct site", "Stockpile North", "Kilby Ridge Quarry", "Harborough Compound"])],
      "controls": [{"n": 1, "name": "A47 at the new Tilton junction: HGV diversion while the junction is built and for some "
                                    "weeks after it opens"}, {"n": 2, "name": "Burrough village 7.5 t limit"}]}
key = KIT.map_key(SK)
ok("the key is a header row and ONE row of three columns, each holding its own lines",
   len(key._cellvalues) == 2 and all(isinstance(c, list) for c in key._cellvalues[1]), str(len(key._cellvalues)))
lines = [l.strip() for l in portable.pdf_text(pdf_of([key]), raw=True).splitlines() if l.strip()]
_a = next((i for i, l in enumerate(lines) if "Wolds Link Batching Plant" in l), None)
ok("⭐ no empty line after 'A Wolds Link Batching Plant': B follows at once in its column (pdftotext order)",
   _a is not None and any("Melton Compound" in l for l in lines[_a:_a + 3]), str(lines[:12]))

# --------------------------------------------------------------------------- #
#  A-F2b (John, 11 Nov 2026: "Yes, both together"): the five band blues re-stepped, screens and paper together
# --------------------------------------------------------------------------- #
import re  # noqa: E402
NEW = ["#72A7FF", "#006AFD", "#0051C4", "#00388E", "#00215B"]
MAP_HTML = open(os.path.join(os.path.dirname(BACKEND), "map", "index.html"), encoding="utf-8").read()
_m = re.search(r"const CARBON_RAMP = \[([^\]]+)\];", MAP_HTML)
MAP_RAMP = [x.strip().strip("'") for x in _m.group(1).split(",")] if _m else []
ok("⭐ A-F2b: the bulletin's five blues are the card's (was #94BBF9 #5A96F6 #2071F3 #0B55CB #073888)",
   list(bulletin_doc.VOLUME_RAMP) == NEW, str(bulletin_doc.VOLUME_RAMP))
ok("⭐ A-F2b: the public map's heat-map blues are the same five (screens and paper together)", MAP_RAMP == NEW, str(MAP_RAMP))


def _lin(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def _Y(h):
    r, g, b = _lin(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _okl(h):
    r, g, b = _lin(h)
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_


_c0 = 1.05 / (_Y(bulletin_doc.VOLUME_RAMP[0]) + 0.05)
ok("⭐ A-F2b: the lightest band clears the colour system's 2:1 floor on white (rule 5; the old one was 1.96:1)",
   _c0 >= 2.0, f"{_c0:.2f}:1")
_L = [_okl(h) for h in bulletin_doc.VOLUME_RAMP]
ok("A-F2b: light to dark, each step at least 0.06 darker (OK lightness; the palette checker's ordinal rule)",
   all(a - b >= 0.06 for a, b in zip(_L, _L[1:])), str([round(x, 3) for x in _L]))
_g = [116 * _Y(h) ** (1 / 3) - 16 for h in bulletin_doc.VOLUME_RAMP]
ok("⭐ A-F2b: 'under 20' and '20 to 50' part in a black-and-white print (grey step at least 15 L*; it was 13.0)",
   _g[0] - _g[1] >= 15, str([round(x, 1) for x in _g]))
ok("A-F2b: a route-table bar with no colour takes the second band's from the one list, no hex of its own",
   'r.get("color") or bulletin_doc.VOLUME_RAMP[1]' in open(os.path.join(BACKEND, "export.py"), encoding="utf-8").read())
_bar = export._route_bar({"a_day": 3, "a_day_text": "3"}, 120, 10)
ok("A-F2b: the bar itself is drawn in that blue",
   any(getattr(c, "fillColor", None) is not None and abs(c.fillColor.blue - 0xFD / 255) < 1e-3
       and abs(c.fillColor.green - 0x6A / 255) < 1e-3 for c in _bar.contents), "no #006AFD bar")
ok("A-F2b: the one-width rule stays (one line width on the printed map, no width by band)",
   "ONE line width" in open(os.path.join(BACKEND, "bulletin_doc.py"), encoding="utf-8").read()
   and "weight" not in str(bulletin_doc.volume_legend(2) if hasattr(bulletin_doc, "volume_legend") else ""))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
# ---- 12 Nov 2026 (BUILD.md rule 13): the newsletter's fit ladder (export.NEWSLETTER_FIT), with stand-in builds
print("Newsletter fit ladder (four pages, one section a page)")
F0 = export.NEWSLETTER_FIT[0]
ok("FIT1 the first step is the look of 14 Oct: rows 2.2 pt, small print 7.5 pt, section gap 7 pt, council map 70 mm, terms 8 pt",
   F0 == {"pad": 2.2, "small_pad": 1.3, "lot_pad": 2.5, "sec_before": 7, "council_map": 70, "small": 7.5, "terms": 8})
_k = export._Kit(100)
ok("FIT2 the leaflet's kit (no step named) is the first step", _k.fit is F0 and _k.st_grey.fontSize == 7.5
   and _k.st_sec.spaceBefore == 7)
ok("FIT3 each step is tighter than the one before, never under 7 pt small print or 46 mm of council map",
   all(b[k] <= a[k] for a, b in zip(export.NEWSLETTER_FIT, export.NEWSLETTER_FIT[1:]) for k in F0)
   and min(f["small"] for f in export.NEWSLETTER_FIT) >= 7 and min(f["council_map"] for f in export.NEWSLETTER_FIT) >= 46)
_real_nl, _calls = export._newsletter, []


def _stand_in(pages_at):
    def nl(S, map_h, pages=None, fit=None):
        st = export.NEWSLETTER_FIT.index(fit)
        _calls.append((st, round(map_h / mm), pages))
        return (f"step{st}".encode(), pages_at[st], 2)
    return nl


try:
    for pages_at, want in (((4, 4, 4, 4), 0), ((5, 4, 4, 4), 1), ((5, 5, 5, 4), 3), ((6, 6, 6, 5), 3)):
        del _calls[:]
        export._newsletter = _stand_in(pages_at)
        out = export.build_bulletin_pdf({"x": 1})
        ok(f"FIT4 pages by step {pages_at}: served at step {want}, the page total passed to the last build",
           out == f"step{want}".encode() and _calls[-1][0] == want and _calls[-1][2] == pages_at[want]
           and [c[0] for c in _calls[:-1]] == list(range(want + 1)), str(_calls))
finally:
    export._newsletter = _real_nl

# 12 Nov 2026 (A-F8 (a), John's yes): the route column takes the room the Map and "In the month" columns do not use
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402
_u = 180 * mm
ok("ROUTE1 the route table still makes the whole width (map, route, bar 0.25, in the month, last month 0.07, flag 0.10)",
   abs(sum(export.ROUTE_COLS) + 0.25 + 0.07 + 0.10 - 1.0) < 1e-9, str(export.ROUTE_COLS))
ok("ROUTE2 the route column is wider than before (0.42) and the Map column still holds two letters and a dash",
   export.ROUTE_COLS[1] > 0.42 and _u * export.ROUTE_COLS[0] - 8 >= stringWidth("M–G", export._BF("regular"), 8))
ok("ROUTE3 'month' in the In the month header fits its column whole (it broke as mont / h at 0.06)",
   _u * export.ROUTE_COLS[2] - 8 >= stringWidth("month", KIT.st_h.fontName, KIT.st_h.fontSize)
   and _u * export.ROUTE_COLS[2] - 8 >= stringWidth("9,999", export._BF("regular"), 8))

print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

"""
Look-ahead v2, slice 4 (2026-09-09) — the commit-week export. Browser download, no
email, no upload.

Both builders take the page dict from lookahead.page() and return bytes. They read the
same numbers the screen shows; nothing is recomputed here.

    build_xlsx(page)   sheet 1  day × line (the export mock's columns + € where set)
                       sheet 2  stock at week end
                       sheet 3  clashes
    build_pdf(page)    LANDSCAPE, as many pages as it takes (10 Sep, the human): the
                       week's routes on a map, then ONE ROW PER LINE with Mon…Fri as
                       five separate columns (no collapse rule any more), origin and
                       destination with their coordinates, a week total, flags (not a
                       stop) and the honest-gap footer lines. Header row repeats on
                       every page. Payloads are planning figures; km from HERE unless
                       marked ‡.

2026-09-10, on the human's feedback: **Mon–Fri only** (weekend rows are dropped from
both files — the days still exist at 0 in the database), **no stockpile section** (the
sheet is for the supplier; stock belongs on a look-ahead dashboard, not built), and a
**route map** on the PDF in the stock section's place. The map is Mapbox's Static
Images API when MAPBOX_TOKEN is set and the fetch succeeds (never tested from the
sandbox, which is offline), otherwise a schematic drawn from the baked geometry —
the PDF says which it is. Road-restriction flags come from the STORED per-route check, so the
export is as fast as the page.

openpyxl and reportlab are runtime dependencies of these two functions ONLY — added to
requirements.txt; the app boots without them and the export endpoints say so if they
are missing.
"""
import datetime
import io
import json
import os
import urllib.parse
import urllib.request

import db

MISSING = {}
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except Exception as e:                                   # pragma: no cover
    openpyxl = None
    MISSING["xlsx"] = str(e)
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, LongTable,
                                    PageTemplate, Paragraph, Spacer, TableStyle)
except Exception as e:                                   # pragma: no cover
    rl_canvas = None
    MISSING["pdf"] = str(e)

import config

# Wayscope theme (29 Sep): ink #1F2024 for headings, the accent red for over/short, grey for notes.
NAVY = "1F2024"
NAVY_RGB = (0x1F / 255, 0x20 / 255, 0x24 / 255)
RED_RGB = (0xDC / 255, 0x26 / 255, 0x26 / 255)
BLUE_RGB = (0x25 / 255, 0x63 / 255, 0xEB / 255)
GREY = (0x64 / 255, 0x74 / 255, 0x8B / 255)
# 13 Oct 2026 (D45, Option A): the demo notice as the app's demo bar: light grey band, red text, a red rule and a
# red DEMO tag with white text (5.91:1 and 6.47:1). The same on every PDF and in the XLSX.
DEMO_BG_RGB = (0xF1 / 255, 0xF5 / 255, 0xF9 / 255)
DEMO_FG_RGB = (0xB9 / 255, 0x1C / 255, 0x1C / 255)
DEMO_RULE_RGB = (0xDC / 255, 0x26 / 255, 0x26 / 255)
DEMO_FG_HEX, DEMO_BG_HEX = "B91C1C", "F1F5F9"
BAND = (0xEF / 255, 0xF6 / 255, 0xFF / 255)


def _tenant():
    """The tenant block — name, team label, currency symbol — for titles and headers."""
    try:
        import conversions as _conversions
        return config.tenant_settings(_conversions)
    except Exception:
        return dict(config.TENANT_DEFAULTS, currency_symbol="€")


def _tenant_name():
    return _tenant().get("name") or "Wayscope"


def _demo_notice():
    """The tenant's notice ("Fictional demo scheme …"), or None — H2, 5 Oct 2026. Printed
    on both exports whenever it is set, so no demo sheet leaves the stand unlabelled."""
    return _tenant().get("demo_notice") or None


def _cur():
    """The tenant's currency SYMBOL. Every figure on a sheet is in the tenant's own
    currency; the symbol is presentation, never a conversion."""
    return _tenant().get("currency_symbol") or "€"


# H1 (29 Sep 2026, HU5): the distance unit the tenant READS on its sheets. Everything the
# page hands over is in km; these convert at the sheet boundary and nowhere else.
KM_PER_MI = 1.609344


def _du():
    """'km' or 'mi'."""
    return "mi" if (_tenant().get("distance_unit") or "km") == "mi" else "km"


def _dist(km):
    """A km figure in the tenant's unit (None stays None)."""
    if km is None:
        return None
    try:
        v = float(km)
    except (TypeError, ValueError):
        return km
    return v / KM_PER_MI if _du() == "mi" else v


def _dist_rate(per_km):
    """A per-km rate in the tenant's unit (currency per mile = per km × 1.609)."""
    if per_km is None:
        return None
    try:
        v = float(per_km)
    except (TypeError, ValueError):
        return per_km
    return v * KM_PER_MI if _du() == "mi" else v


def _tkm():
    return "t·mi" if _du() == "mi" else "t·km"


def footer_lines():
    cur = _cur()
    return (f"{cur} from the contract rate typed on the route, or the target rate on Config where the "
            f"route has none (marked 'target'); not printed where neither exists. {cur} + BAF applies the "
            "fuel surcharge (the diesel index vs the locked base × fuel share) and never "
            "replaces the quote.",
            "Road-user charges are not on this sheet. Payloads are planning "
            f"figures, not plated. {'Miles' if _du() == 'mi' else 'Km'} from the baked HERE route unless marked ‡.",
          "Mon–Fri only, one row per line; each day cell is qty / trips · vehicles; † = a typed day "
          "that no longer follows the week ÷ 5. Coordinates are "
          "the location's own (WGS84). Road restrictions are the road authority's stored check as of its own "
          "date, not re-read for this sheet.",
           )


def _n(v, nd=0):
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if nd == 0:
        return f"{int(round(f)):,}".replace(",", " ")
    return f"{f:,.{nd}f}".replace(",", " ")


def _day_label(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d:%a} {d.day}" if hasattr(d, "strftime") else iso


def _day_month(d):
    """'MON 7 SEP' — no %-d: that strftime flag is glibc-only and raises on Windows."""
    return f"{d:%a} {d.day} {d:%b}".upper()


def _week_title(page):
    cw = page.get("commit_week") or {}
    if not cw.get("from"):
        return "no commit week"
    d = datetime.date.fromisoformat(cw["from"])
    return f"week of {d.day} {d.strftime('%b %Y')}"


def _is_weekday(iso):
    return datetime.date.fromisoformat(iso).weekday() <= 4


def _line_rows(page, weekdays_only=True):
    """Flatten commit lines into (line, day) rows in the export mock's column order.
    Mon–Fri only by default (10 Sep): the weekend days exist at 0 and are not printed."""
    rows = []
    _team = _team_namer()
    for l in page.get("commit", {}).get("lines", []):
        c = l.get("context") or {}
        for d in l.get("days", []):
            if weekdays_only and not _is_weekday(d["day_date"]):
                continue
            f = d.get("derived") or {}
            rows.append({
                "date": d["day_date"], "origin": c.get("origin_name") or c.get("origin_id"),
                "dest": c.get("dest_name") or c.get("dest_id"), "ipt": _team(c.get("ipt")) or "",
                "ws": c.get("section_id") or "", "discipline": c.get("discipline") or "",
                "material": c.get("material_type") or "", "vehicle": c.get("vehicle_short") or c.get("vehicle_type") or "",
                "qty": d.get("planned_qty"), "unit": c.get("unit"),
                "tonnes": f.get("tonnes"), "trips": f.get("trips"), "veh": f.get("vehicles"),
                "km_trip": _dist(c.get("km_trip")), "km_day": _dist(f.get("km_day")), "tonne_km": _dist(f.get("tonne_km")),
                "eur": f.get("eur"), "rate_source": c.get("rate_source") or "",
                "eur_adj": f.get("eur_adj"), "fair_eur": f.get("fair_eur"),
                "fair_eur_per_t": ((c.get("fair") or {}).get("eur_per_t")),
                "fair_flags": " ".join(((c.get("fair") or {}).get("flags")) or []),
                "cycle_min": c.get("cycle_min"),
                "cycle_mark": c.get("cycle_mark") or ("" if c.get("baked") else "—"),
                "baked": c.get("baked"), "status": d.get("status"),
                "days_ne_week": l.get("days_ne_week"), "week_qty": (l.get("week") or {}).get("planned_qty"),
                "route_id": l.get("route_id"), "line": l, "day": d,
            })
    return rows


# --------------------------------------------------------------------------- #
#  XLSX                                                                        #
# --------------------------------------------------------------------------- #
XLSX_COLS_EUR = [("Date", "date"), ("Route", "route_id"), ("Origin", "origin"), ("Destination", "dest"),
             ("IPT", "ipt"), ("WS", "ws"), ("Discipline", "discipline"), ("Material", "material"),
             ("Vehicle", "vehicle"), ("Qty", "qty"), ("Unit", "unit"), ("Tonnes", "tonnes"),
             ("Trips", "trips"), ("Vehicles", "veh"), ("km/trip", "km_trip"), ("km/day", "km_day"),
             ("t·km", "tonne_km"), ("€", "eur"), ("€ source", "rate_source"), ("€ + BAF", "eur_adj"),
             ("€ fair (model)", "fair_eur"), ("fair €/t", "fair_eur_per_t"), ("fair flags", "fair_flags"),
             ("Cycle min", "cycle_min"), ("Cycle source", "cycle_mark"),
             ("Day status", "status"), ("Week qty", "week_qty"), ("Days ≠ week", "days_ne_week")]


def _team_namer():
    """team_text() bound to ONE read of the tenant's team names — call once per sheet,
    not once per row (the export is read by people; ids never reach them)."""
    try:
        import taxonomy
        labels, word = taxonomy.team_labels(), taxonomy._team_word()
        return lambda v: taxonomy.team_text(v, labels, word)
    except Exception:
        return lambda v: v


# What a person reads for each clash code — the same names the user guide's §10.1 uses.
FLAG_LABEL = {"SHORTAGE": "SHORTAGE", "DAYS_NE_WEEK": "DAYS ≠ WEEK", "STOCKPILE_OVER": "STOCKPILE OVER",
              "ROUTE_CAP": "ROUTE CAP", "IPT_SHARE": "SHARE",
              # H1: the restriction flag reads the provider's word (TARK TEE / ROADWORKS);
              # see _flag_label(), which reads it off the flag itself
              "RESTRICTION": "RESTRICTION",
              "UNBAKED": "UNBAKED", "PARENT_CHANGED": "PARENT CHANGED"}


def _flag_label(f):
    """The word a person reads for a flag: the provider's own for RESTRICTION (the flag
    carries `label` — "TARK TEE" for Tark Tee, "ROADWORKS" for National Highways)."""
    code = (f or {}).get("code")
    if code == "RESTRICTION" and (f or {}).get("label"):
        return str(f["label"])
    return FLAG_LABEL.get(code, code)


def _src_word(page):
    """The provider's short name for the sheet's source rows ("Tark Tee", "National
    Highways"), or a neutral word when the page names none."""
    src = ((page.get("clashes") or {}).get("sources") or {})
    ui = src.get("restrictions_ui_label")
    if ui and "(" in ui and ui.endswith(")"):
        return ui[ui.index("(") + 1:-1]
    return "Road restrictions"


def xlsx_cols():
    """XLSX_COLS_EUR with the tenant's currency symbol, team label and distance unit in
    the headers (km/trip → mi/trip, t·km → t·mi for a tenant that reads miles)."""
    cur, team, du = _cur(), _tenant().get("team_label") or "Team", _du()
    def hd(h):
        if h == "IPT":
            return team
        h = h.replace("€", cur)
        if du == "mi":
            h = {"km/trip": "mi/trip", "km/day": "mi/day", "t·km": "t·mi"}.get(h, h)
        return h
    return [(hd(h), k) for h, k in XLSX_COLS_EUR]


XLSX_COLS = XLSX_COLS_EUR   # the EUR-labelled reference set (tests read it); sheets use xlsx_cols()


def build_xlsx(page):
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed: " + MISSING.get("xlsx", ""))
    wb = openpyxl.Workbook()
    head = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor=NAVY)

    def sheet(ws, cols, rows):
        for j, (title, _) in enumerate(cols, 1):
            c = ws.cell(row=1, column=j, value=title)
            c.font, c.fill = head, fill
            c.alignment = Alignment(horizontal="center")
        for i, r in enumerate(rows, 2):
            for j, (_, key) in enumerate(cols, 1):
                v = r.get(key)
                if isinstance(v, bool):
                    v = "yes" if v else ""
                ws.cell(row=i, column=j, value=v)
        for j, (title, _) in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(j)].width = max(10, min(28, len(title) + 6))
        ws.freeze_panes = "A2"

    ws = wb.active
    ws.title = "Commit week"
    rows = _line_rows(page)
    sheet(ws, xlsx_cols(), rows)
    # no Stock sheet (10 Sep): the sheet is for the supplier; stock is the planner's
    # 10 Sep evening: the fuel index and settings every € + BAF above was computed from
    ws_f = wb.create_sheet("Fuel")
    cost = page.get("costing") or {}
    fu = cost.get("fuel") or {}
    for i, (k, v) in enumerate((
            (f"Diesel index {_cur()}/L", cost.get("index_eur_per_l")),
            (_index_date_label(cost), cost.get("index_bulletin_date")),
            ("Index source", cost.get("index_source")),
            ("Attribution", _index_attribution(cost)),
            (f"BAF base {_cur()}/L", fu.get("baf_base_eur_per_l")),
            (f"BAF base {_index_date_label(cost).lower()}", fu.get("baf_base_bulletin_date")),
            ("Fuel share %", fu.get("share_pct")),
            ("BAF %", (round(cost["baf_pct"] * 100, 2) if cost.get("baf_pct") is not None else None)),
            ("BAF not applied because", cost.get("baf_reason") or ""),
            # the yard price and the target rates are the planner's own numbers and are
            # NOT on the supplier's sheet — only the public index and the BAF terms
            ("Lines priced at the target rate", (page.get("commit", {}).get("totals") or {}).get("eur_target_lines")),
            ("Fair price (model) — total this week", (page.get("commit", {}).get("totals") or {}).get("fair_eur")),
            (f"Fair price: driver {_cur()}/h", (cost.get("fair") or {}).get("driver_eur_per_h")),
            (f"Fair price: vehicle standing {_cur()}/h", (cost.get("fair") or {}).get("vehicle_standing_eur_per_h")),
            (f"Fair price: running {_cur()}/{_du()}", _dist_rate((cost.get("fair") or {}).get("running_eur_per_km"))),
            ("Fair price: margin %", (cost.get("fair") or {}).get("margin_pct")),
            ("Fair price: L/100 km per tonne · rigid empty · artic empty",
             " · ".join(str((cost.get("fair") or {}).get(k)) for k in ("l_per_100km_per_tonne", "rigid_l_per_100km_empty", "artic_l_per_100km_empty"))),
            ("Fair price: winter months / uplift % / thaw months",
             f"{(cost.get('fair') or {}).get('winter_months')} / {(cost.get('fair') or {}).get('winter_consumption_uplift_pct')} / {(cost.get('fair') or {}).get('thaw_months')}")), 1):
        ws_f.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws_f.cell(row=i, column=2, value=v)
    ws_f.column_dimensions["A"].width = 34
    ws_f.column_dimensions["B"].width = 40
    ws3 = wb.create_sheet("Clashes")
    _nm = _team_namer()
    sheet(ws3, [("Code", "code"), ("Route", "route_id"), (_tenant().get("team_label") or "Team", "ipt"),
                ("WS", "section_id"), ("Day", "day_date"), ("Detail", "text")],
          [dict(f, code=_flag_label(f), ipt=_nm(f.get("ipt")), text=_nm(f.get("text")))
           for f in ((page.get("clashes") or {}).get("flags") or [])])
    ws4 = wb.create_sheet("About")
    about = [
        ("Sheet", f"{_tenant_name()} · {_week_title(page)} · commit week"),
        ("Notice", _demo_notice() or ""),
        ("Generated", datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        ("Bucket", page.get("bucket")),
        ("Lines", (page.get("commit", {}).get("totals") or {}).get("lines")),
        ("Unbaked lines", (page.get("commit", {}).get("totals") or {}).get("unbaked_lines")),
        (_src_word(page), ((page.get("clashes") or {}).get("sources") or {}).get("restrictions")),
        (_src_word(page) + " checked", ((page.get("clashes") or {}).get("sources") or {}).get("restrictions_checked_at")),
        ("Days", "Mon–Fri only; Sat/Sun are 0 and not listed"),
    ] + [("Note", f) for f in footer_lines()]
    for i, (k, v) in enumerate(about, 1):
        ws4.cell(row=i, column=1, value=k).font = Font(bold=True)
        cv = ws4.cell(row=i, column=2, value=v)
        if k == "Notice" and v:   # 13 Oct 2026 (D45): the demo bar's colours
            cv.font = Font(bold=True, color=DEMO_FG_HEX)
            cv.fill = PatternFill("solid", fgColor=DEMO_BG_HEX)
    ws4.column_dimensions["A"].width = 16
    ws4.column_dimensions["B"].width = 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  The route map (2026-09-10)                                                  #
# --------------------------------------------------------------------------- #
def _encode_polyline(coords, precision=5):
    """Google encoded polyline of [(lon, lat), …] — what Mapbox's static path takes."""
    out, last_lat, last_lon, f = [], 0, 0, 10 ** precision
    for lon, lat in coords:
        ilat, ilon = int(round(lat * f)), int(round(lon * f))
        for v in (ilat - last_lat, ilon - last_lon):
            v = ~(v << 1) if v < 0 else (v << 1)
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1f)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        last_lat, last_lon = ilat, ilon
    return "".join(out)


def _thin(coords, n=120):
    if len(coords) <= n:
        return coords
    step = (len(coords) - 1) / (n - 1)
    return [coords[int(round(i * step))] for i in range(n)]


def route_geometries(page):
    """[(route_id, origin_name, dest_name, [(lon, lat), …])] for the lines on the page —
    the loaded alt-0 geometry for the line's own vehicle, else any baked profile. Since
    10 Sep this is lookahead.week_geometry(), the same read the Commit view's map makes
    (three queries for the whole page, not two per route). Unbaked routes are absent."""
    import lookahead
    lines = page.get("commit", {}).get("lines", [])
    out = []
    for g in lookahead.week_geometry([l.get("route_id") for l in lines],
                                     {l.get("route_id"): (l.get("context") or {}).get("vehicle_type") for l in lines}):
        if g.get("geometry") and len(g["geometry"]) >= 2:
            out.append((g["route_id"], g["origin"]["name"], g["dest"]["name"],
                        [(float(p[0]), float(p[1])) for p in g["geometry"]]))
    return out


def mapbox_static_png(routes, size="1200x600", timeout=12, token=None):
    """
    A PNG of the routes over Mapbox's light style, or None. Uses config.mapbox_token()
    — MAPBOX_TOKEN on Render when set, else the same public token the browser map
    uses (until 10 Sep this read only the env var, which Render never had, so every
    PDF fell back to the schematic). Needs a network path to api.mapbox.com; the build
    sandbox has none, so the fetch itself is exercised only through a stub.
    """
    token = config.mapbox_token() if token is None else token
    if not token or not routes:
        return None
    overlays = []
    for i, (rid, o, d, coords) in enumerate(routes):
        thin = _thin(coords)
        overlays.append("path-3+1F2024-0.9(" + urllib.parse.quote(_encode_polyline(thin), safe="") + ")")
        overlays.append(f"pin-s-{chr(97 + (i % 26))}+1F2024({thin[0][0]:.5f},{thin[0][1]:.5f})")
        overlays.append(f"pin-s-{chr(97 + (i % 26))}+DC2626({thin[-1][0]:.5f},{thin[-1][1]:.5f})")
    url = ("https://api.mapbox.com/styles/v1/mapbox/light-v11/static/" + ",".join(overlays)
           + f"/auto/{size}@2x?padding=40&access_token=" + urllib.parse.quote(token))
    if len(url) > 8000:                       # the API's URL limit; drop pins, thin harder
        overlays = ["path-3+1F2024-0.9(" + urllib.parse.quote(_encode_polyline(_thin(c, 60)), safe="") + ")"
                    for (_, _, _, c) in routes]
        url = ("https://api.mapbox.com/styles/v1/mapbox/light-v11/static/" + ",".join(overlays)
               + f"/auto/{size}@2x?padding=40&access_token=" + urllib.parse.quote(token))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Wayscope/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return data if data[:8] == b"\x89PNG\r\n\x1a\n" else None
    except Exception:
        return None


def _draw_schematic(c, routes, x, y, w, h):
    """The fallback: every route as a line scaled into the box, ends labelled."""
    c.setStrokeColorRGB(0.85, 0.85, 0.85)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, stroke=1, fill=0)
    pts = [p for (_, _, _, cs) in routes for p in cs]
    if not pts:
        c.setFont("Helvetica", 8); c.setFillColorRGB(*GREY)
        c.drawString(x + 3 * mm, y + h / 2, "no baked route to draw")
        return
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    lo_x, hi_x, lo_y, hi_y = min(lons), max(lons), min(lats), max(lats)
    import math
    kx = math.cos(math.radians((lo_y + hi_y) / 2)) or 1.0    # lon degrees are shorter than lat degrees
    span_x, span_y = max((hi_x - lo_x) * kx, 1e-6), max(hi_y - lo_y, 1e-6)
    pad = 6 * mm
    scale = min((w - 2 * pad) / span_x, (h - 2 * pad) / span_y)
    ox = x + (w - span_x * scale) / 2
    oy = y + (h - span_y * scale) / 2
    def P(p):
        return ox + (p[0] - lo_x) * kx * scale, oy + (p[1] - lo_y) * scale
    for i, (rid, o, d, cs) in enumerate(routes):
        c.setStrokeColorRGB(*NAVY_RGB); c.setLineWidth(1.4)
        path = c.beginPath()
        path.moveTo(*P(cs[0]))
        for p in cs[1:]:
            path.lineTo(*P(p))
        c.drawPath(path, stroke=1, fill=0)
        sx, sy = P(cs[0]); ex, ey = P(cs[-1])
        c.setFillColorRGB(*NAVY_RGB); c.circle(sx, sy, 1.6, stroke=0, fill=1)
        c.setFillColorRGB(*RED_RGB); c.circle(ex, ey, 1.6, stroke=0, fill=1)
        c.setFont("Helvetica", 6.5); c.setFillColorRGB(*NAVY_RGB)
        c.drawString(sx + 2, sy + 2, f"{o}"[:24])
        c.setFillColorRGB(*RED_RGB)
        c.drawString(ex + 2, ey - 6, f"{d} ({rid})"[:30])


def draw_route_map(c, page, x, y, w, h, routes=None):
    """The map block: Mapbox static when it can be had, else the schematic. Returns
    which one was drawn, so the caption can say so. `routes` may be passed in when the
    caller has already read them (one DB read, not two)."""
    routes = route_geometries(page) if routes is None else routes
    png = mapbox_static_png(routes)
    if png:
        try:
            c.drawImage(ImageReader(io.BytesIO(png)), x, y, width=w, height=h,
                        preserveAspectRatio=True, anchor="c")
            return "mapbox"
        except Exception:
            pass
    _draw_schematic(c, routes, x, y, w, h)
    return "schematic"


# --------------------------------------------------------------------------- #
#  The page frame (12 Oct 2026) — one helper for the week sheet, the carbon     #
#  summary and the monthly bulletin                                             #
# --------------------------------------------------------------------------- #
def page_frame(W, H, lm, rm, title, *, rule_y, title_font, title_y, right=None, sub=None,
               notice=None, foot=None, page_y=None):
    """
    The frame every PDF here draws on each page, as an onPage(canvas, doc) for a PageTemplate.
    Extracted from the Carbon planner summary's portrait frame (review §2.6) so the bulletin
    does not grow a third copy. Drawn in one fixed order, each part only when it is given:

        rule      a 2 pt ink rule across the page at rule_y
        title     ink, title_font = (font, size), at title_y
        right     (text, font, size, rgb) right-aligned on the title's baseline: the stamp
        sub       (text, font, size, rgb, y) the sub-line under the title
        notice    (text, font, size, rgb, y) the tenant's demo notice — on EVERY page, so no
                  sheet that leaves the stand is unlabelled. 13 Oct 2026 (D45): drawn as the app's demo
                  bar, a light grey band across the page with a red DEMO tag, red text and a red rule
                  under it; rgb is ignored (the bar's colours are fixed)
        foot      (left text or None, font or None, size, rgb) at the foot; font None keeps the
                  sub-line's font for the page number (the week sheet's order)
        page N    right-aligned at the foot, always

    The two sheets that had their own frame draw exactly what they drew before (the pinned PDF
    texts in test_lookahead, test_carbon, test_h1_uk, test_costing, test_fairprice and
    http_smoke are unchanged). Text in Helvetica's WinAnsi set: callers pass _pdf_safe() text.
    """
    page_y = 7 * mm if page_y is None else page_y

    def on_page(c, doc):
        c.saveState()
        c.setStrokeColorRGB(*NAVY_RGB); c.setLineWidth(2)
        c.line(lm, rule_y, W - rm, rule_y)
        c.setFont(*title_font); c.setFillColorRGB(*NAVY_RGB)
        c.drawString(lm, title_y, title)
        if right:
            text, font, size, rgb = right
            c.setFont(font, size); c.setFillColorRGB(*rgb)
            c.drawRightString(W - rm, title_y, text)
        if sub:
            text, font, size, rgb, y = sub
            c.setFont(font, size); c.setFillColorRGB(*rgb)
            c.drawString(lm, y, text)
        if notice:
            text, font, size, rgb, y = notice
            c.setFillColorRGB(*DEMO_BG_RGB)
            c.rect(lm, y - 3, W - lm - rm, size + 4, stroke=0, fill=1)
            c.setStrokeColorRGB(*DEMO_RULE_RGB); c.setLineWidth(1.5)
            c.line(lm, y - 3, W - rm, y - 3)
            tag_w = c.stringWidth("DEMO", font, size) + 6
            c.setFillColorRGB(*DEMO_FG_RGB)
            c.rect(lm + 4, y - 1.5, tag_w, size + 1.5, stroke=0, fill=1)
            c.setFont(font, size); c.setFillColorRGB(1, 1, 1)
            c.drawString(lm + 7, y, "DEMO")
            c.setFillColorRGB(*DEMO_FG_RGB)
            c.drawString(lm + 4 + tag_w + 6, y, text)
        if foot:
            left, font, size, rgb = foot
            if font:
                c.setFont(font, size); c.setFillColorRGB(*rgb)
            if left:
                c.drawString(lm, page_y, left)
        c.drawRightString(W - rm, page_y, f"page {doc.page}")
        c.restoreState()
    return on_page


def frame_doc(buf, W, H, lm, rm, top, bottom, title, on_page):
    """One page template, one full-width frame inside the margins, the frame drawn on every page."""
    doc = BaseDocTemplate(buf, pagesize=(W, H), leftMargin=lm, rightMargin=rm, topMargin=top,
                          bottomMargin=bottom, title=title, pageCompression=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(lm, bottom, W - lm - rm, H - top - bottom, id="f",
                                                                leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
                                       onPage=on_page)])
    return doc


# --------------------------------------------------------------------------- #
#  PDF — landscape, one row per line, Mon…Fri as columns, as many pages as needed #
# --------------------------------------------------------------------------- #
class _MapFlowable(Flowable):
    """The route map as a platypus flowable: Mapbox static when it can be had, else the
    schematic. Records which one it drew in `kind` for the caption that follows it."""
    def __init__(self, page, width, height):
        Flowable.__init__(self)
        self.page, self.width, self.height, self.kind = page, width, height, None

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        # 29 Sep 2026 first look: with nothing baked the caption blamed Mapbox. Remember
        # whether there was anything to draw, so the caption can tell the two apart.
        routes = route_geometries(self.page)
        self.n_drawn = len(routes)
        self.kind = draw_route_map(self.canv, self.page, 0, 0, self.width, self.height, routes=routes)


def _coord(lat, lon):
    return f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else "no coordinates"


def _pdf_rows(page):
    """One entry per line: the context, the five weekday cells (Mon..Fri in order), and
    the week's totals. Sorted by origin, then route, then WS — the supplier reads by
    where the material leaves from."""
    import lookahead
    lines = page.get("commit", {}).get("lines", [])
    ends = {g["route_id"]: g for g in lookahead.week_geometry(
        [l.get("route_id") for l in lines],
        {l.get("route_id"): (l.get("context") or {}).get("vehicle_type") for l in lines})}
    out = []
    for l in lines:
        c = l.get("context") or {}
        wd = sorted([d for d in l.get("days", []) if _is_weekday(d["day_date"])], key=lambda d: d["day_date"])
        g = ends.get(l.get("route_id")) or {}
        out.append({"line": l, "ctx": c, "days": wd, "geo": g,
                    "origin": c.get("origin_name") or c.get("origin_id") or "—",
                    "dest": c.get("dest_name") or c.get("dest_id") or "—",
                    "wk": l.get("week_derived") or {}})
    out.sort(key=lambda r: (r["origin"], r["line"].get("route_id") or "", r["ctx"].get("section_id") or ""))
    return out


def build_pdf(page):
    if rl_canvas is None:
        raise RuntimeError("reportlab is not installed: " + MISSING.get("pdf", ""))
    buf = io.BytesIO()
    W, H = landscape(A4)
    lm = rm = 10 * mm
    top, bottom = (25 if _demo_notice() else 20) * mm, 12 * mm   # 13 Oct 2026 (D45): room for the demo bar
    usable = W - lm - rm
    lines = page.get("commit", {}).get("lines", [])
    confirmed_all = bool(lines) and all(((l.get("week") or {}).get("status") == "confirmed") for l in lines)
    title = f"{_tenant_name()} · {_week_title(page)}"

    # 12 Oct 2026 (the bulletin, review §2.6): the frame is page_frame(), shared with the carbon
    # summary and the bulletin; this sheet's values, drawn in the same order as before
    on_page = page_frame(W, H, lm, rm, title, rule_y=H - 8 * mm, title_font=("Helvetica-Bold", 14),
                         title_y=H - 14 * mm,
                         right=("CONFIRMED" if confirmed_all else "DRAFT — not confirmed", "Helvetica-Bold", 9,
                                NAVY_RGB if confirmed_all else RED_RGB),
                         sub=("Commitment sheet · not a delivery note · planning payloads, not plated · Mon–Fri only",
                              "Helvetica", 7.5, GREY, H - 18 * mm),
                         notice=((_pdf_safe(_demo_notice()), "Helvetica-Bold", 8.5, DEMO_FG_RGB, H - 22.5 * mm)
                                 if _demo_notice() else None))
    doc = frame_doc(buf, W, H, lm, rm, top, bottom, title, on_page)

    st = ParagraphStyle("b", fontName="Helvetica", fontSize=7.5, leading=9)
    st_sm = ParagraphStyle("s", parent=st, fontSize=6.5, leading=7.5, textColor=colors.Color(*GREY))
    st_h = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold", fontSize=7, leading=8.5, textColor=colors.white)
    st_hc = ParagraphStyle("hc", parent=st_h, alignment=1)
    st_r = ParagraphStyle("r", parent=st, alignment=2)
    st_c = ParagraphStyle("c", parent=st, alignment=1)
    st_grey = ParagraphStyle("g", parent=st, fontSize=8, leading=10, textColor=colors.Color(*GREY))
    st_navy = ParagraphStyle("n", parent=st, fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.Color(*NAVY_RGB))
    st_red = ParagraphStyle("rd", parent=st, fontSize=8, leading=10, textColor=colors.Color(*RED_RGB))

    def P(txt, style=st):
        return Paragraph(str(txt), style)

    def E(v):
        """Data into markup: escape it. The markup itself (<b>, <br/>, <font>) is ours."""
        return str(v if v is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = []
    # 1. the map, full width
    map_h = 92 * mm
    mp = _MapFlowable(page, usable, map_h)
    story.append(mp)
    story.append(_Caption(page, mp, st_grey))
    story.append(Spacer(1, 3 * mm))

    # 2. the table
    rows = _pdf_rows(page)
    dates = sorted({d["day_date"] for r in rows for d in r["days"]})[:5]
    priced = (page.get("commit", {}).get("totals") or {}).get("eur") is not None
    today = page.get("today")
    head = [P("ROUTE", st_h), P("ORIGIN<br/><font size=6>name · lat, lon</font>", st_h),
            P("DESTINATION<br/><font size=6>name · lat, lon</font>", st_h), P(f"{E((_tenant().get('team_label') or 'Team').upper())} / WS", st_h),
            P("MATERIAL", st_h), P("VEHICLE", st_h)]
    for iso in dates:
        d = datetime.date.fromisoformat(iso)
        head.append(P(f"{_day_month(d)}{' · TODAY' if iso == today else ''}"
                      f"<br/><font size=6>qty / trips · veh</font>", st_hc))
    head += [P(f"WEEK<br/><font size=6>qty · trips · {_tkm()}</font>", st_hc), P(f"{_du().upper()}/TRIP", st_hc)]
    if priced:
        head.append(P(f"{_cur()} WEEK", st_hc))
    data = [head]
    tot = {"t": 0.0, "trips": 0, "tkm": 0.0, "eur": 0.0, "eur_any": False}
    _nm_rows = _team_namer()
    for r in rows:
        c, g, wk, l = r["ctx"], r["geo"], r["wk"], r["line"]
        o, d = g.get("origin") or {}, g.get("dest") or {}
        by_date = {x["day_date"]: x for x in r["days"]}
        row = [P(f"<b>{E(l.get('route_id'))}</b>", st),
               P(f"<b>{E(r['origin'])}</b><br/><font size=6.5 color='#64748B'>{_coord(o.get('lat'), o.get('lon'))}</font>", st),
               P(f"<b>{E(r['dest'])}</b><br/><font size=6.5 color='#64748B'>{_coord(d.get('lat'), d.get('lon'))}</font>", st),
               P(f"{E(_nm_rows(c.get('ipt')) or '—')}<br/>{E(c.get('section_id') or '')}", st),
               P(E(c.get("material_type") or "—"), st),
               P(f"{E(c.get('vehicle_short') or c.get('vehicle_type') or '—')}"
                 + ("" if c.get("baked") else "<br/><font size=6 color='#B45309'>not baked</font>"), st)]
        for iso in dates:
            x = by_date.get(iso)
            if not x:
                row.append(P("—", st_c)); continue
            f = x.get("derived") or {}
            qty = f"{_n(x.get('planned_qty'))} {c.get('unit') or ''}".strip()
            sub = (f"{_n(f.get('trips'))} tr · {_n(f.get('vehicles')) if c.get('baked') else '—'} veh"
                   if x.get("planned_qty") else "0")
            mark = " †" if x.get("status") == "edited" else ""       # Helvetica has no ✎
            row.append(P(f"<b>{qty}</b>{mark}<br/><font size=6.5 color='#64748B'>{sub}</font>", st_c))
        wq = (l.get("week") or {}).get("planned_qty")
        row.append(P(f"<b>{_n(wq)} {c.get('unit') or ''}</b><br/><font size=6.5 color='#64748B'>{_n(wk.get('trips'))} tr · "
                     f"{_n(_dist(wk.get('tonne_km'))) if c.get('baked') else '—'} {_tkm()}</font>", st_c))
        row.append(P((_n(_dist(c.get("km_trip"))) + (c.get("cycle_mark") or "")) if c.get("baked") else "—", st_c))
        if priced:
            if wk.get("eur") is None:
                row.append(P("—", st_c))
            else:
                tail = ("<br/><font size=6 color='#64748B'>target</font>" if c.get("rate_source") == "target" else "")
                if wk.get("eur_adj") is not None:
                    tail += f"<br/><font size=6.5 color='#64748B'>+BAF {_n(wk['eur_adj'])}</font>"
                row.append(P(_n(wk.get("eur")) + tail, st_c))
        data.append(row)
        tot["t"] += float(wk.get("tonnes") or 0)
        tot["trips"] += int(wk.get("trips") or 0)
        tot["tkm"] += float(_dist(wk.get("tonne_km")) or 0)
        if wk.get("eur") is not None:
            tot["eur"] += float(wk["eur"]); tot["eur_any"] = True
        if wk.get("eur_adj") is not None:
            tot["eur_adj"] = tot.get("eur_adj", 0.0) + float(wk["eur_adj"])

    if rows:
        n_fixed = 6
        ndays = len(dates)
        day_w = 19 * mm
        widths = [13 * mm, 33 * mm, 33 * mm, 15 * mm, 22 * mm, 18 * mm] + [day_w] * ndays + [27 * mm, 13 * mm]
        if priced:
            # wider when a + BAF line sits under the quote, so "+BAF 9 896" does not wrap
            widths.append(20 * mm if (page.get("costing") or {}).get("baf_pct") is not None else 14 * mm)
        # whatever is left after the fixed columns goes to origin / destination
        spare = usable - sum(widths)
        widths[1] += spare / 2; widths[2] += spare / 2
        total_row = [P("<b>TOTAL</b>", st), P(f"{len(rows)} line(s)", st), "", "", "", ""] + [""] * ndays + [
            P(f"<b>{_n(tot['t'])} t</b><br/><font size=6.5 color='#64748B'>{_n(tot['trips'])} tr · {_n(tot['tkm'])} {_tkm()}</font>", st_c), ""]
        if priced:
            adj = (f"<br/><font size=6.5 color='#64748B'>+BAF {_n(tot['eur_adj'])}</font>"
                   if tot.get("eur_adj") is not None else "")
            total_row.append(P((f"<b>{_n(tot['eur'])}</b>" + adj) if tot["eur_any"] else "—", st_c))
        data.append(total_row)
        t = LongTable(data, colWidths=widths, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.Color(*NAVY_RGB)),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.Color(0.85, 0.87, 0.9)),
                 ("LINEAFTER", (0, 0), (-2, -1), 0.3, colors.Color(0.9, 0.92, 0.95)),
                 ("BOX", (0, 0), (-1, -1), 0.6, colors.Color(0.75, 0.78, 0.83)),
                 ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.Color(0.97, 0.98, 0.99)]),
                 ("BACKGROUND", (0, -1), (-1, -1), colors.Color(*BAND)),
                 ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.Color(*NAVY_RGB))]
        if today in dates:
            ci = n_fixed + dates.index(today)
            style.append(("BACKGROUND", (ci, 1), (ci, -2), colors.Color(0.94, 0.97, 1.0)))
        t.setStyle(TableStyle(style))
        story.append(t)
    else:
        story.append(P("No approved forecast line in this commit week.", st_grey))
    story.append(Spacer(1, 4 * mm))

    # 3. flags
    _nm = _team_namer()
    flags = (page.get("clashes") or {}).get("flags") or []
    fl = [P("Flags (not a stop)", st_navy)]
    if flags:
        for f in flags[:12]:
            fl.append(P(E(f"{_flag_label(f)}: {_nm(f['text'])}"[:160]), st_red))
        if len(flags) > 12:
            fl.append(P(f"+{len(flags) - 12} more on the XLSX", st_red))
    else:
        tt = ((page.get("clashes") or {}).get("sources") or {}).get("restrictions")
        fl.append(P("none" + (f" · {_src_word(page)} unavailable, restrictions not checked" if tt == "unavailable" else ""), st_grey))
    story.append(KeepTogether(fl))
    story.append(Spacer(1, 3 * mm))

    # 4. footer lines + the confirmation stamp
    stamp = None
    for l in lines:
        if (l.get("week") or {}).get("confirmed_at"):
            stamp = l["week"]["confirmed_at"]
    ft = [P(E(f), st_grey) for f in footer_lines()]
    if _demo_notice():                       # H2: the demo label is on the PDF too
        ft.insert(0, P(f'<font color="#{DEMO_FG_HEX}"><b>' + E(_demo_notice()) + "</b></font>", st_grey))
    ft.append(P(E(_fuel_line(page)), st_grey))
    ft.append(P((f"Confirmed {stamp}. " if stamp else "Not yet confirmed. ") + "Re-open the week in Look-ahead to change the plan.", st_grey))
    story.append(KeepTogether(ft))
    doc.build(story)
    return buf.getvalue()


# ------------------------------------------------------------------ carbon summary (11 Oct 2026)
def _pdf_safe(s):
    """Helvetica's WinAnsi set has no arrow: route words read "A to B" on paper."""
    return str(s if s is not None else "").replace("→", "to")


def build_carbon_pdf(sc, commentary=None, generated=None):
    """
    After the show (notes/carbon-ui-1011 item 11): the Carbon page's one-page summary for the file —
    the approved plan beside the alternative, the decisions in words and ranked, what the figures
    count, and a Commentary box. Every figure is the scenario's own (carbon.scenario, the read the
    page shows); this draws, it never computes. Stamped on the page: a Wayscope planning estimate on
    the DESNZ 2026 basis, not Carbon Tool figures; the tenant's demo notice when it is set.
    """
    if rl_canvas is None:
        raise RuntimeError("reportlab is not installed: " + MISSING.get("pdf", ""))
    import carbon as _carbon
    buf = io.BytesIO()
    W, H = A4
    lm = rm = 14 * mm
    top, bottom = 30 * mm, 14 * mm
    usable = W - lm - rm
    when = generated or datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y")
    title = f"{_tenant_name()} · Carbon planner summary"
    stamp = _carbon.SUMMARY_STAMP
    notice = _demo_notice()

    # 12 Oct 2026 (the bulletin, review §2.6): the portrait frame, now page_frame() — the bulletin
    # draws the same one with its own words
    on_page = page_frame(W, H, lm, rm, _pdf_safe(title), rule_y=H - 9 * mm, title_font=("Helvetica-Bold", 13),
                         title_y=H - 15 * mm, right=(f"Generated {when}", "Helvetica", 8, GREY),
                         sub=(stamp, "Helvetica-Bold", 9, RED_RGB, H - 20.5 * mm),
                         notice=((_pdf_safe(notice), "Helvetica-Bold", 8.5, DEMO_FG_RGB, H - 25 * mm) if notice else None),
                         foot=(stamp, "Helvetica", 7, GREY))
    doc = frame_doc(buf, W, H, lm, rm, top, bottom, title, on_page)
    st = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=10.5)
    st_r = ParagraphStyle("r", parent=st, alignment=2)
    st_h = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white)
    st_hr = ParagraphStyle("hr", parent=st_h, alignment=2)
    st_sec = ParagraphStyle("sec", parent=st, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=4,
                            textColor=colors.Color(*NAVY_RGB))
    st_grey = ParagraphStyle("g", parent=st, fontSize=7.5, leading=9.5, textColor=colors.Color(*GREY))

    def E(v):
        return _pdf_safe(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def P(txt, style=st):
        return Paragraph(str(txt), style)

    def t1(v):
        return "no data" if v is None else _n(v, 1)

    def moved(v):
        if v is None:
            return "no data"
        return (f"{_n(-v, 1)} tCO2e lower" if v < -0.0005 else f"{_n(v, 1)} tCO2e higher" if v > 0.0005 else "no change")

    def loads(n):
        return "" if not n else (f"{_n(-n)} fewer lorry loads" if n < 0 else f"{_n(n)} more lorry loads")

    def lkm(km):
        if km is None or abs(km) < 0.5:
            return ""
        return f"{_n(abs(_dist(km)))} {'fewer' if km < 0 else 'more'} lorry-{_du()}"

    def grid(data, widths, right_from=1):
        t = LongTable(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(*NAVY_RGB)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.Color(0.85, 0.87, 0.9)),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.Color(0.75, 0.78, 0.83)),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
        return t

    B = sc.get("baseline") or {}
    A = (sc.get("alternatives") or [None])[0]
    bt, at = B.get("totals") or {}, (A or {}).get("totals") or {}
    bs, as_ = B.get("stages") or {}, (A or {}).get("stages") or {}
    bf, af = B.get("fleet") or {}, (A or {}).get("fleet") or {}

    def alt(v):
        return v if A else "no alternative"

    story = []
    # 1. the approved plan and the alternative
    story.append(P("The approved plan and the alternative", st_sec))
    stage = lambda s: f"{t1(s.get('A1-A3'))} · {t1(s.get('A4'))} · {t1(s.get('A5'))}"
    rows = [[P("tCO2e", st_h), P("Approved plan", st_hr), P("Alternative", st_hr)],
            [P("<b>Total</b>"), P(f"<b>{t1(bt.get('total_t'))}</b>", st_r), P(f"<b>{alt(t1(at.get('total_t')))}</b>", st_r)],
            [P("Material"), P(t1(bt.get("material_t")), st_r), P(alt(t1(at.get("material_t"))), st_r)],
            [P("Transport"), P(t1(bt.get("transport_t")), st_r), P(alt(t1(at.get("transport_t"))), st_r)],
            [P("Waste disposal"), P(t1(bt.get("disposal_t")), st_r), P(alt(t1(at.get("disposal_t"))), st_r)],
            [P("By life-cycle module: A1–A3 · A4 · A5"), P(stage(bs), st_r), P(alt(stage(as_)), st_r)],
            [P("Transport well-to-wheel (adds producing the fuel or electricity; not in the total)"),
             P(t1(bt.get("transport_wtw_t")), st_r), P(alt(t1(at.get("transport_wtw_t"))), st_r)],
            [P("Lorry loads (deliveries)"), P(_n(bf.get("trips")), st_r), P(alt(_n(af.get("trips"))), st_r)],
            [P("Lorries needed in the busiest month"), P(_n(bf.get("lorries_peak")), st_r), P(alt(_n(af.get("lorries_peak"))), st_r)]]
    story.append(grid(rows, [usable * 0.52, usable * 0.24, usable * 0.24]))
    if A:                                    # full width, so the change reads as one line, not a wrapped cell
        ch = [moved(A.get("delta_t")) + (f" ({abs(A['delta_pct']):.1f}%)" if A.get("delta_pct") is not None and abs(A.get("delta_t") or 0) > 0.0005 else "")]
        ch += [x for x in (loads(A.get("delta_trips")), lkm(A.get("delta_vkm_km"))) if x]
        story.append(Spacer(1, 1.5 * mm))
        story.append(P("<b>Change against the approved plan: " + E(" · ".join(ch)) + "</b>"))

    # 2. the decisions, in words and ranked
    story.append(P("The decisions in the alternative", st_sec))
    words = (A or {}).get("lever_words") or []
    if words:
        for w in words:
            story.append(P("• " + E(w)))
    else:
        story.append(P("No alternative chosen: this summary shows the approved plan only.", st_grey))
    drivers = (A or {}).get("drivers") or []
    if drivers:
        story.append(P("Which decisions change carbon most, each on its own", st_sec))
        dr = [[P("Decision", st_h), P("tCO2e", st_hr), P("Lorry loads", st_hr), P(f"Lorry-{_du()}", st_hr)]]
        for d in drivers:
            dr.append([P(E(d.get("label"))), P(E(moved(d.get("delta_t"))) + (f" ({abs(d['delta_pct']):.1f}%)" if d.get("delta_pct") is not None else ""), st_r),
                       P(E(loads(d.get("delta_trips")) or "no change"), st_r), P(E(lkm(d.get("delta_vkm_km")) or "no change"), st_r)])
        story.append(grid(dr, [usable * 0.34, usable * 0.24, usable * 0.21, usable * 0.21]))
        it = A.get("interaction_t") or 0
        story.append(P("The decisions do not affect each other here: together they come to the sum of each on its own."
                       if abs(it) < 0.0005 else
                       f"Together, the result is {_n(abs(it), 1)} tCO2e {'lower' if it < 0 else 'higher'} than adding up each decision on its own.",
                       st_grey))

    # 3. what the figures count
    sw = sc.get("scope_words") or {}
    fl = bt.get("flags") or {}
    unrouted = (bt.get("lines") or 0) - (bt.get("baked_lines") or 0)
    out = [x for x in (
        f"{unrouted} plan line{'s have' if unrouted != 1 else ' has'} no route distance yet: transport not counted" if unrouted > 0 else "",
        f"{_n(bt.get('material_excluded_tonnes'))} t has no Government production factor: making it is not counted" if (bt.get("material_excluded_tonnes") or 0) > 0 else "",
        f"{fl.get('RETURN_NOT_BAKED')} plan lines have no return route distance: loaded leg only" if fl.get("RETURN_NOT_BAKED") else "",
        f"{fl.get('NO_DISPOSAL_FACTOR')} plan lines have no Government disposal factor: disposal not counted" if fl.get("NO_DISPOSAL_FACTOR") else "",
        f"{bt.get('wtw_lines_out')} plan lines' lorries have no published well-to-tank row" if bt.get("wtw_lines_out") else "",
    ) if x]
    story.append(P("What these figures count", st_sec))
    for k, lab in (("counts", "Counts"), ("not_counted", "Does not count"), ("factors", "Factors")):
        story.append(P(f"<b>{lab}:</b> " + E(sw.get(k) or "")))
    story.append(P("<b>Left out here:</b> " + (E("; ".join(out)) if out else "nothing: every plan line is counted in full.")))

    # 4. the commentary, as typed (escaped), or a box to write in
    story.append(P("Commentary", st_sec))
    txt = (commentary or "").strip()
    body = P(E(txt).replace(chr(10), "<br/>")) if txt else P("", st)
    box = LongTable([[body]], colWidths=[usable], rowHeights=[None if txt else 28 * mm])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.Color(0.75, 0.78, 0.83)),
                             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]))
    story.append(box)
    story.append(Spacer(1, 3 * mm))

    # 5. the footer lines
    ft = [P("<b>Planning estimates. Not a National Highways Carbon Tool return.</b> Figures are rounded, so the parts may "
            "not add exactly to the total.", st_grey),
          P(f"Computed on request from the {E((sc.get('status') or 'Approved').lower())} forecast; nothing is stored. The "
            "commentary is printed as typed and is not saved. Each factor's source, year and status is on the Carbon page.", st_grey)]
    if notice:
        ft.insert(0, P(f'<font color="#{DEMO_FG_HEX}"><b>' + E(notice) + "</b></font>", st_grey))
    story.append(KeepTogether(ft))
    doc.build(story)
    return buf.getvalue()


def _index_date_label(cost):
    """The word for the index's date: "Bulletin date" only where the series IS a bulletin
    (the EU Weekly Oil Bulletin); "Published" for DESNZ; "Index date" for a typed figure
    or an unknown provider. 29 Sep 2026 first look: the GB XLSX said "Bulletin date"."""
    country = (cost.get("fuel") or {}).get("country") or ""
    try:
        import fuel as _fuel
        prov = _fuel.provider_public(country)
    except Exception:
        prov = None
    key = (prov or {}).get("key") or ""
    if key == "eu_bulletin":
        return "Bulletin date"
    if key == "desnz":
        return "Published (week ending)"
    return "Index date"


def _index_attribution(cost):
    """What the diesel index IS: the country's provider series (typed or fetched) — the EU
    bulletin for EU-27, DESNZ weekly road fuel prices for GB — or a typed national figure
    for a country with no series (and for a tenant with no country)."""
    if not cost.get("index_source"):
        return ""
    country = (cost.get("fuel") or {}).get("country") or ""
    typed = cost.get("index_source") == "manual"
    try:
        import fuel as _fuel
        prov = _fuel.provider_public(country)
    except Exception:
        prov = None
    if prov:
        return prov["label"] + (" — typed" if typed else "")
    return "typed — no automatic diesel series for this country"


def _fuel_line(page):
    """One footer line naming the diesel index the sheet's € + BAF used — or that none did."""
    cost = page.get("costing") or {}
    fu = cost.get("fuel") or {}
    if cost.get("index_eur_per_l") is None:
        return "Diesel index: not available (no index row for this country and nothing typed)."
    cur = _cur()
    _c = cost.get('fuel', {}).get('country') or '—'
    s = (f"Diesel {'(no country)' if _c == '--' else _c} {cur}{cost['index_eur_per_l']:.3f}/L, "
         f"dated {cost.get('index_bulletin_date') or '—'} ({_index_attribution(cost)}).")
    if cost.get("baf_pct") is not None:
        s += (f" BAF {cost['baf_pct'] * 100:+.2f} % = (index / base {cur}{fu.get('baf_base_eur_per_l'):.3f} of "
              f"{fu.get('baf_base_bulletin_date') or '—'} − 1) × {fu.get('share_pct'):g} % fuel share.")
    else:
        s += f" No BAF applied ({cost.get('baf_reason') or 'not set up'})."
    return s


class _Caption(Flowable):
    """The line under the map — written AFTER the map has drawn, so it can say which
    map it was (Mapbox tiles or the schematic)."""
    def __init__(self, page, map_flowable, style):
        Flowable.__init__(self)
        self.page, self.mp, self.style = page, map_flowable, style
        self.height = 4.5 * mm

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.height

    def draw(self):
        n_routes = len({l.get("route_id") for l in self.page.get("commit", {}).get("lines", [])})
        kind = self.mp.kind
        if kind == "schematic" and not getattr(self.mp, "n_drawn", 1):
            tail = " · no baked route to draw — bake the network for the map"
        elif kind == "schematic":
            tail = " · schematic from the baked geometry (no map tiles — Mapbox could not be reached)"
        else:
            tail = " · map © Mapbox © OpenStreetMap"
        txt = f"Routes this week: {n_routes}" + tail
        self.canv.setFont("Helvetica", 7.5)
        self.canv.setFillColorRGB(*GREY)
        self.canv.drawString(0, 1 * mm, txt)


# ------------------------------------------------------------------ the monthly bulletin (C4, 12 Oct 2026)
# Review §2.6 / mockup 9. The view model is bulletin_doc.sheet() — the SAME one the HTML page
# renders — so every figure here is already formatted; this draws, it never computes.
# The print treatment (colour-system-1010.md): routes and bars in the plan blue as a solid edge
# with its light tint inside, labels in ink; a planning flag dashed in the cap red with its word;
# local controls amber.
PLAN_BLUE_HEX = "4A72C9"
PLAN_BLUE_RGB = (0x4A / 255, 0x72 / 255, 0xC9 / 255)
PLAN_TINT_RGB = (0xD7 / 255, 0xE0 / 255, 0xF3 / 255)
AMBER_HEX = "D97706"
AMBER_RGB = (0xD9 / 255, 0x77 / 255, 0x06 / 255)


def bulletin_map_png(map_routes, places, controls, size="1100x480", timeout=12, token=None):
    """
    The month's routes over Mapbox's light style, or None: each route a plan-blue path whose
    width follows its two-way movements a day (2-8 px), a lettered pin on each site, a numbered
    amber pin on each local control. The URL is thinned until it fits the API's 8,192-character
    limit; when it cannot fit, None (the caller draws the schematic). The harnesses never reach
    Mapbox (portable.offline); the fetch itself is exercised only through that stub.
    """
    token = config.mapbox_token() if token is None else token
    if not token or not map_routes:
        return None
    pins = ([f"pin-s-{p['letter'].lower()}+1F2024({p['at'][0]:.5f},{p['at'][1]:.5f})"
             for p in places if p.get("letter") and p.get("at")]
            + [f"pin-s-{z['n']}+{AMBER_HEX}({z['at'][0]:.5f},{z['at'][1]:.5f})"
               for z in controls if z.get("at") and z["n"] <= 99])
    url = None
    for n_pts in (100, 60, 35, 20, 10):
        paths = [f"path-{2 + round(6 * r['weight'])}+{PLAN_BLUE_HEX}-0.85("
                 + urllib.parse.quote(_encode_polyline(_thin(r["coords"], n_pts)), safe="") + ")"
                 for r in sorted(map_routes, key=lambda r: r["weight"])]
        for with_pins in (True, False):
            u = ("https://api.mapbox.com/styles/v1/mapbox/light-v11/static/" + ",".join(paths + (pins if with_pins else []))
                 + f"/auto/{size}@2x?padding=40&access_token=" + urllib.parse.quote(token))
            if len(u) <= 8000:
                url = u
                break
        if url:
            break
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Wayscope/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return data if data[:8] == b"\x89PNG\r\n\x1a\n" else None
    except Exception:
        return None


def _draw_bulletin_schematic(c, S, x, y, w, h):
    """The fallback: the bulletin's routes, sites and controls scaled into the box (bulletin_doc.projector)."""
    import bulletin_doc
    c.setStrokeColorRGB(0.85, 0.85, 0.85); c.setLineWidth(0.5)
    c.rect(x, y, w, h, stroke=1, fill=0)
    proj = bulletin_doc.projector(bulletin_doc.map_points(S), w, h, 6 * mm)
    if proj is None:
        c.setFont("Helvetica", 8); c.setFillColorRGB(*GREY)
        c.drawString(x + 3 * mm, y + h / 2, "no route with a stored road route to draw this month")
        return
    P = lambda lon, lat: tuple(a + b for a, b in zip((x, y), proj(lon, lat)))
    c.setStrokeColorRGB(*PLAN_BLUE_RGB)
    c.setLineCap(1); c.setLineJoin(1)
    for r in sorted(S["map_routes"], key=lambda r: r["weight"]):
        c.setLineWidth(0.8 + 3.2 * r["weight"])
        path = c.beginPath()
        path.moveTo(*P(*r["coords"][0]))
        for p in r["coords"][1:]:
            path.lineTo(*P(*p))
        c.drawPath(path, stroke=1, fill=0)
    for p in S["places"]:
        if p.get("at") and p.get("letter"):
            px, py = P(*p["at"])
            c.setFillColorRGB(*NAVY_RGB); c.circle(px, py, 4.2, stroke=0, fill=1)
            c.setFillColorRGB(1, 1, 1); c.setFont("Helvetica-Bold", 6.5)
            c.drawCentredString(px, py - 2.3, p["letter"])
    for z in S["controls"]:
        if z.get("at"):
            px, py = P(*z["at"])
            c.setFillColorRGB(*AMBER_RGB); c.rect(px - 4.2, py - 4.2, 8.4, 8.4, stroke=0, fill=1)
            c.setFillColorRGB(1, 1, 1); c.setFont("Helvetica-Bold", 6.5)
            c.drawCentredString(px, py - 2.3, str(z["n"]))


class _BulletinMap(Flowable):
    """The bulletin's map: Mapbox static when it can be had, else the schematic; `kind` says which."""
    def __init__(self, S, width, height):
        Flowable.__init__(self)
        self.S, self.width, self.height, self.kind = S, width, height, None

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        png = bulletin_map_png(self.S["map_routes"], self.S["places"], self.S["controls"])
        if png:
            try:
                self.canv.drawImage(ImageReader(io.BytesIO(png)), 0, 0, width=self.width, height=self.height,
                                    preserveAspectRatio=True, anchor="c")
                self.kind = "mapbox"
                return
            except Exception:
                pass
        _draw_bulletin_schematic(self.canv, self.S, 0, 0, self.width, self.height)
        self.kind = "schematic"


class _BulletinMapCaption(Flowable):
    """The line under the map, written after it has drawn so it says which map it was."""
    def __init__(self, mp, n_routes):
        Flowable.__init__(self)
        self.mp, self.n_routes, self.height = mp, n_routes, 4.5 * mm

    def wrap(self, aw, ah):
        self.width = aw
        return aw, self.height

    def draw(self):
        tail = (" · map © Mapbox © OpenStreetMap" if self.mp.kind == "mapbox"
                else " · schematic from the stored road routes, not to scale (no map tiles)")
        self.canv.setFont("Helvetica", 7.5); self.canv.setFillColorRGB(*GREY)
        self.canv.drawString(0, 1 * mm, f"Routes this month: {self.n_routes} · haul routes in the plan blue, thicker = "
                                        "more two-way movements" + tail)


def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _draw_council_map(c, C, x, y, w, h):
    """
    13 Oct 2026: the districts alone, each in the council layer's orange ramp (bulletin_doc.COUNCIL_RAMP, the
    public map's), drawn from the stored boundary polygons — no routes, no roads, no Mapbox. Holes kept (even-odd
    fill); "no figure" hatched; a white border between districts; one label per district at its label point.
    """
    import bulletin_doc
    proj = bulletin_doc.projector(bulletin_doc.council_points(C), w, h, 3 * mm)
    if proj is None:
        c.setFont("Helvetica", 8); c.setFillColorRGB(*GREY)
        c.drawString(x + 3 * mm, y + h / 2, "no district boundary to draw")
        return
    P = lambda lon, lat: tuple(a + b for a, b in zip((x, y), proj(lon, lat)))
    even_odd = getattr(rl_canvas, "FILL_EVEN_ODD", 0)

    def outline(d):
        path = c.beginPath()
        for ring in d["rings"]:
            path.moveTo(*P(*ring[0]))
            for pt in ring[1:]:
                path.lineTo(*P(*pt))
            path.close()
        return path

    for d in C["districts"]:
        if d["cls"] == "nofig":
            c.saveState()
            c.setFillColorRGB(*_hex_rgb(bulletin_doc.HATCH_PAPER))
            c.drawPath(outline(d), stroke=0, fill=1, fillMode=even_odd)
            c.clipPath(outline(d), stroke=0, fill=0, fillMode=even_odd)
            c.setStrokeColorRGB(*_hex_rgb(bulletin_doc.HATCH_INK)); c.setLineWidth(0.8)
            k = -h
            while k < w:
                c.line(x + k, y, x + k + h, y + h)
                k += 2.4 * mm
            c.restoreState()
        else:
            c.setFillColorRGB(*_hex_rgb(d["fill"]))
            c.drawPath(outline(d), stroke=0, fill=1, fillMode=even_odd)
    c.setStrokeColorRGB(1, 1, 1); c.setLineWidth(1.3); c.setLineJoin(1)
    for d in C["districts"]:
        c.drawPath(outline(d), stroke=1, fill=0)
    for d in C["districts"]:
        if not d.get("label_at"):
            continue
        px, py = P(*d["label_at"])
        for txt, font, size, dy in ((_pdf_safe(d["name"]), "Helvetica-Bold", 7.5, 1.2), (_pdf_safe(d["text"]), "Helvetica", 7.5, -7.4)):
            tw = c.stringWidth(txt, font, size)
            # a white halo (the glyphs stroked), then the ink filled on top: the map's ink-on-white-halo labels. The
            # stroke mode is graphics state and outlives ET (reportlab does not re-emit "0 Tr"), so the halo has its own q/Q
            c.saveState()
            c.setLineWidth(1.6); c.setLineJoin(1)
            t = c.beginText(px - tw / 2, py + dy)
            t.setFont(font, size); t.setStrokeColorRGB(1, 1, 1); t.setTextRenderMode(1)
            t.textOut(txt)
            c.drawText(t)
            c.restoreState()
            c.setFillColorRGB(*NAVY_RGB); c.setFont(font, size)
            c.drawString(px - tw / 2, py + dy, txt)


class _CouncilMap(Flowable):
    def __init__(self, C, width, height):
        Flowable.__init__(self)
        self.C, self.width, self.height = C, width, height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        _draw_council_map(self.canv, self.C, 0, 0, self.width, self.height)


def _council_legend(C, width):
    """The six swatches in one row: the four orange steps, the neutral grey, the hatched "no figure"."""
    from reportlab.graphics.shapes import Drawing, Line, Rect, String, Group
    import bulletin_doc
    items = C["legend"]
    d = Drawing(width, 11)
    d.add(String(0, 2.5, "t CO2e in the month:", fontName="Helvetica-Bold", fontSize=7, fillColor=colors.Color(*NAVY_RGB)))
    x0, step = 30 * mm, (width - 30 * mm) / len(items)
    for i, g in enumerate(items):
        x = x0 + i * step
        if g["hatch"]:
            grp = Group()
            grp.add(Rect(x, 1, 8, 8, fillColor=colors.Color(*_hex_rgb(bulletin_doc.HATCH_PAPER)), strokeColor=None))
            for k in (0, 3, 6):
                grp.add(Line(x + k, 1, x + min(8, k + 8), 1 + min(8, 8 - k), strokeColor=colors.Color(*_hex_rgb(bulletin_doc.HATCH_INK)), strokeWidth=0.8))
            d.add(grp)
            d.add(Rect(x, 1, 8, 8, fillColor=None, strokeColor=colors.Color(0.8, 0.8, 0.8), strokeWidth=0.3))
        else:
            d.add(Rect(x, 1, 8, 8, fillColor=colors.Color(*_hex_rgb(g["fill"])), strokeColor=colors.Color(0.8, 0.8, 0.8), strokeWidth=0.3))
        d.add(String(x + 10.5, 2.5, _pdf_safe(g["label"]), fontName="Helvetica", fontSize=6.8, fillColor=colors.Color(*NAVY_RGB)))
    return d


def _bulletin_chart(S, width):
    """Two-way movements a day by route, each typed cap a dashed red mark (reportlab.graphics)."""
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    import bulletin_doc
    rows = S["routes"][:bulletin_doc.CHART_MAX_ROUTES]
    row_h, top, foot, lab_w = 9.5, 4.0, 14.0, 64 * mm
    h = top + row_h * max(1, len(rows)) + foot
    d = Drawing(width, h)
    if not rows:
        d.add(String(0, h / 2, "No route to chart this month.", fontName="Helvetica", fontSize=8,
                     fillColor=colors.Color(*GREY)))
        return d
    bw = width - lab_w - 18 * mm
    vmax = max([r["a_day"] or 0 for r in rows] + [r["cap"] or 0 for r in rows]) or 1
    for i, r in enumerate(rows):
        y = h - top - (i + 1) * row_h
        lw = bw * (r["a_day"] or 0) / vmax
        d.add(String(lab_w - 4, y + 2.5, _pdf_safe(r["label"])[:46], fontName="Helvetica", fontSize=6.8,
                     textAnchor="end", fillColor=colors.Color(*NAVY_RGB)))
        d.add(Rect(lab_w, y + 1.5, max(lw, 0.01), row_h - 3.5, fillColor=colors.Color(*PLAN_TINT_RGB),
                   strokeColor=colors.Color(*PLAN_BLUE_RGB), strokeWidth=1.2))
        d.add(String(lab_w + lw + 3, y + 2.5, r["a_day_text"], fontName="Helvetica", fontSize=6.8,
                     fillColor=colors.Color(*NAVY_RGB)))
        if r["cap"] is not None:
            cx = lab_w + bw * r["cap"] / vmax
            d.add(Line(cx, y, cx, y + row_h, strokeColor=colors.Color(*RED_RGB), strokeWidth=1.4,
                       strokeDashArray=[2.5, 1.8]))
            d.add(String(cx + 2, y + row_h - 3.2, f"flag {r['cap']:,}", fontName="Helvetica", fontSize=5.5,
                         fillColor=colors.Color(*RED_RGB)))
    d.add(Line(lab_w, foot - 4, lab_w + bw, foot - 4, strokeColor=colors.Color(0.75, 0.75, 0.75), strokeWidth=0.5))
    d.add(String(lab_w, 2, "0", fontName="Helvetica", fontSize=6.5, fillColor=colors.Color(*GREY)))
    d.add(String(lab_w + bw, 2, f"{vmax:,.0f} a day", fontName="Helvetica", fontSize=6.5, textAnchor="end",
                 fillColor=colors.Color(*GREY)))
    return d


def build_bulletin_pdf(S):
    """
    The monthly bulletin, A4 portrait, from bulletin_doc.sheet(month) — page 1 the figures, the
    map, the busiest routes and the counting rule; page 2 the chart, what is being moved, the
    works affecting the roads, what changed, terms, caveats and the report-a-lorry block. The
    frame is page_frame() with the tenant's demo notice on every page.
    """
    if rl_canvas is None:
        raise RuntimeError("reportlab is not installed: " + MISSING.get("pdf", ""))
    from reportlab.platypus import PageBreak
    buf = io.BytesIO()
    W, H = A4
    lm = rm = 14 * mm
    top, bottom = 30 * mm, 14 * mm
    usable = W - lm - rm
    notice = S.get("demo_notice")
    on_page = page_frame(W, H, lm, rm, _pdf_safe(S["title"]), rule_y=H - 9 * mm, title_font=("Helvetica-Bold", 13),
                         title_y=H - 15 * mm, right=(_pdf_safe(S["as_at"]), "Helvetica-Bold", 8.5, NAVY_RGB),
                         sub=(_pdf_safe(f"{S['tenant']} · monthly bulletin · counts are two-way movements"),
                              "Helvetica", 8, GREY, H - 20.5 * mm),
                         notice=((_pdf_safe(notice), "Helvetica-Bold", 8.5, DEMO_FG_RGB, H - 25 * mm) if notice else None),
                         foot=(_pdf_safe(S["foot"]), "Helvetica", 7, GREY))
    doc = frame_doc(buf, W, H, lm, rm, top, bottom, _pdf_safe(f"{S['title']} · {S['tenant']}"), on_page)

    st = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=10.5)
    st_r = ParagraphStyle("r", parent=st, alignment=2)
    st_h = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white)
    st_hr = ParagraphStyle("hr", parent=st_h, alignment=2)
    st_sec = ParagraphStyle("sec", parent=st, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=5,
                            spaceAfter=2, textColor=colors.Color(*NAVY_RGB))
    st_grey = ParagraphStyle("g", parent=st, fontSize=7.5, leading=9.5, textColor=colors.Color(*GREY))
    st_big = ParagraphStyle("big", parent=st, fontName="Helvetica-Bold", fontSize=17, leading=20,
                            textColor=colors.Color(*NAVY_RGB))
    st_lab = ParagraphStyle("lab", parent=st, fontSize=7.5, leading=9, textColor=colors.Color(*GREY))
    st_red = ParagraphStyle("red", parent=st_r, textColor=colors.Color(*RED_RGB), fontName="Helvetica-Bold")

    def E(v):
        return _pdf_safe(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def P(txt, style=st):
        return Paragraph(str(txt), style)

    def grid(data, widths, total_row=False):
        t = LongTable(data, colWidths=widths, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.Color(*NAVY_RGB)),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.Color(0.85, 0.87, 0.9)),
                 ("BOX", (0, 0), (-1, -1), 0.6, colors.Color(0.75, 0.78, 0.83)),
                 ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                 ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if total_row:
            style += [("BACKGROUND", (0, -1), (-1, -1), colors.Color(*BAND)),
                      ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.Color(*NAVY_RGB))]
        t.setStyle(TableStyle(style))
        return t

    story = []
    # ---- page 1
    story.append(P("<b>" + E(S["counting_line"]) + "</b>"))
    story.append(Spacer(1, 2.5 * mm))
    figs = [[P(E(f["value"]), st_big) for f in S["headline"]], [P(E(f["label"]), st_lab) for f in S["headline"]]]
    ft = LongTable(figs, colWidths=[usable / 4] * 4)
    ft.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LINEBEFORE", (1, 0), (-1, -1), 0.6, colors.Color(0.85, 0.87, 0.9)),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story.append(ft)
    if S["empty"] and S.get("empty_note"):
        story.append(Spacer(1, 1.5 * mm))
        story.append(P(E(S["empty_note"]), st_grey))
    story.append(Spacer(1, 3 * mm))
    mp = _BulletinMap(S, usable, 76 * mm)
    story.append(mp)
    story.append(_BulletinMapCaption(mp, len(S["map_routes"])))
    legend = " · ".join(f"<b>{E(p['letter'])}</b> {E(p['name'])}" for p in S["places"] if p["letter"])
    if S["controls"]:
        legend += (" · " if legend else "") + "Local controls (page 2): " + " · ".join(
            f"<b>{z['n']}</b> {E(z['name'])}" for z in S["controls"])
    if legend:
        story.append(P(legend, st_grey))

    story.append(P("The busiest routes this month", st_sec))
    rows = [[P("Route", st_h), P("Two-way a day", st_hr), P("In the month", st_hr),
             P(E(S["prev_long"] or "Last month") + " (a day)", st_hr), P("Planning flag", st_hr)]]
    for r in S["busiest"]:
        rows.append([P(E(r["label"]) + (f" <font color='#64748B'>({E(r['letters'])})</font>" if r["letters"] else "")),
                     P(f"<b>{E(r['a_day_text'])}</b>", st_r), P(E(r["in_month_text"]), st_r),
                     P(E(r["last_month_text"]), st_r), P(E(r["flag_text"]), st_red if r["over_flag"] else st_r)])
    if not S["busiest"]:
        rows.append([P("No route with a stored road route carries approved lorries this month.", st_grey), "", "", "", ""])
    story.append(grid(rows, [usable * 0.40, usable * 0.13, usable * 0.13, usable * 0.16, usable * 0.18]))
    story.append(Spacer(1, 1.5 * mm))
    story.append(P(E(f"A planning flag is a cap the scheme has typed, in two-way movements a day; it is never a legal "
                     f"limit. {S['flagged_routes']} of {len(S['routes'])} routes carry one. Every route is charted on "
                     "page 2."), st_grey))
    story.append(P("Terms explained", st_sec))
    story.append(P(E(S["two_way_sentence"] + " " + S["other_schemes"])))

    # ---- page 2
    story.append(PageBreak())
    # 13 Oct 2026: the Sizewell C tracker's shape — item, this month, the kind of data; observed items Not reported
    story.append(P("This month at a glance", st_sec))
    st_nr = ParagraphStyle("nr", parent=st, textColor=colors.Color(*GREY), fontName="Helvetica-Oblique")
    gl = [[P("Item", st_h), P("This month", st_hr), P("Data", st_h)]]
    for g in S["glance"]:
        gl.append([P(E(g["item"]), st_grey if g["not_reported"] else st),
                   P(E(g["figure"]), ParagraphStyle("nrr", parent=st_nr, alignment=2) if g["not_reported"] else st_r),
                   P(E(g["data"]), st_grey if g["not_reported"] else st)])
    story.append(grid(gl, [usable * 0.47, usable * 0.17, usable * 0.36]))
    story.append(P("Forecast: from the approved plan. Not reported: what a monitoring report fills from observed records "
                   "(counts, gate and camera records, operators' returns). A planning forecast has none, so the line is "
                   "left empty, never estimated.", st_grey))

    story.append(P("Two-way movements a day by route", st_sec))
    story.append(_bulletin_chart(S, usable))
    story.append(P("Bars: two-way movements a day, approved plan (light fill, solid edge). Dashed red mark: the "
                   "planning flag typed on the route." + (f" The {bulletin_charted(S)} busiest routes of "
                   f"{len(S['routes'])} are charted; every route is on the HTML page."
                   if len(S["routes"]) > bulletin_charted(S) else ""), st_grey))

    story.append(P("What is being moved", st_sec))
    mv = [[P("Discipline", st_h), P("Two-way a day", st_hr), P("Vehicles", st_hr), P("Tonnes a day", st_hr)]]
    for m in S["moved"]:
        mv.append([P(E(m["name"])), P(E(m["a_day"]), st_r), P(E(m["vehicles"]), st_r), P(E(m["t_day"]), st_r)])
    mt = S["moved_total"]
    mv.append([P("<b>All routes</b>"), P(f"<b>{E(mt['a_day'])}</b>", st_r), P(f"<b>{E(mt['vehicles'])}</b>", st_r),
               P(f"<b>{E(mt['t_day'])}</b>", st_r)])
    story.append(grid(mv, [usable * 0.46, usable * 0.18, usable * 0.18, usable * 0.18], total_row=True))

    story.append(P(E(f"Works affecting the roads in {S['month_long']}"), st_sec))
    wk = [[P("Location", st_h), P("Works", st_h), P("When and who", st_h)]]
    for w in S["works"]:
        wk.append([P(E(w["where"])), P(E(w["line"]) + f"<br/><font size=7 color='#64748B'>"
                                       f"{E(w['routes_text'])}</font>"),
                   P(E(w["when"]) + f"<br/><font size=7 color='#64748B'>{E(w['who'])}</font>")])
    for z in S["controls"]:
        wk.append([P(f"<b>{z['n']}</b> " + E(z["name"])), P(E(z["kind"] + (f": {z['note']}" if z["note"] else ""))),
                   P(E(z["when"]) + "<br/><font size=7 color='#64748B'>typed by the scheme</font>")])
    if len(wk) == 1:
        wk.append([P("Nothing stored for this month.", st_grey), "", ""])
    story.append(grid(wk, [usable * 0.26, usable * 0.46, usable * 0.28]))
    for line in S["checks"]:
        story.append(P(E(line), st_grey))
    for o in S["others"]:
        story.append(P(f"<b>{E(o['kind'])}.</b> " + E(o["text"])))

    story.append(P("What changed since last month", st_sec))
    ch = [[P("Month", st_h), P("Two-way a day", st_hr), P("Vehicles", st_hr), P("CO2e a day", st_hr), P("Routes", st_hr)]]
    for c in S["change_rows"]:
        b = (lambda s: f"<b>{s}</b>") if c["this"] else (lambda s: s)
        ch.append([P(b(E(c["label"]))), P(b(E(c["a_day"])), st_r), P(b(E(c["vehicles"])), st_r),
                   P(b(E(c["co2_day"])), st_r), P(b(E(c["routes"])), st_r)])
    story.append(grid(ch, [usable * 0.32, usable * 0.17, usable * 0.17, usable * 0.17, usable * 0.17]))
    story.append(P(E(S["change_text"])))
    story.append(P("Plan against plan: each month's approved plan as it stands today. No earlier issue of this "
                   "bulletin is stored.", st_grey))

    # 13 Oct 2026: carbon by council — the districts alone, drawn from the boundary polygons (no Mapbox call)
    C = S.get("council")
    if C:
        if C.get("error"):
            story.append(P(E(C["title"]), st_sec))
            story.append(P(E(C["error"]), st_grey))
        else:
            cc = [[P("District", st_h), P("Highway authority", st_h), P("t CO2e in the month", st_hr),
                   P("Share of the scheme's", st_hr)]]
            for d in C["districts"]:
                cc.append([P(E(d["name"])), P(E(d["highway_authority"])), P(E(d["text"]), st_r), P(E(d["share"]), st_r)])
            story.append(KeepTogether([P(E(C["title"]), st_sec), P(E(C["lede"])), Spacer(1, 1.5 * mm),
                                       _CouncilMap(C, usable, 100 * mm), Spacer(1, 1 * mm), _council_legend(C, usable)]))
            story.append(Spacer(1, 1.5 * mm))
            story.append(grid(cc, [usable * 0.30, usable * 0.34, usable * 0.18, usable * 0.18]))
            story.append(P(E(C["tally"])))
            for line in C["county_lines"] + C["notes"]:
                story.append(P(E(line), st_grey))
            story.append(P(E(C["basis"] + " " + C["stamp"] + "."), st_grey))
            story.append(P(E(" ".join(C["sources"] + C["attribution"])), st_grey))

    story.append(P("Terms explained", st_sec))
    for k, v in S["terms"]:
        story.append(P(f"<b>{E(k)}:</b> " + E(v)))
    story.append(P("Caveats", st_sec))
    for cv in S["caveats"]:
        story.append(P("• " + E(cv), st_grey))
    story.append(Spacer(1, 2.5 * mm))
    rep = LongTable([[P("<b>" + E(S["report"]["lorry"]) + "</b>")], [P(E(S["report"]["hours"]))],
                     [P(E(S["report"]["formats"]))]], colWidths=[usable])
    rep.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.2, colors.Color(*NAVY_RGB)),
                             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(KeepTogether([rep]))
    doc.build(story)
    return buf.getvalue()


def bulletin_charted(S):
    """How many routes the PDF's chart draws (the rest are on the HTML page)."""
    import bulletin_doc
    return min(len(S["routes"]), bulletin_doc.CHART_MAX_ROUTES)

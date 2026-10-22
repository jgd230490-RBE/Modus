"""
22 Oct 2026 (S16 / B5, abnormal loads, phase 3, D73): the abnormal loads' DOCUMENTS.

- The NOTICE CALENDAR across every movement the caller may see: an XLSX (one row a movement) and a PDF (A4 landscape,
  one table), sorted by the date the first notice must be received, then the apply-by date, then the window.
- One movement's ESDAL DETAILS SHEET (A4 portrait): the fields ESDAL and the notices ask for — the vehicle, the
  dimensions, the weights and axles, the load, from and to with the gates, the dates, the notices and permissions as
  advised, the references — laid out so the haulier copies them across into their own ESDAL application. Nothing here
  submits anything (D73): every line is advice from the typed figures, and the sheet says so.

Both carry the tenant's demo notice like every export. The words are the rules module's own, never new rules.
"""
import datetime
import io

import export
import abnormal
import abnormal_rules as rules

FLAG_WORDS = {"NOTICE_DUE": "Notice due", "NOTICE_LATE": "Notice late", "SO_LEAD_TIME": "Special Order lead time",
              "AIL_ROAD_LIMIT": "Over a signed limit"}
ESCORT_WORDS = {"none": "none planned", "attendant": "an attendant", "private": "a private escort", "police": "a police escort"}
CALENDAR_HEAD = ["Load", "Team", "From → to", "Window", "Band", "Movements", "Size (W × H × L m · t)", "Class", "Permission",
                 "Apply by", "Applied on", "Police notice by", "Authorities notice by", "Notify by", "Notified on", "Status",
                 "Flags", "ESDAL ref", "VR1 ref", "Special Order ref", "Escort planned", "Route drawn", "Potential pinch points"]
SHEET_WORDS = ("This sheet lists what the haulier types into ESDAL and gives the notices as Wayscope advises them from the "
               "typed figures. It is not an application and nothing has been sent: the haulier's ESDAL route and route "
               "survey govern; ESDAL, the police and the road and bridge authorities decide.")
FAR = "9999-12-31"
PERMISSION_WORDS = {"special_order": "Special Order (BE16)", "vr1": "VR1 (National Highways)"}


def _permission_words(adv):
    """The permission in words: the rules' lead words when there are any, else the key's words, else 'none beyond the notices'."""
    if adv.get("lead_words"):
        return adv["lead_words"]
    return PERMISSION_WORDS.get(adv.get("permission") or "", "none beyond the notices")


def _nw(x):
    v = rules._num(x)
    if v is None:
        return "—"
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _day(iso):
    d = rules._date(iso)
    return f"{d.day} {d.strftime('%b %Y')}" if d else "—"


def _window(m):
    a, b = rules._date(m.get("date_from")), rules._date(m.get("date_to"))
    if not a:
        return "—"
    if not b or b == a:
        return _day(a.isoformat())
    if a.year == b.year and a.month == b.month:
        return f"{a.day}–{b.day} {b.strftime('%b %Y')}"
    if a.year == b.year:
        return f"{a.day} {a.strftime('%b')} – {b.day} {b.strftime('%b %Y')}"
    return f"{_day(a.isoformat())} – {_day(b.isoformat())}"


def _size(m):
    return f"{_nw(m.get('width_m'))} × {_nw(m.get('height_m'))} × {_nw(m.get('length_m'))} m · {_nw(m.get('gross_t'))} t"


def _from_to(m):
    o = (m.get("origin_name") or "—") + (f" ({m['origin_gate_name']})" if m.get("origin_gate_name") else "")
    d = (m.get("dest_name") or "—") + (f" ({m['dest_gate_name']})" if m.get("dest_gate_name") else "")
    return f"{o} → {d}"


def _generated(generated=None):
    return generated or datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# --------------------------------------------------------------------------- #
#  The notice calendar                                                         #
# --------------------------------------------------------------------------- #
def calendar(acc, today=None, generated=None):
    """Everything the calendar prints, as data: one row a movement (withdrawn ones left out), the words, the holidays."""
    today_d = rules._date(today) or datetime.date.today()
    pg = abnormal.page(acc, today=today_d)
    rows = []
    for m in pg["movements"]:
        if m.get("status") == "withdrawn":
            continue
        adv = m.get("advice") or {}
        nt = adv.get("notices") or {}
        rows.append({
            "id": m["id"], "name": m.get("name"), "team": m.get("team_name"), "from_to": _from_to(m),
            "window": _window(m), "date_from": m.get("date_from"), "date_to": m.get("date_to"),
            "band": m.get("time_band") or "day", "movements": m.get("movements"), "return_abnormal": bool(m.get("return_abnormal")),
            "size": _size(m), "status": m.get("status_word") or m.get("status"), "status_key": m.get("status"),
            "class": adv.get("category_words") or adv.get("summary"), "summary": adv.get("summary"),
            "permission": _permission_words(adv), "permission_key": adv.get("permission"), "lead": adv.get("lead_words"),
            "apply_by": adv.get("apply_by"), "apply_by_be16": adv.get("apply_by_be16"), "applied_on": m.get("applied_on"),
            "police_days": nt.get("police_days"), "police_by": nt.get("police_by"),
            "rba_days": nt.get("rba_days"), "rba_by": nt.get("rba_by"), "rba_indemnity": bool(nt.get("rba_indemnity")),
            "notify_by": adv.get("notify_by"), "notified_on": m.get("notified_on"), "calendar": adv.get("calendar_words"),
            "escort": ESCORT_WORDS.get(m.get("escort_planned") or "none", m.get("escort_planned")),
            "escort_expected": adv.get("escort_expected"), "attendant": bool(adv.get("attendant")),
            "esdal_ref": m.get("esdal_ref"), "vr1_ref": m.get("vr1_ref"), "so_ref": m.get("so_ref"),
            "flags": [FLAG_WORDS.get(f.get("code"), f.get("code")) for f in (m.get("flags") or [])],
            "flag_text": [f.get("text") for f in (m.get("flags") or [])],
            "routed": bool(m.get("routed")), "distance_km": m.get("distance_km"),
            "candidates": len(m.get("candidates") or []) + len(m.get("typed_points") or []),
        })
    rows.sort(key=lambda r: (r["notify_by"] or FAR, r["apply_by"] or FAR, r["date_from"] or FAR, r["id"]))
    settings = pg.get("settings") or {}
    hol = settings.get("holidays") or {}
    hol_words = ("GOV.UK bank holidays (Open Government Licence), " + (f"fetched {str(hol.get('fetched_at'))[:10]}" if hol.get("source") == "fetched" else f"the shipped copy of {hol.get('seed_fetched_on')}")
                 + (f"; dates to {hol.get('to')}" if hol.get("to") else ""))
    return {"rows": rows, "count": len(rows), "today": today_d.isoformat(), "generated": _generated(generated),
            "tenant": export._tenant().get("name") or "", "demo_notice": export._demo_notice(),
            "holidays": hol_words, "nation": settings.get("nation"),
            "words": {"advice": rules.ADVICE_WORDS, "not_modelled": rules.NOT_MODELLED_WORDS,
                      "counted_apart": (pg.get("words") or {}).get("counted_apart"),
                      "sorted": "Sorted by the date the first notice must be received, then the date to apply by, then the window."}}


def calendar_file_name(C, ext):
    return f"abnormal-loads-notice-calendar-{C['today']}.{ext}"


def _flag_words(r):
    return "; ".join(r["flags"]) if r["flags"] else ""


def _police_words(r):
    if not r.get("police_by"):
        return "—"
    return f"{_day(r['police_by'])} ({r['police_days']} clear working days)"


def _rba_words(r):
    if not r.get("rba_by"):
        return "—"
    return f"{_day(r['rba_by'])} ({r['rba_days']} days{', with the indemnity' if r.get('rba_indemnity') else ''})"


def _apply_words(r):
    if not r.get("apply_by"):
        return "—"
    s = _day(r["apply_by"])
    if r.get("apply_by_be16") and r["apply_by_be16"] != r["apply_by"]:
        s += f" (the BE16 form says {_day(r['apply_by_be16'])})"
    return s


def build_calendar_xlsx(C):
    """The calendar as an XLSX: the rows on one sheet, About on a second."""
    if export.openpyxl is None:
        raise RuntimeError("openpyxl is not installed: " + export.MISSING.get("xlsx", ""))
    Font, PatternFill = export.Font, export.PatternFill
    wb = export.openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notice calendar"
    r = 1
    if C.get("demo_notice"):
        cv = ws.cell(row=r, column=1, value=C["demo_notice"])
        cv.font = Font(bold=True, color=export.DEMO_FG_HEX)
        cv.fill = PatternFill("solid", fgColor=export.DEMO_BG_HEX)
        r += 1
    ws.cell(row=r, column=1, value=f"Abnormal loads — notice calendar · {C['tenant']} · as at {C['today']}").font = Font(bold=True, size=12)
    r += 1
    ws.cell(row=r, column=1, value=C["words"]["sorted"] + " " + C["words"]["advice"])
    r += 2
    for j, h in enumerate(CALENDAR_HEAD, 1):
        ws.cell(row=r, column=j, value=h).font = Font(bold=True)
    ws.freeze_panes = ws.cell(row=r + 1, column=2)
    r += 1
    for row in C["rows"]:
        vals = [f"{row['id']} · {row['name']}", row["team"], row["from_to"], row["window"], row["band"],
                f"{row['movements']}{' (in and out)' if row['return_abnormal'] else ''}", row["size"], row["class"],
                row["permission"],
                row["apply_by"] or "", row["applied_on"] or "", row["police_by"] or "", row["rba_by"] or "",
                row["notify_by"] or "", row["notified_on"] or "", row["status"], _flag_words(row),
                row["esdal_ref"] or "", row["vr1_ref"] or "", row["so_ref"] or "", row["escort"],
                (f"{row['distance_km']:g} km" if row["routed"] and row.get("distance_km") is not None else "not drawn"),
                row["candidates"]]
        for j, v in enumerate(vals, 1):
            ws.cell(row=r, column=j, value=v)
        r += 1
    widths = [34, 16, 44, 20, 7, 12, 22, 24, 40, 12, 12, 16, 20, 12, 12, 11, 30, 14, 12, 16, 16, 12, 10]
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[export.openpyxl.utils.get_column_letter(j)].width = w
    ab = wb.create_sheet("About")
    lines = [("Document", "Abnormal loads — notice calendar"), ("Scheme", C["tenant"]), ("As at", C["today"]),
             ("Generated", C["generated"]), ("Movements", C["count"]), ("Bank holidays", C["holidays"]),
             ("Nation", C.get("nation") or "england-and-wales"), ("Sorting", C["words"]["sorted"]),
             ("Advice", C["words"]["advice"]), ("Not worked out", C["words"]["not_modelled"]),
             ("Counted apart", C["words"]["counted_apart"] or "")]
    for i, (k, v) in enumerate(lines, 1):
        ab.cell(row=i, column=1, value=k).font = Font(bold=True)
        ab.cell(row=i, column=2, value=v)
    ab.column_dimensions["A"].width = 18
    ab.column_dimensions["B"].width = 120
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  PDF plumbing shared by both documents                                       #
# --------------------------------------------------------------------------- #
class _Page:
    """A canvas with a cursor that starts a new page when the next block will not fit, repeating the header."""

    def __init__(self, c, W, H, margin, header, footer):
        self.c, self.W, self.H, self.m = c, W, H, margin
        self.header, self.footer, self.n = header, footer, 0
        self.y = H
        self.new_page()

    def new_page(self):
        if self.n:
            self.footer(self.c, self.n)
            self.c.showPage()
        self.n += 1
        self.y = self.H - self.m
        self.y = self.header(self.c, self.y, self.n)

    def need(self, h):
        if self.y - h < self.m + 22:
            self.new_page()

    def text(self, s, font, size, colour, width, gap=2.5, indent=0):
        """A wrapped paragraph; returns the lines drawn."""
        lines = export._wrap(s, font, size, width - indent)
        self.need(len(lines) * (size + gap))
        self.c.setFillColorRGB(*colour)
        self.c.setFont(font, size)
        for ln in lines:
            self.y -= size + gap
            self.c.drawString(self.m + indent, self.y, ln)
        return len(lines)

    def finish(self):
        self.footer(self.c, self.n)
        self.c.showPage()
        self.c.save()


def _table(P, widths, head, rows, size=7.4, gap=2.2, head_size=7.6):
    """A wrapped table that continues on the next page with its header; `rows` are lists of strings."""
    R, B = export._BF("regular"), export._BF("bold")
    c = P.c

    def draw_head():
        x = P.m
        c.setFillColorRGB(*export.NAVY_RGB)
        c.setFont(B, head_size)
        P.y -= head_size + 3
        for w, h in zip(widths, head):
            for i, ln in enumerate(export._wrap(h, B, head_size, w - 4)[:2]):
                c.drawString(x + 2, P.y - i * (head_size + 1), ln)
            x += w
        P.y -= head_size + 3
        c.setStrokeColorRGB(*export.GREY)
        c.setLineWidth(0.5)
        c.line(P.m, P.y + 2, P.m + sum(widths), P.y + 2)

    P.need(2 * (head_size + 3) + 20)
    draw_head()
    for row in rows:
        cells = [export._wrap(str(v if v is not None else ""), R, size, w - 4) for v, w in zip(row, widths)]
        h = max(len(cl) for cl in cells) * (size + gap) + 4
        if P.y - h < P.m + 22:
            P.new_page()
            draw_head()
        x = P.m
        c.setFillColorRGB(*export.NAVY_RGB)
        c.setFont(R, size)
        for cl, w in zip(cells, widths):
            for i, ln in enumerate(cl):
                c.drawString(x + 2, P.y - (i + 1) * (size + gap) + gap, ln)
            x += w
        P.y -= h
        c.setStrokeColorRGB(0.85, 0.87, 0.9)
        c.setLineWidth(0.3)
        c.line(P.m, P.y + 2, P.m + sum(widths), P.y + 2)


def _header_block(title, sub, C):
    """The header every page of a document repeats: the title, the tenant, the demo notice, a sub line."""
    def header(c, y, n):
        R, B = export._BF("regular"), export._BF("bold")
        W = c._pagesize[0]
        m = 12 * export.mm
        c.setFillColorRGB(*export.NAVY_RGB)
        c.setFont(B, 15 if n == 1 else 11)
        c.drawString(m, y - (15 if n == 1 else 11), export._pdf_safe(title))
        c.setFont(B, 8.5)
        c.drawRightString(W - m, y - 9, export._pdf_safe(C.get("tenant") or ""))
        c.setFillColorRGB(*export.GREY)
        c.setFont(R, 7.6)
        c.drawRightString(W - m, y - 19, export._pdf_safe(f"Generated {C['generated']}" + (f" · page {n}" if n > 1 else "")))
        if C.get("demo_notice"):
            c.setFillColorRGB(*export.DEMO_FG_RGB)
            c.setFont(B, 8)
            c.drawRightString(W - m, y - 29, export._pdf_safe("DEMO · " + C["demo_notice"]))
        y -= (22 if n == 1 else 16)
        if sub and n == 1:
            for ln in export._wrap(sub, R, 8.2, W - 2 * m - 150):
                c.setFillColorRGB(*export.GREY)
                c.setFont(R, 8.2)
                c.drawString(m, y - 8.2, ln)
                y -= 10.5
        return y - 6
    return header


def _footer_block(C, words):
    def footer(c, n):
        R = export._BF("regular")
        W = c._pagesize[0]
        m = 12 * export.mm
        c.setFillColorRGB(*export.GREY)
        c.setFont(R, 6.8)
        y = m - 4
        for ln in reversed(export._wrap(words, R, 6.8, W - 2 * m)):
            c.drawString(m, y, ln)
            y += 8.2
    return footer


def build_calendar_pdf(C):
    """The calendar as an A4 landscape PDF: one table, continued over pages, the words under it."""
    if export.rl_canvas is None:
        raise RuntimeError("reportlab is not installed: " + export.MISSING.get("pdf", ""))
    W, H = export.landscape(export.A4)
    buf = io.BytesIO()
    c = export.rl_canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle("Abnormal loads — notice calendar")
    m = 12 * export.mm
    sub = (f"{C['count']} abnormal load{'s' if C['count'] != 1 else ''} as at {_day(C['today'])}. " + C["words"]["sorted"]
           + f" Bank holidays: {C['holidays']}.")
    P = _Page(c, W, H, m, _header_block("Abnormal loads — notice calendar", sub, C),
              _footer_block(C, C["words"]["advice"] + " " + (C["words"]["counted_apart"] or "")))
    mm_ = export.mm
    widths = [w * mm_ for w in (44, 46, 30, 42, 22, 24, 26, 20, 23)]
    head = ["Load", "From → to", "Window · band · movements", "Class · permission", "Apply by", "Police notice by",
            "Authorities notice by", "Notify by", "Status · flags"]
    rows = []
    for r in C["rows"]:
        rows.append([f"{r['id']} · {r['name']}\n{r['size']} · {r['team'] or ''}", r["from_to"],
                     f"{r['window']} · {r['band']} · {r['movements']} movement{'s' if r['movements'] != 1 else ''}{' (in and out)' if r['return_abnormal'] else ''}",
                     (r["class"] or "") + (f" · {r['permission']}" if r.get("permission_key") else ""),
                     _apply_words(r) + (f"\napplied {_day(r['applied_on'])}" if r.get("applied_on") else ""),
                     _police_words(r), _rba_words(r),
                     (_day(r["notify_by"]) if r.get("notify_by") else "—") + (f"\n{r['calendar']}" if r.get("calendar") else "")
                     + (f"\nnotified {_day(r['notified_on'])}" if r.get("notified_on") else ""),
                     r["status"] + (f"\n{_flag_words(r)}" if r["flags"] else "")])
    if rows:
        _table(P, widths, head, [[str(v).replace("\n", " — ") for v in row] for row in rows])
    else:
        P.text("No abnormal load is planned.", export._BF("regular"), 9, export.GREY, W - 2 * m)
    P.y -= 8
    P.text(C["words"]["not_modelled"], export._BF("regular"), 7.4, export.GREY, W - 2 * m)
    P.finish()
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  The ESDAL details sheet                                                     #
# --------------------------------------------------------------------------- #
def esdal_sheet(movement_id, acc, today=None, generated=None):
    """Everything one sheet prints, as data; None when the caller may not see the movement."""
    row = abnormal.get(movement_id)
    if not row or not abnormal._visible(row, acc):
        return None
    pg = abnormal.page(acc, today=rules._date(today) or datetime.date.today())
    m = next((x for x in pg["movements"] if x["id"] == movement_id), None)
    if not m:
        return None
    adv = m.get("advice") or {}
    nt = adv.get("notices") or {}
    via = []
    try:
        import abnormal_route
        via = abnormal_route.via_points(m)
    except Exception:       # noqa: BLE001
        via = []
    S = {
        "movement": m, "id": m["id"], "name": m.get("name"), "team": m.get("team_name"), "status": m.get("status_word") or m.get("status"),
        "generated": _generated(generated), "tenant": export._tenant().get("name") or "", "demo_notice": export._demo_notice(),
        "vehicle": m.get("vehicle_word") or rules.VEHICLE_WORDS.get(m.get("vehicle_type") or "", m.get("vehicle_type") or "—"),
        "fill_in": [("Haulier", ""), ("Contact", ""), ("Vehicle registration", ""), ("ESDAL movement reference", m.get("esdal_ref") or "")],
        "load": [("Load", m.get("name")), ("Indivisible", "declared" if m.get("indivisible") else "not declared — say so if it is"),
                 ("Movements", f"{m.get('movements')}{' (the return abnormal too)' if m.get('return_abnormal') else ''}"),
                 ("Window", _window(m)), ("Time band", (m.get("time_band") or "day") + " " + "–".join(rules.TIME_BANDS.get(m.get("time_band") or "day", ()))),
                 ("Vehicle type", None)],
        "dims": [("Overall length", f"{_nw(m.get('length_m'))} m"), ("Rigid length", f"{_nw(m.get('rigid_length_m'))} m"),
                 ("Overall width", f"{_nw(m.get('width_m'))} m"), ("Travelling height", f"{_nw(m.get('height_m'))} m"),
                 ("Projection, front", f"{_nw(m.get('proj_front_m'))} m"), ("Projection, rear", f"{_nw(m.get('proj_rear_m'))} m"),
                 ("Projection, side", f"{_nw(m.get('proj_side_m'))} m")],
        "weights": [("Gross weight", f"{_nw(m.get('gross_t'))} t"), ("Heaviest axle", f"{_nw(m.get('max_axle_t'))} t" + (" (a driving axle)" if m.get("axle_driving") else "")),
                    ("Axles", _nw(m.get("axle_count"))), ("Axle spacings", m.get("axle_spacings_m") or "not typed"),
                    ("C&U vehicle", "yes" if m.get("cu_vehicle") else "no")],
        "route": [("From", (m.get("origin_name") or "—") + (f", {m['origin_gate_name']}" if m.get("origin_gate_name") else "")),
                  ("To", (m.get("dest_name") or "—") + (f", {m['dest_gate_name']}" if m.get("dest_gate_name") else "")),
                  ("Via points", "; ".join(f"{p[0]:.5f}, {p[1]:.5f}" for p in via) if via else "none"),
                  ("Roads (indicative)", m.get("roads_words") or ("not drawn yet" if not m.get("routed") else "—")),
                  ("Distance", f"{m['distance_km']:g} km" if m.get("routed") and m.get("distance_km") is not None else "—")],
        "notices": [("Class", adv.get("category_words") or adv.get("summary") or "—"),
                    ("Permission", _permission_words(adv)),
                    ("Apply by", _apply_words({"apply_by": adv.get("apply_by"), "apply_by_be16": adv.get("apply_by_be16")}) if adv.get("apply_by") else "—"),
                    ("Police notice", _police_words({"police_by": nt.get("police_by"), "police_days": nt.get("police_days")})
                     + (f"; {', '.join(nt.get('police_triggers') or [])}" if nt.get("police_triggers") else "")),
                    ("Road and bridge authorities", _rba_words({"rba_by": nt.get("rba_by"), "rba_days": nt.get("rba_days"), "rba_indemnity": nt.get("rba_indemnity")})),
                    ("Notify by", (_day(adv["notify_by"]) + (f" — {adv['calendar_words']}" if adv.get("calendar_words") else "")) if adv.get("notify_by") else "—"),
                    ("Attendant", "required" if adv.get("attendant") else "not required by the figures"),
                    ("Escort", f"{adv.get('escort_expected') or 'none'} expected; planned: {ESCORT_WORDS.get(m.get('escort_planned') or 'none', m.get('escort_planned'))}"),
                    ("Markers and speeds", ", ".join(adv.get("markers") or []) + (f"; {', '.join(str(x) for x in adv['speeds_mph'])} mph" if adv.get("speeds_mph") else "")),
                    ("Height", adv.get("height") or "—")],
        "refs": [("ESDAL", m.get("esdal_ref") or "—"), ("VR1", m.get("vr1_ref") or "—"), ("Special Order", m.get("so_ref") or "—"),
                 ("Applied on", _day(m["applied_on"]) if m.get("applied_on") else "—"), ("Notified on", _day(m["notified_on"]) if m.get("notified_on") else "—")],
        "lines": list(adv.get("lines") or []), "notes": list(adv.get("notes") or []),
        "flags": [f"{FLAG_WORDS.get(f.get('code'), f.get('code'))}: {f.get('text')}" for f in (m.get("flags") or [])],
        "pinch": [f"{c.get('id')} · {c.get('words')} — {abnormal_route_grade(c)}" for c in (m.get("candidates") or [])]
                 + [f"{t.get('id')} · {t.get('place') or ''}{': ' if t.get('place') and t.get('words') else ''}{t.get('words') or ''} — {abnormal_route_grade(t)} (the planner's own)" for t in (m.get("typed_points") or [])],
        "route_words": m.get("route_words"), "route_notes": list(m.get("route_notes") or []),
        "words": {"sheet": SHEET_WORDS, "advice": rules.ADVICE_WORDS, "not_modelled": rules.NOT_MODELLED_WORDS,
                  "counted_apart": (pg.get("words") or {}).get("counted_apart")},
    }
    S["load"][-1] = ("Vehicle type", S["vehicle"])
    return S


def abnormal_route_grade(c):
    try:
        import abnormal_route
        return abnormal_route.GRADE_WORDS.get(c.get("grade") or "grey", c.get("grade") or "grey")
    except Exception:       # noqa: BLE001
        return c.get("grade") or "grey"


def esdal_file_name(S):
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(S["id"]))
    return f"esdal-details-{safe}.pdf"


def build_esdal_pdf(S):
    """The ESDAL details sheet as an A4 portrait PDF, more pages when the pinch-point list needs them."""
    if export.rl_canvas is None:
        raise RuntimeError("reportlab is not installed: " + export.MISSING.get("pdf", ""))
    W, H = export.A4
    buf = io.BytesIO()
    c = export.rl_canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"ESDAL details sheet — {S['id']}")
    m = 12 * export.mm
    cw = W - 2 * m
    R, B = export._BF("regular"), export._BF("bold")
    sub = f"{S['id']} · {S['name']} · {S['team'] or ''} · {S['status']}. " + S["words"]["sheet"]
    P = _Page(c, W, H, m, _header_block("ESDAL details sheet", sub, S),
              _footer_block(S, S["words"]["advice"] + " " + (S["words"]["counted_apart"] or "")))

    def section(title, pairs, cols=2):
        P.need(22)
        P.y -= 8
        c.setFillColorRGB(*export.NAVY_RGB)
        c.setFont(B, 9.6)
        P.y -= 9.6
        c.drawString(m, P.y, export._pdf_safe(title))
        P.y -= 3
        colw = cw / cols
        i = 0
        while i < len(pairs):
            group = pairs[i:i + cols]
            cells = [(k, export._wrap(str(v if v is not None else "") or "____________________", R, 8.2, colw - 92)) for k, v in group]
            h = max(len(v) for _, v in cells) * 10.4 + 4
            P.need(h)
            x = m
            for k, lines in cells:
                c.setFillColorRGB(*export.GREY)
                c.setFont(R, 7.6)
                c.drawString(x, P.y - 9, export._pdf_safe(k))
                c.setFillColorRGB(*export.NAVY_RGB)
                c.setFont(R, 8.2)
                for j, ln in enumerate(lines):
                    c.drawString(x + 88, P.y - 9 - j * 10.4, ln)
                x += colw
            P.y -= h
            i += cols

    section("For the haulier to fill in", S["fill_in"])
    section("The load", S["load"])
    section("Dimensions (metres)", S["dims"])
    section("Weights and axles", S["weights"])
    section("The route", S["route"], cols=1)
    if S.get("route_words"):
        P.text(S["route_words"], R, 7.4, export.GREY, cw)
    for n in S.get("route_notes") or []:
        P.text("Note: " + n, R, 7.4, export.GREY, cw)
    section("Notices and permissions, as Wayscope advises them", S["notices"], cols=1)
    for ln in S["lines"]:
        P.text("• " + ln, R, 7.8, export.NAVY_RGB, cw, indent=4)
    for n in S["notes"]:
        P.text("• " + n, R, 7.8, export.NAVY_RGB, cw, indent=4)
    for f in S["flags"]:
        P.text("! " + f, B, 7.8, export.DEMO_FG_RGB, cw, indent=4)
    section("References", S["refs"])
    P.y -= 8
    P.need(20)
    c.setFillColorRGB(*export.NAVY_RGB)
    c.setFont(B, 9.6)
    P.y -= 9.6
    c.drawString(m, P.y, export._pdf_safe(f"Potential pinch points ({len(S['pinch'])})"))
    P.y -= 3
    if S["pinch"]:
        for p_ in S["pinch"]:
            P.text(p_, R, 7.6, export.NAVY_RGB, cw, indent=4)
    else:
        P.text("None found yet: draw the route on Plan → Abnormal loads.", R, 7.6, export.GREY, cw, indent=4)
    P.y -= 6
    P.text(S["words"]["not_modelled"], R, 7.2, export.GREY, cw)
    P.finish()
    return buf.getvalue()

"""
22 Oct 2026 (S16 / B5, abnormal loads, phase 3, D73): the abnormal loads' DOCUMENTS.

- The NOTICE CALENDAR across every movement the caller may see: an XLSX (one row a movement) and a PDF (A4 landscape,
  one table), sorted by the date the first notice must be received, then the apply-by date, then the window.
- 27 Oct 2026 (the final UI pass; the user: the haulier plans and applies in their own software, Wayscope forecasts the
  load and tracks the notices): the ESDAL DETAILS SHEET of 22 Oct is GONE. The references the haulier gives back (ESDAL,
  VR1, Special Order) stay on the load and in the calendar; nothing here submits anything (D73).

The calendar carries the tenant's demo notice like every export. The words are the rules module's own, never new rules.
"""
import datetime
import io

import export
import abnormal
import abnormal_rules as rules

FLAG_WORDS = {"NOTICE_DUE": "Notice due", "NOTICE_LATE": "Notice late", "SO_LEAD_TIME": "Special Order lead time",
              "AIL_ROAD_LIMIT": "Over a signed limit"}
ESCORT_WORDS = {"none": "none planned", "attendant": "an attendant", "private": "a private escort", "police": "a police escort"}
ESCORT_EXPECTED_WORDS = {"none": "none expected from the figures",
                         "other_roads": "expected on roads other than motorways (National Highways' code of practice)",
                         "motorways": "expected on motorways (National Highways' code of practice)",
                         "all_roads": "expected on every road (National Highways' code of practice)"}
CAL_SHORT = {"stgo": "STGO clear working days", "cu": "C&U working days", "calendar": "calendar days"}
CALENDAR_HEAD = ["Load", "Team", "From → to", "Window", "Band", "Movements", "Size (W × H × L m · t)", "Class", "Permission",
                 "Apply by", "Applied on", "Police notice by", "Authorities notice by", "Notify by", "Notified on", "Status",
                 "Flags", "ESDAL ref", "VR1 ref", "Special Order ref", "Escort planned", "Route drawn", "Potential pinch points"]
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
            "calendar_key": adv.get("calendar"),
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
        wrapped = [export._wrap(h, B, head_size, w - 4)[:2] for w, h in zip(widths, head)]
        nl = max(len(w_) for w_ in wrapped) or 1
        top = P.y - 3
        for w, lines in zip(widths, wrapped):
            for i, ln in enumerate(lines):
                c.drawString(x + 2, top - (i + 1) * (head_size + 1.5), ln)
            x += w
        P.y = top - nl * (head_size + 1.5) - 4
        c.setStrokeColorRGB(*export.GREY)
        c.setLineWidth(0.5)
        c.line(P.m, P.y + 2, P.m + sum(widths), P.y + 2)

    P.need(3 * (head_size + 1.5) + 24)
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
    widths = [w * mm_ for w in (40, 42, 30, 42, 22, 24, 26, 24, 23)]      # 273 mm: the page less the margins
    head = ["Load", "From and to", "Window · band · movements", "Class · permission", "Apply by", "Police notice by",
            "Authorities notice by", "Notify by", "Status · flags"]
    used_cals = []
    rows = []
    for r in C["rows"]:
        rows.append([f"{r['id']} · {r['name']}\n{r['size']} · {r['team'] or ''}", r["from_to"],
                     f"{r['window']} · {r['band']} · {r['movements']} movement{'s' if r['movements'] != 1 else ''}{' (in and out)' if r['return_abnormal'] else ''}",
                     (r["class"] or "") + (f" · {r['permission']}" if r.get("permission_key") else ""),
                     _apply_words(r) + (f"\napplied {_day(r['applied_on'])}" if r.get("applied_on") else ""),
                     _police_words(r), _rba_words(r),
                     (_day(r["notify_by"]) if r.get("notify_by") else "—") + (f" ({CAL_SHORT[r['calendar_key']]})" if r.get("calendar_key") in CAL_SHORT else "")
                     + (f"\nnotified {_day(r['notified_on'])}" if r.get("notified_on") else ""),
                     r["status"] + (f"\n{_flag_words(r)}" if r["flags"] else "")])
    for r in C["rows"]:
        if r.get("calendar_key") in CAL_SHORT and r["calendar_key"] not in used_cals:
            used_cals.append(r["calendar_key"])
    if rows:
        _table(P, widths, head, [[str(v).replace("\n", " — ") for v in row] for row in rows])
    else:
        P.text("No abnormal load is planned.", export._BF("regular"), 9, export.GREY, W - 2 * m)
    P.y -= 8
    if used_cals:
        P.text("The calendars: " + " · ".join(rules.CALENDAR_WORDS[k] for k in used_cals) + ".", export._BF("regular"), 7.4, export.GREY, W - 2 * m)
        P.y -= 4
    P.text(C["words"]["not_modelled"], export._BF("regular"), 7.4, export.GREY, W - 2 * m)
    P.finish()
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  The ESDAL details sheet                                                     #
# --------------------------------------------------------------------------- #

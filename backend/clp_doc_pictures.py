"""
clp_doc_pictures.py — the CLP document's pictures: three charts and the three plans.
Wayscope, 30 Oct 2026 (task 4a, PR 2). Plan: notes/session-1030-clp-document.md §4–§5 (not in git).

CHARTS (the CLOCS tool's three, from clp_doc.gather's figures; no figure is worked out here)
  * programme      one bar a stage from its first to its last month with approved loads, a mark at its busiest month (§3)
  * monthly        trips a month stacked by stage; the right-hand scale is the same bars ÷ working days ("a day") (§6)
  * hourly         one chart a gate: the plan's arrivals in each open hour of the site's busiest month (§6)
Drawn with reportlab on a one-page PDF and rasterised with pypdfium2 (no matplotlib), PNG at 200 dpi.

PLANS (route_map_export's three, CLOCS outline CLP template §2.2 / §4)
  * one Regional plan of every route in this CLP, in the CLP's busiest month (fitted, 1:20,000 or smaller);
  * per site a Local plan (1:2,500) and a Site plan (1:1,000), centred on the site, in the Streets style (the Light
    style is nearly blank at those scales, notes/session-1030-clp-document.md §11), in that site's busiest month.
The plan's PDF page → JPEG straight from the rasterised page (31 Oct 2026: at PLAN_DPI, not the 2,560 px of the
route map export's PNG, and never through a PNG: less to hold while a plan is drawn).
A plan whose basemap did not come is drawn on its plain background (export's own fallback) and the caller is told
(basemap.MISSES), so a copy without the map is never kept in the read cache.
"""
import io
import math

import brand_pdf

#: the stage colours: the print palette's slots (clp_pack.SLOTS), then three more for stages 6–8
STAGE_COLOURS = ("#E8590C", "#2563EB", "#0D9488", "#7C3AED", "#A07D34", "#DB2777", "#64748B", "#65A30D")
INK, GRID, MUTED, BAND = "#1E293B", "#E2E8F0", "#5B6470", "#F1F5F9"
CHART_W_MM = 170.0
DPI = 200
JPEG_QUALITY = 85
#: 31 Oct 2026: the plans' raster. The frame is 285 mm wide and Word shows it about 170 mm wide, so 150 dpi here is
#: about 250 dpi on the page — sharp in print — at 0.43 times the pixels (and memory) of the export's 228 dpi.
PLAN_DPI = 150


def _rgb(hx):
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _nice_top(v, steps=4):
    if v <= 0:
        return steps
    raw = v / steps
    mag = 10 ** math.floor(math.log10(raw))
    for k in (1, 2, 2.5, 5, 10):
        if raw <= k * mag:
            return k * mag * steps
    return 10 * mag * steps


def day_ticks(top, wd):
    """The right-hand scale's ticks in trips a day: round steps from 0 up to the month scale's top ÷ working days."""
    if not wd or top <= 0:
        return [0]
    step = _nice_top(top / wd) / 4
    out, v = [], 0.0
    while v * wd <= top + 1e-9:
        out.append(round(v, 6))
        v += step
    return out


def _fmt(v):
    return f"{v:,.0f}" if abs(v) >= 10 or float(v).is_integer() else f"{v:,.1f}"


def _png(draw, w_mm, h_mm, dpi=DPI):
    """draw(c, F, w, h) on a one-page PDF of w_mm × h_mm, rasterised to PNG bytes (the DPI written into the file)."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    import pypdfium2 as pdfium
    buf = io.BytesIO()
    W, H = w_mm * mm, h_mm * mm
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    draw(c, brand_pdf.fonts(), W, H)
    c.showPage()
    c.save()
    pdf = pdfium.PdfDocument(buf.getvalue())
    try:
        page = pdf[0]
        img = page.render(scale=dpi / 72.0).to_pil().convert("RGB")
        page.close()
    finally:
        pdf.close()
    out = io.BytesIO()
    img.save(out, "PNG", dpi=(dpi, dpi))
    return out.getvalue()


def _months_axis(c, F, x0, x1, y, months, label):
    """Month ticks along y: a label every k-th month so none overlap; year boundaries carry the year."""
    from reportlab.lib.units import mm
    n = len(months)
    if not n:
        return
    step = (x1 - x0) / n
    c.setFont(F["regular"], 6.5)
    every = max(1, math.ceil(c.stringWidth("Mmm 00", F["regular"], 6.5) * 1.3 / step))
    for i, m in enumerate(months):
        if i % every:
            continue
        c.setFillColorRGB(*_rgb(MUTED))
        c.drawCentredString(x0 + (i + 0.5) * step, y - 3.2 * mm, label(m))


def programme_chart(data):
    """§3: a bar per stage with loads, first to last month; a dark mark at its busiest month. None when no stage has any."""
    from reportlab.lib.units import mm
    import clp_doc
    st = [s for s in data["stages"] if s["first"]]
    T = data["totals"]
    if not st or not T["first"]:
        return None
    months = list(range(T["first"], T["last"] + 1))
    row_h = 7.0
    h_mm = 16 + row_h * len(st)

    def draw(c, F, W, H):
        x0, x1 = 58 * mm, W - 4 * mm
        top = H - 4 * mm
        step = (x1 - x0) / len(months)
        for i, m in enumerate(months):                       # year boundaries
            if clp_doc.month_label(m).startswith("Jan") or i == 0:
                c.setStrokeColorRGB(*_rgb(GRID)); c.setLineWidth(0.5)
                c.line(x0 + i * step, 9 * mm, x0 + i * step, top)
        for j, s in enumerate(st):
            y = top - (j + 1) * row_h * mm + 1.5 * mm
            c.setFillColorRGB(*_rgb(INK)); c.setFont(F["regular"], 7)
            name = f"{s['number']} {s['name']}"
            while c.stringWidth(name, F["regular"], 7) > 54 * mm and len(name) > 8:
                name = name[:-2]
            c.drawString(2 * mm, y + 1.2 * mm, name if name == f"{s['number']} {s['name']}" else name.rstrip() + "…")
            a, b = s["first"] - T["first"], s["last"] - T["first"] + 1
            c.setFillColorRGB(*_rgb(STAGE_COLOURS[(int(s["number"].split(".")[-1]) - 1) % len(STAGE_COLOURS)]))
            c.rect(x0 + a * step, y, (b - a) * step, 4.2 * mm, stroke=0, fill=1)
            p = s["peak_month"] - T["first"]
            c.setFillColorRGB(*_rgb(INK))
            c.rect(x0 + (p + 0.5) * step - 0.6, y - 0.6 * mm, 1.2, 5.4 * mm, stroke=0, fill=1)
        _months_axis(c, F, x0, x1, 9 * mm + 3.2 * mm - 1.5 * mm, months, clp_doc.month_label)
        c.setFont(F["italic"], 6.5); c.setFillColorRGB(*_rgb(MUTED))
        c.drawString(2 * mm, 2.5 * mm, "Bars: first to last month with approved lorry loads. Mark: the stage's busiest month.")
    return {"png": _png(draw, CHART_W_MM, h_mm),
            "alt": "Programme: " + "; ".join(f"{s['name']} {clp_doc.period_words(s['first'], s['last'])}" for s in st) + "."}


def monthly_chart(data):
    """§6: trips a month stacked by stage, left scale a month, right scale a day (÷ working days). None when empty."""
    from reportlab.lib.units import mm
    import clp_doc
    T = data["totals"]
    st = [s for s in data["stages"] if s["first"]]
    if not st or not T["first"]:
        return None
    months = list(range(T["first"], T["last"] + 1))
    wd = data["working_days"]
    top = _nice_top(max(data["by_month"].get(m, 0) for m in months))

    def draw(c, F, W, H):
        x0, x1 = 16 * mm, W - 16 * mm
        y0, y1 = 22 * mm, H - 6 * mm
        step = (x1 - x0) / len(months)
        c.setFont(F["regular"], 6.5)
        for k in range(5):                                    # gridlines and the month scale
            v = top * k / 4
            y = y0 + (y1 - y0) * k / 4
            c.setStrokeColorRGB(*_rgb(GRID)); c.setLineWidth(0.5); c.line(x0, y, x1, y)
            c.setFillColorRGB(*_rgb(MUTED))
            c.drawRightString(x0 - 1.5 * mm, y - 2, _fmt(v))
        for v in day_ticks(top, wd):                          # the day scale at round numbers of its own
            c.drawString(x1 + 1.5 * mm, y0 + (y1 - y0) * v * wd / top - 2, _fmt(v))
        c.saveState(); c.translate(4 * mm, (y0 + y1) / 2); c.rotate(90)
        c.drawCentredString(0, 0, "Trips a month"); c.restoreState()
        c.saveState(); c.translate(W - 3 * mm, (y0 + y1) / 2); c.rotate(90)
        c.drawCentredString(0, 0, f"Trips a day (÷ {wd:g} working days)"); c.restoreState()
        for i, m in enumerate(months):
            y = y0
            for s in st:
                v = s["by_month"].get(m, 0)
                if v <= 0:
                    continue
                hgt = (y1 - y0) * v / top
                c.setFillColorRGB(*_rgb(STAGE_COLOURS[(int(s["number"].split(".")[-1]) - 1) % len(STAGE_COLOURS)]))
                c.rect(x0 + i * step + step * 0.12, y, step * 0.76, hgt, stroke=0, fill=1)
                y += hgt
        _months_axis(c, F, x0, x1, y0, months, clp_doc.month_label)
        lx, ly = x0, 6 * mm                                    # the key
        c.setFont(F["regular"], 6.5)
        for s in st:
            name = s["name"]
            wdt = c.stringWidth(name, F["regular"], 6.5) + 7 * mm
            if lx + wdt > x1:
                lx, ly = x0, ly - 4 * mm
            c.setFillColorRGB(*_rgb(STAGE_COLOURS[(int(s["number"].split(".")[-1]) - 1) % len(STAGE_COLOURS)]))
            c.rect(lx, ly, 3 * mm, 2.4 * mm, stroke=0, fill=1)
            c.setFillColorRGB(*_rgb(INK)); c.drawString(lx + 4 * mm, ly + 0.3 * mm, name)
            lx += wdt
    n_rows = 1 + sum(1 for _ in st) // 4
    return {"png": _png(draw, CHART_W_MM, 78 + 4 * n_rows),
            "alt": (f"Trips a month by stage, {clp_doc.period_words(T['first'], T['last'])}; the busiest month "
                    f"{clp_doc.month_label(T['peak_month'])} with {T['peak_trips']:,} trips ({T['peak_daily']:g} a day).")}


def hourly_chart(h):
    """§6: one gate's arrivals in each hour of the site's busiest month; closed hours left empty."""
    from reportlab.lib.units import mm
    import clp_doc
    hours = [x for x in h["per_hour"] if x["open_minutes"] > 0]
    if not hours:
        return None
    lo, hi = hours[0]["hour"], hours[-1]["hour"]
    span = [x for x in h["per_hour"] if lo <= x["hour"] <= hi]
    top = _nice_top(max(x["lorries"] for x in span) or 1)

    def draw(c, F, W, H):
        x0, x1 = 16 * mm, W - 4 * mm
        y0, y1 = 12 * mm, H - 6 * mm
        step = (x1 - x0) / len(span)
        c.setFont(F["regular"], 6.5)
        for k in range(5):
            v = top * k / 4
            y = y0 + (y1 - y0) * k / 4
            c.setStrokeColorRGB(*_rgb(GRID)); c.setLineWidth(0.5); c.line(x0, y, x1, y)
            c.setFillColorRGB(*_rgb(MUTED)); c.drawRightString(x0 - 1.5 * mm, y - 2, _fmt(v))
        c.saveState(); c.translate(4 * mm, (y0 + y1) / 2); c.rotate(90)
        c.drawCentredString(0, 0, "Lorries arriving"); c.restoreState()
        for i, x in enumerate(span):
            cx = x0 + i * step
            if x["open_minutes"] < 60:                          # a closed or part-closed hour: a pale band behind
                c.setFillColorRGB(*_rgb(BAND))
                c.rect(cx, y0, step * (1 - x["open_minutes"] / 60.0), y1 - y0, stroke=0, fill=1)
            if x["lorries"] > 0:
                hgt = (y1 - y0) * x["lorries"] / top
                c.setFillColorRGB(*_rgb(STAGE_COLOURS[1]))
                c.rect(cx + step * 0.15, y0, step * 0.7, hgt, stroke=0, fill=1)
                c.setFillColorRGB(*_rgb(INK)); c.setFont(F["regular"], 6)
                c.drawCentredString(cx + step / 2, y0 + hgt + 1, _fmt(x["lorries"]))
            c.setFillColorRGB(*_rgb(MUTED)); c.setFont(F["regular"], 6.5)
            c.drawCentredString(cx + step / 2, y0 - 3.5 * mm, f"{x['hour']:02d}:00")
        c.setFont(F["italic"], 6.5)
        c.drawString(x0, 2.5 * mm, "Shaded: closed for part or all of the hour (no-delivery bands, shut times).")
    return {"png": _png(draw, CHART_W_MM, 62),
            "alt": (f"{h['gate']}, {clp_doc.month_label(h['month'])}: {h['arrivals_per_day']:g} lorries a day, "
                    + ", ".join(f"{x['hour']:02d}:00 {x['lorries']:g}" for x in hours) + ".")}


# --------------------------------------------------------------------------- #
#  The three plans                                                             #
# --------------------------------------------------------------------------- #
PLAN_STYLE = {"regional": None, "local": "streets", "site": "streets"}   # None = the tenant's "Maps on paper" style


def _plan_jpeg(pdf_bytes, dpi=PLAN_DPI):
    """The plan's one-page PDF as a JPEG: rasterised at `dpi`, the white margin cut off (as export.route_map_png), the
    DPI written into the file so Word places it at its printed width. One bitmap at a time, closed as soon as the
    JPEG is written."""
    import pypdfium2 as pdfium
    import route_map_export as rme
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        page = pdf[0]
        bitmap = page.render(scale=dpi / 72.0)
        img = bitmap.to_pil()
        page.close()
    finally:
        pdf.close()
    cut = max(0, int(round(rme.MARGIN_MM / 25.4 * dpi)) - 1)      # keep the frame's keyline
    img = img.crop((cut, cut, img.width - cut, img.height - cut)).convert("RGB")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, dpi=(dpi, dpi))
    img.close()
    del bitmap
    return out.getvalue()


def _site_month(data, site_id):
    sm = {}
    ends = {r["route_id"]: r for r in data["routes"]}
    for l in data["lines"]:
        r = ends.get(l["route_id"])
        if r and site_id in (r.get("from_id"), r.get("to_id")):
            sm[l["month"]] = sm.get(l["month"], 0) + l["trips"]
    return min(sm, key=lambda m: (-sm[m], m)) if sm else None


def plans(data, acc=None):
    """[{kind, name, scale, site, month, jpg, alt, note}] — the regional plan, then each site's local and site plans.
    Empty when no route of this CLP is drawn. acc: the caller's access (rolls up the whole scheme for planner / admin)."""
    import basemap
    import export
    import route_map_export as rme
    import clp_doc
    drawn = [r["route_id"] for r in data["routes"] if r["routed"]]
    if not drawn or not data["totals"]["peak_month"]:
        return []
    acc = acc or {"role": "planner"}
    sheets = {}

    def sheet(mi):
        if mi not in sheets:
            sheets[mi] = rme.sheet(mi, route_ids=drawn, acc=acc)
        return dict(sheets[mi], places=list(sheets[mi]["places"]))

    def draw(S, kind, style):
        # the PDF here is only rendered to a picture, never kept: no ASCII85 text wrapping of its images (reportlab's
        # pure-Python encoder took 14 of a site's 38 s on this laptop; rl_config is read when each image is written)
        from reportlab import rl_config
        was = rl_config.useA85
        rl_config.useA85 = 0
        try:
            if style:
                with basemap.use(style):
                    return _plan_jpeg(export.build_route_map_pdf(S))
            return _plan_jpeg(export.build_route_map_pdf(S))
        finally:
            rl_config.useA85 = was

    out = []
    pm = data["totals"]["peak_month"]
    S = sheet(pm)
    if S["map_routes"]:
        rme.plan(S, "regional")
        P = S["plan"]
        if P["view"]:
            out.append({"kind": "regional", "name": P["name"], "scale": P["scale_words"], "site": None, "month": pm,
                        "jpg": draw(S, "regional", PLAN_STYLE["regional"]),
                        "alt": f"{P['name']}, {P['scale_words']}: this plan's routes in {clp_doc.month_label(pm)}."})
    for s in data["sites"]:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        mi = _site_month(data, s["id"]) or pm
        for kind in ("local", "site"):
            S = sheet(mi)
            if not any(p.get("at") and p["name"].strip().lower() == s["name"].strip().lower() for p in S["places"]):
                import bulletin_doc
                S["places"].append({"letter": bulletin_doc._letters(len(S["places"])), "name": s["name"],
                                    "at": [float(s["lon"]), float(s["lat"])], "end": "dest", "loc_id": s["id"]})
            rme.plan(S, kind, None, at=s["name"])
            P = S["plan"]
            if not P["view"]:
                continue
            LY = P.get("layout") or {}
            # 31 Oct 2026 (4c PR 5): the Site plan draws the site's layout phase in force in that month; §4 names it
            out.append({"kind": kind, "name": P["name"], "scale": P["scale_words"], "site": s["name"], "month": mi,
                        "site_id": s["id"], "layout": LY.get("phase") if LY.get("things") else None,
                        "layout_months": LY.get("months") if LY.get("things") else None,
                        "jpg": draw(S, kind, PLAN_STYLE[kind]),
                        "alt": f"{P['name']} of {s['name']}, {P['scale_words']}, routes in {clp_doc.month_label(mi)}."})
    return out

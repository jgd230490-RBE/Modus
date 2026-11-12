"""
8 Nov 2026 (v2.1 task 2.1-10, mockup notes/supplier-orders-mockup-1108, John: "Yes, as recommended", Q1–Q12).

SUPPLIER ORDERS: one order sheet per supplier from the Look-ahead's commit week (this week or next, as the page's switch
says), as a PDF and an XLSX, or every supplier in one zip. A supplier is a route's ORIGIN location that is not one of the
scheme's own places (Q5: compounds, sites, stockpiles and holding areas are left out and counted on the screen).

Built from the same read the Look-ahead shows (lookahead.page, scoped to the caller: a team sees its own team's lines and
the sheet says "<team>'s lines only", Q1). Only CONFIRMED lines are on an order (Q2); the lines left out are counted on
the screen, never printed on a sheet. Lines to the same gate with the same material, unit and vehicle are one row (Q6);
no team name is printed. Quantities in the material's own unit with the loads beside them (Q3). No price, ever (Q4).
Saturday and Sunday print only when something is on them (Q8). A batching plant with a pour that week gets a Pours
block (Q7). A delivery that calls off through a holding area names it (Q9). Route sheets are named, not included (Q10).
A reference SO-<week>-<location id> and who made it (Q11). Wayscope sends nothing: the sheets are downloaded.
"""
import datetime
import io
import re
import zipfile

OWN_TYPES = ("Compound", "Site", "Stockpile", "Holding area")      # Q5: the scheme's own places, never a supplier
NOT_A_PO = "Not a purchase order · no prices · planning quantities, not plated weights"
SENDS_NOTHING = "Wayscope sends nothing: download and send them yourself."
UNIT_WORD = {"m3": "m³", "t": "t"}


class OrderError(Exception):
    pass


def unit_word(u):
    return UNIT_WORD.get(u or "", u or "")


def _now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/London"))
    except Exception:                                            # noqa: BLE001 — no time-zone database
        return datetime.datetime.now(datetime.timezone.utc)


def made_by(acc):
    """Q11: the signed-in person's name, or the code's role for a shared code."""
    if not acc:
        return "Wayscope"
    if acc.get("via") == "login" and acc.get("name"):
        return str(acc["name"])
    return str(acc.get("label") or acc.get("role") or "staff")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "supplier"


def _is_own(loc):
    import network
    return (network.canonical_loc_type((loc or {}).get("loc_type")) or "") in OWN_TYPES


def _qty(d):
    try:
        return float(d.get("planned_qty") or 0)
    except (TypeError, ValueError):
        return 0.0


def _trips(d):
    try:
        return int((d.get("derived") or {}).get("trips") or 0)
    except (TypeError, ValueError):
        return 0


def _week_qty(line):
    return sum(_qty(d) for d in (line.get("days") or []))


def orders(page, acc=None, now=None):
    """
    Every supplier's order for the page's commit week, as data:
      {"week": {from, to, bucket}, "suppliers": [order…], "left_out": {...}, "team_only": team name or None}
    An order: {location_id, name, vendor, reference, file_stem, days [dates printed], rows [...], totals, pours, …}.
    """
    import db
    import gates
    import gate_hours
    import conversions
    import route_sheet
    import export

    cw = page.get("commit_week") or {}
    lines = (page.get("commit") or {}).get("lines") or []
    tenant = db.current_tenant()
    locs = {l["id"]: l for l in db.query("SELECT * FROM locations WHERE tenant_id = ?", (tenant,))}
    routes = {r["id"]: r for r in db.query("SELECT * FROM routes WHERE tenant_id = ?", (tenant,))}
    gbl = gates.gates_by_location(include_inactive=True)
    factors = conversions.load_factors()
    bands = gate_hours.peak_words(gate_hours.peak_bands(factors))
    try:
        import holding
        hctx = holding.context(factors)
    except Exception:                                            # noqa: BLE001 — no holding areas here
        holding, hctx = None, None
    team = None
    if acc and acc.get("ipt"):
        team = export._team_namer()(acc["ipt"]) or None

    sup, left = {}, {"not_confirmed": 0, "not_confirmed_places": [], "own": 0, "own_places": []}
    confirmed_keys = set()
    for l in lines:
        c = l.get("context") or {}
        if _week_qty(l) <= 0 and not any(_trips(d) for d in (l.get("days") or [])):
            continue
        oid = c.get("origin_id")
        oloc = locs.get(oid) or {}
        oname = oloc.get("name") or c.get("origin_name") or oid or "—"
        if _is_own(oloc):
            left["own"] += 1
            if oname not in left["own_places"]:
                left["own_places"].append(oname)
            continue
        if (l.get("week") or {}).get("status") != "confirmed":
            left["not_confirmed"] += 1
            if oname not in left["not_confirmed_places"]:
                left["not_confirmed_places"].append(oname)
            continue
        confirmed_keys.add((l.get("route_id"), l.get("month_index"), l.get("discipline") or "", l.get("section_id") or ""))
        r = routes.get(l.get("route_id")) or {}
        did = c.get("dest_id") or r.get("dest_id")
        dloc = locs.get(did) or {}
        entry = route_sheet._gate_words(dloc, "entry", r.get("dest_gate_id"), gbl.get(did), factors)
        exit_ = route_sheet._gate_words(dloc, "exit", r.get("dest_gate_id"), gbl.get(did), factors)
        load_exit = route_sheet._gate_words(oloc, "exit", r.get("origin_gate_id"), gbl.get(oid), factors)
        # 11 Nov 2026 (CLOCS C-F2): the lorry's name, as every sheet prints it (export._vehicle_name)
        vehicle = (conversions.vehicle_label(factors, c.get("vehicle_type")) if c.get("vehicle_type") else c.get("vehicle_short")) or "—"
        hold = None
        if holding is not None and hctx and hctx.get("holding") and r:
            h = holding.stops(r, "loaded", hctx, c.get("vehicle_type"))
            hold = (h.get("name") or h["id"]) if h else None
        o = sup.setdefault(oid, {
            "location_id": oid, "name": oname, "vendor": (oloc.get("vendor") or "").strip() or None,
            "rows": {}, "leave_by": []})
        lw = _gate_line(load_exit)
        if lw and lw not in o["leave_by"]:
            o["leave_by"].append(lw)
        unit = l.get("unit") or c.get("unit") or ""
        key = (did, entry.get("name"), c.get("material_type") or "—", unit, vehicle)
        row = o["rows"].setdefault(key, {
            "dest_id": did, "dest_name": dloc.get("name") or c.get("dest_name") or did or "—",
            "gate": entry.get("name") or "the site's entrance",
            "exit_gate": (exit_.get("name") if exit_.get("name") and exit_.get("name") != entry.get("name") else None),
            "open": entry.get("hours") or (f"{entry['default_hours']} (the scheme's default)" if entry.get("default_hours")
                                           else "not typed"),
            "no_deliveries": ", ".join(x for x in (bands, entry.get("shut")) if x) or "none",
            "closed": _closed(entry.get("closed")),
            "site_rules": (dloc.get("site_rules") or "").strip() or None,
            "holding": hold,
            "material": c.get("material_type") or "—", "unit": unit, "vehicle": vehicle,
            "route_ids": [], "qty": {}, "loads": {}})
        if l.get("route_id") and l["route_id"] not in row["route_ids"]:
            row["route_ids"].append(l["route_id"])
        for d in l.get("days") or []:
            dd = d.get("day_date")
            if not dd:
                continue
            row["qty"][dd] = row["qty"].get(dd, 0.0) + _qty(d)
            row["loads"][dd] = row["loads"].get(dd, 0) + _trips(d)

    week_days = _week_days(cw)
    stamp = now or _now()
    out = []
    for oid, o in sup.items():
        rows = sorted(o["rows"].values(), key=lambda x: (-sum(x["qty"].values()), x["dest_name"], x["material"]))
        days = [d for d in week_days if datetime.date.fromisoformat(d).weekday() < 5
                or any(r["qty"].get(d) or r["loads"].get(d) for r in rows)]
        for r in rows:
            r["week_qty"] = sum(r["qty"].get(d, 0.0) for d in days)
            r["week_loads"] = sum(r["loads"].get(d, 0) for d in days)
            r["loads_day_max"] = max([r["loads"].get(d, 0) for d in days] or [0])
        units = {}
        for r in rows:
            units.setdefault(r["unit"], {"day": {d: 0.0 for d in days}, "week": 0.0})
            for d in days:
                units[r["unit"]]["day"][d] += r["qty"].get(d, 0.0)
            units[r["unit"]]["week"] += r["week_qty"]
        loads_day = {d: sum(r["loads"].get(d, 0) for r in rows) for d in days}
        vehicles = sorted({r["vehicle"] for r in rows})
        frm = (cw.get("from") or "week").replace("-", "")
        out.append({
            "location_id": oid, "name": o["name"], "vendor": o["vendor"],
            "reference": f"SO-{frm}-{oid}",
            "file_stem": f"supplier-order-{cw.get('from') or 'week'}-{slug(o['name'])}",
            "leave_by": "; ".join(o["leave_by"]) or None,
            "days": days, "rows": rows, "units": units, "loads_day": loads_day,
            "loads_day_max": max(loads_day.values() or [0]), "week_loads": sum(loads_day.values()),
            "vehicles": vehicles, "deliveries": len(rows),
            "pours": _pours(page, oid, routes, confirmed_keys),
        })
    out.sort(key=lambda s: (-sum(u["week"] for u in s["units"].values()), s["name"]))
    return {
        "week": {"from": cw.get("from"), "to": cw.get("to"), "bucket": page.get("bucket")},
        "tenant": export._tenant_name() or "Wayscope", "demo_notice": export._demo_notice() or None,
        "made_by": made_by(acc), "made_at": stamp.strftime("%d %b %Y %H:%M").lstrip("0"),
        "team_only": team, "suppliers": out, "left_out": left, "sends_nothing": SENDS_NOTHING,
    }


def _gate_line(g):
    if not g or not g.get("name"):
        return None
    hours = g.get("hours") or (f"{g['default_hours']} (default)" if g.get("default_hours") else None)
    bits = [g["name"]] + ([hours] if hours else []) + ([g["closed"]] if g.get("closed") else [])
    return ", ".join(bits)


def _closed(words):
    """'closed on Saturdays and Sundays' -> 'Saturdays and Sundays'; none -> 'open every day'."""
    if not words:
        return "open every day"
    return re.sub(r"^closed on\s+", "", str(words)).strip() or str(words)


def _week_days(cw):
    try:
        a = datetime.date.fromisoformat(cw["from"])
    except (KeyError, TypeError, ValueError):
        return []
    try:
        b = datetime.date.fromisoformat(cw["to"])
    except (KeyError, TypeError, ValueError):
        b = a + datetime.timedelta(days=6)
    out, d = [], a
    while d <= b:
        out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def _pours(page, oid, routes, confirmed_keys):
    """Q7: the week's pours on this supplier's confirmed lines (a batching plant's), earliest first."""
    mine = [p for p in (page.get("pours") or [])
            if (routes.get(p.get("route_id")) or {}).get("origin_id") == oid
            and (p.get("route_id"), p.get("month_index"), p.get("discipline") or "", p.get("section_id") or "") in confirmed_keys]
    if not mine:
        return []
    import pours as _p
    rows = [r for r in (_p.get_pour(x["id"]) for x in mine) if r]
    out = []
    for p in sorted(_p.decorate(rows), key=lambda p: (p.get("pour_date") or "", p.get("start") or "", p["id"])):
        out.append({"id": p["id"], "date": p.get("pour_date"), "start": p.get("start"), "m3": p.get("m3"),
                    "rate_m3h": p.get("rate_m3h"), "dest_name": p.get("dest_name"), "gate_name": p.get("gate_name"),
                    "place": p.get("place")})
    return out


def summary(data):
    """The list the screen shows: no rows, just each supplier's headline and what was left out."""
    return {
        "week": data["week"], "team_only": data["team_only"], "left_out": data["left_out"],
        "sends_nothing": data["sends_nothing"],
        "suppliers": [{"location_id": s["location_id"], "name": s["name"], "vendor": s["vendor"],
                       "deliveries": s["deliveries"], "reference": s["reference"],
                       "totals": [{"unit": unit_word(u), "qty": round(v["week"], 1)} for u, v in s["units"].items()]}
                      for s in data["suppliers"]],
    }


def find(data, location_id):
    s = next((x for x in data["suppliers"] if x["location_id"] == location_id), None)
    if s is None:
        raise OrderError("That place has no confirmed lines to order this week.")
    return s


# ------------------------------------------------------------------ the files
def _day_head(d):
    x = datetime.date.fromisoformat(d)
    return f"{x:%a} {x.day}"


def _num(v, unit):
    """A quantity in its unit: whole tonnes, m³ to one place when it has one."""
    if v is None:
        return "—"
    f = float(v)
    if abs(f - round(f)) < 1e-9:
        return f"{int(round(f)):,}"
    return f"{f:,.1f}"


def _week_words(data):
    try:
        d = datetime.date.fromisoformat(data["week"]["from"])
        return f"Week of {d:%a} {d.day} {d:%b %Y}"
    except (TypeError, ValueError, KeyError):
        return "This week"


def build_pdf(data, s):
    """One supplier's order, A4 portrait, on the Day sheet's frame (export.page_frame)."""
    import export
    from export import (rl_canvas, A4, mm, colors, ParagraphStyle, Paragraph, Spacer, LongTable, TableStyle,
                        KeepTogether, NAVY_RGB, GREY, DEMO_FG_RGB, BAND, MISSING)
    if rl_canvas is None:
        raise RuntimeError("reportlab is not installed: " + MISSING.get("pdf", ""))
    safe = export._pdf_safe
    buf = io.BytesIO()
    W, H = A4
    lm = rm = 12 * mm
    notice = data.get("demo_notice")
    top, bottom = (27 if notice else 22) * mm, 14 * mm
    usable = W - lm - rm
    # the supplier's name is the page's first line, not the title: a long name ran into the CONFIRMED stamp
    title = f"Supplier order · {data['tenant']}"
    on_page = export.page_frame(
        W, H, lm, rm, safe(title), rule_y=H - 9 * mm, title_font=("Helvetica-Bold", 13), title_y=H - 15 * mm,
        right=("CONFIRMED", "Helvetica-Bold", 9, NAVY_RGB),
        sub=(NOT_A_PO, "Helvetica", 8, GREY, H - 19.5 * mm),
        notice=((safe(notice), "Helvetica-Bold", 8.5, DEMO_FG_RGB, H - 24.5 * mm) if notice else None),
        foot=("Wayscope · " + safe(data["tenant"]), "Helvetica", 7, GREY))
    doc = export.frame_doc(buf, W, H, lm, rm, top, bottom, title, on_page)

    st = ParagraphStyle("b", fontName="Helvetica", fontSize=8, leading=9.6)
    st_h = ParagraphStyle("h", parent=st, fontName="Helvetica-Bold", fontSize=7.5, leading=9,
                          textColor=colors.Color(*NAVY_RGB))
    st_hr = ParagraphStyle("hr", parent=st_h, alignment=2)
    st_r = ParagraphStyle("r", parent=st, alignment=2)
    st_g = ParagraphStyle("g", parent=st, fontSize=7.5, leading=9.5, textColor=colors.Color(*GREY))
    st_big = ParagraphStyle("d", parent=st, fontName="Helvetica-Bold", fontSize=15, leading=18,
                            textColor=colors.Color(*NAVY_RGB))
    st_f = ParagraphStyle("f", parent=st, fontSize=10, leading=13)
    st_n = ParagraphStyle("n", parent=st, fontName="Helvetica-Bold", fontSize=10, leading=12,
                          textColor=colors.Color(*NAVY_RGB))

    def E(v):
        return safe(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def P(t, style=st):
        return Paragraph(str(t), style)

    def small(t):
        return f"<br/><font size=6.5 color='#64748B'>{E(t)}</font>"

    story = [P(E(s["name"]), st_big), P(f"<b>{E(_week_words(data))}</b>", st_f), Spacer(1, 1.5 * mm)]
    if data.get("team_only"):
        story.append(P(f"<b>{E(data['team_only'])}'s lines only.</b> Other teams' lines from this supplier are not on this order.", st))
    tot = " · ".join(f"<b>{E(_num(v['week'], u))} {E(unit_word(u))}</b> in the week" for u, v in s["units"].items())
    days_n = len([d for d in s["days"] if s["loads_day"].get(d)])
    story.append(P(f"<b>{s['deliveries']}</b> deliver{'y' if s['deliveries'] == 1 else 'ies'} · {tot} · "
                   f"<b>{s['week_loads']}</b> loads over {days_n} day{'' if days_n == 1 else 's'} · "
                   f"{E(', '.join(s['vehicles']))}", st_f))
    story.append(Spacer(1, 3 * mm))
    left = (f"<b>Supplier</b><br/>{E(s['name'])}" + (f"<br/>{E(s['vendor'])}" if s.get("vendor") else "")
            + (f"<br/>Lorries leave by: {E(s['leave_by'])}" if s.get("leave_by") else ""))
    right = (f"<b>Order</b><br/>Reference {E(s['reference'])}<br/>Made {E(data['made_at'])} by {E(data['made_by'])}"
             f"<br/>Sent by {E(data['tenant'])}, not by Wayscope")
    box = LongTable([[P(left), P(right)]], colWidths=[usable / 2 - 2 * mm, usable / 2 - 2 * mm])
    box.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 0.6, colors.HexColor("#CBD5E1")),
                             ("BOX", (1, 0), (1, 0), 0.6, colors.HexColor("#CBD5E1")),
                             ("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [box, Spacer(1, 4 * mm)]

    if s.get("pours"):
        pdata = [[P(x, st_h) for x in ("POUR", "DAY", "SITE / GATE", "START", "M3", "RATE AN HOUR")]]
        for p in s["pours"]:
            d = datetime.date.fromisoformat(p["date"]) if p.get("date") else None
            pdata.append([P(E(p.get("place") or p["id"])), P(f"{d:%a} {d.day} {d:%b}" if d else "—"),
                          P(E(p.get("dest_name") or "—") + (small(p["gate_name"]) if p.get("gate_name") else "")),
                          P(E(p.get("start") or "—")), P(f"{_num(p.get('m3'), 'm3')} m³"),
                          P(f"{_num(p.get('rate_m3h'), 'm3')} m³")])
        pw = [40 * mm, 22 * mm, 50 * mm, 18 * mm, 20 * mm]
        pw.append(usable - sum(pw))
        pt = LongTable(pdata, colWidths=pw, repeatRows=1)
        pt.setStyle(_grid_style(colors, NAVY_RGB, last_total=False))
        story += [KeepTogether([P("Pours this week", st_n), Spacer(1, 1 * mm), pt]), Spacer(1, 4 * mm)]

    nd = len(s["days"])
    head = [P("DELIVER TO · GATE", st_h), P("MATERIAL · VEHICLE", st_h)]
    head += [P(E(_day_head(d)).upper(), st_hr) for d in s["days"]]
    head += [P("WEEK", st_hr), P("ROUTE", st_h)]
    data_rows = [head]
    for r in s["rows"]:
        u = unit_word(r["unit"])
        row = [P(f"<b>{E(r['dest_name'])}</b>" + small(r["gate"])),
               P(E(r["material"]) + small(r["vehicle"]))]
        for d in s["days"]:
            q, n = r["qty"].get(d, 0.0), r["loads"].get(d, 0)
            row.append(P((f"{E(_num(q, r['unit']))} {E(u)}" if q else "—") + (small(f"{n} load{'' if n == 1 else 's'}") if n else ""), st_r))
        row.append(P(f"<b>{E(_num(r['week_qty'], r['unit']))} {E(u)}</b>" + small(f"{r['week_loads']} loads"), st_r))
        row.append(P(E(", ".join(r["route_ids"]))))
        data_rows.append(row)
    for unit, v in s["units"].items():
        u = unit_word(unit)
        data_rows.append([P(f"<b>Each day</b>" + (f" ({E(u)})" if len(s["units"]) > 1 else "")), ""]
                         + [P(f"<b>{E(_num(v['day'][d], unit))} {E(u)}</b>", st_r) for d in s["days"]]
                         + [P(f"<b>{E(_num(v['week'], unit))} {E(u)}</b>", st_r), ""])
    day_w = 15 * mm if nd > 5 else 17 * mm
    widths = [44 * mm, 32 * mm] + [day_w] * nd + [19 * mm]
    widths.append(max(14 * mm, usable - sum(widths)))
    if sum(widths) > usable:                                     # seven days: the places give way
        widths[0] -= sum(widths) - usable
    t = LongTable(data_rows, colWidths=widths, repeatRows=1)
    t.setStyle(_grid_style(colors, NAVY_RGB, last_total=True, n_total=len(s["units"]), band=BAND))
    story += [t, Spacer(1, 4 * mm)]

    ghead = [P(x, st_h) for x in ("GATE", "OPEN", "NO DELIVERIES", "CLOSED", "SITE RULES")]
    gdata, seen = [ghead], set()
    for r in s["rows"]:
        k = (r["dest_id"], r["gate"])
        if k in seen:
            continue
        seen.add(k)
        sub = r["gate"] + (f"; leave by {r['exit_gate']}" if r.get("exit_gate") else "")
        rules = r.get("site_rules") or "—"
        if r.get("holding"):
            rules = f"Go to {r['holding']} first and wait to be called forward. " + ("" if rules == "—" else rules)
        gdata.append([P(f"<b>{E(r['dest_name'])}</b>" + small(sub)), P(E(r["open"])), P(E(r["no_deliveries"])),
                      P(E(r["closed"])), P(E(rules))])
    gw = [44 * mm, 22 * mm, 34 * mm, 28 * mm]
    gw.append(usable - sum(gw))
    gt = LongTable(gdata, colWidths=gw, repeatRows=1)
    gt.setStyle(_grid_style(colors, NAVY_RGB, last_total=False))
    story += [KeepTogether([P("The gates", st_n), Spacer(1, 1 * mm), gt]), Spacer(1, 4 * mm)]

    routes = sorted({x for r in s["rows"] for x in r["route_ids"]})
    story.append(P(f"Drivers follow the route sheet named on each line (ask the site for it: {E(', '.join(routes))}). "
                   "A load is one lorry there and back. Quantities are planning figures; the weighbridge ticket is the "
                   "record. " + E(SENDS_NOTHING.split(":")[0]) + ".", st_g))
    doc.build(story)
    return buf.getvalue()


def _grid_style(colors, navy, last_total, n_total=1, band=None):
    from export import TableStyle
    st = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
          ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.Color(*navy)),
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.Color(0.85, 0.87, 0.9)),
          ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if last_total:
        st += [("BACKGROUND", (0, -n_total), (-1, -1), colors.Color(*band)),
               ("LINEABOVE", (0, -n_total), (-1, -n_total), 0.8, colors.Color(*navy))]
    return TableStyle(st)


XLSX_COLS = ("Deliver to", "Gate", "Open", "No deliveries", "Closed", "Material", "Unit", "Vehicle")


def build_xlsx(data, s):
    """One supplier's order as one sheet "Order": the header block, then one row a delivery, the days across (numbers)."""
    from export import openpyxl, Font, PatternFill, Alignment, get_column_letter, NAVY, MISSING
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed: " + MISSING.get("xlsx", ""))
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Order"
    head, fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor=NAVY)
    days = s["days"]
    cols = list(XLSX_COLS) + [f"{_day_head(d)} {datetime.date.fromisoformat(d):%b}" for d in days] \
        + ["Week", "Loads a day", "Route sheet"]
    ws.cell(row=1, column=1, value=f"{data['tenant']} · supplier order · {s['name']} · {_week_words(data).lower()} · "
                                   "CONFIRMED").font = Font(bold=True, size=13)
    note = (f"DEMO · {data['demo_notice']}. " if data.get("demo_notice") else "") + \
        f"Not a purchase order, no prices. Planning quantities, not plated weights. Sent by {data['tenant']}, not by Wayscope."
    ws.cell(row=2, column=1, value=note)
    ws.cell(row=3, column=1, value="Supplier")
    ws.cell(row=3, column=2, value=" · ".join(x for x in (s["name"], s.get("vendor"),
                                                          (f"lorries leave by {s['leave_by']}" if s.get("leave_by") else None)) if x))
    ws.cell(row=4, column=1, value="Reference")
    ws.cell(row=4, column=2, value=f"{s['reference']} · made {data['made_at']} by {data['made_by']}")
    r0 = 6
    if data.get("team_only"):
        ws.cell(row=5, column=1, value=f"{data['team_only']}'s lines only")
    for j, c in enumerate(cols, 1):
        x = ws.cell(row=r0, column=j, value=c)
        x.font, x.fill = head, fill
        x.alignment = Alignment(horizontal="center", wrap_text=True)
    i = r0
    for r in s["rows"]:
        i += 1
        vals = [r["dest_name"], r["gate"], r["open"], r["no_deliveries"], r["closed"], r["material"],
                unit_word(r["unit"]), r["vehicle"]]
        vals += [_cell(r["qty"].get(d, 0.0)) for d in days]
        vals += [_cell(r["week_qty"]), r["loads_day_max"], ", ".join(r["route_ids"])]
        for j, v in enumerate(vals, 1):
            ws.cell(row=i, column=j, value=v)
    for unit, v in s["units"].items():
        i += 1
        ws.cell(row=i, column=1, value="Each day" + (f" ({unit_word(unit)})" if len(s["units"]) > 1 else "")).font = Font(bold=True)
        for k, d in enumerate(days):
            ws.cell(row=i, column=len(XLSX_COLS) + 1 + k, value=_cell(v["day"][d])).font = Font(bold=True)
        ws.cell(row=i, column=len(XLSX_COLS) + len(days) + 1, value=_cell(v["week"])).font = Font(bold=True)
    ws.cell(row=i, column=len(XLSX_COLS) + len(days) + 2, value=s["loads_day_max"]).font = Font(bold=True)
    i += 2
    rules = [(r["dest_name"], r.get("site_rules"), r.get("holding")) for r in s["rows"]]
    seen = set()
    for name, rule, hold in rules:
        if name in seen or not (rule or hold):
            continue
        seen.add(name)
        ws.cell(row=i, column=1, value="Site rules")
        ws.cell(row=i, column=2, value=f"{name}: " + (f"go to {hold} first and wait to be called forward. " if hold else "")
                + (rule or ""))
        i += 1
    if s.get("pours"):
        i += 1
        ws.cell(row=i, column=1, value="Pours this week").font = Font(bold=True)
        for p in s["pours"]:
            i += 1
            for j, v in enumerate((p.get("place") or p["id"], p.get("date"), p.get("dest_name"), p.get("gate_name"),
                                   p.get("start"), _cell(p.get("m3")), _cell(p.get("rate_m3h"))), 1):
                ws.cell(row=i, column=j, value=v)
    widths = [30, 22, 13, 24, 22, 22, 7, 22] + [11] * len(days) + [11, 11, 14]
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(row=r0 + 1, column=2)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _cell(v):
    if v is None:
        return None
    f = float(v)
    return int(round(f)) if abs(f - round(f)) < 1e-9 else round(f, 1)


def build_zip(data):
    """Every supplier's PDF and XLSX in one zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for s in data["suppliers"]:
            z.writestr(f"{s['file_stem']}.pdf", build_pdf(data, s))
            z.writestr(f"{s['file_stem']}.xlsx", build_xlsx(data, s))
    return buf.getvalue()


def zip_name(data):
    return f"supplier-orders-{data['week'].get('from') or 'week'}.zip"

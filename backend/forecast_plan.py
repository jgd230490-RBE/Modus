"""
forecast_plan.py — the approved plan by route and month, as a table and a CSV file. Wayscope, 12 Nov 2026
(claude/ui-map-forecast-detail-1111, option A2: the public map's "All routes"; John's call 7: Copy for everyone,
Download for staff only at first).

The public map draws "All routes" in the browser from the month figures it already holds. This module makes the SAME
table on the server for the staff Download, from the same approved lines (main._month_kpi_line: tonnes and loads per
line and month), by the same rule: a route's loads in a month are the sum of its lines' loads; a day is the month's
loads over its working days; a count is in the organisation's unit (counting.per_visit: movements = visits x 2, or
visits), shown whole, "under 1" below one. Pure: the caller passes the lines, the names and the settings in.
"""
import csv
import io

MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
UNITS = ("count", "t")


def month_label(month_index, start_year):
    """'Apr 2027' for month 16 of a programme that starts in 2026."""
    i = int(month_index)
    return f"{MONTH_NAMES[(i - 1) % 12]} {int(start_year) + (i - 1) // 12}"


def count_text(x):
    """A count a day as a screen shows it: whole, 'under 1' below one, comma thousands."""
    x = float(x or 0)
    if 0 < x < 1:
        return "under 1"
    return f"{int(x + 0.5):,}"


def tonnes_text(x):
    return f"{int(float(x or 0) + 0.5):,}"


def table(lines_by_month, month_count, working_days, per_visit, names=None):
    """
    {month_index: [line, ...]} (each line: route_id, material_type, qty_t, vehicle_loads) -> the plan as rows:

        {"months": [1..month_count], "per_visit": 2, "rows": [{"route_id", "origin", "dest", "materials": [..],
          "t": {m: tonnes}, "count": {m: a day in the organisation's unit}, "total_t", "peak_count"}],
         "total": {"t": {m: ..}, "count": {m: ..}, "total_t", "peak_count"}}

    Rows are in route order; a route with nothing approved is left out. `working_days` is a number, or {month: days}.
    """
    names = names or {}
    pv = 1 if int(per_visit or 2) == 1 else 2
    months = list(range(1, int(month_count) + 1))
    by = {}
    for m in months:
        wd = working_days.get(m) if isinstance(working_days, dict) else working_days
        wd = float(wd or 0)
        for l in (lines_by_month.get(m) or lines_by_month.get(str(m)) or []):
            rid = l.get("route_id")
            if not rid:
                continue
            t = float(l.get("qty_t") or 0)
            loads = float(l.get("vehicle_loads") or 0)
            r = by.setdefault(rid, {"t": {}, "loads": {}, "mats": {}})
            r["t"][m] = r["t"].get(m, 0.0) + t
            r["loads"][m] = r["loads"].get(m, 0.0) + (loads / wd if wd > 0 else 0.0)
            k = l.get("material_type") or "—"
            r["mats"][k] = r["mats"].get(k, 0.0) + t
    rows = []
    tot_t, tot_c = {}, {}
    for rid in sorted(by):
        r = by[rid]
        if not (sum(r["t"].values()) > 0 or sum(r["loads"].values()) > 0):
            continue
        count = {m: v * pv for m, v in r["loads"].items()}
        nm = names.get(rid) or {}
        rows.append({
            "route_id": rid, "origin": nm.get("origin") or "", "dest": nm.get("dest") or "",
            "materials": sorted(r["mats"], key=lambda k: (-r["mats"][k], k)),
            "t": dict(r["t"]), "count": count,
            "total_t": sum(r["t"].values()), "peak_count": max(count.values()) if count else 0.0,
        })
        for m, v in r["t"].items():
            tot_t[m] = tot_t.get(m, 0.0) + v
        for m, v in count.items():
            tot_c[m] = tot_c.get(m, 0.0) + v
    return {"months": months, "per_visit": pv, "rows": rows,
            "total": {"t": tot_t, "count": tot_c, "total_t": sum(tot_t.values()),
                      "peak_count": max(tot_c.values()) if tot_c else 0.0}}


def _safe(text):
    """A typed word in a spreadsheet cell: one that starts like a formula is kept as text."""
    s = "" if text is None else str(text)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def csv_text(tab, unit, start_year):
    """The table as CSV text (with a byte-order mark, so a spreadsheet reads the arrow and any accent)."""
    if unit not in UNITS:
        raise ValueError("unit must be 'count' or 't'")
    months = tab["months"]
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(["Route", "From", "To", "Material"] + [month_label(m, start_year) for m in months]
               + ["Total" if unit == "t" else "Busiest"])
    cell = (lambda r, m: tonnes_text(r["t"][m]) if r["t"].get(m) else "") if unit == "t" else \
           (lambda r, m: count_text(r["count"][m]) if r["count"].get(m) else "")
    for r in tab["rows"]:
        w.writerow([_safe(r["route_id"]), _safe(r["origin"]), _safe(r["dest"]), _safe(", ".join(r["materials"]))]
                   + [cell(r, m) for m in months]
                   + [tonnes_text(r["total_t"]) if unit == "t" else count_text(r["peak_count"])])
    t = tab["total"]
    n = len(tab["rows"])
    w.writerow([f"All {n} route{'s' if n != 1 else ''}", "", "", ""]
               + [cell(t, m) for m in months]
               + [tonnes_text(t["total_t"]) if unit == "t" else count_text(t["peak_count"])])
    return "﻿" + out.getvalue()


def file_name(unit, per_visit):
    """approved-plan-tonnes.csv / approved-plan-movements-a-day.csv / approved-plan-visits-a-day.csv"""
    if unit == "t":
        return "approved-plan-tonnes.csv"
    return "approved-plan-visits-a-day.csv" if int(per_visit or 2) == 1 else "approved-plan-movements-a-day.csv"

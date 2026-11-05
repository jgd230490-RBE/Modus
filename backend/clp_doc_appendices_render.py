"""
clp_doc_appendices_render.py — the Word part of the CLP appendices A–O (task 4a, PR 4). The reads are in
clp_doc_appendices.py; this only prints them. Plan: notes/session-1030-clp-document.md §6 (not in git).

render(D, d, A) prints, after section 7, every appendix that has data, a one-line list of those printed and those left
out, then N (always) and O (a pointer, only when the document has a history table). Nothing here adds a "To complete"
line: an appendix is Wayscope's own figures or it is not printed. Every string is held to clp_doc.banned_words by
test_clp_doc_appendices.
"""
from clp_doc_appendices import DIVERSION_WORDS, LETTERS, MAX_ROWS, TITLES, _more


def _n(x):
    from clp_doc import n
    return n(x)


def _month(mi):
    from clp_doc import month_label
    return month_label(mi)


def _date_words(iso):
    from clp_doc import _date_words as dw
    return dw(iso)


def _hm(minutes):
    if minutes is None:
        return "—"
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


def _more_line(D, k):
    if k:
        D.p(f"{_n(k)} more not shown.", italic=True)


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def render(D, d, A):
    """Print the appendices that have data into the document `D` (clp_doc._Doc). Returns the letters printed."""
    present = [k for k in LETTERS if k in A or k == "N" or (k == "O" and d.get("history"))]
    left = [k for k in LETTERS if k not in present]
    D.page_break()
    D.h("Appendices", 1)
    D.p("What Wayscope holds beyond the template's headings. Each appendix is printed only where the plan has figures "
        "for it. Anything already in sections 2 to 7 is pointed to there, not repeated.")
    D.p("Printed: " + "; ".join(f"{k} {TITLES[k]}" for k in present) + ".")
    if left:
        D.p("Left out, because Wayscope holds nothing for this plan: " + "; ".join(f"{k} {TITLES[k]}" for k in left) + ".",
            italic=True)
    team = d.get("team_name")
    unit = d["unit"]
    sites_word = "these sites" if len(d["sites"]) > 1 else "this site"

    def head(letter, extra=None):
        D.h(f"Appendix {letter} {TITLES[letter]}", 2)
        if extra:
            D.p(extra)

    # ---- A
    if "A" in A:
        a = A["A"]
        head("A", "The routes, their distances and lorries are in section 4. This adds, for each route, why it was chosen, "
                  "what a driver may do instead, and the drive time at busy hours.")
        times = a["has_times"]
        hdr = ["Route", "Why this route", "Permitted deviations"] + (
            [f"Cycle {h} (min)" for h in a["hours"]] + ["Quicker option"] if times else [])
        rows = []
        for r in a["rows"]:
            row = [r["route_id"], r["reason"] or "—", r["deviations"] or "—"]
            if times:
                row += [("—" if r["hours"].get(h) is None else str(r["hours"][h])) for h in a["hours"]]
                row += ["; ".join(r["quicker"]) or "—"]
            rows.append(row)
        D.table(hdr, rows, widths=([1.4, 4.3, 3.7, 1.4, 1.4, 1.4, 3.4] if times else [1.6, 7.7, 7.7]),
                numeric=((3, 4, 5) if times else ()))
        if times:
            D.src(f"Cycle = the {a['profile_label']}'s drive out and back for a weekday set off at that hour, plus its "
                  "turnaround. Section 4's figures use the planned 10:00 road. A quicker option is named only where "
                  "another road is quicker at that hour. Each route's driver route sheet carries the reason and the deviations.")
        else:
            D.src("The words are typed on Data → Routes and printed on each route's driver route sheet.")

    # ---- B
    if "B" in A:
        b = A["B"]
        head("B", "Each gate, its hours and the work areas are in section 4.")
        if b["holding"]:
            D.h("Holding areas", 3)
            D.table(["Holding area", "Spaces", "Called forward at a time", "Serves", "Goes straight to the gate"],
                    [[h["name"], _n(h["spaces"]), _n(h["call"]), ", ".join(h["serves"]),
                      ", ".join(h["straight_to_gate"]) or "—"] for h in b["holding"]], widths=[4.4, 1.6, 2.6, 4.4, 4.0],
                    numeric=(1, 2))
            D.src("Lorries wait in the holding area and are called to the gate when it has room. Section 6's arrivals are "
                  "the plan's spread, before any holding.")
        for lay in b["layouts"]:
            D.h(f"Site layout phases: {lay['site']}", 3)
            D.table(["Phase", "Months", "Things drawn", f"In force in {_month(lay['peak_month'])}"],
                    [[p["name"], p["months"], _n(p["things"]), "Yes" if p["in_force"] else ""] for p in lay["phases"]],
                    widths=[5.5, 6.0, 2.5, 3.0], numeric=(2,))
        D.src("From Data → Locations. The phase in force in a site's busiest month is the one drawn on its site plan in 2.2.")

    # ---- C
    if "C" in A:
        c = A["C"]
        head("C", "Section 2.3.1 lists the closures and dated diversions on the routes. This adds where a closed or worked "
                  "area crosses a route and the change in distance.")
        dk = "miles" if unit == "mi" else "km"

        def km(v):
            if v is None:
                return "—"
            v = v / 1.609344 if unit == "mi" else v
            return f"{'+' if v > 0 else ''}{v:.1f} {dk}"

        D.table(["Route", "Closed or worked area", "From", "To", "What happens", "Laden distance change"],
                [[g["route_id"], ", ".join(g["zones"]) or "a closed area", _date_words(g["from"]) if g["from"] else "—",
                  _date_words(g["to"]) if g["to"] else "—", DIVERSION_WORDS[g["status"]], km(g["km_delta"])]
                 for g in c["rows"]], widths=[1.4, 4.2, 2.4, 2.4, 4.6, 2.0], numeric=(5,))
        D.src("Dates are the area's own. The distance is the change on the loaded leg for the main lorry type.")

    # ---- D
    if "D" in A:
        p = A["D"]
        head("D", "Pours the plan holds for these routes. The transit and cold-joint limits are Wayscope settings, not a standard.")
        rows, more = _more(p["rows"])
        D.table(["Pour", "Date", "Start", "m³", "Route", "Mixers needed", "Booked", "Minutes from loading to discharge",
                 "Checks"],
                [[r["id"], _date_words(r["date"]), r["start"], f"{r['m3']:g}", r["route_id"],
                  _n(r["needed"]) if r["needed"] is not None else "—", (_n(r["booked"]) if r["booked"] is not None else "—"),
                  (f"{r['transit']:g}" if r["transit"] is not None else (r["problem"] or "—")),
                  ", ".join(r["flags"]) or "none"] for r in rows],
                widths=[1.2, 2.3, 1.5, 1.2, 1.4, 1.5, 1.7, 2.9, 3.3], numeric=(3, 5, 6, 7))
        _more_line(D, more)
        lim = next((r["limits"] for r in rows if r["limits"]), {})
        if lim:
            D.src(f"Planned pours on these routes. Limits: {lim['transit_min']:g} min from loading to the end of discharge; "
                  f"{lim['cold_joint_min']:g} min between mixers at the face. The pour supervisor's own limits win.")

    # ---- E
    if "E" in A:
        e = A["E"]
        head("E", f"Abnormal loads to or from {sites_word}.")
        rows, more = _more(e["rows"])

        def size(r):
            bits = [f"{r[k]:g} m {w}" for k, w in (("length_m", "long"), ("width_m", "wide"), ("height_m", "high")) if r.get(k)]
            if r.get("gross_t"):
                bits.append(f"{r['gross_t']:g} t")
            return ", ".join(bits) or "—"

        def notice(r):
            bits = []
            if r.get("notify_by"):
                bits.append(f"notify by {_date_words(r['notify_by'])}")
            if r.get("notified_on"):
                bits.append(f"notified {_date_words(r['notified_on'])}")
            if r.get("applied_on"):
                bits.append(f"applied {_date_words(r['applied_on'])}")
            return "; ".join(bits) or "—"

        D.table(["Load", "From → to", "Dates", "Size", "Status", "Notice"],
                [[f"{r['id']} {r['name']}".strip(), f"{r['from']} → {r['to']}",
                  f"{_date_words(r['from_date'])} – {_date_words(r['to_date'])}", size(r), r["status"], notice(r)]
                 for r in rows], widths=[3.2, 3.4, 2.8, 3.2, 2.2, 2.2])
        _more_line(D, more)
        D.src("Dates and sizes as typed on Plan → Abnormal loads. Notice dates are Wayscope's reading of the rules, to be "
              "checked with the authorities.")

    # ---- F
    if "F" in A:
        head("F", "Stock held at the storage sites in this plan" + (" is every team's, not only this team's." if team else "."))
        for s in A["F"]["sites"]:
            D.h(s["site"], 3)
            bits = []
            if s["capacity"]:
                bits.append(f"capacity {_n(round(s['capacity']))} {s['unit']}")
            if s["opening"]:
                bits.append(f"opening stock {_n(round(s['opening']))} {s['unit']}")
            if s["runs_out"]:
                bits.append(f"runs out in {s['runs_out_weeks']} week{'s' if s['runs_out_weeks'] != 1 else ''}, "
                            f"the first week of {_date_words(s['runs_out'])}")
            if s["over_from"]:
                bits.append(f"over capacity in {s['over_weeks']} week{'s' if s['over_weeks'] != 1 else ''}, "
                            f"the first week of {_date_words(s['over_from'])}")
            if bits:
                D.p("; ".join(bits)[0].upper() + "; ".join(bits)[1:] + ".")
            rows, more = _more(s["months"], 60)
            D.table(["Month", f"In ({s['unit']})", f"Used ({s['unit']})", f"Stock at month end ({s['unit']})", "Note"],
                    [[_month(m["month"]), _n(round(m["in"])), _n(round(m["out"])),
                      (_n(round(m["end"])) if m["end"] is not None else "—"),
                      "runs out" if m["empty"] else ("over capacity" if m["over"] else "")] for m in rows],
                    widths=[2.6, 3.0, 3.0, 4.4, 4.0], numeric=(1, 2, 3))
        D.src("The stock forecast: approved deliveries in, the planned use out, any stock count typed replacing the plan. "
              "A week \"runs out\" when the planned use is more than the pile holds.")

    # ---- G
    if "G" in A:
        g = A["G"]
        head("G", "Tonnes of carbon dioxide equivalent (CO2e) for the lorries on these routes, and all-in with the materials "
                  "and disposal on the same lines.")
        if g["target"] and not g["target"]["invalid"]:
            t = g["target"]
            scope = "this team's share of the scheme's carbon target" if t["scope"] == "team" else "the scheme's carbon target"
            D.p(f"For {scope}: the approved plan is {_n(round(t['approved_t']))} t CO2e all-in; with the agreed decisions "
                f"{_n(round(t['with_decisions_t']))} t; the target {_n(round(t['target_t']))} t "
                f"({'on target' if t['on_target'] else 'not yet on target'}). The figures below are only this plan's lines.")
        if g["decisions"]:
            D.p("Agreed decisions that touch this plan:")
            D.bullets(g["decisions"])
        rows, more = _more(g["months"], 60)
        D.table(["Month", "Loads", "Lorries (t CO2e)", "All-in (t CO2e)"],
                [[_month(m["month"]), _n(m["trips"]), f"{m['lorry']:,.1f}", f"{m['total']:,.1f}"] for m in rows]
                + [["Total", _n(sum(m["trips"] for m in g["months"])), f"{g['lorry_total']:,.1f}", f"{g['total']:,.1f}"]],
                widths=[3.4, 3.0, 4.3, 4.3], numeric=(1, 2, 3))
        if g["unbaked_lines"]:
            D.p(f"{g['unbaked_lines']} line{'s' if g['unbaked_lines'] != 1 else ''} have no drawn route yet, so their lorry "
                "figure is not counted.", italic=True)
        D.src("From the approved plan on the Carbon planner's method: lorry distance and fuel, and the material and disposal "
              "factors on each line.")

    # ---- H
    if "H" in A:
        h = A["H"]
        head("H", "The five-year counts by route are in 2.4.2. This adds the weekday busy hours (07:00–10:00 and 16:00–19:00).")
        if h["busy"]:
            D.p("A stored alternative had clearly fewer collisions on it in the busy hours on:")
            for b in h["busy"]:
                D.p(f"{b['route_id']}: " + " ".join(b["offers"]), size=10)
            D.src("Offered only; nothing is switched. Each route's collision evidence sheet has the counts by hour.")
        else:
            D.p("No stored alternative had clearly fewer collisions in the busy hours on these routes.")
            D.src("Each route's collision evidence sheet has the counts by hour.")
        # 5 Nov 2026 (task 0d-2, Q17): the offers a planner put in use, one sentence each
        for u in h.get("in_use") or []:
            when = ""
            try:
                import datetime as _dt
                dd = _dt.date.fromisoformat(u["since"])
                when = f" since {dd.day} {dd:%b %Y}"
            except Exception:                          # noqa: BLE001
                pass
            kg = u.get("kg")
            fig = ("" if kg is None or abs(kg) < 0.5 else
                   f"; {'saves' if kg < 0 else 'adds'} about {_n(round(abs(kg)))} kg CO₂e over the plan")
            D.p(f"{u['route_id']}: Alt {u['alt']} in use on weekdays {u['from']}–{u['to']}{when}{fig}.", size=10)

    # ---- I
    if "I" in A:
        i = A["I"]
        head("I", f"Places within {i['route_m']} m of a route or {i['site_m']} m of a site, by kind. The schools, hospitals and "
                  "other named places are listed in 2.4.2.")
        D.table(["Kind", "Count", "Nearest", "Metres", "From"],
                [[r["kind"], _n(r["count"]), r["nearest"] or "unnamed", (_n(r["metres"]) if r["metres"] is not None else "—"),
                  r["where"]] for r in i["rows"]], widths=[4.2, 1.6, 5.0, 1.8, 4.4], numeric=(1, 3))

    # ---- J
    if "J" in A:
        j = A["J"]
        head("J", f"The councils the routes cross are in 2.3.1. These figures are this plan's lorries only, in "
                  f"{_month(j['month'])}, the busiest month.")
        kmw = "Lorry miles" if unit == "mi" else "Lorry km"
        D.table(["Council", "Highway authority", "Routes", "Movements a day", f"{kmw} in the month"],
                [[f"{r['name']} ({r['tier']})" if r["tier"] else r["name"], r["authority"] or "—", ", ".join(r["routes"]) or "—",
                  f"{r['movements_per_day']:g}", _n(round(r["lorry_km"]))] for r in j["rows"]],
                widths=[4.4, 4.2, 3.4, 2.4, 2.6], numeric=(3, 4))
        D.src("A movement is one loaded lorry entering the council's area. Distance counts the loaded and empty legs "
              "inside the area. A route that only clips the edge adds distance, not a movement.")

    # ---- K
    if "K" in A:
        k = A["K"]
        head("K", "The Simulation's average working day in each site's busiest month: the plan's loads spread evenly over the "
                  "gates' open hours, less the no-delivery bands.")
        D.table(["Site", "Month", "Lorries in", "Lorries out", "Average on site (min)", "Longest on site (min)",
                 "Longest queue"],
                [[r["site"], _month(r["month"]), _n(r["in"]), _n(r["out"]),
                  (f"{r['avg']:g}" if r["avg"] is not None else "—"), (f"{r['longest']:g}" if r["longest"] is not None else "—"),
                  (f"{r['queue_most']} waiting at {r['queue_area']}" + (f" from {_hm(r['queue_at'])}" if r["queue_at"] is not None else "")
                   if r["queue_area"] else "none")] for r in k["rows"]],
                widths=[3.6, 1.8, 1.6, 1.6, 2.4, 2.4, 3.6], numeric=(2, 3, 4, 5))
        D.src("A planning model, not a count: nothing is observed. It is worked out from the approved plan, the gates' check-in "
              "times and the areas' bays and minutes.")

    # ---- L
    if "L" in A:
        lx = A["L"]
        head("L", "Lorries a day arriving at each gate against what it can check in" +
             (" (the gate's capacity and share are every team's)." if lx["all_teams_pct"] else "."))
        for gt in lx["gates"]:
            D.h(f"{gt['gate']}, {gt['site']}", 3)
            rows, more = _more(gt["rows"], 60)
            D.table(["Month", "Lorries a day", "Gate can check in", "Of capacity", "Note"],
                    [[_month(r["month"]), f"{r['arrivals']:g}", (_n(round(r["capacity"])) if r["capacity"] else "—"),
                      (f"{r['pct']} %" if r["pct"] is not None else "—"), r["word"] or ""] for r in rows],
                    widths=[3.0, 3.0, 3.4, 3.0, 4.6], numeric=(1, 2, 3))
        D.src("\"Queue likely\" from 85 % of capacity, \"Over gate capacity\" over 100 %. The plan's even spread over the open hours.")

    # ---- M
    if "M" in A:
        m = A["M"]
        head("M", f"Lorries needed in {_month(m['month'])}, the busiest month, for the loads on each route.")
        D.table(["Route", "Lorry", "Loads in the month", "Round trips one lorry makes a day", "Lorries needed"],
                [[r["route_id"], r["lorry"], _n(r["trips"]), (_n(r["per_lorry"]) if r["per_lorry"] is not None else "route not drawn"),
                  (_n(r["lorries"]) if r["lorries"] is not None else "—")] for r in m["rows"]]
                + [["Total", "", "", "", _n(m["total"])]], widths=[1.8, 5.0, 3.0, 4.4, 2.8], numeric=(2, 3, 4))
        D.src("A planning figure under the UK drivers' hours rules" + (f" ({m['shift_note']})" if m["shift_note"] else "") +
              ". Weekly limits and the operator's own rota are not modelled.")

    # ---- N
    D.h("Appendix N Sources and how the figures are made", 2)
    snap = d["snapshot"]
    D.bullets([
        "Only lines approved in Wayscope are counted. Lines waiting for approval are not in any figure.",
        "One load is one lorry visit: one trip. A load between two sites in this plan is counted once.",
        f"A day is the month's trips ÷ {d['working_days']:g} working days. The plan spreads each month's loads evenly over the "
        "working days and each day's over the gate's open hours, less the no-delivery bands and shut times. It is a plan, "
        "not a count of lorries.",
        "Routes are drawn for each lorry's size and weight. Distances and drive times come from those drawn routes; a drive "
        "time at a busy hour is for a weekday set off at that hour.",
        "Lorries needed follow the UK drivers' hours rules: a driver's day less the required breaks, driving at most nine hours.",
        "Carbon uses the UK Government's published conversion factors and the Carbon planner's method, with the materials "
        "and disposal on the same lines.",
        "Places and collisions are stored copies of public data, with the dates they were taken. Closures and lorry limits are "
        "as last checked. A figure from a source never fetched is left out, not shown as zero.",
        f"This is a snapshot of the approved plan on {snap.day} {MONTHS[snap.month - 1]} {snap.year}. "
        "Download a new copy to bring it up to date.",
    ])
    st = A["N"]["stored"]
    if st:
        D.table(["Data kept in Wayscope", "Taken or checked"], [[a, b] for a, b in st], widths=[9.0, 8.0])

    # ---- O
    if "O" in present:
        D.h("Appendix O Document history", 2)
        D.p("Every issue of this plan, newest first, with what changed, is the Document history table at the front of this "
            "document, after Still to complete.")
    return present

"""
clp_pack.py — the CLP pack: the CLP monitoring charts for one month, as a PDF and an XLSX.
Wayscope, 14 Oct 2026 (bundle G, W10). Design note: notes/clp-design.md (not in git).

WHAT IT PRINTS
--------------
Exactly the charts of clp.monitoring() whose state is "set", in its order, each with its title, its
units, its headline, a drawing, the figures as a table (so the pack reads on a grey printer), how it is
worked out and its source. The charts with no data are listed by name with the field they need, in one
line each, never as an empty page or a zero. The tenant's demo notice is on EVERY page (export.page_frame's
demo bar) and on every sheet. Team names only; lorries, never trucks.

It draws; it never computes. Every figure is the monitoring reply's (one read, the screen's), so the pack
and the Dashboard section cannot disagree.

THE PRINT PALETTE
-----------------
The data slots of the default look (frontend tokens --chart-1 … --chart-5, the Orange accent of bundle E),
the status red and gold, the "none" grey and ink — the colour system's roles (notes/colour-system-1010.md).
"""
import datetime
import io
import math
import re

import brand_pdf
import export
import weeks

SLOTS = ("#E8590C", "#2563EB", "#0D9488", "#7C3AED", "#A07D34")
NONE, RED, GOLD, INK, TRACK, GRID = "#A8A29E", "#DC2626", "#D97706", "#1E293B", "#F3F2EF", "#E2E8F0"
NOT_TYPED = "Not typed"
TITLE = "CLP monitoring pack"


def _rgb(hexs):
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _txt(s, fallback):
    s = str(s if s is not None else "")
    if fallback:                          # Helvetica's WinAnsi set has neither an arrow nor a subscript 2
        s = s.replace("→", "to").replace("₂", "2").replace("≠", "is not")
    return s


def _n(x, dp=1):
    if x is None:
        return "—"
    v = round(float(x), dp)
    s = f"{v:,.{dp}f}" if dp else f"{int(round(v)):,}"
    return s.replace(",", " ")


def nice_top(v, steps=4):
    """A round axis top above v with `steps` round steps (1, 1.5, 2, 2.5, 3, 4, 5, 6 or 8 × a power of ten): (top, step)."""
    import math
    v = max(float(v or 0), 1e-9)
    raw = v / steps
    p = 10 ** math.floor(math.log10(raw))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * p >= raw:
            step = m * p
            break
    return step * steps, step


def _tick(v, step):
    return _n(v, 0) if float(step).is_integer() else _n(v, 1 if (step * 10).is_integer() else 2)


def _title(M):
    return f"{export._tenant_name()} · {TITLE} · {M.get('label')}"


def file_name(M, ext):
    y, m = weeks._month_of(int(M.get("month") or 1))
    return f"wayscope-clp-pack-{y}-{m:02d}.{ext}"


# --------------------------------------------------------------------------- #
#  The tables: one per chart, the same rows on paper and in the XLSX           #
# --------------------------------------------------------------------------- #
def table_of(c, M):
    """(header, rows) for a chart in state 'set' — the figures the drawing shows, in words a reader can check."""
    k = c["key"]
    dw = c.get("distance_word") or ("lorry-miles" if M.get("distance_unit") == "mi" else "lorry-km")
    if k == "route_caps":
        return (["Route", "Movements a day", "Cap", "Share of cap", "Status"],
                [[r["route"], _n(r["movements_per_day"]), (_n(r["cap"], 0) if r["cap"] is not None else "no cap typed"),
                  (f"{r['pct']} %" if r["pct"] is not None else "—"),
                  ("Over the cap" if r["over"] else ("Within the cap" if r["cap"] is not None else "Not compared"))]
                 for r in c.get("rows") or []])
    if k == "site_caps":
        return (["Site", "Visits a day", "Deliveries", "Coming to load", "CLP cap", "Share", "Status"],
                [[r["site"], _n(r["visits_per_day"]), _n(r["laden_per_day"]), _n(r["empty_per_day"]),
                  (_n(r["cap"]) if r["cap"] is not None else "no cap typed"), (f"{r['pct']} %" if r["pct"] is not None else "—"),
                  ("Over the CLP cap" if r["over"] else ("Within the cap" if r["cap"] is not None else "Not compared"))]
                 for r in c.get("rows") or []])
    if k == "holding_areas":     # 29 Oct 2026 (task 3c)
        return (["Holding area", "Spaces", "Open", "Serves", "Straight to the gate", "Lorries a day", "Most held at once"],
                [[r["holding_area"], (_n(r["spaces"], 0) if r.get("spaces") else "not typed"), r["open"], r["serves"], r["straight"],
                  _n(r["per_day"]), (f"{r['most']} at {r['most_at']}" if (r.get("most") is not None and r.get("most_at")) else
                                     (str(r["most"]) if r.get("most") is not None else "—"))]
                 for r in c.get("rows") or []])
    if k in ("vehicle_types", "euro_class"):
        months = [m["label"] for m in c.get("months") or []]
        head = ["Vehicle type" if k == "vehicle_types" else "Euro class"] + [f"{m} loads" for m in months] + [f"{m} share" for m in months]
        rows = [[s["label"]] + [_n(x, 0) for x in s["loads"]] + [(f"{x:g} %" if x is not None else "—") for x in s["pct"]]
                for s in c.get("series") or []]
        rows.append(["All loads"] + [_n(x, 0) for x in c.get("totals") or []] + ["100 %" if x else "—" for x in c.get("totals") or []])
        return head, rows
    if k == "councils":
        return (["Council", "Movements a day", f"Laden {dw}", f"Empty {dw}", f"All {dw}"],
                [[r["council"], _n(r["movements_per_day"]), _n(r["laden_distance"], 0), _n(r["empty_distance"], 0), _n(r["distance"], 0)]
                 for r in c.get("rows") or []])
    if k == "carbon_rate":
        head = ["Month", "Loads", "Tonnes", "kg CO₂e a load", "a load, with the decisions", "kg CO₂e a tonne",
                "a tonne, with the decisions", "the target a tonne"]
        tgt = c.get("target_kg_per_tonne")
        return head, [[m["label"], _n(m["loads"], 0), _n(m["tonnes"], 0), _n(m["kg_per_load"]), _n(m["kg_per_load_decisions"]),
                       _n(m["kg_per_tonne"], 2), _n(m["kg_per_tonne_decisions"], 2), (_n(tgt, 2) if tgt is not None else "no target")]
                      for m in c.get("months") or []]
    if k == "trips_avoided":
        return (["Month", "Loads as planned", "With the agreed decisions", "Trips avoided"],
                [[m["label"], _n(m["loads_planned"], 0), _n(m["loads_with_decisions"], 0), _n(m["avoided"], 0)]
                 for m in c.get("months") or []])
    return [], []


# --------------------------------------------------------------------------- #
#  The tables on paper: the same figures, laid out to fit A4                   #
# --------------------------------------------------------------------------- #
PAD = 6          # reportlab's default left and right cell padding, points
FIGURE = re.compile(r"^[\d .,%—-]+$")


def _units(c, M):
    """(key, units, n_rows) for a chart's table on paper. key = the first column (header, cells); a unit = (header over it or
    None, [(column header, cells)]) and is never split across two tables. The vehicle and Euro class tables run one row a
    month (the XLSX keeps one column a month): 24 months across would be 49 columns, more than A4 holds."""
    k = c["key"]
    if k in ("vehicle_types", "euro_class"):
        months = [m["label"] for m in c.get("months") or []]
        units = [(s["label"], [("Loads", [_n(x, 0) for x in s["loads"]]),
                               ("Share", [(f"{x:g} %" if x is not None else "—") for x in s["pct"]])])
                 for s in c.get("series") or []]
        units.append((None, [("All loads", [_n(x, 0) for x in c.get("totals") or []])]))
        return ("Month", months), units, len(months)
    head, rows = table_of(c, M)
    if not head:
        return None, [], 0
    return ((head[0], [r[0] for r in rows]), [(None, [(h, [r[j] for r in rows])]) for j, h in enumerate(head[1:], 1)], len(rows))


def pdf_tables(c, M, usable, F):
    """A chart's table as one or more tables that each fit `usable` points: a list of dicts with 'header' (one or two rows),
    'rows', 'widths' (None = reportlab shares the width out, the layout of a table that fits) and 'spans'. A table too wide
    for the page is split into column groups, each repeating the first column; no figure is dropped or shortened."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    fb = F["fallback"]

    def word_w(s, bold=True):
        return max([stringWidth(w, F["bold"] if bold else F["regular"], 7) for w in _txt(s, fb).split()] + [0])

    def cell_w(x):                # a figure never wraps (its thousands gap is a space); words wrap at their spaces
        s = _txt(x, fb)
        return stringWidth(s, F["regular"], 7) if FIGURE.match(s) else word_w(s, bold=False)

    def col_w(h, cells):
        return max([word_w(h)] + [cell_w(x) for x in cells]) + 2 * PAD

    key, units, n = _units(c, M)
    if key is None or not n:
        return []
    two = any(top is not None for top, _ in units)
    kw = max(col_w(key[0], key[1]),
             min(max([stringWidth(_txt(x, fb), F["regular"], 7) for x in key[1]] + [0]) + 2 * PAD, usable * 0.22))
    uw = []
    for top, cols in units:
        ws = [col_w(h, cells) for h, cells in cols]
        if top is not None and word_w(top) + 2 * PAD > sum(ws):
            extra = (word_w(top) + 2 * PAD - sum(ws)) / len(ws)
            ws = [w + extra for w in ws]
        uw.append(ws)
    groups, cur, cur_w = [], [], kw
    for i, ws in enumerate(uw):
        if cur and cur_w + sum(ws) > usable:
            groups.append(cur)
            cur, cur_w = [], kw
        cur.append(i)
        cur_w += sum(ws)
    groups.append(cur)
    out = []
    for g in groups:
        cols = [cc for i in g for cc in units[i][1]]
        natural = [kw] + [w for i in g for w in uw[i]]
        if len(groups) == 1 and not two:
            widths = None
        else:
            widths = [w * usable / sum(natural) for w in natural] if sum(natural) < usable else natural
        spans, header = [], []
        if two:
            top_row, sub_row, x = [key[0]], [""], 1
            for i in g:
                top, ucols = units[i]
                if top is None:                       # a lone column: its header fills both header rows
                    top_row.append(ucols[0][0]); sub_row.append("")
                    spans.append(((x, 0), (x, 1)))
                else:
                    top_row += [top] + [""] * (len(ucols) - 1)
                    sub_row += [h for h, _ in ucols]
                    if len(ucols) > 1:
                        spans.append(((x, 0), (x + len(ucols) - 1, 0)))
                x += len(ucols)
            spans.append(((0, 0), (0, 1)))
            header = [top_row, sub_row]
        else:
            header = [[key[0]] + [h for h, _ in cols]]
        rows = [[key[1][r]] + [cells[r] for _, cells in cols] for r in range(n)]
        out.append({"header": header, "rows": rows, "widths": widths, "spans": spans})
    return out


# --------------------------------------------------------------------------- #
#  PDF                                                                         #
# --------------------------------------------------------------------------- #
def _chart_flowable(c, width, F):
    """A platypus Flowable that draws one chart with the canvas; None for a chart with nothing to draw."""
    Flowable = export.Flowable
    mm = export.mm
    k = c["key"]
    fb = F["fallback"]

    class Chart(Flowable):
        def __init__(self, height):
            Flowable.__init__(self)
            self.width, self.height = width, height

        def wrap(self, aw, ah):
            return self.width, self.height

        # --- helpers
        def _font(self, cv, bold=False, size=7.5):
            cv.setFont(F["bold"] if bold else F["regular"], size)

        def _fill(self, cv, hx):
            cv.setFillColorRGB(*_rgb(hx))

        def _stroke(self, cv, hx, w=0.6):
            cv.setStrokeColorRGB(*_rgb(hx)); cv.setLineWidth(w)

        # --- the month under each bar or point; with many months (a 24-month window) every k-th, so none overlap
        def _months(self, cv, xs, labels, y):
            gap = (xs[1] - xs[0]) if len(xs) > 1 else self.width
            wid = max([cv.stringWidth(_txt(s, fb), F["regular"], 7) for s in labels] + [1]) + 2 * mm
            every = max(1, math.ceil(wid / gap))
            self._fill(cv, INK); self._font(cv, size=7)
            for i, lab in enumerate(labels):
                if i % every == 0:
                    cv.drawCentredString(xs[i], y, _txt(lab, fb))

        def draw(self):
            cv = self.canv
            getattr(self, "_" + kind)(cv)

        # --- one row a route or site: a track to the cap, the planned figure, a marker at the cap, the words
        def _bullet(self, cv):
            rows = rows_b
            label_w, words_w = 52 * mm, 58 * mm
            plot_w = self.width - label_w - words_w
            top = max([max(r["v"], r["cap"]) for r in rows] + [1]) * 1.08
            rh = 8 * mm
            for i, r in enumerate(rows):
                y = self.height - (i + 1) * rh + 2 * mm
                self._fill(cv, INK); self._font(cv, size=7.5)
                cv.drawString(0, y + 1.2 * mm, _txt(r["name"], fb)[:44])
                sx = lambda v: label_w + plot_w * float(v) / top
                self._fill(cv, TRACK); self._stroke(cv, "#E7E5E4", 0.5)
                cv.rect(label_w, y, sx(r["cap"]) - label_w, 4.8 * mm, fill=1, stroke=1)
                self._fill(cv, RED if r["over"] else SLOTS[0])
                cv.rect(label_w, y + 1.2 * mm, max(0.5, sx(r["v"]) - label_w), 2.4 * mm, fill=1, stroke=0)
                self._stroke(cv, INK, 1.4); cv.line(sx(r["cap"]), y - 0.6 * mm, sx(r["cap"]), y + 5.4 * mm)
                self._fill(cv, RED if r["over"] else INK); self._font(cv, bold=True, size=7.5)
                cv.drawString(label_w + plot_w + 2 * mm, y + 1.2 * mm, _txt(r["words"], fb))

        # --- a 100 % stacked bar a month
        def _share(self, cv):
            months = [m["label"] for m in c.get("months") or []]
            series = c.get("series") or []
            left, bottom, legend_h = 10 * mm, 12 * mm + 6 * mm * (len(legend_lines) - 1), 6 * mm
            ph = self.height - bottom - legend_h
            pw = self.width - left
            n = max(1, len(months))
            bw = min(16 * mm, pw / n * 0.6)
            self._stroke(cv, GRID, 0.4)
            for p in (0, 25, 50, 75, 100):
                y = bottom + ph * p / 100
                cv.line(left, y, self.width, y)
                self._fill(cv, "#64748B"); self._font(cv, size=6.5); cv.drawRightString(left - 1.5 * mm, y - 1, f"{p} %")
            colours = share_colours
            for i, m in enumerate(months):
                x = left + pw * (i + 0.5) / n - bw / 2
                y = bottom
                for s, col in zip(series, colours):
                    v = s["pct"][i] or 0.0
                    h = ph * v / 100.0
                    if h > 0:
                        self._fill(cv, col); cv.rect(x, y, bw, h, fill=1, stroke=0)
                        self._stroke(cv, "#FFFFFF", 0.8); cv.line(x, y + h, x + bw, y + h)
                    y += h
            self._months(cv, [left + pw * (i + 0.5) / n for i in range(len(months))], months, bottom - 4 * mm)
            for li, line in enumerate(legend_lines):          # the key wraps onto more lines, never off the page
                lx, ly = left, 1 * mm + (len(legend_lines) - 1 - li) * 6 * mm
                for t, col in line:
                    self._fill(cv, col); cv.rect(lx, ly, 3 * mm, 3 * mm, fill=1, stroke=0)
                    self._fill(cv, INK); self._font(cv, size=7)
                    cv.drawString(lx + 4 * mm, ly + 0.4 * mm, t)
                    lx += 4 * mm + _sw(t) + 5 * mm

        # --- councils: laden and empty distance, stacked, with movements a day in words
        def _councils(self, cv):
            rows = c.get("rows") or []
            label_w, words_w = 34 * mm, 62 * mm
            plot_w = self.width - label_w - words_w
            top = max([r["distance"] or 0 for r in rows] + [1]) * 1.05
            rh = 7 * mm
            for i, r in enumerate(rows):
                y = self.height - (i + 1) * rh
                self._fill(cv, INK); self._font(cv, size=7.5); cv.drawString(0, y + 1.4 * mm, _txt(r["council"], fb)[:26])
                lw = plot_w * float(r["laden_distance"] or 0) / top
                ew = plot_w * float(r["empty_distance"] or 0) / top
                self._fill(cv, SLOTS[0]); cv.rect(label_w, y + 0.6 * mm, lw, 4 * mm, fill=1, stroke=0)
                self._fill(cv, SLOTS[2]); cv.rect(label_w + lw, y + 0.6 * mm, ew, 4 * mm, fill=1, stroke=0)
                self._fill(cv, INK); self._font(cv, bold=True, size=7.5)
                cv.drawString(label_w + lw + ew + 2 * mm, y + 1.4 * mm,
                              f"{_n(r['movements_per_day'])} movements a day · {_n(r['distance'], 0)} {c.get('distance_word')}")
            y = self.height - (len(rows) + 1) * rh + 2 * mm
            for j, (lab, col) in enumerate((("Laden", SLOTS[0]), ("Empty", SLOTS[2]))):
                self._fill(cv, col); cv.rect(label_w + j * 26 * mm, y, 3 * mm, 3 * mm, fill=1, stroke=0)
                self._fill(cv, INK); self._font(cv, size=7); cv.drawString(label_w + j * 26 * mm + 4 * mm, y + 0.4 * mm, f"{lab} {c.get('distance_word')}")

        # --- lines a month (kg a tonne): planned, with the decisions, the target dashed
        def _lines(self, cv):
            ms = c.get("months") or []
            labels = [m["label"] for m in ms]
            series = [("As planned", [m["kg_per_tonne"] for m in ms], SLOTS[0], None),
                      ("With the agreed decisions", [m["kg_per_tonne_decisions"] for m in ms], SLOTS[2], None)]
            if c.get("target_kg_per_tonne") is not None:
                series.append(("The target, shared out", [c["target_kg_per_tonne"]] * len(ms), INK, (3, 2)))
            series = [s for s in series if any(v is not None for v in s[1])]
            left, bottom, legend_h = 14 * mm, 10 * mm, 6 * mm
            ph, pw = self.height - bottom - legend_h, self.width - left - 4 * mm
            top, step = nice_top(max([v for s in series for v in s[1] if v is not None] + [1]) * 1.05)
            self._stroke(cv, GRID, 0.4)
            for p in range(5):
                v = step * p
                y = bottom + ph * p / 4
                cv.line(left, y, left + pw, y)
                self._fill(cv, "#64748B"); self._font(cv, size=6.5); cv.drawRightString(left - 1.5 * mm, y - 1, _tick(v, step))
            n = max(1, len(labels))
            xs = [left + pw * (i + 0.5) / n for i in range(n)]
            self._months(cv, xs, labels, bottom - 4 * mm)
            for name, vals, col, dash in series:
                self._stroke(cv, col, 1.6)
                cv.setDash(*dash) if dash else cv.setDash()
                pts = [(xs[i], bottom + ph * v / top) for i, v in enumerate(vals) if v is not None]
                for a, b in zip(pts, pts[1:]):
                    cv.line(a[0], a[1], b[0], b[1])
                cv.setDash()
                self._fill(cv, col)
                for x, y in pts:
                    cv.circle(x, y, 1.1 * mm if not dash else 0.4 * mm, fill=1, stroke=0)
            lx = left
            for name, vals, col, dash in series:
                self._fill(cv, col); cv.rect(lx, 1 * mm, 3 * mm, 3 * mm, fill=1, stroke=0)
                self._fill(cv, INK); self._font(cv, size=7); cv.drawString(lx + 4 * mm, 1.4 * mm, name)
                lx += 4 * mm + cv.stringWidth(name, F["regular"], 7) + 5 * mm

        # --- loads as planned and with the decisions, a pair a month, the trips avoided over them
        def _pairs(self, cv):
            ms = c.get("months") or []
            left, bottom, legend_h = 14 * mm, 10 * mm, 6 * mm
            ph, pw = self.height - bottom - legend_h - 4 * mm, self.width - left - 4 * mm
            top, step = nice_top(max([m["loads_planned"] for m in ms] + [1]) * 1.05)
            n = max(1, len(ms))
            bw = min(10 * mm, pw / n * 0.3)
            self._stroke(cv, GRID, 0.4)
            for p in range(5):
                y = bottom + ph * p / 4
                cv.line(left, y, left + pw, y)
                self._fill(cv, "#64748B"); self._font(cv, size=6.5); cv.drawRightString(left - 1.5 * mm, y - 1, _tick(step * p, step))
            xs = [left + pw * (i + 0.5) / n for i in range(n)]
            gap = (xs[1] - xs[0]) if n > 1 else pw
            # the trips avoided over each pair: "31 avoided" where every month's fits, else the figure alone where every
            # month's fits (the key then says what it is), else none over the bars (the key points to the table); never
            # some months and not others. The table below carries every month either way.
            fit = lambda fmt: all(cv.stringWidth(fmt(m), F["bold"], 7) + 1 * mm <= gap for m in ms if m["avoided"])
            words = (lambda m: f"{_n(m['avoided'], 0)} avoided")
            figure = (lambda m: _n(m["avoided"], 0))
            say = words if fit(words) else (figure if fit(figure) else None)
            for i, m in enumerate(ms):
                cx = xs[i]
                h1, h2 = ph * m["loads_planned"] / top, ph * m["loads_with_decisions"] / top
                self._fill(cv, "#F8C9AE"); self._stroke(cv, SLOTS[0], 0.6); cv.rect(cx - bw - 0.5 * mm, bottom, bw, h1, fill=1, stroke=1)
                self._fill(cv, SLOTS[0]); cv.rect(cx + 0.5 * mm, bottom, bw, h2, fill=1, stroke=0)
                if m["avoided"] and say:
                    self._fill(cv, INK); self._font(cv, bold=True, size=7)
                    cv.drawCentredString(cx, bottom + max(h1, h2) + 1.5 * mm, say(m))
            self._months(cv, xs, [m["label"] for m in ms], bottom - 4 * mm)
            lx = left
            for name, col in (("Loads as planned", "#F8C9AE"), ("With the agreed decisions", SLOTS[0])):
                self._fill(cv, col); cv.rect(lx, 1 * mm, 3 * mm, 3 * mm, fill=1, stroke=0)
                self._fill(cv, INK); self._font(cv, size=7); cv.drawString(lx + 4 * mm, 1.4 * mm, name)
                lx += 4 * mm + cv.stringWidth(name, F["regular"], 7) + 5 * mm
            if any(m["avoided"] for m in ms) and say is not words:
                self._fill(cv, INK); self._font(cv, bold=True, size=7)
                cv.drawString(lx, 1.4 * mm, "Figure over a pair: trips avoided" if say else "Trips avoided each month: the table below")

    rows_b = []
    if k in ("route_caps", "site_caps"):
        vk, nk, word = (("movements_per_day", "route", "movements a day") if k == "route_caps"
                        else ("visits_per_day", "site", "visits a day"))
        for r in c.get("rows") or []:
            if r.get("cap") is None:
                continue
            rows_b.append({"name": r[nk], "v": float(r[vk] or 0), "cap": float(r["cap"]), "over": r["over"],
                           "words": f"{_n(r[vk])} {word} · {r['pct']} % of {_n(r['cap'], 0)}" + (" · over the cap" if r["over"] else "")})
        if not rows_b:
            return None
        kind = "bullet"
        return Chart(len(rows_b) * 8 * mm + 4 * mm)
    if k in ("vehicle_types", "euro_class"):
        kind = "share"
        from reportlab.pdfbase.pdfmetrics import stringWidth
        _sw = lambda t: stringWidth(t, F["regular"], 7)
        share_colours, slot = [], 0
        for s in c.get("series") or []:
            if s["group"] == NOT_TYPED:
                share_colours.append(NONE)
            else:
                share_colours.append(SLOTS[slot % len(SLOTS)]); slot += 1
        legend_lines, line, lx = [], [], 10 * mm
        for s, col in zip(c.get("series") or [], share_colours):
            t = _txt(s["label"], fb)
            w = 4 * mm + _sw(t) + 5 * mm
            if line and lx + w - 5 * mm > width:
                legend_lines.append(line)
                line, lx = [], 10 * mm
            line.append((t, col))
            lx += w
        legend_lines.append(line)
        return Chart(56 * mm + 6 * mm * len(legend_lines))
    if k == "councils":
        kind = "councils"
        return Chart((len(c.get("rows") or []) + 1) * 7 * mm + 4 * mm)
    if k == "carbon_rate":
        kind = "lines"
        return Chart(58 * mm)
    if k == "trips_avoided":
        kind = "pairs"
        return Chart(58 * mm)
    return None


def build_pdf(M, generated=None):
    """The CLP pack as a PDF (A4 portrait): every chart with data, the rest named with what they need."""
    if export.rl_canvas is None:
        raise RuntimeError("reportlab is not installed: " + export.MISSING.get("pdf", ""))
    mm, colors, P_, PS, Spacer, KeepTogether, LongTable, TableStyle = (
        export.mm, export.colors, export.Paragraph, export.ParagraphStyle, export.Spacer, export.KeepTogether,
        export.LongTable, export.TableStyle)
    F = brand_pdf.fonts()
    fb = F["fallback"]
    buf = io.BytesIO()
    W, H = export.A4
    lm = rm = 14 * mm
    notice = M.get("demo_notice") or export._demo_notice()
    top, bottom = (30 if notice else 25) * mm, 14 * mm
    usable = W - lm - rm
    when = generated or datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y")
    title = _title(M)
    stamp = "Planned figures from the approved plan, not observed: Wayscope holds no gate log or arrival times."
    on_page = export.page_frame(W, H, lm, rm, _txt(title, fb), rule_y=H - 9 * mm, title_font=(F["bold"], 13),
                                title_y=H - 15 * mm, right=(f"Generated {when}", F["regular"], 8, export.GREY),
                                sub=(stamp, F["regular"], 8, export.GREY, H - 20.5 * mm),
                                notice=((_txt(notice, fb), F["bold"], 8.5, export.DEMO_FG_RGB, H - 25 * mm) if notice else None),
                                foot=(f"{export._tenant_name()} · {TITLE}", F["regular"], 7, export.GREY))
    doc = export.frame_doc(buf, W, H, lm, rm, top, bottom, title, on_page)
    st = PS("b", fontName=F["regular"], fontSize=8.5, leading=11)
    st_g = PS("g", parent=st, fontSize=7.5, leading=9.5, textColor=colors.Color(*export.GREY))
    st_h1 = PS("h1", parent=st, fontName=F["bold"], fontSize=11.5, leading=14, spaceBefore=6, textColor=colors.Color(*_rgb(INK)))
    st_head = PS("hd", parent=st, fontName=F["bold"], fontSize=9.5, leading=12, textColor=colors.Color(*_rgb(INK)))
    st_th = PS("th", parent=st, fontName=F["bold"], fontSize=7, leading=8.5, textColor=colors.white)
    st_td = PS("td", parent=st, fontSize=7, leading=8.5)
    st_red = PS("rd", parent=st, fontName=F["bold"], textColor=colors.Color(*_rgb(RED)))

    def E(v):
        return _txt(v, fb).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = [P_(E(f"{M.get('scope_line') or ''} {M.get('limit') or ''}"), st_g)]
    if M.get("peak_words"):
        story.append(P_(E(M["peak_words"]), st_g))
    story.append(Spacer(1, 3 * mm))
    charts = M.get("charts") or {}
    drawn = [k for k in M.get("order") or [] if (charts.get(k) or {}).get("state") == "set"]
    missing = [k for k in M.get("order") or [] if (charts.get(k) or {}).get("state") != "set"]
    for k in drawn:
        c = charts[k]
        block = [P_(E(c["title"]) + (f' <font size="8" color="#64748B">· {E(c.get("subtitle"))}</font>' if c.get("subtitle") else ""), st_h1)]
        if c.get("headline"):
            block.append(P_(E(c["headline"]), st_head))
        fl = _chart_flowable(c, usable, F)
        if fl is not None:
            block += [Spacer(1, 2 * mm), fl]
        for tb in pdf_tables(c, M, usable, F):
            nh = len(tb["header"])
            data = [[P_(E(h), st_th) for h in hr] for hr in tb["header"]] + [[P_(E(x), st_td) for x in r] for r in tb["rows"]]
            t = LongTable(data, colWidths=tb["widths"], repeatRows=nh, hAlign="LEFT")
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, nh - 1), colors.Color(*_rgb(INK))),
                                   ("GRID", (0, 0), (-1, -1), 0.3, colors.Color(*_rgb("#CBD5E1"))),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
                                  + [("SPAN", a, b) for a, b in tb["spans"]]))
            block += [Spacer(1, 2 * mm), t]
        for note_key in ("target_note", "invalid", "double_count"):
            if c.get(note_key):
                block.append(P_(E(c[note_key]), st_g))
        if c.get("decisions"):
            block.append(P_(E("The agreed decisions: " + "; ".join(c["decisions"]) + "."), st_g))
        if c.get("vehicles_untyped"):
            block.append(P_(E("No Euro class typed for: " + ", ".join(c["vehicles_untyped"]) + " (Config → Vehicles)."), st_g))
        block.append(P_(E("How it is worked out: " + (c.get("basis") or "")), st_g))
        block.append(P_(E("Source: " + (c.get("source") or "")), st_g))
        for a in c.get("attribution") or []:
            block.append(P_(E(a), st_g))
        # the title, the headline and the drawing never part across a page (the table may run on)
        keep = 4 if (c.get("headline") and fl is not None) else 3
        story.append(KeepTogether(block[:keep]))
        story += block[keep:]
        story.append(Spacer(1, 4 * mm))
    if missing:
        story.append(P_("Not drawn this month", st_h1))
        for k in missing:
            c = charts[k]
            story.append(P_(E(f"{c['title']}: {c.get('missing') or 'no data'}"), st))
    if not drawn:
        story.insert(0, P_("No chart has data for this month.", st_red))
    doc.build(story)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  XLSX                                                                        #
# --------------------------------------------------------------------------- #
SHEET = {"route_caps": "Routes vs cap", "site_caps": "Sites vs CLP cap", "holding_areas": "Holding areas", "vehicle_types": "By vehicle type",
         "euro_class": "By Euro class", "councils": "By council", "carbon_rate": "Carbon a tonne", "trips_avoided": "Trips avoided"}


def build_xlsx(M, generated=None):
    """The CLP pack as an XLSX: About first, then one sheet a chart with data (its table, headline, basis, source)."""
    if export.openpyxl is None:
        raise RuntimeError("openpyxl is not installed: " + export.MISSING.get("xlsx", ""))
    Font, PatternFill = export.Font, export.PatternFill
    wb = export.openpyxl.Workbook()
    notice = M.get("demo_notice") or export._demo_notice()
    charts = M.get("charts") or {}
    drawn = [k for k in M.get("order") or [] if (charts.get(k) or {}).get("state") == "set"]
    missing = [k for k in M.get("order") or [] if (charts.get(k) or {}).get("state") != "set"]

    def demo_row(ws, row=1):
        if notice:
            cv = ws.cell(row=row, column=1, value=notice)
            cv.font = Font(bold=True, color=export.DEMO_FG_HEX)
            cv.fill = PatternFill("solid", fgColor=export.DEMO_BG_HEX)
            return row + 1
        return row

    ws = wb.active
    ws.title = "About"
    r = demo_row(ws)
    about = [("Pack", _title(M)), ("Month", M.get("label")),
             ("Generated", generated or datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"),
             ("Scope", M.get("scope_line")), ("Basis", M.get("limit")), ("Peak bands", M.get("peak_words") or "none typed"),
             ("Working days a month", M.get("working_days")),
             ("Charts in this pack", ", ".join(charts[k]["title"] for k in drawn) or "none")]
    about += [("Not drawn", f"{charts[k]['title']}: {charts[k].get('missing') or 'no data'}") for k in missing]
    for k_, v in about:
        ws.cell(row=r, column=1, value=k_).font = Font(bold=True)
        ws.cell(row=r, column=2, value=v)
        r += 1
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 110
    for k in drawn:
        c = charts[k]
        sh = wb.create_sheet(SHEET.get(k, k)[:31])
        r = demo_row(sh)
        sh.cell(row=r, column=1, value=c["title"]).font = Font(bold=True, size=12)
        r += 1
        if c.get("headline"):
            sh.cell(row=r, column=1, value=c["headline"]).font = Font(bold=True)
            r += 1
        r += 1
        head, rows = table_of(c, M)
        for j, h in enumerate(head, 1):
            cell = sh.cell(row=r, column=j, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=INK.lstrip("#"))
        r += 1
        for row in rows:
            for j, v in enumerate(row, 1):
                sh.cell(row=r, column=j, value=v)
            r += 1
        r += 1
        for lab, key in (("Note", "target_note"), ("Note", "invalid"), ("Note", "double_count"), ("How it is worked out", "basis"),
                         ("Source", "source")):
            if c.get(key):
                sh.cell(row=r, column=1, value=lab).font = Font(bold=True)
                sh.cell(row=r, column=2, value=c[key])
                r += 1
        if c.get("decisions"):
            sh.cell(row=r, column=1, value="Agreed decisions").font = Font(bold=True)
            sh.cell(row=r, column=2, value="; ".join(c["decisions"]))
            r += 1
        for a in c.get("attribution") or []:
            sh.cell(row=r, column=2, value=a)
            r += 1
        sh.column_dimensions["A"].width = 34
        for col in "BCDEFGH":
            sh.column_dimensions[col].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

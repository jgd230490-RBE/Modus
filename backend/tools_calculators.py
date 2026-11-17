"""
17 Nov 2026 (claude/tools-calculators) — the three free haul calculators on the public tools page /tools/calculators.

Lorries needed, haul carbon and fuel surcharge, each worked out from the figures a person types. The sums are the
platform's own, called on those figures and on the lorry figures SHIPPED in backend/factors.json (read-only, through
conversions.load_factors_file_cached): never the organisation's Config, never access.current(), nothing of a plan.

  lorries   loads = ceil(tonnes / the lorry's payload)                    derived.payload_for on the shipped file
            lorries = carbon.lorries_for(loads, round trips a day, working days)
            "about N loads a day" = loads over the working days, to the nearest whole load (never 0 when there are loads)
  carbon    return_journey.trip_kg(factors, lorry, loaded_km, return_km, share) with the round trip typed in MILES,
            half out loaded and half back. "Way back": Empty = share 1 (John's answer R3, the default); Not counted =
            share 0; Loaded = the way back counted at the LOADED figure. trip_kg has no such switch (its return leg is
            always the empty figure), so Loaded is worked as trip_kg on the whole round trip as loaded km with no return
            leg (loaded_km = both halves, return_km = 0): the same laden figure on every kilometre. Proved in the harness.
  surcharge costing.baf_pct(diesel now, fuel={"baf_base_eur_per_l": diesel then, "share_pct": share}) and
            costing.adjust(rate, pct). Both are pure functions of the figures they are given (settings are read only
            when `fuel` is None), so they are called as they stand. The "eur_per_l" names are the platform's; the sum is a
            RATIO of two prices, so pence a litre goes through unchanged.

The PDF is one A4 page for the one calculator pressed: Wayscope's name, the figures typed, the answer, the date, and "A
planning estimate" on the carbon one. No organisation name, no demo notice, no map. The page's figures are sent again with
the PDF request and worked out again here, so the file can never disagree with what the server would answer.

An email is asked for with the PDF; the file downloads at once, nothing is sent by email and nothing is checked by email
(John's answers Q2 and R4). The address is kept through tools_leads.keep("calculator-pdf", …) (the route-check request
branch owns that one store) once the figures have worked and the file is built; a refused request keeps nothing.
"""
import base64
import datetime
import io
import math
import re

import tools_leads
import tools_public

#: a sum is pressed often (a figure typed, a lorry picked): 300 an hour per address, about five a minute, which is far more
#: than a person reading and changing figures reaches, and far less than a script. The page waits a moment after the
#: last keystroke before it asks.
SUM_LIMIT = tools_public.Limit("calculators", 300, 3600)
#: a PDF stores an email and builds a file: 20 an hour per address.
PDF_LIMIT = tools_public.Limit("calculators-pdf", 20, 3600)

KM_PER_MILE = 1.609344
WAY_BACK = ("Empty", "Loaded", "Not counted")
WAY_BACK_DEFAULT = "Empty"
WHICH = ("lorries", "carbon", "surcharge")
TITLES = {"lorries": "Lorries needed", "carbon": "Haul carbon", "surcharge": "Fuel surcharge"}
MAX_TONNES = 1e9
MAX_LOADS = 1e7
MAX_MILES = 100000.0
MAX_DAYS = 3650.0
MAX_TRIPS = 100.0
MAX_PENCE = 100000.0
MAX_RATE = 1e9


# --------------------------------------------------------------------------- the shipped lorries

def factors():
    """The shipped lorry figures (factors.json), read only."""
    import conversions
    return conversions.load_factors_file_cached()


def lorry_keys():
    import conversions
    return list(conversions.planning_vehicle_names(factors()))


def lorry_label(key):
    import conversions
    return conversions.vehicle_label(factors(), key)


def lorry_short(key):
    """The lorry's name without its weight class ("Artic Flatbed (44t)" -> "Artic Flatbed"), as card 2 draws it."""
    return re.sub(r"\s*\(\d+(?:\.\d+)?\s*t\)\s*$", "", lorry_label(key)).strip() or lorry_label(key)


def payload_t(key):
    import derived
    return derived.payload_for(key, factors())[0]


def _t(n):
    """A tonnage as a person reads it: 28 not 28.0, 14.4 as it is."""
    n = float(n)
    return str(int(n)) if n == int(n) else ("%g" % n)


def lorry_options():
    """[(key, option text for Lorries needed, option text for Haul carbon)] for the pickers, in the shipped order."""
    return [(k, f"{lorry_short(k)}, {_t(payload_t(k))} t a load", lorry_label(k)) for k in lorry_keys()]


# --------------------------------------------------------------------------- reading what was typed

def _num(x):
    """A typed figure as a float, or None when it is blank, not a number or not finite."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(str(x).replace(",", "").strip()) if isinstance(x, str) else float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _pos(x, most):
    v = _num(x)
    return v if (v is not None and 0 < v <= most) else None


def _lorry(x):
    """The shipped lorry key for what was picked: the page sends the lorry's NAME as a person reads it (a key such as
    "Truck mixer …" never reaches a screen), and the key itself is read too."""
    k = str(x or "").strip()
    keys = lorry_keys()
    if k in keys:
        return k
    for key in keys:
        if lorry_label(key) == k:
            return key
    return None


def grp(n):
    return f"{int(round(n)):,}"


def money(v):
    return f"£{v:,.2f}"


# --------------------------------------------------------------------------- the three sums

def lorries_needed(tonnes, lorry, working_days, round_trips):
    """{"loads", "lorries", "per_day", "payload_t", "words": {...}} from the typed figures; refuses in a sentence."""
    import carbon
    t = _pos(tonnes, MAX_TONNES)
    if t is None:
        tools_public.refuse(400, "Type the tonnes to move.")
    key = _lorry(lorry)
    if key is None:
        tools_public.refuse(400, "Pick a lorry.")
    days = _pos(working_days, MAX_DAYS)
    if days is None:
        tools_public.refuse(400, "Type the working days.")
    rt = _pos(round_trips, MAX_TRIPS)
    if rt is None:
        tools_public.refuse(400, "Type the round trips a lorry makes in a day.")
    payload = payload_t(key)
    loads = int(math.ceil(round(t / payload, 9)))
    lorries = carbon.lorries_for(loads, rt, days)
    per_day = max(1, int(math.floor(loads / days + 0.5))) if loads else 0
    return {"loads": loads, "lorries": lorries, "per_day": per_day, "payload_t": payload, "tonnes": t, "lorry": key,
            "working_days": days, "round_trips": rt,
            "answer": f"{lorries} {'lorry' if lorries == 1 else 'lorries'}",
            "detail": f"{grp(loads)} {'load' if loads == 1 else 'loads'} · about {per_day} "
                      f"{'load' if per_day == 1 else 'loads'} a day"}


def haul_carbon(loads, miles, lorry, way_back=WAY_BACK_DEFAULT):
    """The carbon of `loads` round trips of `miles` each: kg a trip and t CO2e in all, by return_journey.trip_kg."""
    import return_journey
    n = _pos(loads, MAX_LOADS)
    if n is None:
        tools_public.refuse(400, "Type the number of loads.")
    mi = _pos(miles, MAX_MILES)
    if mi is None:
        tools_public.refuse(400, "Type the round trip in miles.")
    key = _lorry(lorry)
    if key is None:
        tools_public.refuse(400, "Pick a lorry.")
    wb = str(way_back or WAY_BACK_DEFAULT).strip()
    if wb not in WAY_BACK:
        tools_public.refuse(400, "Pick how the way back is counted.")
    leg_km = mi * KM_PER_MILE / 2.0                 # half out loaded, half back
    f = factors()
    if wb == "Loaded":
        # trip_kg's return leg is always the empty figure, so the whole round trip goes in as loaded km, no return leg
        trip = return_journey.trip_kg(f, key, 2.0 * leg_km, 0.0, 1.0)
    else:
        trip = return_journey.trip_kg(f, key, leg_km, leg_km, 1.0 if wb == "Empty" else 0.0)
    kg_trip = trip["kg"]
    total_kg = kg_trip * n
    t_total = total_kg / 1000.0
    answer = f"{t_total:.2f} t CO₂e" if t_total >= 1 else f"{grp(total_kg)} kg CO₂e"
    return {"kg_per_trip": kg_trip, "total_kg": total_kg, "total_t": t_total, "loads": n, "miles": mi, "lorry": key,
            "way_back": wb, "answer": answer,
            "detail": f"{kg_trip:.1f} kg a trip · transport only · a planning estimate"}


def fuel_surcharge(diesel_then_p, diesel_now_p, share_pct, rate):
    """The surcharge as a percentage and the agreed rate with it added, by costing.baf_pct and costing.adjust."""
    import costing
    then = _pos(diesel_then_p, MAX_PENCE)
    if then is None:
        tools_public.refuse(400, "Type the diesel price when the rate was agreed.")
    now = _pos(diesel_now_p, MAX_PENCE)
    if now is None:
        tools_public.refuse(400, "Type the diesel price now.")
    share = _num(share_pct)
    if share is None or not (0 <= share <= 100):
        tools_public.refuse(400, "Type fuel's share of the rate, from 0 to 100 %.")
    rt = _pos(rate, MAX_RATE)
    if rt is None:
        tools_public.refuse(400, "Type the agreed rate.")
    frac = costing.baf_pct(now, {"baf_base_eur_per_l": then, "share_pct": share})
    new_rate = costing.adjust(rt, frac)
    pct = round(frac * 100.0, 4)
    word = "reduction" if pct < 0 else "surcharge"
    return {"pct": pct, "rate": rt, "rate_with": new_rate, "answer": f"{abs(pct):.1f} % {word}",
            "detail": f"{money(new_rate)} a load"}


def work(which, figures):
    """The one sum named, on a dict of typed figures: the same call the page and the PDF both go through."""
    f = figures if isinstance(figures, dict) else {}
    if which == "lorries":
        return lorries_needed(f.get("tonnes"), f.get("lorry"), f.get("working_days"), f.get("round_trips"))
    if which == "carbon":
        return haul_carbon(f.get("loads"), f.get("miles"), f.get("lorry"), f.get("way_back") or WAY_BACK_DEFAULT)
    if which == "surcharge":
        return fuel_surcharge(f.get("diesel_then"), f.get("diesel_now"), f.get("share"), f.get("rate"))
    tools_public.refuse(400, "Pick one of the three calculators.")


def public(which, out):
    """What the page is sent: the answer's two lines and nothing else."""
    return {"which": which, "answer": out["answer"], "detail": out["detail"]}


# --------------------------------------------------------------------------- the PDF

def figure_lines(which, out):
    """[(label, value)] the figures typed, as the card shows them."""
    if which == "lorries":
        return [("Material to move", f"{grp(out['tonnes']) if out['tonnes'] == int(out['tonnes']) else '%g' % out['tonnes']} t"),
                ("Lorry", f"{lorry_short(out['lorry'])}, {_t(out['payload_t'])} t a load"),
                ("Working days", _t(out["working_days"])),
                ("Round trips a lorry a day", _t(out["round_trips"]))]
    if which == "carbon":
        return [("Loads", _t(out["loads"])), ("Round trip", f"{_t(out['miles'])} miles"),
                ("Lorry", lorry_label(out["lorry"])), ("Way back", out["way_back"])]
    return None


def surcharge_figure_lines(figures, out):
    return [("Diesel when the rate was agreed", f"{_t(_num(figures.get('diesel_then')))}p a litre"),
            ("Diesel now", f"{_t(_num(figures.get('diesel_now')))}p a litre"),
            ("Fuel's share of the rate", f"{_t(_num(figures.get('share')))} %"),
            ("Agreed rate", f"{money(out['rate'])} a load")]


def today():
    try:
        from zoneinfo import ZoneInfo
        d = datetime.datetime.now(ZoneInfo("Europe/London")).date()
    except Exception:
        d = datetime.date.today()
    return d


def build_pdf(which, figures, on=None):
    """One A4 page, bytes: Wayscope's name, the figures typed, the answer and the date. No organisation, no map."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas
    import brand_pdf
    out = work(which, figures)
    rows = surcharge_figure_lines(figures, out) if which == "surcharge" else figure_lines(which, out)
    on = on or today()
    fo = brand_pdf.fonts()
    W, H = A4
    lm = 22 * 2.8346
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{TITLES[which]} · Wayscope")
    c.setAuthor("Wayscope")
    brand_pdf.draw_logo(c, lm, H - 26 * 2.8346, 7 * 2.8346, "logo-header-on-light")
    y = H - 52 * 2.8346
    c.setFillColorRGB(0.45, 0.47, 0.5)
    c.setFont(fo["regular"], 10)
    c.drawString(lm, y, "Haul calculators")
    y -= 24
    c.setFillColorRGB(0.1, 0.12, 0.16)
    c.setFont(fo["bold"], 22)
    c.drawString(lm, y, TITLES[which])
    y -= 30
    c.setFont(fo["bold"], 11)
    c.drawString(lm, y, "Figures typed")
    y -= 8
    c.setStrokeColorRGB(0.85, 0.86, 0.88)
    c.line(lm, y, W - lm, y)
    for label, value in rows:
        y -= 20
        c.setFillColorRGB(0.45, 0.47, 0.5)
        c.setFont(fo["regular"], 11)
        c.drawString(lm, y, label)
        c.setFillColorRGB(0.1, 0.12, 0.16)
        c.drawRightString(W - lm, y, value)
        y -= 6
        c.setStrokeColorRGB(0.92, 0.93, 0.94)
        c.line(lm, y, W - lm, y)
    y -= 34
    c.setFillColorRGB(0.96, 0.95, 0.93)
    c.roundRect(lm, y - 42, W - 2 * lm, 70, 6, stroke=0, fill=1)
    c.setFillColorRGB(0.1, 0.12, 0.16)
    c.setFont(fo["bold"], 11)
    c.drawString(lm + 12, y + 14, "Answer")
    c.setFont(fo["bold"], 24)
    c.drawString(lm + 12, y - 12, out["answer"])
    c.setFont(fo["regular"], 11)
    c.setFillColorRGB(0.45, 0.47, 0.5)
    c.drawString(lm + 12, y - 33, out["detail"])
    y -= 70
    if which == "carbon":
        c.setFont(fo["bold"], 10)
        c.setFillColorRGB(0.1, 0.12, 0.16)
        c.drawString(lm, y, "A planning estimate")
        c.setFont(fo["regular"], 9)
        c.setFillColorRGB(0.45, 0.47, 0.5)
        y -= 14
        c.drawString(lm, y, "Lorry emission figures: UK Government greenhouse gas conversion factors 2026. Transport only.")
        y -= 12
        c.drawString(lm, y, "The round trip is counted half out loaded and half back, the way back as picked above.")
    c.setFont(fo["regular"], 9)
    c.setFillColorRGB(0.45, 0.47, 0.5)
    c.drawString(lm, 20 * 2.8346, f"Wayscope · wayscope.co.uk/tools · {on.day} {on.strftime('%B %Y')}")
    c.showPage()
    c.save()
    return buf.getvalue(), out


# --------------------------------------------------------------------------- the email kept with a PDF

def email_ok(email):
    """The store's own shape check (tools_leads.email_ok), so the page and the store never disagree."""
    return tools_leads.email_ok(email)


def keep_email(which, email, news, ip=""):
    """Keep the address with this download in the one store (tools_leads, owned by the route check request branch)."""
    tools_leads.keep("calculator-pdf", str(email).strip(), news=bool(news), details={"calculator": which}, ip=ip)
    return True


def pdf_answer(body, ip=""):
    """The /pdf call's JSON: the file (base64), its name, and whether the address was kept."""
    which = str((body or {}).get("which") or "")
    if which not in WHICH:
        tools_public.refuse(400, "Pick one of the three calculators.")
    email = (body or {}).get("email")
    if not str(email or "").strip():
        tools_public.refuse(400, "Type your email to download the PDF.")
    if not email_ok(email):
        tools_public.refuse(400, "That email does not look right. Check it and try again.")
    data, _ = build_pdf(which, (body or {}).get("figures"))
    kept = keep_email(which, email, bool((body or {}).get("news")), ip)
    return {"ok": True, "kept": kept, "filename": f"wayscope-{which}.pdf",
            "pdf": base64.b64encode(data).decode("ascii")}

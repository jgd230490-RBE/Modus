"""
test_tools_calculators.py — the three free haul calculators (claude/tools-calculators, 17 Nov 2026). No FastAPI needed.

    python backend/tests/test_tools_calculators.py        (the .venv-tests interpreter)

The three example answers of the mockup's card 2 to the figure; each sum equal to the platform function it stands on over
a spread of inputs; "Loaded" worked and proved; every refusal sentence; the limits; the PDF's text (through
portable.pdf_text) with no organisation name, no demo notice and no map; the page's words against card 2 line by line; the
page's script; the pins in main.py, OPEN_ROUTES, the shared files and the UI audit; the email kept through the one store
(a stand-in module here: tools_leads belongs to the route-check request branch).
The app's side (the real routes, the gate on, the limit, no audit row) is smoke_tools_calculators.py.
"""
import io
import itertools
import json
import math
import os
import re
import subprocess
import sys
import types
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))

import tempfile  # noqa: E402
TMP = tempfile.mkdtemp(prefix="wayscope_calc_")
import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
from portable import remove_scratch_db  # noqa: E402
import carbon  # noqa: E402
import costing  # noqa: E402
import derived  # noqa: E402
import return_journey  # noqa: E402
import tools_calculators as tc  # noqa: E402
import tools_public  # noqa: E402
from portable import pdf_text  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  {extra}"[:600])


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def refusal(fn, *a, **k):
    """(status, sentence) of the open-call refusal a call raises, or None when it answered."""
    try:
        fn(*a, **k)
    except Exception as e:
        d = getattr(e, "detail", None)
        return getattr(e, "status_code", None), (d.get("say") if isinstance(d, dict) else None)
    return None


FLAT = "Artic Flatbed (44t)"
F = tc.factors()

# =========================================================================== #
#  1. the three example answers of card 2                                      #
# =========================================================================== #
L = tc.lorries_needed(2500, FLAT, 22, 6)
ok("⭐ 2,500 t, Artic Flatbed 28 t a load, 22 working days, 6 round trips: 1 lorry", L["answer"] == "1 lorry", str(L))
ok("⭐ ...90 loads, about 4 loads a day", L["loads"] == 90 and L["per_day"] == 4 and L["detail"] == "90 loads · about 4 loads a day", L["detail"])
C = tc.haul_carbon(90, 9.2, FLAT, "Empty")
ok("⭐ 90 loads, 9.2 miles, Artic Flatbed (44t), Empty: 1.16 t CO₂e", C["answer"] == "1.16 t CO₂e", C["answer"])
ok("⭐ ...12.8 kg a trip, transport only, a planning estimate", C["detail"] == "12.8 kg a trip · transport only · a planning estimate", C["detail"])
S = tc.fuel_surcharge(140.0, 154.0, 30, 180.00)
ok("⭐ 140.0p, 154.0p, 30 %, £180.00 a load: 3.0 % surcharge", S["answer"] == "3.0 % surcharge", S["answer"])
ok("⭐ ...£185.40 a load", S["detail"] == "£185.40 a load" and S["rate_with"] == 185.4, S["detail"])

# =========================================================================== #
#  2. each sum equals the platform function it stands on                       #
# =========================================================================== #
keys = tc.lorry_keys()
ok("the pickers hold the six shipped planning lorries", len(keys) == 6 and FLAT in keys, str(keys))
n_checked = 0
for key, tonnes, days, trips in itertools.product(keys, (1, 27.9, 28, 28.01, 500, 2500, 61234.5), (1, 5, 22, 260), (1, 2, 6, 11.5)):     # NARROWED 17 Nov: under one trip a day is refused now
    r = tc.lorries_needed(tonnes, key, days, trips)
    payload = derived.payload_for(key, F)[0]
    loads = int(math.ceil(round(tonnes / payload, 9)))
    n_checked += 1
    if r["loads"] != loads or r["lorries"] != carbon.lorries_for(loads, trips, days):
        ok("lorries needed equals derived.payload_for + carbon.lorries_for", False, f"{key} {tonnes} {days} {trips} {r}")
        break
else:
    ok(f"⭐ lorries needed equals derived.payload_for and carbon.lorries_for over {n_checked} inputs", True)
ok("a lorry's payload is the shipped file's own", all(tc.payload_t(k) == float(F["vehicles"][k]["payload_t"]) for k in keys))
ok("loads round UP (28.01 t on a 28 t lorry is 2 loads) and never 3.0000000000000004 up", tc.lorries_needed(28.01, FLAT, 22, 6)["loads"] == 2
   and tc.lorries_needed(84, FLAT, 22, 6)["loads"] == 3)
ok("a lorry that cannot do the loads in the days needs more lorries (the fleet rule)", tc.lorries_needed(2500, FLAT, 5, 2)["lorries"] == 9,
   str(tc.lorries_needed(2500, FLAT, 5, 2)))
# REVERSED 17 Nov 2026 (the live check's F9): fewer loads than days gives no "a day" figure
ok("one load is 'load', one lorry is 'lorry', and one load over 20 days has no 'a day'", tc.lorries_needed(10, FLAT, 20, 6)["detail"] == "1 load"
   and tc.lorries_needed(10, FLAT, 20, 6)["answer"] == "1 lorry")
ok("🔴 fewer loads than days: the loads alone; as many loads as days or more: the 'a day' figure",
   tc.lorries_needed(280, FLAT, 22, 6)["detail"] == "10 loads" and tc.lorries_needed(28 * 22, FLAT, 22, 6)["detail"] == "22 loads · about 1 load a day")


def _refusal17(fn, *a):
    try:
        fn(*a)
    except Exception as e:  # noqa: BLE001
        return (getattr(e, "status_code", None), getattr(e, "detail", {}).get("say"))
    return None


# 17 Nov 2026 (F4): 0.5 round trips a day answered 5 lorries for 90 loads in 22 days (the sum needs 9)
ok("🔴 under one round trip a day is refused in a sentence, one or more is worked", _refusal17(tc.lorries_needed, 2500, FLAT, 22, 0.5)
   == (400, "Type 1 or more round trips a day.") == _refusal17(tc.lorries_needed, 2500, FLAT, 22, "0.99")
   and tc.lorries_needed(2500, FLAT, 22, 1)["lorries"] == 5)
ok("many lorries read 'lorries'", tc.lorries_needed(25000, FLAT, 5, 1)["answer"].endswith("lorries"))

n_checked = 0
bad = []
for key, loads, miles, wb in itertools.product(keys, (1, 90, 1234), (0.5, 9.2, 40, 250.5), tc.WAY_BACK):
    r = tc.haul_carbon(loads, miles, key, wb)
    half = miles * tc.KM_PER_MILE / 2.0
    share = {"Empty": 1.0, "Not counted": 0.0}.get(wb)
    laden, empty, _ = return_journey.leg_factors(F, key)
    if wb == "Loaded":
        want = half * laden + half * laden                       # the way back at the loaded figure
        via = return_journey.trip_kg(F, key, 2 * half, 0.0, 1.0)["kg"]
    else:
        via = return_journey.trip_kg(F, key, half, half, share)["kg"]
        want = half * laden + half * share * empty
    n_checked += 1
    if abs(r["kg_per_trip"] - via) > 1e-9 or abs(via - want) > 1e-9 or abs(r["total_kg"] - via * loads) > 1e-6:
        bad.append((key, loads, miles, wb, r["kg_per_trip"], via, want))
ok(f"⭐ haul carbon equals return_journey.trip_kg (and the figures by hand) over {n_checked} inputs", not bad, str(bad[:2]))
Lo = tc.haul_carbon(90, 9.2, FLAT, "Loaded")
Em = tc.haul_carbon(90, 9.2, FLAT, "Empty")
No = tc.haul_carbon(90, 9.2, FLAT, "Not counted")
laden_f, empty_f, _ = return_journey.leg_factors(F, FLAT)
ok("⭐ 'Loaded' counts every kilometre of the round trip at the laden figure (9.2 miles = 14.806 km x 1.08004)",
   abs(Lo["kg_per_trip"] - 9.2 * tc.KM_PER_MILE * laden_f) < 1e-9 and Lo["detail"].startswith("16.0 kg a trip"), str(Lo["kg_per_trip"]))
ok("'Not counted' leaves the way back out; 'Empty' charges it at the empty figure; Loaded > Empty > Not counted",
   abs(No["kg_per_trip"] - 9.2 * tc.KM_PER_MILE / 2 * laden_f) < 1e-9 and No["kg_per_trip"] < Em["kg_per_trip"] < Lo["kg_per_trip"])
ok("the way back is Empty unless 'Loaded' or 'Not counted' is picked (R3): no pick = Empty", tc.haul_carbon(90, 9.2, FLAT)["answer"] == Em["answer"]
   and tc.WAY_BACK_DEFAULT == "Empty" and tc.work("carbon", dict(loads=90, miles=9.2, lorry=FLAT))["answer"] == Em["answer"])
ok("a small total is in kg, a big one in t (never '0.00 t')", tc.haul_carbon(2, 3, FLAT)["answer"].endswith(" kg CO₂e")
   and tc.haul_carbon(9000, 90, FLAT)["answer"].endswith(" t CO₂e"), tc.haul_carbon(2, 3, FLAT)["answer"])
ok("an electric lorry is not offered (the picker is the planning lorries)", not any("electric" in k for k in keys))

bad = []
n_checked = 0
for then, now, share, rate in itertools.product((100.0, 140.0, 1.5), (80.0, 140.0, 154.0, 200.5), (0, 10, 30, 100), (50.0, 180.0, 1234.56)):
    r = tc.fuel_surcharge(then, now, share, rate)
    frac = costing.baf_pct(now, {"baf_base_eur_per_l": then, "share_pct": share})
    want = costing.adjust(rate, frac)
    by_hand = round((now / then - 1.0) * (share / 100.0), 6)
    n_checked += 1
    if r["rate_with"] != want or frac != by_hand or abs(r["pct"] - frac * 100) > 1e-9:
        bad.append((then, now, share, rate, r, frac, want))
ok(f"⭐ fuel surcharge equals costing.baf_pct and costing.adjust (and the formula by hand) over {n_checked} inputs", not bad, str(bad[:2]))
ok("a falling price reads 'reduction' with the rate below the agreed one", tc.fuel_surcharge(150, 135, 30, 100)["answer"] == "3.0 % reduction"
   and tc.fuel_surcharge(150, 135, 30, 100)["rate_with"] == 97.0)
ok("no change reads 0.0 % surcharge at the agreed rate", tc.fuel_surcharge(150, 150, 30, 100)["answer"] == "0.0 % surcharge"
   and tc.fuel_surcharge(150, 150, 30, 100)["detail"] == "£100.00 a load")
ok("a typed comma and a typed string are read (2,500 and '154.0')", tc.lorries_needed("2,500", FLAT, "22", "6")["loads"] == 90
   and tc.fuel_surcharge("140.0", "154.0", "30", "180.00")["answer"] == "3.0 % surcharge")

# the sums read nothing of any organisation: the shipped file only, and no access.current()
_src = read("backend/tools_calculators.py")
_code = re.sub(r'"""(?:.|\n)*?"""', "", _src)
ok("🔴 the module reads the shipped file only (no config.load, no load_factors, no access)",
   "load_factors_file_cached" in _code and "load_factors()" not in _code and "access." not in _code and "config." not in _code
   and "import config" not in _code and "import access" not in _code)

# =========================================================================== #
#  3. every refusal is one plain sentence                                      #
# =========================================================================== #
CASES = [
    ("lorries tonnes missing", tc.lorries_needed, ("", FLAT, 22, 6), "Type the tonnes to move."),
    ("lorries tonnes zero", tc.lorries_needed, (0, FLAT, 22, 6), "Type the tonnes to move."),
    ("lorries tonnes negative", tc.lorries_needed, (-5, FLAT, 22, 6), "Type the tonnes to move."),
    ("lorries tonnes words", tc.lorries_needed, ("lots", FLAT, 22, 6), "Type the tonnes to move."),
    ("lorries tonnes huge", tc.lorries_needed, (1e12, FLAT, 22, 6), "Type the tonnes to move."),
    ("lorries tonnes nan", tc.lorries_needed, ("nan", FLAT, 22, 6), "Type the tonnes to move."),
    ("lorries tonnes true", tc.lorries_needed, (True, FLAT, 22, 6), "Type the tonnes to move."),
    ("lorries lorry unknown", tc.lorries_needed, (2500, "Hovercraft", 22, 6), "Pick a lorry."),
    ("lorries lorry missing", tc.lorries_needed, (2500, "", 22, 6), "Pick a lorry."),
    ("lorries days", tc.lorries_needed, (2500, FLAT, 0, 6), "Type the working days."),
    ("lorries trips", tc.lorries_needed, (2500, FLAT, 22, ""), "Type the round trips a lorry makes in a day."),
    ("carbon loads", tc.haul_carbon, ("", 9.2, FLAT, "Empty"), "Type the number of loads."),
    ("carbon miles", tc.haul_carbon, (90, 0, FLAT, "Empty"), "Type the round trip in miles."),
    ("carbon lorry", tc.haul_carbon, (90, 9.2, "x", "Empty"), "Pick a lorry."),
    ("carbon way back", tc.haul_carbon, (90, 9.2, FLAT, "Sideways"), "Pick how the way back is counted."),
    ("surcharge then", tc.fuel_surcharge, ("", 154, 30, 180), "Type the diesel price when the rate was agreed."),
    ("surcharge now", tc.fuel_surcharge, (140, 0, 30, 180), "Type the diesel price now."),
    ("surcharge share low", tc.fuel_surcharge, (140, 154, -1, 180), "Type fuel's share of the rate, from 0 to 100 %."),
    ("surcharge share high", tc.fuel_surcharge, (140, 154, 101, 180), "Type fuel's share of the rate, from 0 to 100 %."),
    ("surcharge share missing", tc.fuel_surcharge, (140, 154, "", 180), "Type fuel's share of the rate, from 0 to 100 %."),
    ("surcharge rate", tc.fuel_surcharge, (140, 154, 30, ""), "Type the agreed rate."),
    ("which", tc.work, ("flying", {}), "Pick one of the three calculators."),
]
for label, fn, args, sentence in CASES:
    r = refusal(fn, *args)
    ok(f"🔴 refusal: {label}: 400 and '{sentence}'", r == (400, sentence), str(r))
ok("a share of 0 and of 100 are allowed (a rate with no fuel in it; all fuel)", tc.fuel_surcharge(140, 154, 0, 180)["pct"] == 0.0
   and tc.fuel_surcharge(140, 154, 100, 180)["pct"] == 10.0)
_sents = {c[3] for c in CASES}
ok("every refusal sentence is plain", all(re.match(r"^[A-Z][^{}\[\]_\n]*[.]$", s) and not re.search(r"\b(?:error|invalid|null|none|json|status)\b", s, re.I)
                                          for s in _sents), str(_sents))

# =========================================================================== #
#  4. the limits                                                               #
# =========================================================================== #
ok("the sums' limit is 300 an hour per address (about five a minute: a person changing figures never reaches it)",
   tc.SUM_LIMIT.most == 300 and tc.SUM_LIMIT.window_s == 3600 and tc.SUM_LIMIT.name == "calculators")
ok("the PDF's limit is 20 an hour per address (it keeps an email and builds a file)", tc.PDF_LIMIT.most == 20 and tc.PDF_LIMIT.window_s == 3600)
_lim = tools_public.Limit("t", tc.PDF_LIMIT.most, tc.PDF_LIMIT.window_s)
t0 = 1_800_000_000.0
ok("⭐ the PDF's limit allows 20 and refuses the 21st, with the plain sentence",
   all(_lim.hit("198.51.100.1", now=t0 + i) for i in range(20)) and not _lim.hit("198.51.100.1", now=t0 + 21)
   and _lim.say == "Too many checks from this connection. Please try again in an hour." and _lim.hit("198.51.100.2", now=t0 + 21))

# =========================================================================== #
#  5. the PDF                                                                  #
# =========================================================================== #
import datetime  # noqa: E402

DAY = datetime.date(2026, 11, 17)
FIG = {
    "lorries": dict(tonnes="2,500", lorry="Artic Flatbed (44t)", working_days="22", round_trips="6"),
    "carbon": dict(loads="90", miles="9.2", lorry="Artic Flatbed (44t)", way_back="Empty"),
    "surcharge": dict(diesel_then="140.0", diesel_now="154.0", share="30", rate="180.00"),
}
TEXT = {}
for which in tc.WHICH:
    data, out = tc.build_pdf(which, FIG[which], on=DAY)
    txt = pdf_text(data)
    TEXT[which] = txt
    ok(f"{which}: a PDF, one A4 page", data[:5] == b"%PDF-" and txt.count("\f") == 1, f"{data[:8]!r} {txt.count(chr(12))}")
    ok(f"{which}: carries the title, Wayscope's name, the answer and its second line and the date",
       tc.TITLES[which] in txt and "Wayscope" in txt and out["answer"] in txt and out["detail"].split(" · ")[0] in txt
       and "17 November 2026" in txt, txt[:300])
    ok(f"🔴 {which}: no organisation name, no demo notice, no map, no supplier",
       not re.search(r"DEMO|fictional|Wolds|Modus|Mapbox|HERE\b|OpenStreetMap|organisation|map\b", txt, re.I), txt[:400])
ok("the lorries PDF lists the figures typed as the card shows them", all(s in TEXT["lorries"] for s in (
    "Material to move", "2,500 t", "Artic Flatbed, 28 t a load", "Working days", "22", "Round trips a lorry a day", "6", "1 lorry", "90 loads")))
ok("⭐ the carbon PDF says 'A planning estimate' and names the way back and the lorry", "A planning estimate" in TEXT["carbon"]
   and "Way back" in TEXT["carbon"] and "Empty" in TEXT["carbon"] and "Artic Flatbed (44t)" in TEXT["carbon"] and "9.2 miles" in TEXT["carbon"]
   and "1.16 t CO₂e" in TEXT["carbon"])
ok("'A planning estimate' is on the carbon PDF only", "A planning estimate" not in TEXT["lorries"] and "A planning estimate" not in TEXT["surcharge"])
ok("the surcharge PDF lists its four figures and the answer", all(s in TEXT["surcharge"] for s in (
    "Diesel when the rate was agreed", "140p a litre", "154p a litre", "30 %", "£180.00 a load", "3.0 % surcharge", "£185.40 a load")), TEXT["surcharge"][:500])
ok("the PDF is worked out from the figures again: a different figure gives a different file",
   tc.build_pdf("lorries", dict(FIG["lorries"], tonnes="5000"), on=DAY)[0] != tc.build_pdf("lorries", FIG["lorries"], on=DAY)[0])
r = refusal(tc.build_pdf, "lorries", dict(FIG["lorries"], tonnes=""), DAY)
ok("a PDF of figures that do not work gives the same refusal sentence as the sum", r == (400, "Type the tonnes to move."), str(r))
ok("the page's PDF date follows the clock (today() is a date)", isinstance(tc.today(), datetime.date))

# =========================================================================== #
#  6. the email kept with a PDF                                                #
# =========================================================================== #
r = refusal(tc.pdf_answer, dict(which="lorries", figures=FIG["lorries"], email=""))
ok("🔴 no email: 'Type your email to download the PDF.'", r == (400, "Type your email to download the PDF."), str(r))
for bad_email in ("nobody", "a@b", "a b@c.co", "@x.co", "a@@x.co", "x" * 300 + "@x.co"):
    r = refusal(tc.pdf_answer, dict(which="lorries", figures=FIG["lorries"], email=bad_email))
    ok(f"🔴 an email that does not look right is refused in a sentence ({bad_email[:12]!r})",
       r == (400, "That email does not look right. Check it and try again."), str(r))
r = refusal(tc.pdf_answer, dict(which="nope", figures={}, email="a@b.co"))
ok("🔴 an unknown calculator is refused", r == (400, "Pick one of the three calculators."), str(r))
r = refusal(tc.pdf_answer, dict(which="lorries", figures=dict(FIG["lorries"], tonnes=""), email="a@b.co"))
ok("🔴 figures that do not work are refused before anything is kept", r == (400, "Type the tonnes to move."), str(r))

import base64  # noqa: E402
import tools_leads  # noqa: E402
remove_scratch_db(db, TMP)
db.init_tool_leads_db()


def rows():
    return db.query("SELECT * FROM tool_leads ORDER BY created_at")


a = tc.pdf_answer(dict(which="carbon", figures=FIG["carbon"], email=" Name@Example.co.uk ", news=True), ip="203.0.113.9")
r1 = rows()
ok("⭐ a good email: the file comes back and ONE row is kept as 'calculator-pdf'", a["ok"] and a["kept"] is True and len(r1) == 1 and r1[0]["kind"] == "calculator-pdf"
   and base64.b64decode(a["pdf"])[:5] == b"%PDF-" and a["filename"] == "wayscope-carbon.pdf", str(r1))
ok("...the tick is 1, the calculator is in the details, the email is the store's (trimmed, lower case)", r1[0]["news"] == 1
   and json.loads(r1[0]["details"]) == {"calculator": "carbon"} and r1[0]["email"] == "name@example.co.uk", str(r1[0]))
# 17 Nov 2026 (claude/tools-leads-status-kept): read on live after one download, the row said "queued" though nothing is ever sent for it
ok("🔴 a PDF's row reads 'kept', never 'queued': nothing is sent for a download", r1[0]["status"] == "kept" == tools_leads.STATUS_KEPT, str(r1[0]["status"]))
ok("🔴 ...the address is kept only as a hash", "203.0.113.9" not in json.dumps(r1[0], default=str) and r1[0]["ip_hash"] == tools_public.address_hash("203.0.113.9"))
tc.pdf_answer(dict(which="surcharge", figures=FIG["surcharge"], email="a@b.co"))
r2 = rows()
ok("the tick unticked (or missing) is kept as 0, with no address hash when none was passed", len(r2) == 2 and sorted(x["news"] for x in r2) == [0, 1]
   and [x for x in r2 if x["news"] == 0][0]["ip_hash"] == "")
n = len(rows())
for label, body in (("no email", dict(which="lorries", figures=FIG["lorries"], email="")),
                    ("a bad email", dict(which="lorries", figures=FIG["lorries"], email="a@b")),
                    ("figures that do not work", dict(which="lorries", figures=dict(FIG["lorries"], tonnes=""), email="a@b.co")),
                    ("an unknown calculator", dict(which="nope", figures={}, email="a@b.co"))):
    ok(f"🔴 {label}: refused, nothing kept", refusal(tc.pdf_answer, body) is not None and len(rows()) == n)
ok("the page's email check is the store's own", tc.email_ok("a@b.co") == tools_leads.email_ok("a@b.co") and tc.email_ok("a@b") == tools_leads.email_ok("a@b") is False)
ok("🔴 the trap box is checked in the route before anything is kept (main.py)", read("backend/main.py").index("tools_public.trapped(body)",
   read("backend/main.py").index("async def tools_calc_pdf")) < read("backend/main.py").index("tools_calculators.pdf_answer("))

# =========================================================================== #
#  7. the page against card 2                                                  #
# =========================================================================== #
PAGE = ROOT / "frontend" / "tools" / "calculators.html"
SAMPLE = HERE / "tools_sample" / "calculators.html"


class Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.rows, self.heads, self.btns, self.tags = [], [], [], [], []
        self.text = []
        self.cur_opt = None
        self.in_sel = None
        self.sel_val = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        self.stack.append((tag, a))
        if tag == "select":
            self.in_sel = a.get("name") or a.get("id")
        if tag == "option":
            self.cur_opt = (self.in_sel, a.get("value"), "selected" in a)

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_sel = None
        if self.stack:
            self.stack.pop()

    def handle_data(self, d):
        if d.strip():
            self.text.append(re.sub(r"\s+", " ", d.strip()))


def doc(path):
    d = Doc()
    d.feed(path.read_text(encoding="utf-8"))
    return d


P = doc(PAGE)
S = doc(SAMPLE)
ptext = " ".join(P.text)
ok("the page exists and is the calculators page", PAGE.is_file() and "<title>Haul calculators · Wayscope tools</title>" in read("frontend/tools/calculators.html"))
for line in ("Haul calculators", "Three quick answers from a few figures.", "Free", "Lorries needed", "Haul carbon", "Fuel surcharge",
             "Download as PDF", "Download the PDF", "Your email", "Download", "Send me Wayscope news now and then",
             "We keep your email with this download. Read the", "privacy notice", "Need the roads compared?", "Ask for a route check.", "Route check",
             "Material to move", "Lorry", "Working days", "Round trips a lorry a day", "Loads", "Round trip", "Way back",
             "Diesel when the rate was agreed", "Diesel now", "Fuel's share of the rate", "Agreed rate"):
    ok(f"card 2's line is on the page: '{line}'", line in ptext and line in " ".join(S.text), line)
ok("the pieces of card 2 that are headings, in order, are the page's headings",
   [t for t in P.text if t in ("Lorries needed", "Haul carbon", "Fuel surcharge")] == ["Lorries needed", "Haul carbon", "Fuel surcharge"])
btn_pdf = [a for t, a in P.tags if t == "button" and "pdf" in (a.get("class") or "").split()]
raw = read("frontend/tools/calculators.html")
ok("three 'Download as PDF' buttons, ALL outline at load: none is dark while the box is closed (the drawing's dark third button is the one pressed)",
   [a.get("class") for a in btn_pdf] == ["btn btn-line sm pdf"] * 3 and "btn-ink" not in raw, str([a.get("class") for a in btn_pdf]))
_calcjs = re.sub(r"/\*.*?\*/", "", read("frontend/tools/calculators.js"), flags=re.S)
ok("⭐ the script turns the PRESSED card's button dark (btn-ink) and every other one outline (btn-line)",
   'cards[j] === card ? "btn-ink" : "btn-line"' in _calcjs and 'className = "btn sm pdf "' in _calcjs)
ok("⭐ the script puts the box in the pressed card's column (data-col 1, 2 or 3) and under that card on one column",
   'setAttribute("data-col", String(Array.prototype.indexOf.call(cards, card) + 1))' in _calcjs and "insertBefore(box, card.nextSibling)" in _calcjs)
_css = read("frontend/tools/tools.css")
ok("the box is inside the card grid, in its second row, in the column data-col names; on one column it follows its card",
   raw.index('id="pdfbox"') < raw.index('<div class="next wide">') and raw.index('id="pdfbox"') > raw.index('id="c-surcharge"')
   and all(f'.calcs > .pdfbox[data-col="{n}"]{{grid-column:{n}}}' in _css for n in (1, 2, 3))
   and '.calcs > .pdfbox[data-col]{grid-row:auto;grid-column:auto}' in _css)
ok("no word changed: the box's heading and labels are card 2's", all(w in ptext for w in ("Download the PDF", "Your email", "Download", "Send me Wayscope news now and then")))
ok("the pill reads Free and the 'next' strip's button goes to /tools/route-check",
   any(t == "span" and a.get("class") == "cr free" for t, a in P.tags) and any(t == "a" and a.get("href") == "/tools/route-check" for t, a in P.tags))
ok("the box under the third card: email, the news tick UNTICKED, a trap box, the privacy link, and it is closed until a PDF button is pressed",
   any(t == "form" and a.get("id") == "pdfbox" and "hidden" in a for t, a in P.tags)
   and any(t == "input" and a.get("type") == "checkbox" and a.get("name") == "news" and "checked" not in a for t, a in P.tags)
   and any(t == "input" and a.get("type") == "email" for t, a in P.tags)
   and any(t == "input" and a.get("name") == "website" for t, a in P.tags)
   and any(t == "a" and a.get("href") == "https://wayscope.co.uk/privacy.html" for t, a in P.tags))
ok("'privacy notice' is a visible link (the drawing's plain text bent on purpose: told to John)", "<a href=\"https://wayscope.co.uk/privacy.html\">privacy notice</a>" in read("frontend/tools/calculators.html"))
ok("the rows are real boxes: 8 typed boxes (4 + 3 numbers... ) and 3 pickers, each with a label",
   sum(1 for t, a in P.tags if t == "input" and a.get("inputmode") == "decimal") == 9
   and sum(1 for t, a in P.tags if t == "select") == 3
   and sum(1 for t, a in P.tags if t == "label" and a.get("for")) == 12)
ids = [a.get("id") for t, a in P.tags if a.get("id")]
ok("every label points at a real box", all(a.get("for") in ids for t, a in P.tags if t == "label" and a.get("for")))

# the opening figures are card 2's, as typed boxes (value + unit read back from the page against the drawing's row)
raw = read("frontend/tools/calculators.html")
rows = re.findall(r'<div class="row"><label for="([^"]+)">([^<]+)</label><span class="bx">(.*?)</span></div>', raw)
SRC = read("backend/tests/tools_sample/calculators.html")
srows = dict(re.findall(r'<div class="row"><span>([^<]+)</span><b>([^<]+)</b></div>', SRC))


def row_text(inner):
    parts = []
    for m in re.finditer(r'<input[^>]*value="([^"]*)"[^>]*>|<i>([^<]*)</i>|<option selected(?: [^>]*)?>([^<]*)</option>|<option value="[^"]*" selected>([^<]*)</option>', inner):
        parts.append(next(g for g in m.groups() if g is not None))
    out = " ".join(parts)
    return re.sub(r"^£ ", "£", out)


got = {label: row_text(inner).replace(" p a litre", "p a litre") for _id, label, inner in rows}   # the box and its unit sit apart
ok("the page has twelve rows", len(rows) == 12, str(len(rows)))
for label, want in srows.items():
    ok(f"⭐ the opening figure of '{label}' is card 2's '{want}'", got.get(label) == want, f"{got.get(label)!r} vs {want!r}")

# the pickers hold the shipped lorries, in the shipped order, with the drawing's wording
opts = {}
for name, v, sel in [(a, b, c) for a, b, c in []]:
    pass
sel_blocks = re.findall(r'<select id="([^"]+)"[^>]*>(.*?)</select>', raw, re.S)
ok("three pickers", len(sel_blocks) == 3)
by_id = {i: re.findall(r'<option(?: value="([^"]*)")?(?: selected)?>([^<]*)</option>', b) for i, b in sel_blocks}
ok("⭐ the Lorries needed picker lists the six shipped lorries with their payload, in order",
   [(v, t) for v, t in by_id["l-lorry"]] == [(tc.lorry_label(k), f"{tc.lorry_short(k)}, {tc._t(tc.payload_t(k))} t a load") for k in tc.lorry_keys()],
   str(by_id["l-lorry"]))
ok("⭐ the Haul carbon picker lists the six shipped lorries by their names", [(v, t) for v, t in by_id["c-lorry"]] == [(tc.lorry_label(k), tc.lorry_label(k)) for k in tc.lorry_keys()],
   str(by_id["c-lorry"]))
ok("the Way back picker: Empty, Loaded, Not counted", [t for v, t in by_id["c-back"]] == ["Empty", "Loaded", "Not counted"] and tuple(t for v, t in by_id["c-back"]) == tc.WAY_BACK)
ok("🔴 no lorry key with a banned word reaches the page (the mixers read 'Concrete mixer')", "Truck" not in raw and "truck" not in raw.lower())
ok("every picker value the page sends is accepted by the server", all(tc._lorry(v) for i in ("l-lorry", "c-lorry") for v, t in by_id[i]))
ok("the answer blocks start empty and are filled by the call: nothing is baked into the page",
   raw.count('<span class="v">&nbsp;</span>') == 3 and "1.16" not in raw and "185.40" not in raw)

# the opening answers, as the page will print them, are card 2's
for which, ans, small in (("lorries", "1 lorry", "90 loads · about 4 loads a day"), ("carbon", "1.16 t CO₂e", "12.8 kg a trip · transport only · a planning estimate"),
                          ("surcharge", "3.0 % surcharge", "£185.40 a load")):
    o = tc.work(which, {"lorries": dict(tonnes="2,500", lorry="Artic Flatbed (44t)", working_days="22", round_trips="6"),
                        "carbon": dict(loads="90", miles="9.2", lorry="Artic Flatbed (44t)", way_back="Empty"),
                        "surcharge": dict(diesel_then="140.0", diesel_now="154.0", share="30", rate="180.00")}[which])
    ok(f"⭐ the opening answer of {which}: '{ans}' · '{small}' as card 2 draws it", (o["answer"], o["detail"]) == (ans, small)
       and ans in SRC and small.replace(" · ", " · ") in SRC, f"{o['answer']} | {o['detail']}")

# =========================================================================== #
#  8. the page's script and the pins                                           #
# =========================================================================== #
JS = read("frontend/tools/calculators.js")
_js = re.sub(r"/\*.*?\*/", "", JS, flags=re.S)
_node = subprocess.run(["where" if os.name == "nt" else "which", "node"], capture_output=True, text=True).stdout.split("\n")[0].strip()
if _node:
    r = subprocess.run([_node, "--check", str(ROOT / "frontend/tools/calculators.js")], capture_output=True, text=True)
    ok("calculators.js parses (node --check)", r.returncode == 0, r.stderr[:300])
else:
    ok("node is on the PATH to check calculators.js", False)
ok("🔴 the script writes no HTML (no innerHTML, no document.write), loads nothing from outside and calls only /api/tools/",
   "innerHTML" not in _js and "document.write" not in _js and not re.search(r"https?://", _js) and "eval(" not in _js
   and set(re.findall(r'"(/api/[^"]*)"', _js)) == {"/api/tools/calculators/sum", "/api/tools/calculators/pdf"})
ok("🔴 the script sets no cookie and keeps nothing in the browser", "cookie" not in _js.lower() and "localStorage" not in _js and "sessionStorage" not in _js)
ok("the script goes through the shared WaysTools.call (one place for the sentence and the no-cookie rule)", _js.count("WaysTools.call(") == 2
   and "fetch(" not in _js)
ok("the page loads its script before the shared one, and the shared one last (the harness's rule)",
   raw.rstrip().endswith('<script src="/tools/calculators.js"></script>\n<script src="/tools/tools.js"></script>\n</body>\n</html>'))
ok("the script is served at /tools/calculators.js", tools_public.page_file("calculators.js") is not None
   and tools_public.page_file("calculators.js")[1].startswith("text/javascript") and tools_public.page_file("calculators") is not None)
ok("both calls are named open on purpose", set(tools_public.OPEN_ROUTES) >= {"/api/tools/calculators/sum", "/api/tools/calculators/pdf"})
MAIN = read("backend/main.py")
ok("main.py: both routes take the guard first, with this module's own limits; the PDF call checks the trap box",
   re.search(r'@app.post\("/api/tools/calculators/sum"\)\nasync def tools_calc_sum\(request: Request\):\n    tools_public.guard\(request, tools_calculators.SUM_LIMIT\)', MAIN)
   and re.search(r'@app.post\("/api/tools/calculators/pdf"\)\nasync def tools_calc_pdf\(request: Request\):\n    tools_public.guard\(request, tools_calculators.PDF_LIMIT\)', MAIN)
   and "tools_public.trapped(body)" in MAIN)
ok("🔴 neither route reads the cookie or the session", "access.current()" not in MAIN[MAIN.index("async def tools_calc_sum"):MAIN.index("async def tools_calc_pdf") + 600])
ok("ui_audit.js walks the page (TOOL_PAGES holds 'calculators')", re.search(r"const TOOL_PAGES = \[[^\]]*\"calculators\"", read("backend/tests/ui_audit.js")))
ok("the stylesheet's calculator rows are in tools.css", ".calc .row input" in read("frontend/tools/tools.css") and ".calc .row select" in read("frontend/tools/tools.css"))

# 17 Nov 2026 (claude/tools-review-looks; John's yes to the review's B1): a line once the file has downloaded
_html17 = (ROOT / "frontend" / "tools" / "calculators.html").read_text(encoding="utf-8")
_js17 = (ROOT / "frontend" / "tools" / "calculators.js").read_text(encoding="utf-8")
ok("🔴 B1: the box holds 'Your PDF has downloaded.', hidden until a download",
   '<p class="done" role="status" hidden>Your PDF has downloaded.</p>' in _html17
   and _html17.index('class="done"') > _html17.index('id="pdfbox"'))
ok("🔴 B1: the script shows it after the file is handed over and hides it on the next press or send",
   'download(data.filename || "wayscope.pdf", data.pdf); done(true);' in _js17 and _js17.count("done(false);") == 2
   and "if (el) el.hidden = !on;" in _js17)

# 17 Nov 2026 (claude/tools-working; John's yes to the frontier check's Ideas 1 and 3): "How this was worked out"
_EX = {"lorries": dict(tonnes="2,500", lorry="Artic Flatbed (44t)", working_days="22", round_trips="6"),
       "carbon": dict(loads="90", miles="9.2", lorry="Artic Flatbed (44t)", way_back="Empty"),
       "surcharge": dict(diesel_then="140.0", diesel_now="154.0", share="30", rate="180.00")}
_ST = {w: tc.work(w, f)["steps"] for w, f in _EX.items()}
ok("⭐ lorries: the three steps for the card's example", _ST["lorries"] == [
    "2,500 t at 28 t a load is 90 loads (89.3, rounded up).", "One lorry makes 6 round trips a day for 22 days: 132 loads.",
    "90 loads need 1 lorry."], str(_ST["lorries"]))
ok("⭐ carbon: the three steps, the source named inside the fold (John's yes, Q2)", _ST["carbon"] == [
    "A 9.2 mile round trip: 4.6 miles loaded, 4.6 back empty.",
    "Artic Flatbed: 1.74 kg a mile loaded, 1.05 empty (UK Government figures, 2026). That is 8.00 + 4.84 = 12.84 kg a trip.",
    "12.84 kg × 90 loads = 1.16 t."], str(_ST["carbon"]))
ok("⭐ surcharge: the three steps, with the line that a fall lowers the rate (Q3)", _ST["surcharge"] == [
    "Diesel is up 10.0 %: from 140.0p to 154.0p a litre.", "Fuel is 30 % of the rate: 10.0 % × 30 % = 3.0 %.",
    "£180.00 + 3.0 % = £185.40 a load. A fall in diesel lowers the rate the same way."], str(_ST["surcharge"]))
ok("the page is sent the steps with the answer", tc.public("carbon", tc.work("carbon", _EX["carbon"]))["steps"] == _ST["carbon"]
   and set(tc.public("carbon", tc.work("carbon", _EX["carbon"]))) == {"which", "answer", "detail", "steps"})
_fall = tc.work("surcharge", dict(_EX["surcharge"], diesel_now="126"))["steps"]
ok("a fall in diesel: 'down', a minus, and no line about a fall", _fall[0] == "Diesel is down 10.0 %: from 140.0p to 126.0p a litre."
   and _fall[2] == "£180.00 − 3.0 % = £174.60 a load.", str(_fall))
ok("way back Loaded and Not counted say so in step 1", tc.work("carbon", dict(_EX["carbon"], way_back="Loaded"))["steps"][0]
   == "A 9.2 mile round trip, counted loaded both ways."
   and tc.work("carbon", dict(_EX["carbon"], way_back="Not counted"))["steps"][0] == "A 9.2 mile round trip: 4.6 miles loaded; the way back is not counted.")
ok("one of anything is singular", tc.work("lorries", dict(tonnes="28", lorry="Artic Flatbed (44t)", working_days="1", round_trips="1"))["steps"]
   == ["28 t at 28 t a load is 1 load.", "One lorry makes 1 round trip a day for 1 day: 1 load.", "1 load needs 1 lorry."]
   and tc.work("carbon", dict(loads="3", miles="2", lorry="Artic Flatbed (44t)", way_back="Empty"))["steps"][0] == "A 2 mile round trip: 1 mile loaded, 1 back empty.")
_bad17 = []
for _key, _n, _mi, _wb in itertools.product(tc.lorry_keys(), (1, 7, 90, 5000), (0.5, 2, 9.2, 120), tc.WAY_BACK):
    _o = tc.work("carbon", dict(loads=_n, miles=_mi, lorry=_key, way_back=_wb))
    _m = re.search(r"([\d.]+) kg × ", _o["steps"][2])
    if not _m or abs(float(_m.group(1)) - _o["kg_per_trip"]) > 0.005 or abs(float(_m.group(1)) * _n - _o["total_kg"]) > 0.005 * _n + 1e-6:
        _bad17.append((_key, _n, _mi, _wb, _o["steps"][2]))
    if _wb == "Empty":
        _p = re.search(r"That is ([\d.]+) \+ ([\d.]+) = ([\d.]+) kg", _o["steps"][1])
        if not _p or abs(float(_p.group(1)) + float(_p.group(2)) - float(_p.group(3))) > 0.0101:
            _bad17.append((_key, _n, _mi, "parts", _o["steps"][1]))
ok("🔴 carbon over 288 inputs: the kg a trip printed in the steps is the sum's own, and its two parts add up to it", not _bad17, str(_bad17[:3]))
ok("the source's year comes from the shipped figures, not from a typed year", tc.source_words() == "UK Government figures, 2026"
   and "UK Government figures, 2026" not in read("backend/tools_calculators.py").replace('"""', ""))
_h17 = read("frontend/tools/calculators.html")
_j17 = read("frontend/tools/calculators.js")
ok("🔴 each card carries the closed fold, hidden until there is an answer", _h17.count(
    '<details class="how" hidden><summary>How this was worked out</summary><ol></ol></details>') == 3 and " open" not in _h17.split("<details")[1][:40])
ok("the script fills the fold as text from the server's steps and hides it without an answer",
   "show(card, data.answer, data.detail, data.steps);" in _j17 and "li.textContent = steps[i];" in _j17
   and "how.hidden = !(steps && steps.length);" in _j17 and "innerHTML" not in _j17)
for _w in ("lorries", "carbon", "surcharge"):
    _raw17, _ = tc.build_pdf(_w, _EX[_w], on=datetime.date(2026, 11, 17))
    _t17 = " ".join(pdf_text(_raw17, raw=True).split())
    ok(f"🔴 the {_w} PDF prints 'How this was worked out' and its three steps, on one page",
       "How this was worked out" in _t17 and all(st.replace(" (UK Government figures, 2026)", "").split(". ")[0][:40] in _t17 for st in _ST[_w])
       and pdf_text(_raw17).count("\f") == 1, _t17[:400])
_c17 = " ".join(pdf_text(tc.build_pdf("carbon", _EX["carbon"], on=datetime.date(2026, 11, 17))[0], raw=True).split())
ok("the carbon PDF names the source once, in its own line, and the old 'half out loaded' line is gone (the steps say it)",
   _c17.count("UK Government") == 1 and "half out loaded" not in _c17 and "A planning estimate" in _c17, _c17[:400])

print(f"test_tools_calculators.py: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)

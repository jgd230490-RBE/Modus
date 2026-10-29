"""
Carbon planner, 10 Oct 2026 — backend/carbon.py (phase 1: the engine) and the factor block.

What is asserted, every expected figure worked by hand in the comment beside it:
  * the factor file: the `carbon` block (UK Government GHG conversion factors 2026, flat file
    v1.2) with a row ID, year, scope, GWP basis and status on every entry; no ICE; the diesel
    pairs now say VERIFIED; Rigid 7.5t is the 2026 class figure 0.49944; the two electric
    variants (fuel, scenario-only, geometry twin, lower payload, kWh/km DERIVED);
  * material carbon = quantity × conversion × factor; the recycled blend (only where primary
    AND closed-loop are published, refused otherwise with the reason); the supplier EPD
    override (source required); the re-used row;
  * transport, both methods: Wayscope's vehicle-km (= costlines.co2_t, the Dashboard's
    figure) and the NH Carbon Tool's tonne-km basis with its ×2 return rule; the DESNZ 2026
    class tonne-km benchmark; the worked example of carbon-why-different-1010.md (§3);
  * allocation to the tool's five categories with the remainder Not Allocated, and the
    error over 100 %; the double-count rule (earthworks excludes bulk materials);
  * disposal routes (soils to landfill 19.55376 vs closed-loop 1.01398);
  * electric: kWh/km × UK electricity, derived in ONE place (conversions._emissions), the
    shift with charging, the fleet; miles ↔ km;
  * config validation of the new keys; the live-document fallback to the file;
  * a scenario end to end on a scratch database: baseline, an alternative, the per-driver
    deltas RANKED by tCO2e moved, the interaction, the benchmarks, the fleet comparison,
    the unbaked line excluded (never estimated), the team filter.

WHAT THIS DOES NOT PROVE
------------------------
  * That the factors are right beyond the published file: the values were read from the
    gov.uk flat file v1.2 on 10 Oct 2026 and the NH Carbon Tool v2.7 workbook on 9 Oct 2026.
  * Anything over HTTP (http_smoke.py) or in a browser. The route geometry is seeded by hand,
    not baked by HERE: every distance here is a fixture.
  * That ZEHID's mixed-fleet 1.25 kWh/km, the battery and charger figures, or the electric
    payload penalty hold for a real tipper fleet. They are labelled DERIVED / ASSUMPTION.

Run:  python3 backend/tests/test_carbon.py
"""
import copy
import json
import re
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

# ---- stubs, verbatim from test_lookahead.py --------------------------------------
_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


def _passthrough_decorator(*a, **k):
    def wrap(fn):
        return fn
    return wrap


class _App:
    def __init__(self, *a, **k):
        pass

    def get(self, *a, **k):
        return _passthrough_decorator()

    post = put = delete = patch = get

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


class _HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def _Query(default=None, **k):
    return default


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query

# G2, 16 Sep: main.py also imports Request (the overlay endpoint reads If-None-Match)
# and Response (the overlay, export and import endpoints return raw JSON / a 304).
class _Request:
    def __init__(self, headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


_fa.Request = _Request
sys.modules.setdefault("fastapi", _fa)
_mw = types.ModuleType("fastapi.middleware")
_cors = types.ModuleType("fastapi.middleware.cors")
_cors.CORSMiddleware = object
_mw.cors = _cors
sys.modules.setdefault("fastapi.middleware", _mw)
sys.modules.setdefault("fastapi.middleware.cors", _cors)
_resp = types.ModuleType("fastapi.responses")
_resp.FileResponse = lambda *a, **k: None

class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


_resp.Response = _Response
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass

    async def get_response(self, path, scope):
        return None


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="rbe_carbon_")
from portable import remove_scratch_db   # tests/portable.py: Windows cannot unlink an open SQLite file
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import derived  # noqa: E402
import costing  # noqa: E402
import config  # noqa: E402
import costlines  # noqa: E402
import carbon  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
access.set_current("planner123")
days.START_YEAR = main.START_YEAR

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def _raises(fn):
    try:
        fn()
    except Exception as e:
        return e
    return None


def near(a, b, tol=1e-6):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


FILE = conversions.load_factors_file()
CB = FILE["carbon"]
CP = carbon.params(FILE)
V = FILE["vehicles"]
EA, ER = "Artic Tipper (44t) — electric", "Rigid 8-wheeler (32t) — electric"
ART, R8 = "Artic Tipper (44t)", "Rigid 8-wheeler (32t)"

# =========================================================================== #
#  1. The factor file                                                           #
# =========================================================================== #
M = CB["materials"]
ok("⭐ the carbon block carries the six Government material classes",
   sorted(k for k in M if not k.startswith("_")) == ["aggregates", "asphalt", "average_construction", "concrete", "metals", "soils"])
ok("...each with row IDs, year 2026, Scope 3, AR4 GWP, status VERIFIED and the checked date",
   all(M[k]["year"] == 2026 and M[k]["scope"] == "Scope 3" and M[k]["gwp"] == "AR4" and M[k]["status"] == "VERIFIED"
       and M[k]["ids"] and M[k]["checked"] == "2026-10-10" and "2026" in M[k]["source"] for k in M if not k.startswith("_")))
# the brief's table, value for value (gov.uk flat file v1.2, 'Material use — Construction', kg CO2e per tonne)
ok("aggregates 7.80307 / re-used 2.21 / closed-loop 3.22398 (19_500_5000_15_1)",
   M["aggregates"]["kg_co2e_per_t"] == {"primary": 7.80307, "reused": 2.21, "closed_loop": 3.22398}
   and M["aggregates"]["ids"]["primary"] == "19_500_5000_15_1")
ok("asphalt 39.21249 / 1.73826 / 28.68398 (19_500_5012_15_1)",
   M["asphalt"]["kg_co2e_per_t"] == {"primary": 39.21249, "reused": 1.73826, "closed_loop": 28.68398}
   and M["asphalt"]["ids"]["primary"] == "19_500_5012_15_1")
ok("concrete 118.80307, no re-used row, closed-loop 3.22398 (19_500_5020_15_1) — ONE generic figure, EPD instead of grades",
   M["concrete"]["kg_co2e_per_t"] == {"primary": 118.80307, "reused": None, "closed_loop": 3.22398}
   and "EPD" in M["concrete"]["_note"] and "GGBS" in M["concrete"]["_note"])
ok("metals 3821.94858 / closed-loop 1636.68994 (19_500_5028_15_1)",
   M["metals"]["kg_co2e_per_t"]["primary"] == 3821.94858 and M["metals"]["kg_co2e_per_t"]["closed_loop"] == 1636.68994
   and M["metals"]["ids"]["primary"] == "19_500_5028_15_1")
ok("soils: NO primary factor, closed-loop 1.01398 (19_500_5035_15_1)",
   M["soils"]["kg_co2e_per_t"]["primary"] is None and M["soils"]["kg_co2e_per_t"]["closed_loop"] == 1.01398
   and M["soils"]["ids"]["closed_loop"] == "19_500_5035_15_1")
ok("average construction 74.9958 (19_500_5004_15_1)",
   M["average_construction"]["kg_co2e_per_t"]["primary"] == 74.9958 and M["average_construction"]["ids"]["primary"] == "19_500_5004_15_1")
ok("disposal: aggregates/asphalt/concrete open- and closed-loop 1.01398, landfill 1.27043",
   all(M[k]["disposal_kg_co2e_per_t"]["closed_loop"] == 1.01398 and M[k]["disposal_kg_co2e_per_t"]["open_loop"] == 1.01398
       and M[k]["disposal_kg_co2e_per_t"]["landfill"] == 1.27043 for k in ("aggregates", "asphalt", "concrete")))
ok("disposal: ⭐ soils closed-loop 1.01398, landfill 19.55376 (20_500_5229_15_1); metals landfill 1.26435",
   M["soils"]["disposal_kg_co2e_per_t"] == {"closed_loop": 1.01398, "landfill": 19.55376}
   and M["soils"]["disposal_ids"]["landfill"] == "20_500_5229_15_1" and M["metals"]["disposal_kg_co2e_per_t"]["landfill"] == 1.26435)
EL = CB["electricity"]
ok("UK electricity 2026: generation 0.13096 (7_400_4000_5_1) + T&D 0.01299 (13_402_4000_5_1); WTT 0.03682 + 0.00359",
   EL["generation_kg_co2e_per_kwh"] == 0.13096 and EL["generation_id"] == "7_400_4000_5_1"
   and EL["td_kg_co2e_per_kwh"] == 0.01299 and EL["td_id"] == "13_402_4000_5_1"
   and EL["wtt_generation_kg_co2e_per_kwh"] == 0.03682 and EL["wtt_td_kg_co2e_per_kwh"] == 0.00359)
TK = CB["transport"]["tonne_km_2026"]
ok("DESNZ 2026 tonne-km benchmarks: rigid >17 t 0.17256 (27_304_3120_14_1), artic >33 t 0.07835 (27_304_3132_14_1)",
   TK["rigid"]["kg_co2e_per_tkm"] == 0.17256 and TK["rigid"]["id"] == "27_304_3120_14_1"
   and TK["artic"]["kg_co2e_per_tkm"] == 0.07835 and TK["artic"]["id"] == "27_304_3132_14_1")
NH = CB["transport"]["nh_carbon_tool_v27"]
ok("the NH Carbon Tool v2.7 basis is the workbook's own cells (G7 0.00012111 laden, G11 unladen per a 7.5 t load)",
   NH["laden_t_co2e_per_tkm"] == 0.00012111 and near(NH["unladen_t_co2e_per_tkm"], 0.000106558666667, 1e-15)
   and "Y9" in NH["formula"] and "Z9" in NH["formula"] and NH["year"] == 2024)
ok("the tool's rules are recorded: ×2 return, five allocation categories, error over 100 %, earthworks excludes bulk",
   CB["transport"]["nh_tool_rules"]["distance_doubled_for_return"] is True
   and CB["transport"]["nh_tool_rules"]["allocation_categories"] == list(carbon.ALLOCATION)
   and CB["transport"]["nh_tool_rules"]["allocation_error_over_100pct"] is True
   and CB["transport"]["nh_tool_rules"]["earthworks_excludes_bulk_materials"] is True)
_txt = json.dumps(CB)
ok("🔴 no ICE factor anywhere in the block (ICE commercial use ended 30 Sep 2026) — only the note that says so",
   "ice_" not in _txt.lower() and "Inventory of Carbon" not in _txt and "ICE commercial use ended 30 Sep 2026" in FILE["_carbon_note"])
ok("every entry has a status in VERIFIED / DERIVED / ASSUMPTION", CB["statuses"] == ["VERIFIED", "DERIVED", "ASSUMPTION"]
   and CB["electric_hgv"]["kwh_per_km_status"] == "DERIVED" and CB["electric_hgv"]["payload_status"] == "ASSUMPTION")
ok("the 'Planned' items are listed, with no figures", len(CB["planned"]["items"]) >= 4
   and not any(ch.isdigit() and "£" in it for it in CB["planned"]["items"] for ch in it))

# the diesel factors (REVERSED 10 Oct 2026: they said VERIFY; the flat file v1.2 has been read)
_rig = ("Rigid 4-wheeler (18t)", "Rigid 6-wheeler (26t)", R8, "Truck mixer 8 m³ (32t)", "Truck mixer 6 m³ (26t)")
ok("⭐ every diesel factor now says it was verified on 10 Oct 2026 against the flat file v1.2, with the row IDs",
   all("Verified 10 Oct 2026 against the gov.uk flat file v1.2" in V[k]["_emissions_basis"] for k in V
       if not k.startswith("_") and V[k].get("fuel") == "diesel")
   and "5_304_3120_4_1" in V[R8]["_emissions_basis"] and "5_304_3132_4_1" in V[ART]["_emissions_basis"])
ok("...and none still says VERIFY", not any("VERIFY" in (v.get("_emissions_basis") or "") for v in V.values() if isinstance(v, dict)))
ok("Rigid 7.5t: 0.55 → the 2026 class figure 0.49944 (5_304_3112_4_1), pair 0.46656 / 0.54675",
   V["Rigid 7.5t"]["emissions_kg_co2e_per_km"] == 0.49944 and V["Rigid 7.5t"]["emissions_kg_co2e_per_km_empty"] == 0.46656
   and V["Rigid 7.5t"]["emissions_kg_co2e_per_km_laden"] == 0.54675 and "5_304_3112_4_1" in V["Rigid 7.5t"]["_emissions_basis"])
ok("the rigid >17 t and artic >33 t figures are unchanged (0.99773 / 0.93939)",
   all(V[k]["emissions_kg_co2e_per_km"] == 0.99773 for k in _rig) and V[ART]["emissions_kg_co2e_per_km"] == 0.93939)
EF, FLB = "Artic Flatbed (44t) — electric", "Artic Flatbed (44t)"
# NARROWED (10 Oct 2026, review): a third electric variant, for the artic flatbed — the demo's
# steel, precast and general lines run on it and could not switch to electric without one
# NARROWED 11 Oct 2026 (EU vehicles removed): eight diesel entries now (the four EU type-approval ones left the seed)
ok("⭐ fuel on every profile: diesel on all eight others, electric on the three new haulage variants",
   all(V[k]["fuel"] == "diesel" for k in V if not k.startswith("_") and k not in (EA, ER, EF))
   and sum(1 for k in V if not k.startswith("_") and k not in (EA, ER, EF)) == 8
   and V[EA]["fuel"] == "electric" and V[ER]["fuel"] == "electric" and V[EF]["fuel"] == "electric"
   and V[EF]["geometry_twin"] == FLB and V[EF]["payload_t"] == V[FLB]["payload_t"] - 3.5 and V[EF]["scenario_only"] is True)
ok("the electric variants are NEW keys beside the baked profiles (nothing renamed), scenario-only, twinned",
   ART in V and R8 in V and V[EA]["geometry_twin"] == ART and V[ER]["geometry_twin"] == R8
   and V[EA]["scenario_only"] is True and V[ER]["scenario_only"] is True)
ok("...with NO stored per-km figure (derived in one place) and a basis that says no electric HGV factor exists",
   "emissions_kg_co2e_per_km" not in V[EA] and "NO electric HGV factor" in V[EA]["_emissions_basis"])
ok("...payload 3.5 t below the twin (ZEHID), the draft +2 t allowance NOT applied, kWh/km 1.25 DERIVED",
   V[EA]["payload_t"] == V[ART]["payload_t"] - 3.5 and V[ER]["payload_t"] == V[R8]["payload_t"] - 3.5
   and "not applied" in V[ER]["_payload_basis"].lower().replace("not applied until", "not applied")
   and V[EA]["kwh_per_km"] == 1.25 and "DERIVED" in V[EA]["_kwh_basis"] and "4,500 MWh" in V[EA]["_kwh_basis"])
ok("every material category names its Government class",
   {k: c.get("carbon_material") for k, c in FILE["material_categories"].items() if not k.startswith("_")}
   == {"Earthworks / soil": "soils", "Small aggregate": "aggregates", "Large aggregate / ballast": "aggregates",
       "Precast / concrete": "concrete", "Steel / rail": "metals", "General / imported": "average_construction",
       # NARROWED 14 Oct 2026 (civils materials): the four categories added, each on its Government class
       "Ready-mixed concrete": "concrete", "Precast units": "concrete", "Structural steel / rebar": "metals",
       "Asphalt": "asphalt",
       # NARROWED 29 Oct 2026 (3b, the steel split): the three steel categories, on the same metals class
       "Rail": "metals", "Reinforcement": "metals", "Structural steel": "metals",
       # NARROWED 22 Oct 2026 (abnormal loads, B2's bare category): null ON PURPOSE — an abnormal load is left out of the
       # carbon totals (D71); the category exists for the holding-area exemption list (D63) and the picker
       "Abnormal loads": None})
ok("⭐ the file passes config.validate as it stands", config.validate(FILE) == [], str(config.validate(FILE)))

# =========================================================================== #
#  2. Material carbon                                                           #
# =========================================================================== #
ok("material = quantity × conversion × factor ÷ 1000: 500 t × 2 × 7.80307 = 7.80307 t",
   near(carbon.material_t(500, 7.80307, conversion=2.0), 7.80307))
f = carbon.material_factor(CP, "aggregates")
ok("aggregates at 0 % recycled = primary 7.80307, VERIFIED", f["kg_per_t"] == 7.80307 and f["status"] == "VERIFIED"
   and f["method"] == "primary" and f["recycled_enabled"])
f = carbon.material_factor(CP, "aggregates", recycled_pct=30)
# 7.80307 × 0.7 + 3.22398 × 0.3 = 5.462149 + 0.967194 = 6.429343
ok("⭐ aggregates at 30 % recycled: 7.80307 × 0.7 + 3.22398 × 0.3 = 6.429343 (linear blend, DERIVED)",
   near(f["kg_per_t"], 6.429343) and f["status"] == "DERIVED" and f["method"] == "blend")
ok("asphalt at 50 %: (39.21249 + 28.68398) / 2 = 33.948235",
   near(carbon.material_factor(CP, "asphalt", recycled_pct=50)["kg_per_t"], 33.948235))
ok("metals at 100 % = the closed-loop figure 1636.68994",
   near(carbon.material_factor(CP, "metals", recycled_pct=100)["kg_per_t"], 1636.68994))
f = carbon.material_factor(CP, "soils")
ok("⭐ soils: no material factor (None), recycled DISABLED with the reason — earthworks is haulage + disposal",
   f["kg_per_t"] is None and not f["recycled_enabled"] and "no primary-production factor" in f["recycled_reason"])
ok("...and recycled content on soils is refused, not guessed",
   isinstance(_raises(lambda: carbon.material_factor(CP, "soils", recycled_pct=10)), carbon.CarbonError))
f = carbon.material_factor(CP, "average_construction")
ok("average construction 74.9958, recycled disabled (no closed-loop row)", f["kg_per_t"] == 74.9958
   and not f["recycled_enabled"] and "no closed-loop" in f["recycled_reason"])
ok("recycled share outside 0–100 % is refused", isinstance(_raises(lambda: carbon.material_factor(CP, "aggregates", recycled_pct=101)), carbon.CarbonError)
   and isinstance(_raises(lambda: carbon.material_factor(CP, "aggregates", recycled_pct=-1)), carbon.CarbonError))
f = carbon.material_factor(CP, "concrete", epd={"kg_per_t": 95.0, "source": "EPD-0001 (fictional)"})
# REVERSED (10 Oct 2026, review): an EPD is TYPED, not checked by Wayscope, so it carries the
# brief's ASSUMPTION status (one of the three), with its reference as the source
ok("⭐ the EPD override replaces the generic concrete figure: 95.0, an ASSUMPTION typed with its reference",
   f["kg_per_t"] == 95.0 and f["method"] == "epd" and f["epd_source"] == "EPD-0001 (fictional)" and f["status"] == "ASSUMPTION"
   and "EPD-0001 (fictional)" in f["source"] and "not checked" in f["source"])
ok("...an EPD without its source is refused", isinstance(_raises(lambda: carbon.material_factor(CP, "concrete", epd={"kg_per_t": 95.0})), carbon.CarbonError))
ok("...a negative EPD is refused", isinstance(_raises(lambda: carbon.material_factor(CP, "concrete", epd={"kg_per_t": -1, "source": "x"})), carbon.CarbonError))
ok("re-used aggregates = the published Re-used row 2.21; re-used concrete (none published) refused",
   carbon.material_factor(CP, "aggregates", reused=True)["kg_per_t"] == 2.21
   and isinstance(_raises(lambda: carbon.material_factor(CP, "concrete", reused=True)), carbon.CarbonError))

# =========================================================================== #
#  3. Transport, both methods                                                   #
# =========================================================================== #
# The worked example of notes/carbon-why-different-1010.md §3: R001, artic tipper (29 t), Sep 15,800 t,
# 18.4 km loaded + 19.1 km return = 37.5 km a trip.
ok("vehicle-km: ceil(15,800 / 29) = 545 trips × 37.5 km × 0.93939 ÷ 1000 = 19.1988 t (the note's 19.20)",
   near(carbon.transport_vehicle_km_t(545, 37.5, 0.93939), 19.19878, 1e-5))
ok("NH tool per tonne per one-way km = 0.00012111 + 0.0001065587 = 0.0002276687 t",
   near(carbon.nh_tool_t_per_t_km(CP), 0.000227668666667, 1e-13))
ok("⭐ NH tool: 62,500 t × 18.4 km one-way → 261.82 t (the note's §3 figure, 3.45× Wayscope's 75.99)",
   near(carbon.transport_nh_t(18.4, 62500, CP), 261.8189667, 1e-4))
ok("⭐ the ×2 rule: one tonne one km = (laden + unladen) ÷ 2 × 2 — twice the average leg",
   near(carbon.transport_nh_t(1, 1, CP), 2 * (0.00012111 + 0.000106558666667) / 2, 1e-13))
ok("...and it is linear in the one-way distance (the return is doubled inside, never typed)",
   near(carbon.transport_nh_t(2, 1, CP), 2 * carbon.transport_nh_t(1, 1, CP), 1e-13))
ok("DESNZ 2026 tonne-km, artic: 62,500 × 18.4 × 0.07835 ÷ 1000 = 90.1025 t (the note rounds to 90.10)",
   near(carbon.transport_tkm_t(18.4, 62500, CP, "artic"), 90.1025, 1e-5))
ok("an unbaked distance gives None on every method, never a guess",
   carbon.transport_nh_t(None, 100, CP) is None and carbon.transport_vehicle_km_t(10, None, 0.9) is None
   and carbon.transport_tkm_t(None, 100, CP, "rigid") is None)

# =========================================================================== #
#  4. Allocation and the double-count rule                                      #
# =========================================================================== #
a = carbon.allocate(100.0, {"Fencing": 10, "Drainage": 20, "Waste": 30})
ok("allocation: 100 t at 10/20/30 % → 10/20/30, the remainder 40 Not Allocated",
   near(a["Fencing"], 10) and near(a["Drainage"], 20) and near(a["Waste"], 30) and near(a["Road Pavements"], 0)
   and near(a["Civils Structures"], 0) and near(a["Not Allocated"], 40))
ok("exactly 100 % leaves nothing Not Allocated", near(carbon.allocate(50.0, {"Road Pavements": 100})["Not Allocated"], 0))
e = _raises(lambda: carbon.allocate(100.0, {"Fencing": 60, "Drainage": 50}))
ok("⭐ allocation over 100 % is an ERROR (the tool's 'err'), and says the sum",
   isinstance(e, carbon.CarbonError) and "110" in str(e))
ok("an allocation to a category the tool does not have is refused",
   isinstance(_raises(lambda: carbon.allocate(1.0, {"Lighting": 10})), carbon.CarbonError))
ok("⭐ double count: soils go to Earthworks, every other class to Bulk Materials — one sheet per line",
   carbon.sheet_of("soils") == "Earthworks" and all(carbon.sheet_of(k) == "Bulk Materials"
                                                    for k in ("aggregates", "asphalt", "concrete", "metals", "average_construction")))
sh = carbon.split_sheets([{"id": 1, "carbon_material": "soils", "t": 5.0}, {"id": 2, "carbon_material": "aggregates", "t": 3.0},
                          {"id": 3, "carbon_material": "aggregates", "t": 2.0}])
ok("...earthworks excludes the bulk rows: Earthworks 5, Bulk 5, and the two sheets add up to the whole",
   near(sh["Earthworks"], 5.0) and near(sh["Bulk Materials"], 5.0) and near(sh["Earthworks"] + sh["Bulk Materials"], 10.0))
sh = carbon.split_sheets([{"id": 1, "carbon_material": "soils", "t": 5.0}, {"id": 2, "carbon_material": "soils", "t": 4.0, "disposal": True}])
ok("...and soil LEAVING site for a tip or a recycling site sits on Waste (the tool's 'exported off-site' rows), not Earthworks",
   near(sh["Earthworks"], 5.0) and near(sh["Waste"], 4.0) and carbon.sheet_of("soils", disposal=True) == "Waste")
ok("...a row counted twice is refused",
   isinstance(_raises(lambda: carbon.split_sheets([{"id": 1, "carbon_material": "soils", "t": 1}, {"id": 1, "carbon_material": "aggregates", "t": 1}])), carbon.CarbonError))

# =========================================================================== #
#  5. Disposal                                                                  #
# =========================================================================== #
ok("⭐ 1,000 t of soil to landfill = 19.55376 t; to closed-loop reuse = 1.01398 t (19× less)",
   near(carbon.disposal_t(1000, carbon.disposal_factor(CP, "soils", "landfill")), 19.55376)
   and near(carbon.disposal_t(1000, carbon.disposal_factor(CP, "soils", "closed_loop")), 1.01398))
ok("metals to landfill 1.26435; a route the file does not publish (aggregates combustion) is None, not 0",
   carbon.disposal_factor(CP, "metals", "landfill") == 1.26435 and carbon.disposal_factor(CP, "aggregates", "combustion") is None)
ok("an unknown disposal route is refused", isinstance(_raises(lambda: carbon.disposal_factor(CP, "soils", "sea")), carbon.CarbonError))
ok("a destination's type marks a disposal line, case-insensitively",
   carbon.disposal_route_of(CP, {"loc_type": "Landfill"}) == "landfill" and carbon.disposal_route_of(CP, {"loc_type": "soil recycling"}) == "closed_loop"
   and carbon.disposal_route_of(CP, {"loc_type": "Compound"}) is None)

# =========================================================================== #
#  6. Electric, units                                                           #
# =========================================================================== #
ok("⭐ electric kg CO2e/km = 1.25 kWh/km × (0.13096 + 0.01299) = 0.1799375, derived in conversions._emissions()",
   near(conversions._emissions(FILE, EA), 0.1799375, 1e-9))
ok("...well-to-wheel 1.25 × 0.18436 = 0.23045 (shown separately)", near(conversions.electric_kg_per_km(FILE, V[EA], "wtw"), 0.23045, 1e-9))
ok("...a stored figure on an electric entry (a fleet's measured one) wins",
   near(conversions._emissions({"vehicles": {"E": {"fuel": "electric", "kwh_per_km": 2.0, "emissions_kg_co2e_per_km": 0.3}}}, "E"), 0.3))
ok("...a live document with no carbon block still derives it from the file's electricity rows",
   near(conversions._emissions({"vehicles": {"E": {"fuel": "electric", "kwh_per_km": 1.0}}}, "E"), 0.14395, 1e-9))
# NARROWED 12 Oct 2026 (B2): the literal fallback is the published Average-HGV figure 0.89743
# (conversions.FALLBACK_KG_CO2E_PER_KM), not the 0.90 no document ever said
ok("diesel is untouched: artic 0.93939, rigid 0.99773; a document with no vehicles reads the ONE fallback 0.89743",
   conversions._emissions(FILE, ART) == 0.93939 and conversions._emissions(FILE, R8) == 0.99773
   and conversions._emissions({"vehicles": {}}, "nothing") == conversions.FALLBACK_KG_CO2E_PER_KM == 0.89743)
ff = conversions.flat_factors(FILE)["vehicle_emissions_kg_co2e_per_km"]
# NARROWED 12 Oct 2026 (B2): the file's `_default` is the published figure too (was the unpublished 0.97)
ok("the map's flat factors carry the derived electric figure, diesel unchanged, _default the published 0.89743",
   near(ff[EA], 0.1799375, 1e-9) and ff[ART] == 0.93939 and ff["_default"] == 0.89743)

# ---- 12 Oct 2026 (B2): ONE fallback rule for an unknown or null per-km factor -------------------
_B2 = {"vehicles": {"D": {"payload_t": 20, "emissions_kg_co2e_per_km": None},
                    "B": {"payload_t": 20, "emissions_kg_co2e_per_km": ""},
                    "Z": {"payload_t": 20, "emissions_kg_co2e_per_km": 0},
                    "M": {"payload_t": 20},
                    "_default": {"payload_t": 20, "emissions_kg_co2e_per_km": 0.5}}}
ok("⭐ B2: a NULL stored factor no longer raises — it reads the document's _default figure (was float(None) → TypeError)",
   conversions._emissions(_B2, "D") == 0.5 and conversions._emissions(_B2, "B") == 0.5 and conversions._emissions(_B2, "M") == 0.5)
ok("B2: an unknown vehicle reads the same _default figure", conversions._emissions(_B2, "nothing") == 0.5)
_B2n = {"vehicles": {k: dict(v) for k, v in _B2["vehicles"].items() if k != "_default"}}
ok("B2: ...and with no _default entry every one of them reads FALLBACK_KG_CO2E_PER_KM, 0.89743",
   all(conversions._emissions(_B2n, k) == 0.89743 for k in ("D", "B", "M", "nothing")))
ok("B2: a stored 0 is a figure, not a gap — 0.0, not the fallback (the zero-factor divergence closed)",
   conversions._emissions(_B2, "Z") == 0.0 and conversions._emissions(_B2n, "Z") == 0.0)
_B2d = {"vehicles": dict(_B2["vehicles"], _default={"payload_t": 20, "emissions_kg_co2e_per_km": None})}
ok("B2: a null _default figure falls through to the literal as well", conversions._emissions(_B2d, "D") == 0.89743
   and conversions._emissions(_B2d, "nothing") == 0.89743)
_ffn = conversions.flat_factors(_B2)["vehicle_emissions_kg_co2e_per_km"]
ok("⭐ B2: the flat factors /api/meta serves the map carry the RESOLVED figure for a null entry, never null",
   _ffn["D"] == 0.5 and _ffn["B"] == 0.5 and _ffn["Z"] == 0.0 and _ffn["_default"] == 0.5
   and conversions.flat_factors(_B2n)["vehicle_emissions_kg_co2e_per_km"]["_default"] == 0.89743)
_net_src = read("backend/network.py")
ok("⭐ B2: network.route_analysis reads conversions._emissions for EVERY profile — no `or _default or 0` chain of its own",
   "co2_per_km = conversions._emissions(factors, prof)" in _net_src
   and 'or default_veh.get("emissions_kg_co2e_per_km")' not in _net_src)
ok("B2: factors_diagnostics shows the resolved figure through the same function",
   '"emissions_kg_co2e_per_km": conversions._emissions(factors, prof)' in _net_src)
_conv_src = read("backend/conversions.py")
ok("B2: the two stale '0.90' notes are gone from conversions.py and neither 0.90 code literal remains",
   'emissions_kg_co2e_per_km", 0.90)' not in _conv_src and 'setdefault("_default", 0.90)' not in _conv_src
   and "else 0.90." not in _conv_src and "0.90 kg/km" not in _conv_src
   and "FALLBACK_KG_CO2E_PER_KM = 0.89743" in _conv_src)
ok("B2: the file's _default names the published row, the same figure as the constant, and no longer a 'mid figure'",
   V["_default"]["emissions_kg_co2e_per_km"] == conversions.FALLBACK_KG_CO2E_PER_KM
   and "All HGVs" in V["_default"]["_emissions_basis"] and "mid figure between" not in V["_default"]["_emissions_basis"]
   and "0.89743" in V["_default"]["_emissions_basis"])
_demo_pkg = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
_demo_doc = json.loads([r for r in _demo_pkg["tables"]["config"] if r["key"] == "factors"][0]["value"])
ok("B2: the demo package's config row carries the same _default (the live row changes only on re-import or a Config save)",
   _demo_doc["vehicles"]["_default"] == V["_default"], str(_demo_doc["vehicles"]["_default"].get("emissions_kg_co2e_per_km")))
import fairprice  # noqa: E402
_fp_src = read("backend/fairprice.py")
ok("B2: fairprice.py's unused 2.68 kg/L diesel constant is deleted; the diesel factor lives in factors.json only",
   not hasattr(fairprice, "KG_CO2E_PER_L_DIESEL") and "2.68" not in _fp_src and "2.58354" in _fp_src)
d = carbon.ev_day(75, 80, 10, 1.25, 500, 350)
# REVERSED 17 Oct 2026 (the user: UK drivers' hours; the cycle counted all as driving when its split is not given): 100 kWh
# a trip; 7 cycles = 525 min + 34.3 min charging + the 45-min break (charging ON TOP of the break) = 604.3 > 600; 6 cycles
# need 100 kWh = 17.1 min → 450 + 17.1 + 45 = 512 ≤ 600 (it was 7, one charge of 34.3, on the shift alone)
ok("⭐ electric shift: 75-min cycle, 80 km a trip, 500 kWh, 350 kW → 6 cycles under the drivers' hours (7 on the shift "
   "alone), one charge of 17.1 min", d["cycles"] == 6 and d["charges"] == 1 and near(d["charge_minutes"], 100 / 350 * 60)
   and d["feasible"] and near(d["range_per_charge_km"], 400.0) and near(d["kwh_per_trip"], 100.0), str(d))
d = carbon.ev_day(60, 40, 10, 1.25, 500, 350)
# REVERSED 17 Oct 2026: a 60-min cycle all driving hits the 9 h driving cap at 9 (it was 10 on the shift alone)
ok("...9 cycles of 50 kWh fit one 500 kWh battery: no charge, the diesel day — the 9 h driving cap (10 on the shift alone)",
   d["cycles"] == 9 and d["charges"] == 0)
d = carbon.ev_day(30, 100, 10, 1.25, 500, 350)
# REVERSED 17 Oct 2026: 13 cycles = 390 + 192.9 charging + 45 = 627.9 > 600; 12 cycles = 360 + 171.4 (1,000 kWh in 2
# stops) + 45 = 576.4 (it was 13 cycles, 3 charges, 192.9 min on the shift alone)
ok("...a short heavy cycle: 12 cycles, 2 charges, 171.4 min charging (85.7 a stop) under the drivers' hours",
   d["cycles"] == 12 and d["charges"] == 2 and near(d["charge_minutes"], 1000 / 350 * 60) and near(d["minutes_per_charge"], 1000 / 350 * 60 / 2), str(d))
# 17 Oct 2026: with its split given (75 min, 45 of them driving), the same lorry is not driving-capped; still 6, the break
d = carbon.ev_day(75, 80, 10, 1.25, 500, 350, drive_min=45)
ok("...with the cycle's driving given (45 of 75 min), the charging and the 45-min break both come out of the shift: 6 cycles",
   d["cycles"] == 6 and d["charges"] == 1, str(d))
ok("...and with no battery figures the electric day is the diesel day under the same rule (drivers_hours.lorry_day)",
   carbon.ev_day(60, 40, 10, 1.25, None, None)["cycles"] == 9 and carbon.ev_day(60, 40, 10, 1.25, None, None, drive_min=30)["cycles"] == 9)
ok("🔴 a trip longer than the battery is flagged infeasible, not sized", not carbon.ev_day(600, 450, 10, 1.25, 500, 350)["feasible"])
ok("fleet = ceil(trips ÷ (cycles a day × working days)): 545 ÷ (7 × 22) → 4; no cycle → None; no trips → 0",
   carbon.lorries_for(545, 7, 22) == 4 and carbon.lorries_for(10, None, 22) is None and carbon.lorries_for(0, None, 22) == 0)
# 17 Oct 2026 (drivers' hours, the review): the electric day with the cycle's split given; a day too short for one trip
ok("⭐ the review: with driving AND other work given, the electric day is the diesel day's rule (13 h, 60 + 30: 8 — "
   # label NARROWED 18 Oct 2026 (the user): charging is counted as working time as the cautious reading, not as a rule
   "drivers_hours.lorry_day), and charging is counted as working time, the cautious reading (30 + 30 a cycle, 125 kWh "
   "trips: fewer than 9)",
   carbon.ev_day(90, 40, 13, 1.25, None, None, drive_min=60, other_min=30)["cycles"] == 8
   and carbon.ev_day(60, 100, 10, 1.25, 500, 350, drive_min=30, other_min=30)["cycles"]
   < carbon.ev_day(60, 100, 10, 1.25, None, None, drive_min=30, other_min=30)["cycles"])
_d0 = carbon.ev_day(800, 50, 10, 1.25, 500, 350)
ok("⭐ the review: a battery that holds the trip but a day that holds none is FEASIBLE with 0 cycles, day_fits False "
   "(never the 'trip exceeds battery' flag); the fleet then counts one lorry a trip",
   _d0["cycles"] == 0 and _d0["feasible"] and _d0["day_fits"] is False
   and carbon.ev_day(60, 40, 10, 1.25, 500, 350)["day_fits"] is True and carbon.lorries_for(44, 0, 22) == 2, str(_d0))
ok("miles ↔ km 1.609344: 10 mi = 16.09344 km and back; km stays km",
   near(carbon.km_from(10, "mi"), 16.09344) and near(carbon.km_to(16.09344, "mi"), 10.0) and carbon.km_from(7, "km") == 7.0
   and carbon.KM_PER_MILE == config.KM_PER_MILE)

# =========================================================================== #
#  7. Validation and the live-document fallback                                 #
# =========================================================================== #
def _v(mut):
    d2 = copy.deepcopy(FILE)
    mut(d2)
    return config.validate(d2)


ok("validate: a fuel other than diesel/electric is refused", any("fuel must be" in x for x in _v(lambda d: d["vehicles"][ART].__setitem__("fuel", "petrol"))))
ok("validate: an electric vehicle without kwh_per_km is refused", any("kwh_per_km" in x for x in _v(lambda d: d["vehicles"][EA].pop("kwh_per_km"))))
ok("validate: a geometry twin that is not another vehicle is refused", any("geometry_twin" in x for x in _v(lambda d: d["vehicles"][EA].__setitem__("geometry_twin", EA))))
# 12 Oct 2026 (B2) — the show-risk bug of 9 Oct: a blank kg CO2e/km cell saved on Config was accepted
# (null passed `em is not None`) and then every costlines read raised and the map blanked all carbon
_null = _v(lambda d: d["vehicles"][ART].__setitem__("emissions_kg_co2e_per_km", None))
ok("⭐ B2: validate REFUSES a null (blank Config cell) emissions factor on a diesel vehicle (it passed until today)",
   bool(_null), str(_null))
ok("B2: ...and the message names the vehicle and the cell", any(f"vehicle '{ART}'" in x and "blank" in x for x in _null), str(_null))
ok("B2: a blank string is refused the same way", any(f"vehicle '{ART}'" in x for x in _v(lambda d: d["vehicles"][ART].__setitem__("emissions_kg_co2e_per_km", ""))))
ok("B2: an electric entry with NO stored figure is still the derived case — accepted", _v(lambda d: d["vehicles"][EA].__setitem__("emissions_kg_co2e_per_km", None)) == [])
ok("B2: a 0 figure (no tailpipe carbon) is accepted", _v(lambda d: d["vehicles"][ART].__setitem__("emissions_kg_co2e_per_km", 0)) == [])
ok("B2: a vehicle entry that never had the key still passes (it reads the fallback; not a Config edit)",
   _v(lambda d: d["vehicles"][ART].pop("emissions_kg_co2e_per_km")) == [])
ok("validate: a carbon_material the block does not carry is refused", any("carbon_material" in x for x in _v(lambda d: d["material_categories"]["Small aggregate"].__setitem__("carbon_material", "granite"))))
ok("validate: a negative material factor is refused", any("carbon.materials.aggregates" in x for x in _v(lambda d: d["carbon"]["materials"]["aggregates"]["kg_co2e_per_t"].__setitem__("primary", -1))))
ok("validate: a carbon block that is not an object is refused", any("carbon must be an object" in x for x in _v(lambda d: d.__setitem__("carbon", 3))))
ok("validate: a document WITHOUT the carbon block (a tenant seeded before 10 Oct) still passes",
   _v(lambda d: (d.pop("carbon"), [c.pop("carbon_material", None) for c in d["material_categories"].values()],
                 d["vehicles"].pop(EA), d["vehicles"].pop(ER))) == [])
_old = copy.deepcopy(FILE)
_old.pop("carbon")
_old["vehicles"].pop(EA); _old["vehicles"].pop(ER)
for _c in _old["material_categories"].values():
    _c.pop("carbon_material", None)
ok("⭐ fallback: a live document without the block reads the file's, key by key",
   carbon.params(_old)["materials"]["aggregates"]["kg_co2e_per_t"]["primary"] == 7.80307
   and carbon.vehicles(_old)[EA]["fuel"] == "electric" and carbon.carbon_material_of("Small aggregate", _old) == "aggregates")
_ov = copy.deepcopy(FILE)
_ov["carbon"]["materials"]["aggregates"]["kg_co2e_per_t"]["primary"] = 9.0
ok("...and a live figure wins over the file's where it is set", carbon.params(_ov)["materials"]["aggregates"]["kg_co2e_per_t"]["primary"] == 9.0
   and carbon.params(_ov)["materials"]["aggregates"]["kg_co2e_per_t"]["closed_loop"] == 3.22398)
_lv = copy.deepcopy(FILE)
_lv["vehicles"][EA]["payload_t"] = 24.0
ok("...a live electric profile wins over the file's", carbon.vehicles(_lv)[EA]["payload_t"] == 24.0)

# provenance: a figure equal to a published row is VERIFIED with its ID; electric DERIVED; anything else ASSUMPTION
_doc = carbon._doc(FILE, carbon.vehicles(FILE), CP)
ok("provenance: artic 0.93939 VERIFIED (5_304_3132_4_1); electric DERIVED; a typed figure ASSUMPTION",
   carbon.vehicle_factor(_doc, CP, ART)["status"] == "VERIFIED" and carbon.vehicle_factor(_doc, CP, ART)["id"] == "5_304_3132_4_1"
   and carbon.vehicle_factor(_doc, CP, EA)["status"] == "DERIVED"
   and carbon.vehicle_factor(carbon._doc(_doc, dict(_doc["vehicles"], X={"payload_t": 10, "emissions_kg_co2e_per_km": 0.8}), CP), CP, "X")["status"] == "ASSUMPTION")

# after the show (11 Oct 2026, notes/carbon-ui-1011 item 12): well-to-tank, read from the DESNZ 2026 flat file
_W, _T = CB["transport"]["wtt_vehicle_km_2026"], CB["transport"]["vehicle_km_2026"]
ok("🔴 the DESNZ 2026 well-to-tank HGV rows (WTT- delivery vehs & freight, average laden, km), one per tank-to-wheel row",
   {k: (r["kg_co2e_per_vkm"], r["id"]) for k, r in _W.items() if isinstance(r, dict)} == {
       "rigid_over_17t": (0.23756, "28_907_3120_4_1"), "artic_over_33t": (0.22058, "28_907_3132_4_1"),
       "rigid_3_5_to_7_5t": (0.11851, "28_907_3112_4_1"), "rigid_7_5_to_17t": (0.14453, "28_907_3116_4_1")}
   and _W["status"] == "VERIFIED" and _W["scope"] == "Scope 3" and _W["year"] == 2026 and _W["checked"] == "2026-10-11")
ok("...each matched to its tank-to-wheel row by the row ID's class and load (…_3132_4_1 ↔ …_3132_4_1), never by a name",
   all(_W[k]["id"].split("_")[2:] == _T[k]["id"].split("_")[2:] for k in _W if isinstance(_W[k], dict))
   and "FORS Silver and Gold" in _W["_note"] and "never in it" in _W["_note"])
_wa, _wr, _we = carbon.wtt_factor(_doc, CP, ART), carbon.wtt_factor(_doc, CP, R8), carbon.wtt_factor(_doc, CP, EA)
_wx = carbon.wtt_factor(carbon._doc(_doc, dict(_doc["vehicles"], X={"payload_t": 10, "emissions_kg_co2e_per_km": 0.8}), CP), CP, "X")
ok("well-to-tank per km: artic 0.22058 and rigid 0.23756 VERIFIED; electric 1.25 × (0.03682 + 0.00359) = 0.0505125 DERIVED",
   _wa["kg_per_km"] == 0.22058 and _wa["id"] == "28_907_3132_4_1" and _wa["status"] == "VERIFIED"
   and _wr["kg_per_km"] == 0.23756 and near(_we["kg_per_km"], 0.0505125, 1e-9) and _we["status"] == "DERIVED")
ok("🔴 ...a typed figure that matches no published row has NO well-to-tank row: None, never a guessed ratio", _wx is None)

# =========================================================================== #
#  8. A scenario end to end                                                     #
# =========================================================================== #
def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
    db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
    db.init_tenant()
    config.invalidate()
    config.seed_from_file(conversions)
    config.invalidate()
    costing.invalidate()


reset_db()
access.set_current("planner123")
SA, SOIL = "Small aggregate", "Earthworks / soil"
for _id, _name, _type in (("L1", "Pit A", "Quarry"), ("L2", "Compound", "Compound"), ("L3", "Tip", "Landfill"),
                          ("L4", "Soil hub", "Soil recycling"), ("L5", "Pit B", "Quarry"), ("L6", "Pit C", "Quarry"),
                          ("L7", "Pit D", "Quarry")):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)", (_id, _name, 52.5, -1.0, _type))
for _rid, _o, _d, _m in (("R1", "L1", "L2", SA), ("R2", "L5", "L2", SA), ("R3", "L2", "L3", SOIL),
                         ("R4", "L2", "L4", SOIL), ("R5", "L6", "L2", SA), ("R6", "L7", "L2", SA)):
    db.execute("INSERT INTO routes (id, origin_id, dest_id, material_category, ipt) VALUES (?, ?, ?, ?, ?)", (_rid, _o, _d, _m, "IPT 1"))


def _geom(rid, prof, leg, km, hr, alt=0):
    db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, "
               "geometry, distance_km, duration_hr) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               ("default", rid, prof, leg, alt, "[[-1,52.5],[-1.1,52.6]]", km, hr))


# R1 artic 30/30 km (0.6/0.5 h) + a HERE alternative 25/25; R1 rigid 30/30; R2 10/10; R3 20/20; R4 8/8; R5 NOT BAKED
for _rid, _p, _l, _r, _lh, _rh, _alt in (("R1", ART, 30, 30, 0.6, 0.5, 0), ("R1", ART, 25, 25, 0.5, 0.45, 1),
                                         ("R1", R8, 30, 30, 0.7, 0.6, 0), ("R2", ART, 10, 10, 0.25, 0.2, 0),
                                         ("R3", ART, 20, 20, 0.4, 0.35, 0), ("R4", ART, 8, 8, 0.2, 0.15, 0)):
    _geom(_rid, _p, "loaded", _l, _lh, _alt); _geom(_rid, _p, "return", _r, _rh, _alt)
_geom("R6", ART, "loaded", 30, 0.6)          # R6: the SAME 30 km as R1 to the same compound, return leg NOT baked


def _line(rid, sect, qty, mat, ipt):
    main.save_matrix_row(main.MatrixRow(
        route_id=rid, discipline="earthworks", section_id=sect, material_type=mat, material_description=None,
        vehicle_type=ART, submitted_by="tester", unit="t", status="Pending",
        cells=[main.Cell(month_index=10, quantity=qty)], ipt=ipt))
    main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline="earthworks", section_id=sect)


_line("R1", "WS1", 2900.0, SA, "IPT1")      # 100 trips at 29 t
_line("R3", "WS2", 5800.0, SOIL, "IPT2")    # 200 trips, muck-away to a LANDFILL
_line("R5", "WS3", 1000.0, SA, "IPT1")      # not baked
config.invalidate()

_q = {"n": 0, "x": 0}
_oq, _ox = db.query, db.execute
db.query = lambda *a, **k: (_q.__setitem__("n", _q["n"] + 1), _oq(*a, **k))[1]
db.execute = lambda *a, **k: (_q.__setitem__("x", _q["x"] + 1), _ox(*a, **k))[1]
try:
    S = carbon.scenario(spend_m=2.0, allocation={SA: {"Road Pavements": 60, "Drainage": 30}}, alternatives=[
        {"name": "Greener", "levers": [
            {"driver": "recycled", "scope": {"category": SA}, "pct": 30},
            {"driver": "disposal", "scope": {"route_id": "R3"}, "to_route": "R4"},
            {"driver": "fuel", "fuel": "electric"}]},
        {"name": "Rigids", "levers": [{"driver": "vehicle", "scope": {"category": SA}, "vehicle": R8}]},
        {"name": "Six-wheelers", "levers": [{"driver": "vehicle", "scope": {"route_id": "R1"}, "vehicle": "Rigid 6-wheeler (26t)"}]},
        {"name": "Alt route", "levers": [{"driver": "route", "scope": {"route_id": "R1"}, "alt_index": 1}]},
        {"name": "Alt 2", "levers": [{"driver": "route", "scope": {"route_id": "R1"}, "alt_index": 2}]},
        {"name": "Nearer pit", "levers": [{"driver": "source", "scope": {"route_id": "R1"}, "to_route": "R2"}]},
        {"name": "80 %", "levers": [{"driver": "source", "scope": {"route_id": "R1"}, "distance_pct": 80}]},
        {"name": "EPD", "levers": [{"driver": "material", "scope": {"category": SA}, "epd": {"kg_per_t": 5.0, "source": "EPD-T1 (fictional)"}}]},
    ])
finally:
    db.query, db.execute = _oq, _ox
ok("🔴 a scenario writes nothing", _q["x"] == 0, str(_q))
ok("...and stays inside a sane statement budget", _q["n"] <= 80, str(_q))

B = S["baseline"]["totals"]
# R1: material 2900 × 7.80307 = 22.628903; transport 100 × 60 × 0.93939 = 5.63634
# R3: disposal (to a Landfill) 5800 × 19.55376 = 113.411808; transport 200 × 40 × 0.93939 = 7.51512
# R5: material 1000 × 7.80307 = 7.80307; transport NONE (not baked)
ok("⭐ baseline total 156.995 t = material 30.432 + transport 13.151 + disposal 113.412",
   near(B["total_t"], 156.995, 0.002) and near(B["material_t"], 30.432, 0.002) and near(B["transport_t"], 13.151, 0.002)
   and near(B["disposal_t"], 113.412, 0.002), str(B))
CL = {l["route_id"]: l for l in costlines.lines(status="Approved")["lines"]}
LN = {l["route_id"]: l for l in S["lines"]}
ok("⭐ ONE number: the baseline's transport on R1 equals the Dashboard's costlines.co2_t (5.636)",
   near(LN["R1"]["transport_t"], CL["R1"]["co2_t"], 0.0006) and near(CL["R1"]["co2_t"], 5.636, 0.0005))
ok("🔴 the unbaked line has NO transport carbon and is excluded (and the totals say so); its material still counts",
   LN["R5"]["transport_t"] is None and "UNBAKED" in LN["R5"]["flags"] and B["excludes_unbaked"] and B["baked_lines"] == 2
   and near(LN["R5"]["material_t"], 7.80307, 0.001))
ok("the muck-away line is a DISPOSAL line (destination type Landfill): no material factor, soils to landfill",
   LN["R3"]["disposal_route"] == "landfill" and LN["R3"]["material_t"] is None and near(LN["R3"]["disposal_t"], 113.412, 0.001))
ok("the NH tool basis is shown beside, never in, the headline: R1 30 km × 2,900 t × 0.0002276687 = 19.807",
   near(LN["R1"]["transport_nh_t"], 19.807, 0.001) and near(B["transport_nh_t"], 19.807 + 20 * 5800 * 0.000227668667, 0.002))
# REVERSED (10 Oct 2026, review): the soil line goes to a LANDFILL — the NH tool reports soil
# exported off site under Waste, so it is the Waste sheet, not Earthworks
ok("sheets: Bulk Materials 36.068 (the aggregate lines) and Waste 120.927 (the soil to landfill) — together the total",
   near(S["baseline"]["sheets"]["Bulk Materials"], 36.068, 0.002) and near(S["baseline"]["sheets"]["Waste"], 120.927, 0.002)
   and near(S["baseline"]["sheets"]["Earthworks"], 0.0) and LN["R3"]["sheet"] == "Waste"
   and near(S["baseline"]["sheets"]["Bulk Materials"] + S["baseline"]["sheets"]["Waste"], B["total_t"], 0.003))
AL = S["baseline"]["allocation"]
ok("allocation: Small aggregate's 36.068 t at 60 % Road Pavements / 30 % Drainage; the rest Not Allocated",
   near(AL["Road Pavements"], 21.641, 0.002) and near(AL["Drainage"], 10.820, 0.002) and near(AL["Not Allocated"], 124.534, 0.003))
BM = S["baseline"]["benchmarks"]
# 13.15146 t over 8,700 baked t; 203,000 t·km against the artic 0.07835; laden 7,000 of 14,000 km
ok("benchmarks: 1.512 kg per tonne delivered; 0.06479 kg per t·km vs DESNZ artic 0.07835 → 17.3 % below the national average",
   near(BM["kg_co2e_per_t_delivered"], 1.512, 0.001) and near(BM["kg_co2e_per_tkm"], 0.06479, 0.00001)
   and BM["desnz_kg_co2e_per_tkm"] == 0.07835 and BM["vs_national_average_pct"] == -17.3, str(BM))
ok("...laden share 50 %, zero-emission deliveries 0 %, 78.5 tCO2e per £m on £2m typed, NH's restated 159 → 181 beside it",
   BM["laden_share_pct"] == 50.0 and BM["zero_emission_share_pct"] == 0.0 and BM["t_co2e_per_gbp_m"] == 78.5
   # REVERSED 11 Oct 2026: NH restated its intensity at 2023 prices (annual progress report 2025-26, §4 fn 1):
   # 159 (2024/25) → 181 (2025/26), a RISE — it replaces the superseded 210 → 148 of the 2025 update
   and BM["nh_kpi"]["series"] == {"2024_25": 159, "2025_26": 181} and BM["nh_kpi"]["price_base"] == "2023 prices"
   and "annual progress report 2025-26" in BM["nh_kpi"]["source"] and BM["nh_kpi"]["status"] == "VERIFIED")
FB = S["baseline"]["fleet"]
# R1 cycle 0.6 + 0.5 + 0.4 h turnaround = 1.5 h → 6 a day → ceil(100 / 132) = 1; R3 1.15 h → 8 → ceil(200 / 176) = 2
ok("baseline fleet: 3 artics in the peak month (1 on R1, 2 on R3); the unbaked line is unsized, not zero",
   FB["lorries_peak"] == 3 and FB["unsized_lines"] == 1, str(FB))

A = {a["name"]: a for a in S["alternatives"]}
G = A["Greener"]
# R1 18.645095 + 1.230773 (114 electric trips × 60 km × 0.1799375); R3→R4 0.656412 + 5.881084; R5 6.429343
ok("⭐ alternative 'Greener' = 32.843 t, 124.153 t (79.1 %) below the baseline",
   near(G["totals"]["total_t"], 32.843, 0.002) and near(G["delta_t"], -124.153, 0.003) and G["delta_pct"] == -79.1, str(G["totals"]))
ok("⭐ drivers RANKED by tCO2e moved: disposal −112.040, diesel→electric −10.280, recycled −5.358",
   [d["driver"] for d in G["drivers"]] == ["disposal", "fuel", "recycled"]
   and near(G["drivers"][0]["delta_t"], -112.040, 0.002) and near(G["drivers"][1]["delta_t"], -10.280, 0.002)
   and near(G["drivers"][2]["delta_t"], -5.358, 0.002), str(G["drivers"]))
ok("...each driver is its levers ALONE on the baseline; the interaction (+3.524) is shown, not hidden",
   near(G["interaction_t"], 3.524, 0.003) and near(sum(d["delta_t"] for d in G["drivers"]) + G["interaction_t"], G["delta_t"], 0.003))
ok("...all deliveries zero-emission in 'Greener' (every artic has an electric variant)",
   G["benchmarks"]["zero_emission_share_pct"] == 100.0 and G["totals"]["electric_trips"] == G["totals"]["trips"])
ok("...an alternative keeps the baseline's baked set (2 of 3) — no line dropped to look like a saving",
   G["totals"]["baked_lines"] == B["baked_lines"])
ok("vehicle: rigid 8-wheelers on R1 cost MORE — 145 trips × 60 × 0.99773 = 8.680 vs 5.636 (+3.044)",
   near(A["Rigids"]["delta_t"], 3.044, 0.002))
ok("🔴 a vehicle with no baked geometry keeps the line, on the baseline vehicle's km, FLAGGED",
   near(A["Six-wheelers"]["delta_t"], 10.895 - 5.636, 0.002) and A["Six-wheelers"]["totals"]["flags"].get("KM_FROM_BASELINE_VEHICLE") == 1)
ok("haul route: HERE alternative 1 (25 + 25 km) saves 0.939 t", near(A["Alt route"]["delta_t"], -0.939, 0.001))
ok("...an alternative that is not baked is flagged and changes nothing",
   near(A["Alt 2"]["delta_t"], 0.0, 0.0005) and A["Alt 2"]["totals"]["flags"].get("ALT_ROUTE_NOT_BAKED") == 1)
ok("source: the nearer supplier (R2, 10 + 10 km to the same compound) saves 3.758 t",
   near(A["Nearer pit"]["delta_t"], -3.758, 0.001))
ok("source: 80 % of the baked distance saves 1.127 t and is flagged as a typed scaling",
   near(A["80 %"]["delta_t"], -1.127, 0.001) and A["80 %"]["totals"]["flags"].get("KM_SCALED") == 1)
ok("material: a supplier EPD of 5.0 kg/t on the aggregates saves (7.80307 − 5) × 3.9 = 10.932 t",
   near(A["EPD"]["delta_t"], -10.932, 0.002))
FC = S["fleet_compare"]
# R1: 114 electric trips at 25.5 t, 90-min cycle, 75 kWh a trip → 6 a day → 1; R3: 228 trips, 69-min, 50 kWh → 8 → 2
ok("⭐ diesel vs electric, same tonnage: 300 → 342 trips, 3 → 3 lorries, 13.151 → 2.872 t, 19,950 kWh",
   FC["lines"] == 2 and FC["diesel"]["trips"] == 300 and FC["electric"]["trips"] == 342
   and FC["diesel"]["lorries_peak"] == 3 and FC["electric"]["lorries_peak"] == 3
   and near(FC["diesel"]["transport_t"], 13.151, 0.002) and near(FC["electric"]["transport_t"], 2.872, 0.002)
   and near(FC["electric"]["kwh"], 19950.0, 0.1) and near(FC["delta_t"], -10.280, 0.002), json.dumps(FC)[:600])
ok("...with the electric day stated: payload 25.5 t (twin 29), 500 kWh, 350 kW, 400 km on one charge, no charge needed",
   FC["electric_profiles"][0]["payload_t"] == 25.5 and FC["electric_profiles"][0]["twin_payload_t"] == 29
   and FC["range_per_charge_km_min"] == 400.0 and FC["charges_per_lorry_day_max"] == 0 and FC["infeasible_lines"] == 0
   and FC["electric_profiles"][0]["status"] == "ASSUMPTION")

e = _raises(lambda: carbon.scenario(alternatives=[{"name": "x", "levers": [{"driver": "source", "scope": {"route_id": "R1"}, "to_route": "R3"}]}]))
ok("a supplier swap to a route with another destination is refused", isinstance(e, carbon.CarbonError) and "destination" in str(e))
ok("an unknown driver, an unknown vehicle and a recycled share over 100 are refused",
   all(isinstance(_raises(lambda lv=lv: carbon.scenario(alternatives=[{"name": "x", "levers": [lv]}])), carbon.CarbonError)
       for lv in ({"driver": "weather"}, {"driver": "vehicle", "vehicle": "Hovercraft"}, {"driver": "recycled", "pct": 140})))
ok("allocation over 100 % refuses the whole scenario",
   isinstance(_raises(lambda: carbon.scenario(allocation={SA: {"Fencing": 70, "Waste": 40}})), carbon.CarbonError))

OP = S["options"]
_om = {m["category"]: m for m in OP["materials"]}
ok("options: each category in view with its class, sheet, factors and whether recycled is allowed (with the reason)",
   _om[SA]["carbon_material"] == "aggregates" and _om[SA]["recycled_enabled"] and _om[SOIL]["sheet"] == "Earthworks"
   and not _om[SOIL]["recycled_enabled"] and "primary" in _om[SOIL]["recycled_reason"])
ok("options: the electric variant is offered beside the artic it twins, with its DERIVED factor",
   any(v["vehicle"] == EA and v["status"] == "DERIVED" and v["geometry_twin"] == ART for v in OP["vehicles"]))
_or = {r["route_id"]: r for r in OP["routes"]}
ok("options: R1's other suppliers to the same compound, each saying whether it is baked, and R1's baked HERE alternatives (0, 1)",
   _or["R1"]["suppliers"] == [{"route_id": "R2", "origin_name": "Pit B", "baked": True}, {"route_id": "R5", "origin_name": "Pit C", "baked": False},
                              {"route_id": "R6", "origin_name": "Pit D", "baked": True}]
   and _or["R1"]["alts"][ART] == [0, 1])
ok("options: R3 is a landfill line with R4 (the soil hub, closed-loop) as another destination; soils publish landfill and closed-loop only",
   _or["R3"]["disposal_route"] == "landfill"
   and _or["R3"]["destinations"] == [{"route_id": "R4", "dest_name": "Soil hub", "disposal_route": "closed_loop", "baked": True}]
   and _or["R3"]["disposal_routes"] == ["landfill", "closed_loop"] and _om[SA]["disposal_routes"] == ["landfill", "closed_loop", "open_loop"])
_pk = {p["key"]: p for p in S["factors"]}
ok("⭐ every factor used carries source, year and status (and the gov.uk row ID where one exists)",
   all(p.get("status") and ("year" in p) for p in S["factors"])
   and _pk["material:aggregates"]["ids"]["primary"] == "19_500_5000_15_1" and _pk[f"vehicle:{ART}"]["status"] == "VERIFIED"
   and _pk[f"vehicle:{EA}"]["status"] == "DERIVED" and _pk["electricity"]["value"] == 0.14395
   and _pk["kwh_per_km"]["status"] == "DERIVED" and _pk["zev_allowance"]["status"] == "ASSUMPTION")
ok("the known limits and the Planned items travel with every answer",
   len(S["limits"]) >= 7 and any("draft" in x for x in S["limits"]) and any("AR4" in x for x in S["limits"])
   and len(S["planned"]) >= 4 and S["unit"] == "km")

# =========================================================================== #
#  8c. The adversarial review of 10–11 Oct 2026 — each confirmed defect, asserted  #
# =========================================================================== #
def _alt(levers, **kw):
    return carbon.scenario(alternatives=[{"name": "x", "levers": levers}], **kw)["alternatives"][0]


a = _alt([{"driver": "disposal", "scope": {"route_id": "R3"}, "to": "open_loop"}])
ok("🔴 review: a disposal route with NO published factor (soils, open-loop) is never counted as zero — unchanged, with a note",
   near(a["delta_t"], 0.0, 0.0005) and any("open-loop" in n and "Earthworks / soil" in n for n in a["notes"]), str(a["notes"]))
ok("...and a destination type whose factor is unpublished is flagged NO_DISPOSAL_FACTOR with its tonnes counted, never 0",
   carbon.disposal_factor(CP, "average_construction", "landfill") is None and carbon.FLAG_NO_DISPOSAL_FACTOR == "NO_DISPOSAL_FACTOR")
a = _alt([{"driver": "disposal", "scope": {"category": SA}, "to": "closed_loop"}])
ok("🔴 review: a disposal lever reaches only lines going to a tip or recycling site — quarry deliveries are unchanged",
   near(a["delta_t"], 0.0, 0.0005) and any("only to lines going to a tip" in n for n in a["notes"]))
a = _alt([{"driver": "disposal", "to": "closed_loop"}])
# R3 only: 5,800 × (1.01398 − 19.55376) = −107.530 t (the aggregate deliveries keep their production carbon)
ok("...an UNSCOPED 'send waste to recycling' moves only the soil to landfill: −107.530 t, not the aggregates' production carbon",
   near(a["delta_t"], -107.530, 0.002), str(a["delta_t"]))
e = _raises(lambda: _alt([{"driver": "material", "epd": {"kg_per_t": 5.0, "source": "EPD-X"}}]))
ok("🔴 review: an EPD is one product's figure — an unscoped EPD is refused", isinstance(e, carbon.CarbonError) and "scope it" in str(e))
a = _alt([{"driver": "material", "scope": {"route_id": "R1"}, "epd": {"kg_per_t": 5.0, "source": "EPD-R1"}}])
ok("...scoped to a route it applies to that route's line only: (7.80307 − 5) × 2.9 = −8.129 t", near(a["delta_t"], -8.129, 0.001))
a = _alt([{"driver": "source", "scope": {"route_id": "R1"}, "to_route": "R5"}])
ok("🔴 review: a swap to a supplier whose route is NOT baked is left out and flagged — never R1's own km under R5's name",
   near(a["delta_t"], 0.0, 0.0005) and a["totals"]["flags"].get("ROUTE_SWAP_NOT_BAKED") == 1 and a["drivers"][0]["lines_changed"] == 0)
a = _alt([{"driver": "source", "scope": {"route_id": "R1"}, "to_route": "R6"}])
ok("🔴 review: a swap to the SAME 30 km whose return leg is not baked is not a saving: the loaded leg stands in, flagged",
   near(a["delta_t"], 0.0, 0.0005) and a["totals"]["flags"].get("RETURN_STAND_IN") == 1, str(a["delta_t"]))

# an electric trip longer than the battery stays diesel (battery 50 kWh: R1's 75 kWh trip cannot, R3's 50 kWh can)
_lv = json.loads(json.dumps(config.load(conversions, use_cache=False)))
_lv["vehicles"][EA]["battery_kwh_usable"] = 50
ok("(a 50 kWh battery saves)", config.save(_lv, by="harness", network=network)["ok"])
config.invalidate()
SE = carbon.scenario(alternatives=[{"name": "e", "levers": [{"driver": "fuel", "fuel": "electric"}]}])
FE = SE["fleet_compare"]
ok("🔴 review: an electric trip that needs more than one battery is NOT credited — R1 stays diesel; only R3 moves (−5.874)",
   near(SE["alternatives"][0]["drivers"][0]["delta_t"], -5.874, 0.002) and SE["alternatives"][0]["totals"]["flags"].get("EV_TRIP_EXCEEDS_BATTERY") == 1)
ok("...and it is left out of BOTH sides of the diesel/electric comparison (1 line compared, 1 infeasible)",
   FE["lines"] == 1 and FE["infeasible_lines"] == 1 and FE["diesel"]["trips"] == 200 and FE["electric"]["trips"] == 228, json.dumps(FE)[:300])
config.reset_to_file(conversions, by="harness")
config.invalidate()

# REVERSED 17 Oct 2026 (UK drivers' hours): 7 cycles = 420 + 154.3 + 45 = 619.3 > 600; 6 cycles: 1,200 kWh from a full
# 500 = 700 kWh in 2 stops (400 then 300, each topped up only to what the rest of the day needs), 120 min, 60 a stop —
# still simulated trip by trip (not 1 of 120); it was 7 cycles, 3 stops of 51.4 on the shift alone
ok("🔴 review: charging is simulated trip by trip — 200 kWh trips on 500 kWh: 6 cycles, 2 stops of 60.0 min (not 1 of 120)",
   carbon.ev_day(60, 160, 10, 1.25, 500, 350)["cycles"] == 6 and carbon.ev_day(60, 160, 10, 1.25, 500, 350)["charges"] == 2
   and near(carbon.ev_day(60, 160, 10, 1.25, 500, 350)["minutes_per_charge"], 700 / 350 * 60 / 2, 1e-6))
ok("...and the range is named for what it is: the range on ONE charge", "range_per_charge_km" in carbon.ev_day(60, 40, 10, 1.25, 500, 350)
   and "daily_range_km" not in carbon.ev_day(60, 40, 10, 1.25, 500, 350))
# 17 Oct 2026 (drivers' hours, the review): the swapped route: at the route's own distance the row's trips a day ARE the answer; scaled, lorry_day on the scaled split
_seen = []
_eval0 = carbon._eval
carbon._eval = lambda line, s, ctx: (_seen.append(_eval0(line, s, ctx)) or _seen[-1])
try:
    _rows = {r["profile"]: r for r in network.route_analysis("R1").get("rows", []) if r.get("alt_index") == 0}
    _base_veh = {x["vehicle"] for x in carbon.scenario()["lines"] if x["route_id"] == "R1"}
    _other = next((k for k in sorted(_rows) if k not in _base_veh and "electric" not in k), None)
    _seen.clear()
    _alt([{"driver": "vehicle", "scope": {"route_id": "R1"}, "vehicle": _other}])
    _sw = [e for e in _seen if e["route_id"] == "R1" and e["vehicle"] == _other and e["baked"]]
    _rw = _rows.get(_other)
    ok("⭐ the review: a vehicle swap at the route's own distance reads route_analysis's trips a day for that vehicle "
       "(no recomputing from rounded hours)",
       bool(_sw) and _rw is not None and all(e["cycles_per_day"] == _rw["trips_per_day"] for e in _sw),
       str((_other, sorted(_rows), [(e["cycles_per_day"], (_rw or {}).get("trips_per_day")) for e in _sw[:2]])))
    _seen.clear()
    _alt([{"driver": "source", "scope": {"route_id": "R1"}, "distance_pct": 50}])
    _sc = [e for e in _seen if e["route_id"] == "R1" and e["baked"] and e["cycles_per_day"] is not None
           and e["vehicle"] in _rows and abs((e["one_way_km"] or 0) - float(_rows[e["vehicle"]]["loaded_km"]) * 0.5) < 1e-6]
    import drivers_hours  # noqa: E402
    _int = lambda r: float((r.get("turnaround_parts") or {}).get("internal_travel_minutes") or 0.0)  # noqa: E731
    _want = lambda r: drivers_hours.lorry_day(  # noqa: E731
        drivers_hours.shift_hours(config.load(conversions))[0], (r["drive_min"] - _int(r)) * 0.5 + _int(r), r["other_work_min"],
        typed_shift_h=drivers_hours.typed_shift_hours(config.load(conversions)))["trips"]
    ok("...and at half the distance: drivers_hours.lorry_day on the halved legs, the gate minutes and other work kept",
       bool(_sc) and all(e["cycles_per_day"] == _want(_rows[e["vehicle"]]) for e in _sc)
       and any(e["cycles_per_day"] > _rows[e["vehicle"]]["trips_per_day"] for e in _sc),
       str([(e["vehicle"], e["cycles_per_day"], _want(_rows[e["vehicle"]])) for e in _sc[:3]]))
finally:
    carbon._eval = _eval0
a = _alt([{"driver": "material", "reused": True}])
# R1 2,900 × (2.21 − 7.80307) = −16.2199; R5 1,000 × (2.21 − 7.80307) = −5.5931; soils: no re-used row → unchanged
ok("🔴 review: an unscoped 're-used' applies where a re-used row is published and notes the rest (−21.813 t), never fails",
   near(a["delta_t"], -21.813, 0.002) and any("re-used" in n for n in a["notes"]), str(a))
for _label, _lev in (("a scope that is not an object", {"driver": "recycled", "scope": "all", "pct": 10}),
                     ("a distance of NaN", {"driver": "source", "distance_pct": "nan"}),
                     ("an infinite alternative index", {"driver": "route", "alt_index": "inf"}),
                     ("a lever that is not an object", "recycled")):
    ok(f"🔴 review: {_label} is a CarbonError (a 400), never a 500 or a NaN total",
       isinstance(_raises(lambda lv=_lev: _alt([lv])), carbon.CarbonError))
ok("🔴 review: an allocation that is not a set of percentages is a CarbonError",
   isinstance(_raises(lambda: carbon.scenario(allocation={SA: [10]})), carbon.CarbonError))
a = _alt([{"driver": "recycled", "scope": {"category": SA}, "pct": 13}])
ok("review: a lone lever has NO interaction (deltas taken on unrounded sums) and its driver equals the whole delta",
   a["interaction_t"] == 0.0 and a["drivers"][0]["delta_t"] == a["delta_t"], str((a["interaction_t"], a["delta_t"], a["drivers"])))
_part = {"vehicles": {"E": {"fuel": "electric", "kwh_per_km": 1.25}}, "carbon": {"electricity": {"generation_kg_co2e_per_kwh": 0.2}}}
ok("review: a partial live electricity block merges key by key — the map's figure and the Carbon page's are the same number",
   near(conversions._emissions(_part, "E"), 1.25 * (0.2 + 0.01299), 1e-9)
   and near(carbon.vehicle_factor(carbon._doc(_part, _part["vehicles"], carbon.params(_part)), carbon.params(_part), "E")["kg_per_km"],
            1.25 * (0.2 + 0.01299), 1e-9))
_ev2 = carbon._doc(FILE, dict(carbon.vehicles(FILE), **{EA: dict(V[EA], kwh_per_km=1.8)}), CP)
ok("review: a profile's OWN kWh/km is an ASSUMPTION (not credited to ZEHID); the 1.25 default stays DERIVED",
   carbon.vehicle_factor(_ev2, CP, EA)["status"] == "ASSUMPTION" and "ASSUMPTION typed on the profile" in carbon.vehicle_factor(_ev2, CP, EA)["source"]
   and carbon.vehicle_factor(_doc, CP, EA)["status"] == "DERIVED")
ok("review: the tonne-km benchmark is read for each vehicle's SIZE class (a 7.5 t rigid against 0.54001, not the >17 t 0.17256)",
   carbon.tkm_class("rigid", 7.5) == "rigid_3_5_7_5" and carbon.tkm_factor(CP, "rigid_3_5_7_5") == 0.54001
   and carbon.tkm_class("rigid", 12) == "rigid_7_5_17" and carbon.tkm_factor(CP, "rigid_7_5_17") == 0.43002
   and carbon.tkm_class("rigid", 32) == "rigid" and carbon.tkm_class("artic", 44) == "artic" and carbon.tkm_class("artic", 30) == "artic_3_5_33"
   and carbon.tkm_factor(CP, "artic_3_5_33") == 0.12292)
_e1 = {"baked": True, "flags": [], "tonnes": 100.0, "one_way_km": 10.0, "transport_t": 0.2, "vkm": 200.0, "laden_km": 100.0, "tkm_class": "artic", "vehicle_class": "artic"}
_e2 = {"baked": True, "flags": ["RETURN_NOT_BAKED"], "tonnes": 100.0, "one_way_km": 10.0, "transport_t": 0.1, "vkm": 100.0, "laden_km": 100.0, "tkm_class": "artic", "vehicle_class": "artic"}
_bm = carbon.benchmarks({"total_t": 0.3, "tonnes": 200.0, "electric_trips": 0, "trips": 20}, [_e1, _e2], CP)
ok("🔴 review: a line counting its loaded leg only is left OUT of the benchmarks (it would read as empty-free), and counted",
   _bm["kg_co2e_per_t_delivered"] == 2.0 and _bm["kg_co2e_per_tkm"] == 0.2 and _bm["laden_share_pct"] == 50.0 and _bm["excluded_lines"] == 1, str(_bm))
SA2 = carbon.scenario(allocation={"R1": {"Road Pavements": 100}, SA: {"Drainage": 50}})["baseline"]["allocation"]
# R1 (22.628903 + 5.63634) all to Road Pavements; R5 (Small aggregate, no route key) 50 % Drainage; the soil line unallocated
ok("review: allocation is per ROW where a route is named (R1 → Road Pavements 28.265), else per category (R5 → Drainage 3.902)",
   near(SA2["Road Pavements"], 28.265, 0.002) and near(SA2["Drainage"], 3.902, 0.002) and near(SA2["Not Allocated"], 124.828, 0.003), str(SA2))
_pk2 = {f["key"]: f for f in S["factors"]}
ok("review: the factors list carries what the ALTERNATIVES used — the 30 % blend (DERIVED, 6.42934) and the typed EPD (ASSUMPTION)",
   _pk2.get("blend:aggregates:30.0", {}).get("status") == "DERIVED" and near(_pk2["blend:aggregates:30.0"]["value"], 6.42934, 1e-5)
   and _pk2.get("epd:Small aggregate:5.0", {}).get("status") == "ASSUMPTION" and "EPD-T1 (fictional)" in _pk2["epd:Small aggregate:5.0"]["source"])
ok("review: each line says which factor it used, how, and its status", all(k in S["lines"][0] for k in ("kg_per_km", "factor_status", "material_kg_per_t", "material_method", "material_status")))

# validation: every shape the planner reads is checked, so no Config save can make every scenario fail
for _label, _mut in (("a material figure typed as a bare number", lambda d: d["carbon"]["materials"]["aggregates"].__setitem__("kg_co2e_per_t", 7.8)),
                     ("transport that is not an object", lambda d: d["carbon"].__setitem__("transport", "x")),
                     ("disposal site types as a list", lambda d: d["carbon"].__setitem__("disposal_loc_types", ["landfill"])),
                     ("a disposal site type mapped to an unknown route", lambda d: d["carbon"]["disposal_loc_types"].__setitem__("tip", "sea")),
                     ("a non-numeric NH tool factor", lambda d: d["carbon"]["transport"]["nh_carbon_tool_v27"].__setitem__("laden_t_co2e_per_tkm", "x")),
                     ("a negative tonne-km benchmark", lambda d: d["carbon"]["transport"]["tonne_km_2026"]["artic"].__setitem__("kg_co2e_per_tkm", -1)),
                     ("materials as a list", lambda d: d["carbon"].__setitem__("materials", [1])),
                     ("a carbon_material that is a list", lambda d: d["material_categories"]["Small aggregate"].__setitem__("carbon_material", ["x"]))):
    ok(f"🔴 review: validate refuses {_label} (and does not crash)", bool(_v(_mut)), _label)
ok("review: a PARTIAL live carbon block (one figure overridden) is accepted — the planner merges it with the file",
   _v(lambda d: d.__setitem__("carbon", {"materials": {"aggregates": {"kg_co2e_per_t": {"primary": 9.0}}}})) == [])
_off = copy.deepcopy(FILE)
_off["carbon"]["materials"]["aggregates"]["kg_co2e_per_t"]["closed_loop"] = None
_off["material_categories"]["General / imported"]["carbon_material"] = None
ok("review: an explicit null in the live document switches a figure or a category OFF (it no longer falls back to the file)",
   not carbon.material_factor(carbon.params(_off), "aggregates")["recycled_enabled"]
   and carbon.carbon_material_of("General / imported", _off) is None and carbon.carbon_material_of("Small aggregate", _off) == "aggregates")
_calls = {"n": 0}
_real_lff = conversions.load_factors_file
conversions.load_factors_file = lambda: (_calls.__setitem__("n", _calls["n"] + 1), _real_lff())[1]
conversions._FILE_CACHE["doc"] = None
try:
    carbon.scenario(factors=_old, alternatives=[{"name": "e", "levers": [{"driver": "fuel", "fuel": "electric"}]}])
finally:
    conversions.load_factors_file = _real_lff
ok("review: on a tenant without the block (the live demo) factors.json is parsed ONCE per change, not once per line",
   _calls["n"] <= 1, str(_calls))

# 11 Oct 2026 — the plain-English pass: the server's words, the lorry-load difference, the NH figure
ok("the ranked decisions carry NH / CLOCS / EA words (custom carbon factor, vehicle choice, receiving site and disposal method)",
   carbon.DRIVER_LABELS == {"material": "Custom carbon factor (supplier EPD) or reused material", "recycled": "Recycled content",
                            "source": "Supplier and haul distance", "route": "Haul route", "vehicle": "Vehicle choice",
                            "fuel": "Battery electric lorries", "disposal": "Receiving site and disposal method"}
   and [d["label"] for d in G["drivers"]] == ["Receiving site and disposal method", "Battery electric lorries", "Recycled content"])
# 335 approved loads (100 + 200 + ceil(1,000 / 29) = 35) against 382 (114 + 228 + 40 electric): 47 more, each lorry carries less
ok("the change in lorry loads comes from the server: 'Greener' is 47 MORE loads (electric lorries carry less per load)",
   G["delta_trips"] == 47 and sum(m["trips"] for m in G["by_month"]) - sum(m["trips"] for m in S["baseline"]["by_month"]) == 47
   # Rigids: R1 145 − 100, and the unrouted line 1,000 t at 20 t (50) against 29 t (35): +15, loads count even with no km
   and A["Rigids"]["delta_trips"] == (145 - 100) + (50 - 35), str((G.get("delta_trips"), A["Rigids"].get("delta_trips"))))
ok("🔴 the file no longer carries the superseded NH 210 → 148; its commitment is quoted with the report named",
   "nh_kpi_t_co2e_per_gbp_m" not in CB["benchmarks"] and CB["benchmarks"]["nh_kpi_2023_prices"]["2025_26"] == 181
   and CB["benchmarks"]["nh_target"].startswith('National Highways commitment: "100% electric or hydrogen heavy vehicles deliver to our sites by 2040"'))
_old_kpi = copy.deepcopy(FILE)
_old_kpi["carbon"]["benchmarks"] = {"nh_kpi_t_co2e_per_gbp_m": {"2023_24": 210, "2024_25": 148}}
ok("🔴 ...and a live document still carrying the old key can never feed it: the page reads only the restated series",
   carbon.benchmarks({"total_t": 1.0, "tonnes": 1.0, "electric_trips": 0, "trips": 1}, [], carbon.params(_old_kpi))["nh_kpi"]["series"]
   == {"2024_25": 159, "2025_26": 181})

# after the show (11 Oct 2026, notes/carbon-ui-1011 items 8, 9, 11–14): every figure hand-worked from the fixture
ok("item 12 ⭐ well-to-wheel: artic WTT 0.22058 per km × (R1 6,000 + R3 8,000 km) = 3.088 t, beside 13.151 tank-to-wheel → 16.240",
   near(B["transport_wtt_t"], 3.08812, 0.0005) and near(B["transport_wtw_t"], 16.23958, 0.0005) and B["wtw_lines_out"] == 0
   and near(LN["R1"]["transport_wtt_t"], 1.32348, 0.0005) and LN["R5"]["transport_wtt_t"] is None, str(B))
ok("🔴 ...never in the total: the total is still material + transport + disposal",
   near(B["total_t"], B["material_t"] + B["transport_t"] + B["disposal_t"], 0.002) and near(B["total_t"], 156.995, 0.002))
# Greener: R1 114 × 60 km and R4 228 × 16 km electric = 10,488 km × 0.0505125
ok("...electric well-to-tank: 'Greener' 10,488 km × 0.0505125 = 0.530 t, well-to-wheel 1.887 + 0.530 = 2.417",
   near(G["totals"]["transport_wtt_t"], 0.529775, 0.0005) and near(G["totals"]["transport_wtw_t"], 2.41696, 0.0006), str(G["totals"]))
ok("item 14 ⭐ life-cycle modules add up to the total: A1–A3 30.432 (material), A4 5.636 (R1 delivered), A5 120.927 (R3's muck-away + disposal)",
   near(S["baseline"]["stages"]["A1-A3"], 30.432, 0.002) and near(S["baseline"]["stages"]["A4"], 5.636, 0.002)
   and near(S["baseline"]["stages"]["A5"], 120.927, 0.002) and near(sum(S["baseline"]["stages"].values()), B["total_t"], 0.003))
ok("...and on 'Greener': A1–A3 25.074 (30 % recycled), A4 1.231 (electric R1), A5 6.537 (to the soil hub)",
   near(G["stages"]["A1-A3"], 25.074, 0.002) and near(G["stages"]["A4"], 1.231, 0.002) and near(G["stages"]["A5"], 6.537, 0.002)
   and near(sum(G["stages"].values()), G["totals"]["total_t"], 0.003), str(G["stages"]))
_GD = {d["driver"]: d for d in G["drivers"]}
ok("item 9 ⭐ each decision's lorry effect on its own: the soil hub 0 loads and 4,800 fewer km (200 × 16 against 200 × 40); "
   "electric 47 more loads and 1,960 more km; recycled content none",
   _GD["disposal"]["delta_trips"] == 0 and near(_GD["disposal"]["delta_vkm_km"], -4800.0, 0.01)
   and _GD["fuel"]["delta_trips"] == 47 and near(_GD["fuel"]["delta_vkm_km"], 1960.0, 0.01)
   and _GD["recycled"]["delta_trips"] == 0 and near(_GD["recycled"]["delta_vkm_km"], 0.0, 0.01), str(_GD))
ok("...the alternative's own: 3,512 fewer lorry-km (14,000 → 10,488); the rigids 2,700 more (145 × 60 against 100 × 60)",
   near(G["delta_vkm_km"], -3512.0, 0.01) and near(A["Rigids"]["delta_vkm_km"], 2700.0, 0.01))
ok("item 13 the waste hierarchy step of each of the four disposal methods that exist, and only those",
   S["waste_hierarchy"] == {"landfill": "Disposal", "closed_loop": "Recycling", "open_loop": "Recycling",
                            "combustion": "Other recovery if the plant recovers energy, otherwise disposal"}
   and set(S["waste_hierarchy"]) == set(carbon.DISPOSAL_ROUTES) and "regulation 12" in S["waste_hierarchy_source"])
ok("item 8 what the page counts, in one set of words for the page and the summary; well-to-tank named as outside the total",
   S["scope_words"] == carbon.SCOPE_WORDS and "(A1–A3)" in S["scope_words"]["counts"] and "both legs (A4)" in S["scope_words"]["counts"]
   and "Site plant and site energy, staff travel" in S["scope_words"]["not_counted"] and "not in the total" in S["scope_words"]["not_counted"])
ok("item 11 the decisions in words for the summary: what, then where (a route by its places as well as its id)",
   G["lever_words"] == ["Recycled content 30% — Small aggregate", "Receiving site: Soil hub (route R4) — route R3: Compound → Tip",
                        "Battery electric lorries, where Config has an electric profile for that lorry — every plan line"]
   and A["EPD"]["lever_words"] == ["Custom carbon factor (supplier EPD) 5 kgCO2e per tonne, reference EPD-T1 (fictional) — Small aggregate"]
   and A["Nearer pit"]["lever_words"] == ["Supplier: Pit B (route R2) — route R1: Pit A → Compound"]
   and A["80 %"]["lever_words"] == ["Haul distance 80% of the planned route — route R1: Pit A → Compound"], str(G["lever_words"]))
_FK = {f["key"]: f for f in S["factors"]}
ok("...the well-to-tank rows used are in the factor list with their status and row ID",
   _FK[f"wtt:{ART}"]["value"] == 0.22058 and _FK[f"wtt:{ART}"]["status"] == "VERIFIED" and _FK[f"wtt:{ART}"]["ids"] == ["28_907_3132_4_1"]
   and near(_FK[f"wtt:{EA}"]["value"], 0.05051, 0.00001) and _FK[f"wtt:{EA}"]["status"] == "DERIVED")
ok("item 10 (committed / proposed / considered) waits for saved scenarios: listed under 'not built yet', with no figure",
   any(x.startswith("Committed, proposed or considered on each decision") for x in CB["planned"]["items"]))

# the team filter: a team code sees only its own lines (the Dashboard's rule)
os.environ["IPT2_CODE"] = "ipt2-secret"
try:
    access.set_current("ipt2-secret")
    ST = carbon.scenario()
finally:
    os.environ.pop("IPT2_CODE", None)
    access.set_current("planner123")
ok("🔴 a team code's scenario holds only its own lines (the soil line: 120.927 t)",
   [l["route_id"] for l in ST["lines"]] == ["R3"] and near(ST["baseline"]["totals"]["total_t"], 120.927, 0.002))

# a live document seeded before 10 Oct: no carbon block, no electric profiles, no carbon_material
_live = json.loads(json.dumps(config.load(conversions, use_cache=False)))
_live.pop("carbon", None)
_live["vehicles"].pop(EA, None); _live["vehicles"].pop(ER, None)
for _c in _live["material_categories"].values():
    _c.pop("carbon_material", None)
ok("(the stripped document saves)", config.save(_live, by="harness", network=network)["ok"])
config.invalidate()
S2 = carbon.scenario(alternatives=[{"name": "e", "levers": [{"driver": "fuel", "fuel": "electric"}]}])
ok("⭐ a tenant seeded before 10 Oct gets the same baseline and the electric alternative, from the file",
   near(S2["baseline"]["totals"]["total_t"], B["total_t"], 0.001)
   and near(S2["alternatives"][0]["drivers"][0]["delta_t"], -10.280, 0.002))
config.reset_to_file(conversions, by="harness")
config.invalidate()

# =========================================================================== #
#  8b. Phase 2 — the endpoint (POST /api/carbon/scenario), called as a function   #
# =========================================================================== #
R = main.carbon_scenario(main.CarbonScenarioIn(spend_gbp_m=2.0, alternatives=[main.CarbonAlternative(
    name="Greener", levers=[{"driver": "recycled", "scope": {"category": SA}, "pct": 30},
                            {"driver": "disposal", "scope": {"route_id": "R3"}, "to_route": "R4"},
                            {"driver": "fuel", "fuel": "electric"}])]))
ok("⭐ the endpoint returns the engine's answer unchanged (baseline 156.995, Greener −124.153)",
   near(R["baseline"]["totals"]["total_t"], 156.995, 0.002) and near(R["alternatives"][0]["delta_t"], -124.153, 0.003))
for _label, _body, _want in (
        ("an allocation over 100 %", main.CarbonScenarioIn(allocation={SA: {"Fencing": 60, "Waste": 60}}), "120"),
        ("an EPD without its source", main.CarbonScenarioIn(alternatives=[main.CarbonAlternative(levers=[{"driver": "material", "scope": {"category": SA}, "epd": {"kg_per_t": 3}}])]), "source"),
        ("an unknown status", main.CarbonScenarioIn(status="Everything"), "status"),
        ("seven alternatives", main.CarbonScenarioIn(alternatives=[main.CarbonAlternative() for _ in range(7)]), "at most 6")):
    e = _raises(lambda b=_body: main.carbon_scenario(b))
    ok(f"🔴 {_label} is a 400 with the reason", getattr(e, "status_code", None) == 400 and _want in str(getattr(e, "detail", "")),
       repr(e))
access.set_current(None)
e = _raises(lambda: main.carbon_scenario(main.CarbonScenarioIn()))
ok("🔴 no code → 401 (the endpoint is gated like every staff read)", getattr(e, "status_code", None) == 401, repr(e))
access.set_current("submitter123")
ok("...any signed-in code may read it (a submitter in demo mode sees every line, as on the Dashboard)",
   len(main.carbon_scenario(main.CarbonScenarioIn())["lines"]) == 3)
access.set_current("planner123")

# item 11: the one-page summary (POST /api/carbon/summary.pdf), called as a function
import export  # noqa: E402
from portable import pdf_text  # noqa: E402
_GREEN = [{"driver": "recycled", "scope": {"category": SA}, "pct": 30},
          {"driver": "disposal", "scope": {"route_id": "R3"}, "to_route": "R4"}, {"driver": "fuel", "fuel": "electric"}]
_real_notice = export._demo_notice
export._demo_notice = lambda: "Fictional demo scheme · nothing here is real"
try:
    _pr = main.carbon_summary_pdf(main.CarbonSummaryIn(alternatives=[main.CarbonAlternative(name="Greener", levers=_GREEN)],
                                                       commentary="Check R3 <b>first</b> & keep the tip as a fallback"))
finally:
    export._demo_notice = _real_notice
_pt = pdf_text(_pr.body)
_flat = " ".join(_pt.split())
ok("⭐ the summary is a PDF download, ONE page", _pr.media_type == "application/pdf" and _pr.body[:5] == b"%PDF-"
   and 'filename="carbon-summary.pdf"' in _pr.headers.get("Content-Disposition", "")
   and _pr.body.count(b"/Type /Page") - _pr.body.count(b"/Type /Pages") == 1)
ok("🔴 ...stamped: a Wayscope planning estimate on the DESNZ 2026 basis, not Carbon Tool figures; the demo notice on it",
   "Wayscope planning estimate, DESNZ 2026 basis, not Carbon Tool figures" in _flat
   and "Fictional demo scheme" in _flat and "Not a National Highways Carbon Tool return" in _flat)
ok("...the scenario's own figures: 157.0 against 32.8, the change in words with the lorry loads and lorry-km",
   "157.0" in _flat and "32.8" in _flat and "124.2 tCO2e lower (79.1%) · 47 more lorry loads · 3 512 fewer lorry-km" in _flat
   and "16.2" in _flat and "2.4" in _flat, _flat[:600])
ok("...the decisions in words (the arrow written 'to', which Helvetica can print) and ranked with their lorry effect",
   "Recycled content 30% — Small aggregate" in _flat and "Receiving site: Soil hub (route R4) — route R3: Compound to Tip" in _flat
   and "Receiving site and disposal method" in _flat and "4 800 fewer lorry-km" in _flat and "→" not in _pt)
ok("...what the figures count, and the commentary printed AS TYPED (markup escaped, never interpreted)",
   "Making the material (A1–A3)" in _flat and "Left out here:" in _flat and "1 plan line has no route distance yet" in _flat
   and "Check R3 <b>first</b> & keep the tip as a fallback" in _flat)
ok("🔴 ...none of the words a public stand must not use",
   not any(w in _flat.lower() for w in ("secure", "trusted by", "testimonial", "real-time", "optimis", "predict", "telematics",
                                        "live tracking", "truck")) and not re.search(r"\bAI\b", _flat))
_pr0 = main.carbon_summary_pdf(main.CarbonSummaryIn())
_f0 = " ".join(pdf_text(_pr0.body).split())
ok("...with no alternative it prints the approved plan and an empty box to write in", "No alternative chosen" in _f0
   and "no alternative" in _f0 and "Fictional demo scheme" not in _f0)
for _label, _body, _want in (
        ("two alternatives", main.CarbonSummaryIn(alternatives=[main.CarbonAlternative(), main.CarbonAlternative()]), "one alternative"),
        ("a commentary over 1,500 characters", main.CarbonSummaryIn(commentary="x" * 1501), "1500"),
        ("an unknown status", main.CarbonSummaryIn(status="Everything"), "status")):
    e = _raises(lambda b=_body: main.carbon_summary_pdf(b))
    ok(f"🔴 summary: {_label} is a 400 with the reason", getattr(e, "status_code", None) == 400 and _want in str(getattr(e, "detail", "")), repr(e))
access.set_current(None)
e = _raises(lambda: main.carbon_summary_pdf(main.CarbonSummaryIn()))
ok("🔴 summary: no code → 401", getattr(e, "status_code", None) == 401, repr(e))
access.set_current("planner123")
_mp = read("backend/main.py")
_fs = _mp[_mp.index("def carbon_summary_pdf("):_mp.index("def carbon_summary_pdf(") + 2400]
ok("🔴 source: the summary's first act is _require_access(); it stores nothing", _fs.index("_require_access()") < _fs.index("carbon.scenario(")
   and "db." not in _fs.split(chr(10) * 3)[0] and '@app.post("/api/carbon/summary.pdf")' in _mp)
_ex = read("backend/export.py")
_bc = _ex[_ex.index("def build_carbon_pdf("):_ex.index("def _index_date_label(")].split(chr(34) * 3, 2)[2]   # the code, below its docstring
ok("...and the PDF draws, never computes: every figure is read off the scenario", "carbon.scenario" not in _bc
   and "_carbon.SUMMARY_STAMP" in _bc and "kg_per_km" not in _bc and "E(txt)" in _bc)
_fn = _mp[_mp.index("def carbon_scenario("):_mp.index("def carbon_scenario(") + 2000]
ok("🔴 source: the endpoint's first act is _require_access(), and a CarbonError becomes a 400",
   _fn.index("_require_access()") < _fn.index("carbon.scenario(") and "except carbon.CarbonError as e:" in _fn
   and "raise HTTPException(400, str(e))" in _fn and '@app.post("/api/carbon/scenario")' in _mp)
ok("...it is a POST that stores nothing: no db call in the endpoint", "db." not in _fn.split("def carbon_scenario(")[1].split(chr(10) * 3)[0])

# the fixture the render harness draws the Carbon page from (sorted keys: stable on every OS)
def _scrub(o):
    if isinstance(o, dict):
        return {k: ("<ts>" if k.endswith("_at") and isinstance(v, str) else _scrub(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_scrub(x) for x in o]
    return o


_fix = os.path.join(HERE, "fixtures", "carbon_scenario.json")
with open(_fix, "w", encoding="utf-8", newline=chr(10)) as fh:
    fh.write(json.dumps(_scrub(R), indent=1, ensure_ascii=False, sort_keys=True) + chr(10))
ok("the carbon fixture is written for render_frontend.js", os.path.exists(_fix))

# =========================================================================== #
#  9. Source-level                                                              #
# =========================================================================== #
_src = read("backend/carbon.py")
_code = _src.split('"""', 2)[2]
ok("carbon.py reads the forecast through costlines.lines (one distance, one trip count)", "costlines.lines(" in _code)
ok("...and the cycle through network.route_analysis — never a third cycle formula", "network.route_analysis(" in _code
   and "avg_haul_speed" not in _code
   # NARROWED 17 Oct 2026: a swapped route's trips a lorry a day are drivers_hours.lorry_day's, never a shift ÷ cycle
   and "// cycle_min" not in _code and "drivers_hours.lorry_day(" in _code and "drivers_hours.ev_trips(" in _code)
ok("...every SQL it runs carries the tenant", _code.count("WHERE tenant_id = ?") == 2 and "INSERT" not in _code
   and "UPDATE " not in _code and "DELETE" not in _code)
ok("🔴 no ICE and no invented factor in the code: every kg figure comes from the factor document",
   not any(x in _code for x in ("7.80307", "118.80307", "19.55376", "0.13096", "0.93939", "0.99773")))
# NARROWED 12 Oct 2026 (B2): network now calls conversions._emissions for EVERY profile, not only the electric
# ones, so the literal it is pinned to is the unconditional call
ok("conversions._emissions is the one place an electric figure is derived (network and the map's flat factors call it)",
   "electric_kg_per_km(factors, v)" in read("backend/conversions.py")
   and "co2_per_km = conversions._emissions(factors, prof)" in read("backend/network.py")
   and 'if v.get("fuel") == "electric"' not in read("backend/network.py"))
ok("the cost lines carry the one-way and return km the planner reads", '"distance_km": ctx.get("distance_km"), "return_km": ctx.get("return_km")'
   in read("backend/costlines.py"))
ok("🔴 the forecast pickers never offer a scenario-only profile (it joins HIDDEN_VEHICLES from /api/meta's vehicle_details)",
   "Object.entries((m && m.vehicle_details) || {}).forEach(([k, v]) => { if(v && v.scenario_only && !HIDDEN_VEHICLES.includes(k)) HIDDEN_VEHICLES.push(k); });"
   in read("frontend/index.html"))

# 12 Oct 2026 (the review and fix pass): a tenant's STORED factors are read before the file, so the live demo keeps its
# old _default (0.97) until its Config is reset to file or its package re-imported — factors_diagnostics says so
import network  # noqa: E402
_real_lf = conversions.load_factors
_old_doc = json.loads(json.dumps(conversions.load_factors()))
_old_doc["vehicles"]["_default"]["emissions_kg_co2e_per_km"] = 0.97
try:
    conversions.load_factors = lambda *a, **k: _old_doc
    _fd_old = network.factors_diagnostics()
    conversions.load_factors = lambda *a, **k: json.loads(json.dumps(_real_lf()))
    _fd_new = network.factors_diagnostics()
finally:
    conversions.load_factors = _real_lf
ok("⭐ factors_diagnostics warns when the stored _default (0.97, a config saved before 12 Oct) is not the published fallback",
   any("_default carries 0.97" in w and "0.89743" in w and "reset the Config page to file" in w for w in _fd_old["warnings"]),
   str(_fd_old["warnings"]))
ok("...and says nothing about it when the _default is the published figure",
   not any("_default carries" in w for w in _fd_new["warnings"]), str(_fd_new["warnings"]))
ok("the constant's note no longer claims a stored config resolves alike (the live demo keeps 0.97 until a reset or re-import)",
   "resolves alike." not in read("backend/conversions.py") and "keeps its stored" in read("backend/conversions.py")
   and "cannot disagree" not in V["_default"]["_emissions_basis"])

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

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
ok("⭐ fuel on every profile: diesel on all twelve existing, electric on the two new",
   all(V[k]["fuel"] == "diesel" for k in V if not k.startswith("_") and k not in (EA, ER))
   and V[EA]["fuel"] == "electric" and V[ER]["fuel"] == "electric")
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
       "Precast / concrete": "concrete", "Steel / rail": "metals", "General / imported": "average_construction"})
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
ok("⭐ the EPD override replaces the generic concrete figure: 95.0 with its source",
   f["kg_per_t"] == 95.0 and f["method"] == "epd" and f["epd_source"] == "EPD-0001 (fictional)" and f["status"] == "EPD (supplier)")
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
ok("diesel is untouched: artic 0.93939, rigid 0.99773, the fallback chain unchanged",
   conversions._emissions(FILE, ART) == 0.93939 and conversions._emissions(FILE, R8) == 0.99773
   and conversions._emissions({"vehicles": {}}, "nothing") == 0.90)
ff = conversions.flat_factors(FILE)["vehicle_emissions_kg_co2e_per_km"]
ok("the map's flat factors carry the derived electric figure, diesel unchanged",
   near(ff[EA], 0.1799375, 1e-9) and ff[ART] == 0.93939 and ff["_default"] == 0.97)
d = carbon.ev_day(75, 80, 10, 1.25, 500, 350)
# 100 kWh a trip; 8 cycles need 300 kWh more = 51.4 min → 651 > 600; 7 need 200 kWh = 34.3 min → 559 ≤ 600
ok("⭐ electric shift: 75-min cycle, 80 km a trip, 500 kWh, 350 kW → 7 cycles (not 8), one charge of 34.3 min",
   d["cycles"] == 7 and d["charges"] == 1 and near(d["charge_minutes"], 200 / 350 * 60) and d["feasible"]
   and near(d["daily_range_km"], 400.0) and near(d["kwh_per_trip"], 100.0), str(d))
d = carbon.ev_day(60, 40, 10, 1.25, 500, 350)
ok("...10 cycles of 50 kWh fit one 500 kWh battery: no charge, the diesel day", d["cycles"] == 10 and d["charges"] == 0)
d = carbon.ev_day(30, 100, 10, 1.25, 500, 350)
# 30n + (125n − 500) / 350 × 60 ≤ 600 → n ≤ 13.3: 13 cycles, 1,125 kWh topped up in 3 stops, 192.9 min
ok("...a short heavy cycle: 13 cycles, 3 charges, 192.9 min charging (64.3 a stop)",
   d["cycles"] == 13 and d["charges"] == 3 and near(d["charge_minutes"], 1125 / 350 * 60) and near(d["minutes_per_charge"], 1125 / 350 * 60 / 3), str(d))
ok("🔴 a trip longer than the battery is flagged infeasible, not sized", not carbon.ev_day(600, 450, 10, 1.25, 500, 350)["feasible"])
ok("fleet = ceil(trips ÷ (cycles a day × working days)): 545 ÷ (7 × 22) → 4; no cycle → None; no trips → 0",
   carbon.lorries_for(545, 7, 22) == 4 and carbon.lorries_for(10, None, 22) is None and carbon.lorries_for(0, None, 22) == 0)
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
                          ("L4", "Soil hub", "Soil recycling"), ("L5", "Pit B", "Quarry"), ("L6", "Pit C", "Quarry")):
    db.execute("INSERT INTO locations (id, name, lat, lon, loc_type) VALUES (?, ?, ?, ?, ?)", (_id, _name, 52.5, -1.0, _type))
for _rid, _o, _d, _m in (("R1", "L1", "L2", SA), ("R2", "L5", "L2", SA), ("R3", "L2", "L3", SOIL),
                         ("R4", "L2", "L4", SOIL), ("R5", "L6", "L2", SA)):
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
ok("sheets: Bulk Materials 36.068 (the aggregate lines) and Earthworks 120.927 (the soil line) — together the total",
   near(S["baseline"]["sheets"]["Bulk Materials"], 36.068, 0.002) and near(S["baseline"]["sheets"]["Earthworks"], 120.927, 0.002)
   and near(S["baseline"]["sheets"]["Bulk Materials"] + S["baseline"]["sheets"]["Earthworks"], B["total_t"], 0.003))
AL = S["baseline"]["allocation"]
ok("allocation: Small aggregate's 36.068 t at 60 % Road Pavements / 30 % Drainage; the rest Not Allocated",
   near(AL["Road Pavements"], 21.641, 0.002) and near(AL["Drainage"], 10.820, 0.002) and near(AL["Not Allocated"], 124.534, 0.003))
BM = S["baseline"]["benchmarks"]
# 13.15146 t over 8,700 baked t; 203,000 t·km against the artic 0.07835; laden 7,000 of 14,000 km
ok("benchmarks: 1.512 kg per tonne delivered; 0.06479 kg per t·km vs DESNZ artic 0.07835 → 17.3 % below the national average",
   near(BM["kg_co2e_per_t_delivered"], 1.512, 0.001) and near(BM["kg_co2e_per_tkm"], 0.06479, 0.00001)
   and BM["desnz_kg_co2e_per_tkm"] == 0.07835 and BM["vs_national_average_pct"] == -17.3, str(BM))
ok("...laden share 50 %, zero-emission deliveries 0 %, 78.5 tCO2e per £m on £2m typed, NH's 210 → 148 beside it",
   BM["laden_share_pct"] == 50.0 and BM["zero_emission_share_pct"] == 0.0 and BM["t_co2e_per_gbp_m"] == 78.5
   and BM["nh_kpi_t_co2e_per_gbp_m"] == {"2023_24": 210, "2024_25": 148})
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
ok("...with the electric day stated: payload 25.5 t (twin 29), 500 kWh, 350 kW, range 400 km, no charge needed",
   FC["electric_profiles"][0]["payload_t"] == 25.5 and FC["electric_profiles"][0]["twin_payload_t"] == 29
   and FC["daily_range_km_min"] == 400.0 and FC["charges_per_lorry_day_max"] == 0 and FC["infeasible_lines"] == 0)

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
ok("options: R1's other supplier to the same compound (R2, R5) and its baked HERE alternatives (0, 1)",
   _or["R1"]["suppliers"] == ["R2", "R5"] and _or["R1"]["alts"][ART] == [0, 1])
ok("options: R3 is a landfill line with R4 as another destination from the same origin",
   _or["R3"]["disposal_route"] == "landfill" and _or["R3"]["destinations"] == ["R4"])
_pk = {p["key"]: p for p in S["factors"]}
ok("⭐ every factor used carries source, year and status (and the gov.uk row ID where one exists)",
   all(p.get("status") and ("year" in p) for p in S["factors"])
   and _pk["material:aggregates"]["ids"]["primary"] == "19_500_5000_15_1" and _pk[f"vehicle:{ART}"]["status"] == "VERIFIED"
   and _pk[f"vehicle:{EA}"]["status"] == "DERIVED" and _pk["electricity"]["value"] == 0.14395
   and _pk["kwh_per_km"]["status"] == "DERIVED" and _pk["zev_allowance"]["status"] == "ASSUMPTION")
ok("the known limits and the Planned items travel with every answer",
   len(S["limits"]) >= 7 and any("draft" in x for x in S["limits"]) and any("AR4" in x for x in S["limits"])
   and len(S["planned"]) >= 4 and S["unit"] == "km")

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
#  9. Source-level                                                              #
# =========================================================================== #
_src = read("backend/carbon.py")
_code = _src.split('"""', 2)[2]
ok("carbon.py reads the forecast through costlines.lines (one distance, one trip count)", "costlines.lines(" in _code)
ok("...and the cycle through network.route_analysis — never a third cycle formula", "network.route_analysis(" in _code
   and "avg_haul_speed" not in _code)
ok("...every SQL it runs carries the tenant", _code.count("WHERE tenant_id = ?") == 2 and "INSERT" not in _code
   and "UPDATE " not in _code and "DELETE" not in _code)
ok("🔴 no ICE and no invented factor in the code: every kg figure comes from the factor document",
   not any(x in _code for x in ("7.80307", "118.80307", "19.55376", "0.13096", "0.93939", "0.99773")))
ok("conversions._emissions is the one place an electric figure is derived (network and the map's flat factors call it)",
   "electric_kg_per_km(factors, v)" in read("backend/conversions.py")
   and 'conversions._emissions(factors, prof) if v.get("fuel") == "electric"' in read("backend/network.py"))
ok("the cost lines carry the one-way and return km the planner reads", '"distance_km": ctx.get("distance_km"), "return_km": ctx.get("return_km")'
   in read("backend/costlines.py"))
ok("🔴 the forecast pickers never offer a scenario-only profile (it joins HIDDEN_VEHICLES from /api/meta's vehicle_details)",
   "Object.entries((m && m.vehicle_details) || {}).forEach(([k, v]) => { if(v && v.scenario_only && !HIDDEN_VEHICLES.includes(k)) HIDDEN_VEHICLES.push(k); });"
   in read("frontend/index.html"))

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

"""The 9 Nov 2026 UI critique, wave 2 (branch claude/ui-fix-consistency), the server's half of finding 20 / decision 5:
one distance unit per organisation.

Run from the repo root:  python backend/tests/test_ui_consistency.py

What this proves: with no unit saved a GB organisation reads miles and any other km; a saved unit wins either way; a
nonsense unit falls back to the country's; the scale bar's round length is in miles when the unit is "mi" (and its pixel
length is right for a mile); the bulletin's map scale bar is labelled in the organisation's unit; the pour words the
server sends are the sentence-case ones the screens show.

What it does not prove: how the bar looks in a printed PDF (ui_audit / a look in Chrome), or that live's saved Config
carries the unit (the demo package sets "mi"; a live organisation saved before this branch reads its country's default).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import basemap  # noqa: E402
import bulletin_doc  # noqa: E402
import config  # noqa: E402
import pours  # noqa: E402

passed = failed = 0


def ok(label, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("  FAIL", label, extra)


def du(block):
    return config.tenant_settings(doc={"tenant": block})["distance_unit"]


# --- the unit -------------------------------------------------------------------------------------------------------
ok("⭐ 20: a GB organisation with no unit saved reads miles", du({"country": "GB"}) == "mi")
ok("...lower-case country too (gb)", du({"country": "gb"}) == "mi")
ok("...any other country with no unit saved reads km (IE, DE)", du({"country": "IE"}) == "km" and du({"country": "DE"}) == "km")
ok("...no country at all reads km", du({}) == "km")
ok("...a saved km wins over GB's miles", du({"country": "GB", "distance_unit": "km"}) == "km")
ok("...a saved mi wins over IE's km", du({"country": "IE", "distance_unit": "mi"}) == "mi")
ok("...a saved unit in capitals is read (MI)", du({"country": "IE", "distance_unit": "MI"}) == "mi")
ok("...a nonsense unit falls back to the country's (GB → mi, IE → km)",
   du({"country": "GB", "distance_unit": "leagues"}) == "mi" and du({"country": "IE", "distance_unit": "leagues"}) == "km")
ok("...the units the app knows are exactly km and mi", set(config.DISTANCE_UNITS) == {"km", "mi"})

# --- the scale bar ---------------------------------------------------------------------------------------------------
v = {"lat": 53.8, "zoom": 10, "w": 720, "h": 420}
m_per_px = 40075016.686 * math.cos(math.radians(v["lat"])) / (basemap.TILE * 2 ** v["zoom"])
n_km, px_km = basemap.scale(v, 110)
n_mi, px_mi = basemap.scale(v, 110, unit="mi")
ok("⭐ 20: the scale bar in km is unchanged by default (a round length, its pixels from 1 km = 1000 m)",
   n_km in (0.5, 1, 2, 5, 10, 20, 50, 100, 200) and abs(px_km - n_km * 1000 / m_per_px) < 1e-6, f"{n_km} km {px_km:.1f} px")
ok("...in miles a round length of miles, its pixels from 1 mile = 1609.344 m",
   n_mi in (0.5, 1, 2, 5, 10, 20, 50, 100, 200) and abs(px_mi - n_mi * 1609.344 / m_per_px) < 1e-6, f"{n_mi} mi {px_mi:.1f} px")
ok("...both bars stay near the length asked for (between a third and twice 110 px)", 36 < px_km < 220 and 36 < px_mi < 220,
   f"{px_km:.1f} / {px_mi:.1f}")

_ts = config.tenant_settings
try:
    config.tenant_settings = lambda *a, **k: dict(_ts(doc={"tenant": {"country": "GB"}}))
    svg_mi = bulletin_doc._svg_scale(v, 720, 420)
    config.tenant_settings = lambda *a, **k: dict(_ts(doc={"tenant": {"country": "GB", "distance_unit": "km"}}))
    svg_km = bulletin_doc._svg_scale(v, 720, 420)
finally:
    config.tenant_settings = _ts
ok("⭐ 20: the bulletin's map scale bar says miles for a miles organisation", (f">{n_mi:g} mile" in svg_mi) and " km<" not in svg_mi, svg_mi[-80:])
ok("...and km for a km one", f">{n_km:g} km<" in svg_km, svg_km[-80:])
ok("...the bulletin's carbon basis speaks of distance, not km",
   "split by the distance driven" in open(bulletin_doc.__file__, encoding="utf-8").read())

# --- the pour words (card 12) ----------------------------------------------------------------------------------------
ok("⭐ 12: the pour words are in sentence case, in words a site manager reads",
   pours.WORDS == {"POUR_COLD_JOINT": "Cold joint likely", "POUR_TRANSIT": "Too long in transit", "POUR_SHORT": "Too few mixers",
                   "POUR_BAND": "Mixers in a no-delivery time", "POUR_OVER_PLAN": "Over the month's plan"})
ok("...no pour word is in capitals", all(not w.isupper() for w in pours.WORDS.values()))

print(f"test_ui_consistency.py: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)

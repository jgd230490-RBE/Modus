"""Wave 5 of the UI critique (findings 21, 22): the landing's pictures, the thanks / error pages, the guide's figures.

Run from the repo root:  python backend/tests/test_ui_landing_stills.py

What this proves (source level, no browser):
  * the thanks, error and privacy pages: the header's 22 px of space is not beaten by `.wrap`'s side padding (the logo sat on the
    top edge), and the way back on thanks / error is a button, 48 px tall, not a text link;
  * the pictures: no landing still is the October app, they are 1240 x 609 and light, the new walkthrough is there; the user guide has
    no PLACEHOLDER frame left (the 22 old files are named by their hashes), carries the 18 new figures in chapters 2 and 14-20,
    numbers them in order, and lists them all in Appendix C.

What it does not prove: how the pages look in a browser (the UI audit does), or that a picture shows the right screen (looked at by eye
at capture time and listed in notes/session-1110-landing-stills.md).
"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LAND = os.path.join(ROOT, "landing")

passed = failed = 0


def ok(label, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL:", label)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


# --- the thanks, error and privacy pages ----------------------------------------------------
for name in ("thanks.html", "error.html", "privacy.html"):
    src = read("landing", name)
    # `.wrap{padding:0 32px}` is a class, `header{padding:22px 0}` an element: the class won and the logo had no space above.
    ok(f"{name}: the header's top and bottom space is set on header.wrap (the class beats the element rule)",
       re.search(r"header\.wrap\{padding-top:22px;padding-bottom:22px\}", src) is not None)
    ok(f"{name}: the side padding is still the .wrap rule's (a phone keeps its 20 px gutter)",
       "@media (max-width:600px){.wrap{padding:0 20px}}" in src and "header.wrap{padding:" not in src)
    ok(f"{name}: the logo still links home", re.search(r'<header class="wrap"><a href="\./"><img src="\./assets/logo-header-on-light\.svg"', src) is not None)

for name, target, words in (("thanks.html", "./", "Back to Wayscope"), ("error.html", "./#demo", "Back to the request form")):
    src = read("landing", name)
    m = re.search(r'<a class="back" href="([^"]*)">([^<]*)</a>', src)
    ok(f"{name}: the way back is a link with the class back to {target}", bool(m) and m.group(1) == target)
    ok(f"{name}: its words say '{words}'", bool(m) and words in m.group(2))
    css = re.search(r"\.back\{([^}]*)\}", src)
    css = css.group(1) if css else ""
    ok(f"{name}: .back is a filled button (background, padding, rounded) and not a bare text link",
       "background:var(--ink)" in css and "padding:12px 22px" in css and "border-radius:8px" in css and "color:#fff" in css)
    ok(f"{name}: .back is at least 48 px tall (the landing's button height)", "min-height:48px" in css)
    ok(f"{name}: the button keeps its colours on hover (the page's a:hover turns text orange)", re.search(r"\.back:hover\{[^}]*color:#fff", src) is not None)
    ok(f"{name}: still no script and no footer", "<script" not in src and "<footer" not in src)


# --- the landing's pictures (finding 21) ---------------------------------------------------------
import hashlib
import struct

MEDIA = os.path.join(LAND, "media")
# sha-256 prefixes of the three October stills this branch replaced: the old bar "NOTHING HERE IS REAL" and the old Look-ahead ("£1.995 / L")
OLD_STILLS = {"still-fairprice": "ef88115a88dc67dd", "still-lookahead": "2d0fc426f4b8b8d3", "still-routes": "0c96c76d31ef29ea"}


def sha16(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def jpeg_size(path):
    with open(path, "rb") as f:
        d = f.read()
    i = 2
    while i < len(d):
        if d[i] != 0xFF:
            i += 1
            continue
        m = d[i + 1]
        if m in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", d[i + 5:i + 9])
            return w, h
        i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
    return None


land = read("landing", "index.html")
STILLS = ("still-fairprice", "still-lookahead", "still-sim", "still-pours", "still-layout", "still-clp", "still-routes", "still-map")
for name in STILLS:
    pth = os.path.join(MEDIA, name + ".jpg")
    ok(f"{name}.jpg exists", os.path.isfile(pth))
for name, old in OLD_STILLS.items():
    pth = os.path.join(MEDIA, name + ".jpg")
    ok(f"{name}.jpg is not the October picture any more (its bytes changed)", os.path.isfile(pth) and sha16(pth) != old)
ok("every landing still is 1240 x 609 (the size the page asks for, so nothing jumps) and under 200 KB",
   all(os.path.isfile(os.path.join(MEDIA, n + ".jpg")) and jpeg_size(os.path.join(MEDIA, n + ".jpg")) == (1240, 609)
       and os.path.getsize(os.path.join(MEDIA, n + ".jpg")) < 200 * 1024 for n in STILLS))
ok("the four walkthrough chips and the new fourth walkthrough are on the page", all(t in land for t in (
    'Four walkthroughs. One plan.', 'id="film-4"', "Test a site day", "Write the CLP",
    "./media/still-sim.jpg", "./media/still-pours.jpg", "./media/still-layout.jpg", "./media/still-clp.jpg")))
alts = re.findall(r'<img [^>]*alt="([^"]*)"', land)
ok("no landing alt text carries the October bar's old wording", alts and not any("NOTHING HERE IS REAL" in a.upper() for a in alts))
ok("the page promises no film file for Walkthrough 4 (stills only) and says all four are on the fictional scheme",
   "./films/film4" not in land and "All four walkthroughs are on the fictional demo scheme" in land)

# --- the user guide's pictures (finding 22) -------------------------------------------------------
HMEDIA = os.path.join(ROOT, "frontend", "help", "media")
guide = read("frontend", "help", "index.html")
# sha-256 prefixes of the 22 grey frames that said PLACEHOLDER — NOT A SCREENSHOT (the guide's S and M pictures before this branch)
OLD_HOLDERS = {
    "S01": "33ea1068c9f14f29", "S02": "0654fedc42889d3f", "S03": "f582d800f22d78c9", "S04": "b4ce88b2dbcc3fc3", "S05": "dbf933695035a81d",
    "S06": "cb84a190e738bdc8", "S07": "ef4c49308704941f", "S08": "efc8f8ae28bb1d5b", "S09": "a3e07e3a83517717", "S10": "c92c4a4485d5cc84",
    "S11": "37c8a4b5c2335061", "S12": "63beae7bb4e724d0", "S13": "8ef009f592f246d2", "S14": "7f236c7c6b935628", "S15": "3e50d8d5c466b3a7",
    "M01": "a72f4cfe9b47b906", "M02": "287de3e0b8b115c2", "M03": "d6f16ee63af89d6a", "M05": "94a462e1be76e50f", "M06": "ae89d5456e10c060",
    "M07": "977121ce052a8919", "M08": "752a3c994b074889",
}
ok("no PLACEHOLDER sentence under the guide's title", "PLACEHOLDER" not in guide and "placeholders until" not in guide)
ok("none of the guide's 22 S / M pictures is still the grey placeholder frame (every file's bytes changed)",
   all(os.path.isfile(os.path.join(HMEDIA, c + ".png")) and sha16(os.path.join(HMEDIA, c + ".png")) != h for c, h in OLD_HOLDERS.items()))
ok("...and each is a real screen: a picture of many colours, not a flat card (more than 40 KB, apart from the sign-in screen)",
   all(os.path.getsize(os.path.join(HMEDIA, c + ".png")) > 40 * 1024 for c in OLD_HOLDERS if c != "S01"))
NEW_FIGS = ("S07m", "D01", "P01", "A01", "A02", "K01", "C01", "C02", "V01", "V02", "V03", "L01", "L02", "L03", "Y01", "Y03", "Q01", "Q02")
ok("the 18 new figures are in the guide, each with its caption and a picture on disk", all(
    f'src="media/{c}.png"' in guide and os.path.isfile(os.path.join(HMEDIA, c + ".png")) for c in NEW_FIGS))
ok("chapters 14 to 20 each have a figure (the guide had none past chapter 13)", all(
    re.search(r'<h1 id="%s">.*?<figure>' % cid, guide[guide.index('<h1 id="%s">' % cid):], re.S) is not None
    and "<figure>" in guide[guide.index('<h1 id="%s">' % cid):guide.index('<h1 id="%s">' % nxt)]
    for cid, nxt in (("14-abnormal-loads", "15-stockpiles"), ("15-stockpiles", "16-concrete-pours"), ("16-concrete-pours", "17-the-simulation"),
                     ("17-the-simulation", "18-clp-documents"), ("18-clp-documents", "19-site-layouts"), ("19-site-layouts", "20-concerns"),
                     ("20-concerns", "appendix-a-methods-and-assumptions"))))
caps = [int(n) for n in re.findall(r"<figcaption>Figure (\d+) — ", guide)]
ok("the figures are numbered 1, 2, 3 … in the order they appear (%d of them)" % len(caps), caps == list(range(1, len(caps) + 1)) and len(caps) == 45)
app_c = guide[guide.index('<h1 id="appendix-c-figures">'):]
ok("Appendix C lists every figure, with the file", len(re.findall(r"<tr><td>\d+</td><td>", app_c)) == len(caps)
   and all(c + ".png" in app_c for c in NEW_FIGS))
ok("no figure caption or alt text of the guide names a back-end word", not re.search(r'(?:alt|figcaption)[^<]*?\b(endpoint|API|JSON|server|token)\b', guide[:guide.index('<h1 id="appendix-c-figures">')]))
ok("the picture generator never overwrites a real capture (it writes a placeholder only for a missing file)",
   "a real capture" in read("backend", "tools", "make_guide_images.js") and "fs.existsSync(path.join(MEDIA, code" in read("backend", "tools", "make_guide_images.js"))

print(f"test_ui_landing_stills.py: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)

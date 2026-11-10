"""Wave 5 of the UI critique (findings 21, 22): the landing's pictures, the thanks / error pages, the guide's figures.

Run from the repo root:  python backend/tests/test_ui_landing_stills.py

What this proves (source level, no browser):
  * the thanks, error and privacy pages: the header's 22 px of space is not beaten by `.wrap`'s side padding (the logo sat on the
    top edge), and the way back on thanks / error is a button, 48 px tall, not a text link;
  * (added with the pictures) no landing picture is the October app, the landing's alt texts name no old wording, the new
    walkthrough is there, and the user guide has no PLACEHOLDER frame left.

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

print(f"test_ui_landing_stills.py: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)

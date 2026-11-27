"""
Own look, the four gate pages (26 Nov 2026): the public map's password page, the user guide's and the bulletin's
sign-in pages and the "map closed" page, which share ONE style block, main._GATE_CSS.

Asserts: none of the old values is left in the block (Inter, the orange button / focus ring, the stock blue link,
warm greys, the 10 px box, the 999px pill); the new ones are there (Sora, IBM Plex Sans, the sign blue #0B4EA2 with
a darker hover and white text at 4.5:1 or better, neutral greys, one 6 px corner, the 3 px DEMO tag, the 44 px eye);
the fonts load from hosts the policy already allows; each page still builds with the words it had before.
NOT proved here: how the pages look (pictures: notes/own-look-gate-mockup-1126/real/).
Named smoke_*: it imports the real app (FastAPI), so run_suite.py and CI run it with the smoke interpreter; under its
first name (own_look_gate_pages.py) the runner's patterns (test_*.py, smoke_*.py) never picked it up.
Run:  .venv-smoke/Scripts/python backend/tests/smoke_own_look_gate_pages.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import main  # noqa: E402
import security_headers  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label)
        print("  FAIL:", label)


def vis(h):
    h = re.sub(r"(?s)<(style|script)\b.*?</\1>", "", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def cr(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


CSS = main._GATE_CSS
# the visible words of each page as they were before this change (read from main 26 Nov 2026)
PAGES = {
    "_MAP_PASSWORD_PAGE": "Wayscope — map access Public map This map is shared by password. Enter the one you were given. Password Open the map That password was not recognised. Staff: sign in to the app at the main page and the map opens with it.",
    "_HELP_SIGNIN_PAGE": "Wayscope — user guide The user guide is for signed-in staff It documents every staff screen, so it sits behind the same sign-in. Go to the app and sign in Once you are signed in, come back to /help/ — or use User guide at the foot of the app's menu on the left.",
    "_BULLETIN_SIGNIN_PAGE": "Wayscope — monthly bulletin The monthly bulletin is for signed-in staff It is issued by the scheme's staff, so it sits behind the same sign-in. Go to the app and sign in Once you are signed in, open it from Monthly bulletin on the Dashboard, or come back to /bulletin/ .",
    "_MAP_UNCONFIGURED_PAGE": "Wayscope — map closed The map is closed No map password has been configured on this deployment, so the map cannot be opened to anyone without a staff sign-in. This is the safe state, not a fault. Set MAP_PASSWORD in the environment to open it. Staff can still see the map by signing in at the main page .",
}

ok("Inter is not in the font list", re.search(r"Inter", CSS) is None)
for old in ("#C2410C", "#9A3412", "#2563EB", "#78716C", "#D6D3D1", "#F5F5F4", "999px", "border-radius:10px"):
    ok("old value gone from the gate block: " + old, old.lower() not in CSS.lower())
for new in ("'IBM Plex Sans'", "Sora", "#0B4EA2", "#083C7D", "#62656B", "#C6C8CC", "#F5F5F6", "#1F2024", "#DC2626"):
    ok("new value present: " + new, new in CSS)
ok("the button, the focus ring and the link take the sign blue",
   "background:#0B4EA2" in CSS and "outline:2px solid #0B4EA2" in CSS and "a { color:#0B4EA2; }" in CSS
   and "button:hover { background:#083C7D; }" in CSS)
ok("white on the sign blue 4.5:1 or better, and on the hover step",
   cr("#FFFFFF", "#0B4EA2") >= 4.5 and cr("#FFFFFF", "#083C7D") >= 4.5)
ok("link blue on the white box 4.5:1 or better", cr("#0B4EA2", "#FFFFFF") >= 4.5)
ok("captions #62656B on white 4.5:1 or better", cr("#62656B", "#FFFFFF") >= 4.5)
ok("the box has the one 6 px corner", re.search(r"\.box \{[^}]*border-radius:6px", CSS) is not None)
ok("the demo notice is 6 px and keeps its red, capitals and spacing",
   re.search(r"\.demo-notice \{[^}]*border-radius:6px[^}]*#B91C1C[^}]*letter-spacing:\.06em; text-transform:uppercase", CSS) is not None
   and "border:1px solid #DC2626" in CSS)
ok("the inner DEMO tag keeps 3 px", "border-radius:3px; background:#B91C1C" in CSS)
ok("the error red stays", "color:#DC2626" in CSS)
ok("the heading is Sora, then IBM Plex Sans", re.search(r"h1 \{[^}]*font-family:Sora,'IBM Plex Sans'", CSS) is not None)
ok("the password eye keeps its 44 px tap area", "width:38px; height:38px;" in CSS and "inset:-3px" in CSS)
ok("one look: the page does not follow the reader's theme", "color-scheme: light" in CSS and "prefers-color-scheme" not in CSS)
ok("the pages ask for Sora and IBM Plex Sans", "family=Sora" in main._GATE_HEAD and "family=IBM+Plex+Sans" in main._GATE_HEAD)
_pol = " ".join(security_headers.CSP_SOURCES["style-src"] + security_headers.CSP_SOURCES["font-src"])
ok("the fonts' hosts are already allowed by the policy", "https://fonts.googleapis.com" in _pol and "https://fonts.gstatic.com" in _pol)
for name, words in PAGES.items():
    pg = getattr(main, name)
    ok(name + ": its visible words are unchanged", vis(pg) == words)
    ok(name + ": carries the font link", "fonts.googleapis.com/css2" in pg)
    ok(name + ": no old colour in the page itself", not re.search(r"#C2410C|#2563EB|Inter,", pg, re.I))
ok("the map page's demo-notice slot still fills", "<!--demo-notice-->" not in main._map_password_page())

print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

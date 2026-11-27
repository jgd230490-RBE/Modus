"""
Write the route-line table's copy into the two pages (27 Nov 2026, claude/route-line-spec).

    python backend/tools/route_line_styles_build.py           # rewrite the copy in map/index.html and frontend/index.html
    python backend/tools/route_line_styles_build.py --check   # exit 1 when a page's copy is not the table's (the harness's check)

The ONE source is backend/route_line_styles.py. Each page carries its surfaces' part of it inline, in two generated
regions:
  * the DATA, as the first statement of the page's main script (`var ROUTE_LINE_STYLES = {...};` between
    `// route-line-styles:begin` and `// route-line-styles:end`), so the harnesses that evaluate that script alone get it;
  * the KEY SAMPLES' custom properties (`--rl-…`), a style block in the head between
    `<!-- route-line-styles:css:begin` and `<!-- route-line-styles:css:end -->`, just before `</head>`.
Inline because a page must not gain a request that can fail and leave it with no lines, and the app stays one file with
no build step. A region is replaced in place where the page has one, else written after its anchor (first run only).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

import route_line_styles as RLS  # noqa: E402

# page: (file, the CSS region's anchor (regex, written after it: after the page's own stylesheet, which several
#        harnesses read up to its first </style>), its indent,
#        the data region's anchor (regex, written after it), its indent)
PAGES = {
    "map": ("map/index.html", r'\n</style>\n(?=</head>)', "    ",
            r'<div id="map"></div>\n\n<script>\n', "    "),
    "frontend": ("frontend/index.html",
                 r'\n</style>\n(?=</head>)', "",
                 r'<script type="text/babel" data-presets="react">\n', ""),
}
CSS_RE = re.compile(r"[ \t]*<!-- route-line-styles:css:begin.*?<!-- route-line-styles:css:end -->\n", re.S)
DATA_RE = re.compile(r"[ \t]*// route-line-styles:begin.*?// route-line-styles:end\n", re.S)


def _indent(text, ind):
    return "".join(ind + ln + "\n" for ln in text.split("\n"))


def css_block(page):
    return _indent(RLS.page_css(page), PAGES[page][2])


def data_block(page):
    return _indent(RLS.page_data(page), PAGES[page][4])


def _put(text, rx, want, anchor, page):
    if rx.search(text):
        return rx.sub(lambda m: want, text, count=1)
    m = re.search(anchor, text)
    if not m:
        raise SystemExit(f"{page}: no place for the route-line styles")
    return text[:m.end()] + want + text[m.end():]


def render(page, text):
    """The page's text with its copy of the table in place."""
    rel, css_a, _ci, data_a, _di = PAGES[page]
    text = _put(text, CSS_RE, css_block(page), css_a, page)
    return _put(text, DATA_RE, data_block(page), data_a, page)


def stale(root=ROOT):
    """The pages whose copy differs from the table (empty when all are current)."""
    out = []
    for page, spec in PAGES.items():
        with open(os.path.join(root, spec[0]), encoding="utf-8", newline="") as f:
            text = f.read()
        if render(page, text) != text:
            out.append(spec[0])
    return out


def main(argv):
    if "--check" in argv:
        s = stale()
        print("stale: " + ", ".join(s) if s else "route-line styles: every page's copy is the table's")
        return 1 if s else 0
    for page, spec in PAGES.items():
        p = os.path.join(ROOT, spec[0])
        with open(p, encoding="utf-8", newline="") as f:
            text = f.read()
        new = render(page, text)
        if new != text:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            print("wrote", spec[0])
        else:
            print("current", spec[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

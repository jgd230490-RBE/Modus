WAYSCOPE — FULL REPOSITORY · 5 October 2026 · Appearance picker + the NH CPU fix
================================================================================

THIS ZIP IS THE WHOLE REPOSITORY. Every file, at its current state. Unzip it over the
Codespace and everything is up to date — nothing to pick, nothing to merge. It replaces
BOTH earlier zips (wayscope-first-look-fixes-0929.zip, already on main, and
wayscope-nh-bbox-0930.zip, which was never applied and is included here).

Built on main at dc6e8be. What is new compared with main:

1. APPEARANCE PICKER (frontend/index.html) — the request of 30 Sep / 5 Oct
   A small half-circle button at the right of the header, left of "Sign out". It opens a
   minimal popover, "Appearance", with three looks, a swatch each and a tick on the one
   in use:
     Ink    — the 29 Sep rebrand as it is today (the default)
     Light  — the same, with a white header bar (lockup on light, dark text)
     Dark   — every surface dark, orange as the control colour (buttons, links, the
              active page in the rail, the chart series)
   Closes on a choice, a click outside, or Escape. The choice is remembered per browser
   (localStorage "modus_theme", like the vehicle-name language) and applied before React
   mounts, so nothing flashes. An unknown stored value falls back to Ink.
   How it is built: html[data-theme] + CSS tokens. The 29 Sep tokens are the Ink set;
   "light" overrides only the header tokens; "dark" overrides the palette. The ~60
   Tailwind colour utilities the app uses are remapped for dark in a generated block
   (DARK-REMAP-START … END); test_h1_uk asserts every utility in the file is covered, so
   a new colour class added later without a dark rule fails the suite. Charts read
   token colours and rebuild on a change. Inputs, selects and the map's zoom control
   follow. Exports (XLSX, PDF) are documents and keep the print palette, on purpose.
   Not themed: the public corridor map at /map/ (its own page, its own basemap
   switcher) and the user guide — say if you want them to follow.

2. NATIONAL HIGHWAYS CPU FIX (backend/restrictions.py, backend/main.py) — from the
   unapplied 30 Sep zip; the live service was at 100 % CPU for hours after the routes
   were baked. A bounding-box test now runs before the vertex-by-segment loop (a strict
   lower bound, so it never hides a hit); /api/restrictions is pre-serialised and cached.
   fitBounds on the Look-ahead map is guarded (it white-screened the whole app when the
   map had no size). Detail in claude/h1-uk-0929.md.

3. A NEW HARNESS, backend/tests/dom_frontend.js: the staff app mounted in a real DOM
   (jsdom) — opens the picker, chooses Dark, reads <html>, localStorage, theme-color,
   Escape, outside-click. 12 assertions. Needs jsdom (see the file's header); without it,
   it prints SKIPPED and exits 0.

4. HOUSEKEEPING carried by the zip: .gitignore is in it (the web uploader had dropped it
   twice; the stray root file "download" was its content). After the unzip, two deletes
   that a zip cannot do are in the commands below.

Counts (fresh clone of dc6e8be + this zip, sandbox): stubbed Python 2,270 / 0, JS
1,190 / 0 (parse_map 520, parse_frontend 394, test_ipt_overlay 160, render_frontend 104,
dom_frontend 12), total 3,460 / 0; http_smoke 81 / 0. Narrowed, never deleted: two
parse_frontend assertions that quoted the header's white utilities now read the header
tokens; one test_h1_uk assertion reads /api/restrictions through the Response body.

NOT TESTED — SAY IT OUT LOUD
----------------------------
* The three looks in a real browser: the CSS was checked by the render harness and jsdom,
  the live site by the overlay you saw on 30 Sep; the real build has not been looked at.
  First look after the deploy: click the half-circle icon, try all three, then Dashboard,
  Look-ahead, Routes, Config → Costing in Dark. Anything still white or still blue in
  Dark is a utility the remap list maps wrongly — paste what you see.
* The NH check against the real feed and real baked legs (the sandbox cannot reach
  ArcGIS). First "check now" after the deploy is the test: expect seconds.

CODESPACE COMMANDS
------------------
Upload this zip as ONE file to the Codespace, then (check the name with `ls *.zip` first):

  unzip -o wayscope-full-1005.zip && rm wayscope-full-1005.zip
  git rm -q --cached download 2>/dev/null; rm -f download frontend/brand/placeholder.pl
  git add -A && git commit -m "Appearance picker (Ink / Light / Dark); NH closures bounding-box pre-filter; fitBounds guarded; dom harness" && git push

If the push is rejected as non-fast-forward:
  git pull origin main --no-rebase --no-edit
  git push

After Render deploys: hard-refresh (Ctrl+F5), sign in, the half-circle icon is next to
Sign out.

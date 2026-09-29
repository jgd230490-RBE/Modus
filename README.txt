MODUS — WAYSCOPE BRAND ASSETS · 29 September 2026
=================================================

What this is
------------
Static brand files for the rename to Wayscope, added under frontend/brand/. NO code changes:
nothing serves or references these files yet. The rebrand itself (name, header, favicon
route, theme, tests) is the next session's work, from claude/rebrand-brief-0929.md in the
Claude project. Putting the files in the repo first means that session can push code only.

Files added (18)
----------------
frontend/brand/logo-header-on-dark.svg, logo-header-on-light.svg, logo-header-mono-white.svg,
mark.svg, logo-stacked-on-dark.svg, logo-stacked-on-light.svg, theme-tokens.css,
favicon.svg, favicon.ico, favicon-16.png, favicon-32.png, favicon-48.png, apple-touch-icon.png,
icon-192.png, icon-512.png, icon-512-maskable.png, site.webmanifest, og-image-1200x630.png,
and frontend/brand/README.md describing them.

Nothing to action, nothing removed
----------------------------------
No data files. No env vars. Render will redeploy main after the merge and nothing changes on
the live site, because nothing references these files.

Verified
--------
backend/tests/test_modus.py: 148 passed, 0 failed at HEAD 830c153 before AND after adding
these files (the project-term scan reads .md/.txt/.json and finds nothing; the README.txt
rule is satisfied because this note starts with "MODUS — ").
Not run: the other harnesses (nothing they read changed), CI on GitHub's runners.

Apply in the Codespace
----------------------
Upload wayscope-brand-assets-0929.zip as ONE file to the repo root, then:

  unzip -o wayscope-brand-assets-0929.zip && rm wayscope-brand-assets-0929.zip
  git checkout -b claude/brand-assets
  git add -A && git commit -m "Wayscope brand assets under frontend/brand (files only)" && git push -u origin claude/brand-assets

Then on github.com: Pull requests → New pull request → claude/brand-assets → Create → Merge.
(If you would rather commit straight to main, drop the checkout line and run
  git add -A && git commit -m "Wayscope brand assets under frontend/brand (files only)" && git push
— it is safe: files only, nothing served.)

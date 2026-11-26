# Wayscope brand assets (29 Sep 2026)

Static files only. Nothing serves or references them yet; the rebrand session wires them in
(see `claude/rebrand-brief-0929.md` in the Claude project).

- `logo-header-on-dark.svg` — the app header lockup (white wordmark, colour mark). Tight box:
  set the height in CSS (36–40 px) and the width follows.
- `logo-header-on-light.svg` — for white pages (the user guide's nav).
- `logo-header-mono-white.svg` — single-colour fallback.
- `mark.svg` — icon only (narrow screens, the map's corner, PDF exports).
- `logo-stacked-on-dark.svg` / `-on-light.svg` — sign-in and map-password pages.
- `favicon.svg`, `favicon.ico` (16/32/48), `favicon-*.png`, `apple-touch-icon.png`,
  `icon-192.png`, `icon-512.png`, `icon-512-maskable.png`, `site.webmanifest` — the favicon set.
  Serve them at the site root (the manifest's paths are root-relative).
- `og-image-1200x630.png` — link preview for the landing page.
- `theme-tokens.css` — the brand colour variables. Orange is the brand accent only; amber keeps
  meaning "warning" in the app and blue keeps meaning control/link.

The wordmark is set in Sora Medium and converted to outlines, so no font is loaded.

24 Nov 2026: each file's frame (its `viewBox`) now holds the whole drawing. The tight files' frame started 9 units
below the top of the first dot, so a page cut about a pixel off it; the frame was moved up, same size, and the mark sits
in its middle. The tall files' frame is 6 units taller, for the tails of the "y" and the "p". No shape was changed.
`backend/tests/test_bulletin.py` checks every file draws inside its frame. The brand kit's generator was not changed:
files made from it again need the same check.
Masters (SVG/PDF/PNG), social covers and business-card artwork are in the brand kit zip
(`wayscope-brand-final-0929.zip`), not in the repo.

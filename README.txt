WAYSCOPE — H5a · LANDING PAGE · 6 October 2026
==============================================

Built on main at 42888f7 (H2 fix 3/3). This zip ADDS the landing page and its test, and
EDITS backend/main.py (one mount). It touches nothing else.

WHAT CHANGED
- landing/index.html        the public landing page, built from the approved design canvas.
                            No script, no tracking. Six bracketed placeholders for you:
                            [MAP CODE] [PLANNER CODE] [TEAM CODE] [STAND NUMBER] [EMAIL]
                            [COMPANY NAME AND NUMBER]. Six media frames marked
                            [SCREEN RECORDING…] / [EXPLAINER n…] wait on the videos.
- landing/assets/           six brand files copied from frontend/brand/ so the folder stands
                            alone (logo on light/dark, favicon.svg/.ico, apple-touch-icon,
                            og-image).
- backend/main.py           +5 lines: mounts landing/ at /landing/ for PREVIEW, before the
                            catch-all "/", not gated, check_dir=False.
- backend/tests/test_landing.py   49 assertions: parses, anchors resolve, assets present,
                            no script, og tags, banned words (secure, Modus, trusted by,
                            testimonial, real-time, AI, optimise, predict, telematics,
                            live tracking, truck), says "fictional", links the demo host.

SUITE IN THE SANDBOX
- test_landing.py 49/0 · test_modus.py 193/0 · test_help.py 40/0 · test_gate.py 111/0.
- Other harnesses untouched and not rerun.

NOT VERIFIED
- The page has not been rendered: the sandbox could not download Chromium this session. The
  layout is the canvas's; your first look is https://<modus-web host>/landing/ after merge.
- The Render static site is NOT created and render.yaml is untouched (the root domain is
  still the app's — H0). Steps are in claude/landing-1006.md.
- og:image is a relative path, which link previews ignore; it becomes absolute once the
  final domain is known.
- .github/workflows/suite.yml is NOT in this repo at 42888f7. If it exists on your side,
  add `python3 backend/tests/test_landing.py` to it.

ALSO IN THIS DELIVERY, FOR THE CLAUDE PROJECT (not the repo)
- claude_landing-1006.md, claude_map-redesign-1006.md (new)
- claude_roadmap-patch-0926-highways-uk.md, claude_for-grok.md (updated: replace)

CODESPACE
  unzip -o wayscope-h5a-landing-1006.zip && rm wayscope-h5a-landing-1006.zip
  git add -A && git commit -m "H5a: landing page, /landing preview mount, test_landing" && git push
Then open  /landing/  on the Render URL.

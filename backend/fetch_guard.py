"""
fetch_guard.py — ONE big fetch at a time (29 Oct 2026); since 23 Nov 2026 the one lock of the "Working" list.

The community layer's fetch (Geofabrik, GIAS, NaPTAN) and the collision history's fetch (DfT, five years, plus the traffic
counts) each read large files on a thread. Run together on live they took the web service over its 512 MB on 29 Oct 2026
(09:12 UTC, after the U8c re-import): Render restarted it and both threads died, leaving their rows 'running' until the stale
rule cleared them. Each start_refresh takes this one lock while it checks and marks its run. Per process: the service runs
one worker (test_areas pins render.yaml).

23 Nov 2026 (claude/working-list, John's yes to the mockup's card 3): the rule is now ONE LONG JOB AT A TIME for every
kind in the "Working" list (working.py), not only the two fetches against each other, and the refusal is one sentence
made in one place (working.refusal). The two sentences that lived here (BUSY_WORDS, other_running) are gone; a start
that must check and mark atomically still takes LOCK, and working.py takes the same one.
"""
import threading

LOCK = threading.Lock()

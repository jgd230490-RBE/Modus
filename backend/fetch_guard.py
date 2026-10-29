"""
fetch_guard.py — ONE big fetch at a time (29 Oct 2026).

The community layer's fetch (Geofabrik, GIAS, NaPTAN) and the collision history's fetch (DfT, five years, plus the traffic
counts) each read large files on a thread. Run together on live they took the web service over its 512 MB on 29 Oct 2026
(09:12 UTC, after the U8c re-import): Render restarted it and both threads died, leaving their rows 'running' until the stale
rule cleared them. Each start_refresh now takes this one lock while it checks and marks its run, and refuses while the OTHER
fetch is running, with words a person can act on. Per process: the service runs one worker (test_areas pins render.yaml).
"""
import threading

LOCK = threading.Lock()

BUSY_WORDS = {
    "community": "The community considerations are being fetched. Fetch the collision history when that has finished.",
    "collisions": "The collision history is being fetched. Fetch the community considerations when that has finished.",
}


def other_running(me):
    """The words to refuse with when the other big fetch is running for this tenant, else None. `me` is 'community' or
    'collisions'."""
    import collisions
    import community
    other = {"community": collisions, "collisions": community}[me]
    if other.status().get("state") == "running":
        return BUSY_WORDS["collisions" if me == "community" else "community"]
    return None

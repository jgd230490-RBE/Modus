"""
Community considerations per route (30 Oct 2026, task 4b) — the Routes page's "Near the route" column.

For every road route that has a drawn line: how many of each kind of community consideration (schools, hospitals,
health centres, community centres, sports facilities, stations and tram stops, bus stops, residential areas) lie within
route_compare.NEAR_M of the line, both legs, every lorry type — the SAME rule and the same pass the collision evidence and
the route comparison use (route_compare.near_counts), so a number on the Routes page equals the one on the evidence for the
route's main line. Counts only: nothing is scored, rated or ranked.

Reads what is stored; nothing is fetched. A route with no drawn line is left out (the page shows a dash). `fetched_at` is
None until the community layer has been fetched (the page then says "Not fetched" instead of a misleading none).
An alternative option and a way round are not counted here (their keys carry an "@"); the evidence PDF has them side by side.
Abnormal loads' lines are in the same index under their own ids and are left out (only the tenant's routes are listed).
"""
import db
import collisions
import community
import route_compare

KINDS = route_compare.KINDS
NEAR_M = route_compare.NEAR_M


def counts(team=None):
    """{"fetched_at", "near_m", "kinds": [{key, label}], "routes": {route_id: {kind: n}}}. `team` = a team slot to keep
    only that team's routes (a team code reads its own team's routes)."""
    tenant = db.current_tenant()
    rows = db.query("SELECT id, ipt FROM routes WHERE tenant_id = ? ORDER BY id", (tenant,))
    if team:
        import access
        want = access.canonical_ipt(team) or team
        rows = [r for r in rows if (access.canonical_ipt(r.get("ipt")) or r.get("ipt")) == want]
    ids = {r["id"] for r in rows}
    fetched_at = (community.status() or {}).get("fetched_at")
    routes = {}
    if fetched_at and ids:
        index = collisions.index_from_db()
        drawn = [k for k, _line in index.lines if k in ids]
        routes = route_compare.near_counts(index, drawn)
    return {"fetched_at": fetched_at, "near_m": NEAR_M,
            "kinds": [{"key": k, "label": community.KIND_BY_KEY[k]["label"]} for k in KINDS],
            "routes": routes, "drawn": sorted(routes) if routes else []}

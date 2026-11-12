"""
When the forecast last changed: the date the public map prints as "Approved plan · updated 31 Oct"
(10 Nov 2026, frontier check Idea 3, branch claude/map-first-view).

The forecasts table holds no time of its own, so the date comes from the audit trail, which records
every write that worked (main._audit_write). The rule: the newest 2xx write that can change the
approved plan —

    PUT    /api/routes/{route}/status   approve, reject or reopen a line
    POST   /api/forecasts/bulk          save a line (a planner's save can approve it)
    DELETE /api/forecasts/{route}       withdraw lines
    POST   /api/admin/tenant/import     the organisation file (the whole plan replaced)

Some of those touch only a Pending line, so the date can be LATER than the last change to the
approved figures, never earlier. Rejected at the build: "the last approval only" (misses a
withdrawal or an un-approval, so it could read older than the plan really is) and "the last
re-import only" (misses every hand edit). On the live demo on 10 Nov all three read 31 Oct 2026.

No audit row (a deployment loaded outside the app, or before G3's audit trail): None, and the map
keeps its old words. A date is never invented.

Not cached: the audit row is written by the middleware AFTER the handler has bumped the data
version, so a cached answer could keep the old date until the next write. The read is one indexed
LIMIT 1 on audit_log (tenant_id, at).
"""
import db

PLAN_WRITES_SQL = (
    "SELECT at FROM audit_log WHERE tenant_id = ? AND kind = 'write' "
    "AND status >= 200 AND status < 300 AND ("
    "(method = 'PUT' AND path LIKE '/api/routes/%/status') "
    "OR (method IN ('POST', 'DELETE') AND path LIKE '/api/forecasts/%') "
    "OR (method = 'POST' AND path = '/api/admin/tenant/import')"
    ") ORDER BY at DESC LIMIT 1"
)


def _london_date(at):
    """'2026-10-31T09:15:43Z' -> '2026-10-31', the day in the UK (a write at 00:30 BST is the next day)."""
    from datetime import datetime, timezone
    s = str(at or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        dt = dt.astimezone(ZoneInfo("Europe/London"))
    except Exception:                    # noqa: BLE001 — no tz database: the UTC day
        pass
    return dt.date().isoformat()


def last_change():
    """The UK date (YYYY-MM-DD) of the newest write that can change the approved plan, or None."""
    tenant_id = db.current_tenant()
    try:
        rows = db.query(PLAN_WRITES_SQL, (tenant_id,))
    except Exception as e:               # noqa: BLE001 — the map must still answer
        print(f"⚠️  plan date not read: {e.__class__.__name__}: {str(e)[:200]}")
        return None
    return _london_date(rows[0]["at"]) if rows else None

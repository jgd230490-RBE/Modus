"""
A helper for test_route_points.py and by hand (NOT a harness): open, or make once, a local SQLite copy of an organisation
file (live's own export) so the take-care block can be read on REAL lines, limits and places. Never in CI: the file is
held offline and is never committed. Used with WAYSCOPE_POINTS_EXPORT=<path to the organisation file> and
WAYSCOPE_POINTS_DB=<path to the SQLite file to make or reuse>.

    import points_livecopy; points_livecopy.open_copy(export_path, db_path)   # imports when the DB file is absent
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, BACKEND)


def open_copy(export_path, db_path):
    """Points db at db_path; imports export_path into it (replace) when the file does not exist yet. Returns a summary."""
    os.environ.pop("DATABASE_URL", None)
    os.environ["WAYSCOPE_WARM_CACHE"] = "0"
    import db
    db._SQLITE_PATH = db_path
    fresh = not os.path.exists(db_path)
    import conversions
    import config
    import costing
    import taxonomy
    import tenant_package
    db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db()
    db.init_gates_db(); db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db()
    db.init_costing_db(); db.init_tenant()
    out = {"fresh": fresh}
    if fresh:
        taxonomy.seed_taxonomy()
        config.seed_from_file(conversions)
        with open(export_path, encoding="utf-8") as f:
            pkg = json.load(f)
        res = tenant_package.import_tenant(pkg, replace=True)
        out["import"] = {k: res.get(k) for k in ("ok", "error") if k in res}
    config.invalidate(); costing.invalidate()
    return out

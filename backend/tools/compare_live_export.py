"""
Compare a live organisation export with a demo package, table by table (29 Oct 2026, task 3d).

WHY: before a full re-import of the demo, the question "what is on live that the generator does not make?" was
answered by guesswork. This lists it. Run it on the export (Config -> Organisation file -> Download) and on a
package from `make_demo_tenant.py`; it prints, for every table, the rows only live has, the rows only the package
has, and the rows that differ, and which tables are baked or fetched (a replace removes them; the re-bake brings
them back).

    python backend/tools/compare_live_export.py live-export.json live.package.json [--show 5]

Numbers are compared to 4 decimals, booleans as 0/1, and every column ending `_at` is ignored (import times).
Read-only: it opens the two files and prints. Outside the checkout is fine; nothing is written.
"""
import argparse
import json
import sys

# Tables a re-import removes and a re-bake or a fetch brings back: never "folded" into the generator.
BAKED = ("route_geometry", "route_sections", "route_area_km", "route_hour_times", "route_choice",
         "traffic_counts", "collision_records", "collision_meta", "community_features", "community_meta")
# Columns a bake, a check or a draw fills on the row itself.
DERIVED = {"routes": ("limits_hits", "limits_status", "restrictions_hits", "restrictions_status"),
           "abnormal_loads": ("roads_json", "pinch_json", "return_geometry_json", "geometry_json",
                              "return_geometry", "duration_hr", "distance_km", "pinch_note", "bake_error",
                              "limits_hits_json", "limits_status")}
# How a table's rows are keyed. Tables not listed use the first of id / key / code / section_id / area_id.
KEYS = {"forecasts": ("route_id", "month_index", "discipline", "section_id"),
        "forecast_weeks": ("route_id", "month_index", "discipline", "section_id", "week_index"),
        "forecast_days": ("route_id", "day_date", "discipline", "section_id"),
        "stockpile_weeks": ("location_id", "month_index", "week_index"),
        "stockpile_plan": ("location_id", "month_index"),
        "route_haul_roads": ("route_id", "seq")}
ONE_KEY = ("id", "key", "code", "section_id", "area_id")


def _norm(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    return v


def _row(r, ignore):
    return {k: _norm(v) for k, v in r.items() if k not in ignore and not k.endswith("_at")}


def _key(table, r):
    if table in KEYS:
        return tuple(r.get(c) for c in KEYS[table])
    for c in ONE_KEY:
        if c in r:
            return (r[c],)
    return (json.dumps(_row(r, ()), sort_keys=True, default=str),)


def load_tables(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return doc.get("tables", doc)


def compare(live, gen, show=5):
    """Return {table: {live, gen, only_live, only_gen, changed, baked}} (the sample lists are cut to `show`)."""
    out = {}
    for t in sorted(set(live) | set(gen)):
        ig = DERIVED.get(t, ())
        lrows, grows = live.get(t) or [], gen.get(t) or []
        ld = {_key(t, r): r for r in lrows}
        gd = {_key(t, r): r for r in grows}
        only_live = [k for k in ld if k not in gd]
        only_gen = [k for k in gd if k not in ld]
        changed = {}
        for k in ld:
            if k in gd:
                a, b = _row(ld[k], ig), _row(gd[k], ig)
                d = {c: (a.get(c), b.get(c)) for c in set(a) | set(b) if a.get(c) != b.get(c)}
                if d:
                    changed[k] = d
        out[t] = {"live": len(lrows), "gen": len(grows), "only_live": len(only_live), "only_gen": len(only_gen),
                  "changed": len(changed), "baked": t in BAKED,
                  "sample_only_live": only_live[:show], "sample_only_gen": only_gen[:show],
                  "sample_changed": dict(list(changed.items())[:show])}
    return out


def verdict(row):
    """One word for a table's row: same, baked (re-bake brings it back), or differs (read it)."""
    if row["only_live"] == row["only_gen"] == row["changed"] == 0 and row["live"] == row["gen"]:
        return "same"
    if row["baked"]:
        return "baked"
    return "differs"


def report(res):
    lines = [f"{'table':<22}{'live':>7}{'package':>9}{'only live':>11}{'only pkg':>10}{'changed':>9}  verdict"]
    for t, r in res.items():
        lines.append(f"{t:<22}{r['live']:>7}{r['gen']:>9}{r['only_live']:>11}{r['only_gen']:>10}{r['changed']:>9}  {verdict(r)}")
    for t, r in res.items():
        if verdict(r) != "differs":
            continue
        lines.append(f"\n{t}")
        for k in r["sample_only_live"]:
            lines.append(f"  only on live : {k}")
        for k in r["sample_only_gen"]:
            lines.append(f"  only package : {k}")
        for k, d in r["sample_changed"].items():
            lines.append(f"  changed      : {k} {json.dumps(d, default=str)[:300]}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("live_export")
    ap.add_argument("package")
    ap.add_argument("--show", type=int, default=5, help="sample rows printed per differing table")
    a = ap.parse_args(argv)
    res = compare(load_tables(a.live_export), load_tables(a.package), a.show)
    sys.stdout.reconfigure(encoding="utf-8")
    print(report(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())

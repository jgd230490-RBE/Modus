"""
Phase 2 — the discipline taxonomy.

Three layers sit above a movement:

    1. discipline          senior managers, programme reporting   (new, this module)
    2. material category   planning: density, payload, emissions  (factors.json)
    3. material item       the engineer's own words               (forecasts.material_description)

Discipline and material category are MANY-TO-MANY, not a tree. Ballast serves both
substructure (sub-ballast) and superstructure (track ballast); nest it under one and the
copies drift.

A discipline never enters routing. Route validity stays origin.supplies n dest.receives on
material categories — the discipline layer sits above that and only ever derives a
destination's `receives`.
"""
import json
import re

import db

# --------------------------------------------------------------------------- #
#  Disciplines                                                                 #
# --------------------------------------------------------------------------- #
# sort_order is "programme order", which was a stated requirement with no values behind
# it. The order below is a construction-sequence reading -- diversions and construction
# bases before bulk earth moves, track last, stations last of all -- and is MINE, not
# sourced from a project document. Confirm it before anyone reports off it. Gaps of ten
# so a discipline can be slotted between two others without renumbering.
DISCIPLINES = [
    # (id, label, sort_order, in_scope, scope_note)
    # A generic linear-infrastructure taxonomy. Notes describe the discipline, not any
    # one project; a tenant edits labels, order and scope on its own rows.
    ("utilities", "Utilities", 10, True,
     "Third-party diversions and protections - HV, telecom, water, gas. Standalone "
     "because lead times run years and it gates everything downstream."),
    ("temporary_works", "Temporary Works", 20, True,
     "Construction bases, hardstanding, access roads, site facilities."),
    ("earthworks", "Earthworks", 30, True,
     "Bulk fill, cut, soil improvement, slope stabilisation. Kept separate from "
     "substructure because the material flows differ."),
    ("substructure", "Substructure", 40, True,
     "Formation beneath the running surface, drainage, culverts, cable channels, ducts "
     "and chambers. Drainage is civils here, not MEP."),
    ("structures", "Structures", 50, True,
     "Bridges, viaducts, retaining walls, noise barriers."),
    ("superstructure", "Superstructure", 60, True,
     "The running surface: ballast, sleepers, rails, fastenings, switches and crossings "
     "on a railway; pavement layers on a road."),
    ("stations", "Stations", 70, True,
     "Terminals, platforms, depots, maintenance buildings, architectural - and their "
     "MEP until the mep discipline is switched on."),
    # Reserved. Seeded now so bringing one into scope is one UPDATE, not a migration.
    ("mep", "MEP", 80, False,
     "Building services. Out of scope by default; switching it on also means moving "
     "the `stations` rows that were really MEP."),
    ("ene", "Energy / Electrification", 90, False,
     "OCS, substations, SCADA. Often procured separately; out of scope by default."),
    ("ccs", "Control, Command & Signalling", 100, False,
     "Signalling and control systems. Often procured separately; out of scope by default."),
]

# The authoritative seed for discipline_materials, not an illustration. A destination's
# derived `receives` is exactly this list for the disciplines it serves.
DISCIPLINE_MATERIALS = {
    "earthworks": ["Earthworks / soil", "Small aggregate"],
    "substructure": ["Small aggregate", "Large aggregate / ballast",
                     "Precast / concrete", "General / imported"],
    "utilities": ["General / imported", "Precast / concrete"],
    "structures": ["Precast / concrete", "Steel / rail", "General / imported"],
    "superstructure": ["Large aggregate / ballast", "Steel / rail", "Precast / concrete"],
    "stations": ["Precast / concrete", "Steel / rail", "General / imported"],
    "temporary_works": ["Small aggregate", "Large aggregate / ballast", "General / imported"],
    # mep / ene / ccs carry no material rows until they come into scope.
}

# --------------------------------------------------------------------------- #
#  Teams, design sections, work sections — TENANT DATA, not shipped            #
# --------------------------------------------------------------------------- #
# G2, 16 Sep 2026. The product used to seed one project's six teams ("IPTs"), three
# design sections and fifteen work sections here. Those are a tenant's own structure
# and now arrive in its package (tenant_package.import_tenant) or are typed on the
# admin pages. The lists stay as empty hooks so seed_taxonomy()'s shape is unchanged
# and a test can pass its own rows through tenant_package.import_rows().
#
# Vocabulary: the table is still `ipts` and the column still `ipt` — internal names.
# The word a user sees is the tenant's `team_label` (config.tenant_settings).
IPTS = []
DESIGN_SECTIONS = []
WORK_SECTIONS = []

_DS3_DATUM = ""

DEFAULT_BUNDLE_SPEC = {"disciplines": DISCIPLINES, "discipline_materials": DISCIPLINE_MATERIALS,
                       "ipts": IPTS, "design_sections": DESIGN_SECTIONS,
                       "work_sections": WORK_SECTIONS, "ds3_datum": _DS3_DATUM}


def _ws_scope_note(note, has_km, datum=""):
    """The row's own note, with the bundle's datum warning appended wherever a km value exists."""
    parts = [p for p in ((note or "").strip(),) if p]
    if has_km and datum:
        parts.append(datum)
    return " ".join(parts).strip() or None


DEFAULT_BUNDLE = DEFAULT_BUNDLE_SPEC


def load_bundle(path):
    """A taxonomy bundle from a JSON file (the legacy list-of-lists shape). For tests
    and migration tools; the product's own path is tenant_package.import_tenant()."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {
        "disciplines": [tuple(r) for r in raw.get("disciplines") or []],
        "discipline_materials": raw.get("discipline_materials") or {},
        "ipts": [tuple(r) for r in raw.get("ipts") or []],
        "design_sections": [tuple(r) for r in raw.get("design_sections") or []],
        "work_sections": [tuple(r) for r in raw.get("work_sections") or []],
        "ds3_datum": raw.get("ds3_datum") or "",
    }


def seed_taxonomy(bundle=None):
    """
    Insert the taxonomy if it isn't already there. Idempotent and additive: it never
    updates or deletes an existing row, so an edit made in the database survives a
    redeploy.

    Since G2 (16 Sep 2026) only the generic disciplines and their materials are seeded:
    teams, design sections and work sections are the tenant's own rows and come from
    its package. The loops below stay so a package's rows, once inserted, are never
    duplicated by a restart.
    """
    counts = {"disciplines": 0, "discipline_materials": 0, "ipts": 0,
              "design_sections": 0, "work_sections": 0}
    b = bundle or DEFAULT_BUNDLE
    DISCIPLINES_ = b["disciplines"]
    DISCIPLINE_MATERIALS_ = b["discipline_materials"]
    IPTS_ = b["ipts"]
    DESIGN_SECTIONS_ = b["design_sections"]
    WORK_SECTIONS_ = b["work_sections"]
    datum = b.get("ds3_datum") or ""

    # Every read and write below is scoped to the current tenant, so "is it already
    # there" is asked of this tenant's rows only. A second tenant seeds its own copy of
    # the taxonomy rather than inheriting the first one's — and an edit one client makes
    # to a discipline label cannot show up in another's picker.
    tenant = db.current_tenant()

    have = {r["id"] for r in db.query("SELECT id FROM disciplines WHERE tenant_id = ?",
                                      (tenant,))}
    for did, label, order, in_scope, note in DISCIPLINES_:
        if did in have:
            continue
        db.execute(
            "INSERT INTO disciplines (tenant_id, id, label, sort_order, in_scope, "
            "scope_note, active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant, did, label, order, bool(in_scope), note, True),
        )
        counts["disciplines"] += 1

    have_dm = {(r["discipline_id"], r["material_category"])
               for r in db.query("SELECT discipline_id, material_category FROM "
                                 "discipline_materials WHERE tenant_id = ?", (tenant,))}
    for did, cats in DISCIPLINE_MATERIALS_.items():
        for cat in cats:
            if (did, cat) in have_dm:
                continue
            db.execute(
                "INSERT INTO discipline_materials (tenant_id, discipline_id, "
                "material_category) VALUES (?, ?, ?)",
                (tenant, did, cat),
            )
            counts["discipline_materials"] += 1

    have_i = {r["id"] for r in db.query("SELECT id FROM ipts WHERE tenant_id = ?",
                                        (tenant,))}
    for iid, label in IPTS_:
        if iid in have_i:
            continue
        db.execute(
            "INSERT INTO ipts (tenant_id, id, label, manager, active, merged_into) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tenant, iid, label, None, True, None),
        )
        counts["ipts"] += 1

    have_ds = {r["id"] for r in db.query("SELECT id FROM design_sections WHERE tenant_id = ?",
                                         (tenant,))}
    for dsid, label, note in DESIGN_SECTIONS_:
        if dsid in have_ds:
            continue
        db.execute(
            "INSERT INTO design_sections (tenant_id, id, label, km_from, km_to, scope_note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tenant, dsid, label, None, None, note),
        )
        counts["design_sections"] += 1

    # Work sections. Additive like everything above: a section already in the table is
    # skipped, never rewritten, so a km value or a scope_note corrected in the database
    # survives the next redeploy. Correcting one of these rows in code therefore does
    # NOT reach a database that already has it -- edit the row, or delete it and let
    # this re-seed it.
    have_ws = {r["section_id"] for r in db.query(
        "SELECT section_id FROM work_sections WHERE tenant_id = ?", (tenant,))}
    for sid, name, ipt_id, ds_id, km_from, km_to, parent, note in WORK_SECTIONS_:
        if sid in have_ws:
            continue
        db.execute(
            "INSERT INTO work_sections (tenant_id, section_id, parent_section_id, "
            "design_section_id, ipt_id, name, primary_discipline, in_scope, active, "
            "km_from, km_to, scope_note, receives_override) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tenant, sid, parent, ds_id, ipt_id, name,
             # primary_discipline stays NULL -- open-questions §A4. See WORK_SECTIONS.
             None, True, True, km_from, km_to,
             _ws_scope_note(note, km_from is not None or km_to is not None, datum),
             None),
        )
        counts["work_sections"] += 1

    return counts


# --------------------------------------------------------------------------- #
#  Reads                                                                       #
# --------------------------------------------------------------------------- #
def list_disciplines(include_out_of_scope=False):
    """In programme order. Out-of-scope disciplines are hidden from pickers by default."""
    rows = db.query(
        "SELECT id, label, sort_order, in_scope, scope_note, active FROM disciplines "
        "WHERE tenant_id = ? ORDER BY sort_order, id",
        (db.current_tenant(),)
    )
    by_disc = {}
    for m in db.query("SELECT discipline_id, material_category FROM discipline_materials "
                      "WHERE tenant_id = ? ORDER BY material_category",
                      (db.current_tenant(),)):
        by_disc.setdefault(m["discipline_id"], []).append(m["material_category"])

    out = []
    for r in rows:
        r["in_scope"] = bool(r["in_scope"])
        r["active"] = bool(r["active"])
        # the categories this discipline moves, so the submission UI can advise without
        # a second request. Advisory only — the join is deliberately permissive.
        r["materials"] = by_disc.get(r["id"], [])
        if not r["active"]:
            continue
        if not r["in_scope"] and not include_out_of_scope:
            continue
        out.append(r)
    return out


def materials_for(discipline_id):
    """The material categories one discipline moves."""
    return [r["material_category"] for r in db.query(
        "SELECT material_category FROM discipline_materials "
        "WHERE tenant_id = ? AND discipline_id = ? "
        "ORDER BY material_category", (db.current_tenant(), discipline_id))]


def derive_receives(discipline_ids):
    """
    A destination's `receives` = the union of the material categories of every discipline
    delivered to it. This replaces hand-authoring a material list per work section -- 90
    checkboxes that silently drift.

    It replaces only the `receives` half. network.backfill_supplies_receives() also fills
    `supplies`, and route validity is origin.supplies n dest.receives, so removing that
    function outright breaks route authoring for origins. Keep its supplies half.
    """
    seen, out = set(), []
    for did in discipline_ids or []:
        for cat in materials_for(did):
            if cat not in seen:
                seen.add(cat)
                out.append(cat)
    return out


def list_ipts(active_only=True):
    rows = db.query("SELECT id, label, manager, active, merged_into FROM ipts "
                    "WHERE tenant_id = ? ORDER BY id", (db.current_tenant(),))
    for r in rows:
        r["active"] = bool(r["active"])
    return [r for r in rows if r["active"]] if active_only else rows


# --------------------------------------------------------------------------- #
#  Team words (G2 label-only decision, 16 Sep 2026)                            #
# --------------------------------------------------------------------------- #
# Team ids stay the internal slots IPT1..IPT6 — the access codes (IPT1_CODE…), the
# forecasts.ipt column and canonical_ipt() are built on them. What a PERSON reads is the
# tenant's own label for the slot ("North Team"), or "<team word> <n>" when the tenant has
# not named it. Every place that shows a team value to someone goes through team_text().
_TEAM_ID = re.compile(r"\bipt\s*[-_ ]?\s*([1-6])\b", re.I)


def team_labels():
    """{team id: the tenant's label} for every team row, active or not."""
    try:
        return {r["id"]: (r.get("label") or r["id"]) for r in list_ipts(active_only=False)}
    except Exception:
        return {}


def _team_word():
    try:
        import config
        import conversions
        return config.tenant_settings(conversions).get("team_label") or "Team"
    except Exception:
        return "Team"


def team_name(team_id, labels=None, word=None):
    """'IPT3' -> the tenant's label for it, else '<team word> 3'. Not an id -> unchanged."""
    if team_id is None or team_id == "":
        return team_id
    m = _TEAM_ID.fullmatch(str(team_id).strip())
    if not m:
        return team_id
    key = f"IPT{m.group(1)}"
    labels = team_labels() if labels is None else labels
    if labels.get(key):
        return labels[key]
    return f"{word or _team_word()} {m.group(1)}"


def team_text(value, labels=None, word=None):
    """
    A team value as a person reads it: every team id inside it ("IPT3", "ipt 3",
    "IPT-3", "IPT3 / IPT6") becomes the tenant's label; any other text is left alone.
    """
    if value is None or value == "":
        return value
    labels = team_labels() if labels is None else labels
    word = word or (None if labels and len(labels) >= 6 else _team_word())
    return _TEAM_ID.sub(lambda m: team_name(f"IPT{m.group(1)}", labels, word or "Team"), str(value))


def team_ids():
    """The tenant's own team ids, in order — empty when the tenant defines none."""
    try:
        return [r["id"] for r in list_ipts(active_only=True)]
    except Exception:
        return []


def list_work_sections(in_scope_only=False):
    rows = db.query(
        # km_from / km_to joined the SELECT when the fifteen rows were seeded. They are
        # LOCAL DS3 chainage and every row carrying one repeats that in scope_note —
        # anything that displays them must display the datum with them.
        "SELECT section_id, parent_section_id, design_section_id, ipt_id, name, "
        "primary_discipline, in_scope, active, km_from, km_to, scope_note "
        "FROM work_sections WHERE tenant_id = ? ORDER BY section_id",
        (db.current_tenant(),)
    )
    for r in rows:
        r["in_scope"] = bool(r["in_scope"])
        r["active"] = bool(r["active"])
    # ⚠️ Ordered in Python, not by the SQL. `ORDER BY section_id` is lexicographic on
    # both backends, and with fifteen rows that puts WS1, WS10, WS11 … WS15, WS2, WS3
    # in the Submit Forecast picker — which reads as a bug and hides WS2 below WS15.
    # Sorting on the numeric tail fixes it without assuming every id is WSn: an id
    # with no digits keeps its place alphabetically after the numbered ones.
    rows.sort(key=_ws_sort_key)
    if in_scope_only:
        rows = [r for r in rows if r["in_scope"] and r["active"]]
    return rows


def _ws_sort_key(row):
    sid = row.get("section_id") or ""
    head = sid.rstrip("0123456789")
    tail = sid[len(head):]
    return (head, 0, int(tail)) if tail else (head, 1, 0)

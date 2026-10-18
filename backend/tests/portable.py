"""
pdftotext for the harnesses, in a form every machine agrees on.

poppler's pdftotext (Linux, CI) reads the PDF from stdin when the input is "-". Xpdf's
pdftotext — the one Git for Windows ships in mingw64/bin, so it is on PATH on this laptop —
does not: it prints its usage, exits 99 and the harness read "" as the PDF's text (7 Oct 2026,
"4 pages, 0 headers"). Both accept a file path, and both accept "-" for stdout, so the PDF goes
through a temp file. Both take -enc UTF-8 (Xpdf defaults to Latin-1, which would turn "©",
"·" and "–" into other bytes) and -eol unix.

Without pdftotext at all the harnesses fall back to the raw bytes decoded as Latin-1 — the
same fallback they always had — which only satisfies assertions on uncompressed strings.

Also here: remove_scratch_db — every harness deletes its scratch SQLite file before a fresh
schema, and Windows refuses to unlink a file another handle still has open (WinError 32).

And fixture_today — the date the week render fixtures are written for (11 Oct 2026).
"""
import datetime
import os
import shutil
import subprocess
import tempfile


def pdf_text(pdf_bytes, fallback=None, raw=False):
    """The PDF's text by pdftotext: -layout (the page as laid out, the default) or, with raw=True, -raw (the order the
    text is drawn in — two columns read one after the other, not across; 14 Oct 2026, the bulletin's Sources)."""
    if not shutil.which("pdftotext"):
        return pdf_bytes.decode("latin-1") if fallback is None else fallback
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(pdf_bytes)
        out = subprocess.run(["pdftotext", "-raw" if raw else "-layout", "-enc", "UTF-8", "-eol", "unix", path, "-"],
                             capture_output=True, timeout=60)
        return out.stdout.decode("utf-8", errors="replace")
    finally:
        os.remove(path)


def offline(export_module):
    """
    Point export's urlopen at a stub that refuses every request, so build_pdf takes the
    schematic branch wherever the harness runs. The sandbox had no route to api.mapbox.com and
    the harnesses were written on that; this laptop (7 Oct 2026) reaches it, and a harness
    must not spend a Mapbox call — or depend on the answer — to pass. Returns the original.
    """
    import urllib.error
    real = export_module.urllib.request.urlopen

    def _refuse(req, timeout=0):
        raise urllib.error.URLError("harness: offline — Mapbox is never called from a test")
    export_module.urllib.request.urlopen = _refuse
    return real


def remove_scratch_db(db, tmp_dir):
    """
    Delete db._SQLITE_PATH before a fresh schema. On Linux an open handle does not block the
    unlink; on Windows it does, and a cursor the harness is still holding is enough. Collect
    garbage and retry once; if the file is still held, move the harness to a NEW file in the
    same temp dir — every db.get_conn() reads _SQLITE_PATH at call time, so nothing else needs
    to know.
    """
    import gc
    if not os.path.exists(db._SQLITE_PATH):
        return
    try:
        os.remove(db._SQLITE_PATH)
        return
    except PermissionError:
        gc.collect()
    try:
        os.remove(db._SQLITE_PATH)
    except PermissionError:
        n = sum(1 for f in os.listdir(tmp_dir) if f.endswith(".db")) + 1
        db._SQLITE_PATH = os.path.join(tmp_dir, f"scratch_{n}.db")


def fixture_today(today=None):
    """
    The `today` the week render fixtures (lookahead_page.json, lookahead_page_fuel.json) are
    written for: today itself Monday to Friday, else the Friday of the same Monday-to-Sunday
    week. The commit week is the bucket containing today, so the pin never moves the week,
    its lines or its days; it only moves `today` back onto one of the five printed columns.

    Why (11 Oct 2026, a Sunday): the harnesses wrote the fixtures with the clock's date, and
    render_frontend.js asserts the populated "today" (the Commit view's "· today" header, the
    Dashboard's Today strip). On a Saturday or Sunday today is no printed column and has 0
    planned, so 2 checks failed on correct output. render_frontend.js now renders the weekend
    case on purpose, from the same fixture with `today` moved to the week's Sunday.
    """
    d = today or datetime.date.today()
    return d - datetime.timedelta(days=d.weekday() - 4) if d.weekday() > 4 else d


DEMO_AS_OF = datetime.date(2026, 11, 26)   # the shipped demo's as-of date (make_demo_tenant.SHIPPED_AS_OF, D96)


def pin_today(day=DEMO_AS_OF, extra=()):
    """
    17 Oct 2026 (demo redesign D104): make every `date.today()` (and `datetime.now()` / `.today()`) the backend reads
    return `day`, so a harness that reads the REAL commit week reads the same week whatever the calendar says. Without it
    http_smoke and test_h1_uk failed whenever the real week fell outside the demo's plan (4 Jan 2027 on the old demo) and
    pinned figures moved every week.

    Replaces, in every backend module already imported (call it after `import main`) and in the date-reading modules
    named here, and in sys.modules (so a function's own `import datetime` reads the pin too): an attribute holding the
    `datetime` MODULE with a copy whose `date` / `datetime` are subclasses with a
    pinned today() / now(); an attribute holding `datetime.date` or `datetime.datetime` itself (`from datetime import
    date`) likewise. isinstance() keeps accepting real dates and datetimes. utcnow() and time.time() are NOT pinned:
    stamps (created_at, an audit row) keep the real clock, and so does restrictions' "current" filter, which reads
    time.time() — a fixture closure must therefore span both the real and the pinned date. Returns the pinned date.
    """
    import importlib
    import sys
    import types
    real_date, real_dt = datetime.date, datetime.datetime

    class _DateMeta(type):
        def __instancecheck__(cls, obj):
            return isinstance(obj, real_date)

    class _DtMeta(type):
        def __instancecheck__(cls, obj):
            return isinstance(obj, real_dt)

    class PinnedDate(real_date, metaclass=_DateMeta):
        def __new__(cls, *a, **k):          # every date built through the pin is a REAL date (sqlite, json, arithmetic)
            return real_date(*a, **k)

        @classmethod
        def today(cls):
            return real_date(day.year, day.month, day.day)

    class PinnedDateTime(real_dt, metaclass=_DtMeta):
        def __new__(cls, *a, **k):
            return real_dt(*a, **k)

        @classmethod
        def now(cls, tz=None):
            t = real_dt.now(tz)
            return t.replace(year=day.year, month=day.month, day=day.day)

        @classmethod
        def today(cls):
            return cls.now()

    proxy = types.ModuleType("datetime")
    proxy.__dict__.update({k: v for k, v in vars(datetime).items() if not k.startswith("__")})
    proxy.date, proxy.datetime = PinnedDate, PinnedDateTime
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("weeks", "days", "lookahead", "network", "stockpiles", "fuel", "zones", "export", "route_sheet",
                 "route_map_export", "collisions", "community", "clp", "bulletin", "gate_arrivals", "clashes") + tuple(extra):
        try:
            importlib.import_module(name)
        except Exception:
            pass
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None) or ""
        if not f or os.path.dirname(os.path.abspath(f)) != backend:
            continue
        for k, v in list(vars(mod).items()):
            if v is datetime:
                setattr(mod, k, proxy)
            elif v is real_date:
                setattr(mod, k, PinnedDate)
            elif v is real_dt:
                setattr(mod, k, PinnedDateTime)
    sys.modules["datetime"] = proxy      # modules imported BEFORE this keep their own reference (the stdlib, the libraries)
    return real_date(day.year, day.month, day.day)

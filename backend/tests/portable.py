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
"""
import os
import shutil
import subprocess
import tempfile


def pdf_text(pdf_bytes, fallback=None):
    if not shutil.which("pdftotext"):
        return pdf_bytes.decode("latin-1") if fallback is None else fallback
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(pdf_bytes)
        out = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", "-eol", "unix", path, "-"],
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

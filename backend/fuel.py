"""
Fuel index, 2026-09-10 (evening) — a national diesel price per country, fetched
server-side from the country's public series, cached in ONE global row per country,
never invented. First built for Estonia; since G2 any EU-27 tenant country; since H1
(29 Sep 2026) Great Britain too, and a typed price for any other country.

THE PROVIDERS (H1, 29 Sep 2026) — one per country, behind one interface
------------------------------------------------------------------------
  eu_bulletin  EU-27: the EU Weekly Oil Bulletin via EuroOilWatch (below). EUR/L with taxes.
  desnz        GB: DESNZ "Weekly road fuel prices" (gov.uk, OGL, every Tuesday). The CSV's
               URL changes every week, so it is RESOLVED through the gov.uk content API
               (`/api/content/government/statistics/weekly-road-fuel-prices` →
               details.attachments[].url) and the LAST row of the CSV is read: the ULSD
               pump price in pence per litre, which INCLUDES duty and VAT. Stored as GBP/L
               (pence ÷ 100); the ex-VAT figure is DERIVED in state() from the VAT % the
               same row carries (20 % if the column is missing) and shown beside it.
               ⚠️ gov.uk is not reachable from the build sandbox: the fetch is exercised
               only against fixtures here. GET /api/admin/diagnostics/fuel-index?probe=1
               on the deployment shows what gov.uk actually returns.
  (none)       any other country, and a tenant with NO country: typed only. There is no
               fallback to another country's series — the pre-H1 fallback to Estonia is
               gone, and a tenant without a country keys its typed row under NO_COUNTRY.

The stored column is still called `eur_per_l` (the table predates GB): it holds the price
per litre in the PROVIDER'S currency — EUR for the bulletin, GBP for DESNZ — and the row
records which (`native_unit`). Nothing converts between currencies.

THE SOURCE (Grok's K6, verified from this sandbox on 10 Sep)
-----------------------------------------------------------
    GET https://eurooilwatch.com/api/v1/prices          (no key)
    { lastUpdated, bulletinDate: "2026-09-07",
      dataSource: "EC Weekly Oil Bulletin (2026-09-07)",
      countries: [ {countryCode: "EE", countryName: "Estonia",
                    petrolPrice: 1.812, dieselPrice: 1.922, ...}, ... ], euAverage }
`bulletinDate` and `dataSource` are TOP-LEVEL, not per country (the note implied per
country). The feed never says "with taxes" — €1.922 can only be the taxed figure (the
ex-tax diesel price is about €1.0), and the widget's attribution says which bulletin
series it is taken to be. That is an inference; if the Commission's figure and this one
ever differ, the Commission's XLSX wins and this row can be typed over (source 'manual').

THE RULES
---------
* The browser never calls the feed. This module does, with an 8 s timeout, and stores
  the last GOOD row. A failed fetch keeps the last good row and records when and why
  it failed (`last_error`), so the page can say "the feed could not be reached at …"
  instead of falling silent — the warning-stack lesson of 09 Sep.
* One row per country, no tenant column: a national index is not client data. It is
  registered as untenanted in test_tenant_audit.py with that reason.
* ⭐ NEVER ON A PAGE READ'S CRITICAL PATH. lookahead.page() reads the stored row only.
  GET /api/fuel-index returns the stored row at once and, if it is older than 12 h,
  starts ONE background refresh (the Tark Tee pattern); the widget polls `refresh`.
  `refresh(sync=True)` runs inline for tests and for the admin's explicit POST.
* Empty table + failed fetch ⇒ eur_per_l None and `stale` true — the widget prints
  "Index unavailable — type a price". Never a litre price this module made up.
* Stale = the last good BULLETIN is older than 8 days (the bulletin is weekly, Monday
  dated, published Thursday), or there is no row at all. Old-but-fresh is not stale:
  a 5-day-old bulletin fetched a minute ago is the current bulletin.
* A manual index (Config, admin) writes the same row with source 'manual' and is
  treated exactly as a bulletin row — including for locking the BAF base.

WHAT THIS DOES NOT DO
---------------------
No station prices (Alexela, Circle K, Fuelo), no OilPriceAPI, no scraping the
Commission's XLSX (its download ids rotate). No yard price here — that is a typed
tenant setting in costing.py, and the feed never overwrites it.
"""
import datetime
import json
import threading
import urllib.request

import db

FEED_URL = "https://eurooilwatch.com/api/v1/prices"
SOURCE_BULLETIN = "eu_oil_bulletin_diesel_with_tax"
SOURCE_DESNZ = "desnz_weekly_road_fuel_ulsd_pump"
SOURCE_MANUAL = "manual"
ATTRIBUTION = "EU Weekly Oil Bulletin via EuroOilWatch"          # the bulletin provider's
TIMEOUT_S = 8
REFRESH_AFTER_H = 12          # re-fetch when the last attempt is older than this
STALE_AFTER_DAYS = 8          # a bulletin older than this is flagged stale

#: The fuel_index key for a tenant with NO country. Typed only; nothing is ever fetched
#: for it, and no other country's row is ever read in its place (H1: the EE fallback is gone).
NO_COUNTRY = "--"

# The countries the EU Weekly Oil Bulletin publishes a diesel row for (EU-27). G2, 16 Sep.
BULLETIN_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
}

# DESNZ weekly road fuel prices — the gov.uk content API resolves this week's CSV.
DESNZ_CONTENT_API = "https://www.gov.uk/api/content/government/statistics/weekly-road-fuel-prices"
DESNZ_PAGE = "https://www.gov.uk/government/statistics/weekly-road-fuel-prices"
DESNZ_VAT_PCT_DEFAULT = 20.0      # UK standard rate; the CSV's own VAT column wins when present

PROVIDERS = {
    "eu_bulletin": {
        "key": "eu_bulletin", "countries": BULLETIN_COUNTRIES, "source": SOURCE_BULLETIN,
        "label": "EU Weekly Oil Bulletin via EuroOilWatch",
        "series": "automotive diesel, price with taxes", "unit": "EUR/L", "vat_pct": None,
        "page": "https://eurooilwatch.com",
    },
    "desnz": {
        "key": "desnz", "countries": {"GB"}, "source": SOURCE_DESNZ,
        "label": "DESNZ weekly road fuel prices (gov.uk)",
        "series": "ULSD pump price, pence/litre, incl. duty and VAT", "unit": "GBP/L",
        "vat_pct": DESNZ_VAT_PCT_DEFAULT, "page": DESNZ_PAGE,
    },
}


def norm_country(country):
    """The fuel_index key for a country: an upper-case ISO-2 code, else NO_COUNTRY."""
    c = str(country or "").strip().upper()
    return c if len(c) == 2 and c.isalpha() else NO_COUNTRY


def provider_for(country):
    """The provider block for a country, or None (typed only)."""
    c = norm_country(country)
    for p in PROVIDERS.values():
        if c in p["countries"]:
            return p
    return None


def auto_available(country):
    """Is there an automatic series for this country at all?"""
    return provider_for(country) is not None


def provider_public(country):
    """The provider as the API and the widget show it (no sets), or None."""
    p = provider_for(country)
    if not p:
        return None
    return {k: p[k] for k in ("key", "label", "series", "unit", "vat_pct", "page")}

_REFRESH = {"running": False, "started_at": None, "finished_at": None, "status": None, "error": None}
_REFRESH_LOCK = threading.Lock()


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _num(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
#  The feed                                                                    #
# --------------------------------------------------------------------------- #
def fetch_feed(timeout=TIMEOUT_S):
    """The raw JSON document from the feed. Raises on any failure; never retries."""
    req = urllib.request.Request(FEED_URL, headers={"Accept": "application/json",
                                                     "User-Agent": "Wayscope/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_feed(doc, country):
    """
    {eur_per_l, bulletin_date, raw_source_label} for one country, or an {"error"}.
    Strict on purpose: a missing price is an error, never a 0 or a guess.
    """
    if not isinstance(doc, dict):
        return {"error": "feed is not a JSON object"}
    rows = doc.get("countries")
    if not isinstance(rows, list):
        return {"error": "feed has no countries[]"}
    hit = None
    for r in rows:
        if isinstance(r, dict) and str(r.get("countryCode") or "").upper() == country.upper():
            hit = r
            break
    if hit is None:
        return {"error": f"feed has no row for {country}"}
    price = _num(hit.get("dieselPrice"))
    if price is None or price <= 0:
        return {"error": f"feed has no diesel price for {country}"}
    bdate = str(doc.get("bulletinDate") or hit.get("bulletinDate") or "")[:10]
    try:
        datetime.date.fromisoformat(bdate)
    except ValueError:
        return {"error": "feed has no bulletin date"}
    label = str(doc.get("dataSource") or "EC Weekly Oil Bulletin")[:120]
    return {"eur_per_l": round(price, 3), "bulletin_date": bdate, "raw_source_label": label}


# --------------------------------------------------------------------------- #
#  DESNZ weekly road fuel prices (GB) — H1, 29 Sep 2026                        #
# --------------------------------------------------------------------------- #
def _http_get(url, timeout, accept):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "Wayscope/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8-sig", errors="replace")


def resolve_desnz_csv(content_doc):
    """
    The URL (and title) of this week's CSV from the gov.uk content API document:
    details.attachments[] — the first CSV whose title mentions weekly road fuel prices,
    else the first CSV at all. Returns {"url", "title"} or {"error"}.
    """
    if not isinstance(content_doc, dict):
        return {"error": "content API did not return a JSON object"}
    atts = ((content_doc.get("details") or {}).get("attachments")) or []
    if not isinstance(atts, list) or not atts:
        return {"error": "content API document has no details.attachments[]"}
    csvs = []
    for a in atts:
        if not isinstance(a, dict):
            continue
        url = str(a.get("url") or "")
        ext = str(a.get("file_extension") or "").lower()
        ctype = str(a.get("content_type") or "").lower()
        if ext == "csv" or url.lower().endswith(".csv") or "csv" in ctype:
            csvs.append({"url": url, "title": str(a.get("title") or "")})
    if not csvs:
        return {"error": f"no CSV attachment among {len(atts)} attachments"}
    for c in csvs:
        t = c["title"].lower()
        if "weekly" in t and "fuel" in t:
            return c
    return csvs[0]


def _parse_uk_date(v):
    """DESNZ dates arrive as dd/mm/yyyy in the CSV; accept ISO and '29 September 2026' too."""
    v = str(v or "").strip().strip('"')
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def parse_desnz_csv(text):
    """
    {eur_per_l (GBP/L), bulletin_date, raw_source_label, native_price (p/L), vat_pct} from
    the weekly road fuel prices CSV, or an {"error"}. The columns are found by their
    HEADER TEXT (the exact wording has changed over the years): the date column, the
    ULSD pump price in pence/litre, and the VAT % column when present. The LAST row with
    a parseable date and price wins. Strict: no price → error, never 0 or a guess.
    """
    import csv
    import io
    if not text or not str(text).strip():
        return {"error": "empty CSV"}
    rows = list(csv.reader(io.StringIO(str(text))))
    hdr_i = None
    for i, r in enumerate(rows[:20]):
        low = [c.strip().lower() for c in r]
        if any(c.startswith("date") for c in low) and any("ulsd" in c for c in low):
            hdr_i = i
            break
    if hdr_i is None:
        return {"error": "no header row naming Date and ULSD in the first 20 lines"}
    hdr = [c.strip() for c in rows[hdr_i]]
    low = [c.lower() for c in hdr]
    date_i = next(i for i, c in enumerate(low) if c.startswith("date"))
    price_i = None
    for i, c in enumerate(low):
        if "ulsd" in c and ("pump" in c or "pence" in c) and "duty" not in c and "vat" not in c:
            price_i = i
            break
    if price_i is None:
        return {"error": "no ULSD pump price column", "header": hdr}
    vat_i = next((i for i, c in enumerate(low) if "vat" in c and "%" in c or c.startswith("vat")), None)
    best = None
    for r in rows[hdr_i + 1:]:
        if len(r) <= max(date_i, price_i):
            continue
        d = _parse_uk_date(r[date_i])
        p = _num(str(r[price_i]).replace(",", "").strip())
        if d is None or p is None or p <= 0:
            continue
        vat = _num(str(r[vat_i]).replace("%", "").strip()) if vat_i is not None and len(r) > vat_i else None
        best = (d, p, vat)
    if best is None:
        return {"error": "no row with a date and a ULSD pump price", "header": hdr}
    d, pence, vat = best
    vat = vat if vat is not None and 0 <= vat < 100 else DESNZ_VAT_PCT_DEFAULT
    return {"eur_per_l": round(pence / 100.0, 3), "bulletin_date": d.isoformat(),
            "native_price": round(pence, 2), "native_unit": "p/L", "vat_pct": vat,
            "raw_source_label": (f"DESNZ weekly road fuel prices — ULSD pump price {pence:.2f} p/L "
                                 f"incl. duty and VAT ({vat:g} %), w/e {d.isoformat()}")[:120]}


def fetch_desnz(timeout=TIMEOUT_S):
    """Resolve this week's CSV through the content API, then fetch it. Raises on failure.
    Returns {"csv", "csv_url", "csv_title"}."""
    doc = json.loads(_http_get(DESNZ_CONTENT_API, timeout, "application/json"))
    att = resolve_desnz_csv(doc)
    if att.get("error"):
        raise ValueError(att["error"])
    text = _http_get(att["url"], timeout, "text/csv,*/*")
    return {"csv": text, "csv_url": att["url"], "csv_title": att["title"]}


def fetch_and_parse(country, timeout=TIMEOUT_S):
    """One call for the refresh thread and the probe: the provider's fetch + parse.
    Returns the parsed dict (with an "error" key on a parse failure); raises on a fetch
    failure. `detail` carries what a probe wants to show."""
    p = provider_for(country)
    if not p:
        return {"error": f"no automatic diesel index for {norm_country(country)} — type the price"}
    if p["key"] == "desnz":
        got = fetch_desnz(timeout=timeout)
        out = parse_desnz_csv(got["csv"])
        out["detail"] = {"csv_url": got["csv_url"], "csv_title": got["csv_title"],
                         "csv_head": got["csv"][:400], "csv_tail": got["csv"][-300:]}
        return out
    doc = fetch_feed(timeout=timeout)
    out = parse_feed(doc, norm_country(country))
    out["detail"] = {"bulletin_date": (doc or {}).get("bulletinDate") if isinstance(doc, dict) else None,
                     "data_source": (doc or {}).get("dataSource") if isinstance(doc, dict) else None}
    return out


# --------------------------------------------------------------------------- #
#  The stored row                                                              #
# --------------------------------------------------------------------------- #
def get_index(country):
    """The stored row for a country (or NO_COUNTRY), or None. Always one query; never a fetch."""
    try:
        rows = db.query("SELECT * FROM fuel_index WHERE country = ?", (norm_country(country),))
    except Exception:
        return None
    return dict(rows[0]) if rows else None


def _upsert(country, source, eur_per_l, bulletin_date, label, fetched_at=None,
            attempt_at=None, error=None, provider=None, native_price=None, native_unit=None,
            vat_pct=None):
    """One row per country key. The H1 columns (provider, native_price, native_unit,
    vat_pct) are added by db.init_costing_db()'s guard; a row written before H1 has NULLs."""
    key = norm_country(country)
    cur = get_index(key)
    if cur:
        db.execute("UPDATE fuel_index SET source = ?, bulletin_date = ?, fetched_at = ?, "
                   "eur_per_l = ?, raw_source_label = ?, last_attempt_at = ?, last_error = ?, "
                   "provider = ?, native_price = ?, native_unit = ?, vat_pct = ? "
                   "WHERE country = ?",
                   (source, bulletin_date, fetched_at, eur_per_l, label, attempt_at, error,
                    provider, native_price, native_unit, vat_pct, key))
    else:
        db.execute("INSERT INTO fuel_index (country, source, bulletin_date, fetched_at, "
                   "eur_per_l, raw_source_label, last_attempt_at, last_error, "
                   "provider, native_price, native_unit, vat_pct) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (key, source, bulletin_date, fetched_at, eur_per_l, label,
                    attempt_at, error, provider, native_price, native_unit, vat_pct))


def _mark_failed(country, error):
    """Keep the last good row; record only that an attempt failed, and why."""
    cur = get_index(country)
    if cur:
        db.execute("UPDATE fuel_index SET last_attempt_at = ?, last_error = ? WHERE country = ?",
                   (_now(), error[:200], norm_country(country)))
    else:
        _upsert(country, None, None, None, None, fetched_at=None, attempt_at=_now(),
                error=error[:200])


def set_manual(eur_per_l, bulletin_date, by=None, country=None):
    """Type the index by hand (admin, Config). Same row, source 'manual'. A tenant with
    no country types under NO_COUNTRY — the only index such a tenant can ever have."""
    price = _num(eur_per_l)
    if price is None or price <= 0:
        return {"ok": False, "problems": ["eur_per_l must be a positive number"]}
    bdate = str(bulletin_date or "")[:10]
    try:
        datetime.date.fromisoformat(bdate)
    except ValueError:
        return {"ok": False, "problems": ["bulletin_date must be YYYY-MM-DD"]}
    p = provider_for(country)
    _upsert(country, SOURCE_MANUAL, round(price, 3), bdate, f"typed by {by or 'unknown'}",
            fetched_at=_now(), attempt_at=_now(), error=None,
            provider="manual", native_price=None, native_unit=(p["unit"] if p else None),
            vat_pct=None)
    return {"ok": True, "problems": [], "index": get_index(country)}


# --------------------------------------------------------------------------- #
#  Refresh                                                                     #
# --------------------------------------------------------------------------- #
def needs_refresh(row, now=None):
    """No successful fetch, or the last ATTEMPT older than REFRESH_AFTER_H hours."""
    if not row:
        return True
    last = row.get("last_attempt_at") or row.get("fetched_at")
    if not last:
        return True
    try:
        t = datetime.datetime.fromisoformat(str(last).replace("Z", ""))
    except ValueError:
        return True
    now = now or datetime.datetime.utcnow()
    return (now - t) > datetime.timedelta(hours=REFRESH_AFTER_H)


def is_stale(row, today=None):
    """No good row, or its bulletin older than STALE_AFTER_DAYS. The widget's chip."""
    if not row or _num(row.get("eur_per_l")) is None or not row.get("bulletin_date"):
        return True
    try:
        b = datetime.date.fromisoformat(str(row["bulletin_date"])[:10])
    except ValueError:
        return True
    today = today or datetime.date.today()
    return (today - b).days > STALE_AFTER_DAYS


def refresh_state():
    with _REFRESH_LOCK:
        return dict(_REFRESH)


def refresh(country, sync=False, timeout=TIMEOUT_S):
    """
    Fetch the country's provider and store the row. `sync=True` runs inline and returns
    the outcome; otherwise ONE background thread runs it and the current state is
    returned at once. On failure the last good row stands and `last_error` says why.
    """
    country = norm_country(country)
    if not auto_available(country):
        # no series to fetch: say so in the state, never mark a fetch as tried
        with _REFRESH_LOCK:
            _REFRESH.update({"running": False, "started_at": _now(), "finished_at": _now(),
                             "status": "manual_only",
                             "error": ("no country set — type the price" if country == NO_COUNTRY
                                       else f"no automatic diesel index for {country} — type the price")})
        return refresh_state()
    prov = provider_for(country)
    with _REFRESH_LOCK:
        if _REFRESH["running"]:
            return dict(_REFRESH)
        _REFRESH.update({"running": True, "started_at": _now(), "finished_at": None,
                         "status": None, "error": None})

    def run():
        try:
            try:
                p = fetch_and_parse(country, timeout=timeout)
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:120]}"
                _mark_failed(country, err)
                with _REFRESH_LOCK:
                    _REFRESH.update({"status": "unavailable", "error": err})
                return
            if p.get("error"):
                _mark_failed(country, p["error"])
                with _REFRESH_LOCK:
                    _REFRESH.update({"status": "unavailable", "error": p["error"]})
                return
            now = _now()
            _upsert(country, prov["source"], p["eur_per_l"], p["bulletin_date"],
                    p["raw_source_label"], fetched_at=now, attempt_at=now, error=None,
                    provider=prov["key"], native_price=p.get("native_price"),
                    native_unit=p.get("native_unit") or prov["unit"], vat_pct=p.get("vat_pct"))
            with _REFRESH_LOCK:
                _REFRESH.update({"status": "ok", "error": None})
        except Exception as e:                       # a DB fault must not kill the thread silently
            with _REFRESH_LOCK:
                _REFRESH.update({"status": "error", "error": str(e)[:200]})
        finally:
            with _REFRESH_LOCK:
                _REFRESH.update({"running": False, "finished_at": _now()})

    if sync:
        run()
    else:
        threading.Thread(target=run, name="fuel-index-refresh", daemon=True).start()
    return refresh_state()


def ensure_fresh(country, sync=False):
    """The lazy path GET /api/fuel-index takes: refresh only when the row is old."""
    country = norm_country(country)
    if not auto_available(country):
        return refresh_state()
    row = get_index(country)
    if needs_refresh(row):
        return refresh(country, sync=sync)
    return refresh_state()


def state(country, today=None):
    """What the widget reads: the row, its staleness, the provider, the refresh.
    `eur_per_l` is the price per litre in the provider's currency (see the module
    docstring); `ex_vat_per_l` is derived for a provider whose series includes VAT."""
    country = norm_country(country)
    row = get_index(country) or {}
    prov = provider_public(country)
    price = _num(row.get("eur_per_l"))
    vat = _num(row.get("vat_pct"))
    if vat is None and prov and prov.get("vat_pct") is not None and row.get("source") != SOURCE_MANUAL:
        vat = prov["vat_pct"]
    ex_vat = round(price / (1.0 + vat / 100.0), 3) if (price is not None and vat) else None
    return {
        "country": country,
        "no_country": country == NO_COUNTRY,
        "auto_available": prov is not None,
        "provider": prov,
        "eur_per_l": price,
        "unit": (row.get("native_unit") if row.get("native_unit") in ("EUR/L", "GBP/L")
                 else (prov["unit"] if prov else None)),
        "native_price": _num(row.get("native_price")),
        "native_unit": row.get("native_unit"),
        "vat_pct": vat,
        "ex_vat_per_l": ex_vat,
        "bulletin_date": row.get("bulletin_date"),
        "fetched_at": row.get("fetched_at"),
        "source": row.get("source"),
        "source_label": row.get("raw_source_label"),
        "attribution": (prov["label"] if prov else "typed — no automatic series for this country"),
        "stale": is_stale(row, today=today),
        "last_attempt_at": row.get("last_attempt_at"),
        "last_error": row.get("last_error"),
        "refresh": refresh_state(),
    }

# Modus

Haulage forecasting, a weekly look-ahead and a corridor route map for construction
programmes on linear infrastructure — rail, road and utility corridors.

Delivery teams forecast their material movements month by month; planners approve them;
Modus turns the approved plan into a day-by-day commitment sheet for hauliers, sized in
trucks rather than trips, with routed distances, cycle times, carbon and cost — and shows
the whole programme on one map.

```
https://<your-service>/          staff app (sign in with an access code)
https://<your-service>/map/      route map (staff sign-in, or the shared map password)
https://<your-service>/help/     user guide (staff sign-in)
https://<your-service>/api/...   the API both pages use
```

One service, one database, no build step: FastAPI + PostgreSQL on the server, React 18
(CDN, in-browser Babel) in `frontend/index.html`, Mapbox GL JS in `map/index.html`, HERE
Routing v8 for truck geometry. SQLite is used automatically when `DATABASE_URL` is unset.

---

## A fresh deployment boots EMPTY

Modus ships no customer data. A new deployment has the generic disciplines and the
default configuration — no locations, routes, teams, sections, forecasts or map
alignment. An organisation (a *tenant*) arrives as **one package file**:

| Step | How |
|---|---|
| Check the tenant is empty | `GET /api/admin/tenant/status?token=<ADMIN_TOKEN>` |
| Import a package | `POST /api/admin/tenant/import?token=<ADMIN_TOKEN>` with the package JSON as the body (`&replace=1` wipes the tenant first) |
| Export the tenant | `GET /api/admin/tenant/export?token=<ADMIN_TOKEN>` — every tenanted table, the configuration rows and any baked geometry |
| Load or replace the map overlay alone | `PUT /api/admin/overlay?token=<ADMIN_TOKEN>` — see `map/overlay.js` for the shape |
| Bake the network | Routes page → **Bake all** (HERE; imported routes read "not baked" until then) |

`backend/tenant_package.py` documents the format and the import rules (whole-tenant, no
merge; columns matched to the live schema; `tenant_id` never read from the file).

### The demo tenant

`demo/uk-corridor.package.json` is a **fictional** organisation — the Wolds Link, a
31.8 km corridor in the English East Midlands with three quarries, a railhead, four
compounds, three stockpiles, three teams, eight work sections, eighteen routes, four
months of approved forecasts (Sep–Dec 2026), two weeks of typed actuals, a confirmed
commit week, contract rates, a GBP diesel price and a map overlay. Every name, quantity
and rate is invented. Rebuild it with:

```
python3 backend/tools/make_demo_tenant.py
```

It boots the product against a scratch SQLite database, writes every row through the
same functions the app uses, and exports the result — so the demo also exercises the
package format end to end.

### Tenant settings

The factors document carries a `tenant` block, edited on Config → Everything (JSON):

| Key | Meaning |
|---|---|
| `name` | shown in the header, the page title and on every export |
| `team_label` | the word for a delivery team — "Team", "Package", "IPT", "Contractor" |
| `currency` | EUR, GBP, SEK, NOK, DKK, PLN, CHF or USD — the **symbol** only; no exchange rate is ever applied |
| `country` | ISO 3166 alpha-2. Decides which country services switch on (below) |

Team **ids** stay the internal slots `IPT1`…`IPT6` (the access-code variables are named
after them). Every place a person reads a team shows the tenant's own name for the slot.

Country-specific services:

| Service | Switched on for |
|---|---|
| Road restrictions (Tark Tee, Estonian Transport Administration) | `EE` |
| National orthophoto basemap (Maa-amet) and Estonian vehicle labels | `EE` |
| Automatic diesel price (EU Weekly Oil Bulletin) | EU-27 countries. Elsewhere an admin types the weekly price on Config |

---

## Deploy on Render

`render.yaml` is a Blueprint for a **new** web service (`modus-web`) and a **new**
database (`modus-db`). It does not touch any existing service or database.

1. Push this repository to a private GitHub repository.
2. Render → **New** → **Blueprint** → pick the repository → **Apply**.
3. In the service's **Environment**, set the secrets below (never in `render.yaml`).
4. Open the service, sign in with `PLANNER_CODE`, import a tenant package, bake.

Plans in `render.yaml` are `starter` (web) and `basic-256mb` (database). Change them to
what you intend to pay for **before** the first sync.

### Environment

| Variable | Needed | What it does |
|---|---|---|
| `DATABASE_URL` | set by the Blueprint | PostgreSQL. Unset locally → SQLite |
| `ADMIN_TOKEN` | **yes** | protects every `/api/admin/*` call. While unset, those calls are **open** |
| `PLANNER_CODE`, `ADMIN_CODE` | **yes** | staff access codes. With no code set nobody can sign in (fails closed) |
| `IPT1_CODE` … `IPT6_CODE` | per team | a team's access code — it sees only that team's lines |
| `MAP_PASSWORD` | for outside viewers | opens `/map/` without an account. Unset → the map is closed to outsiders |
| `GATE_SECRET` | optional | signs the gate cookie; unset → derived from `MAP_PASSWORD` + `ADMIN_TOKEN` |
| `HERE_API_KEY` | to bake routes | HERE Routing v8, called server-side only |
| `MAPBOX_TOKEN` | recommended | the Mapbox **public** token for the app and the PDF map (`map/config.js` carries the browser map's own copy) |
| `GOOGLE_MAPS_API_KEY`, `GOOGLE_MAPS_URL_SIGNING_SECRET` | optional | Street View in site popups |
| `TENANT_ID` | optional | the tenant this deployment serves (default `default`) |
| `ALLOW_DEMO_CODES` | **never on a deployment** | local checkouts only: honours three well-known demo codes when no real code is set |
| `MAP_GATE=off` | local only | opens `/map/` and `/help/` without a password |

`env.example` has the long form of each.

---

## Run it locally

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && ALLOW_DEMO_CODES=1 MAP_GATE=off uvicorn main:app --reload
```

Then open http://127.0.0.1:8000, sign in with `planner123`, and import the demo:

```
curl -X POST "http://127.0.0.1:8000/api/admin/tenant/import" \
     -H "Content-Type: application/json" --data-binary @demo/uk-corridor.package.json
```

(With `ADMIN_TOKEN` unset locally the admin calls need no token.)

---

## Tests

Every harness is a standalone script that prints `N passed, M failed`:

```
for f in backend/tests/test_*.py; do python3 "$f"; done
python3 backend/tests/http_smoke.py            # the real HTTP layer (needs the requirements)
NODE_PATH=$(npm root -g) node backend/tests/parse_map.js
NODE_PATH=$(npm root -g) node backend/tests/parse_frontend.js     # needs global typescript
NODE_PATH=$(npm root -g) node backend/tests/render_frontend.js    # needs global react, react-dom, typescript
NODE_PATH=$(npm root -g) node backend/tests/test_ipt_overlay.js
```

Most Python harnesses stub FastAPI and call the endpoint functions directly against a
scratch SQLite database; `http_smoke.py` boots the real app with FastAPI's TestClient and
skips itself when FastAPI is not installed. `.github/workflows/suite.yml` runs all of them
on every push. Not covered anywhere: PostgreSQL, live HERE / Mapbox / Google calls, and
rendering in a real browser beyond the tools below.

Guide images: `backend/tools/make_guide_images.js` draws the explanatory figures and the
screenshot placeholders; `backend/tools/capture_guide.js` replaces the placeholders with
real screens from a deployment that has the demo imported and baked.

---

## Security — read before showing anyone

Access is a **shared code per role**, checked by the server on every request, plus a
shared password for the map. There are no per-person accounts, no rate limit and no
audit trail of who changed what. Per-person logins are the next security phase. **Do not
describe a deployment as secure until they exist.**

Normal operation sends site and route coordinates to HERE and Mapbox (and to Google where
Street View is used). No quantity, rate or forecast leaves the platform.

## Third-party terms

HERE, Mapbox and Google are used under their own terms and plans. Check that the plan
you hold covers your use — in particular the HERE Base Plan's excluded use cases — and
restrict the Mapbox public token to your own domains in the Mapbox account.

## Layout

```
backend/            FastAPI app (main.py), one module per concern, factors.json (default configuration)
backend/tests/      the harnesses and their fixtures
backend/tools/      the demo generator and the guide-image tools
frontend/           the staff app (index.html) and the user guide (help/)
map/                the route map (index.html, overlay.js, config.js)
demo/               the fictional demo tenant package
render.yaml         the Render Blueprint
env.example         every environment variable, explained
```

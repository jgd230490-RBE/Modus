# Vendored third-party files

Served by the app at `/vendor/` (backend/main.py). Each one is here because its CDN cannot be pinned with an
integrity hash; every other outside script and stylesheet is an exact CDN version with `integrity` + `crossorigin`.

| File | Source | Version | sha384 | Licence |
|---|---|---|---|---|
| `tailwind-play-3.4.17.js` | https://cdn.tailwindcss.com/3.4.17 (what the unversioned URL served on 27 Oct 2026) | 3.4.17 | `igm5BeiBt36UU4gqwWS7imYmelpTsZlQ45FZf+XBn9MuJbn4nQr7yx1yFydocC/K` | MIT (Tailwind Labs) |

The file is byte-identical to the CDN's; `backend/tests/test_hardening.py` checks the hash. To move to a new version:
download it, rename it with the version, update the script tag in `frontend/index.html`, this table and the test.

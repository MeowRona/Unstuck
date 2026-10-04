# Unstuck — current status

Canonical repository: https://github.com/MeowRona/Unstuck

Last updated: 2026-10-04

## Working now

- Python standard-library web app; no runtime package installation required.
- Responsive English **City Compass** UI: compact plan summary, real OpenStreetMap pane on desktop, vertically stacked result cards, synchronized card/marker selection, explicit compromise badges, source/assumption disclosure, and mobile List/Map switching.
- Full plan editor preserves wheel pickers for time/minute fields. Save refreshes the existing session through `/api/update`; Cancel and Escape restore the previous brief instead of leaking unsaved wheel state.
- Default planning date/start time now comes from the user's browser-local clock (5-minute rounding); the judge demo keeps its fixed reproducible time.
- Start location now supports browser Current Location in addition to saved landmarks and exact Warsaw addresses; coordinates feed the same routing/feasibility path and remain limited to the Warsaw pilot bounds.
- Light/dark mode is implemented across City Compass and remembered locally in the browser.
- Scheduled Warsaw transit routing is active from the bundled 2026-10-04 GTFS-derived index (6,946 stops, 19,005 patterns, 324 routes), including departure/arrival times, lines, transfers, stop lists and map geometry; it is explicitly not realtime.
- Wheel pickers use native momentum scrolling with proximity snapping plus a short settle snap, instead of fighting every scroll tick.
- Five real restaurant records carry persistent Google Place IDs. Optional `/api/place-media` enrichment fetches rating/review count/photo attribution live only when `GOOGLE_PLACES_API_KEY` exists **and** `GOOGLE_PLACES_ENABLED=true`; the flag remains false during development to preserve judging quota. Google Maps content is not written to disk or presented as locally sourced data.
- Searchable Warsaw start-point catalog: 158 saved origins across all 18 districts, loaded from data instead of three hard-coded origins. Origins are geocoded once, validated for unique coordinates/Warsaw bounds, and require no runtime geocoding dependency. Matching ignores diacritics for easier international testing.
- Judge-facing copy explicitly frames Warsaw as the first pilot dataset and explains that no local Warsaw knowledge is required to assess cost/time/constraint correctness.
- Validated state separating locked constraints, allowed compromises, and taste preferences.
- Stateful deterministic agent policy with observable action log.
- Hard checks for budget, required meal, travel, minimum stay, return time, opening window, exclusions, and date exceptions.
- Cross-midnight timing and Warsaw CET/CEST handling without an external tzdata dependency.
- Non-dominated/Pareto filtering; max three result cards; no mixed money/minutes/affinity score.
- Unknown or estimated material facts cannot become a confirmed result.
- Warsaw catalog: 1,993 places total, including 1,982 restaurants. The recorded 2026-10-04 OSM snapshot returned 1,979 restaurant features; 1,977 are imported records and 2 duplicates are replaced by stronger curated records. Five restaurant records remain curated; uncurated price/hour facts stay provisional when unknown.
- Local start-location search includes 158 saved points, 6,049 Warsaw street names and 125,217 exact OpenStreetMap addresses; exact coordinates can come from the local address index, a rate-limited Nominatim fallback, or browser Current Location inside pilot bounds.
- Deterministic taste fixtures that are clearly identified as fixtures.
- Feasibility-only baseline provider for later Qloo comparison.
- Live Qloo adapter using `/search` plus same-pool `/v2/insights` place ranking.
- Qloo timeout/retry/429 handling, network-call budget, short-lived RAM-only cache, response size limit, and no secret logging.
- Local HTTP end-to-end flow tested through search, reject, and update.

## Validation status

| Area | Status | Evidence |
| --- | --- | --- |
| Python compile | PASS | `python -m compileall -q .` |
| Logic/unit suite | PASS | 40/40 tests: `python -m unittest discover -s tests -v` |
| HTTP end-to-end | PASS | automated `search -> reject -> update` test on the real catalog with fixture taste |
| Browser UI load | PASS | local page loaded successfully; City Compass rendered at 1600x1000 and 1280x800; true 390x844 emulation has no document overflow; editor wheel Save/Cancel/Escape flow verified |
| Live Qloo | BLOCKED_NO_API_KEY | `python live_smoke.py` exits blocked when `QLOO_API_KEY` is absent |
| Human blind comparison | NOT RUN | protocol documented in README; no fabricated result |
| Public deployment | TEMPORARY | Cloudflare Quick Tunnel is live while the local server/tunnel process runs; Render account is created but stable deployment is waiting only for email verification |
| Public open-source repository | PASS | https://github.com/MeowRona/Unstuck |
| Devpost submission | NOT DONE | submission is a later action after live validation/deployment |

## Current blockers to claiming hackathon readiness

1. Obtain/set the hackathon `QLOO_API_KEY` and run `python live_smoke.py`.
2. Inspect raw live Qloo results for entity resolution and same-pool ranking; fix any contract mismatch instead of adapting fixtures to hide it.
3. Run the documented live-Qloo vs no-taste comparison with real testers; record real results only.
4. Replace the temporary Quick Tunnel with a stable hosted deployment and test it from a clean browser/network.
5. Publish the repository with this license and README.
6. Re-check Qloo/Devpost rules and the exact deadline immediately before submission.

Until item 1 passes, the project is a working local MVP with a prepared Qloo integration, **not** a competition-ready live Qloo submission.

## Resume point

Project root: `D:\Unstuck`

Local start:

```powershell
cd D:\Unstuck
python app.py
```

Live integration gate:

```powershell
$env:QLOO_API_KEY="..."
python live_smoke.py
```

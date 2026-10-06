# Unstuck — current status

Canonical repository: https://github.com/MeowRona/Unstuck

Last updated: 2026-10-06

## Working now

- Python standard-library web app; no runtime package installation required.
- Two product modes now share City Compass: **Rescue a plan** and **Plan a day**.
- Plan a day adds a month calendar, Today/Tomorrow/This weekend shortcuts, per-date Explore, up to three day variants, 1–4 stop control, fixed-event arrival buffer, numbered map stops, point-to-point travel timeline, local saved plans, Repair this day and plan/activity `.ics` export.
- Planner data is a deliberately limited verified Warsaw snapshot checked 2026-10-06: selected Warsaw Tourism Office event occurrences plus official schedules for POLIN, Copernicus Science Centre, Museum of Modern Art and Museum of Warsaw, combined with the existing restaurant catalog. Coverage is disclosed and is not described as all Warsaw events.
- Planner venue / attraction / event-occurrence objects are distinct. Separate days in a series remain separate occurrences; events with no captured session time remain discoverable but unschedulable; unknown prices/availability/event ends are not filled in.
- Planner feasibility checks opening windows, last entry, explicit 0/10/15/30-minute fixed-event buffer, sequential travel, fixed event times, budget uncertainty and optional return. The selected plan is then route-checked segment-by-segment at the actual previous-stop departure time.
- Saved planner state uses versioned browser localStorage (`unstuck-planner-saved-v1`) with no account sync. The last selected planner date also survives refresh. Copying settings to another date drops fixed event occurrences and re-runs feasibility.
- Planner Taste matching is explicitly **not live yet**: taste references are stored but do not affect planner ordering until a live Qloo planner contract is validated. Google Places remains disabled.
- Responsive English **City Compass** UI: compact plan summary, real OpenStreetMap pane on desktop, vertically stacked result cards, synchronized card/marker selection, explicit kept/changed/check condition states, source/assumption disclosure, and mobile List/Map switching.
- Full plan editor preserves wheel pickers for time/minute fields. Save refreshes the existing session through `/api/update`; Cancel and Escape restore the previous brief instead of leaking unsaved wheel state.
- Default planning date/start time now comes from the user's browser-local clock (5-minute rounding); the judge demo keeps its fixed reproducible time.
- Start location now supports browser Current Location in addition to saved landmarks and exact Warsaw addresses; coordinates feed the same routing/feasibility path and remain limited to the Warsaw pilot bounds.
- Light/dark mode is implemented across City Compass and remembered locally in the browser.
- Scheduled Warsaw transit routing is active from the bundled 2026-10-04 GTFS-derived index (6,946 stops, 19,005 patterns, 324 routes), including departure/arrival times, lines, transfers, stop lists and map geometry; it is explicitly not realtime. Selected cards now check both outbound and return routes and feed those checked durations back into feasibility/ranking.
- Wheel pickers use native momentum scrolling with proximity snapping plus a short settle snap, instead of fighting every scroll tick.
- Five real restaurant records carry persistent Google Place IDs. Optional `/api/place-media` enrichment fetches rating/review count/photo attribution live only when `GOOGLE_PLACES_API_KEY` exists **and** `GOOGLE_PLACES_ENABLED=true`; the flag remains false during development to preserve judging quota. Google Maps content is not written to disk or presented as locally sourced data.
- Searchable Warsaw start-point catalog: 158 saved origins across all 18 districts, loaded from data instead of three hard-coded origins. Origins are geocoded once, validated for unique coordinates/Warsaw bounds, and require no runtime geocoding dependency. Matching ignores diacritics for easier international testing.
- Judge-facing copy explicitly frames Warsaw as the first pilot dataset and explains that no local Warsaw knowledge is required to assess cost/time/constraint correctness.
- Validated state separating locked constraints, allowed compromises, and taste preferences.
- Stateful deterministic agent policy with observable action log, rejection reasons (Too far / Not my vibe / Been there / skip), session undo, and no silent global-constraint changes.
- Hard checks for budget, required meal, travel, minimum stay, return time, opening window, exclusions, and date exceptions.
- Cross-midnight timing and Warsaw CET/CEST handling without an external tzdata dependency.
- Non-dominated/Pareto filtering; max three result cards; no mixed money/minutes/affinity score.
- Unknown or estimated material facts cannot become a confirmed result. Cards distinguish confirmed kept conditions, explicit compromises, and conditions that still need verification.
- Warsaw catalog: 1,993 places total, including 1,982 restaurants. The recorded 2026-10-04 OSM snapshot returned 1,979 restaurant features; 1,977 are imported records and 2 duplicates are replaced by stronger curated records. Five restaurant records remain curated; uncurated price/hour facts stay provisional when unknown.
- Local start-location search includes 158 saved points, 6,049 Warsaw street names and 125,217 exact OpenStreetMap addresses; exact coordinates can come from the local address index, a rate-limited Nominatim fallback, or browser Current Location inside pilot bounds.
- Deterministic taste fixtures that are clearly identified as a preview with Qloo pending; the jury-facing evidence panel never presents them as a live Qloo result.
- Feasibility-only baseline provider for later Qloo comparison.
- Live Qloo adapter using `/search` plus same-pool `/v2/insights` place ranking, with an evidence contract for recognized signals, optional unavailable-venue taste anchor, no-taste baseline order, and actual live ordering impact once a key is connected.
- Qloo timeout/retry/429 handling, network-call budget, short-lived RAM-only cache, response size limit, and no secret logging.
- Local HTTP end-to-end flow tested through search, round-trip route check, reject reason, undo, and update. The fixed **Try a rescue · 60 sec** scenario is also covered by engine, API and cloud browser smoke tests.

## Validation status

| Area | Status | Evidence |
| --- | --- | --- |
| Python compile | PASS | `python -m compileall -q .` |
| Logic/unit suite | PASS | 74/74 tests in GitHub Actions: `python -m unittest discover -s tests -q` |
| HTTP end-to-end | PASS | rescue `search -> route-check -> reject(reason) -> undo -> update` plus planner `catalog -> generate -> route-check -> repair -> ICS` coverage |
| Browser UI load | PASS | GitHub Actions headless Chrome verifies Rescue plus Plan a day demo, local save/refresh/load, repair with locked event preserved, and both rescue/planner mobile navigation at 390x844 |
| Live Qloo | BLOCKED_NO_API_KEY | `python live_smoke.py` exits blocked when `QLOO_API_KEY` is absent |
| Human blind comparison | NOT RUN | protocol documented in README; no fabricated result |
| Public deployment | PENDING THIS DEPLOY | Existing Render service is live at https://unstuck-city-compass.onrender.com; this branch will be merged only after CI passes, then the workflow waits for the exact commit and runs `tools/production_smoke.py` against the public service |
| Public open-source repository | PASS | https://github.com/MeowRona/Unstuck |
| Devpost submission | NOT DONE | submission is a later action after live validation/deployment |

## Current blockers to claiming hackathon readiness

1. Obtain/set the hackathon `QLOO_API_KEY` and run `python live_smoke.py`.
2. Inspect raw live Qloo results for entity resolution and same-pool ranking; fix any contract mismatch instead of adapting fixtures to hide it.
3. Validate the planner-specific Qloo taste contract before allowing taste references to affect attraction/event ordering; until then the planner remains feasibility + explicit-interest based.
4. Run the documented live-Qloo vs no-taste comparison with real testers; record real results only.
5. Refresh/extend the selected event snapshot near judging if broader future-date coverage is needed; never imply complete Warsaw coverage.
6. Re-test the stable Render deployment after switching from fixture taste to live Qloo near submission.
7. Re-check Qloo/Devpost rules and the exact deadline immediately before submission.

Until item 1 passes, the project is a working local MVP with a prepared Qloo integration, **not** a competition-ready live Qloo submission.

## Resume point

Canonical work path is cloud-first:

1. edit/test on a GitHub branch;
2. open/update a PR so GitHub Actions runs compile, JavaScript syntax checks, 74 unit/HTTP tests and browser smoke;
3. merge only after green checks;
4. the main-branch workflow triggers the existing Render deploy hook, waits for the exact commit via `/api/version`, then runs `tools/production_smoke.py` against the public service.

Live Qloo remains gated by `QLOO_API_KEY` and `live_smoke.py`.

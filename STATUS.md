# Unstuck — current status

Canonical repository: https://github.com/MeowRona/Unstuck

Last updated: 2026-10-14

## Working now

- Python standard-library web app; no runtime package installation required.
- Two product modes now share City Compass: **Rescue a plan** and **Plan a day**.
- Plan a day adds a month calendar, Today/Tomorrow/This weekend shortcuts, per-date Explore, up to three day variants, 1–4 stop control, fixed-event arrival buffer, numbered map stops, point-to-point travel timeline, local saved plans, Repair this day and plan/activity `.ics` export.
- The Warsaw attraction/event snapshot was initially checked 2026-10-06; selected future event occurrences were manually refreshed 2026-10-15 through **28 November 2026** using official Go2Warsaw and Polish National Opera schedules. This is NOT a live event feed, and unknown tickets/end times stay unknown. The restaurant overlay has 30 operator-confirmed weekly-hour schedules and 2 provisional schedules with conflicting official evidence. Six restaurant branches include source-specific named-dish quotes, never whole-meal guarantees.
- Planner venue / attraction / event-occurrence objects are distinct. Separate days in a series remain separate occurrences; events with no captured session time remain discoverable but unschedulable; unknown prices/availability/event ends are not filled in.
- Planner feasibility checks opening windows, last entry, explicit 0/10/15/30-minute fixed-event buffer, sequential travel, fixed event times, budget uncertainty and optional return. The selected plan is then route-checked segment-by-segment at the actual previous-stop departure time.
- Saved planner state uses versioned browser localStorage (`unstuck-planner-saved-v1`) with no account sync. The last selected planner date also survives refresh. Copying settings to another date drops fixed event occurrences and re-runs feasibility.
- In live mode, Qloo can rank eligible **restaurant** choices in Plan a day when at least two Qloo-ranked venues are available. Museum/concert matching remains explicit-interest based. All reduced-coverage cases are labeled. Google Places remains disabled.
- Responsive English **City Compass** UI: compact plan summary, real OpenStreetMap pane on desktop, vertically stacked result cards, synchronized card/marker selection, explicit kept/changed/check condition states, source/assumption disclosure, and mobile List/Map switching.
- Full plan editor preserves wheel pickers for time/minute fields. Save refreshes the existing session through `/api/update`; Cancel and Escape restore the previous brief instead of leaking unsaved wheel state.
- Default planning date/start time now comes from the user's browser-local clock (5-minute rounding); the judge demo keeps its fixed reproducible time.
- Start location now supports browser Current Location in addition to saved landmarks and exact Warsaw addresses; coordinates feed the same routing/feasibility path and remain limited to the Warsaw pilot bounds.
- Plan a day now has **Already out?** replanning: completed stops are immutable history, the remaining day starts from the user's current time and last completed venue or Current Location, budget is explicitly scoped to the remaining plan, and an optional newly failed future stop can be replaced without rewriting completed history.
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
- Deterministic taste fixtures remain only for offline tests and clearly labeled preview mode. **Hosted production uses live Qloo**, and the jury-facing evidence panel records the actual per-request ranking coverage or explicit missing-coverage status.
- Feasibility-only baseline provider, actual same-generated-plan-pool Qloo-vs-operational comparisons, and a blinded test instrument. A measured ranking difference is NOT evidence of user preference.
- Live Qloo adapter using `/search` plus same-pool `/v2/insights` place ranking, optional explicit movie/artist/book/show entity picker, evidence on recognized signals, and actual live-vs-operational ranking impact. A production run confirmed a changed top plan; observed ranking coverage was 2 out of 10 restaurants for one smoke scenario.
- Qloo timeout/retry/429 handling, network-call budget, short-lived RAM-only cache, response size limit, and no secret logging.
- Local HTTP end-to-end flow tested through search, round-trip route check, reject reason, undo, and update. The fixed **Try a rescue · 60 sec** scenario is also covered by engine, API and cloud browser smoke tests.

## Validation status

| Area | Status | Evidence |
| --- | --- | --- |
| Python compile | PASS | `python -m compileall -q .` |
| Logic/unit suite | PASS | Current unit suite plus desktop and mobile browser checks run through [GitHub Actions](https://github.com/MeowRona/Unstuck/actions?query=branch%3Amain); do not freeze the outdated 74-test count |
| HTTP end-to-end | PASS | rescue `search -> route-check -> reject(reason) -> undo -> update` plus planner `catalog -> generate -> route-check -> repair -> ICS` coverage |
| Browser UI load | PASS | GitHub Actions headless Chrome verifies Rescue plus Plan a day demo, local save/refresh/load, Already-out completed-history replanning, repair with locked event preserved, and both rescue/planner mobile navigation at 390x844 |
| Live Qloo | PASS in Rescue + limited Plan a Day | Production smoke confirms 5/10 resolved + ranked planner restaurants, exact named venue matches, an actual same-pool top-plan change, and a bounded **Good for both** probe with 4 common ranked venues (A=4, B=4); [evidence run #242](https://github.com/MeowRona/Unstuck/actions/runs/38598353686) |
| Human blind comparison | NOT RUN | Anonymous blind-comparison instrument and protocol exist; **no volunteer responses collected** and no improvement claim |
| Public deployment | PASS for previously merged commits | [Render public app](https://unstuck-city-compass.onrender.com/) is independent of the development PC. Each new main commit waits for an exact-sha Render deployment and runs `tools/production_smoke.py`; check the [most recent main run](https://github.com/MeowRona/Unstuck/actions?query=branch%3Amain) before claiming new code has been deployed |
| Public open-source repository | PASS | https://github.com/MeowRona/Unstuck |
| Devpost submission | NOT DONE | submission is a later action after live validation/deployment |

## Current blockers to claiming hackathon readiness

1. Reconfirm every final production deploy and run mobile/desktop browser smoke near submission. Live Qloo was connected on 2026-10-13.
2. Continue improving Qloo venue coverage beyond the measured 5/10 ranked local restaurants without increasing per-plan request cost or mismatching similarly named branches. Four identities came from the bounded coverage probe and a fifth was confirmed by the production smoke; the earlier geo-scoped experiment remains rolled back.
3. The Qloo planner still ranks **restaurant choices only**. Music/attraction interests are matched with explicit tags/constraints; do not claim Qloo scored concerts or museums.
4. Recruit 6–10 voluntary testers and run the existing blinded Qloo-vs-operational preference study; results do not exist yet.
5. Event coverage now reaches **28 November 2026** with selected official sessions. Refresh again near judging only if judging extends materially beyond that date; never imply complete Warsaw coverage.
6. Confirm stable Render deployment and sufficient Qloo request budget for real jurors before final release.
7. Official Qloo/Devpost rules were re-checked on 2026-10-14: submission deadline is **30 October 2026, 23:45 EDT**; a functional external demo, public source repository, English text description and visible open-source license are required; a demo video is **not required**. Re-check once more immediately before the actual submission in case the published rules change.

Live Rescue and limited Plan a Day Qloo have been verified. The two-stage simulated dinner failure and bounded route repair are implemented, but real venue availability, partial 5/10 Qloo coverage in the latest bounded planner sample, and the missing human preference results remain limitations. **No claim of fully validated competition readiness is made.**

## Resume point

Canonical work path is cloud-first:

1. edit/test on a GitHub branch;
2. open/update a PR so GitHub Actions runs compile, JavaScript syntax checks, 74 unit/HTTP tests and browser smoke;
3. merge only after green checks;
4. the main-branch workflow triggers the existing Render deploy hook, waits for the exact commit via `/api/version`, then runs `tools/production_smoke.py` against the public service.

Live Qloo remains gated by `QLOO_API_KEY` and `live_smoke.py`.

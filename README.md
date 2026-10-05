# Unstuck

**Find the smallest change that saves your plan.**

Repository: https://github.com/MeowRona/Unstuck

Unstuck is a compact agentic web application for the Qloo Agentic Hackathon 2026. It is built for the moment when an outing plan stops working: the original venue is closed, too expensive, too far away, or no longer fits the available time. Instead of restarting discovery from scratch, Unstuck looks for a feasible substitute while preserving as much of the original intent as possible.

The current MVP is deliberately narrow in data scope: **one outing in Warsaw**, one shared brief, an auditable pilot catalog, and at most three non-dominated alternatives. Warsaw is the first test city, not the product thesis. The failure mode — a plan becomes infeasible and the user needs the smallest acceptable change — is city-independent.

## Why a one-city pilot

The hackathon judges do not need prior knowledge of Warsaw to evaluate the product. Unstuck converts local facts into explicit, portable dimensions: total cost, travel minutes, opening windows, return time, required activity, and taste fit. A judge can therefore evaluate whether a proposed rescue is valid without knowing which neighbourhood is fashionable or how far two Warsaw districts "feel" from each other.

Keeping one city in the first validated dataset is intentional: it lets the project prove constraint correctness and Qloo's role with facts that can be audited instead of pretending to have reliable operational coverage everywhere. The architecture treats origin points and place facts as data, so broader city coverage is an expansion of the catalog/provider layer rather than a different product concept.

## What is different

Unstuck does not collapse money, minutes, and taste into one opaque score. It keeps three kinds of input separate:

- **Locked constraints** — the engine cannot violate them without an explicit user change. Examples: total budget, return time, required meal.
- **Negotiable constraints** — the user may allow a precise amount of extra travel, a shorter stay, or a category change.
- **Preferences** — taste signals help rank options that survive feasibility checks.

Taste references are **taste anchors, not activity keywords**. They do not need to be literally related to the plan: a musician, film, book, or creator can express an aesthetic preference that Qloo can use as a cross-domain signal when ranking otherwise feasible places.

The search policy is deterministic and stateful. It is an agentic tool policy, not a simulated chain-of-thought UI: it observes the result of each feasibility pass, chooses whether the next explicitly allowed strategy is necessary, logs the action, remembers rejections and updates, and stops when a useful non-dominated set is found or the allowed search space is exhausted.

## Current flow

`brief -> validated state -> taste ranking -> strict feasibility -> allowed relaxation(s) -> Pareto filtering -> max 3 cards -> reject/change -> re-run`

The current interface is the **City Compass** layout: a light plan-summary shell with a real OpenStreetMap view on desktop, up to three vertically stacked recommendation cards, synchronized card/marker selection, explicit compromise badges, source/assumption disclosure, and a full plan editor with wheel pickers for time and minute-based constraints. On mobile the same flow switches to a **List / Map** toggle instead of squeezing both panes side by side. Venue photography is never invented: when a verified image is not available, the UI shows a neutral labeled fallback.

The search starts with a conservative city travel estimate, then the selected card is checked with a **real outbound and return route**: pedestrian street geometry from Valhalla/OpenStreetMap or scheduled Warsaw public-transport geometry from the bundled GTFS-derived index. The checked route is written back into the session and the engine re-evaluates travel allowance, return-by time, compromises and ranking. A card can therefore move, gain an extra-travel compromise, or disappear after the route check. Transit is scheduled, not realtime, and the interface shows the route source/check timestamp instead of continuing to describe a checked route as a straight-line estimate. OpenStreetMap attribution remains visible in the map/footer. Leaflet 1.9.4 is vendored under `static/vendor/leaflet/`; its license is included alongside the files. No JavaScript package manager or runtime dependency is required.

The default brief uses the **browser's local date and local clock**. Start time is rounded up to the next 5-minute step, and the initial return-by time is three hours later. The **Try a rescue · 60 sec** walkthrough is intentionally a fixed reproducible scenario dated **2026-10-09** against the bundled Warsaw data snapshot. It assumes HOŻA Steakhouse is unavailable **for the scenario only**; that is not a claim that the venue is actually closed. The scenario is constructed so the original 120-minute stay does not fit the locked evening window, while an explicitly allowed 30-minute stay reduction can rescue it. The engine still chooses the venue; no winning result card is hard-coded.

Start location supports saved Warsaw landmarks, local street autocomplete + exact-address resolution, and **Current location** through the browser Geolocation API. The local data bundle contains **6,049 Warsaw street names and 125,217 exact OpenStreetMap addresses**, so ordinary exact-address resolution usually requires no network call. Nominatim is a rate-limited fallback only for missing addresses and is never used as per-keystroke autocomplete. Browser geolocation permission is required for Current Location; coordinates are used for the active plan/routing and are not written into the project dataset. Current-location searches are intentionally restricted to the Warsaw pilot bounds.

Public-transport directions use the bundled Warsaw scheduled GTFS index (6,946 stops / 19,005 patterns / 324 routes in the current 2026-10-04 build). The UI shows departure/arrival times, line numbers, transfers, stop lists and route geometry. These are **scheduled, not realtime** departures. Walking and access/egress legs use street routing where available; same-interchange transfers are labeled as transfers rather than fake zero-distance walks.

The interface also includes a persistent **light/dark theme toggle**. The preference is stored only in browser `localStorage`; without a saved preference Unstuck follows the device color-scheme preference.

Restaurant cards can optionally enrich their existing thumbnail with a **live Google Places photo and Google Maps rating**. Only stable Google Place IDs are stored in the catalog. The actual rating, review count, photo URI and required author attribution are requested at runtime from Places API only when **both** `GOOGLE_PLACES_API_KEY` is present **and** `GOOGLE_PLACES_ENABLED=true`. Unstuck does not persist or rehost Google Maps content. The feature flag is intentionally `false` during development so free quota is preserved for the judging window; without it, the app keeps the neutral fallback and a direct Google Maps listing link.

Each result card separates condition status into three states:

- **Kept** — supported by the currently used data;
- **Changed** — an explicit allowed compromise, with every actual delta shown;
- **Check** — no violation is known, but the available fact/route is not strong enough to guarantee the condition.

The final plan repeats those conditions, shows the evening timeline, lists facts to verify, opens the route, and can copy a short plan to the clipboard. It never sends a message or makes a reservation.

Unknown data never becomes a confirmed PASS. A result with unknown price/hours or an unchecked route can remain useful, but it stays visibly incomplete.

## Data modes

The same business logic is used in all modes.

| Mode | Operational place facts | Taste signal | Intended use |
| --- | --- | --- | --- |
| `fixture` + `real` catalog | 1,993 Warsaw places (1,982 restaurants; curated + complete recorded OSM restaurant layer) | deterministic authored taste fixtures | default local development before a Qloo key is available |
| `baseline` + `real` catalog | same real Warsaw catalog | none | controlled no-Qloo comparison |
| `live` + `real` catalog | same real Warsaw catalog | live Qloo | final integration / judging |
| `fixture` + `fixture` catalog | synthetic places | deterministic fixtures | fully deterministic engine tests |

Fixture taste data is always labeled as a **taste preview / Qloo pending** state and is never presented as a Qloo response. The result payload also includes a `taste_audit` evidence contract for the jury-facing explanation. In live mode it records the actually resolved Qloo signals and compares the Qloo ordering with a no-taste ordering of the **same candidate pool**; in fixture mode it explicitly marks that comparison as unavailable as Qloo evidence.

## Qloo's role

The live adapter follows the current Qloo hackathon API pattern:

1. apply operational feasibility/geography prefiltering before Qloo;
2. resolve named interests and candidate places through `GET /search`;
3. optionally resolve the original unavailable venue as an additional taste anchor while still excluding it from recommendations;
4. evaluate the **same candidate place pool** through one `GET /v2/insights` ranking call;
5. pass the resolved taste references/anchor in `signal.interests.entities`;
6. restrict the comparison with `filter.results.entities` and `filter.type=urn:entity:place`;
7. preserve the no-taste order of that same pool so the UI can truthfully answer “What did Qloo change?”;
8. treat affinity as a relative recommendation signal, not a probability of satisfaction.

The server sends the key only in the `X-Api-Key` header. The browser never receives it. The transport has timeouts, bounded retry for 429/temporary server failures, a per-process network-call budget, and a small **process-memory-only** short-lived cache. Qloo output is not persisted to disk or bulk-downloaded.

Official references:

- https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide
- https://docs.qloo.com/reference/parameters
- https://docs.qloo.com/reference/search
- https://www.qloo.com/legal/terms

The public Qloo terms can be supplemented by account-specific API terms. Before final deployment, review any additional terms supplied with the hackathon key.

## Place facts and scope

`data/places_warsaw.json` is the operational catalog/source-of-truth for this MVP. It currently contains **1,993 Warsaw places**, including **1,982 restaurants**. The restaurant layer is built from the recorded OpenStreetMap Overpass snapshot dated **2026-10-04**: 1,979 `amenity=restaurant` features were returned, 1,977 are represented as imported OSM records, and 2 duplicate OSM entries are replaced by stronger curated records; 5 curated restaurant records are retained in total. Uncurated price/hour facts remain provisional when the source is not strong enough for a hard guarantee. `data/origins_warsaw.json` contains **158 recognizable starting points across all 18 Warsaw districts**, while `data/streets_warsaw.json` contains a local searchable index of **6,049 street names**. This keeps autocomplete local and avoids using public Nominatim as a forbidden per-keystroke autocomplete service.

Each material field carries a status and provenance where available:

- `confirmed` — checked against the listed source on 2026-10-04;
- `estimated` — usable only with a visible warning;
- `unknown` — never sufficient to confirm a locked constraint.

Saved-origin coordinates were geocoded from the listed addresses with OpenStreetMap Nominatim on 2026-10-04. Search feasibility still starts from a conservative city estimate. The selected option is then validated with **outbound and return** walking/scheduled-transit routes, and those checked durations are fed back into the engine before the plan is treated as route-confirmed. Transit remains **scheduled, not realtime**, and provisional OSM discovery restaurants are never promoted to confirmed hard-budget/hours fits without stronger facts.

The compressed exact-address bundle is reproducible with `python tools/build_warsaw_address_index.py`. The builder can fetch Warsaw address objects from OpenStreetMap Overpass directly, or rebuild deterministically from a saved raw Overpass JSON via `--input`. The restaurant discovery layer is likewise reproducible with `python tools/build_warsaw_restaurants.py`; curated venue records take precedence over duplicate OSM features, and missing prices/hours remain explicitly unknown or estimated.

## Run locally on Windows

Requirements: Python 3.12+; no pip packages are required for the current MVP.

Optional environment variables:

- `QLOO_API_KEY` — enables the live Qloo taste adapter.
- `GOOGLE_PLACES_API_KEY` — stores the server-side Google Places credential.
- `GOOGLE_PLACES_ENABLED=true` — separately enables live Google Places calls. Keep this `false` during development to preserve the free quota for judging.

```powershell
cd D:\Unstuck
python app.py
```

Open:

```text
http://127.0.0.1:8817
```

Equivalent convenience command:

```powershell
.\start.ps1
```

The default mode uses the real Warsaw catalog and clearly labeled fixture taste data.

For a feasibility-only baseline:

```powershell
python app.py --mode baseline --catalog real
```

For fully synthetic deterministic demo data:

```powershell
python app.py --mode fixture --catalog fixture
```

## Activate live Qloo

Set the secret only in the server environment:

```powershell
$env:QLOO_API_KEY="your-key-here"
python live_smoke.py
```

`live_smoke.py` is the single live-integration gate. Without a key it returns `BLOCKED_NO_API_KEY`; it does not pretend that fixture tests validate Qloo.

If the smoke test passes, run:

```powershell
python app.py --mode live --catalog real
```

## Tests

Run the complete local suite:

```powershell
python -m unittest discover -s tests -v
```

The tests cover hard constraints, per-person vs total cost, outbound/stay/return timing, required meals, unknown facts, exclusions, cross-midnight hours, date-specific closures, one- and two-compromise searches, Pareto dominance, state updates, rejection persistence, Qloo same-pool request construction, API call budget/cache behavior, missing-key status, and an HTTP end-to-end `search -> reject -> update` flow.

See `STATUS.md` for the exact latest results.

## Qloo advantage validation protocol

The product claim is narrower than "Qloo makes recommendations better." The claim to test is: **Qloo helps choose a more acceptable substitute among options that already satisfy the same operational constraints.**

When the live key is available, compare:

1. `--mode live --catalog real`;
2. `--mode baseline --catalog real`.

Use the same briefs, candidate catalog, price/hour facts, travel estimator, locked constraints, and relaxation rules. Randomize which result set a tester sees first and do not label the provider during preference selection. Record:

- constraint correctness;
- time from brief to accepted choice;
- whether the tester accepts any option;
- blind preference between the two result sets;
- reasons for rejection.

Do not use a rise in Qloo affinity as evidence of product quality. If a free LLM-only baseline is available later, it can be added as a third arm without changing the operational facts. **No human results are currently claimed.**

## Reproducible demo

The UI includes **Try a rescue · 60 sec** for an evaluator who has never visited Warsaw and does not want to grant geolocation access or fill a long form.

The fixed scenario is dated **2026-10-09** and explicitly labels itself as a scenario using the bundled Warsaw data. It assumes the originally planned HOŻA Steakhouse is unavailable for the walkthrough only. The brief keeps the dinner goal, budget, travel limit and return-by time, requests a 120-minute stay, and permits a maximum 30-minute stay reduction. The strict plan cannot fit the available time, so the engine must use the explicit shorter-stay allowance or return no rescue.

The evaluator can then:

1. inspect which conditions are confirmed, changed or still need checking;
2. let the selected option run through outbound + return route validation;
3. reject it as **Too far / Not my vibe / Been there / Just skip it** without changing global constraints;
4. undo the rejection;
5. lock the offered compromise and observe the engine recalculate;
6. inspect **How this recommendation was made / What did Qloo change?**;
7. choose a plan, review its timeline/checks, open the route and copy a short plan.

The engine does not hard-code a winning venue for this demo.

## Deployment path

`render.yaml` is prepared for the zero-cost Render web service in `fixture` taste mode with the real Warsaw catalog. This keeps the stable demo available before credentials arrive and avoids accidental Qloo or Google Places quota use. Near submission, switch the hosted service to live Qloo only after `python live_smoke.py` passes locally and the server-side `QLOO_API_KEY` is configured. Free hosting can cold-start, so verify the public URL from a clean browser session before final submission.

Stable public demo: **https://unstuck-city-compass.onrender.com**. It runs on Render independently of the development PC. The current hosted build intentionally uses `fixture` taste mode with the real Warsaw catalog until live Qloo is enabled near submission. Devpost submission remains a separate final action. The free Render instance can cold-start after inactivity, so the first request may take a few seconds; this does not depend on the development PC being online.

## Limitations

- Warsaw only by design: one deeply auditable pilot city rather than shallow multi-city coverage.
- No reservations or live table availability.
- Initial search travel is an estimate; selected options are checked with street/scheduled-transit outbound and return routing. Transit is not realtime and there is no live traffic/vehicle-position guarantee.
- Some restaurant/cafe prices or hours are deliberately unknown when a strong current source was not confirmed.
- No user accounts, payments, social features, or full-trip planning.
- Live Qloo quality is not considered validated until `live_smoke.py` passes against the real API and human comparison is run.

## Hackathon

Qloo Agentic Hackathon 2026: https://qloo.devpost.com/

Rules: https://qloo.devpost.com/rules

The published deadline should be re-checked immediately before submission.

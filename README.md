# Unstuck

**Find the smallest change that saves your plan.**

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

The search policy is deterministic and stateful. It is an agentic tool policy, not a simulated chain-of-thought UI: it observes the result of each feasibility pass, chooses whether the next explicitly allowed strategy is necessary, logs the action, remembers rejections and updates, and stops when a useful non-dominated set is found or the allowed search space is exhausted.

## Current flow

`brief -> validated state -> taste ranking -> strict feasibility -> allowed relaxation(s) -> Pareto filtering -> max 3 cards -> reject/change -> re-run`

Each result card exposes:

- **Keep** — what still satisfies the brief;
- **Change** — exact deltas such as extra one-way minutes or reduced stay;
- **Why this fits** — the role of the current taste provider;
- **Needs checking** — facts that are not strong enough to confirm a hard constraint;
- source/status metadata for price and opening hours.

Unknown data never becomes a confirmed PASS.

## Data modes

The same business logic is used in all modes.

| Mode | Operational place facts | Taste signal | Intended use |
| --- | --- | --- | --- |
| `fixture` + `real` catalog | 16 real Warsaw seed places | deterministic authored taste fixtures | default local development before a Qloo key is available |
| `baseline` + `real` catalog | same real Warsaw seed places | none | controlled no-Qloo comparison |
| `live` + `real` catalog | same real Warsaw seed places | live Qloo | final integration / judging |
| `fixture` + `fixture` catalog | synthetic places | deterministic fixtures | fully deterministic engine tests |

Fixture taste data is always labeled as fixture data and is never presented as a Qloo response.

## Qloo's role

The live adapter follows the current Qloo hackathon API pattern:

1. resolve named interests and places through `GET /search`;
2. evaluate the **same candidate place pool** through `GET /v2/insights`;
3. pass the resolved taste references in `signal.interests.entities`;
4. restrict the comparison with `filter.results.entities` and `filter.type=urn:entity:place`;
5. sort by affinity and keep Qloo's result as a recommendation signal, not a probability of satisfaction.

The server sends the key only in the `X-Api-Key` header. The browser never receives it. The transport has timeouts, bounded retry for 429/temporary server failures, a per-process network-call budget, and a small **process-memory-only** short-lived cache. Qloo output is not persisted to disk or bulk-downloaded.

Official references:

- https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide
- https://docs.qloo.com/reference/parameters
- https://docs.qloo.com/reference/search
- https://www.qloo.com/legal/terms

The public Qloo terms can be supplemented by account-specific API terms. Before final deployment, review any additional terms supplied with the hackathon key.

## Place facts and scope

`data/places_warsaw.json` is the operational seed catalog and source-of-truth for this MVP. It currently contains **16 real Warsaw places across restaurant, cafe, and culture categories**. `data/origins_warsaw.json` contains **158 recognizable starting points across all 18 Warsaw districts**, so travel constraints are not limited to a handful of centre presets. Start-point matching is diacritic-insensitive, which makes the demo usable for judges typing Polish place names on non-Polish keyboards.

Each material field carries a status and provenance where available:

- `confirmed` — checked against the listed source on 2026-10-04;
- `estimated` — usable only with a visible warning;
- `unknown` — never sufficient to confirm a locked constraint.

Coordinates were geocoded from the listed addresses with OpenStreetMap Nominatim on 2026-10-04. Travel time is intentionally shown as an estimate derived from straight-line distance and a simple city model; it is **not** a live route or punctuality guarantee. The catalog is a seed set, not a claim about everything available in Warsaw.

## Run locally on Windows

Requirements: Python 3.12+; no pip packages are required for the current MVP.

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

The UI includes a **Load a judge-friendly demo** action so an evaluator who has never visited Warsaw can reproduce the intended flow immediately. One simple judging path:

1. choose a dinner brief for two people in central Warsaw;
2. lock the total budget and return time;
3. allow a small amount of extra one-way travel and a small stay reduction;
4. run the search and inspect `Keep`, `Change`, `Why this fits`, and sources;
5. reject the top option;
6. observe the next round: the rejected place stays excluded;
7. lock one of the offered compromises or edit the budget;
8. observe that the policy either changes strategy or honestly returns no feasible result.

The engine does not hard-code a winning venue for this demo.

## Deployment path

`render.yaml` is prepared for a zero-cost Render web service using the live Qloo mode. Before deploying it, set the `QLOO_API_KEY` secret in the service environment. Free hosting can cold-start and its limits can change, so verify the current free-plan behavior before submission and test the public URL from a clean browser session.

Public deployment, public repository creation, and Devpost submission are intentionally not performed by the local build step.

## Limitations

- Warsaw only and a deliberately small seed catalog.
- No reservations or live table availability.
- Travel is an estimate, not a routing engine.
- Some restaurant/cafe prices or hours are deliberately unknown when a strong current source was not confirmed.
- No user accounts, payments, social features, or full-trip planning.
- Live Qloo quality is not considered validated until `live_smoke.py` passes against the real API and human comparison is run.

## Hackathon

Qloo Agentic Hackathon 2026: https://qloo.devpost.com/

Rules: https://qloo.devpost.com/rules

The published deadline should be re-checked immediately before submission.

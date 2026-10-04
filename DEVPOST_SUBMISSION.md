# Devpost submission draft — Unstuck

> Status: ready as submission copy, but **do not final-submit until live Qloo smoke test and public deployment pass**.

## Project name

Unstuck

## Elevator pitch

An agent that rescues broken real-world plans by finding the smallest acceptable change — preserving hard constraints first, then using Qloo to choose the best cultural fit among feasible alternatives.

## One-line positioning

**The plan failed. Unstuck changes as little as possible.**

## Inspiration

Most recommendation products start from a blank page: “What should I do?” Real life often starts somewhere harder: the plan already exists, then one thing breaks.

The restaurant is closed. The replacement is too expensive. The museum closes too early. A new option would get us home too late. At that point the user does not want another endless discovery feed — they want to save the original plan without renegotiating everything.

Unstuck treats this as a constrained recovery problem. The goal is not to find the highest-scoring place in the city. The goal is to preserve the parts of the plan that still matter and change only what must change.

Warsaw is the first auditable pilot dataset, not the product thesis. The underlying problem — recovering an infeasible plan under time, cost, activity and taste constraints — is city-independent.

## What it does

The user describes a plan that failed and separates the brief into three layers:

- **Locked constraints**: conditions Unstuck cannot violate unless the user explicitly changes them, such as total budget, required activity, minimum stay and return time.
- **Negotiable constraints**: a precise amount of extra travel, a shorter stay, or an optional category change that the user is willing to accept only if necessary.
- **Preferences**: taste references used to distinguish between alternatives that already pass feasibility.

Unstuck then:

1. removes the failed place and previously rejected options;
2. evaluates the current candidate pool against cost, timing, opening-window, activity and travel constraints;
3. uses Qloo to rank the **same feasible place pool** against the user's cultural taste signals;
4. tries the strict brief first;
5. only if strict search fails, applies the next explicitly allowed compromise;
6. removes dominated compromises with Pareto filtering instead of mixing money, minutes and affinity into one opaque score;
7. returns at most three alternatives with explicit **Keep**, **Change**, **Why this fits**, and **Needs checking** sections;
8. remembers rejected places and changed conditions in the next round.

If no candidate can satisfy the checked facts and allowed compromises, Unstuck stops and explains the blockers instead of silently breaking a locked condition.

## How Qloo is used

The intended live flow is:

`taste names -> /search -> Qloo entity IDs -> fixed place candidate pool -> /v2/insights with filter.results.entities -> affinity ordering + explainability -> feasibility-preserving result cards`

Unstuck uses Qloo for a specific step that operational rules alone cannot solve well: **which of several feasible substitutes is the strongest cultural fit for this user's taste**.

The operational facts — price, hours, travel estimate, budget and return time — remain separate from Qloo. Qloo does not decide whether a place is open or affordable. It ranks the same already-defined place pool by cultural affinity, and the UI only surfaces explainability evidence when Qloo actually returns it.

That separation is intentional. A generic LLM could generate plausible venue names, but it would not provide the same grounded cross-domain cultural graph and controlled same-pool ranking that the decision policy can inspect.

## How I built it

Unstuck is a lightweight Python web application with a deterministic, stateful decision engine and a responsive HTML/CSS/JavaScript interface.

The backend models:

- a validated `SearchBrief`;
- persistent session state with rejected places and updated constraints;
- hard feasibility checks;
- explicitly ordered relaxation strategies;
- Pareto dominance for compromise minimality;
- separate taste providers for fixture, no-taste baseline and live Qloo modes.

The current Warsaw pilot has:

- 1,993 Warsaw destination places, including 1,982 restaurants from the recorded 2026-10-04 OpenStreetMap snapshot plus curated overrides; provisional operational facts are clearly distinguished;
- 158 saved starting locations across all 18 Warsaw districts;
- 6,049 locally indexed Warsaw street names and 125,217 exact OpenStreetMap addresses, plus browser Current Location inside the pilot bounds;
- scheduled Warsaw public-transport routing with departure/arrival times, line numbers, transfers, stop lists and map geometry;
- pedestrian street routing through Valhalla/OpenStreetMap;
- per-field provenance/status for material place facts;
- diacritic-insensitive start-location matching for international testers;
- deterministic fixtures for local development;
- a feasibility-only baseline for later controlled Qloo comparison.

The live Qloo adapter uses server-side `X-Api-Key` authentication, bounded retries for temporary errors/429s, request timeouts, a process-level network-call budget, response-size protection and a short-lived RAM-only cache. Qloo responses are not bulk-downloaded into a local database.

## Agent behavior

The agent makes concrete, observable decisions rather than running one static recommendation query:

- construct the current candidate pool;
- exclude the failed place and prior vetoes;
- test the strict brief first;
- decide whether the next allowed compromise is necessary;
- stop once a non-dominated feasible set exists;
- preserve rejected places across rounds;
- recompute when the user changes a condition;
- return no result instead of inventing a compromise outside the brief.

The UI exposes a compact action log so these decisions can be inspected without exposing hidden chain-of-thought.

## Challenges I ran into

### 1. Defining “smallest change” without a fake universal score

The tempting implementation is to turn price, time, distance and taste into one weighted number. That makes ranking easy but the units are not naturally comparable: five minutes and 20 PLN do not have a universal exchange rate.

Unstuck keeps these dimensions separate and uses Pareto filtering. An option is removed when another option is at least as good on every compromise dimension and strictly better on at least one.

### 2. Keeping unknown operational data honest

A recommendation system can look polished while hiding uncertainty. In Unstuck, missing or weak price/hour data never becomes a confirmed PASS. The UI marks the result as requiring checking instead of manufacturing certainty.

### 3. Making Qloo important without letting it override reality

Qloo is strongest as a cultural taste layer, not as a substitute for opening hours, budgets or transport. The architecture therefore makes feasibility a gate and uses Qloo inside the surviving candidate pool. This also creates a clean no-taste baseline for measuring Qloo's real contribution later.

### 4. Making a one-city beta understandable to an international jury

The first dataset is Warsaw because it can be audited deeply. The UI therefore translates every local fact into universal quantities — cost, minutes, hours and preserved/changed constraints — and includes a judge-friendly preset so no knowledge of Warsaw is required to understand whether the rescue is valid.

## Accomplishments that I am proud of

- The engine never allows a strong taste signal to override a hard budget or required activity.
- Unknown price/hour facts cannot become confirmed feasibility.
- Rejected places persist into later rounds.
- A budget or constraint change recomputes the same session instead of restarting from scratch.
- Cross-midnight opening windows and return-time calculations are covered by tests.
- Compromise minimality is tested directly with Pareto dominance cases.
- The Warsaw pilot supports 158 saved start points, 6,049 street names, 125,217 exact addresses and browser Current Location inside Warsaw.
- Selecting a result builds a real pedestrian street route or scheduled Warsaw transit itinerary; transit output includes departure/arrival, lines, transfers and stops and is explicitly labelled as scheduled rather than realtime.
- The discovery catalog now contains 1,982 restaurants. The recorded 2026-10-04 OpenStreetMap snapshot returned 1,979 restaurant features; curated records replace two duplicates. Places with insufficient price/hour evidence are shown as provisional instead of being silently treated as hard-constraint passes.
- The Qloo adapter evaluates an explicitly fixed place pool through `filter.results.entities` instead of comparing unrelated discovery queries.
- The current automated suite passes **40/40 tests**, including HTTP end-to-end state flow, large Warsaw data coverage, address lookup and routing checks.
- Fixture taste data is clearly labelled and never presented as live Qloo output.

## What I learned

Recommendation and recovery are different product problems.

When a plan is already partially specified, the useful question is often not “what is best?” but “what is the smallest acceptable change that keeps the rest true?” That shifts the architecture from pure ranking toward constraint reasoning, explicit uncertainty and persistent state.

I also learned that Qloo is easier to evaluate credibly when its role is isolated. If operational facts, taste and agent policy are separated, I can compare live Qloo against the exact same feasible candidate pool with a no-taste baseline instead of claiming that a higher affinity score automatically means a better human outcome.

## Potential impact

The immediate use case is everyday local planning: dinner, coffee, a cultural visit or another short outing where the original plan becomes impossible.

The broader pattern applies to any city where a user already has intent and constraints but one dependency fails. The value is reducing the cost of replanning: keep the budget, keep the return time, keep the purpose of the outing, and change only the smallest necessary part.

The current submission does not claim global operational coverage or proven satisfaction gains. It demonstrates a concrete recovery policy in one auditable city pilot and is structured so city coverage is a data/provider expansion rather than a redesign of the decision engine.

## What's next

Before final submission:

1. set the official hackathon `QLOO_API_KEY` and run the live smoke test;
2. verify live Qloo entity resolution for the Warsaw candidate catalog;
3. verify the exact live explainability structure;
4. compare live Qloo against the no-taste baseline using identical briefs and candidate pools;
5. deploy the live backend publicly with the API key stored server-side;
6. test the public URL from a clean browser session;
7. capture final live screenshots;
8. re-run the complete submission preflight before Devpost submission.

After the hackathon, the next product step would be a second city using the same engine to demonstrate portability, followed by richer live availability/transport integrations where reliable sources permit it.

## Built with

Python, JavaScript, HTML, CSS, Qloo API, REST API, Leaflet, OpenStreetMap, Valhalla, Warsaw GTFS/WTP data, Nominatim fallback, Git, Render

## Testing instructions for judges

1. Open the public demo URL.
2. Click **Load a judge-friendly demo**. No Warsaw knowledge is required.
3. Inspect the locked constraints: two people, total budget, return time, minimum stay and maximum one-way travel. The preset runs immediately and uses the nearest sensible evening rather than a stale fixed date.
4. Select different A/B/C cards. The map marker and detailed route must change with the selected result.
5. In transit mode, inspect scheduled departure/arrival times, line number(s), transfers and stop list. Switch to walking mode to see the routed pedestrian street path.
6. Open **Review conditions** and enter **Chmielna 26** as the start point. It should resolve from the bundled Warsaw address index without per-keystroke network autocomplete.
7. Reject the top option. The next round must keep that place excluded. Change the budget or lock one of the offered compromises to recompute the same session.
8. Toggle dark mode and, if physically inside Warsaw, optionally test **Current location**.
9. For final live judging, the status badge must show the verified live-Qloo mode rather than fixture taste.

No login is required. The Qloo API key is server-side.

## Devpost form values

### Project name

`Unstuck`

### Elevator pitch / tagline

`An agent that rescues broken real-world plans by finding the smallest acceptable change — preserving hard constraints first, then using Qloo to choose the best cultural fit among feasible alternatives.`

### Project start date

`October 4, 2026`

### Existing project / prior work

`N/A — Unstuck was started as a new project for this hackathon. An earlier separate hackathon prototype (CommonGround) was not reused as the Unstuck product; only general lessons and selectively reusable API patterns informed development.`

### Built with

`Python, JavaScript, HTML, CSS, Qloo API, REST API, OpenStreetMap Nominatim, Git, Render`

### Source code

`https://github.com/MeowRona/Unstuck`

### Demo URL

**Do not paste a placeholder into the final submission.** Add the verified public deployment URL here after the live Qloo smoke test and deployment pass.

### Video

Not required by the current Qloo hackathon submission baseline. If an optional short video is added later, show: failed plan -> judge demo -> result Keep/Change -> rejection -> second round -> live Qloo badge.

## Public links

- Repository: https://github.com/MeowRona/Unstuck
- Demo: **TBD after verified live deployment**

## Final release gate

Do **not** final-submit while any of these is true:

- `python live_smoke.py` still returns `BLOCKED_NO_API_KEY`;
- public demo is in fixture taste mode instead of verified live Qloo mode;
- a live Qloo request cannot resolve the chosen taste references/candidate places;
- a rejected result can reappear in the next round;
- an unknown material fact is displayed as confirmed;
- the public repository is missing source, README, license or run instructions;
- the public deployment has not been tested from a clean session.

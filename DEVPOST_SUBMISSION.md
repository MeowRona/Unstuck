# Unstuck — Devpost submission draft and judge script

> **Not submitted.** Last technical review: **14 October 2026**. Official event: [Qloo Agentic Hackathon](https://qloo.devpost.com/rules). Submission closes **30 October 2026, 23:45 Eastern Time**. Keep this draft aligned with the final public build before submitting. The organizer's published requirements prevail if they change.

## Required submission fields

**Name:** Unstuck

**Tagline:** The plan failed. Unstuck changes as little as possible.

**Live demo:** https://unstuck-city-compass.onrender.com/

**Open-source repository:** https://github.com/MeowRona/Unstuck — MIT `LICENSE` at repository root, README, startup instructions and full source.

**Built with:** Python (standard library), JavaScript, HTML, CSS, Qloo API, Leaflet, OpenStreetMap, scheduled Warsaw GTFS/WTP, Valhalla pedestrian routing, Nominatim fallback, GitHub Actions and Render.

**Started:** 4 October 2026, during the competition period. Earlier separate prototype ideas informed the design; Unstuck is a separately built product, not a relabeled submission.

**Testing:** Public browser demo, no login. Qloo credential lives only in the server's environment, not in the repository or browser.

## Short description — for the Devpost project page

Most city planning tools help you start a plan. **Unstuck helps when the plan breaks.**

A restaurant closes, the trip takes too long, or a replacement breaks your return deadline. Users want to preserve what still matters, not start over. Unstuck asks what is *locked* (budget, time, required meal or event), what may *change* (a limited travel extension, a shorter stay, optionally the category), and what each person *likes*.

Its agent filters for operational feasibility, then uses **live Qloo taste signals** to rank the **same feasible restaurant shortlist**. It can reject suggestions with a reason, undo them, check routes, and revise the plan without silently relaxing locked conditions. A second mode builds and repairs a multi-stop day around a fixed event. A reproducible two-stage dinner-failure demo keeps the concert locked while replacing the unavailable dinner, and visibly reports what changed.

Qloo's role is measurable: a same-pool comparison shows the top itinerary **with and without Qloo**, rather than treating a successful API call as proof of improvement. The first pilot city is **Warsaw**, with local transit schedules and a source-aware venue catalog.

This is a working, deliberately constrained product—not a claim that any restaurant has live table availability or that Qloo has scored every museum or concert.

## The real-world problem

When a plan is already partially committed, generic recommendation feeds offer unrelated options and hide the trade-offs. An evening has dependencies: opening windows, travel time, fixed events, people, price, and a deadline to return. A new suggestion can be attractive and still impossible.

Unstuck treats that as a **constrained plan-repair problem**, not just a generic place search. Success means preserving the original intent and changing only the minimum explicitly acceptable parts.

## What the app actually does

### Rescue a Plan

1. Accept the failed place, goal, date, location and return time.
2. Keep the user's **locked conditions** immutable until the user edits them.
3. Exclude the failed venue and prior rejections.
4. Test local restaurants against open windows, cost confidence, trip duration, required activity and return feasibility. Unknown facts remain unknown.
5. Prefer strict solutions. Try only the user's explicitly permitted extra travel, stay reduction or category change when needed.
6. Use Qloo to rank **up to ten operationally feasible place options** by recognized cultural interests.
7. Return no more than three non-dominated suggestions with **Keep / Change / Needs checking**, route details, provenance and a baseline-vs-Qloo explanation.
8. Allow **Too far / Not my vibe / Been there / skip**, undo, precise preference changes and another search without losing the rejected-place state.

Optional **Good for both** takes two separately supplied taste profiles, requests independent Qloo rankings of the same feasible shortlist, and uses a transparent minimax compromise in rank *positions*. If fewer than two venues are ranked in both lists, the feature honestly falls back to operational recommendations. In the bounded production probe on **14 October 2026**, the Radiohead / Coldplay test returned a **verified shared ranking over 4 common venues** (Person A: 4 ranked, Person B: 4 ranked). That verifies the comparison path and coverage for one request; it is not a claim that two real users preferred the result.

### Plan a Day

- Month/date selection, attractions, museums, restaurants and a **small manually sourced event snapshot**.
- One to four stops, a fixed-event arrival buffer, sequential travel and a return deadline.
- Up to three alternative itineraries; automatic next-option route check when a route proves conflicting, capped at three.
- The **Try a full-evening rescue** button performs **two simulated reported dinner failures** on the actual plan-repair path, keeping a booked concert locked and showing before/after stops and time shifts.
- Saved browser-local plans and full-plan / activity calendar `.ics` export.
- **Already out?** can freeze the completed prefix as immutable history and replan only what remains from the user's current time and current/last-stop location. The user supplies the **budget left** for the rest of the day; a newly failed future stop can be excluded in the same action.
- In live mode, Qloo ranks **eligible restaurants only**. The code does not infer Qloo affinity for museum exhibits, events or concert tickets.

### How Qloo makes a difference

The actual integration is:

`named taste → bounded Qloo /search or user-picked exact entity → resolved Qloo IDs → filtered feasible venues → /v2/insights → restaurant ordering`

Qloo ranks a **fixed operational candidate pool**; it never overrides a locked budget, closed hours or a route conflict. The interface displays recognized/unrecognized signals, how many of ten candidates resolved, how many actually received ranks, and whether the **same-pool no-taste baseline** chose another top restaurant/itinerary.

The latest bounded production acceptance run verified live Qloo in Rescue and Plan a Day, **5 ranked restaurants out of 10 candidates** in the sampled planner scenario, and a changed top plan when Qloo was used. The five exact catalog identities resolved in that request were **HOŻA Steakhouse, Akademia, Vegan Ramen Shop — Muranów, Kieliszki na Próżnej, and Mąka i woda**. A separate bounded two-profile production probe then verified **4 common ranked venues** for the Radiohead / Coldplay test (A=4, B=4) using the same-feasible-pool minimax policy. These are technical ranking/coverage results, not evidence of statistically significant user satisfaction or universal catalog coverage.

**Why this is agentic:** Unstuck retains state; enforces immutable constraints; iteratively tests strict, relaxed and rejected candidate sets; calls external ranking and routing tools; checks tool results; retries bounded alternative routes; and stops transparently when no feasible action exists. The agent has visible actions and testable outputs, not fabricated reasoning.

## Architecture, data and provenance

The deployment is a lightweight Python standard-library backend plus vanilla responsive browser frontend. The Warsaw pilot contains approximately **1,993 locations**, including **1,982 restaurants**, 158 curated starting landmarks, and a local address/street index. Operational routing uses OpenStreetMap-based walking geometry or **scheduled** GTFS/WTP transit, not realtime train/bus positions.

A separately audited overlay covers **32 individually identified restaurant branches**: 30 operator-confirmed regular weekly-hour schedules, and 2 schedules intentionally marked provisional due to conflicting sources. Six branches include examples of a **published named-dish price**. The app explicitly refuses to treat an optional dish quote as a whole dinner price or a guaranteed minimum bill. Holiday exceptions, actual availability, other menu costs and ticket stock are not asserted.

The event list is a **manual snapshot**, not a citywide live events API. The current selected-source window reaches **28 November 2026** and includes dated sessions from official Go2Warsaw and Polish National Opera listings. Some records still have no verified session time and are discoverable but cannot be inserted into an itinerary. The user can inspect sources and verification dates.

Qloo requests use a server-side API key, explicit request limits, short-lived in-memory cache, bounded timeouts and retries. Google Places enrichment is configured but **disabled** during judging-preparation work to avoid wasting quota; the app does not present unsourced ratings or images as authentic Google data.

## Technical challenges and lessons

**Minimal compromise without false math.** We do not add PLN to minutes to produce a single pseudo-scientific score. The planner respects a strict relaxation ladder, and candidates are Pareto-compared on explicit change dimensions.

**Incomplete city data.** It is easy to make an impressive but inaccurate demo by inventing opening hours, menu prices or event availability. Unknowns are marked as requiring confirmation; a single named-dish quote is never passed off as proof the whole meal fits a hard budget.

**Qloo coverage and exact cultural identities.** Names like films and artists can be ambiguous. The optional entity picker lets the user explicitly select an artist, film, book or show. Catalog places that do not resolve against Qloo keep their operational ranking; the API may be temporarily unavailable or return insufficient coverage.

**Real repair instead of rearranging static cards.** A rejected restaurant is excluded on the next round. A simulated failed dinner is replaced through the same day-planning API, preserving the fixed concert. Checked route conflicts trigger bounded re-validation of the next generated variants, not a silently optimistic itinerary.

## Judge-friendly demonstration — ~100–120 seconds

**0–15 s:** Open the live demo. Explain the failed plan and the difference between locked conditions and allowed changes. No Warsaw knowledge is required.

**15–35 s:** In **Rescue a Plan**, use **Try a rescue · 60 sec** (or the judge demo preset). Compare the three results. Show the **Keep / Change / Needs checking** evidence and a transit route. Reject an option and observe the next round without it.

**35–50 s:** Expand Qloo evidence. Show recognized cultural entities, actual ranked venue count and the same-pool baseline. If coverage is missing, say so; don't claim Qloo improved anything unless the evidence says the top actually changed.

**50–80 s:** Switch to **Plan a Day → Try a full-evening rescue**. The fixed **17 October 2026** scenario builds an evening with a locked concert. Two separate restaurant unavailability reports are **simulated**. Show how the real repair tool preserves the concert and excludes both failed restaurants.

**80–105 s:** Review the changed timeline, route-check evidence, sources, unknown ticket/meal availability, and the same-pool Qloo-versus-operational comparison. Demonstrate `.ics` export if the plan has no checked route conflict.

**105–120 s:** State the product thesis: *preserve the plan, not just the venue*. Note the Warsaw pilot and the constraints on actual Qloo entity coverage.

**Important:** The demonstration's reported restaurant failures are simulated; the app has no reservation or closure-detection feed. On a future judging date, the 17 October scenario is historical and should be described that way.

## What is NOT proven

- No broad claim that Qloo recognizes all Warsaw restaurants; the latest bounded production sample ranked **5/10** eligible restaurant candidates and changed the top plan. Treat that as request-specific evidence, not universal coverage.
- The two-profile production probe verified a technical shared ranking for one Radiohead / Coldplay request (4 common venues; A=4, B=4), but **no human preference improvement is validated**. The minimax result is a transparent ranking policy, not a probability that two people will like the same restaurant.
- No survey outcome or statistically validated human preference improvement. The app has an optional anonymous, client-local A/B study interface and CSV export, but **no 6–10 actual volunteer results** have been collected.
- No realtime opening, queue, restaurant table, ticket inventory, live GTFS delay, or complete concert/museum Qloo personalization.
- No guarantee of restaurant-specific price and exact date hours beyond documented sources.
- No guarantee that a proposed venue is bookable right now.

## Deployment and quality evidence

- Public source and MIT license: https://github.com/MeowRona/Unstuck
- Live app: https://unstuck-city-compass.onrender.com/
- Automated tests / exact-commit Render production smoke: https://github.com/MeowRona/Unstuck/actions?query=branch%3Amain
- Baseline comparison and human-study protocol: [JUDGE_DEMO_AND_VALIDATION.md](JUDGE_DEMO_AND_VALIDATION.md)
- Qloo integration details: [QLOO_INTEGRATION.md](QLOO_INTEGRATION.md)

CI runs Python unit/HTTP tests, JavaScript checks, desktop/mobile browser smoke and an exact-git-SHA live Render smoke on merge. Do **not** copy a stale hardcoded passing-test count into the Devpost entry.

## Final submission checklist (not all complete)

- [x] Functional HTTPS demo, public code and MIT license.
- [x] Live Qloo Rescue + limited Plan a Day verified in production.
- [x] Reproducible judge scenario, route/repair and same-pool Qloo evidence.
- [x] English source docs and user interface.
- [ ] Record a short honest walkthrough video or screenshots; the rules permit judging from text and images, so a polished optional demo is valuable.
- [ ] Run one clean-session mobile and desktop acceptance check against the **final exact SHA**.
- [ ] Refresh operational/event data if materially stale, or state the current snapshot dates.
- [ ] Conduct the voluntary anonymous A/B test **if consenting real testers are available**; never invent results.
- [ ] Register/enter required fields and **submit** on Devpost by the official deadline. This is a user/account action, not completed by the repository.

**Official judging criteria:** Technological Implementation, Design, Potential Impact and Quality of the Idea are **equally weighted**. The entry must offer a functional demo, public open-source repo with license, and English description; video is not listed as a mandatory standalone element in the published baseline rules. See https://qloo.devpost.com/rules.

# Unstuck — judge walkthrough and evidence protocol

Status: 2026-10-13. Public app: https://unstuck-city-compass.onrender.com/

## Interactive 110-second walkthrough

Use **Plan a day → Try a two-failure rescue · 110 sec**. The button runs a *fixed, reproducible scenario* dated **17 October 2026** against the bundled Warsaw source snapshot. It is not an assertion about today's event listings or a real restaurant closure.

1. **0–15 s — The commitments.** Observe a three-stop day with a concert (Simple Plan) locked in place, a meal, a budget, and a return deadline. Check unknown ticket availability and event end separately; neither is magically verified.
2. **15–30 s — The disruption.** The demonstration explicitly **simulates a user reporting the selected restaurant unavailable**. Unstuck excludes that restaurant from the new plan. The app does not monitor actual closures or restaurant availability.
3. **30–55 s — The repair.** The planner reuses the existing candidate search and schedule constraints. It is allowed to replace dinner but not remove the locked concert or silently expand the deadline/budget.
4. **55–80 s — A second disruption.** The first replacement is also *reported* unavailable. The app calls its actual repair operation a second time, carrying both excluded restaurant IDs forward; the locked concert cannot be removed. This loop is deliberately bounded at two attempts. If no second alternative exists or its checked travel fails, the interface must report that outcome rather than claiming a successful rescue.
5. **80–100 s — Evidence.** Read the genuine **BEFORE / AFTER** differences and the final substitute. Confirm the two excluded places and review checks for budget, opening times and travel.
6. **100–110 s — Qloo and export.** Open **Sources, coverage & assumptions**. Qloo currently ranks *eligible restaurants only*, and only when at least two distinct Qloo entities and a usable taste profile are returned. On insufficient coverage, the planner deliberately reports the limitation and keeps feasibility ranking. Click **Download .ics** to export the displayed plan.

**Do not claim:** autonomous closure detection, ticket inventory, realtime transit, a fully personalized concert/museum ranking, or that 17 October is a current live event feed.

## What the current automation validates

GitHub Actions runs unit, HTTP, desktop browser and 390x844 mobile UI checks on pull requests. The full-evening demo browser check verifies that the concert remains, both user-reported unavailable dinners are excluded by the real repair flow, the locked concert is retained, and BEFORE/AFTER notes are shown. On merge to main, the pipeline checks the *exact* Render commit and executes production smoke. This is not a user preference study.

## Human evaluation protocol (not yet conducted)

**The app now includes an opt-in blind trial instrument:** open Plan a day, generate a result with two distinct same-pool rankings, expand **Optional blind comparison · real testers**, and click **Start one blind trial**. Option A/B is randomized client-side and does not reveal which option used Qloo. The chosen plan and decision time are kept only in that browser's local storage; use **Export anonymous CSV** to collect responses. The preview contains only the original schedule estimates, not later route-check validation. No result is transmitted to a server and **no real human trials have yet been run or claimed**. A tester should consent before participating. If Qloo makes no difference or does not cover two alternatives, the button is disabled and no artificial preference test is created.

Recruit **6–10 willing testers**. For each tester use a clear consent statement and no identifying information, account registration, or Qloo private user data. Show two options from an **identical frozen feasible pool** with identical source facts, budget, travel and date, once with Qloo taste ordering and once with the operational no-taste ordering. Randomize which unlabeled ranking appears first. Do not tell testers which is Qloo until their choice is recorded.

Record only anonymized trial number, scenario ID, whether two-plus Qloo options were actually ranked, the selected proposal (or “neither”), time to first decision, reason for rejection, and whether a non-taste hard constraint was violated. Include no-coverage and no-order-change trials, don't cherry-pick the best case, and don't invent a result.

| Trial | Scenario | Qloo-ranked / eligible | Order shown first | Choice | Decision time | Rejection / notes |
| --- | --- | --- | --- | --- | --- | --- |
| Not run | — | — | — | — | — | Awaiting real testers |

Report descriptive totals (e.g. 4/8 preferred the taste-ordered shortlist), *not* statistical significance or guaranteed improvement. A different ordering only proves ranking impact; preference must be measured separately.

## Known limitations / next gate

- The pilot is Warsaw-only and the bundled event snapshot is small and may be outdated by the judging period.
- The live Qloo connection for Rescue was verified; the planner may return **insufficient_coverage** for restaurants, and this must remain visible until real coverage improves.
- Prices, hours, tickets and scheduled transit can require manual confirmation.
- A demonstration of operational repair is not proof of globally smallest change across every Warsaw venue.
- Before final submission, refresh appropriate event sources, retest mobile/desktop on the public build, validate at least two *actually ranked* restaurants across multiple scenarios, and run the human study or clearly label it NOT RUN.

# Qloo integration alignment

This document records how Unstuck maps to the official Qloo Hackathon Kit and what must be verified before submission.

Official references:

- https://github.com/qloo/qloo-hackathon-kit
- https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/API_ACCESS.md
- https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SAFE_USE.md
- https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SUBMISSION.md
- https://docs.qloo.com/reference/insights-api-deep-dive

## Canonical product mapping

The closest official workflow is **`qloo_rank`**.

Unstuck first applies non-Qloo feasibility logic: required activity, budget, time window, return-by time, travel allowance, fact confidence, rejected venues, and the explicitly allowed relaxation ladder. Qloo is then used to order one shared shortlist against one shared taste profile.

| Unstuck concept | Qloo rank field |
|---|---|
| feasible restaurant/venue shortlist | `options` / `filter.results.entities` |
| place domain | `option_type=place` / `filter.type=urn:entity:place` |
| named taste references such as a film, artist, book or creator | `signals` / `signal.interests.entities` |
| output ordering | one shared `/v2/insights` result set |

The official harness contract accepts at most **10 options** for `qloo_rank`. The live adapter therefore sends no more than 10 candidates in one ranking round. Fixture mode is not subject to this live API boundary.

## Why this fits Unstuck

Qloo does not decide whether a place is open, affordable, reachable, or compatible with a locked return time. Those are product constraints. Qloo answers the narrower question: **among the options that can still save the plan, which ones align best with the supplied cultural/taste signals?**

This keeps Qloo essential without asking it to impersonate a routing, pricing, opening-hours, or reservation system.

## Resolution and ambiguity policy

- Named taste references and candidate venues are resolved through Qloo entity search before the rank call unless a verified Qloo entity ID is already known.
- An exact normalized name can proceed when it resolves uniquely.
- Ambiguous names fail visibly instead of silently accepting the first search result.
- Search ordering is never presented as taste affinity.
- When the live key arrives, the official harness should be used to cross-check ambiguous entities and the final request shape before launch.

## Quota discipline

The Hackathon Kit says to use the smallest request that answers the product question and to keep retries/cache bounded. Unstuck follows that policy:

- hard/geographic prefilter before Qloo;
- at most 10 live ranking options;
- one shared insights ranking request, not separate per-option affinity calls;
- short-lived process-memory cache only;
- bounded network-call budget;
- bounded retry count and explicit 429 handling;
- no bulk Qloo scraping and no persistent local Qloo database.

## Meaning guardrail

Affinity is a **relative Qloo signal for the interpreted profile**, not a probability that an individual will like a venue, not a universal quality score, and not evidence of causality. UI/submission copy must preserve that distinction.

Qloo receives public cultural/taste references and venue candidates. Unstuck does not need to send names, emails, device identifiers, location history, or other personal identifiers to Qloo.

## Evidence package required before final submission

Once `QLOO_API_KEY` is available:

1. Install/verify `@qloo/qloo-harness` **0.1.26 or newer**.
2. Run the offline-safe readiness checks from `tools/qloo_harness_preflight.py`.
3. Use `qloo explore` or `qloo exec rank` to validate the intended names/entities and one representative shortlist.
4. Inspect a redacted request preview and confirm the same fixed option set is used in one rank call.
5. Run `python live_smoke.py` against the real Unstuck adapter.
6. Save a redacted request-to-result example for the Devpost write-up/screenshots. Never include the credential.
7. Run a small human comparison of Qloo ranking versus the no-taste baseline.

Do not claim live Qloo validation before these steps pass.


## Product evidence contract

Unstuck exposes a compact `taste_audit` object with every search result so the jury-facing explanation can be generated from actions the product actually took rather than invented reasoning.

The contract separates:

- `input_references` — the cultural references supplied by the user;
- `recognized_signals` — live Qloo entities actually resolved from those references, including entity IDs/names safe for a redacted demo;
- `failed_place_anchor` / `anchor_used` — whether the unavailable original venue was successfully resolved and used as an additional live Qloo signal;
- `candidate_pool_size` — the same operationally feasible comparison pool;
- `baseline_order` — ordering of that pool without taste;
- `ranked_order` — live Qloo ordering of the same pool;
- `changed_top_choice` — whether Qloo actually changed the top result;
- `discovery_used` — currently `false`; Unstuck uses Qloo for ranking, not candidate discovery.

This separation matters because discovery and re-ranking are different product effects. If Qloo discovery is added later, it must be reported separately instead of being mixed into the same comparison.

### Before the API key is connected

The hosted beta runs in fixture taste mode. Its `taste_audit.status` is `fixture_preview`.

The interface may show the supplied references and a fixture preview order, but it must also say:

- Qloo was not called;
- fixture order is not proof of Qloo performance;
- entity recognition, live ranking impact and the baseline-vs-Qloo comparison become available only after the Qloo connection.

No affinity percentage or fabricated Qloo advantage is shown.

### Failed venue as a taste anchor

The optional unavailable venue has two concrete product effects:

1. it is always excluded from recommendations by the core rescue engine;
2. in live mode only, Unstuck best-effort resolves that place through Qloo and uses the resolved entity as an additional shared ranking signal.

Failure to resolve the venue as a Qloo entity never re-admits it and never blocks the rescue search. The evidence panel records whether the anchor was actually used.

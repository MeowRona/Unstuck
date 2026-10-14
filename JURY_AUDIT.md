# Jury verification audit

This file maps the current polish work to the Qloo Agentic Hackathon judging criteria and gives a concrete way to verify each claim in the public demo.

Official criteria: Technological Implementation, Design, Potential Impact, and Quality of the Idea are equally weighted. The rules also require a functional externally hosted demo and a public open-source repository.

Sources:
- https://qloo.devpost.com/
- https://qloo.devpost.com/rules

| Item | Jury value | How a judge can verify it | Current state |
|---|---|---|---|
| Clear, symmetric plan-choice CTA | High for **Design** | Run the judge demo, select any result, inspect the two aligned action buttons and choose a plan | Implemented |
| Smooth iOS-style wheel controls | Medium for **Design** | Open Review conditions and scroll Start/Back by/travel/stay wheels with mouse, trackpad or touch | Implemented; native momentum + proximity snap + settle snap |
| Warsaw-only pilot | High for **Potential Impact / Quality** if framed correctly | Use the judge demo; no local knowledge is needed because output is expressed as cost, minutes, hours, constraints and taste fit | Good scope; do not pretend global coverage |
| Large restaurant discovery pool | High for **Impact / Design** | Move the origin between central Warsaw, Muranów, Praga and Mokotów; cards change geographically. Reject cards to continue the session | 1,982 restaurants from the recorded 2026-10-04 Warsaw OSM snapshot plus curated overrides; repeated rejection descends into deeper alternatives while provisional facts remain visibly provisional |
| Exact Warsaw address input | High for **Design / Tech** | Type `Chmielna 26`; 6,049 street suggestions and 125,217 exact addresses are local, so this test requires no geocoder request | Implemented; public Nominatim is not used for autocomplete |
| Current location | Medium for **Design / Impact** | Click Current location and approve browser permission while physically inside Warsaw | Implemented; intentionally rejects locations outside pilot bounds, so remote judges outside Warsaw may only inspect the control |
| Scheduled public transport | Very high for **Tech / Design** | Use transit mode. The selected card shows a scheduled route with departure/arrival, lines, transfers, stop list and map geometry | Implemented from bundled Warsaw GTFS; explicitly not realtime |
| Walking route | High for **Tech / Design** | Switch Travel mode to Walk and choose a result; map changes to the routed pedestrian street path with route duration | Implemented via Valhalla/OpenStreetMap |
| Remove non-functional settings | High for **Design** | Open Review conditions: original-plan prose, failed-place name and failure reason are no longer exposed because they did not change ranking | Implemented |
| Taste references can be cross-domain | Critical for **Qloo / Quality of Idea** | In either mode, use the optional explicit artist/film/book/show picker; inspect which references actually resolved | Live Qloo works in Rescue and ranks limited eligible planner restaurants; unresolved signals are disclosed, not guessed |
| Same-pool Qloo counterfactual | Critical for **Tech / Quality** | Run a planner scenario with a recognized taste reference, open **What did Qloo change?** and compare operational vs Qloo top plans on the identical generated pool | Implemented; production smoke observed a changed first choice in one scenario, not proven preference improvement |
| Two-profile Good for both | High for **Qloo / Tech / Design** | In Rescue, enable **Good for both**, provide one taste for Person A and one for Person B, then open the evidence panel to inspect each person's Qloo rank and the minimax compromise | Live production probe #242 verified 4 common ranked venues (A=4, B=4) for one Radiohead / Coldplay request. This proves the two-ranking comparison path, not joint human preference |
| Two successive reported failures | High for **Agentic Tech** | Click **Try a full-evening rescue · 90 sec** and inspect first replacement, second exclusion, resulting locked concert and final substitute | Implemented as an explicitly simulated user report on a fixed 17 Oct 2026 snapshot; no live closure detection is implied |
| Bounded route self-repair | High for **Tech / Design** | Select a planner variant and verify route legs; conflict triggers at most two further distinct variants without silently relaxing hard constraints | Implemented; source/tested conflict fallback, scheduled transit is not realtime |
| Restaurant source confidence | High for **Credibility / Tech** | Open any OSM record versus a checked venue and inspect price/hour warnings | 30 operator-confirmed weekly schedules, 2 estimated due to conflicting operator evidence, and 6 independently quoted dish-only prices. Most prices remain unknown |
| Blind preference study | High for **Potential Impact** | Use blinded comparison instrument and protocol; verify any claims against actual anonymized voluntary responses | Instrument implemented, real participants NOT RUN; no satisfaction gain claimed |
| Google Maps photo/rating | Medium for **Design** | Near submission, enable Places and inspect restaurant thumbnail + rating | Integration ready but deliberately disabled to preserve free quota for judging |
| Dark mode | Low/medium for **Design polish** | Toggle moon/sun in header or menu and reload | Implemented; persisted in localStorage |
| Stable external hosting | **Submission-critical** | Open https://unstuck-city-compass.onrender.com from a clean browser/network | PASS — Render deployment is independent of the development PC; root/health and public search→reject flow were tested |
| Live Qloo | **Stage-one critical** | Run Rescue + Plan a Day and open the per-request Qloo evidence panel; compare the same candidate pool with and without taste | Live in both modes for eligible restaurants; latest bounded production planner scenario ranked 5 of 10 candidates and changed the top plan. No broader coverage or preference gain is claimed |

## Warsaw-only decision

Do **not** add a shallow second city just for optics. The rules do not require multi-city coverage. A deeply testable Warsaw pilot is stronger for Design and Potential Impact than two inconsistent datasets. The submission should say clearly: **Warsaw is the first auditable city pilot; the decision logic is the product.**

## Claims we deliberately do not make

- Transit is scheduled GTFS, not realtime vehicle prediction.
- OSM-imported restaurants with missing price/hours are visibly provisional and never silently treated as hard-budget confirmed.
- Google Maps photos/ratings are not scraped or persisted.
- The stable judging host is `https://unstuck-city-compass.onrender.com`. The old Quick Tunnel is development-only and is not required for the hosted demo.

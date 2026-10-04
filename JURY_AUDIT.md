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
| Taste references can be cross-domain | Critical for **Qloo / Quality of Idea** | Enter film/music/creator references and compare ranking once live Qloo is enabled | UI/adapter ready; live Qloo key still pending |
| Google Maps photo/rating | Medium for **Design** | Near submission, enable Places and inspect restaurant thumbnail + rating | Integration ready but deliberately disabled to preserve free quota for judging |
| Dark mode | Low/medium for **Design polish** | Toggle moon/sun in header or menu and reload | Implemented; persisted in localStorage |
| Stable external hosting | **Submission-critical** | Open https://unstuck-g5pc.onrender.com from a clean browser/network | PASS — Render deployment is independent of the development PC; root/health and public search→reject flow were tested |
| Live Qloo | **Stage-one critical** | Run the public demo after Qloo live mode is enabled; repository includes live adapter and smoke command | BLOCKED_NO_API_KEY until key arrives |

## Warsaw-only decision

Do **not** add a shallow second city just for optics. The rules do not require multi-city coverage. A deeply testable Warsaw pilot is stronger for Design and Potential Impact than two inconsistent datasets. The submission should say clearly: **Warsaw is the first auditable city pilot; the decision logic is the product.**

## Claims we deliberately do not make

- Transit is scheduled GTFS, not realtime vehicle prediction.
- OSM-imported restaurants with missing price/hours are visibly provisional and never silently treated as hard-budget confirmed.
- Google Maps photos/ratings are not scraped or persisted.
- The stable judging host is `https://unstuck-g5pc.onrender.com`. The old Quick Tunnel is development-only and is not required for the hosted demo.

# Plan a day — Warsaw data contract

The **Plan a day** beta is intentionally narrower than a city-wide event search engine. It combines the existing Unstuck restaurant catalog with a small verified Warsaw attraction/event snapshot and the existing routing stack.

Attraction/hours base snapshot checked: **2026-10-06**. Selected future event occurrences refreshed from official listings: **2026-10-14**. Event refresh does not re-verify the older attraction facts.

## Coverage semantics

The bundled event snapshot declares its own coverage window in `data/planner_warsaw.json`.

- Inside the declared event window, “no events” means **none of the selected loaded sources produced a matching record in this snapshot**.
- Outside the declared event window, the UI says **event data not loaded**.
- Neither state means “there are no events in Warsaw”.
- Institution opening schedules can remain useful outside the event snapshot window when a date-specific closure is not recorded, but they still carry their own `checked_at` date.

The current snapshot is manual/verified. It does **not** scrape sources on page load and does not pretend its verification date advances automatically.

## Selected event source

### Go To Warsaw / Warsaw Tourism Office

Calendar:
- https://go2warsaw.pl/en/what-where-when/
- https://go2warsaw.pl/en/main-page/

The current snapshot includes selected concrete occurrences such as:

- Simple Plan — 2026-10-17, 18:00, EXPO XXI
- Targi Rzeczy Wyjątkowych — separate 2026-10-17 and 2026-10-18 occurrences
- BERRE — 2026-10-17, 19:00, Klub Hybrydy
- GOD SAVE THE QUEEN — 2026-10-17, 20:00, Arena Ursynów
- HAPPYSAD — 2026-10-15, 19:00, Klub Stodoła
- Harlem Globetrotters — 2026-10-19, 19:00, COS Torwar
- Modern Seniors Club sculpture tour — 2026-10-27, 13:00–14:30, Museum of Modern Art ([museum schedule](https://artmuseum.pl/en/events/the-modern-seniors-club-gives-a-guided-tour-of-the-exhibition?term=019eff31-4b7a-71cf-88cd-ca8d3b89a08e))
- Fado Gala — 2026-10-29, 20:00, Scena Relax ([city events calendar](https://go2warsaw.pl/en/what-where-when/))
- Nigel Kennedy — 2026-11-04, 20:00, Warsaw Philharmonic ([city event](https://go2warsaw.pl/en/events/nigel-kennedy-virtuoso-tour-349/))
- Chopin recital — 2026-11-08, 17:00–18:00, Fryderyk Concert Hall ([organizer schedule](https://www.fryderyk.events/pl/pianist/chopin-concert-2/4720))

Date-only Warsaw listings for Europe (20 Oct), Jazz Jamboree (23 Oct), and YAMATO (9 Nov) remain **discoverable only**, because this snapshot does not establish a specific performance start time. Source URL and verification date are stored with each record; tickets remain explicitly unknown.

A festival/listing without a concrete captured session time can be shown in Explore but remains **not schedulable**. The planner never invents a start time.

## Selected attraction sources

### POLIN Museum
Official visit information:
https://polin.pl/en/basic-information

The snapshot records opening windows, weekly closure and core-exhibition last-entry behavior. Numeric admission price is left unknown when it was not captured confidently from the checked official material.

### Copernicus Science Centre
Official opening hours:
https://www.kopernik.org.pl/en/visit/opening-hours

The exhibitions are modeled separately from the Planetarium. The planner does not treat a Planetarium ticket as interchangeable with general exhibitions.

### Museum of Modern Art in Warsaw
Official visit information:
https://artmuseum.pl/en/visit

The snapshot records the currently published weekly hours, selected closure exceptions and the published regular-ticket range.

### Museum of Warsaw
Official visit information:
https://muzeumwarszawy.pl/en/visit/

The snapshot records the permanent-exhibition opening windows, last-entry behavior and currently captured regular-ticket price.

## Object model

The planner keeps three concepts separate:

1. **venue** — stable place/address/coordinates and source IDs;
2. **attraction** — a visitable activity with date-aware opening windows, estimated visit duration and optional last entry;
3. **event occurrence** — a concrete dated occurrence with its own start/end semantics.

Event series use a `series_id`; separate dates remain separate occurrences. Unknown end times stay unknown. The engine may use an explicit planning-duration estimate for feasibility, but ICS export does not write a fake confirmed `DTEND` for such an event.

## Price and availability

- Unknown price is never converted to 0.
- Unknown ticket availability is never converted to “available”.
- A plan with unknown cost components cannot claim the total budget is confirmed.
- `cancelled` and `sold_out` occurrences are excluded from feasible plans.
- Daily ticket, session ticket and pass semantics are not inferred when the source snapshot does not establish them.

## Routing

Initial variants use conservative distance-based estimates so the search can stay bounded.

The selected variant is then checked **segment by segment**:

`start → stop 1 → stop 2 → … → return`

Each transit query uses the end time of the previous activity as its departure time. Walking uses the existing Valhalla/OpenStreetMap adapter. Warsaw public transit uses the bundled scheduled GTFS index and is explicitly **not realtime**.

After route checking, fixed event arrival, attraction last entry, opening window and requested return time are re-evaluated. A checked route can therefore turn a candidate plan into a conflict.

## Saved plans

There is no account system. Saved planner state lives in browser `localStorage` under schema:

`unstuck-planner-saved-v1`

The store has an explicit schema version. Copying a saved plan to another date copies the flexible brief and re-runs planning; fixed event occurrences are not silently repeated on the new date.

## Qloo

**Limited live Qloo restaurant ranking** is available when the shared provider is in live mode and at least two eligible restaurant entities are returned and ranked.

Taste references are evaluated by Qloo for the restaurant shortlist only. At insufficient coverage the service visibly falls back to operational planning. Attractions and concerts use explicit interests and published operational facts, not fabricated cross-domain affinities. Current ordering uses:

1. preservation of existing stops during Repair this day;
2. feasibility confidence;
3. explicit category/tag interests;
4. a verified *restaurant-only* Qloo ranking, when present;
5. unplanned idle minutes, then travel;
6. known cost.

Every plan includes a `taste_status`, a domain-limited `taste_note`, and an audit of recognized/unresolved signals. For a successful live restaurant ranking, `same_pool_comparison` uses exactly the same generated feasible schedules for a no-taste versus taste comparison (before detailed route checks). Ranking impact is not the same as measured user preference. No fixture ranking is presented as Qloo evidence.

## Google Places

Google Places remains disabled by policy during development:

`GOOGLE_PLACES_ENABLED=false`

Plan a day does not require Places to function.

## Refreshing the snapshot

A future refresh should:

1. read the official source;
2. update only records actually checked;
3. preserve occurrence identity/series identity;
4. retain unknown fields as unknown;
5. change `checked_at` only for data actually re-verified;
6. update the declared event coverage window to match what was loaded;
7. run the planner tests and public production smoke.

Do not bulk-copy a third-party event database or claim completeness.

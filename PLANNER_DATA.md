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

## Restaurant facts: official hours and selected dish prices (14 October 2026)

The primary Warsaw restaurant catalog contains about 1,982 restaurant records, mostly OSM-discovered. It is **not** a catalog of independently verified prices and opening hours. Source confidence is stored per field.

**Confirmed closure exclusion:** the operator of [AleGloria](https://www.alegloria.pl/) at Plac Trzech Krzyży 3 announces that the restaurant is closing after the end of its lease. Although the unchanged OSM discovery snapshot still contains this venue, `data/restaurant_closures_20261014.json` excludes its exact ID/name/address from runtime recommendations (checked 2026-10-14). We do not infer closure of other venues from outdated or missing opening hours. The precise closure date is not asserted.

`data/restaurant_official_hours_20261014.json` audits **23 existing, branch-specific Warsaw restaurants**: **21 operator-confirmed regular schedules** and **2 conservatively estimated schedules** where different official 360° pages disagree. A provisional window must never be presented as confirmed opening hours. It updates **regular weekly hours**, with an exact ID/name/address guard. **Two ORZO branches** additionally include an independently checked single-dish price (Bigoli carbonara at 49 PLN) from the [published, city-wide identical ORZO menu](https://orzo.pl/pages/miasto/makarony-warszawa). Every other unknown meal price stays unknown. This is not a total cost or restaurant-wide estimate. No holiday exceptions or live table availability are inferred, and Google Places remains disabled.

Official opening-hour sources (reviewed 2026-10-14):

- [Aioli](https://aioli.com.pl/) — Świętokrzyska 18 and Chmielna 26 (two separate branches).
- [Mąka i Woda](https://makaiwoda.pl/) — Chmielna 13A and Duchnicka 3 (two distinct venues with different closing times).
- [U Szwejka](https://www.uszwejka.pl/) — Plac Konstytucji 1.
- [Banjaluka](https://www.banjaluka.pl/) — Szkolna 2/4 (Monday opening updated from unverified OSM 12:00 to venue-published 13:00).
- [Der Elefant](https://derelefant.com/pl/kontakt) — Plac Bankowy 1.
- [Kieliszki na Próżnej](https://kieliszkinaproznej.eatbu.com/?lang=pl) — Próżna 12; restaurant-operated hours list Sunday as closed.
- [ORZO](https://orzo.pl/pages/restauracje) — Plac Konstytucji 5 and Plac Konesera 5 (two branches; same published menu prices).
- [Stary Dom](https://restauracjastarydom.pl/zamow-online/) — Puławska 104/106.
- [Hard Rock Cafe Warsaw](https://cafe.hardrock.com/warsaw/pl/) — Złota 59.
- [360° Pizza](https://360pizza.pl/) — Chłodna 2/18 and Franciszka Klimczaka 5. **Both are provisional** because their [contact](https://360pizza.pl/kontakt-chlodna), [Klimczaka contact](https://360pizza.pl/kontakt), [Chłodna menu](https://360pizza.pl/360-menu-chlodna) and [Klimczaka gallery](https://360pizza.pl/galeria) pages show conflicting weekday closing times. The catalog uses only their conservative overlap and requests reconfirmation.
- [Akademia](https://restauracjaakademia.pl/kontakt/) — Różana 2; earlier Sunday closing.
- [Bazyliszek](https://bazyliszek.waw.pl/kontakt) — Rynek Starego Miasta 1/3.
- [Bella Napoli](https://bellanapoli.com.pl/centrum.html) — Kolejowa 47; later opening on weekends.
- [Byk Bar](https://bykbar.pl/kontakt/) — Rozbrat 8; earlier Monday closing.
- [Polka](https://warszawa.restauracjapolka.pl/) — Świętojańska 2.
- [Beef N' Pepper](https://beefandpepper.pl/menu/) — Nowogrodzka 47A; ends at midnight.
- [Capriccio](https://capriccio.makro.bar/?lang=pl) — Nowy Świat 36; later weekend closing.
- [Ciao Napoli](https://www.ciaonapoli.pl/) — Wąski Dunaj 4/6/8 (Friday and Saturday later closing).
- [Art Sushi](https://online.artsushi.pl/) — Nowogrodzka 56 (distinct weekend hours).

The sources establish normal *hours*, not a meal price. Some venues offer conditional lunch promotions or charge extra for drinks. A promotional menu amount is **not** converted into a guaranteed per-person total. Verified weekly hours can still be overridden by holidays and changes after the recorded check date. A published closing time of 24:00 is stored internally as 00:00 on the following calendar day (not as an invalid 24:00 clock), and an explicitly closed Sunday has no opening window.

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

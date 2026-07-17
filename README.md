# Shipment Route Prioritizer

Given a list of shipments - each with a mandatory delivery point and,
optionally, its own pickup point - and a fixed set of candidate driver
origins (warehouses the driver could start from), this project calls
Geoapify to get real driving distances/times between every stop, evaluates
every candidate origin on its own merits, and builds a prioritized route:
which origin to start from, and what order to visit every pickup/delivery in.

## How it works

1. Accept shipment data and a list of candidate origins. Each shipment has a
   `delivery` (address + optional time window) and, optionally, its own
   `pickup` (a specific address + optional time window) - a shipment's
   pickup is completely independent of the candidate origins; it's just
   another stop that must be visited before that shipment's delivery.
2. Geocode every origin/pickup/delivery address (Geoapify Geocoding API),
   then get a real drive distance/time matrix between all of them in one
   combined call (Geoapify Routing Matrix API).
3. Pass shipments + origins + that matrix to `generate_prioritized_route()`,
   which validates the data, generates one full candidate route per origin,
   and selects the best one.
4. Return the selected origin and its final, customer-friendly route (every
   candidate that was considered is also returned, for UI inspection - see
   "Origin selection" below).

Geoapify is only ever asked to compute *drive distances/times* - which
origin to start from and what order to visit stops in are decided entirely
by this project's own logic (below), never by a Geoapify route optimizer.

## Project structure

```
main.py                       # Runs the full pipeline end-to-end (CLI)
app.py                        # Optional visual demo UI (Streamlit) - same pipeline, no logic changes
config.py                     # Loads the Geoapify API key from the environment
sample_data.py                # Sample shipments + candidate origins to test with immediately
services/
    geoapify_service.py       # get_travel_matrix() - geocoding + Routing Matrix call
    route_service.py          # generate_prioritized_route() - validation + origin evaluation + prioritization
utils/
    time_utils.py             # Time parsing/formatting helpers
requirements.txt
.env / .env.example
```

There's no `models.py` - shipments and origins are plain dicts matching the
JSON shapes below, so a dataclass layer wouldn't add anything.

## Installation

```bash
pip install -r requirements.txt
```

## Environment variables

`.env` holds only the one secret this project needs - your Geoapify API key
(free at https://www.geoapify.com/). Copy `.env.example` to `.env` and fill
it in:

```
GEOAPIFY_API_KEY=your_geoapify_api_key_here
```

Everything else (API base URL, request timeout) is a fixed constant in
`config.py`, not an environment variable - it's part of the Geoapify API
itself, not something a deployment would need to change.

Shipment and origin data are **not** stored in config or `.env` either -
they're request data, supplied by the caller for each run (see
`sample_data.py` / `main.py`).

## Running the project

```bash
python main.py
```

This runs the pipeline against the sample shipments/origins in
`sample_data.py` and prints the selected origin and its route as JSON - not
every candidate origin that was considered (see "Origin selection" below for
where to inspect those).

## Visual demo UI (optional)

For a non-technical, visual way to see the whole pipeline in action,
including *why* one origin was picked over the others:

```bash
streamlit run app.py
```

This opens a dashboard with a sidebar action and five pages you switch
between instantly:

- **Sidebar** - one button, **Generate Prioritized Route**, which runs the
  exact same `get_travel_matrix()` -> `generate_prioritized_route()` pipeline
  as `main.py`. Clicking it jumps you straight to the results page.
- **🏭 Shipments** - a read-only record of the input data (from
  `sample_data.py`): the available origins (name + address), and every
  shipment's pickup address/window and delivery address/window. Not
  editable live by design - to test different data, edit that file and
  re-run.
- **📋 Prioritized Route** - the selected origin shown as an unnumbered
  "Start" row, followed by every pickup/delivery stop numbered from `001`,
  with a **Reason** column explaining why each stop landed where it did (e.g.
  `"Delivery: strict window 09:00-10:00"` or, for a genuine tie, `"...- tied
  on priority with SH001 (delivery); 850m from that stop won the tie"`). This
  reasoning is generated live from the real shipment data and the real
  Geoapify travel matrix for that run - see `_describe_event()` /
  `build_priority_reasons()` in `app.py`. It exists only for this UI; the
  core `generate_prioritized_route()` output has no reason field, matching
  the assignment's exact output format.
- **📊 Origin Comparison** - a comparison table of every candidate origin
  (total distance, total duration, time-window violations, constraint
  violations, a readable score, and which one was selected), plus an
  expander per origin showing its complete candidate route in the exact
  same format as the Prioritized Route page - this is where you can see why
  one origin won over the others.
- **🔍 Geoapify Response** - a table of every leg in the selected route (the
  real distance/time Geoapify returned for each consecutive stop-to-stop
  hop - these numbers sum to the totals on the Prioritized Route page), an
  expander per origin with that candidate's own processed leg table, and the
  actual, unmodified JSON Geoapify's Routing Matrix API returned (shown once
  - one combined API call already covers every origin, so that raw response
  is genuinely shared across all of them).
- **🗺️ Map** - every stop in the selected route plotted in visiting order
  (🟢 origin, 🟣 pickup, 🔵 delivery), connected by straight lines (not
  turn-by-turn road geometry - see "Notes / assumptions"), with a dropdown
  to switch the map to any other candidate origin's route instead.

`app.py` is a UI layer only - it imports and calls the same functions as
`main.py` and doesn't duplicate or change any business logic.

## Sample input

`sample_data.py` uses real, verified locations in Gurugram (Gurgaon),
Haryana. `AVAILABLE_ORIGINS` is the driver's fixed set of candidate starting
warehouses:

```python
AVAILABLE_ORIGINS = [
    {"name": "Warehouse A", "address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016"},
    {"name": "Warehouse B", "address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002"},
    {"name": "Warehouse C", "address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018"},
]
```

`SAMPLE_SHIPMENTS` covers every combination the requirements describe:

```python
SAMPLE_SHIPMENTS = [
    {"shipment_id": "SH001",
     "pickup": {"address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016",
                "time_window": {"end": "10:30"}},
     "delivery": {"address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002",
                  "time_window": {"start": "11:00", "end": "13:00"}}},
    # ... SH002-SH010, see sample_data.py
]
```

Between the 10 sample shipments:
- **Most (7/10) have their own pickup**, independent of `AVAILABLE_ORIGINS` -
  SH001, SH002, SH005, SH006, SH007, SH008, SH009.
- **A few (SH003, SH004, SH010) don't** - delivery-only, exactly like a
  single-location shipment.
- **Both windows** - SH001, SH005, SH006. **Only a delivery window** - SH002,
  SH003, SH009, SH010. **Only a pickup window** - SH008. **Neither window** -
  SH004 (no pickup at all) and SH007 (has a pickup address, but no window on
  either side).
- **The worked edge case**: SH005's own pickup address ("Vatika Chowk, Sector
  48, Sohna Road...") is *identical* to Warehouse C's address. Whichever
  origin ends up selected, SH005 always shows up as an ordinary `"pickup"`
  stop at that address - it only becomes the route's `"origin"` stop on the
  run where Warehouse C itself is the one actually selected.

## Sample output

```json
{
  "selected_origin": "Warehouse B (DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002)",
  "routes": {
    "001": {"pickup_address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002", "delivery_address": "HUDA City Centre, Sector 29, Gurugram, Haryana 122001", "shipment_id": "SH006", "type": "pickup"},
    "002": {"pickup_address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001", "delivery_address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018", "shipment_id": "SH008", "type": "pickup"},
    "003": {"pickup_address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002", "delivery_address": "HUDA City Centre, Sector 29, Gurugram, Haryana 122001", "shipment_id": "SH006", "type": "delivery"},
    "004": {"pickup_address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018", "delivery_address": "Galleria Market, DLF Phase 4, Gurugram, Haryana 122009", "shipment_id": "SH005", "type": "pickup"},
    "005": {"pickup_address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016", "delivery_address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002", "shipment_id": "SH001", "type": "pickup"},
    "006": {"pickup_address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016", "delivery_address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002", "shipment_id": "SH001", "type": "delivery"},
    "007": {"pickup_address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018", "delivery_address": "Galleria Market, DLF Phase 4, Gurugram, Haryana 122009", "shipment_id": "SH005", "type": "delivery"},
    "008": {"pickup_address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002", "delivery_address": "Kingdom of Dreams, Sector 29, Gurugram, Haryana 122001", "shipment_id": "SH007", "type": "pickup"},
    "009": {"pickup_address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002", "delivery_address": "Kingdom of Dreams, Sector 29, Gurugram, Haryana 122001", "shipment_id": "SH007", "type": "delivery"},
    "010": {"pickup_address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001", "delivery_address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002", "shipment_id": "SH002", "type": "pickup"},
    "011": {"pickup_address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001", "delivery_address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002", "shipment_id": "SH002", "type": "delivery"},
    "012": {"pickup_address": null, "delivery_address": "MGF Metropolitan Mall, MG Road, Sector 28, Gurugram, Haryana 122002", "shipment_id": "SH003", "type": "delivery"},
    "013": {"pickup_address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002", "delivery_address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002", "shipment_id": "SH009", "type": "pickup"},
    "014": {"pickup_address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002", "delivery_address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002", "shipment_id": "SH009", "type": "delivery"},
    "015": {"pickup_address": null, "delivery_address": "Sohna Road, Sector 49, Gurugram, Haryana 122018", "shipment_id": "SH010", "type": "delivery"},
    "016": {"pickup_address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001", "delivery_address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018", "shipment_id": "SH008", "type": "delivery"},
    "017": {"pickup_address": null, "delivery_address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001", "shipment_id": "SH004", "type": "delivery"}
  },
  "total_miles": 93.18,
  "total_duration": "3h"
}
```

(Re-running this may show a slightly different `total_miles`/`total_duration`,
and even a different `selected_origin` - Geoapify's `drive` mode factors in
live traffic, so the same request can get marginally different distance/time
estimates between calls, and the origin comparison is sensitive to those
numbers when candidates are close. The stop *order within* a given origin's
route is fully deterministic given the same input data and travel numbers.)

Here Warehouse B won because all three candidate origins had zero time-window
violations, so the tie went to whichever had the lowest total travel time
(see "Origin selection" below for the exact comparison rule).

Note that `"selected_origin"` is the only place `"origin"` means anything in
this output - it's metadata, not a numbered stop, and `"001"` is the first
actual pickup/delivery stop. Every stop shows **both** `"pickup_address"` and
`"delivery_address"` for its shipment regardless of `"type"` - e.g. SH006's
`"001"` (pickup) and `"003"` (delivery) both carry the same pair of
addresses; `"type"` says which action happens at *that* stop, not which
address to hide. The only `null` case is `"pickup_address"` for a shipment
that has no pickup at all (SH003/SH004/SH010 above) - a shipment never has an
"origin" field either way, only addresses.

On invalid shipment or origin data:

```json
{
  "error": "Invalid shipment data",
  "details": [
    {"shipment_id": "SH003", "issue": "Delivery window: End time is earlier than start time"}
  ]
}
```

On a Geoapify failure (bad API key, network error, no usable travel data,
etc.), a valid shipment with no usable travel data for one of its required
points, or every candidate origin being unroutable:

```json
{"error": "Unable to generate route"}
```

## Origin selection

The driver has a fixed list of candidate starting warehouses
(`AVAILABLE_ORIGINS`) - the system never just picks the nearest one. Instead,
`generate_prioritized_route()` (`services/route_service.py`) evaluates every
candidate independently (`_evaluate_origin()`):

1. Build a full candidate route as if the driver started there, using the
   exact same prioritization rules described below (the origin is simply
   the route's starting "current position" for the very first distance
   tiebreak).
2. Simulate feasibility (`_simulate_feasibility()`): starting from a fixed
   assumed departure time (`DEFAULT_DEPARTURE_TIME = "08:00"`), walk the
   route accumulating real Geoapify travel time leg by leg. Arriving before a
   stop's `start` just means waiting (no violation); arriving after its
   `end` deadline is recorded as a violation, and the driver's clock stays
   late for every stop after it.
3. Total the real travel distance/time for that candidate (`_compute_totals`,
   including the origin-to-first-stop leg, even though the origin itself
   isn't a numbered stop in the output - see "Sample output" above).

Once every origin has a candidate, the best one is selected by a simple,
deterministic, ascending sort on:

1. **Time-window violations** - deadlines missed (zero is best).
2. **Constraint violations** - today this is always equal to #1, since a
   missed deadline is the only constraint type modeled; it's tracked as a
   separate count so a future second constraint type (e.g. a max
   driving-hours cap) only needs to append to the same violations list, not
   reshape this comparison.
3. **Total travel time** - lowest wins.
4. **Total travel distance** - lowest wins.

Candidates are evaluated in `AVAILABLE_ORIGINS`'s order, and ties on all four
numbers fall back to that declaration order (Python's `min()` is stable) -
deterministic without an explicit extra tiebreak key.

`generate_prioritized_route()`'s return value includes `"candidates"`: every
origin's own route, totals, and violations, plus which one was `"selected"`.
`main.py` strips this before printing (the terminal shows only the selected
origin + route); `app.py`'s Origin Comparison page uses it to let you inspect
every candidate.

## Business rules for prioritization

A shipment with a `pickup` contributes **two independent events** to the
ordering - a pickup and a delivery - each classified by its own time window;
a shipment with no `pickup` contributes only a delivery event. Events are
computed once per run (not once per candidate origin) and reused across
every candidate, so origins are compared on identical urgency classification
- only the distance-based tiebreak reference point differs. Events are
classified into 3 groups (`services/route_service.py`, `_classify_window()`):

1. **Group 0 - Time-critical** - any event with a deadline (an `end`),
   whether or not it also has a `start`. Strict-window and deadline-only
   events are merged onto **one shared timeline**, rather than treating "has
   a full window" as always more urgent than "has a deadline" regardless of
   timing. Sorted by:
   1. **Anchor time** - the `start` if present, otherwise the `end`.
   2. **Window duration** - tiebreak for two events sharing the same anchor
      (tighter window = more urgent).
   3. **Travel distance from whichever stop comes right before it** (closer
      first) - see "Tiebreak" below.
2. **Group 1 - Start-only** - has a `start` but no `end`. Always after every
   Group 0 event. Sorted by start time, then distance.
3. **Group 2 - No constraint** - no time window at all. Always last, sorted
   by distance only.

**Inherited pickup urgency.** A pickup with no window of its own still has
to happen early enough for its *own delivery's* deadline to be reachable -
so if a pickup has no window, it borrows its delivery's window for
classification purposes only (its actual, displayed window, and the window
used for feasibility checking, is still "none"). Without this, an
unconstrained pickup would always sort into Group 2 and could land after its
own delivery's deadline has effectively already passed (SH007 in the sample
above is exactly this case).

**Precedence.** A pickup event must always come before its own shipment's
delivery event. `_prioritize_events()` enforces this directly while building
the sequence - a delivery is only ever considered "ready" to be picked once
its own pickup has already been placed - rather than sorting everything
first and patching the order afterwards.

**Tiebreak.** Same-priority candidates are tie-broken by real travel distance
from whichever stop was placed immediately before it in the route being
built - and since every candidate route always starts from a real origin,
this applies uniformly from the very first stop onward: among tied
candidates, whichever one is physically closest to wherever the driver
currently is (starting at the selected origin) goes next.

Putting it together, `_prioritize_events()` builds the route one stop at a
time: among all precedence-ready events, take the most urgent group/anchor/
duration, break any tie by distance from the last-placed stop (starting from
the origin), place it, and repeat.

## Notes / assumptions

- `total_miles` / `total_duration` are an exact sum of real travel
  distance/time over the selected origin's sequence, including the
  origin-to-first-stop leg (no return-to-origin leg at the end).
- Feasibility checking assumes a single fixed driver departure time from the
  selected origin (`DEFAULT_DEPARTURE_TIME = "08:00"`) for every run/origin -
  not derived dynamically per shipment set, and not configurable via the CLI
  or UI. No loading/unloading dwell time is modeled at any stop.
- If an origin, pickup, or delivery address can't be geocoded (e.g. it
  doesn't resolve to a real place), that point is skipped when building the
  travel matrix so one bad address doesn't fail the whole request. A
  *valid* shipment left with no usable travel data for one of its required
  points makes the whole run return `{"error": "Unable to generate route"}`
  (this check doesn't depend on which origin is chosen - a bad shipment
  address is unroutable regardless). An *origin* left with no usable travel
  data is instead just dropped from candidate evaluation; if every origin
  ends up unroutable, the same error is returned. Field-level validation
  (missing `shipment_id`/delivery address, bad time formats, a pickup given
  without an address, a pickup deadline scheduled at or after its own
  delivery deadline, missing/duplicate origin names) still catches
  structurally invalid data up front; it does not verify that an address is
  a real, resolvable location.
- The nearest-previous-stop tiebreak and the precedence-aware greedy build
  are a simple, explainable heuristic - not a provably optimal solver. Origin
  selection is a plain multi-criteria sort, not a weighted "best fit" score -
  that tradeoff (auditable rules over a black-box optimizer) matches the
  rest of this project's design, and keeps the logic readable rather than
  reaching for a full VRP solver for what's fundamentally a prioritization
  exercise.

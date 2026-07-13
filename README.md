# Shipment Route Prioritizer

Given a list of shipments - each with its own delivery point, and optionally
its own pickup point (a specific warehouse origin) - this project calls
Geoapify to get real driving distances/times between every stop, then builds
a prioritized delivery route: what order to visit every pickup/delivery in.

## How it works

1. Accept shipment data. Each shipment has a `delivery` (address + optional
   time window) and, optionally, its own `pickup` (a specific warehouse
   address + optional time window) - different shipments can have different
   pickup origins; there's no single shared warehouse.
2. Geocode every pickup/delivery address (Geoapify Geocoding API), then get
   a real drive distance/time matrix between all of them (Geoapify Routing
   Matrix API).
3. Pass shipments + that matrix to `generate_prioritized_route()`, which
   validates the data and prioritizes every stop.
4. Return the final, customer-friendly route.

Geoapify is only ever asked to compute *drive distances/times* - what order
to visit stops in is decided entirely by this project's own logic (below),
not by a Geoapify route optimizer.

## Project structure

```
main.py                       # Runs the full pipeline end-to-end (CLI)
app.py                        # Optional visual demo UI (Streamlit) - same pipeline, no logic changes
config.py                     # Loads the Geoapify API key from the environment
sample_data.py                # Sample shipments to test with immediately
services/
    geoapify_service.py       # get_travel_matrix() - geocoding + Routing Matrix call
    route_service.py          # generate_prioritized_route() - validation + prioritization
utils/
    time_utils.py             # Time parsing/formatting helpers
requirements.txt
.env / .env.example
```

There's no `models.py` - shipments are plain dicts matching the JSON shape
below, so a dataclass layer wouldn't add anything.

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

Shipment data is **not** stored in config or `.env` either - it's request
data, supplied by the caller for each run (see `sample_data.py` / `main.py`).

## Running the project

```bash
python main.py
```

This runs the pipeline against the sample shipments in `sample_data.py` and
prints the resulting route as JSON.

## Visual demo UI (optional)

For a non-technical, visual way to see the whole pipeline in action:

```bash
streamlit run app.py
```

This opens a dashboard with a sidebar action and four pages you switch
between instantly:

- **Sidebar** - one button, **Generate Prioritized Route**, which runs the
  exact same `get_travel_matrix()` -> `generate_prioritized_route()` pipeline
  as `main.py`. Clicking it jumps you straight to the results page.
- **🏭 Shipments** - a read-only record of the input data (from
  `sample_data.py`): every shipment's pickup origin/address/window and
  delivery address/window. Not editable live by design - to test different
  data, edit that file and re-run.
- **📋 Prioritized Route** - the final stop order (pickups and deliveries
  interleaved), with a **Reason** column explaining why each stop landed
  where it did (e.g. `"Delivery: strict window 09:00-10:00"` or, for a
  genuine tie, `"...- tied on priority with SH001 (delivery); 850m from that
  stop won the tie"`). This reasoning is generated live from the real
  shipment data and the real Geoapify travel matrix for that run - see
  `_describe_event()` / `build_priority_reasons()` in `app.py`. It exists
  only for this UI; the core `generate_prioritized_route()` output has no
  reason field, matching the assignment's exact output format. A shipment
  with its own pickup contributes two stops (pickup + delivery), so the
  stop count here is naturally higher than the shipment count - both pages
  call this out explicitly to avoid confusion.
- **🔍 Geoapify Response** - a table of every leg in the final route (the
  real distance/time Geoapify returned for each consecutive stop-to-stop
  hop - these are exactly the numbers that sum to the totals on the
  Prioritized Route page), plus the actual, unmodified JSON Geoapify's
  Routing Matrix API returned, in an expander.
- **🗺️ Map** - every stop plotted in visiting order (🟣 pickup, 🔵
  delivery), connected by straight lines (not turn-by-turn road geometry -
  see "Notes / assumptions").

`app.py` is a UI layer only - it imports and calls the same functions as
`main.py` and doesn't duplicate or change any business logic.

## Sample input

`sample_data.py` uses real, verified locations in Gurugram (Gurgaon),
Haryana. Shipments cover every combination the requirements describe:

```python
SAMPLE_SHIPMENTS = [
    {"shipment_id": "SH001",
     "pickup": {"origin": "Warehouse Udyog Vihar",
                "address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016",
                "time_window": {"end": "10:30"}},
     "delivery": {"address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002",
                  "time_window": {"start": "11:00", "end": "13:00"}}},
    {"shipment_id": "SH002",
     "delivery": {"address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002",
                  "time_window": {"start": "14:00", "end": "17:00"}}},
    # ... SH003-SH010, see sample_data.py
]
```

Between the 10 sample shipments:
- **Both windows** - SH001, SH005 (each picks up from a *different*
  warehouse - "Warehouse Udyog Vihar" and "Warehouse Sohna Road").
- **Only a delivery window** - SH002, SH003, SH006, SH009, SH010 (no
  `pickup` at all - delivery-only, exactly like a single-location shipment).
- **Only a pickup window** - SH008 (a third warehouse, "Warehouse Sector
  14"; its delivery has no window).
- **Neither window** - SH004 (no pickup, no delivery window) and SH007 (has
  a `pickup` address/origin - a fourth warehouse - but no window on either
  side).

## Sample output

```json
{
  "routes": {
    "001": {"address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001", "shipment_id": "SH008", "type": "pickup", "origin": "Warehouse Sector 14"},
    "002": {"address": "HUDA City Centre, Sector 29, Gurugram, Haryana 122001", "shipment_id": "SH006", "type": "delivery"},
    "003": {"address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018", "shipment_id": "SH005", "type": "pickup", "origin": "Warehouse Sohna Road"},
    "004": {"address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016", "shipment_id": "SH001", "type": "pickup", "origin": "Warehouse Udyog Vihar"},
    "005": {"address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002", "shipment_id": "SH001", "type": "delivery"},
    "006": {"address": "Galleria Market, DLF Phase 4, Gurugram, Haryana 122009", "shipment_id": "SH005", "type": "delivery"},
    "007": {"address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002", "shipment_id": "SH007", "type": "pickup", "origin": "Warehouse DLF"},
    "008": {"address": "Kingdom of Dreams, Sector 29, Gurugram, Haryana 122001", "shipment_id": "SH007", "type": "delivery"},
    "009": {"address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002", "shipment_id": "SH002", "type": "delivery"},
    "010": {"address": "MGF Metropolitan Mall, MG Road, Sector 28, Gurugram, Haryana 122002", "shipment_id": "SH003", "type": "delivery"},
    "011": {"address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002", "shipment_id": "SH009", "type": "delivery"},
    "012": {"address": "Sohna Road, Sector 49, Gurugram, Haryana 122018", "shipment_id": "SH010", "type": "delivery"},
    "013": {"address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018", "shipment_id": "SH008", "type": "delivery"},
    "014": {"address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001", "shipment_id": "SH004", "type": "delivery"}
  },
  "total_miles": 79.09,
  "total_duration": "2h 32m"
}
```

(Re-running this may show a slightly different `total_miles`/`total_duration`
- Geoapify's `drive` mode factors in live traffic, so the same request can
get marginally different distance/time estimates between calls. The stop
*order* itself is fully deterministic given the same input data.)

Why this order (see "Business rules" below for the full algorithm): SH008's
pickup deadline (09:00) is the earliest anchor of any stop, so it goes
first - even though its own delivery has no window at all. SH006's
09:00-10:00 delivery window, SH005's pickup window (09:30-10:30), and
SH001's pickup deadline (10:30) follow in anchor order; each pickup is
placed as soon as it's the most urgent *ready* stop, but always before its
own delivery. SH005 and SH001's deliveries then tie on window
(11:00-13:00), broken by real travel distance from whichever stop was
placed right before them. SH007's pickup has no window of its own, but its
delivery has a 12:30 deadline - so the pickup inherits that urgency and both
get scheduled right after the SH001/SH005 tie, ahead of SH002's 14:00
window. Everything else follows the same anchor-then-duration-then-distance
rule, with SH010 (start-only) and SH008/SH004's remaining no-constraint
stops last regardless of their own start times, since none of them has
deadline pressure.

On invalid shipment data:

```json
{
  "error": "Invalid shipment data",
  "details": [
    {"shipment_id": "SH003", "issue": "Delivery window: End time is earlier than start time"}
  ]
}
```

On a Geoapify failure (bad API key, network error, no usable travel data,
etc.), or a valid shipment with no usable travel data for one of its
required points:

```json
{"error": "Unable to generate route"}
```

## Business rules for prioritization

A shipment with a `pickup` contributes **two independent events** to the
ordering - a pickup and a delivery - each classified by its own time window;
a shipment with no `pickup` contributes only a delivery event, exactly like
the original single-location design. Events are classified into 3 groups
(`services/route_service.py`, `_classify_window()`):

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
classification purposes only (its actual, displayed window is still "none").
Without this, an unconstrained pickup would always sort into Group 2 and
could land after its own delivery's deadline has effectively already passed
(SH007 in the sample above is exactly this case).

**Precedence.** A pickup event must always come before its own shipment's
delivery event. `_prioritize_events()` enforces this directly while building
the sequence - a delivery is only ever considered "ready" to be picked once
its own pickup has already been placed - rather than sorting everything
first and patching the order afterwards.

**Tiebreak.** The original single-warehouse design tie-broke same-window
shipments by "distance from the warehouse." With several different pickup
origins now in play, there's no longer one shared point to measure "closer"
from - so the tiebreak here is real travel distance from whichever stop was
placed immediately before it in the route being built (falling back to
`shipment_id` for the very first stop, when there's no "current position"
yet). This is a direct generalization of the original rule: among tied
candidates, whichever one is physically closest to wherever the driver
currently is goes next.

Putting it together, `_prioritize_events()` builds the route one stop at a
time: among all precedence-ready events, take the most urgent group/anchor/
duration, break any tie by distance from the last-placed stop, place it, and
repeat.

## Notes / assumptions

- `total_miles` / `total_duration` are an exact sum of real travel
  distance/time over the sequence this project produces (no return-to-origin
  leg, since there's no single shared warehouse to return to).
- If a pickup or delivery address can't be geocoded (e.g. it doesn't resolve
  to a real place), that point is skipped when building the travel matrix so
  one bad address doesn't fail the whole request. If a *valid* shipment ends
  up with no usable travel data for one of its required points,
  `generate_prioritized_route()` returns `{"error": "Unable to generate
  route"}` rather than silently mis-prioritizing it. Field-level validation
  (missing `shipment_id`/delivery address, bad time formats, a pickup given
  without an address, a pickup deadline scheduled at or after its own
  delivery deadline) still catches structurally invalid data up front; it
  does not verify that an address is a real, resolvable location.
- The nearest-previous-stop tiebreak and the precedence-aware greedy build
  are a simple, explainable heuristic - not a provably optimal solver. That
  tradeoff (auditable rules over a black-box optimizer) matches the rest of
  this project's design, and keeps the logic readable rather than reaching
  for a full VRP solver for what's fundamentally a prioritization exercise.

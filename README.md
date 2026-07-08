# Shipment Route Prioritizer

Given a warehouse origin and a list of shipments, this project calls the
[Geoapify Route Planner API](https://apidocs.geoapify.com/docs/route-planner/)
to get real driving distances/times, then builds a prioritized delivery route
based on each shipment's delivery time window.

## How it works

1. Accept shipment data and the origin warehouse address.
2. Geocode the warehouse and every shipment address (Geoapify Geocoding API).
3. Build the Route Planner request payload and call the Geoapify API.
4. Receive the raw JSON response.
5. Pass shipments + response to `generate_prioritized_route()`, which validates
   the data and prioritizes the shipments.
6. Return the final, customer-friendly route.

Geoapify is only ever asked to compute *drive distances/times* between stops.
The actual delivery order is decided by our own business rules (below), not
by Geoapify's route optimizer.

## Project structure

```
main.py                       # Runs the full pipeline end-to-end (CLI)
app.py                        # Optional visual demo UI (Streamlit) - same pipeline, no logic changes
config.py                     # Loads the Geoapify API key from the environment
sample_data.py                # Sample shipments + origin address to test with immediately
services/
    geoapify_service.py       # get_geoapify_route() - geocoding + Route Planner call
    route_service.py          # generate_prioritized_route() - validation + prioritization
utils/
    time_utils.py             # Time parsing/formatting helpers
requirements.txt
.env / .env.example
```

There's no `models.py` - shipments are plain dicts matching the JSON shape
given in the assignment, so a dataclass layer wouldn't add anything.

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

The origin warehouse address is **not** stored in config or `.env` either.
It's request data, supplied by the caller alongside the shipments (see
`sample_data.py` / `main.py`), since a real system could serve more than one
warehouse.

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
  exact same `get_geoapify_route()` -> `generate_prioritized_route()`
  pipeline as `main.py`. Clicking it jumps you straight to the results page.
- **🏭 Warehouse & Deliveries** - a read-only record of the input data (from
  `sample_data.py`). Not editable live by design - to test different data,
  edit that file and re-run.
- **📋 Prioritized Route** - the final stop order, with a **Priority** number
  and a **Reason** column explaining why each shipment landed where it did
  (e.g. `"Strict window 09:00-10:00"` or, for a genuine tie, `"...- same as
  SH001, farther stop wins the tie"`). This reasoning is generated live from
  the real shipment data and the real Geoapify distances for that run - see
  `_describe_shipment()` / `build_priority_reasons()` in `app.py`. It exists
  only for this UI; the core `generate_prioritized_route()` output has no
  reason field, matching the assignment's exact output format.
- **🔍 Geoapify Response** - a per-shipment breakdown of priority category and
  Geoapify-computed distance, plus the raw JSON response in an expander.
- **🗺️ Map** - the actual driving route (from Geoapify's route geometry),
  with numbered pins in delivery order (🟢 warehouse start, 🔵 stops, 🔴
  warehouse end).

`app.py` is a UI layer only - it imports and calls the same functions as
`main.py` and doesn't duplicate or change any business logic.

## Sample input

`sample_data.py` uses real, verified locations in Gurugram (Gurgaon),
Haryana, covering every priority rule - including a 3-way tie on the same
2-hour window (SH001/SH005/SH009):

```python
SAMPLE_ORIGIN_ADDRESS = "Udyog Vihar Phase 1, Gurugram, Haryana 122016"

SAMPLE_SHIPMENTS = [
    {"shipment_id": "SH001", "address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002",
     "time_window": {"start": "11:00", "end": "13:00"}},
    {"shipment_id": "SH002", "address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002",
     "time_window": {"start": "14:00", "end": "17:00"}},
    {"shipment_id": "SH003", "address": "MGF Metropolitan Mall, MG Road, Sector 28, Gurugram, Haryana 122002",
     "time_window": {"end": "15:00"}},
    {"shipment_id": "SH004", "address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001"},
    {"shipment_id": "SH005", "address": "Galleria Market, DLF Phase 4, Gurugram, Haryana 122009",
     "time_window": {"start": "11:00", "end": "13:00"}},
    {"shipment_id": "SH006", "address": "HUDA City Centre, Sector 29, Gurugram, Haryana 122001",
     "time_window": {"start": "09:00", "end": "10:00"}},
    {"shipment_id": "SH007", "address": "Kingdom of Dreams, Sector 29, Gurugram, Haryana 122001",
     "time_window": {"end": "12:30"}},
    {"shipment_id": "SH008", "address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018"},
    {"shipment_id": "SH009", "address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002",
     "time_window": {"start": "16:00", "end": "18:00"}},
    {"shipment_id": "SH010", "address": "Sohna Road, Sector 49, Gurugram, Haryana 122018",
     "time_window": {"start": "08:00"}},
]
```

## Sample output

```json
{
  "routes": {
    "000": {"address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016", "shipment_id": "", "type": "origin"},
    "001": {"address": "HUDA City Centre, Sector 29, Gurugram, Haryana 122001", "shipment_id": "SH006", "type": "drop"},
    "002": {"address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002", "shipment_id": "SH001", "type": "drop"},
    "003": {"address": "Galleria Market, DLF Phase 4, Gurugram, Haryana 122009", "shipment_id": "SH005", "type": "drop"},
    "004": {"address": "Kingdom of Dreams, Sector 29, Gurugram, Haryana 122001", "shipment_id": "SH007", "type": "drop"},
    "005": {"address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002", "shipment_id": "SH002", "type": "drop"},
    "006": {"address": "MGF Metropolitan Mall, MG Road, Sector 28, Gurugram, Haryana 122002", "shipment_id": "SH003", "type": "drop"},
    "007": {"address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002", "shipment_id": "SH009", "type": "drop"},
    "008": {"address": "Sohna Road, Sector 49, Gurugram, Haryana 122018", "shipment_id": "SH010", "type": "drop"},
    "009": {"address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001", "shipment_id": "SH004", "type": "drop"},
    "010": {"address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018", "shipment_id": "SH008", "type": "drop"},
    "011": {"address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016", "shipment_id": "", "type": "end"}
  },
  "total_miles": 33.92,
  "total_duration": "1h 12m"
}
```

Why this order (see "Business rules" below for the full algorithm):
SH006's 09:00-10:00 window is the earliest, so it goes first. SH001, SH005,
and SH009 all share a 2-hour window duration and get sorted by their actual
start time, then SH001/SH005 (both starting 11:00) are a genuine tie broken
by Geoapify distance (SH001 is closer). SH007's 12:30 deadline slots in
between SH005 (11:00 start) and SH002 (14:00 start) - a deadline can be more
urgent than a window that simply starts later, so the two are merged onto
one timeline rather than treating "has a window" as always beating "has a
deadline". SH010 (start-only, no deadline) and SH004/SH008 (no constraint)
come last regardless of their own start times, since neither has any
deadline pressure.

Note: occasionally re-running this will return `{"error": "Unable to
generate route"}` instead - that's the live Geoapify optimizer flakiness
documented in "Notes / assumptions" below, not a bug here. Just run it again.

On invalid shipment data:

```json
{
  "error": "Invalid shipment data",
  "details": [
    {"shipment_id": "SH003", "issue": "End time is earlier than start time"}
  ]
}
```

On a Geoapify failure (bad API key, network error, no usable route, etc.):

```json
{"error": "Unable to generate route"}
```

## Business rules for prioritization

Shipments are sorted into 3 groups (`services/route_service.py`, `_classify()`):

1. **Group 0 - Time-critical** - any shipment with a deadline (an `end`),
   whether or not it also has a `start`. Strict-window shipments
   (`start`+`end`) and deadline-only shipments (`end` only) are merged onto
   **one shared timeline** here, rather than treating "has a full window" as
   always more urgent than "has a deadline" regardless of timing - a 12:30
   deadline is genuinely more urgent than a window that doesn't even start
   until 14:00, and a rigid window-group-before-deadline-group split gets
   that backwards. Sorted by:
   1. **Anchor time** - the `start` if present (a window's earliest useful
      arrival), otherwise the `end` (a deadline's only reference point).
   2. **Window duration** - tiebreak for two shipments sharing the same
      anchor (tighter window = more urgent). Deadline-only shipments have no
      duration, so they always lose this tiebreak to an actual windowed
      shipment at the same anchor time.
   3. **Geoapify route distance** - the assignment's "same time window"
      tiebreak rule (closer stop first).
2. **Group 1 - Start-only** - has a `start` but no `end` ("don't deliver
   before X"). No deadline pressure at all, so always after every Group 0
   shipment regardless of how early its start is. Sorted by start time, then
   distance.
3. **Group 2 - No constraint** - no `time_window` at all. Always last,
   sorted by distance only.

This design was reached by working backwards from a worked example: a rigid
"all strict windows, then all deadlines, then start-only, then none" grouping
(an earlier version of this project) produces a wrong-feeling order whenever
a tight deadline falls earlier in the day than a wide window - the merged
Group 0 timeline above fixes that while keeping the same 4 raw time-window
shapes the assignment describes.

## Notes / assumptions

- `total_miles` / `total_duration` reflect Geoapify's own computed route
  totals for visiting every stop from the warehouse. Since business rules
  (not Geoapify) decide the final delivery order, these totals are a close
  real-world estimate rather than an exact recomputation for the reordered
  sequence - recomputing a brand new route for every possible order was
  considered out of scope for this assignment.
- If a shipment's address can't be geocoded (e.g. it doesn't resolve to a
  real place), that shipment is skipped when calling Geoapify so one bad
  address doesn't fail the whole request. Field-level validation (missing
  `shipment_id`/`address`, bad time formats) still catches structurally
  invalid shipments; it does not verify that an address is a real, resolvable
  location.
- Geoapify's live Route Planner has occasionally been observed to silently
  drop a job from its solution (missing from `properties.actions`) without
  reporting anything in `properties.issues`. `generate_prioritized_route()`
  checks that every validated shipment actually has a distance in the
  response and returns `{"error": "Unable to generate route"}` if one is
  missing, rather than defaulting its tiebreak distance to 0 (which would
  silently make it look like the closest stop).

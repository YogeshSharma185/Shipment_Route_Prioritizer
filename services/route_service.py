"""Turns shipment data + a Geoapify travel-time matrix into a prioritized,
customer-friendly route. Responsibilities:
  1. Validate the shipment and origin data (ids, addresses, time windows).
  2. Evaluate every candidate driver origin independently, prioritizing every
     pickup/delivery stop for each using the business rules below.
  3. Compare all candidate routes and select the best one.
  4. Build the final "routes" output for the selected origin.

Output shape - the selected origin is metadata, not a numbered stop:
  {
    "selected_origin": "Warehouse B (DLF Cyber Greens, Sector 25A, ...)",
    "routes": {
        "001": {"pickup_address": "...", "delivery_address": "...", "shipment_id": "SH006", "type": "pickup"},
        "002": {"pickup_address": "...", "delivery_address": "...", "shipment_id": "SH006", "type": "delivery"},
        ...
    },
    "total_miles": ..., "total_duration": ..., "candidates": [...],
  }
Every stop shows both "pickup_address" and "delivery_address" for its
shipment, regardless of "type" - like a delivery rider who sees both the
pickup and drop-off address at every step of one order, not just the leg
they're currently on. "type" says which action happens at *this* stop, not
which address to hide. The only null case is "pickup_address" for a
shipment that has no pickup at all (delivery-only).

Shipment shape - note a shipment never has an "origin" field, only
addresses (a shipment doesn't choose a warehouse; the driver does):
  {
    "shipment_id": "SH001",
    "pickup": {                                        # optional
        "address": "Udyog Vihar Phase 1, ...",
        "time_window": {"start": "09:00", "end": "10:00"},  # optional
    },
    "delivery": {
        "address": "123 Main Street",
        "time_window": {"start": "11:00", "end": "13:00"},  # optional
    },
  }

Origin shape (a candidate starting warehouse for the driver - the only place
"origin" means anything - see sample_data.AVAILABLE_ORIGINS):
  {"name": "Warehouse A", "address": "Udyog Vihar Phase 1, ..."}

A shipment's own "pickup" is completely independent of AVAILABLE_ORIGINS -
it's just another stop that must be visited before that shipment's delivery.
A pickup address may even coincide with one of the driver's candidate
origins (e.g. two shipments could each pick up from a different warehouse
that's also in AVAILABLE_ORIGINS); it's still only ever treated as an
ordinary pickup stop, never as the selected origin, unless that same
warehouse is the one actually chosen to start the route from. A shipment
with no "pickup" at all is delivery-only. Both time_window fields are
independently optional, so a shipment may have neither, either, or both.

Business rules - a shipment with a pickup contributes two independent
*events* to the ordering (a pickup and a delivery), each classified by its
own time window:

  Group 0 - TIME_CRITICAL: any event with a deadline (an "end"), whether or
  not it also has a "start" (strict windows and deadline-only events share
  one timeline, rather than treating "has a full window" as always more
  urgent than "has a deadline" regardless of timing).
  Group 1 - START_ONLY: has a start but no end.
  Group 2 - NO_WINDOW: no time window at all.

Within a tied group, the tiebreak is real travel distance from whichever
stop was placed immediately before it in the route being built (the closer
one wins) - see _prioritize_events. Every candidate route always starts from
a real origin, so this applies uniformly from the very first stop onward:
even the first tie is broken by distance from the selected origin, not by
falling back to an arbitrary ordering.

On top of priority, a pickup event must always come before its own
shipment's delivery event. _prioritize_events enforces this directly (by
only ever considering a delivery "ready" once its own pickup has already
been placed) rather than sorting first and patching precedence afterwards -
simpler to read, and impossible to get out of order by construction.

Origin selection - every available origin is evaluated independently
(_evaluate_origin): a full candidate route is generated as if the driver
started there, a fixed-departure-time feasibility simulation checks whether
every pickup/delivery deadline can realistically be met, and the real total
travel distance/time is computed. The best candidate is then chosen by a
simple, deterministic, ascending sort on:
  1. time_window_violations - deadlines missed (zero is best)
  2. constraint_violations  - total constraint violations (today this is
     always equal to time_window_violations, since deadline-miss is the only
     constraint type modeled; kept as a separate count so a future second
     constraint type - e.g. a max driving-hours cap - only needs to append to
     the same violations list, not reshape this comparison)
  3. total_time     - lowest real travel time wins
  4. total_distance - lowest real travel distance wins
Candidates are built by iterating origins in the order given (the same order
as sample_data.AVAILABLE_ORIGINS), and Python's min() is stable, so an exact
tie on all four numbers is broken by origin declaration order - deterministic
without needing an explicit extra tiebreak key.

Feasibility simulation assumes a fixed driver departure time from the
selected origin (DEFAULT_DEPARTURE_TIME below) - the same simple assumption
for every origin/run, not derived dynamically. No loading/unloading dwell
time is modeled at any stop, consistent with the rest of this project's
"readable, explainable heuristic" design rather than a full arrival-clock
simulator with real-world logistics constraints.
"""
from utils.time_utils import (
    format_clock,
    meters_to_miles,
    parse_time,
    seconds_since_midnight,
    seconds_to_duration_str,
)

TIME_CRITICAL, START_ONLY, NO_WINDOW = range(3)
NO_DURATION = 24 * 3600 + 1  # bigger than any possible same-day window

PICKUP, DELIVERY = "pickup", "delivery"

DEFAULT_DEPARTURE_TIME = "08:00"  # fixed assumed departure time from the selected origin


def generate_prioritized_route(shipments, travel, skipped_keys, origins):
    """Validate the shipments and origins, evaluate every candidate origin,
    and return the best route along with every candidate for inspection.

    travel/skipped_keys are exactly what geoapify_service.get_travel_matrix()
    returns for these same shipments and origins.

    On any validation failure, returns {"error": ..., "details": [...]}.
    On missing travel data, or any unexpected failure, returns
    {"error": "Unable to generate route"} instead of raising.
    """
    try:
        valid_shipments, shipment_errors = _validate_shipments(shipments)
        origin_errors = _validate_origins(origins)
        errors = shipment_errors + origin_errors
        if errors:
            return {"error": "Invalid shipment data", "details": errors}

        if _has_missing_travel_data(valid_shipments, skipped_keys):
            # Mirrors the original project's stance: one unresolvable address
            # shouldn't fail validation, but a *valid* shipment with no usable
            # travel data can't be routed, so it's an "Unable to generate
            # route" case rather than silently dropping or mis-prioritizing it.
            # This check is global/origin-independent - a shipment with a bad
            # address is unroutable under any origin choice.
            return {"error": "Unable to generate route"}

        valid_origins = [
            origin for origin in origins if ("origin", origin["name"]) not in skipped_keys
        ]
        if not valid_origins:
            return {"error": "Unable to generate route"}

        events = _expand_events(valid_shipments)

        candidates = [_evaluate_origin(origin, events, travel) for origin in valid_origins]
        best = min(
            candidates,
            key=lambda c: (
                c["time_window_violations"],
                c["constraint_violations"],
                c["total_time"],
                c["total_distance"],
            ),
        )

        return {
            "selected_origin": f"{best['origin']['name']} ({best['origin']['address']})",
            "routes": best["routes"],
            "total_miles": meters_to_miles(best["total_distance"]),
            "total_duration": seconds_to_duration_str(best["total_time"]),
            "candidates": [_summarize_candidate(candidate, candidate is best) for candidate in candidates],
        }
    except Exception:
        return {"error": "Unable to generate route"}


def _summarize_candidate(candidate, selected):
    return {
        "origin": candidate["origin"]["name"],
        "routes": candidate["routes"],
        "total_miles": meters_to_miles(candidate["total_distance"]),
        "total_duration": seconds_to_duration_str(candidate["total_time"]),
        "time_window_violations": candidate["time_window_violations"],
        "constraint_violations": candidate["constraint_violations"],
        "violations": candidate["violations"],
        "selected": selected,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_shipments(shipments):
    """Check every shipment for structural and time-window problems.

    Returns (valid_shipments, errors). All shipments are checked (not just the
    first bad one) so a caller sees every problem in one pass.
    """
    if not isinstance(shipments, list) or not shipments:
        return [], [{"shipment_id": None, "issue": "No shipment data provided"}]

    valid = []
    errors = []

    for index, shipment in enumerate(shipments):
        label = f"shipment[{index}]"

        if not isinstance(shipment, dict):
            errors.append({"shipment_id": label, "issue": "Malformed shipment data"})
            continue

        shipment_id = shipment.get("shipment_id")
        label = shipment_id or label

        if not shipment_id:
            errors.append({"shipment_id": label, "issue": "Missing shipment_id"})
            continue

        delivery = shipment.get("delivery")
        if not isinstance(delivery, dict) or not delivery.get("address"):
            errors.append({"shipment_id": label, "issue": "Missing delivery address"})
            continue

        delivery_window = delivery.get("time_window")
        if delivery_window is not None:
            issue = _validate_time_window(delivery_window)
            if issue:
                errors.append({"shipment_id": label, "issue": f"Delivery window: {issue}"})
                continue

        pickup = shipment.get("pickup")
        pickup_window = None
        if pickup is not None:
            if not isinstance(pickup, dict) or not pickup.get("address"):
                errors.append({"shipment_id": label, "issue": "Missing pickup address"})
                continue
            pickup_window = pickup.get("time_window")
            if pickup_window is not None:
                issue = _validate_time_window(pickup_window)
                if issue:
                    errors.append({"shipment_id": label, "issue": f"Pickup window: {issue}"})
                    continue

        if pickup_window and delivery_window:
            issue = _validate_pickup_before_delivery(pickup_window, delivery_window)
            if issue:
                errors.append({"shipment_id": label, "issue": issue})
                continue

        valid.append(shipment)

    return valid, errors


def _validate_time_window(time_window):
    """Return an error string if the time window is malformed, else None."""
    if not isinstance(time_window, dict):
        return "Malformed time_window"

    start, end = time_window.get("start"), time_window.get("end")
    try:
        start_t = parse_time(start) if start else None
        end_t = parse_time(end) if end else None
    except ValueError:
        return "Invalid time format"

    if start_t and end_t and end_t <= start_t:
        return "End time is earlier than start time"

    return None


def _validate_pickup_before_delivery(pickup_window, delivery_window):
    """Structural sanity check only: a pickup deadline can't be at or after
    the delivery deadline, since that leaves no time at all for delivery to
    happen afterwards.
    """
    pickup_end, delivery_end = pickup_window.get("end"), delivery_window.get("end")
    if pickup_end and delivery_end and parse_time(pickup_end) >= parse_time(delivery_end):
        return "Pickup deadline is not before delivery deadline"
    return None


def _validate_origins(origins):
    """Check every candidate origin for structural problems, mirroring
    _validate_shipments: a non-empty list, each with a name and address, and
    names unique - a duplicate name would silently collide in the travel
    matrix, since ("origin", name) is the lookup key.
    """
    if not isinstance(origins, list) or not origins:
        return [{"origin": None, "issue": "No origin data provided"}]

    errors = []
    seen_names = set()

    for index, origin in enumerate(origins):
        label = f"origin[{index}]"

        if not isinstance(origin, dict):
            errors.append({"origin": label, "issue": "Malformed origin data"})
            continue

        name = origin.get("name")
        label = name or label

        if not name:
            errors.append({"origin": label, "issue": "Missing origin name"})
            continue

        if not origin.get("address"):
            errors.append({"origin": label, "issue": "Missing origin address"})
            continue

        if name in seen_names:
            errors.append({"origin": label, "issue": "Duplicate origin name"})
            continue

        seen_names.add(name)

    return errors


def _has_missing_travel_data(shipments, skipped_keys):
    for shipment in shipments:
        shipment_id = shipment["shipment_id"]
        if ("delivery", shipment_id) in skipped_keys:
            return True
        if shipment.get("pickup") and ("pickup", shipment_id) in skipped_keys:
            return True
    return False


# ---------------------------------------------------------------------------
# Event expansion + classification
# ---------------------------------------------------------------------------

def _expand_events(shipments):
    """Turn each shipment into one event (delivery only) or two events
    (pickup + delivery, linked by shipment_id).

    Each event carries both its own "time_window" (the real constraint, used
    for feasibility checking/validation/display) and a "priority_window" used
    for classification. They're usually the same - except a pickup with no
    window of its own still has to happen early enough for its own delivery's
    deadline to be reachable, so it borrows the delivery's window for
    priority purposes only. Without this, an unconstrained pickup would
    always sort into the lowest priority group and could get scheduled after
    its own delivery's deadline has effectively already passed. Feasibility
    simulation (_simulate_feasibility) deliberately uses the real
    "time_window" instead, so a borrowed deadline is never flagged as missed.

    Events are computed once per run (not once per origin) and reused across
    every candidate origin, since they don't depend on which origin is being
    evaluated - this is what keeps candidates comparable on identical urgency
    classification, with only the distance-based tiebreak reference point
    differing between them.

    Every event also carries both "pickup_address" and "delivery_address" for
    its shipment (not just its own leg's address) - a delivery driver reading
    the output needs both, regardless of which leg ("type") this particular
    stop is, the same way a food-delivery rider sees both the restaurant and
    the customer address on every step of one order. "pickup_address" is
    None only when the shipment genuinely has no pickup at all.
    """
    events = []
    for shipment in shipments:
        shipment_id = shipment["shipment_id"]
        pickup = shipment.get("pickup")
        delivery = shipment["delivery"]
        pickup_address = pickup["address"] if pickup else None
        delivery_address = delivery["address"]
        if pickup:
            pickup_window = pickup.get("time_window")
            events.append(
                {
                    "shipment_id": shipment_id,
                    "kind": PICKUP,
                    "key": ("pickup", shipment_id),
                    "pickup_address": pickup_address,
                    "delivery_address": delivery_address,
                    "time_window": pickup_window,
                    "priority_window": pickup_window or delivery.get("time_window"),
                }
            )
        delivery_window = delivery.get("time_window")
        events.append(
            {
                "shipment_id": shipment_id,
                "kind": DELIVERY,
                "key": ("delivery", shipment_id),
                "pickup_address": pickup_address,
                "delivery_address": delivery_address,
                "time_window": delivery_window,
                "priority_window": delivery_window,
            }
        )
    return events


def _classify_window(time_window):
    """Return (group, anchor_seconds, window_duration_seconds) for a single
    time window - see module docstring for the group rules.
    """
    time_window = time_window or {}
    start, end = time_window.get("start"), time_window.get("end")

    if end:
        start_s = seconds_since_midnight(parse_time(start)) if start else None
        end_s = seconds_since_midnight(parse_time(end))
        anchor = start_s if start_s is not None else end_s
        duration = (end_s - start_s) if start_s is not None else NO_DURATION
        return TIME_CRITICAL, anchor, duration
    if start:
        return START_ONLY, seconds_since_midnight(parse_time(start)), 0
    return NO_WINDOW, 0, 0


# ---------------------------------------------------------------------------
# Prioritization
# ---------------------------------------------------------------------------

def _prioritize_events(events, travel, origin_key):
    """Greedily build the visiting order one stop at a time, starting from
    the given origin:
      1. Only consider events that are "ready" - a delivery is only ready
         once its own shipment's pickup has already been placed; everything
         else is always ready.
      2. Among ready events, take the most urgent priority group/anchor/
         duration (see _classify_window).
      3. Break ties on real travel distance from whichever stop was placed
         right before it (the closer one wins) - the route always has a real
         "current position" to measure from, starting with origin_key itself,
         so even the very first tie is broken by distance from the origin.
    """
    has_pickup = {event["shipment_id"] for event in events if event["kind"] == PICKUP}
    placed_pickups = set()
    remaining = list(events)
    sequence = []
    current_key = origin_key

    while remaining:
        ready = [
            event
            for event in remaining
            if event["kind"] == PICKUP
            or event["shipment_id"] not in has_pickup
            or event["shipment_id"] in placed_pickups
        ]

        best_priority = min(_classify_window(event["priority_window"]) for event in ready)
        tied = [event for event in ready if _classify_window(event["priority_window"]) == best_priority]

        if len(tied) == 1:
            next_event = tied[0]
        else:
            next_event = min(tied, key=lambda event: _leg_distance(current_key, event["key"], travel))

        sequence.append(next_event)
        remaining.remove(next_event)
        if next_event["kind"] == PICKUP:
            placed_pickups.add(next_event["shipment_id"])
        current_key = next_event["key"]

    return sequence


def _leg_distance(from_key, to_key, travel):
    leg = travel.get((from_key, to_key))
    return leg["distance"] if leg else 0


# ---------------------------------------------------------------------------
# Feasibility simulation
# ---------------------------------------------------------------------------

def _simulate_feasibility(origin_key, sequence, travel):
    """Walk the built sequence from DEFAULT_DEPARTURE_TIME, accumulating real
    travel time leg-by-leg, and flag every stop whose own deadline ("end") is
    missed. Uses each event's real "time_window", not its "priority_window" -
    a pickup that borrowed its delivery's deadline for sorting purposes must
    never be flagged as late against a deadline it doesn't actually have.

    Arriving before a "start" just means waiting until start (no violation,
    no distance impact); arriving after an "end" is recorded as a violation,
    and the driver's clock stays at the late arrival time so the delay
    correctly compounds into every stop after it. No loading/unloading dwell
    time is modeled at any stop.
    """
    current_time = seconds_since_midnight(parse_time(DEFAULT_DEPARTURE_TIME))
    current_key = origin_key
    violations = []

    for event in sequence:
        leg = travel.get((current_key, event["key"]))
        current_time += leg["time"] if leg else 0

        time_window = event.get("time_window") or {}
        start, end = time_window.get("start"), time_window.get("end")

        if start:
            current_time = max(current_time, seconds_since_midnight(parse_time(start)))

        if end:
            end_s = seconds_since_midnight(parse_time(end))
            if current_time > end_s:
                violations.append(
                    {
                        "shipment_id": event["shipment_id"],
                        "kind": event["kind"],
                        "type": "missed_deadline",
                        "scheduled_arrival": current_time,
                        "deadline": end_s,
                        "delay_seconds": current_time - end_s,
                        "message": (
                            f"{event['shipment_id']} {event['kind']} missed deadline "
                            f"{format_clock(end_s)} by {seconds_to_duration_str(current_time - end_s)} "
                            f"(arrived {format_clock(current_time)})"
                        ),
                    }
                )

        current_key = event["key"]

    return violations


def _compute_totals(origin_key, sequence, travel):
    """Sum real travel distance/time along the exact sequence produced above,
    starting from the selected origin - the origin-to-first-stop leg counts
    toward the total, since that's real driving the vehicle does.
    """
    total_distance, total_time = 0, 0
    prev_key = origin_key
    for event in sequence:
        leg = travel.get((prev_key, event["key"]))
        if leg:
            total_distance += leg["distance"]
            total_time += leg["time"]
        prev_key = event["key"]
    return total_distance, total_time


# ---------------------------------------------------------------------------
# Origin evaluation
# ---------------------------------------------------------------------------

def _evaluate_origin(origin, events, travel):
    """Generate one full candidate route as if the driver started at this
    origin: build its visiting sequence, check pickup/delivery feasibility,
    and total the real travel distance/time - all using our own business
    logic, with Geoapify supplying only distances/times.
    """
    origin_key = ("origin", origin["name"])
    sequence = _prioritize_events(events, travel, origin_key)
    violations = _simulate_feasibility(origin_key, sequence, travel)
    total_distance, total_time = _compute_totals(origin_key, sequence, travel)
    routes = _build_routes_output(sequence)

    return {
        "origin": origin,
        "routes": routes,
        "total_distance": total_distance,
        "total_time": total_time,
        "violations": violations,
        "time_window_violations": sum(1 for v in violations if v["type"] == "missed_deadline"),
        "constraint_violations": len(violations),
    }


# ---------------------------------------------------------------------------
# Output building
# ---------------------------------------------------------------------------

def _build_routes_output(sequence):
    """Build the final stop-by-stop output, numbered from "001" - the
    selected origin is never a numbered stop here (it's surfaced separately
    as top-level "selected_origin" metadata by generate_prioritized_route),
    since a shipment never has an origin of its own, only addresses.

    Every stop shows both "pickup_address" and "delivery_address" for its
    shipment, regardless of "type" - "type" says which action happens at
    *this* stop (pick up vs. drop off), not which address to hide. The one
    exception is "pickup_address" being null, which means the shipment
    genuinely has no pickup at all (delivery-only).
    """
    routes = {}
    for step, event in enumerate(sequence, start=1):
        routes[f"{step:03d}"] = {
            "pickup_address": event["pickup_address"],
            "delivery_address": event["delivery_address"],
            "shipment_id": event["shipment_id"],
            "type": event["kind"],
        }
    return routes

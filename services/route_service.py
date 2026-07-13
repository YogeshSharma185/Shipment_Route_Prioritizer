"""Turns shipment data + a Geoapify travel-time matrix into a prioritized,
customer-friendly route. Responsibilities:
  1. Validate the shipment data (ids, addresses, time windows).
  2. Prioritize every pickup/delivery stop using the business rules below.
  3. Build the final "routes" output.

Shipment shape:
  {
    "shipment_id": "SH001",
    "pickup": {                                        # optional
        "origin": "Warehouse A",                        # label only, for display
        "address": "Warehouse A",
        "time_window": {"start": "09:00", "end": "10:00"},  # optional
    },
    "delivery": {
        "address": "123 Main Street",
        "time_window": {"start": "11:00", "end": "13:00"},  # optional
    },
  }

Each shipment may belong to a different pickup origin (warehouse) - there is
no single shared starting point. A shipment with no "pickup" at all is
delivery-only, exactly like the original single-location design. Both
time_window fields are independently optional, so a shipment may have
neither, either, or both.

Business rules - a shipment with a pickup contributes two independent
*events* to the ordering (a pickup and a delivery), each classified by its
own time window exactly like the original single-window design:

  Group 0 - TIME_CRITICAL: any event with a deadline (an "end"), whether or
  not it also has a "start" (strict windows and deadline-only events share
  one timeline, rather than treating "has a full window" as always more
  urgent than "has a deadline" regardless of timing).
  Group 1 - START_ONLY: has a start but no end.
  Group 2 - NO_WINDOW: no time window at all.

Within a tied group, the standard rule is real travel distance - but with
several different pickup origins in play there's no longer one shared
warehouse to measure "closer" from. So the tiebreak here is "closer to
wherever the driver currently is" - i.e. distance from whichever stop was
placed immediately before it in the route being built (see
_prioritize_events). This is a direct generalisation of the original
single-origin "closer stop wins the tie" rule to a multi-origin setting.

On top of priority, a pickup event must always come before its own
shipment's delivery event. _prioritize_events enforces this directly (by
only ever considering a delivery "ready" once its own pickup has already
been placed) rather than sorting first and patching precedence afterwards -
simpler to read, and impossible to get out of order by construction.
"""
from utils.time_utils import (
    meters_to_miles,
    parse_time,
    seconds_since_midnight,
    seconds_to_duration_str,
)

TIME_CRITICAL, START_ONLY, NO_WINDOW = range(3)
NO_DURATION = 24 * 3600 + 1  # bigger than any possible same-day window

PICKUP, DELIVERY = "pickup", "delivery"


def generate_prioritized_route(shipments, travel, skipped_keys):
    """Validate the shipments, prioritize every stop, and return the final
    route.

    travel/skipped_keys are exactly what geoapify_service.get_travel_matrix()
    returns for these same shipments.

    On any validation failure, returns {"error": ..., "details": [...]}.
    On missing travel data, or any unexpected failure, returns
    {"error": "Unable to generate route"} instead of raising.
    """
    try:
        valid_shipments, errors = _validate_shipments(shipments)
        if errors:
            return {"error": "Invalid shipment data", "details": errors}

        if _has_missing_travel_data(valid_shipments, skipped_keys):
            # Mirrors the original project's stance: one unresolvable address
            # shouldn't fail validation, but a *valid* shipment with no usable
            # travel data can't be routed, so it's an "Unable to generate
            # route" case rather than silently dropping or mis-prioritizing it.
            return {"error": "Unable to generate route"}

        shipments_by_id = {shipment["shipment_id"]: shipment for shipment in valid_shipments}
        events = _expand_events(valid_shipments)
        sequence = _prioritize_events(events, travel)

        total_distance, total_time = _compute_totals(sequence, travel)
        routes = _build_routes_output(sequence, shipments_by_id)

        return {
            "routes": routes,
            "total_miles": meters_to_miles(total_distance),
            "total_duration": seconds_to_duration_str(total_time),
        }
    except Exception:
        return {"error": "Unable to generate route"}


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
    for validation/display) and a "priority_window" used for classification.
    They're usually the same - except a pickup with no window of its own
    still has to happen early enough for its own delivery's deadline to be
    reachable, so it borrows the delivery's window for priority purposes.
    Without this, an unconstrained pickup would always sort into the lowest
    priority group and could get scheduled after its own delivery's deadline
    has effectively already passed.
    """
    events = []
    for shipment in shipments:
        shipment_id = shipment["shipment_id"]
        pickup = shipment.get("pickup")
        delivery = shipment["delivery"]
        if pickup:
            pickup_window = pickup.get("time_window")
            events.append(
                {
                    "shipment_id": shipment_id,
                    "kind": PICKUP,
                    "key": ("pickup", shipment_id),
                    "address": pickup["address"],
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
                "address": delivery["address"],
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

def _prioritize_events(events, travel):
    """Greedily build the visiting order one stop at a time:
      1. Only consider events that are "ready" - a delivery is only ready
         once its own shipment's pickup has already been placed; everything
         else is always ready.
      2. Among ready events, take the most urgent priority group/anchor/
         duration (see _classify_window).
      3. Break ties on real travel distance from whichever stop was placed
         right before it (the closer one wins) - falling back to
         shipment_id for the very first stop, when there's no "current
         position" yet to measure from.
    """
    has_pickup = {event["shipment_id"] for event in events if event["kind"] == PICKUP}
    placed_pickups = set()
    remaining = list(events)
    sequence = []
    current_key = None

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

        if current_key is None or len(tied) == 1:
            next_event = sorted(tied, key=lambda event: event["shipment_id"])[0]
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


def _compute_totals(sequence, travel):
    """Sum real travel distance/time along the exact sequence produced above."""
    total_distance, total_time = 0, 0
    prev_key = None
    for event in sequence:
        if prev_key is not None:
            leg = travel.get((prev_key, event["key"]))
            if leg:
                total_distance += leg["distance"]
                total_time += leg["time"]
        prev_key = event["key"]
    return total_distance, total_time


# ---------------------------------------------------------------------------
# Output building
# ---------------------------------------------------------------------------

def _build_routes_output(sequence, shipments_by_id):
    routes = {}
    for step, event in enumerate(sequence, start=1):
        entry = {
            "address": event["address"],
            "shipment_id": event["shipment_id"],
            "type": event["kind"],
        }
        if event["kind"] == PICKUP:
            entry["origin"] = shipments_by_id[event["shipment_id"]]["pickup"].get("origin")
        routes[f"{step:03d}"] = entry
    return routes

"""Turns shipment data + a Geoapify Route Planner response into a prioritized,
customer-friendly route. Responsibilities:
  1. Validate the Geoapify response itself.
  2. Validate shipment data (ids, addresses, time windows).
  3. Prioritize shipments using the business rules below.
  4. Build the final "routes" output.

Priority rules (most to least urgent):

  Group 0 - TIME_CRITICAL: any shipment with a deadline (an "end"), whether
  or not it also has a "start" (i.e. both strict windows and deadline-only
  shipments land in this one group). They're merged onto a single timeline
  rather than treating "has a full window" as always more urgent than "has a
  deadline" - a deadline of 12:30 is more urgent than a window that doesn't
  even start until 14:00, so a rigid window-before-deadline split produces
  the wrong order. Sorted by:
    a. anchor time - the start time if present (a window's earliest useful
       arrival), otherwise the end time (a deadline's only reference point).
    b. window duration, as a tiebreak when two shipments share the same
       anchor (e.g. same start time but different end times - the tighter
       window is more urgent). Deadline-only shipments have no duration, so
       they always lose this tiebreak to an actual windowed shipment sharing
       their anchor time.
    c. Geoapify route distance (closer first) - the assignment's
       "same time window" tiebreak rule.

  Group 1 - START_ONLY: has a start but no end ("don't deliver before X").
  No deadline pressure at all, so always after every TIME_CRITICAL shipment
  regardless of how early its start is. Sorted by start time, then distance.

  Group 2 - NO_WINDOW: no time_window at all. Always last, sorted by
  distance only.
"""
from utils.time_utils import (
    meters_to_miles,
    parse_time,
    seconds_since_midnight,
    seconds_to_duration_str,
)

TIME_CRITICAL, START_ONLY, NO_WINDOW = range(3)
NO_DURATION = 24 * 3600 + 1  # bigger than any possible same-day window


def generate_prioritized_route(shipments, geoapify_response, origin_address):
    """Validate everything, prioritize shipments, and return the final route.

    origin_address is the warehouse address supplied by the caller for this
    run - there is no configured default, since the warehouse can change per
    request.

    On any validation failure, returns {"error": ..., "details": [...]}.
    On a bad/unusable Geoapify response, or any unexpected failure, returns
    {"error": "Unable to generate route"} instead of raising.
    """
    try:
        if not _is_valid_geoapify_response(geoapify_response):
            return {"error": "Unable to generate route"}

        valid_shipments, errors = _validate_shipments(shipments)
        if errors:
            return {"error": "Invalid shipment data", "details": errors}

        job_distances = _extract_job_distances(geoapify_response)
        if any(shipment["shipment_id"] not in job_distances for shipment in valid_shipments):
            # Geoapify's live optimizer occasionally drops a job from its solution
            # without reporting it in properties.issues. Treat that as incomplete
            # data rather than silently defaulting the missing job's tie-break
            # distance to 0, which would make it look (wrongly) like the closest stop.
            return {"error": "Unable to generate route"}

        total_distance_m, total_time_s = _extract_totals(geoapify_response)

        sorted_shipments = _prioritize_shipments(valid_shipments, job_distances)
        routes = _build_routes_output(sorted_shipments, origin_address)

        return {
            "routes": routes,
            "total_miles": meters_to_miles(total_distance_m),
            "total_duration": seconds_to_duration_str(total_time_s),
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
        if not shipment.get("address"):
            errors.append({"shipment_id": label, "issue": "Missing address"})
            continue

        time_window = shipment.get("time_window")
        if time_window is not None:
            issue = _validate_time_window(time_window)
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


def _is_valid_geoapify_response(geoapify_response):
    """A usable response has at least one route feature and no unassigned jobs."""
    if not isinstance(geoapify_response, dict):
        return False
    if not geoapify_response.get("features"):
        return False
    issues = geoapify_response.get("properties", {}).get("issues", {})
    if issues.get("unassigned_jobs"):
        return False
    return True


# ---------------------------------------------------------------------------
# Prioritization
# ---------------------------------------------------------------------------

def _classify(shipment):
    """Return (group, anchor_seconds, window_duration_seconds) - see module docstring."""
    time_window = shipment.get("time_window") or {}
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


def _prioritize_shipments(shipments, job_distances):
    def sort_key(shipment):
        group, anchor, duration = _classify(shipment)
        distance = job_distances.get(shipment["shipment_id"], 0)
        return (group, anchor, duration, distance, shipment["shipment_id"])

    return sorted(shipments, key=sort_key)


# ---------------------------------------------------------------------------
# Geoapify response parsing
# ---------------------------------------------------------------------------

def _extract_job_distances(geoapify_response):
    """Map each job's id to its cumulative route distance (meters) from the
    warehouse, based on the order Geoapify chose. Used only as a tie-breaker
    when two shipments share the same time-window priority. Returns an empty
    dict (falling back to no tie-break) if the response shape is unexpected.
    """
    distances = {}
    try:
        properties = geoapify_response["features"][0]["properties"]
        legs = properties.get("legs", [])
        actions = properties.get("actions", [])

        cumulative_by_waypoint = {0: 0}
        for leg in legs:
            from_idx, to_idx = leg["from_waypoint_index"], leg["to_waypoint_index"]
            cumulative_by_waypoint[to_idx] = cumulative_by_waypoint.get(from_idx, 0) + leg["distance"]

        for action in actions:
            if action.get("type") == "job" and "job_id" in action:
                distances[action["job_id"]] = cumulative_by_waypoint.get(action["waypoint_index"], 0)
    except (KeyError, IndexError, TypeError):
        pass
    return distances


def _extract_totals(geoapify_response):
    """Pull the overall route distance (meters) and time (seconds)."""
    try:
        properties = geoapify_response["features"][0]["properties"]
        return properties.get("distance", 0), properties.get("time", 0)
    except (KeyError, IndexError, TypeError):
        return 0, 0


# ---------------------------------------------------------------------------
# Output building
# ---------------------------------------------------------------------------

def _build_routes_output(sorted_shipments, origin_address):
    routes = {"000": {"address": origin_address, "shipment_id": "", "type": "origin"}}

    step = 0
    for step, shipment in enumerate(sorted_shipments, start=1):
        routes[f"{step:03d}"] = {
            "address": shipment["address"],
            "shipment_id": shipment["shipment_id"],
            "type": "drop",
        }

    routes[f"{step + 1:03d}"] = {"address": origin_address, "shipment_id": "", "type": "end"}
    return routes

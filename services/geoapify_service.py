"""Everything related to talking to Geoapify: geocoding addresses and getting
real drive distances/times between them. This module has one job: turn
addresses into facts (coordinates, pairwise travel time/distance). It does
not decide what order to visit stops in or validate shipment data - that's
route_service.py's job.

Each shipment carries its own pickup point (a specific warehouse origin) and
delivery point, so "what order to visit stops in" is a sequencing problem
route_service.py solves itself. The only thing asked of Geoapify here is a
travel-time matrix between every point that could appear in a route.
"""
import requests

import config


class GeoapifyError(Exception):
    """Raised whenever we can't get usable travel data back from Geoapify."""


def geocode_address(address: str) -> list:
    """Turn a street address into a [longitude, latitude] pair using Geoapify's
    Geocoding API. Raises GeoapifyError if the address can't be resolved.
    """
    params = {
        "text": address,
        "apiKey": config.GEOAPIFY_API_KEY,
        "format": "json",
        "limit": 1,
    }
    response = requests.get(config.GEOCODE_URL, params=params, timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()

    results = response.json().get("results", [])
    if not results:
        raise GeoapifyError(f"Could not geocode address: {address!r}")

    top_match = results[0]
    return [top_match["lon"], top_match["lat"]]


def _collect_points(shipments: list) -> list:
    """List every (key, address) pair that needs a location: one per shipment
    pickup (if it has one - each shipment's own pickup.address is that
    shipment's specific warehouse origin) and one per shipment delivery. key
    is a (kind, id) tuple used to look distances back up later -
    ("pickup", shipment_id) / ("delivery", shipment_id).
    """
    points = []
    for shipment in shipments:
        if not isinstance(shipment, dict):
            continue
        shipment_id = shipment.get("shipment_id")
        if not shipment_id:
            continue
        pickup = shipment.get("pickup")
        if isinstance(pickup, dict) and pickup.get("address"):
            points.append((("pickup", shipment_id), pickup["address"]))
        delivery = shipment.get("delivery") or {}
        points.append((("delivery", shipment_id), delivery.get("address")))

    return points


def _call_matrix_api(locations: list) -> tuple:
    """Call Geoapify's Routing Matrix API with every location as both a
    source and a target. Returns (matrix, raw_response):
      - matrix: a locations x locations grid of {"distance": meters, "time": seconds} cells.
      - raw_response: the exact JSON Geoapify returned, unmodified - kept
        around purely so the UI can show the real API response, not just
        our own derived numbers.
    """
    payload = {
        "mode": "drive",
        "sources": [{"location": location} for location in locations],
        "targets": [{"location": location} for location in locations],
    }
    response = requests.post(
        config.MATRIX_URL,
        params={"apiKey": config.GEOAPIFY_API_KEY},
        json=payload,
        timeout=config.REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    raw_response = response.json()
    matrix = [
        [{"distance": cell["distance"], "time": cell["time"]} for cell in row]
        for row in raw_response.get("sources_to_targets", [])
    ]
    return matrix, raw_response


def get_travel_matrix(shipments: list) -> tuple:
    """Geocode every pickup/delivery point (once per distinct address) and
    return real drive distance/time between every pair of them.

    Returns (travel, skipped_keys, raw_response):
      - travel: {(from_key, to_key): {"distance": meters, "time": seconds}}
        for every pair of successfully-geocoded points.
      - skipped_keys: the set of point keys whose address couldn't be
        geocoded (missing address, or Geoapify couldn't resolve it) - mirrors
        the old _build_jobs behaviour of skipping bad addresses here so one
        unresolvable stop doesn't fail the whole request; route_service.py
        treats any *valid* shipment that lands in here as an unusable route.
      - raw_response: the unmodified JSON Geoapify's Matrix API returned.

    Raises GeoapifyError only if nothing at all could be geocoded, or the
    Matrix API call itself fails.
    """
    points = _collect_points(shipments)

    address_cache = {}
    geocoded = []
    skipped_keys = set()

    for key, address in points:
        if not address:
            skipped_keys.add(key)
            continue
        if address not in address_cache:
            try:
                address_cache[address] = geocode_address(address)
            except GeoapifyError:
                address_cache[address] = None
        location = address_cache[address]
        if location is None:
            skipped_keys.add(key)
            continue
        geocoded.append((key, location))

    if not geocoded:
        raise GeoapifyError("No shipment addresses could be geocoded")

    keys = [key for key, _ in geocoded]
    locations = [location for _, location in geocoded]

    try:
        matrix, raw_response = _call_matrix_api(locations)
    except requests.RequestException as exc:
        raise GeoapifyError(f"Geoapify matrix request failed: {exc}") from exc

    travel = {}
    for i, from_key in enumerate(keys):
        for j, to_key in enumerate(keys):
            if i == j:
                continue
            travel[(from_key, to_key)] = matrix[i][j]

    return travel, skipped_keys, raw_response

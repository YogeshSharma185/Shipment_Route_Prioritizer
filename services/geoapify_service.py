"""Everything related to talking to Geoapify: geocoding addresses and calling
the Route Planner API. This module has one job: get a route plan back from
Geoapify. It does not validate shipment data or decide delivery order -
that happens in route_service.py.
"""
import requests

import config


class GeoapifyError(Exception):
    """Raised whenever we can't get a usable route plan back from Geoapify."""


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


def _build_jobs(shipments: list) -> list:
    """Geocode each shipment's address into a Route Planner "job". Shipments with
    a missing address or an address Geoapify can't find are skipped here -
    they're reported properly later by route_service's field validation.
    """
    jobs = []
    for index, shipment in enumerate(shipments):
        if not isinstance(shipment, dict):
            continue
        address = shipment.get("address")
        if not address:
            continue
        try:
            location = geocode_address(address)
        except GeoapifyError:
            continue
        jobs.append({"id": shipment.get("shipment_id") or f"job_{index}", "location": location})
    return jobs


def get_geoapify_route(origin: str, shipments: list) -> dict:
    """Prepare the Route Planner payload, call the Geoapify API, and return the
    raw JSON response. Raises GeoapifyError on any failure (network issue,
    bad API key, no geocodable stops, etc.) so callers can handle it gracefully.
    """
    try:
        origin_location = geocode_address(origin)
        jobs = _build_jobs(shipments)
        if not jobs:
            raise GeoapifyError("No shipment addresses could be geocoded")

        payload = {
            "mode": "drive",
            "agents": [{"start_location": origin_location}],
            "jobs": jobs,
        }

        response = requests.post(
            config.ROUTE_PLANNER_URL,
            params={"apiKey": config.GEOAPIFY_API_KEY},
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    except GeoapifyError:
        raise
    except requests.RequestException as exc:
        raise GeoapifyError(f"Geoapify request failed: {exc}") from exc

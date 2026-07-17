"""Entry point demonstrating the full pipeline:

  1. Accept shipment data (each optionally has its own "pickup") and a fixed
     list of candidate driver origins (AVAILABLE_ORIGINS).
  2. Geocode every origin/pickup/delivery point and get a real drive
     distance/time matrix between all of them (Geoapify) in a single call.
  3. Pass shipments + origins + that matrix to generate_prioritized_route(),
     which validates the data, evaluates every candidate origin, and selects
     the best one.
  4. Print only the selected origin and its final, customer-friendly route -
     not every candidate that was considered.
"""
import json

from sample_data import AVAILABLE_ORIGINS, SAMPLE_SHIPMENTS
from services.geoapify_service import GeoapifyError, get_travel_matrix
from services.route_service import generate_prioritized_route


def build_route(shipments, origins):
    try:
        travel, skipped_keys, _raw_response, _locations = get_travel_matrix(shipments, origins)
    except GeoapifyError as exc:
        print(f"Geoapify request failed: {exc}")
        return {"error": "Unable to generate route"}

    return generate_prioritized_route(shipments, travel, skipped_keys, origins)


if __name__ == "__main__":
    result = build_route(SAMPLE_SHIPMENTS, AVAILABLE_ORIGINS)
    result.pop("candidates", None)  # terminal output shows only the selected route
    print(json.dumps(result, indent=2))

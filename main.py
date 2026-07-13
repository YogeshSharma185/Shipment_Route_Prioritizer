"""Entry point demonstrating the full pipeline:

  1. Accept shipment data - each shipment optionally has its own "pickup"
     (a specific warehouse origin) alongside its "delivery".
  2. Geocode every pickup/delivery point and get a real drive distance/time
     matrix between all of them (Geoapify).
  3. Pass shipments + that matrix to generate_prioritized_route(), which
     validates the data and prioritizes every stop.
  4. Print the final, customer-friendly route.
"""
import json

from sample_data import SAMPLE_SHIPMENTS
from services.geoapify_service import GeoapifyError, get_travel_matrix
from services.route_service import generate_prioritized_route


def build_route(shipments):
    try:
        travel, skipped_keys = get_travel_matrix(shipments)
    except GeoapifyError as exc:
        print(f"Geoapify request failed: {exc}")
        return {"error": "Unable to generate route"}

    return generate_prioritized_route(shipments, travel, skipped_keys)


if __name__ == "__main__":
    result = build_route(SAMPLE_SHIPMENTS)
    print(json.dumps(result, indent=2))

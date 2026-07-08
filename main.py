"""Entry point demonstrating the full pipeline:

  1. Accept shipment data and origin warehouse.
  2/3/4. Build the Geoapify payload, call the Route Planner API, get the response.
  5. Pass the response to generate_prioritized_route() for validation + prioritization.
  6. Print the final, customized route.
"""
import json

from sample_data import SAMPLE_ORIGIN_ADDRESS, SAMPLE_SHIPMENTS
from services.geoapify_service import GeoapifyError, get_geoapify_route
from services.route_service import generate_prioritized_route


def build_route(shipments, origin_address):
    try:
        geoapify_response = get_geoapify_route(origin_address, shipments)
    except GeoapifyError as exc:
        print(f"Geoapify request failed: {exc}")
        return {"error": "Unable to generate route"}

    return generate_prioritized_route(shipments, geoapify_response, origin_address)


if __name__ == "__main__":
    result = build_route(SAMPLE_SHIPMENTS, SAMPLE_ORIGIN_ADDRESS)
    print(json.dumps(result, indent=2))

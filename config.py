"""Centralized configuration. The only secret/environment-specific value is
the Geoapify API key, loaded from .env. Everything else here is a fixed
constant of the Geoapify API itself, not something a deployment would need
to override.
"""
import os

from dotenv import load_dotenv

load_dotenv()

GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "")

GEOAPIFY_BASE_URL = "https://api.geoapify.com"
REQUEST_TIMEOUT = 15

GEOCODE_URL = f"{GEOAPIFY_BASE_URL}/v1/geocode/search"
ROUTE_PLANNER_URL = f"{GEOAPIFY_BASE_URL}/v1/routeplanner"

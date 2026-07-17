"""Sample data, so the project can be run immediately without needing real
customer data.

AVAILABLE_ORIGINS is the driver's fixed set of candidate starting warehouses
- this is the only place the concept of "origin" exists. Every origin is
evaluated independently by generate_prioritized_route() (see
services/route_service.py) before the best one is selected; there's no
"just pick the nearest origin" shortcut. Origin `name` values must be unique
- they double as the key used to look up that origin's real Geoapify travel
distances.

A shipment never has an "origin" - only addresses. Each shipment optionally
carries its own "pickup" (address + optional hard time_window) alongside its
"delivery" (address + optional time_window); a shipment's pickup address is
completely independent of AVAILABLE_ORIGINS.

The three origins are deliberately spread far apart from each other and from
the shipment cluster, while staying within Gurugram (Gurgaon) district
throughout - Sector 110 to the north (near the city's Delhi-facing edge),
Bilaspur Chowk to the southwest, Ghata on Sohna Road to the south. These are
20-30km apart from each other, versus the shipment cluster's own few-km
span, rather than all sitting close together like the shipment addresses do.
This makes origin choice actually matter: the origin-to-first-stop leg
differs enough between candidates to meaningfully change total distance/
duration, and - since SH006's pickup has a tight 08:00-08:45 deadline
against a fixed 08:00 departure time - an origin that's simply too far away
can genuinely fail to reach it in time, producing a real time-window
violation for that candidate that the others don't have.

Most shipments (7/10) have their own pickup; a few (SH003, SH004, SH010)
don't - delivery-only, exactly like a single-location shipment. Between
them, every time-window combination is covered:
  - both windows           -> SH001, SH005, SH006
  - only a delivery window  -> SH002, SH003, SH009, SH010
  - only a pickup window    -> SH008
  - neither window          -> SH004, SH007 (pickup present, no window on either side)

All shipment pickup/delivery addresses are real, verified places in Gurugram
(Gurgaon), Haryana - each one geocodes correctly and stays within Gurugram
(checked against the live Geoapify geocoder); every pickup address below
reuses one of these verified addresses rather than introducing new ones.
AVAILABLE_ORIGINS addresses are separately verified real Gurugram places too,
chosen specifically to sit far outside that cluster (see above) while
staying within the same district.
"""

AVAILABLE_ORIGINS = [
    {"name": "Warehouse A", "address": "Sector 110, Gurugram, Haryana 122017"},
    {"name": "Warehouse B", "address": "Bilaspur Chowk, Gurugram, Haryana 122413"},
    {"name": "Warehouse C", "address": "Ghata, Sohna Road, Gurugram, Haryana 122102"},
]

SAMPLE_SHIPMENTS = [
    {
        "shipment_id": "SH001",
        "pickup": {
            "address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016",
            "time_window": {"end": "10:30"},  # hard pickup deadline
        },
        "delivery": {
            "address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002",
            "time_window": {"start": "11:00", "end": "13:00"},  # strict 2h delivery window
        },
    },
    {
        "shipment_id": "SH002",
        "pickup": {
            "address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001",
            # no pickup time_window - pickup address only
        },
        "delivery": {
            "address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002",
            "time_window": {"start": "14:00", "end": "17:00"},  # strict 3h window
        },
    },
    {
        "shipment_id": "SH003",
        "delivery": {
            "address": "MGF Metropolitan Mall, MG Road, Sector 28, Gurugram, Haryana 122002",
            "time_window": {"end": "15:00"},  # "deliver before" constraint
        },
    },
    {
        "shipment_id": "SH004",
        "delivery": {
            "address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001",
            # no time_window at all - delivered last
        },
    },
    {
        "shipment_id": "SH005",
        "pickup": {
            "address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018",
            "time_window": {"start": "09:30", "end": "10:30"},  # hard 1h pickup window
        },
        "delivery": {
            "address": "Galleria Market, DLF Phase 4, Gurugram, Haryana 122009",
            "time_window": {"start": "11:00", "end": "13:00"},  # ties with SH001 on delivery
        },
    },
    {
        "shipment_id": "SH006",
        "pickup": {
            "address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002",
            "time_window": {"start": "08:00", "end": "08:45"},  # tight pickup window, well before delivery
        },
        "delivery": {
            "address": "HUDA City Centre, Sector 29, Gurugram, Haryana 122001",
            "time_window": {"start": "09:00", "end": "10:00"},  # tightest 1h window
        },
    },
    {
        "shipment_id": "SH007",
        "pickup": {
            "address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002",
            # no pickup time_window - pickup address only
        },
        "delivery": {
            "address": "Kingdom of Dreams, Sector 29, Gurugram, Haryana 122001",
            "time_window": {"end": "12:30"},  # "deliver before" constraint
        },
    },
    {
        "shipment_id": "SH008",
        "pickup": {
            "address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001",
            "time_window": {"start": "08:00", "end": "09:00"},  # only a pickup window
        },
        "delivery": {
            "address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018",
            # no delivery time_window
        },
    },
    {
        "shipment_id": "SH009",
        "pickup": {
            "address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002",
            # no pickup time_window - pickup address only
        },
        "delivery": {
            "address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002",
            "time_window": {"start": "16:00", "end": "18:00"},  # ties with SH001/SH005 on duration
        },
    },
    {
        "shipment_id": "SH010",
        "delivery": {
            "address": "Sohna Road, Sector 49, Gurugram, Haryana 122018",
            "time_window": {"start": "08:00"},  # "deliver after" - start only
        },
    },
]

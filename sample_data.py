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

Warehouse C's address is deliberately identical to SH005's own pickup address
- this is the project's worked edge case: a shipment's pickup can itself sit
at a location that's also a candidate driver origin, but it must always be
treated as an ordinary pickup stop, never as the selected origin, unless that
same warehouse is the one actually chosen to start the route from.

Most shipments (7/10) have their own pickup; a few (SH003, SH004, SH010)
don't - delivery-only, exactly like a single-location shipment. Between
them, every time-window combination is covered:
  - both windows           -> SH001, SH005, SH006
  - only a delivery window  -> SH002, SH003, SH009, SH010
  - only a pickup window    -> SH008
  - neither window          -> SH004, SH007 (pickup present, no window on either side)

All addresses are real, verified places in Gurugram (Gurgaon), Haryana -
each one geocodes correctly and stays within Gurugram (checked against the
live Geoapify geocoder). Every AVAILABLE_ORIGINS / pickup address below
reuses one of these verified addresses rather than introducing new ones.
"""

AVAILABLE_ORIGINS = [
    {"name": "Warehouse A", "address": "Udyog Vihar Phase 1, Gurugram, Haryana 122016"},
    {"name": "Warehouse B", "address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002"},
    {"name": "Warehouse C", "address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018"},
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

"""Sample shipment data, so the project can be run immediately without
needing real customer data.

Each shipment optionally carries its own "pickup" (a specific warehouse
origin - address + optional hard time_window) alongside its "delivery"
(address + optional time_window). There's no single shared warehouse here:
SH001/SH005/SH008 each pick up from a *different* origin, SH007 has a pickup
address but no pickup time_window, and the rest have no "pickup" at all
(delivery-only, exactly like a single-location shipment). Between them, every
combination the notes describe is covered:
  - both windows           -> SH001, SH005
  - only a delivery window  -> SH002, SH003, SH006, SH009, SH010
  - only a pickup window    -> SH008
  - neither window          -> SH004, SH007 (pickup present, no window on either side)

All addresses are real, verified places in Gurugram (Gurgaon), Haryana -
each one geocodes correctly and stays within Gurugram (checked against the
live Geoapify geocoder).
"""

SAMPLE_SHIPMENTS = [
    {
        "shipment_id": "SH001",
        "pickup": {
            "origin": "Warehouse Udyog Vihar",
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
            "origin": "Warehouse Sohna Road",
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
        "delivery": {
            "address": "HUDA City Centre, Sector 29, Gurugram, Haryana 122001",
            "time_window": {"start": "09:00", "end": "10:00"},  # tightest 1h window
        },
    },
    {
        "shipment_id": "SH007",
        "pickup": {
            "origin": "Warehouse DLF",
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
            "origin": "Warehouse Sector 14",
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

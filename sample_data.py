"""Sample shipment data and origin warehouse, so the project can be run
immediately without needing real customer data.

The warehouse address is deliberately defined here (as an input) rather than
in config.py - the assignment treats it as data supplied per-request, not a
fixed environment setting.

All 11 addresses below are real, verified places in Gurugram (Gurgaon),
Haryana - each one geocodes correctly and stays within Gurugram (checked
against the live Geoapify geocoder), so this is a realistic "happy path"
dataset covering every priority rule.
"""

SAMPLE_ORIGIN_ADDRESS = "Udyog Vihar Phase 1, Gurugram, Haryana 122016"

SAMPLE_SHIPMENTS = [
    {
        "shipment_id": "SH001",
        "address": "DLF Cyber Hub, DLF Cyber City, Sector 24, Gurugram, Haryana 122002",
        "time_window": {"start": "11:00", "end": "13:00"},  # strict 2h window
    },
    {
        "shipment_id": "SH002",
        "address": "Ambience Mall, NH 48, Sector 24, Gurugram, Haryana 122002",
        "time_window": {"start": "14:00", "end": "17:00"},  # strict 3h window
    },
    {
        "shipment_id": "SH003",
        "address": "MGF Metropolitan Mall, MG Road, Sector 28, Gurugram, Haryana 122002",
        "time_window": {"end": "15:00"},  # "deliver before" constraint
    },
    {
        "shipment_id": "SH004",
        "address": "Sector 14 Market, Sector 14, Gurugram, Haryana 122001",
        # no time_window at all - delivered last
    },
    {
        "shipment_id": "SH005",
        "address": "Galleria Market, DLF Phase 4, Gurugram, Haryana 122009",
        "time_window": {"start": "11:00", "end": "13:00"},  # ties with SH001
    },
    {
        "shipment_id": "SH006",
        "address": "HUDA City Centre, Sector 29, Gurugram, Haryana 122001",
        "time_window": {"start": "09:00", "end": "10:00"},  # tightest 1h window
    },
    {
        "shipment_id": "SH007",
        "address": "Kingdom of Dreams, Sector 29, Gurugram, Haryana 122001",
        "time_window": {"end": "12:30"},  # "deliver before" constraint
    },
    {
        "shipment_id": "SH008",
        "address": "Vatika Chowk, Sector 48, Sohna Road, Gurugram, Haryana 122018",
        # no time_window at all - delivered last
    },
    {
        "shipment_id": "SH009",
        "address": "DLF Cyber Greens, Sector 25A, Gurugram, Haryana 122002",
        "time_window": {"start": "16:00", "end": "18:00"},  # ties with SH001/SH005 on duration
    },
    {
        "shipment_id": "SH010",
        "address": "Sohna Road, Sector 49, Gurugram, Haryana 122018",
        "time_window": {"start": "08:00"},  # "deliver after" - start only
    },
]

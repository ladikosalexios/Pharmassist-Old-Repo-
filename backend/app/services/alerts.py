"""Active safety alerts (mock) for the dashboard."""


MOCK_ACTIVE_ALERTS = [
    {
        "id": "AL-1001",
        "type": "INTERACTION",
        "description": "Warfarin + Aspirin: high risk of bleeding. Immediate review required before dispensing.",
        "rxId": "RX2024-005",
        "createdAt": "2026-04-30T08:14:00Z",
    },
    {
        "id": "AL-1002",
        "type": "G6PD",
        "description": "Patient P003 has G6PD deficiency. Verify medication safety against current SPC.",
        "rxId": "RX2024-002",
        "createdAt": "2026-04-30T07:42:00Z",
    },
    {
        "id": "AL-1003",
        "type": "PREGNANCY",
        "description": "Patient P001 is 18 weeks pregnant. Check teratogenicity classification before approval.",
        "rxId": "RX2024-003",
        "createdAt": "2026-04-30T06:20:00Z",
    },
    {
        "id": "AL-1004",
        "type": "CONTRAINDICATION",
        "description": "Metformin contraindicated — patient eGFR < 30 ml/min recorded last week.",
        "rxId": None,
        "createdAt": "2026-04-29T18:05:00Z",
    },
]

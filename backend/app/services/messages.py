"""Pharmacist ↔ prescriber message threads (mock, keyed by rxId)."""

MOCK_MESSAGES: dict = {
    "RX2024-005": [
        {
            "id": "m-005-1",
            "rxId": "RX2024-005",
            "from": "pharmacist",
            "fromName": "Demo Pharmacist",
            "body": "Patient is currently on Aspirin 100 mg. Could you confirm the bleeding-risk plan and the INR monitoring schedule before I dispense?",
            "sentAt": "2026-04-29T14:30:00Z",
        },
        {
            "id": "m-005-2",
            "rxId": "RX2024-005",
            "from": "prescriber",
            "fromName": "Dr. Michael Chen",
            "body": "Yes — patient has a recent stent (12/2025). Please continue but stress INR every 3–5 days for the first two weeks. I've already booked the follow-up labs for next Monday.",
            "sentAt": "2026-04-29T16:12:00Z",
        },
    ],
}

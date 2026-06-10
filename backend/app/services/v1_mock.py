"""Mock fixtures for the B2B /v1 surface (PHARMAPI_MOCK=true).

Self-contained on purpose: the B2C mock stores (PATIENT_PROFILES, MOCK_QUEUE)
are shaped for the pharmacist UI; these are shaped exactly like the LIVE /v1
mappings so contract tests exercise the same response models in both modes.
Keys deliberately overlap the B2C demo patients (Maria Stavrou's AMKA matches
MOCK_INTOLERANCES, so the safety intolerance check fires in mock /v1 too) and
the seeded drug catalog (medicineBarcode 3661001 = warfarin seed row).
"""

# Keyed by the identifier a caller would pass: AMKA (11 digits) or EKAA.
MOCK_V1_PATIENTS: dict[str, dict] = {
    "15031962456": {
        "id": "15031962456",
        "amka": "15031962456",
        "ekaa": None,
        "first_name": "Maria",
        "last_name": "Stavrou",
        "date_of_birth": "1962-03-15",
        "age": 64,
        "sex": "F",
        "phone": "+30 694 312 3456",
        "nationality": "Ελληνική",
        "address": "Αριστοτέλους 22, Θεσσαλονίκη 546 24",
        # Live shape: /common/getpatient `patientPartExceptions` after the
        # clean_pharmapi_patient_data mapping (FT-2/D-9 — co-pay exemptions).
        "participation_exceptions": [
            {
                "id": 1,
                "reason": "Χρόνια πάθηση — μηδενική συμμετοχή",
                "effective_from": "2025-01-01",
                "effective_to": None,
            }
        ],
    },
    "08111947033": {
        "id": "08111947033",
        "amka": "08111947033",
        "ekaa": None,
        "first_name": "Nikos",
        "last_name": "Papadopoulos",
        "date_of_birth": "1947-11-08",
        "age": 78,
        "sex": "M",
        "phone": "+30 697 630 9415",
        "nationality": "Ελληνική",
        "address": "Γεωργίου Παπανδρέου 14, Θεσσαλονίκη 564 30",
    },
    # EKAA fixture — the European-card path had no mock coverage anywhere (audit
    # gap): B2C mock lookups are AMKA-only, so /v1 carries its own.
    "DE801234567890123456": {
        "id": "DE801234567890123456",
        "amka": None,
        "ekaa": "DE801234567890123456",
        "first_name": "Hans",
        "last_name": "Müller",
        "date_of_birth": "1958-02-11",
        "age": 68,
        "sex": "M",
        "phone": "+49 170 1234567",
        "nationality": "Γερμανική",
        "address": "Berliner Str. 12, Berlin",
    },
}

# Live shape: the upstream camelCase insurance dicts (PatientInsurancePayload
# validates these via its aliases). B2C mock returns [] — another parity gap
# /v1 doesn't inherit.
MOCK_V1_INSURANCES: dict[str, list[dict]] = {
    "15031962456": [
        {
            "id": 1,
            "memberType": {"id": 1, "name": "Άμεσα ασφαλισμένος"},
            "ama": "1234567",
            "updateDate": "2026-01-10",
            "directlyInsuredAmka": "15031962456",
            "fromEmaes": False,
            "lastActive": True,
            "isRetired": True,
            "socialInsurance": {"id": 1, "name": "ΕΟΠΥΥ", "shortName": "ΕΟΠΥΥ", "eopyy": True},
        }
    ],
    "08111947033": [
        {
            "id": 2,
            "memberType": {"id": 1, "name": "Άμεσα ασφαλισμένος"},
            "ama": "7654321",
            "updateDate": "2025-11-02",
            "directlyInsuredAmka": "08111947033",
            "fromEmaes": False,
            "lastActive": True,
            "isRetired": True,
            "socialInsurance": {"id": 1, "name": "ΕΟΠΥΥ", "shortName": "ΕΟΠΥΥ", "eopyy": True},
        }
    ],
}

# Live shape: _parse_page_xml_items output for the intolerances endpoint.
MOCK_V1_INTOLERANCES: dict[str, list[dict]] = {
    "15031962456": [
        {
            "activeSubstance": "AMOXICILLIN",
            "intolerance": "ΑΛΛΕΡΓΙΑ",
            "remarks": "Αναφυλαξία — καταγραφή 2019",
        }
    ],
}

# Live shape: services/patients._map_history_item output (camelCase keys).
MOCK_V1_MEDICINE_HISTORY: dict[str, list[dict]] = {
    "15031962456": [
        {
            "rxId": "1262602210000000",
            "date": "2026-04-28",
            "drugName": "PANADOL 500MG/TAB",
            "prescriberName": None,
            "status": "COMPLETED",
            "quantityPrescribed": "2",
            "quantityOutstanding": "0",
            "euDispensed": False,
        },
        {
            "rxId": "1262602210000001",
            "date": "2026-03-02",
            "drugName": "ZINADOL 500MG/TAB",
            "prescriberName": None,
            "status": "COMPLETED",
            "quantityPrescribed": "1",
            "quantityOutstanding": "0",
            "euDispensed": False,
        },
    ],
}

# Live shape: _parse_prescription_search_json output. medicineBarcode values
# point at seeded drug_catalog rows so safety/formulary flows resolve ATCs.
MOCK_V1_PRESCRIPTIONS: list[dict] = [
    {
        "rxId": "1262602210000100",
        "patientName": "Maria Stavrou",
        "patientAmka": "15031962456",
        "medication": "Warfarin 5 mg",
        "medicineBarcode": "3661001",
        "physician": "Dr. Michael Chen",
        "date": "2026-06-01",
        "expiryDate": "2026-07-01",
        "status": "PENDING",
        "socialInsurance": "ΕΟΠΥΥ",
        "pharmApiStatus": "PENDING",
        "repeatNo": 1,
        "totalRepeats": 1,
    },
    {
        "rxId": "1262602210000101",
        "patientName": "Nikos Papadopoulos",
        "patientAmka": "08111947033",
        "medication": "Aspirin 100 mg",
        "medicineBarcode": "3661002",
        "physician": "Dr. Anna Kostas",
        "date": "2026-06-02",
        "expiryDate": "2026-07-02",
        "status": "PENDING",
        "socialInsurance": "ΕΟΠΥΥ",
        "pharmApiStatus": "PENDING",
        "repeatNo": 1,
        "totalRepeats": 1,
    },
    {
        "rxId": "1262602210000102",
        "patientName": "Maria Stavrou",
        "patientAmka": "15031962456",
        "medication": "Atorvastatin 20 mg",
        "medicineBarcode": "3661006",
        "physician": "Dr. Michael Chen",
        "date": "2026-05-12",
        "expiryDate": "2026-06-12",
        "status": "COMPLETED",
        "socialInsurance": "ΕΟΠΥΥ",
        "pharmApiStatus": "EXECUTED",
        "repeatNo": 1,
        "totalRepeats": 1,
    },
]

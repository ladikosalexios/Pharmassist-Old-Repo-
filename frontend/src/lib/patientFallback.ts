// Mirror of the backend's _PATIENT_PROFILES + per-patient histories.
// Used by the Patient Profile page when the API returns nothing useful or
// hasn't yet been restarted to pick up the expanded /patients endpoints.

import type {
  PatientCondition,
  PatientProfile,
  PatientRxHistoryRow,
  SideEffectReport,
} from "../types";

interface PatientBundle {
  profile: PatientProfile;
  rxHistory: PatientRxHistoryRow[];
  adrHistory: SideEffectReport[];
  conditions: PatientCondition[];
}

const PROFILES: PatientProfile[] = [
  {
    id: "15031962456",
    amka: "15031962456",
    firstName: "Maria",
    lastName: "Stavrou",
    name: "Maria Stavrou",
    dateOfBirth: "1962-03-15",
    age: 64,
    sex: "F",
    phone: "+30 694 312 3456",
    conditions: ["Type II Diabetes", "Hypertension", "Hyperlipidemia"],
    allergies: ["Penicillin (anaphylaxis)", "Sulfa drugs"],
    intolerances: ["Lactose"],
    safetyFlags: {
      g6pd: false,
      pregnancyWeeks: null,
      renalFunction: "MILD_IMPAIRMENT",
      hepaticFunction: "NORMAL",
      breastfeeding: false,
    },
  },
  {
    id: "08111974201",
    amka: "08111974201",
    firstName: "Eleni",
    lastName: "Papadopoulos",
    name: "Eleni Papadopoulos",
    dateOfBirth: "1974-11-08",
    age: 51,
    sex: "F",
    phone: "+30 697 555 0142",
    conditions: ["Atrial fibrillation"],
    allergies: [],
    intolerances: [],
    safetyFlags: {
      g6pd: false,
      pregnancyWeeks: null,
      renalFunction: "NORMAL",
      hepaticFunction: "NORMAL",
      breastfeeding: false,
    },
  },
  {
    id: "22071993789",
    amka: "22071993789",
    firstName: "Sarah",
    lastName: "Johnson",
    name: "Sarah Johnson",
    dateOfBirth: "1993-07-22",
    age: 32,
    sex: "F",
    phone: "+30 698 011 2233",
    conditions: ["Bacterial sinusitis"],
    allergies: [],
    intolerances: [],
    safetyFlags: {
      g6pd: false,
      pregnancyWeeks: 18,
      renalFunction: "NORMAL",
      hepaticFunction: "NORMAL",
      breastfeeding: false,
    },
  },
  {
    id: "03051961334",
    amka: "03051961334",
    firstName: "Dimitrios",
    lastName: "Konstantinou",
    name: "Dimitrios Konstantinou",
    dateOfBirth: "1961-05-03",
    age: 64,
    sex: "M",
    phone: "+30 698 555 7012",
    conditions: ["Hyperlipidemia", "Coronary artery disease"],
    allergies: [],
    intolerances: [],
    safetyFlags: {
      g6pd: false,
      pregnancyWeeks: null,
      renalFunction: "NORMAL",
      hepaticFunction: "MODERATE_IMPAIRMENT",
      breastfeeding: false,
    },
  },
  {
    id: "12101948112",
    amka: "12101948112",
    firstName: "Anna",
    lastName: "Kostas",
    name: "Anna Kostas",
    dateOfBirth: "1948-10-12",
    age: 77,
    sex: "F",
    phone: "+30 697 999 0011",
    conditions: ["Coronary stent (2025)", "Atrial fibrillation"],
    allergies: [],
    intolerances: [],
    safetyFlags: {
      g6pd: false,
      pregnancyWeeks: null,
      renalFunction: "MODERATE_IMPAIRMENT",
      hepaticFunction: "NORMAL",
      breastfeeding: false,
    },
  },
  {
    id: "27021982557",
    amka: "27021982557",
    firstName: "Nikos",
    lastName: "Vlachos",
    name: "Nikos Vlachos",
    dateOfBirth: "1982-02-27",
    age: 43,
    sex: "M",
    phone: "+30 698 222 0099",
    conditions: ["Type II Diabetes"],
    allergies: ["Aspirin (urticaria)"],
    intolerances: [],
    safetyFlags: {
      g6pd: true,
      pregnancyWeeks: null,
      renalFunction: "NORMAL",
      hepaticFunction: "NORMAL",
      breastfeeding: false,
    },
  },
];

const RX_HISTORY: Record<string, PatientRxHistoryRow[]> = {
  15031962456: [
    {
      rxId: "RX2024-005",
      date: "2026-04-28",
      drugName: "Warfarin 5 mg",
      prescriberName: "Dr. Michael Chen",
      status: "PENDING",
    },
    {
      rxId: "RX2023-118",
      date: "2025-11-12",
      drugName: "Atorvastatin 20 mg",
      prescriberName: "Dr. Michael Chen",
      status: "COMPLETED",
    },
    {
      rxId: "RX2023-077",
      date: "2025-09-03",
      drugName: "Metformin 1000 mg",
      prescriberName: "Dr. Maria Lampraki",
      status: "COMPLETED",
    },
    {
      rxId: "RX2023-022",
      date: "2025-04-19",
      drugName: "Ramipril 5 mg",
      prescriberName: "Dr. Maria Lampraki",
      status: "COMPLETED",
    },
  ],
  "08111974201": [
    {
      rxId: "RX2024-002",
      date: "2026-03-11",
      drugName: "Warfarin 7.5 mg",
      prescriberName: "Dr. Emily Roberts",
      status: "FLAGGED",
    },
    {
      rxId: "RX2023-054",
      date: "2025-08-20",
      drugName: "Bisoprolol 5 mg",
      prescriberName: "Dr. Emily Roberts",
      status: "COMPLETED",
    },
  ],
  "22071993789": [
    {
      rxId: "RX2024-001",
      date: "2026-03-11",
      drugName: "Amoxicillin 500 mg",
      prescriberName: "Dr. Michael Chen",
      status: "PENDING",
    },
  ],
  "03051961334": [
    {
      rxId: "RX2023-091",
      date: "2025-12-08",
      drugName: "Atorvastatin 20 mg",
      prescriberName: "Dr. David Lee",
      status: "COMPLETED",
    },
    {
      rxId: "RX2023-044",
      date: "2025-06-14",
      drugName: "Aspirin 100 mg",
      prescriberName: "Dr. David Lee",
      status: "COMPLETED",
    },
  ],
  "12101948112": [
    {
      rxId: "RX2023-066",
      date: "2025-09-30",
      drugName: "Clopidogrel 75 mg",
      prescriberName: "Dr. Sophia Roussou",
      status: "COMPLETED",
    },
  ],
  "27021982557": [
    {
      rxId: "RX2023-032",
      date: "2025-05-18",
      drugName: "Metformin 1000 mg",
      prescriberName: "Dr. Niko Pateli",
      status: "COMPLETED",
    },
  ],
};

const ADR_HISTORY: Record<string, SideEffectReport[]> = {
  "15031962456": [
    {
      id: "ADR-2026-0009",
      patientId: "15031962456",
      patientName: "Maria Stavrou",
      patientPhone: "+30 694 312 3456",
      rxId: "RX2024-005",
      drugName: "Warfarin 5 mg",
      severity: "SEVERE",
      status: "ESCALATED",
      reportedAt: "2026-04-29T16:42:00+00:00",
      symptom: "Dark stools, dizziness on standing, gum bleeding after brushing teeth.",
      onset: "8 hours after the second dose",
    },
  ],
  "08111974201": [
    {
      id: "ADR-2026-0008",
      patientId: "08111974201",
      patientName: "Eleni Papadopoulos",
      patientPhone: "+30 697 555 0142",
      rxId: "RX2024-002",
      drugName: "Warfarin 7.5 mg",
      severity: "MODERATE",
      status: "PENDING_REVIEW",
      reportedAt: "2026-04-28T11:05:00+00:00",
      symptom: "Persistent nosebleeds and unusual bruising on forearms.",
      onset: "Within 48 hours of dose increase",
    },
  ],
  "22071993789": [
    {
      id: "ADR-2026-0007",
      patientId: "22071993789",
      patientName: "Sarah Johnson",
      patientPhone: "+30 698 011 2233",
      rxId: "RX2024-001",
      drugName: "Amoxicillin 500 mg",
      severity: "MILD",
      status: "PENDING_REVIEW",
      reportedAt: "2026-04-26T08:20:00+00:00",
      symptom: "Diffuse maculopapular rash on torso, no breathing difficulty.",
      onset: "Day 3 of antibiotic course",
    },
  ],
  "03051961334": [
    {
      id: "ADR-2026-0006",
      patientId: "03051961334",
      patientName: "Dimitrios Konstantinou",
      patientPhone: "+30 698 555 7012",
      rxId: null,
      drugName: "Atorvastatin 20 mg",
      severity: "SEVERE",
      status: "EOF_REPORTED",
      reportedAt: "2026-04-22T19:14:00+00:00",
      symptom: "Generalised muscle pain, dark urine, ALT 5x upper limit.",
      onset: "Three weeks after starting therapy",
    },
  ],
  "12101948112": [
    {
      id: "ADR-2026-0005",
      patientId: "12101948112",
      patientName: "Anna Kostas",
      patientPhone: "+30 697 999 0011",
      rxId: null,
      drugName: "Clopidogrel 75 mg",
      severity: "MODERATE",
      status: "ESCALATED",
      reportedAt: "2026-04-15T12:00:00+00:00",
      symptom: "Two episodes of melena, mild dyspnoea on exertion.",
      onset: "Two weeks into therapy",
    },
  ],
  "27021982557": [
    {
      id: "ADR-2026-0004",
      patientId: "27021982557",
      patientName: "Nikos Vlachos",
      patientPhone: "+30 698 222 0099",
      rxId: null,
      drugName: "Metformin 1000 mg",
      severity: "MILD",
      status: "EOF_REPORTED",
      reportedAt: "2026-03-30T10:30:00+00:00",
      symptom: "Mild gastrointestinal upset and metallic taste.",
      onset: "First week of therapy",
    },
  ],
};

const CONDITIONS: Record<string, PatientCondition[]> = {
  "15031962456": [
    {
      conditionCode: "G6PD",
      name: "Glucose-6-phosphate dehydrogenase deficiency",
      amka: "15031962456",
      notes:
        "Confirmatory enzyme assay positive (2024). Patient also has mild renal impairment — review dose adjustments for all renally-cleared agents.",
      pharmacyId: "e6d9f9cc-65da-4400-8194-fdd99ecace92",
      createdAt: "2026-05-11T17:45:03.373179+00:00",
      severity: "MODERATE",
      id: "7cec3ae6-dcec-46f2-ab4d-1e293ce858a0",
      recordedBy: "b77e5118-59e1-4318-9d3d-5d1de2e26c25",
      active: true,
      updatedAt: "2026-05-11T17:45:03.373179+00:00",
    },
  ],
  "08111974201": [
    {
      conditionCode: "I48.0",
      name: "Paroxysmal atrial fibrillation",
      amka: "08111974201",
      notes: "Long-standing AF; rate-controlled on bisoprolol. Anticoagulation initiated 2025.",
      pharmacyId: "e6d9f9cc-65da-4400-8194-fdd99ecace92",
      createdAt: "2025-03-04T09:12:47.821033+00:00",
      severity: "MODERATE",
      id: "a2f14c8b-3d72-4e91-b605-8c3a1f9e2d47",
      recordedBy: "b77e5118-59e1-4318-9d3d-5d1de2e26c25",
      active: true,
      updatedAt: "2025-03-04T09:12:47.821033+00:00",
    },
  ],
  "22071993789": [
    {
      conditionCode: "J01.0",
      name: "Acute maxillary sinusitis",
      amka: "22071993789",
      notes:
        "Current episode; antibiotic course initiated. Patient 18 weeks pregnant — beta-lactam selected.",
      pharmacyId: "e6d9f9cc-65da-4400-8194-fdd99ecace92",
      createdAt: "2026-03-09T14:30:15.002100+00:00",
      severity: "MILD",
      id: "b83e20d1-9c54-4fa3-a712-5d6b07c4e318",
      recordedBy: "b77e5118-59e1-4318-9d3d-5d1de2e26c25",
      active: true,
      updatedAt: "2026-03-09T14:30:15.002100+00:00",
    },
  ],
  "03051961334": [
    {
      conditionCode: "I25.1",
      name: "Atherosclerotic coronary artery disease",
      amka: "03051961334",
      notes:
        "Stable CAD; on dual therapy (statin + antiplatelet). Moderate hepatic impairment — dose adjustments applied.",
      pharmacyId: "e6d9f9cc-65da-4400-8194-fdd99ecace92",
      createdAt: "2024-11-18T08:55:22.441200+00:00",
      severity: "SEVERE",
      id: "c49a17f3-6b80-4d2e-9038-2e5c84b1f762",
      recordedBy: "b77e5118-59e1-4318-9d3d-5d1de2e26c25",
      active: true,
      updatedAt: "2024-11-18T08:55:22.441200+00:00",
    },
  ],
  "12101948112": [
    {
      conditionCode: "Z95.5",
      name: "Presence of coronary angioplasty implant",
      amka: "12101948112",
      notes:
        "Drug-eluting stent placed 2025; dual antiplatelet therapy ongoing. Concurrent AF — anticoagulation under review.",
      pharmacyId: "e6d9f9cc-65da-4400-8194-fdd99ecace92",
      createdAt: "2025-06-03T11:20:09.883500+00:00",
      severity: "MODERATE",
      id: "d5072c6e-1a39-48b7-bf94-7f3d92e05a81",
      recordedBy: "b77e5118-59e1-4318-9d3d-5d1de2e26c25",
      active: true,
      updatedAt: "2025-06-03T11:20:09.883500+00:00",
    },
  ],
  "27021982557": [
    {
      conditionCode: "E11.9",
      name: "Type 2 diabetes mellitus without complications",
      amka: "27021982557",
      notes:
        "Managed with metformin. G6PD deficiency noted in safety flags — avoid oxidative-stress agents.",
      pharmacyId: "e6d9f9cc-65da-4400-8194-fdd99ecace92",
      createdAt: "2024-08-22T16:07:34.110400+00:00",
      severity: "MILD",
      id: "e6183d7a-2b41-4c58-8e25-9a0f61c73b95",
      recordedBy: "b77e5118-59e1-4318-9d3d-5d1de2e26c25",
      active: true,
      updatedAt: "2024-08-22T16:07:34.110400+00:00",
    },
  ],
};

export function fallbackForPatient(key: string): PatientBundle | null {
  const profile = PROFILES.find((p) => p.id === key || p.amka === key);
  if (!profile) return null;
  return {
    profile,
    rxHistory: RX_HISTORY[profile.id] ?? [],
    adrHistory: ADR_HISTORY[profile.id] ?? [],
    conditions: CONDITIONS[profile.id] ?? [],
  };
}

/** True when the live response is missing the fields the new page UI relies on. */
export function isProfileShapeIncomplete(p: PatientProfile | null | undefined): boolean {
  if (!p) return true;
  return p.amka == null || p.safetyFlags == null || p.conditions == null || p.allergies == null;
}

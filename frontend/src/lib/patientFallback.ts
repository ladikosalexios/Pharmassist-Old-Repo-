// Mirror of the backend's _PATIENT_PROFILES + per-patient histories.
// Used by the Patient Profile page when the API returns nothing useful or
// hasn't yet been restarted to pick up the expanded /patients endpoints.

import type { PatientProfile, PatientRxHistoryRow, SideEffectReport } from "../types";

interface PatientBundle {
  profile: PatientProfile;
  rxHistory: PatientRxHistoryRow[];
  adrHistory: SideEffectReport[];
}

const PROFILES: PatientProfile[] = [
  {
    id: "P001", amka: "15031962456",
    firstName: "Maria", lastName: "Stavrou", name: "Maria Stavrou",
    dateOfBirth: "1962-03-15", age: 64, sex: "F", phone: "+30 694 312 3456",
    conditions: ["Type II Diabetes", "Hypertension", "Hyperlipidemia"],
    allergies: ["Penicillin (anaphylaxis)", "Sulfa drugs"],
    intolerances: ["Lactose"],
    safetyFlags: { g6pd: false, pregnancyWeeks: null, renalFunction: "MILD_IMPAIRMENT", hepaticFunction: "NORMAL", breastfeeding: false },
  },
  {
    id: "P004", amka: "08111974201",
    firstName: "Eleni", lastName: "Papadopoulos", name: "Eleni Papadopoulos",
    dateOfBirth: "1974-11-08", age: 51, sex: "F", phone: "+30 697 555 0142",
    conditions: ["Atrial fibrillation"],
    allergies: [],
    intolerances: [],
    safetyFlags: { g6pd: false, pregnancyWeeks: null, renalFunction: "NORMAL", hepaticFunction: "NORMAL", breastfeeding: false },
  },
  {
    id: "P010", amka: "22071993789",
    firstName: "Sarah", lastName: "Johnson", name: "Sarah Johnson",
    dateOfBirth: "1993-07-22", age: 32, sex: "F", phone: "+30 698 011 2233",
    conditions: ["Bacterial sinusitis"],
    allergies: [],
    intolerances: [],
    safetyFlags: { g6pd: false, pregnancyWeeks: 18, renalFunction: "NORMAL", hepaticFunction: "NORMAL", breastfeeding: false },
  },
  {
    id: "P012", amka: "03051961334",
    firstName: "Dimitrios", lastName: "Konstantinou", name: "Dimitrios Konstantinou",
    dateOfBirth: "1961-05-03", age: 64, sex: "M", phone: "+30 698 555 7012",
    conditions: ["Hyperlipidemia", "Coronary artery disease"],
    allergies: [],
    intolerances: [],
    safetyFlags: { g6pd: false, pregnancyWeeks: null, renalFunction: "NORMAL", hepaticFunction: "MODERATE_IMPAIRMENT", breastfeeding: false },
  },
  {
    id: "P020", amka: "12101948112",
    firstName: "Anna", lastName: "Kostas", name: "Anna Kostas",
    dateOfBirth: "1948-10-12", age: 77, sex: "F", phone: "+30 697 999 0011",
    conditions: ["Coronary stent (2025)", "Atrial fibrillation"],
    allergies: [],
    intolerances: [],
    safetyFlags: { g6pd: false, pregnancyWeeks: null, renalFunction: "MODERATE_IMPAIRMENT", hepaticFunction: "NORMAL", breastfeeding: false },
  },
  {
    id: "P031", amka: "27021982557",
    firstName: "Nikos", lastName: "Vlachos", name: "Nikos Vlachos",
    dateOfBirth: "1982-02-27", age: 43, sex: "M", phone: "+30 698 222 0099",
    conditions: ["Type II Diabetes"],
    allergies: ["Aspirin (urticaria)"],
    intolerances: [],
    safetyFlags: { g6pd: true, pregnancyWeeks: null, renalFunction: "NORMAL", hepaticFunction: "NORMAL", breastfeeding: false },
  },
];

const RX_HISTORY: Record<string, PatientRxHistoryRow[]> = {
  P001: [
    { rxId: "RX2024-005", date: "2026-04-28", drugName: "Warfarin 5 mg",      prescriberName: "Dr. Michael Chen",   status: "PENDING" },
    { rxId: "RX2023-118", date: "2025-11-12", drugName: "Atorvastatin 20 mg", prescriberName: "Dr. Michael Chen",   status: "COMPLETED" },
    { rxId: "RX2023-077", date: "2025-09-03", drugName: "Metformin 1000 mg",  prescriberName: "Dr. Maria Lampraki", status: "COMPLETED" },
    { rxId: "RX2023-022", date: "2025-04-19", drugName: "Ramipril 5 mg",      prescriberName: "Dr. Maria Lampraki", status: "COMPLETED" },
  ],
  P004: [
    { rxId: "RX2024-002", date: "2026-03-11", drugName: "Warfarin 7.5 mg",    prescriberName: "Dr. Emily Roberts",  status: "FLAGGED" },
    { rxId: "RX2023-054", date: "2025-08-20", drugName: "Bisoprolol 5 mg",    prescriberName: "Dr. Emily Roberts",  status: "COMPLETED" },
  ],
  P010: [
    { rxId: "RX2024-001", date: "2026-03-11", drugName: "Amoxicillin 500 mg", prescriberName: "Dr. Michael Chen",   status: "PENDING" },
  ],
  P012: [
    { rxId: "RX2023-091", date: "2025-12-08", drugName: "Atorvastatin 20 mg", prescriberName: "Dr. David Lee",      status: "COMPLETED" },
    { rxId: "RX2023-044", date: "2025-06-14", drugName: "Aspirin 100 mg",     prescriberName: "Dr. David Lee",      status: "COMPLETED" },
  ],
  P020: [
    { rxId: "RX2023-066", date: "2025-09-30", drugName: "Clopidogrel 75 mg",  prescriberName: "Dr. Sophia Roussou", status: "COMPLETED" },
  ],
  P031: [
    { rxId: "RX2023-032", date: "2025-05-18", drugName: "Metformin 1000 mg",  prescriberName: "Dr. Niko Pateli",    status: "COMPLETED" },
  ],
};

const ADR_HISTORY: Record<string, SideEffectReport[]> = {
  P001: [{
    id: "ADR-2026-0009", patientId: "P001", patientName: "Maria Stavrou", patientPhone: "+30 694 312 3456",
    rxId: "RX2024-005", drugName: "Warfarin 5 mg", severity: "SEVERE", status: "ESCALATED",
    reportedAt: "2026-04-29T16:42:00+00:00",
    symptom: "Dark stools, dizziness on standing, gum bleeding after brushing teeth.",
    onset: "8 hours after the second dose",
  }],
  P004: [{
    id: "ADR-2026-0008", patientId: "P004", patientName: "Eleni Papadopoulos", patientPhone: "+30 697 555 0142",
    rxId: "RX2024-002", drugName: "Warfarin 7.5 mg", severity: "MODERATE", status: "PENDING_REVIEW",
    reportedAt: "2026-04-28T11:05:00+00:00",
    symptom: "Persistent nosebleeds and unusual bruising on forearms.",
    onset: "Within 48 hours of dose increase",
  }],
  P010: [{
    id: "ADR-2026-0007", patientId: "P010", patientName: "Sarah Johnson", patientPhone: "+30 698 011 2233",
    rxId: "RX2024-001", drugName: "Amoxicillin 500 mg", severity: "MILD", status: "PENDING_REVIEW",
    reportedAt: "2026-04-26T08:20:00+00:00",
    symptom: "Diffuse maculopapular rash on torso, no breathing difficulty.",
    onset: "Day 3 of antibiotic course",
  }],
  P012: [{
    id: "ADR-2026-0006", patientId: "P012", patientName: "Dimitrios Konstantinou", patientPhone: "+30 698 555 7012",
    rxId: null, drugName: "Atorvastatin 20 mg", severity: "SEVERE", status: "EOF_REPORTED",
    reportedAt: "2026-04-22T19:14:00+00:00",
    symptom: "Generalised muscle pain, dark urine, ALT 5x upper limit.",
    onset: "Three weeks after starting therapy",
  }],
  P020: [{
    id: "ADR-2026-0005", patientId: "P020", patientName: "Anna Kostas", patientPhone: "+30 697 999 0011",
    rxId: null, drugName: "Clopidogrel 75 mg", severity: "MODERATE", status: "ESCALATED",
    reportedAt: "2026-04-15T12:00:00+00:00",
    symptom: "Two episodes of melena, mild dyspnoea on exertion.",
    onset: "Two weeks into therapy",
  }],
  P031: [{
    id: "ADR-2026-0004", patientId: "P031", patientName: "Nikos Vlachos", patientPhone: "+30 698 222 0099",
    rxId: null, drugName: "Metformin 1000 mg", severity: "MILD", status: "EOF_REPORTED",
    reportedAt: "2026-03-30T10:30:00+00:00",
    symptom: "Mild gastrointestinal upset and metallic taste.",
    onset: "First week of therapy",
  }],
};

export function fallbackForPatient(key: string): PatientBundle | null {
  const profile = PROFILES.find((p) => p.id === key || p.amka === key);
  if (!profile) return null;
  return {
    profile,
    rxHistory: RX_HISTORY[profile.id] ?? [],
    adrHistory: ADR_HISTORY[profile.id] ?? [],
  };
}

/** True when the live response is missing the fields the new page UI relies on. */
export function isProfileShapeIncomplete(p: PatientProfile | null | undefined): boolean {
  if (!p) return true;
  return p.amka == null || p.safetyFlags == null || p.conditions == null || p.allergies == null;
}

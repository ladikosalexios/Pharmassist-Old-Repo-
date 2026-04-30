export type CheckStatus = "ok" | "review" | "block";

export interface Patient {
  id: string;
  name: string;
  age: number;
  dateOfBirth: string;
  amka: string;
  conditions: string[];
  allergies: string;
}

export interface Medication {
  drugName: string;
  dose: string;
  form: string;
  route: string;
  frequency: string;
  treatmentDuration: string;
  spcRecommendedDosage: string;
}

export interface Prescriber {
  name: string;
  licenceId: string;
  specialty: string;
  contact: string;
  email: string;
}

export interface Interaction {
  drug: string;
  effect: string;
}

export interface SpcQuickReference {
  contraindications: string[];
  majorInteractions: Interaction[];
}

export interface SafetyCheck {
  id: string;
  name: string;
  status: CheckStatus;
  message: string;
  details?: string;
  recommendedAction?: string | null;
}

export interface Prescription {
  rxId: string;
  code: string;
  dateIssued: string;
  status: string;
  spcVersion: string;
  patient: Patient;
  medication: Medication;
  prescriber: Prescriber;
  spcQuickReference: SpcQuickReference;
  safetyChecks: SafetyCheck[];
  flagReason?: string;
}

export interface QueueItem {
  rxId: string;
  patientName: string;
  medication: string;
  physician: string;
  date: string;
  status: "PENDING" | "FLAGGED" | "APPROVED";
}

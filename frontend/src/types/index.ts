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
  atcCode?: string;
  dose: string;
  form: string;
  route: string;
  frequency: string;
  treatmentDuration: string;
  spcRecommendedDosage: string;
}

export interface SpcDetails {
  atcCode: string;
  drugName: string;
  version: string;
  updatedAt: string;
  fullSpcUrl?: string | null;
  fullSpcText?: string | null;
  recommendedDosage: string;
  contraindications: string[];
  majorInteractions: Interaction[];
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

export type PrescriptionStatus = "PENDING" | "FLAGGED" | "COMPLETED";

export interface QueueItem {
  rxId: string;
  patientName: string;
  medication: string;
  physician: string;
  date: string;
  status: PrescriptionStatus;
}

export type AlertType = "INTERACTION" | "G6PD" | "PREGNANCY" | "CONTRAINDICATION";

export interface ActiveAlert {
  id: string;
  type: AlertType;
  description: string;
  rxId?: string | null;
  createdAt: string;
}

export type DeliveryMethod = "PRINT" | "DIGITAL" | "BOTH";
export type DeliveryMethodFilter = DeliveryMethod | "ALL";

export interface DocumentationRecord {
  id: string;
  rxId: string;
  patientName: string;
  drugName: string;
  setting: "Private" | "Hospital";
  deliveryMethod: DeliveryMethod;
  language: string;
  informationProvided: string;
  pharmacistName: string;
  pharmacistLicense: string;
  signatureConfirmed: boolean;
  dispensedAt: string;
}

export interface DocumentationStats {
  total: number;
  print: number;
  digital: number;
  both: number;
}

export interface DocumentationListResponse {
  items: DocumentationRecord[];
  total: number;
  stats: DocumentationStats;
}

export interface PrescriptionMessage {
  id: string;
  rxId: string;
  from: "pharmacist" | "prescriber";
  fromName: string;
  body: string;
  sentAt: string;
  to?: string;
}

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
  nhrn?: string;
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

export type AlertType =
  | "interactions"
  | "contraindications"
  | "duplicate_therapy"
  | "dose_validation"
  | "pregnancy"
  | "G6PD";

export interface ActiveAlert {
  id: string;
  type: AlertType;
  status: CheckStatus;
  description: string;
  rxId?: string | null;
  createdAt: string | null;
}

export type InstructionsLanguage = "el" | "en" | "other";

export interface InstructionsOptions {
  additionalNotes?: string;
  includeSideEffects: boolean;
  includeLifestyle: boolean;
}

export interface GeneratedInstructions {
  rxId: string;
  language: string;
  content: string;
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

export type AdrSeverity = "MILD" | "MODERATE" | "SEVERE";
export type AdrStatus = "PENDING_REVIEW" | "ESCALATED" | "EOF_REPORTED";
export type AdrSort = "date" | "severity" | "status";

export interface SideEffectReport {
  id: string;
  patientId: string;
  patientName: string;
  patientPhone?: string | null;
  rxId?: string | null;
  drugName: string;
  severity: AdrSeverity;
  status: AdrStatus;
  reportedAt: string;
  symptom: string;
  onset: string;
  lastFlaggedAt?: string | null;
}

export interface SideEffectStats {
  total: number;
  pendingReview: number;
  severe: number;
  escalated: number;
}

export interface SideEffectListResponse {
  items: SideEffectReport[];
  stats: SideEffectStats;
}

export interface PatientCondition {
  id: string;
  amka: string;
  conditionCode: string;
  name: string;
  notes: string;
  pharmacyId: string;
  createdAt: string;
  severity: string;
  recordedBy: string;
  active: boolean;
  updatedAt: string;
}

export type OrganFunction =
  | "NORMAL"
  | "MILD_IMPAIRMENT"
  | "MODERATE_IMPAIRMENT"
  | "SEVERE_IMPAIRMENT";

export interface PatientSafetyFlags {
  g6pd: boolean;
  pregnancyWeeks: number | null;
  renalFunction: OrganFunction;
  hepaticFunction: OrganFunction;
  breastfeeding: boolean;
}

export interface PatientProfile {
  id: string;
  amka?: string;
  firstName?: string;
  lastName?: string;
  name: string;
  dateOfBirth?: string;
  age?: number;
  sex?: "F" | "M" | string;
  phone?: string | null;
  nationality?: string | null;
  address?: string | null;
  email?: string | null;
  conditions?: string[];
  allergies?: string[];
  intolerances?: string[];
  safetyFlags?: PatientSafetyFlags;
}

export interface PatientRxHistoryRow {
  rxId: string;
  date: string;
  drugName: string;
  prescriberName: string;
  status: PrescriptionStatus | string;
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

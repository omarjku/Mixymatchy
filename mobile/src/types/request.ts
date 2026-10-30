import type { RoleId } from "@/data/roles";
import type { PatientBrief } from "@/types/fact";

// What the start screen hands to the loading/results flow (route state). Not part of the backend contract.

export type DeliveryMode = "display" | "speak";

export interface BriefRequest {
  role: RoleId;
  task: string;
  readAloud: boolean; // true when the clinician chose "Vorlesen" mode
}

// What the loading screen hands to the results screen.
export interface ResultsState {
  brief: PatientBrief;
  readAloud: boolean;
}

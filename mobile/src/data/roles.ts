import type { StringKey } from "@/i18n/strings";

// "other": the typed text is sent as the whole situation (any role the jury tries, e.g. "Dietitian reviewing her weight").
export type RoleId = "anaesthetist" | "pharmacist" | "surgeon" | "gp" | "emergency" | "other";

export interface RoleConfig {
  id: RoleId;
  nameKey: StringKey;
  descriptionKey: StringKey;
  taskPresetKeys: StringKey[];
}

export const roles: RoleConfig[] = [
  {
    id: "anaesthetist",
    nameKey: "role.anaesthetist.name",
    descriptionKey: "role.anaesthetist.description",
    taskPresetKeys: ["task.anaesthetist.breast", "task.anaesthetist.hip", "task.anaesthetist.general"],
  },
  {
    id: "pharmacist",
    nameKey: "role.pharmacist.name",
    descriptionKey: "role.pharmacist.description",
    taskPresetKeys: ["task.pharmacist.polypharmacy", "task.pharmacist.renal", "task.pharmacist.admission"],
  },
  {
    id: "surgeon",
    nameKey: "role.surgeon.name",
    descriptionKey: "role.surgeon.description",
    taskPresetKeys: ["task.surgeon.hip", "task.surgeon.breast", "task.surgeon.hernia"],
  },
  {
    id: "gp",
    nameKey: "role.gp.name",
    descriptionKey: "role.gp.description",
    taskPresetKeys: ["task.gp.discharge", "task.gp.chronic", "task.gp.medication"],
  },
  {
    id: "emergency",
    nameKey: "role.emergency.name",
    descriptionKey: "role.emergency.description",
    taskPresetKeys: ["task.emergency.neuro", "task.emergency.contrast"],
  },
  {
    id: "other",
    nameKey: "role.other.name",
    descriptionKey: "role.other.description",
    taskPresetKeys: [],
  },
];

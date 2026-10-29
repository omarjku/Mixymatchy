import type { StringKey } from "@/i18n/strings";

export type RoleId = "anaesthetist" | "pharmacist" | "surgeon" | "gp";

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
];

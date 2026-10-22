import type { Member } from "./types";

// Filled from the API whenever a group's state arrives. Components read these through memberById, so avatars and names stay in step with the roster.
export const GROUP = { name: "", currency: "USD", contribution: 50, cycleDays: 14, cycles: 0, currentCycle: 1, organiser: "" };
export const MEMBERS: Member[] = [];
const UNKNOWN: Member = { id: "", name: "Someone", first: "Someone", role: "member", hue: 200, email: "", turn: 0 };
export const memberById = (id: string): Member => MEMBERS.find((m) => m.id === id) ?? { ...UNKNOWN, id };

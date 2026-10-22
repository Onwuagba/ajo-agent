export type Tone = "good" | "warn" | "bad" | "info" | "agent";

export interface Member { id: string; name: string; first: string; role: "organiser" | "member"; hue: number; email: string; turn: number; sandbox?: boolean; paypal?: "linked" | "pending" }
export interface Account { id: string; name: string; email: string; sandbox: boolean }
export interface GroupSummary { id: string; name: string; status: "forming" | "starting" | "active" | "complete"; role: "organiser" | "member"; members: number; size: number }
export interface GroupMeta { id: string; name: string; currency: string; status: "forming" | "starting" | "active" | "complete"; treasurer: boolean; size: number }
export interface Invite { code: string; name: string; email: string; status: "pending" | "accepted" }
export interface InviteInfo { code: string; status: "pending" | "accepted" | "revoked" | "closed"; forName: string; group: string; organiser: string; contribution: number; currency: string; cycleDays: number; size: number; joined: number }

export interface Check { label: string; pass: boolean; detail: string }

export type LedgerKind = "contribution" | "payout" | "invoice" | "invoice_payment" | "repayment" | "reminder";
export type LedgerStatus = "completed" | "pending" | "failed" | "awaiting_approval" | "sent";

export interface LedgerRow {
  id: string; cycle: number; kind: LedgerKind; member: string; amount: number; status: LedgerStatus; ts: number;
  paypalId: string; ruleVersion: number; rule: string; approver?: string; simulated?: boolean; explanation: string; checks: Check[];
}

export interface Cycle { n: number; date: string; recipient: string; pot: number; status: "paid" | "collecting" | "upcoming" }

export interface TimelineEvent { id: string; ts: number; tone: Tone; title: string; body: string; why?: string }

export interface AuditEntry { seq: number; ts: number; actor: "agent" | "engine" | "member" | "paypal" | "organiser"; action: string; detail: string; prev: string; hash: string }

export type ApprovalState = "pending" | "approved" | "declined";
export interface Approval { id: string; title: string; body: string; kind: "payout" | "swap" | "hardship" | "decision"; needs: { who: string; state: ApprovalState }[]; amount?: number; checks: Check[] }

export interface ChatMsg { id: string; from: "member" | "agent"; who?: string; text: string; ts: number; checks?: Check[]; blocked?: boolean; approvalId?: string; source?: string }

export interface RuleSet {
  version: number; currency: string; contribution: number; cycleDays: number; members: number; order: "random" | "fixed"; seed: string;
  graceDays: number; ladder: { after: number; action: string }[]; swap: string; hardship: string; maxPayout: number; approvalAbove: number;
}

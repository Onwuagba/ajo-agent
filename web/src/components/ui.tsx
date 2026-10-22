import type { CSSProperties, ReactNode } from "react";
import { AlertTriangle, ArrowDownLeft, ArrowUpRight, Bell, Check, CircleDashed, Clock3, FileText, Shield, ShieldAlert, X } from "lucide-react";
import { GROUP, MEMBERS, memberById } from "../data/roster";
import type { Check as CheckT, LedgerKind, LedgerStatus, Tone } from "../data/types";
import type { MemberStatus } from "../state/store";

export const money = (n: number) => {
  try { return n.toLocaleString("en-US", { style: "currency", currency: GROUP.currency || "USD", minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 }); } catch { return "$" + n; }
};
export const when = (ts: number, now: number) => {
  const m = Math.round((now - ts) / 60000); if (m < 1) return "just now"; if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60); if (h < 24) return `${h} h ago`; const d = Math.round(h / 24); return d < 30 ? `${d} d ago` : new Date(ts).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};
export const dateTime = (ts: number) => new Date(ts).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }) + " UTC";

export function Avatar({ id, size = 36 }: { id: string; size?: number }) {
  const m = memberById(id); const initials = m.name.split(" ").map((p) => p[0]).join("");
  return <span className="avatar" style={{ "--h": m.hue, "--s": `${size}px` } as CSSProperties} title={m.name}>{initials}</span>;
}
export const Chip = ({ tone = "neutral", children, icon }: { tone?: Tone | "neutral"; children: ReactNode; icon?: ReactNode }) => <span className={`chip ${tone}`}>{icon}{children}</span>;

export function MemberChip({ s }: { s: MemberStatus }) {
  const map: Record<MemberStatus, [Tone | "neutral", string, ReactNode]> = {
    paid: ["good", "Paid", <Check size={13} key="i" />], pending: ["warn", "Due", <Clock3 size={13} key="i" />], late: ["bad", "Missed", <AlertTriangle size={13} key="i" />],
    invoiced: ["info", "Invoiced", <FileText size={13} key="i" />], skipped: ["neutral", "Skipping", <CircleDashed size={13} key="i" />],
  };
  const [t, l, i] = map[s]; return <Chip tone={t} icon={i}>{l}</Chip>;
}
export function StatusChip({ s }: { s: LedgerStatus }) {
  const map: Record<LedgerStatus, [Tone | "neutral", string]> = { completed: ["good", "Completed"], pending: ["warn", "Pending"], failed: ["bad", "Failed"], awaiting_approval: ["warn", "Needs approval"], sent: ["info", "Sent"] };
  const [t, l] = map[s]; return <Chip tone={t}>{l}</Chip>;
}
export const kindLabel: Record<LedgerKind, string> = { contribution: "Contribution", payout: "Payout", invoice: "Invoice", invoice_payment: "Invoice paid", repayment: "Repayment", reminder: "Reminder" };
export function KindIcon({ k, size = 15 }: { k: LedgerKind; size?: number }) {
  if (k === "payout") return <ArrowUpRight size={size} />; if (k === "invoice") return <FileText size={size} />; if (k === "reminder") return <Bell size={size} />; return <ArrowDownLeft size={size} />;
}

export function CheckList({ checks }: { checks: CheckT[] }) {
  return <ul className="checks">{checks.map((c, i) => (
    <li key={i}><span className={`ic ${c.pass ? "pass" : "fail"}`}>{c.pass ? <Check size={13} /> : <X size={13} />}</span><span>{c.label}<small>{c.detail}</small></span></li>))}</ul>;
}

export function PotRing({ collected, target, size = 190 }: { collected: number; target: number; size?: number }) {
  const n = MEMBERS.length, r = 78, c = 2 * Math.PI * r, gap = 7, seg = c / n - gap, per = target / n, filled = Math.round(collected / per);
  return (
    <div className="ring-wrap" style={{ width: size, height: size }}>
      <svg viewBox="0 0 190 190" role="img" aria-label={`${money(collected)} collected of ${money(target)}`}>
        {Array.from({ length: n }).map((_, i) => (
          <circle key={i} className="seg" cx="95" cy="95" r={r} fill="none" strokeWidth="15" strokeLinecap="round" strokeDasharray={`${seg} ${c - seg}`} strokeDashoffset={-(i * (c / n))}
            stroke={i < filled ? "var(--gold)" : "var(--line)"} />
        ))}
      </svg>
      <div className="ring-center"><div className="big num">{money(collected)}</div><div className="faint" style={{ fontSize: 13 }}>of {money(target)}</div></div>
    </div>
  );
}

export const Mark = ({ size = 22 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden><circle cx="16" cy="16" r="9" fill="none" stroke="#e0a526" strokeWidth="4" strokeDasharray="10.4 3.7" strokeLinecap="round" /><circle cx="16" cy="16" r="2.6" fill="#fff" /></svg>
);
export const ShieldTag = ({ ok = true }: { ok?: boolean }) => (ok ? <Shield size={15} /> : <ShieldAlert size={15} />);

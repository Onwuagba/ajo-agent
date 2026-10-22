import { ArrowRight, Check, Copy, Hourglass, Lock, UserMinus } from "lucide-react";
import { MEMBERS } from "../data/roster";
import { currentCycle, isOrganiser, memberStatus, removeMember, revokeInvite, toast, useStore } from "../state/store";
import { Avatar, Chip, MemberChip, money } from "../components/ui";
import { PageHead } from "./Ledger";

const linkFor = (code: string) => `${location.origin}${location.pathname}#/join/${code}`;

export function Members() {
  const s = useStore((x) => x); const organiser = useStore(isOrganiser); const c = currentCycle(s); const running = s.group?.status === "active";
  const pending = s.invites.filter((i) => i.status === "pending");
  const sorted = [...MEMBERS].sort((a, b) => (a.turn || 99) - (b.turn || 99));
  const received = (id: string) => s.ledger.filter((r) => r.kind === "payout" && r.status === "completed" && r.member === id).reduce((t, r) => t + r.amount, 0);
  const paidIn = (id: string) => s.ledger.filter((r) => (r.kind === "contribution" || r.kind === "invoice_payment" || r.kind === "repayment") && r.status === "completed" && r.member === id).reduce((t, r) => t + r.amount, 0);
  return (
    <>
      <PageHead title="Members" sub={`${MEMBERS.length} of ${s.group?.size ?? MEMBERS.length} people in ${s.group?.name}. Turn order, who is up to date, and what each person has paid in and received.`} right={<Chip tone="agent">Order drawn · seed {s.rules.seed}</Chip>} />
      <section className="card card-pad">
        <div style={{ overflow: "auto" }}>
          <table className="m-table">
            <thead><tr><th>Member</th><th>Turn</th><th>This cycle</th><th>PayPal</th><th className="r">Paid in</th><th className="r">Received</th>{organiser && !running && <th />}</tr></thead>
            <tbody>{sorted.map((m) => {
              const cycleOf = s.cycles.find((x) => x.recipient === m.id);
              return (
                <tr key={m.id}>
                  <td><span className="row" style={{ gap: 12 }}><Avatar id={m.id} size={36} /><span><b>{m.name}{m.id === s.you ? " (you)" : ""}</b><div className="faint" style={{ fontSize: 12.5 }}>{m.role === "organiser" ? "Organiser" : "Member"}{m.sandbox ? " · sandbox" : ""}{m.email ? ` · ${m.email}` : ""}</div>{s.repayments.filter((r) => r.member === m.id && r.status !== "paid").length > 0 && <div className="faint" style={{ fontSize: 12.5, color: "var(--warn)" }}>Repaying {money(s.repayments.filter((r) => r.member === m.id && r.status !== "paid")[0].amount)} in cycle{s.repayments.filter((r) => r.member === m.id && r.status !== "paid").length > 1 ? "s" : ""} {s.repayments.filter((r) => r.member === m.id && r.status !== "paid").map((r) => r.cycle).join(", ")}</div>}</span></span></td>
                  <td>{cycleOf ? <span>Cycle {cycleOf.n}<div className="faint" style={{ fontSize: 12.5 }}>{cycleOf.date}{cycleOf.status === "paid" ? " · paid out" : cycleOf.status === "collecting" ? " · collecting" : ""}</div></span> : <span className="faint">Drawn at start</span>}</td>
                  <td>{c && running ? <MemberChip s={memberStatus(s, m.id, c.n)} /> : <span className="faint">{s.group?.status === "complete" ? "Complete" : "Not started"}</span>}</td>
                  <td>{m.paypal === "linked" ? <Chip tone="good" icon={<Check size={13} />}>Linked</Chip> : <Chip tone="warn" icon={<Hourglass size={13} />}>Not yet</Chip>}</td>
                  <td className="r num">{money(paidIn(m.id))}</td><td className="r num">{money(received(m.id))}</td>
                  {organiser && !running && <td className="r">{m.role !== "organiser" && s.group?.status === "forming" && <button className="btn sm danger" onClick={() => { if (confirm(`Remove ${m.first} from the circle?`)) void removeMember(m.id); }}><UserMinus size={14} /> Remove</button>}</td>}
                </tr>);
            })}</tbody>
          </table>
        </div>
      </section>
      {organiser && pending.length > 0 && (
        <section className="card card-pad" style={{ marginTop: 18 }}>
          <div className="card-h"><h3>Open invitations</h3></div>
          <div style={{ display: "grid", gap: 8 }}>{pending.map((i) => (
            <div key={i.code} className="pp-row"><Hourglass size={16} /><b>{i.name}</b><span className="faint">{i.email || "no email"}</span><span className="grow" />
              <button className="btn sm" onClick={() => { void navigator.clipboard?.writeText(linkFor(i.code)).then(() => toast("Invite link copied")); }}><Copy size={13} /> Copy link</button>
              <button className="btn sm danger" onClick={() => void revokeInvite(i.code)}>Withdraw</button></div>))}</div>
        </section>)}
      {running && (
        <div className="banner info" style={{ marginTop: 18 }}><Lock size={18} /><span><b>The roster is fixed while the rotation runs.</b> Each member has their own PayPal subscription and a turn in the recorded order. To trade turns, use a swap on the Requests page.</span><button className="btn sm" style={{ marginLeft: "auto" }} onClick={() => (location.hash = `#/g/${s.gid}/requests`)}>Requests <ArrowRight size={14} /></button></div>)}
    </>
  );
}

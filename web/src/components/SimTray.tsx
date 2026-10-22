import { useState } from "react";
import { Clock, CreditCard, FlaskConical, Receipt, TriangleAlert, UserRound, X } from "lucide-react";
import { MEMBERS, memberById } from "../data/roster";
import { currentCycle, getState, memberStatus, setActAs, simAdvance, simFail, simPay, simPayInvoice, toast, useStore } from "../state/store";

const openInvoice = (s: ReturnType<typeof getState>, member: string) => s.ledger.some((r) => r.kind === "invoice" && r.member === member && !s.ledger.some((p) => p.paypalId === r.paypalId && (p.kind === "invoice_payment" || p.kind === "repayment")));

/** Stand-ins for what one person can't do alone in a demo: PayPal events, time passing, and being a different member. Same engine and webhook path as the real thing. */
export function SimTray() {
  const s = useStore((x) => x); const [open, setOpen] = useState(false); const [who, setWho] = useState("");
  if (!s.sandbox || !s.cycles.length || s.group?.status !== "active") return null;
  const c = currentCycle(s); const you = s.you; const target = who || MEMBERS.find((m) => memberStatus(s, m.id, c.n) !== "paid")?.id || MEMBERS[0]?.id || "";
  const status = target ? memberStatus(s, target, c.n) : "pending";
  const run = async (fn: () => Promise<any>, done: string) => { const r = await fn(); if (r !== undefined) toast(done); };
  return (
    <div className={`sim ${open ? "open" : ""}`}>
      {open && (
        <div className="sim-panel" role="dialog" aria-label="Sandbox simulator">
          <div className="row" style={{ justifyContent: "space-between" }}><b><FlaskConical size={15} style={{ verticalAlign: -2 }} /> Sandbox simulator</b><button className="btn sm icon-btn" onClick={() => setOpen(false)} aria-label="Close"><X size={14} /></button></div>
          <p className="faint" style={{ fontSize: 12.5, margin: "4px 0 12px" }}>Stands in for PayPal and the clock. Events go through the same signed-webhook path the real ones would.</p>
          <label className="field"><span><UserRound size={13} style={{ verticalAlign: -2 }} /> Viewing as</span>
            <select className="input" value={s.actAs ?? ""} onChange={(e) => setActAs(e.target.value || null)}><option value="">Me</option>{MEMBERS.filter((m) => m.sandbox).map((m) => <option key={m.id} value={m.id}>{m.name} (sandbox)</option>)}</select></label>
          {s.actAs && <p className="faint" style={{ fontSize: 12.5, margin: "-6px 0 10px" }}>Everything you do now is done as {memberById(s.actAs).first}.</p>}
          <hr className="sep" />
          <label className="field"><span><CreditCard size={13} style={{ verticalAlign: -2 }} /> A PayPal event for cycle {c.n}</span>
            <select className="input" value={target} onChange={(e) => setWho(e.target.value)}>{MEMBERS.map((m) => <option key={m.id} value={m.id}>{m.first}{m.id === you ? " (you)" : ""} · {memberStatus(s, m.id, c.n)}</option>)}</select></label>
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            <button className="btn sm primary" disabled={status === "paid"} onClick={() => void run(() => simPay(target), `${memberById(target).first}'s payment arrived`)}><CreditCard size={13} /> Payment arrives</button>
            <button className="btn sm" disabled={status === "paid"} onClick={() => void run(() => simFail(target), `${memberById(target).first}'s payment failed`)}><TriangleAlert size={13} /> Payment fails</button>
            {openInvoice(s, target) && <button className="btn sm" onClick={() => void run(() => simPayInvoice(target), `${memberById(target).first} paid the invoice`)}><Receipt size={13} /> Invoice paid</button>}
          </div>
          <hr className="sep" />
          <div className="eyebrow" style={{ marginBottom: 8 }}><Clock size={12} style={{ verticalAlign: -2 }} /> Move time forward</div>
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>{[[1, "1 day"], [s.rules.graceDays + 1, "Past the grace period"], [s.rules.cycleDays, "One cycle"]].map(([d, l]) => <button key={String(l)} className="btn sm" onClick={() => void run(() => simAdvance(Number(d)), `Moved forward ${d} day${d === 1 ? "" : "s"}`)}>{l}</button>)}</div>
        </div>)}
      <button className="sim-fab" onClick={() => setOpen(!open)} aria-expanded={open}><FlaskConical size={16} /> Sandbox simulator</button>
    </div>
  );
}

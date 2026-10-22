import { ChevronRight, CircleCheck } from "lucide-react";
import { GROUP, MEMBERS, memberById } from "../data/roster";
import { currentCycle, go, memberStatus, potCollected, potTarget, useStore } from "../state/store";
import { Avatar, Chip, MemberChip, PotRing, money } from "../components/ui";
import { Timeline } from "../components/Timeline";
import { Approvals } from "../components/Approvals";
import { CycleStepper } from "../components/CycleStepper";

export function Overview() {
  const s = useStore((x) => x); const c = currentCycle(s); const lastPayout = s.ledger.find((r) => r.kind === "payout" && r.status === "completed" && r.cycle === c.n); const target = s.group?.status === "complete" && lastPayout ? lastPayout.amount : potTarget(s, c.n); const got = s.group?.status === "complete" && lastPayout ? lastPayout.amount : potCollected(s, c.n);
  const done = s.group?.status === "complete";
  const pending = s.approvals.filter((a) => a.needs.some((n) => n.state === "pending")).length;
  const mine = s.approvals.filter((a) => a.needs.some((n) => n.state === "pending" && n.who === s.you)).length;
  const paid = s.cycles.filter((x) => x.status === "paid").length;
  const total = s.ledger.filter((r) => r.status === "completed" && r.kind === "payout").reduce((a, r) => a + r.amount, 0);
  const missed = s.ledger.filter((r) => r.kind === "contribution" && r.status === "failed").length;
  const recovered = s.ledger.filter((r) => r.kind === "invoice_payment" && r.status === "completed").length;
  const onTime = Math.round(((s.ledger.filter((r) => r.kind === "contribution" && r.status === "completed").length) / Math.max(1, s.ledger.filter((r) => r.kind === "contribution").length)) * 100);
  return (
    <>
      <section className="hero" aria-label="Group summary">
        <div className="eyebrow" style={{ color: "#b9d6c8" }}>Rotating savings group · {GROUP.currency}</div>
        <h2 className="display" style={{ marginTop: 6 }}>{done ? `${GROUP.name} is complete` : `${GROUP.name}, cycle ${c.n} of ${GROUP.cycles}`}</h2>
        <div className="meta"><span><b>{money(GROUP.contribution)}</b> every {GROUP.cycleDays} days</span><span><b>{MEMBERS.length}</b> members</span>{done ? <span><b>All {GROUP.cycles} cycles</b> paid out</span> : <span>Next payout <b>{memberById(c.recipient).first}</b> · {c.date}</span>}<span>Rule set <b>v{s.rules.version}</b></span></div>
      </section>

      <div className="stats" style={{ margin: "18px 0" }}>
        <div className="stat"><div className="eyebrow">Paid out so far</div><div className="v num">{money(total)}</div><div className="s">{paid} of {GROUP.cycles} cycles</div></div>
        <div className="stat"><div className="eyebrow">Paid on time</div><div className="v num">{onTime}%</div><div className="s">{missed === 0 ? "No missed payments" : recovered >= missed ? `${missed} missed, recovered by invoice` : `${missed - recovered} missed, invoice sent`}</div></div>
        <div className="stat"><div className="eyebrow">Waiting on you</div><div className="v num">{mine}</div><div className="s">{mine ? "Your decision is needed" : pending ? `${pending} waiting on others` : "Nothing to approve"}</div></div>
        <div className="stat"><div className="eyebrow">Agent can spend</div><div className="v num">{money(0)}</div><div className="s">Only the rules can move money</div></div>
      </div>

      <div className="grid2" style={{ alignItems: "start" }}>
        <section className="card card-pad" aria-labelledby="pot-h">
          <div className="card-h"><h3 id="pot-h">{done ? "Final cycle's pot" : "This cycle's pot"}</h3><Chip tone={got === target ? "good" : "warn"}>{done ? "Paid out" : got === target ? "Fully funded" : `${money(Math.max(0, target - got))} to go`}</Chip></div>
          <div className="pot">
            <PotRing collected={got} target={target} />
            <div className="members">
              {MEMBERS.map((m) => { const st = memberStatus(s, m.id, c.n); return (
                <div className="mrow" key={m.id}><Avatar id={m.id} /><div className="grow"><b>{m.first}</b><small>{done ? `Turn ${m.turn}` : m.id === c.recipient ? "Collects this cycle" : `Turn ${m.turn}`}</small></div><MemberChip s={st} /></div>); })}
            </div>
          </div>
        </section>

        <section className="card card-pad" aria-labelledby="ag-h">
          <div className="card-h"><h3 id="ag-h">Treasurer agent</h3><span className="chip agent"><span className="pulse" /> {pending ? "Waiting for a human" : "Watching"}</span></div>
          {pending > 0 && <Approvals compact />}
          {pending === 0 && <div className="banner info" style={{ marginBottom: 14 }}><CircleCheck size={18} /><span>Nothing needs approval. I act only when a rule allows it.</span></div>}
          <div className="eyebrow" style={{ margin: "6px 0 12px" }}>Recent activity</div>
          <Timeline limit={5} />
          <button className="btn sm" style={{ marginTop: 4 }} onClick={() => go("audit")}>Open the audit trail <ChevronRight size={14} /></button>
        </section>
      </div>

      <section className="card card-pad" style={{ marginTop: 18 }} aria-labelledby="rot-h">
        <div className="card-h"><h3 id="rot-h">Rotation</h3><button className="btn sm" onClick={() => go("schedule")}>Full schedule <ChevronRight size={14} /></button></div>
        <CycleStepper />
      </section>
    </>
  );
}

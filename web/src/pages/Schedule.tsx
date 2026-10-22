import { ArrowRight, CalendarClock, Dices } from "lucide-react";
import { MEMBERS, memberById } from "../data/roster";
import { memberStatus, useStore } from "../state/store";
import { Avatar, Chip, MemberChip, money } from "../components/ui";
import { CycleStepper } from "../components/CycleStepper";
import { PageHead } from "./Ledger";

export function Schedule() {
  const s = useStore((x) => x);
  const swapped = s.approvals.some((a) => a.kind === "swap" && a.needs.every((n) => n.state === "approved"));
  const original = s.drawOrder;
  return (
    <>
      <PageHead title="Rotation schedule" sub="Who collects when. The order was drawn once, recorded, and only changes through an approved swap." right={<Chip tone="agent" icon={<Dices size={14} />}>Random draw · seed {s.rules.seed}</Chip>} />
      <section className="card card-pad"><div className="card-h"><h3>{s.cycles.length} cycles</h3><Chip icon={<CalendarClock size={13} />}>Every {s.rules.cycleDays} days</Chip></div><CycleStepper /></section>
      {swapped && (
        <section className="card card-pad diff" style={{ marginTop: 18 }}>
          <div className="card-h"><h3>Schedule change</h3><Chip tone="good">Approved by both members and the organiser</Chip></div>
          <div className="grid2">
            <div><div className="eyebrow" style={{ marginBottom: 10 }}>Before</div><div className="row" style={{ gap: 6, flexWrap: "wrap" }}>{original.map((m, i) => <span key={m} className="need"><span className="faint">{i + 1}</span><Avatar id={m} size={22} />{memberById(m).first}</span>)}</div></div>
            <div><div className="eyebrow" style={{ marginBottom: 10 }}>After</div><div className="row" style={{ gap: 6, flexWrap: "wrap" }}>{s.cycles.map((c) => <span key={c.n} className="need" style={c.recipient !== original[c.n - 1] ? { borderColor: "var(--gold)", background: "var(--gold-soft)" } : undefined}><span className="faint">{c.n}</span><Avatar id={c.recipient} size={22} />{memberById(c.recipient).first}</span>)}</div></div>
          </div>
          <p className="muted" style={{ margin: "12px 0 0" }}>Two members swapped turns. Neither payout had gone out, so the rule allowed it. The change is in the audit trail with every approval.</p>
        </section>)}
      <section className="card card-pad" style={{ marginTop: 18 }}>
        <div className="card-h"><h3>Who has paid, cycle by cycle</h3></div>
        <div style={{ overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
            <thead><tr style={{ textAlign: "left", color: "var(--ink3)", fontSize: 12.5 }}><th style={{ padding: "6px 8px" }}>Member</th>{s.cycles.map((c) => <th key={c.n} style={{ padding: "6px 8px" }}>Cycle {c.n}</th>)}</tr></thead>
            <tbody>{MEMBERS.map((m) => (
              <tr key={m.id} style={{ borderTop: "1px solid var(--line)" }}>
                <td style={{ padding: "10px 8px" }}><span className="row"><Avatar id={m.id} size={28} />{m.first}</span></td>
                {s.cycles.map((c) => <td key={c.n} style={{ padding: "10px 8px" }}>{c.status === "upcoming" ? <span className="faint">{money(s.rules.contribution)} due {c.date}</span> : <MemberChip s={memberStatus(s, m.id, c.n)} />}{c.recipient === m.id && <span className="chip agent" style={{ marginLeft: 6 }}><ArrowRight size={12} /> collects</span>}</td>)}
              </tr>))}</tbody>
          </table>
        </div>
      </section>
    </>
  );
}

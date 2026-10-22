import { useMemo, useState } from "react";
import { Download, Search } from "lucide-react";
import { useStore } from "../state/store";
import { LedgerGrid } from "../components/LedgerGrid";
import { Chip } from "../components/ui";

const FILTERS = [["all", "All"], ["contribution", "Money in"], ["payout", "Payouts"], ["invoice", "Invoices"], ["attention", "Needs attention"]] as const;

export function Ledger() {
  const ledger = useStore((s) => s.ledger); const flash = useStore((s) => s.flash);
  const [f, setF] = useState<(typeof FILTERS)[number][0]>("all"); const [q, setQ] = useState(""); const [cycle, setCycle] = useState(0);
  const rows = useMemo(() => ledger
    .filter((r) => (cycle ? r.cycle === cycle : true))
    .filter((r) => f === "all" ? true : f === "contribution" ? r.kind === "contribution" || r.kind === "invoice_payment" || r.kind === "repayment" : f === "invoice" ? r.kind === "invoice" || r.kind === "reminder" : f === "attention" ? r.status === "failed" || r.status === "awaiting_approval" : r.kind === f)
    .map((r) => ({ ...r, _flash: flash.includes(r.id) })), [ledger, f, cycle, flash]);
  return (
    <>
      <PageHead title="Shared ledger" sub="Every movement of money, with the rule that allowed it. Click a row to see why." />
      <div className="toolbar">
        <label className="search"><Search size={17} className="faint" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search member, status, reference" aria-label="Search ledger" /></label>
        <div className="seg-btns" role="group" aria-label="Filter">{FILTERS.map(([k, l]) => <button key={k} aria-pressed={f === k} onClick={() => setF(k)}>{l}</button>)}</div>
        <div className="seg-btns" role="group" aria-label="Cycle">{[0, 1, 2, 3].map((n) => <button key={n} aria-pressed={cycle === n} onClick={() => setCycle(n)}>{n ? `Cycle ${n}` : "All cycles"}</button>)}</div>
        <span className="grow" style={{ flex: 1 }} /><Chip tone="neutral">{rows.length} rows</Chip>
        <button className="btn sm" onClick={() => { const csv = ["when,cycle,type,member,amount,status,reference,rule_version", ...rows.map((r) => [new Date(r.ts).toISOString(), r.cycle, r.kind, r.member, r.amount, r.status, r.paypalId, r.ruleVersion].join(","))].join("\n"); const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = "ajo-ledger.csv"; a.click(); }}><Download size={15} /> CSV</button>
      </div>
      <div className="card grid-card"><LedgerGrid rows={rows} quick={q} /></div>
    </>
  );
}
export function PageHead({ title, sub, right }: { title: string; sub?: string; right?: React.ReactNode }) {
  return <header style={{ display: "flex", gap: 16, alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", marginBottom: 20 }}><div><h1 className="display page-title">{title}</h1>{sub && <p className="page-sub">{sub}</p>}</div>{right}</header>;
}

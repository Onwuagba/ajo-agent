import { Shield, X } from "lucide-react";
import { memberById } from "../data/roster";
import { go, set, useStore } from "../state/store";
import { Avatar, CheckList, Chip, KindIcon, StatusChip, dateTime, kindLabel, money } from "./ui";

export function Drawer() {
  const rowId = useStore((s) => s.drawerRow); const row = useStore((s) => s.ledger.find((r) => r.id === s.drawerRow));
  if (!rowId || !row) return null;
  const close = () => set({ drawerRow: null });
  return (
    <>
      <div className="drawer-back" onClick={close} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Why this payment">
        <div className="row" style={{ justifyContent: "space-between" }}><span className="eyebrow">Why this payment</span><button className="btn icon-btn" onClick={close} aria-label="Close"><X size={18} /></button></div>
        <div className="row" style={{ margin: "14px 0 6px", gap: 14 }}><Avatar id={row.member} size={52} /><div><h3 className="display" style={{ fontSize: 26 }}>{kindLabel[row.kind]} · {money(row.amount)}</h3><span className="muted">{memberById(row.member).name}, cycle {row.cycle}</span></div></div>
        <div className="row" style={{ gap: 8, marginBottom: 14, flexWrap: "wrap" }}><StatusChip s={row.status} /><Chip tone="agent" icon={<KindIcon k={row.kind} size={13} />}>{kindLabel[row.kind]}</Chip>{row.simulated && <span className="chip sim">simulated event</span>}</div>
        <div className="banner info"><Shield size={18} /><span>{row.explanation}</span></div>
        <h4 style={{ margin: "18px 0 4px" }}>Checks the engine ran</h4>
        <CheckList checks={row.checks} />
        <hr className="sep" />
        <dl className="kv">
          <dt>Rule applied</dt><dd>{row.rule}</dd><dt>Rule version</dt><dd>v{row.ruleVersion}</dd><dt>Approved by</dt><dd>{row.approver ?? "No approval needed (under the threshold)"}</dd>
          <dt>PayPal reference</dt><dd className="mono">{row.paypalId}</dd><dt>Recorded</dt><dd>{dateTime(row.ts)}</dd>
        </dl>
        <button className="btn" style={{ marginTop: 18 }} onClick={() => { set({ drawerRow: null }); go("audit"); }}>See it in the audit trail</button>
      </aside>
    </>
  );
}

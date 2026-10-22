import { Check, Hourglass, X } from "lucide-react";
import { memberById } from "../data/roster";
import { decide, useStore } from "../state/store";
import { Avatar, CheckList } from "./ui";

export function Approvals({ compact = false }: { compact?: boolean }) {
  const list = useStore((s) => s.approvals); const you = useStore((s) => s.you); const sandbox = useStore((s) => s.sandbox);
  const shown = compact ? list.filter((a) => a.needs.some((n) => n.state === "pending")) : list;
  if (!shown.length) return <p className="muted">No requests yet. Ask the treasurer for a swap or a hardship skip in the Requests tab.</p>;
  return (
    <div style={{ display: "grid", gap: 12, marginBottom: 14 }}>
      {shown.map((a) => {
        const open = a.needs.some((n) => n.state === "pending"); const declined = a.needs.some((n) => n.state === "declined");
        return (
          <div key={a.id} className={`approval ${open ? "" : "done"}`}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div><b>{a.title}</b><div className="muted" style={{ fontSize: 14 }}>{a.body}</div></div>
              {!open && <span className={`chip ${declined ? "bad" : "good"}`}>{declined ? "Declined" : "Approved"}</span>}
            </div>
            <div className="needs">
              {a.needs.map((n) => (
                <span className="need" key={n.who}><Avatar id={n.who} size={24} />{memberById(n.who).first}{n.who === you ? " (you)" : ""}
                  {n.state === "approved" && <Check size={14} color="var(--good)" />}{n.state === "declined" && <X size={14} color="var(--bad)" />}{n.state === "pending" && <Hourglass size={13} color="var(--warn)" />}</span>))}
            </div>
            {!compact && <CheckList checks={a.checks} />}
            {open && (
              <div className="row" style={{ marginTop: 12, flexWrap: "wrap" }}>
                {a.needs.filter((n) => n.state === "pending").map((n) => {
                  const m = memberById(n.who);
                  if (n.who === you) return <span key={n.who} className="row" style={{ gap: 8 }}><button className="btn primary sm" onClick={() => decide(a.id, n.who, "approved")}><Check size={14} /> Approve</button><button className="btn sm danger" onClick={() => decide(a.id, n.who, "declined")}><X size={14} /> Decline</button></span>;
                  // A sandbox friend is not a real person, so the organiser can answer for them. Real members answer for themselves.
                  return sandbox && m.sandbox ? <button key={n.who} className="btn sm" onClick={() => decide(a.id, n.who, "approved")}>{m.first} approves <span className="chip sim">sandbox</span></button>
                    : <span key={n.who} className="muted" style={{ fontSize: 13.5 }}>Waiting for {m.first}</span>;
                })}
              </div>)}
          </div>);
      })}
    </div>
  );
}

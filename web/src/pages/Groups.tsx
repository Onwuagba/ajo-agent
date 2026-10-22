import { ArrowRight, Plus, Users } from "lucide-react";
import { navigate, useStore } from "../state/store";
import { Chip } from "../components/ui";

export function Groups() {
  const groups = useStore((s) => s.groups); const auth = useStore((s) => s.auth);
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", marginBottom: 20 }}>
        <div><div className="eyebrow">Welcome, {auth?.name.split(" ")[0]}</div><h1 className="display page-title">Your circles</h1></div>
        <button className="btn gold" onClick={() => navigate("#/new")}><Plus size={16} /> Start a circle</button>
      </div>
      {!groups.length ? (
        <section className="card card-pad empty">
          <Users size={30} /><h3 className="display">No circles yet</h3>
          <p className="muted">Start one, invite your people, then appoint the treasurer. Or open an invite link someone sent you.</p>
          <button className="btn primary" onClick={() => navigate("#/new")}><Plus size={16} /> Start your first circle</button>
        </section>
      ) : (
        <div className="group-grid">
          {groups.map((g) => (
            <button key={g.id} className="card card-pad group-card" onClick={() => navigate(g.status === "forming" || g.status === "starting" ? `#/g/${g.id}/setup` : `#/g/${g.id}/overview`)}>
              <div className="row" style={{ justifyContent: "space-between" }}><h3 className="display">{g.name}</h3><Chip tone={g.status === "active" || g.status === "complete" ? "good" : "warn"}>{g.status === "complete" ? "Complete" : g.status === "active" ? "Running" : g.status === "starting" ? "Waiting for PayPal" : "Setting up"}</Chip></div>
              <div className="muted">{g.members} of {g.size} members · you are {g.role === "organiser" ? "the organiser" : "a member"}</div>
              <span className="open">{g.status === "active" || g.status === "complete" ? "Open" : "Continue setup"} <ArrowRight size={15} /></span>
            </button>))}
        </div>)}
    </>
  );
}

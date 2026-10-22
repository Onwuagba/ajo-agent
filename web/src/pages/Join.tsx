import { ArrowRight, Users } from "lucide-react";
import { acceptInvite, navigate, useStore } from "../state/store";
import { AuthForm } from "./Auth";
import { money } from "../components/ui";
import { GROUP } from "../data/roster";

export function Join({ code }: { code: string }) {
  const inv = useStore((s) => s.invite); const auth = useStore((s) => s.auth); const busy = useStore((s) => s.busy);
  if (!inv) return <p className="muted">Looking up your invitation…</p>;
  if (inv.status !== "pending") {
    return <section className="card card-pad empty"><Users size={30} /><h3 className="display">{inv.status === "accepted" ? "This invitation has been used" : "This invitation is no longer open"}</h3>
      <p className="muted">{inv.status === "accepted" ? "Each invite link works once. If it was you, sign in to find your circle." : "The organiser may have withdrawn it, or the circle is already full or running. Ask them for a new link."}</p>
      <button className="btn primary" onClick={() => navigate(auth ? "#/groups" : "#/")}>{auth ? "Your circles" : "Sign in"}</button></section>;
  }
  GROUP.currency = inv.currency;
  return (
    <div className="split" style={{ alignItems: "start" }}>
      <section className="card card-pad invite-card">
        <div className="eyebrow">{inv.organiser} invited {inv.forName.split(" ")[0]}</div>
        <h1 className="display page-title" style={{ marginTop: 6 }}>{inv.group}</h1>
        <p className="muted">A rotating savings circle of {inv.size} people. Everyone pays {money(inv.contribution)} every {inv.cycleDays} days and one person collects the pot each cycle, in an order drawn at random and recorded.</p>
        <ul className="plain"><li><b>{inv.joined} of {inv.size}</b> places filled so far</li><li>An AI treasurer tracks payments and proposes payouts; <b>only the rules can move money</b></li><li>You'll see every payment and decision in a shared ledger</li></ul>
      </section>
      <section>
        {auth ? <div className="card card-pad"><h3 className="display" style={{ marginBottom: 6 }}>Join as {auth.name}</h3><p className="muted">You'll be added to the roster. Nothing is charged until the organiser starts the circle.</p><button className="btn gold wide" disabled={busy} onClick={() => void acceptInvite(code)}>Join {inv.group} <ArrowRight size={16} /></button></div>
          : <AuthForm defaultName={inv.forName} lead={`Create an account to join ${inv.group}. Already have one? Use the Sign in tab.`} />}
      </section>
    </div>
  );
}

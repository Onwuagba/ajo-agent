import { useState } from "react";
import { ArrowRight, Link2, ScrollText, ShieldCheck } from "lucide-react";
import { login, register, useStore } from "../state/store";
import { Mark } from "../components/ui";

/** Create-account and sign-in form. Used on the landing page and inside an invitation. */
export function AuthForm({ initialMode = "register", defaultName = "", lead }: { initialMode?: "register" | "login"; defaultName?: string; lead?: string }) {
  const busy = useStore((s) => s.busy);
  const [mode, setMode] = useState(initialMode); const [name, setName] = useState(defaultName); const [email, setEmail] = useState(""); const [pw, setPw] = useState("");
  const submit = (e: React.FormEvent) => { e.preventDefault(); void (mode === "register" ? register(name, email, pw) : login(email, pw)); };
  return (
    <form className="auth-card" onSubmit={submit}>
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "register"} onClick={() => setMode("register")}>Create account</button>
        <button type="button" role="tab" aria-selected={mode === "login"} onClick={() => setMode("login")}>Sign in</button>
      </div>
      {lead && <p className="muted" style={{ margin: "0 0 14px" }}>{lead}</p>}
      {mode === "register" && <label className="field"><span>Your name</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required minLength={2} placeholder="Amara Okafor" /></label>}
      <label className="field"><span>Email</span><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required placeholder="you@example.com" /></label>
      <label className="field"><span>Password</span><input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete={mode === "register" ? "new-password" : "current-password"} required minLength={mode === "register" ? 8 : 1} placeholder={mode === "register" ? "At least 8 characters" : ""} /></label>
      <button className="btn primary wide" type="submit" disabled={busy}>{busy ? "One moment…" : mode === "register" ? "Create my account" : "Sign in"} <ArrowRight size={16} /></button>
      <p className="faint" style={{ fontSize: 12.5, margin: "12px 0 0" }}>Sandbox: PayPal's test environment, no real money moves. Use a throwaway password.</p>
    </form>
  );
}

export function Landing() {
  return (
    <div className="auth">
      <aside className="auth-hero">
        <div className="row" style={{ gap: 11 }}><span className="brand-mark"><Mark size={24} /></span><span className="brand-name" style={{ color: "#fff" }}>Ajo</span></div>
        <div>
          <div className="eyebrow" style={{ color: "#b9d6c8" }}>Rotating savings circles, run by an AI treasurer</div>
          <h1 className="display">The group pot, run by a treasurer that can't run off with it.</h1>
          <p className="lead">Write your circle's rules the way you'd say them. The treasurer collects, chases, and proposes each payout. Only the rules engine can move money, and only with the approvals your rules ask for.</p>
        </div>
        <ul className="points">
          <li><ScrollText size={18} /><span><b>Your rules, in plain English.</b> Turned into rules you confirm before anything is enforced.</span></li>
          <li><ShieldCheck size={18} /><span><b>The agent proposes. Code decides.</b> Seven checks on every payout, and a human above your limit.</span></li>
          <li><Link2 size={18} /><span><b>A log nobody can quietly edit.</b> Every entry is chained to the one before it.</span></li>
        </ul>
      </aside>
      <main className="auth-side"><div className="auth-wrap"><h2 className="display">Start a circle, or join one</h2><p className="muted" style={{ margin: "0 0 18px" }}>Got an invite link? Open it. It will bring you straight to your circle.</p><AuthForm /></div></main>
    </div>
  );
}

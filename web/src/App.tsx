import { Suspense, lazy, useEffect } from "react";
import { ArrowLeft, CalendarRange, FlaskConical, LayoutDashboard, LogOut, Users, MessagesSquare, Moon, ScrollText, ShieldCheck, Sun, Table2 } from "lucide-react";
import { GROUP } from "./data/roster";
import { go, navigate, retryBoot, setTheme, signOut, useStore } from "./state/store";
import { Mark } from "./components/ui";
import { Chrome } from "./components/Chrome";
import { Drawer } from "./components/Drawer";
import { SimTray } from "./components/SimTray";
import { Landing } from "./pages/Auth";
import { Groups } from "./pages/Groups";
import { NewGroup } from "./pages/NewGroup";
import { Join } from "./pages/Join";
import { Setup } from "./pages/Setup";
import { Overview } from "./pages/Overview";
const Ledger = lazy(() => import("./pages/Ledger").then((m) => ({ default: m.Ledger })));
import { Schedule } from "./pages/Schedule";
import { Requests } from "./pages/Requests";
import { Rules } from "./pages/Rules";
import { Audit } from "./pages/Audit";
import { Members } from "./pages/Members";

const NAV = [["overview", "Overview", LayoutDashboard], ["ledger", "Ledger", Table2], ["schedule", "Schedule", CalendarRange], ["members", "Members", Users], ["requests", "Requests", MessagesSquare], ["rules", "Rules", ScrollText], ["audit", "Audit", ShieldCheck]] as const;
const PAGES: Record<string, React.ComponentType> = { overview: Overview, ledger: Ledger, schedule: Schedule, members: Members, requests: Requests, rules: Rules, audit: Audit };

function Dashboard({ page }: { page: string }) {
  const theme = useStore((s) => s.theme); const auth = useStore((s) => s.auth); const loaded = useStore((s) => s.loaded); const active = useStore((s) => s.group?.status === "active" || s.group?.status === "complete"); const actAs = useStore((s) => s.actAs); const sandbox = useStore((s) => s.sandbox);
  const pending = useStore((s) => s.approvals.filter((a) => a.needs.some((n) => n.state === "pending" && n.who === s.you)).length);
  const Page = PAGES[page] ?? Overview;
  if (!loaded || !active) return <Chrome><p className="muted">Opening your circle…</p></Chrome>;
  return (
    <div className="app">
      <aside className="side" aria-label="Main">
        <div className="brand"><span className="brand-mark"><Mark size={24} /></span><div><div className="brand-name">Ajo</div><div className="brand-sub">The AI treasurer</div></div></div>
        <nav className="nav">{NAV.map(([k, l, I]) => <button key={k} aria-current={page === k ? "page" : undefined} onClick={() => go(k)}><I size={19} />{l}{k === "requests" && pending > 0 && <span className="badge">{pending}</span>}</button>)}</nav>
        <div className="side-foot">
          <div className="agent-card"><div className="row" style={{ gap: 8 }}><span className="pulse" /><b>Treasurer agent</b></div><div style={{ fontSize: 13, marginTop: 6, color: "var(--ink2)" }}>Proposes and explains. Only the rules engine moves money, and only with the approvals the rules require.</div></div>
          <button className="btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />} {theme === "dark" ? "Light" : "Dark"} mode</button>
        </div>
      </aside>
      <main className="main" id="main">
        <div className="top">
          <button className="btn sm" onClick={() => navigate("#/groups")}><ArrowLeft size={14} /> Circles</button>
          {sandbox && <span className="sandbox"><FlaskConical size={14} /> Sandbox · no real money</span>}
          <span className="muted"><b>{GROUP.name}</b></span>
          {actAs && <span className="chip sim">viewing as a sandbox member</span>}
          <span className="grow" />
          <button className="btn sm" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">{theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}</button><span className="who-name muted">{auth?.name}</span><button className="btn sm" onClick={() => void signOut()}><LogOut size={14} /> Sign out</button>
        </div>
        <Suspense fallback={<p className="muted">Loading…</p>}><Page /></Suspense>
      </main>
      <nav className="mobile-nav" aria-label="Main">{NAV.map(([k, l, I]) => <button key={k} aria-current={page === k ? "page" : undefined} onClick={() => go(k)}><I size={19} />{l}{k === "requests" && pending > 0 && <span className="badge" style={{ position: "absolute", top: 2, right: "20%", minWidth: 17, height: 17, fontSize: 10.5 }}>{pending}</span>}</button>)}</nav>
      <Drawer />
      <SimTray />
    </div>
  );
}

export default function App() {
  const api = useStore((s) => s.api); const route = useStore((s) => s.route); const theme = useStore((s) => s.theme); const toastMsg = useStore((s) => s.toast);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  let view: React.ReactNode;
  if (api === "checking") view = <div className="splash"><Mark size={34} /></div>;
  else if (api === "down") view = <Chrome narrow><section className="card card-pad empty"><h3 className="display">The Ajo server isn't running</h3><p className="muted">Start it with <code>server/run.sh</code>, then try again.</p><button className="btn primary" onClick={retryBoot}>Try again</button></section></Chrome>;
  else if (route.name === "home") view = <Landing />;
  else if (route.name === "join") view = <Chrome><Join code={route.code} /></Chrome>;
  else if (route.name === "groups") view = <Chrome><Groups /></Chrome>;
  else if (route.name === "new") view = <Chrome narrow><NewGroup /></Chrome>;
  else if (route.name === "setup") view = <Chrome><Setup /></Chrome>;
  else view = <Dashboard page={route.page} />;
  return <>{view}{toastMsg && <div role="alert" className="toast">{toastMsg}</div>}</>;
}

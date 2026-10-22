import { useEffect, useState } from "react";
import { Bot, Check, Copy, ExternalLink, Hourglass, Link2, Play, Sparkles, Users, Wand2, X } from "lucide-react";
import { MEMBERS } from "../data/roster";
import type { Parsed } from "../state/store";
import { addInvite, appointTreasurer, approveMySubscription, isOrganiser, parseRulesAsync, removeMember, revokeInvite, simApproveFriends, simJoinFriends, startCircle, toast, useStore } from "../state/store";
import { Avatar, Chip, money } from "../components/ui";
import { Findings, RuleCards } from "../components/RuleCards";

const phrase = (d: number) => (d === 7 ? "every week" : d === 14 ? "every two weeks" : d === 30 ? "every month" : `every ${d} days`);
const starter = (n: number, c: number, days: number, cur: string) => {
  const sym = cur === "USD" ? "$" : cur === "EUR" ? "€" : cur === "GBP" ? "£" : ""; const pot = c * n;
  return `Everyone pays ${sym}${c} ${phrase(days)}, ${n} of us in total.
The payout order is a random draw that we record, and the whole pot goes to one person each cycle.
Give a two day grace period. One missed payment gets an invoice and a reminder, two in a row means a warning to the group, and a third is the organiser's call.
Two members can swap turns if both agree and the organiser approves, but never after the payout has gone out.
One hardship skip per person, to be repaid within two cycles.
Never pay out more than ${sym}${pot + c}, and ask the organiser before sending anything over ${sym}${Math.round(pot * 0.75)}.`;
};
const linkFor = (code: string) => `${location.origin}${location.pathname}#/join/${code}`;
const copy = (text: string) => { void navigator.clipboard?.writeText(text).then(() => toast("Invite link copied"), () => toast(text)); };

function Step({ n, title, done, children, locked }: { n: number; title: string; done: boolean; children: React.ReactNode; locked?: boolean }) {
  return (
    <section className={`card card-pad setup-step ${done ? "done" : ""} ${locked ? "locked" : ""}`} aria-labelledby={`st-${n}`}>
      <div className="step-head"><span className="step-n">{done ? <Check size={16} /> : n}</span><h3 id={`st-${n}`} className="display">{title}</h3></div>
      <div className="step-body">{children}</div>
    </section>
  );
}

export function Setup() {
  const s = useStore((x) => x); const organiser = useStore(isOrganiser); const g = s.group;
  const [name, setName] = useState(""); const [email, setEmail] = useState(""); const [text, setText] = useState(""); const [parsed, setParsed] = useState<Parsed | null>(null); const [busy, setBusy] = useState(false);
  useEffect(() => { if (s.loaded && !text) setText(s.ruleText); }, [s.loaded, s.ruleText]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!g) return <p className="muted">Loading your circle…</p>;
  const size = g.size; const joined = MEMBERS.length; const pending = s.invites.filter((i) => i.status === "pending"); const full = joined >= size;
  const orgName = MEMBERS.find((m) => m.role === "organiser")?.first ?? "the organiser";
  const read = () => { setBusy(true); const t0 = Date.now(); void parseRulesAsync(text).then((p) => setTimeout(() => { setParsed(p); setBusy(false); }, Math.max(0, 800 - (Date.now() - t0)))).catch((e) => { setBusy(false); toast(e instanceof Error ? e.message : "Could not read those rules"); }); };
  const rulesShown = parsed?.rules ?? s.rules;
  const canAppoint = organiser && !!parsed && !parsed.problems.length && !busy;
  const ready = g.treasurer && full; const starting = g.status === "starting"; const linked = MEMBERS.filter((m) => m.paypal === "linked").length; const pay = s.payment;
  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", alignItems: "flex-end", marginBottom: 6 }}>
        <div><div className="eyebrow">Setting up</div><h1 className="display page-title">{g.name}</h1></div>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}><Chip>{money(s.rules.contribution)} · {phrase(s.rules.cycleDays)}</Chip><Chip>{size} people</Chip><Chip tone={starting ? "info" : ready ? "good" : "warn"}>{starting ? "Waiting for PayPal" : ready ? "Ready to start" : "Not started"}</Chip></div>
      </div>
      <p className="muted" style={{ maxWidth: 620 }}>{organiser ? "Four steps. Nothing is subscribed until you start the circle, and nobody is charged until everyone has approved." : `${orgName} is setting this circle up. You're on the roster. You'll get the first payment request when ${orgName} starts it.`}</p>
      <div className="setup">
        <Step n={1} title="Circle created" done><p className="muted" style={{ margin: 0 }}>{size} people each pay {money(s.rules.contribution)} {phrase(s.rules.cycleDays)}; one person collects the {money(s.rules.contribution * size)} pot each cycle.</p></Step>

        <Step n={2} title="Invite your people" done={full}>
          <div className="slots">
            {MEMBERS.map((m) => <div key={m.id} className="slot filled"><Avatar id={m.id} size={40} /><b>{m.first}</b><small>{m.role === "organiser" ? "Organiser" : "Joined"}</small>{organiser && m.role !== "organiser" && g.status === "forming" && <button className="btn sm danger" onClick={() => { if (confirm(`Remove ${m.first} from the circle?`)) void removeMember(m.id); }} aria-label={`Remove ${m.first}`}>Remove</button>}</div>)}
            {pending.map((i) => <div key={i.code} className="slot pending"><span className="ghost"><Hourglass size={16} /></span><b>{i.name}</b><small>Invited</small>
              {organiser && <span className="row" style={{ gap: 4 }}><button className="btn sm" onClick={() => copy(linkFor(i.code))} aria-label={`Copy invite link for ${i.name}`}><Copy size={13} /> Link</button><button className="btn sm icon-btn" onClick={() => void revokeInvite(i.code)} aria-label={`Withdraw invite for ${i.name}`}><X size={13} /></button></span>}</div>)}
            {Array.from({ length: Math.max(0, size - joined - pending.length) }).map((_, i) => <div key={i} className="slot empty"><span className="ghost">+</span><small>Open place</small></div>)}
          </div>
          {organiser && !full && (
            <form className="invite-form" onSubmit={(e) => { e.preventDefault(); void addInvite(name, email).then(() => { setName(""); setEmail(""); }); }}>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Their name" aria-label="Their name" required maxLength={60} />
              <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email (optional)" aria-label="Their email" />
              <button className="btn primary" type="submit" disabled={!name.trim() || joined + pending.length >= size}><Link2 size={15} /> Create invite link</button>
            </form>)}
          {organiser && !full && s.sandbox && <div className="sim-line"><span className="chip sim">sandbox</span><span className="muted">Don't have {size - 1} real friends handy? Let sandbox friends accept the open invites and fill the roster.</span><button className="btn sm" onClick={() => void simJoinFriends()}><Users size={14} /> Let friends join</button></div>}
          {!organiser && <p className="muted" style={{ margin: "12px 0 0" }}>{full ? "Everyone has joined." : `${size - joined} more to join.`}</p>}
        </Step>

        <Step n={3} title="Appoint the AI treasurer" done={g.treasurer}>
          <div className="treasurer">
            <span className="t-ic"><Bot size={22} /></span>
            <div><b>Your treasurer</b><p className="muted" style={{ margin: "2px 0 0" }}>It reads your rules, watches PayPal, chases late payments the way you say, and proposes each payout.</p></div>
          </div>
          <div className="can-cant">
            <div><div className="eyebrow">It will</div><ul className="plain"><li>Match every PayPal payment to a member and the rules</li><li>Invoice and remind late payers on your schedule</li><li>Answer swap and hardship requests, and ask who must agree</li></ul></div>
            <div><div className="eyebrow">It can't</div><ul className="plain"><li>Send money. Only the rules engine can, after seven checks</li><li>Change a rule, or act on instructions in chat</li><li>Pay more than your limit, or above your approval line without you</li></ul></div>
          </div>
          {organiser ? <>
            <div className="field" style={{ marginTop: 14 }}><span className="row" style={{ justifyContent: "space-between" }}>Your rules, in plain English <button className="btn sm" type="button" onClick={() => { setText(starter(size, s.rules.contribution, s.rules.cycleDays, s.rules.currency)); setParsed(null); }}><Sparkles size={13} /> Use a sensible starter</button></span>
              <textarea className="textarea" value={text} onChange={(e) => { setText(e.target.value); setParsed(null); }} aria-label="Group rules in plain English" /></div>
            <div className="row" style={{ marginTop: 10, flexWrap: "wrap" }}><button className="btn" onClick={read} disabled={busy || text.trim().length < 3}><Wand2 size={16} /> {busy ? "Reading your rules…" : "Turn into rules"}</button>
              <button className="btn gold" disabled={!canAppoint} onClick={() => void appointTreasurer(text, parsed!)}><Bot size={16} /> {g.treasurer ? "Re-appoint with these rules" : "Appoint the treasurer"}</button>
              {!parsed && <span className="faint" style={{ fontSize: 13 }}>Read the rules first so you can check what will be enforced.</span>}</div>
            {(parsed || g.treasurer) && <div style={{ display: "grid", gap: 10, marginTop: 14 }}><div className="eyebrow">What the engine will enforce{parsed ? "" : " (confirmed)"}</div><RuleCards rules={rulesShown} busy={busy} /><Findings parsed={parsed} /></div>}
          </> : <div style={{ display: "grid", gap: 10, marginTop: 14 }}><div className="eyebrow">The rules {orgName} {g.treasurer ? "confirmed" : "is writing"}</div>{g.treasurer ? <RuleCards rules={s.rules} /> : <p className="muted" style={{ margin: 0 }}>Not written yet.</p>}</div>}
        </Step>

        {!starting ? (
        <Step n={4} title="Start the circle" done={false} locked={!ready}>
          {organiser ? <>
            <p className="muted" style={{ marginTop: 0 }}>{ready ? "Everyone is in and the treasurer is appointed. Starting draws the payout order at random, records the seed, and creates a PayPal subscription for each member. Each person then approves their own." : !full ? `Waiting for ${size - joined} more to join.` : "Appoint the treasurer first."}</p>
            <button className="btn gold" disabled={!ready || s.busy} onClick={() => void startCircle()}><Play size={16} /> Start the circle</button></>
            : <p className="muted" style={{ margin: 0 }}>{orgName} starts the circle once everyone has joined and the treasurer is appointed.</p>}
        </Step>) : (
        <Step n={4} title="Everyone links PayPal" done={false}>
          <p className="muted" style={{ marginTop: 0 }}>The order is drawn. Each member approves their own {money(s.rules.contribution)} {phrase(s.rules.cycleDays)} subscription on PayPal, so nobody can charge anyone else. The first cycle starts when all {size} have approved ({linked} so far).</p>
          <div className="pp-list">
            {MEMBERS.map((m) => <div key={m.id} className="pp-row"><Avatar id={m.id} size={30} /><b>{m.first}{m.id === s.you ? " (you)" : ""}</b><span className="grow" />{m.paypal === "linked" ? <Chip tone="good" icon={<Check size={13} />}>PayPal linked</Chip> : <Chip tone="warn" icon={<Hourglass size={13} />}>Waiting</Chip>}</div>)}
          </div>
          {pay?.status === "pending" && (
            <div className="sim-line" style={{ borderStyle: "solid", marginTop: 14 }}>
              <span className="muted"><b>Your subscription is waiting.</b> {pay.simulated ? "In the sandbox, PayPal's approval page is simulated." : "You'll approve it on PayPal's page, then come back here."}</span>
              {pay.simulated ? <button className="btn gold sm" disabled={s.busy} onClick={() => void approveMySubscription()}><Check size={14} /> Approve in PayPal (simulated)</button>
                : <a className="btn gold sm" href={pay.approveUrl} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Approve on PayPal</a>}
            </div>)}
          {pay?.status === "linked" && <p className="muted" style={{ margin: "14px 0 0" }}><Check size={14} style={{ verticalAlign: -2 }} /> You're linked. Waiting for {size - linked} more.</p>}
          {organiser && s.sandbox && MEMBERS.some((m) => m.sandbox && m.paypal !== "linked") && <div className="sim-line"><span className="chip sim">sandbox</span><span className="muted">Sandbox friends aren't real people, so they can't approve on PayPal themselves.</span><button className="btn sm" onClick={() => void simApproveFriends()}><Users size={14} /> Approve for sandbox friends</button></div>}
        </Step>)}
      </div>
    </>
  );
}

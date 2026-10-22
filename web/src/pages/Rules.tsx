import { useEffect, useState } from "react";
import { Check, Code2, Lock, Sparkles, Wand2 } from "lucide-react";
import type { Parsed } from "../state/store";
import { confirmRulesAsync, isOrganiser, parseRulesAsync, toast, useStore } from "../state/store";
import { Chip } from "../components/ui";
import { Findings, RuleCards } from "../components/RuleCards";
import { ModelCard } from "../components/ModelCard";
import { PageHead } from "./Ledger";

export function Rules() {
  const live = useStore((s) => s.rules); const text0 = useStore((s) => s.ruleText); const history = useStore((s) => s.ruleHistory); const organiser = useStore(isOrganiser);
  const [text, setText] = useState(text0); const [parsed, setParsed] = useState<Parsed | null>(null); const [busy, setBusy] = useState(false); const [json, setJson] = useState(false); const [confirmed, setConfirmed] = useState(false);
  useEffect(() => { setText(text0); }, [text0]);
  const draft = parsed?.rules ?? null; const shown = draft ?? live; const changed = draft && JSON.stringify({ ...draft, version: 0 }) !== JSON.stringify({ ...live, version: 0 });
  const parse = () => { setBusy(true); setConfirmed(false); const t0 = Date.now(); void parseRulesAsync(text).then((p) => setTimeout(() => { setParsed(p); setBusy(false); }, Math.max(0, 900 - (Date.now() - t0)))).catch((e) => { setBusy(false); toast(e instanceof Error ? e.message : "Could not read those rules"); }); };
  return (
    <>
      <PageHead title="Group rules" sub="Written the way the group would say them. They become a structured rule set the organiser confirms, and from then on the engine enforces them. The treasurer can't act on anything unconfirmed." right={<Chip tone="agent" icon={<Sparkles size={13} />}>Live: rule set v{live.version}</Chip>} />
      {!organiser && <div className="banner info"><Lock size={18} /><span>Only the organiser can change the rules. Everyone can read them, and every change shows up in the audit trail.</span></div>}
      <div className="split">
        <section className="card card-pad"><div className="card-h"><h3>In plain English</h3><span className="faint" style={{ fontSize: 13 }}>{text.length} characters</span></div>
          <textarea className="textarea" value={text} onChange={(e) => { setText(e.target.value); setConfirmed(false); }} aria-label="Group rules in plain English" readOnly={!organiser} />
          {organiser && <div className="row" style={{ marginTop: 12, flexWrap: "wrap" }}><button className="btn primary" onClick={parse} disabled={busy}><Wand2 size={16} /> {busy ? "Reading your rules…" : "Turn into rules"}</button><span className="faint" style={{ fontSize: 13 }}>Change an amount or a limit and see what the engine would enforce.</span></div>}
          <hr className="sep" /><div className="eyebrow" style={{ marginBottom: 10 }}>Version history</div>
          <div style={{ display: "grid", gap: 8 }}>{history.map((h) => <div key={h.version} className="row" style={{ justifyContent: "space-between" }}><span><b>v{h.version}</b> <span className="muted">{h.note}</span></span><span className="faint">{h.when}</span></div>)}</div>
        </section>
        <section style={{ display: "grid", gap: 12, alignContent: "start" }}>
          <div className="row" style={{ justifyContent: "space-between" }}><div className="eyebrow">What the engine will enforce</div><button className="btn sm" onClick={() => setJson(!json)}><Code2 size={14} /> {json ? "Cards" : "JSON"}</button></div>
          {json && !busy ? <pre className="json mono">{JSON.stringify(shown, null, 2)}</pre> : <RuleCards rules={shown} busy={busy} />}
          <Findings parsed={parsed} />
        </section>
      </div>
      <div style={{ marginTop: 18 }}><ModelCard /></div>
      {organiser && (changed || confirmed) && (
        <div className="confirm-bar" style={{ marginTop: 18 }}>
          <span style={{ flex: 1 }}>{confirmed ? <><b>Rule set v{live.version} is live.</b> Every decision from now on records it.</> : <>You changed the rules. Nothing is enforced until you confirm.</>}</span>
          {!confirmed && <><button className="btn" onClick={() => { setParsed(null); setText(text0); }}>Discard</button><button className="btn gold" disabled={!!parsed?.problems.length} onClick={() => { void confirmRulesAsync(text, parsed!).then(() => { setParsed(null); setConfirmed(true); }).catch(() => {}); }}><Check size={16} /> Confirm these rules</button></>}
        </div>)}
    </>
  );
}

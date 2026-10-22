import { useState } from "react";
import { Check, FileSearch, Link2, ScanLine, ShieldAlert, ShieldCheck, Pencil, Undo2 } from "lucide-react";
import { memberById } from "../data/roster";
import { replayCycle, tamper, useStore, verifyChain } from "../state/store";
import { Chip, dateTime } from "../components/ui";
import { PageHead } from "./Ledger";

const actorTone = { agent: "agent", engine: "agent", member: "info", paypal: "good", organiser: "warn" } as const;

export function Audit() {
  const audit = useStore((s) => s.audit); const tampered = useStore((s) => s.tampered);
  const [scan, setScan] = useState<Record<number, boolean>>({}); const [running, setRunning] = useState(false); const [result, setResult] = useState<"idle" | "ok" | number>("idle"); const cycles = useStore((s) => s.cycles); const paidCycles = cycles.filter((c) => c.status === "paid"); const sandbox = useStore((s) => s.sandbox); const [replay, setReplay] = useState<Awaited<ReturnType<typeof replayCycle>>>(null); const last = paidCycles[paidCycles.length - 1];
  const run = async () => { setRunning(true); setScan({}); setResult("idle"); const bad = await verifyChain((seq, ok) => setScan((p) => ({ ...p, [seq]: ok }))); setResult(bad ?? "ok"); setRunning(false); };
  const target = audit.length > 3 ? 4 : audit[0]?.seq ?? 1;
  return (
    <>
      <PageHead title="Audit trail" sub="Every request, interpretation, check, approval and payment, in order. Each entry is chained to the one before it, so an edit anywhere breaks the chain." right={<Chip tone="agent" icon={<Link2 size={13} />}>{audit.length} entries · SHA-256 chain</Chip>} />
      <div className="row" style={{ flexWrap: "wrap", marginBottom: 14 }}>
        <button className="btn primary" onClick={() => void run()} disabled={running || !audit.length}><ScanLine size={16} /> {running ? "Verifying…" : "Verify the chain"}</button>
        {sandbox && <button className="btn" onClick={() => { tamper(tampered ? null : target); setResult("idle"); setScan({}); }} disabled={running}>{tampered ? <><Undo2 size={16} /> Undo the edit</> : <><Pencil size={16} /> Edit entry #{target} (try to cheat)</>}</button>}
        {last && <button className="btn" onClick={() => void replayCycle(last.n).then(setReplay)}><FileSearch size={16} /> Replay cycle {last.n}</button>}
      </div>
      {result === "ok" && <div className="banner good"><ShieldCheck size={18} /> Chain intact. Every entry matches the hash of the one before it.</div>}
      {typeof result === "number" && <div className="banner bad"><ShieldAlert size={18} /> Chain broken at entry #{result}. Its content no longer matches its recorded hash, so everything after it can't be trusted.</div>}
      {replay && <div className="banner info"><Check size={18} /> Replayed cycle {replay.cycle} from the log: recipient {memberById(replay.recipient).first}, amount {replay.amount}, {replay.checksPassed ? "every hard check passed" : "a hard check failed"}, {replay.approvedBy ? `approved by ${replay.approvedBy}` : "no human approval needed"}. {replay.matchesRecord ? "The recorded decision matches." : "The recorded decision does NOT match."}<button className="btn sm" style={{ marginLeft: "auto" }} onClick={() => setReplay(null)}>Dismiss</button></div>}
      <div className="audit">
        {audit.slice().reverse().map((e) => {
          const st = scan[e.seq]; const cls = st === undefined ? "" : st ? "ok" : "bad";
          return (
            <div key={e.seq} className={`a-row ${cls}`}>
              <div className="a-seq num">{e.seq}</div>
              <div className={`a-body ${cls === "bad" ? "bad" : ""}`}>
                <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 6 }}><span><b>{e.action}</b> <Chip tone={actorTone[e.actor]}>{e.actor}</Chip></span><span className="faint" style={{ fontSize: 12.5 }}>{dateTime(e.ts)}</span></div>
                <div className="muted">{e.detail}</div>
                <div className="hashes mono"><span>prev {e.prev.slice(0, 10)}…</span><span>hash {e.hash.slice(0, 10)}…</span></div>
              </div>
            </div>);
        })}
        {!audit.length && <p className="muted">Building the log…</p>}
      </div>
    </>
  );
}

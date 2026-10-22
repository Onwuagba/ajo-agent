import { AlertTriangle, Check, Info, ShieldAlert, Sparkles } from "lucide-react";
import type { Tone } from "../data/types";
import { useStore } from "../state/store";
import { when } from "./ui";

const icon: Record<Tone, JSX.Element> = { good: <Check size={14} />, bad: <ShieldAlert size={14} />, warn: <AlertTriangle size={14} />, info: <Info size={14} />, agent: <Sparkles size={14} /> };

export function Timeline({ limit }: { limit?: number }) {
  const items = useStore((s) => s.timeline); const now = useStore((s) => s.now);
  return (
    <div className="tl" aria-live="polite">
      {items.slice(0, limit).map((e) => (
        <div className="tl-item" key={e.id}>
          <span className={`tl-dot ${e.tone}`}>{icon[e.tone]}</span>
          <div><div className="tl-title">{e.title} <span className="tl-when">· {when(e.ts, now)}</span></div><div className="tl-body">{e.body}</div>{e.why && <div className="why"><b>Why:</b> {e.why}</div>}</div>
        </div>))}
    </div>
  );
}

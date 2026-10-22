import { useState } from "react";
import { ArrowLeft, ArrowRight, Minus, Plus } from "lucide-react";
import { createGroup, navigate, useStore } from "../state/store";

const CYCLES = [[7, "Every week"], [14, "Every two weeks"], [30, "Every month"]] as const;
const sym: Record<string, string> = { USD: "$", EUR: "€", GBP: "£", CAD: "CA$" };

export function NewGroup() {
  const busy = useStore((s) => s.busy);
  const [name, setName] = useState(""); const [size, setSize] = useState(5); const [amount, setAmount] = useState(50); const [days, setDays] = useState(14); const [cur, setCur] = useState("USD");
  const pot = amount * size; const span = size * days;
  return (
    <>
      <button className="btn sm" onClick={() => navigate("#/groups")}><ArrowLeft size={15} /> Your circles</button>
      <div className="eyebrow" style={{ margin: "18px 0 4px" }}>Step 1 of 4</div>
      <h1 className="display page-title">Start a circle</h1>
      <p className="muted" style={{ maxWidth: 560 }}>Everyone pays in each cycle and one person collects the whole pot, until everyone has had a turn. You can write the finer rules in a moment.</p>
      <form className="split" style={{ marginTop: 22, alignItems: "start" }} onSubmit={(e) => { e.preventDefault(); void createGroup({ name, size, contribution: amount, cycleDays: days, currency: cur }); }}>
        <section className="card card-pad" style={{ display: "grid", gap: 16 }}>
          <label className="field"><span>Circle name</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Sunday Circle" required minLength={2} maxLength={60} autoFocus /></label>
          <div className="field"><span>How many people, including you?</span>
            <div className="stepper-in"><button type="button" className="btn icon-btn" onClick={() => setSize(Math.max(3, size - 1))} aria-label="Fewer people"><Minus size={16} /></button><b className="num">{size}</b><button type="button" className="btn icon-btn" onClick={() => setSize(Math.min(12, size + 1))} aria-label="More people"><Plus size={16} /></button></div></div>
          <div className="two">
            <label className="field"><span>Each person pays</span><span className="amount"><span>{sym[cur] ?? cur}</span><input className="input num" type="number" min={1} max={100000} step="any" value={amount} onChange={(e) => setAmount(Number(e.target.value))} required /></span></label>
            <label className="field"><span>Currency</span><select className="input" value={cur} onChange={(e) => setCur(e.target.value)}>{Object.keys(sym).map((c) => <option key={c}>{c}</option>)}</select></label>
          </div>
          <div className="field"><span>How often?</span><div className="seg-btns">{CYCLES.map(([d, l]) => <button type="button" key={d} aria-pressed={days === d} onClick={() => setDays(d)}>{l}</button>)}</div></div>
          <button className="btn primary wide" type="submit" disabled={busy || !name.trim() || !(amount > 0)}>Create the circle <ArrowRight size={16} /></button>
        </section>
        <section className="card card-pad summary">
          <div className="eyebrow">What this means</div>
          <div className="big-num display">{sym[cur] ?? cur}{pot.toLocaleString("en-US")}</div>
          <div className="muted">collected every {days === 7 ? "week" : days === 14 ? "two weeks" : "month"} and paid to one person</div>
          <hr className="sep" />
          <ul className="plain"><li><b>{size}</b> cycles, so everyone collects exactly once</li><li>About <b>{span >= 60 ? `${Math.round(span / 30)} months` : `${span} days`}</b> from start to finish</li><li>Each person pays <b>{sym[cur] ?? cur}{amount}</b> and collects <b>{sym[cur] ?? cur}{pot.toLocaleString("en-US")}</b> once</li></ul>
        </section>
      </form>
    </>
  );
}

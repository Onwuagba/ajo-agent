import { useEffect, useState } from "react";
import { Bot, Check, Cpu, FlaskConical, KeyRound, Loader2, RefreshCw } from "lucide-react";
import type { ModelInfo } from "../state/store";
import { isOrganiser, loadModel, saveModel, testModel, toast, useStore } from "../state/store";

const PROVIDERS = [["default", "Server default"], ["ollama", "Ollama (on this computer)"], ["openai_compat", "OpenAI-compatible"], ["anthropic", "Anthropic"]] as const;

/** Which model reads the group's messages. The organiser can switch it at any time; the engine's rules and checks do not change with the model. */
export function ModelCard() {
  const organiser = useStore(isOrganiser); const gid = useStore((s) => s.gid);
  const [info, setInfo] = useState<ModelInfo | null>(null); const [provider, setProvider] = useState<ModelInfo["provider"]>("default");
  const [model, setModel] = useState(""); const [baseUrl, setBaseUrl] = useState(""); const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false); const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);
  const apply = (m: ModelInfo) => { setInfo(m); setProvider(m.provider); setModel(m.model); setBaseUrl(m.baseUrl); setKey(""); };
  const refresh = () => { void loadModel().then(apply).catch((e) => toast(e instanceof Error ? e.message : "Could not load the model settings")); };
  useEffect(refresh, [gid]);
  if (!info) return <section className="card card-pad"><p className="muted" style={{ margin: 0 }}>Loading the treasurer's model…</p></section>;
  const installed = info.installed;
  const save = async () => {
    setBusy(true); setResult(null);
    const r = await saveModel({ provider, baseUrl: provider === "openai_compat" ? baseUrl : provider === "ollama" ? "" : "", model, apiKey: key || undefined });
    if (r) { apply(r); toast("Treasurer model saved"); }
    setBusy(false);
  };
  const test = async () => { setBusy(true); setResult(null); try { setResult(await testModel()); } catch (e) { setResult({ ok: false, detail: e instanceof Error ? e.message : "The test failed" }); } setBusy(false); };
  const dirty = provider !== info.provider || model !== info.model || baseUrl !== info.baseUrl || !!key;
  return (
    <section className="card card-pad" id="model" aria-labelledby="model-h">
      <div className="card-h"><h3 id="model-h" className="row" style={{ gap: 8 }}><Bot size={18} /> Treasurer model</h3>
        <span className={`chip ${info.effective === "none" ? "neutral" : "agent"}`}>{info.effective === "none" ? "Built-in rules" : info.effective}</span></div>
      <p className="muted" style={{ marginTop: 0 }}>The model reads each message and puts the answer into words. It can't move money or change a rule: the rules engine checks and decides whatever model you use.</p>
      {!organiser ? <p className="muted" style={{ margin: 0 }}>Only the organiser can change the model. Right now: <b>{info.effective === "none" ? "built-in rules" : info.effective}</b>.</p> : (
        <div style={{ display: "grid", gap: 12 }}>
          <div className="seg-btns" role="group" aria-label="Provider">{PROVIDERS.map(([k, l]) => <button key={k} type="button" aria-pressed={provider === k} onClick={() => { setProvider(k); setResult(null); if (k === "ollama" && !model && installed[0]) setModel(installed[0].name); }}>{l}</button>)}</div>
          {provider === "default" && <p className="muted" style={{ margin: 0 }}>Uses whatever the server is set up with: a local Ollama if one is running, otherwise the built-in rules reader.</p>}
          {provider === "ollama" && (
            <div className="field"><span className="row" style={{ justifyContent: "space-between" }}>Model installed in Ollama <button className="btn sm" type="button" onClick={refresh}><RefreshCw size={13} /> Refresh</button></span>
              {installed.length ? <select className="input" value={model} onChange={(e) => setModel(e.target.value)} aria-label="Ollama model">{!installed.some((m) => m.name === model) && <option value={model}>{model || "Choose a model"}</option>}{installed.map((m) => <option key={m.name} value={m.name}>{m.name} · {m.params || `${m.sizeGb} GB`}{m.sizeGb ? ` · ${m.sizeGb} GB` : ""}</option>)}</select>
                : <><input className="input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="llama3.2:3b" aria-label="Ollama model name" /><small className="faint">Ollama isn't answering at {info.ollamaUrl}. Start it with <code>ollama serve</code>, then <code>ollama pull llama3.2:3b</code>.</small></>}
              <small className="faint"><Cpu size={12} style={{ verticalAlign: -1 }} /> Runs on this computer. Smaller models answer faster; larger ones read unusual wording better.</small></div>)}
          {provider === "openai_compat" && <>
            <label className="field"><span>Service address</span><input className="input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" /></label>
            <label className="field"><span>Model name</span><input className="input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o-mini" /></label></>}
          {provider === "anthropic" && <label className="field"><span>Model name</span><input className="input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="claude-haiku-5-5" /></label>}
          {(provider === "openai_compat" || provider === "anthropic") && <label className="field"><span><KeyRound size={13} style={{ verticalAlign: -2 }} /> API key</span><input className="input" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={info.hasKey && info.provider === provider ? "Saved. Leave empty to keep it" : "Paste your key"} /><small className="faint">Stored on the server for this circle only, never shown again and never written to the audit log.</small></label>}
          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <button className="btn primary" type="button" disabled={busy || !dirty || (provider !== "default" && !model.trim())} onClick={() => void save()}>{busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />} Save</button>
            <button className="btn" type="button" disabled={busy} onClick={() => void test()}><FlaskConical size={15} /> Test the model</button>
          </div>
          {result && <div className={`banner ${result.ok ? "good" : "bad"}`} style={{ margin: 0 }}>{result.detail}</div>}
        </div>)}
    </section>
  );
}

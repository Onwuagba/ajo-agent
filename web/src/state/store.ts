import { useSyncExternalStore } from "react";
import { GROUP, MEMBERS } from "../data/roster";
import type { Account, Approval, AuditEntry, ChatMsg, Check, Cycle, GroupMeta, GroupSummary, Invite, InviteInfo, LedgerRow, Member, RuleSet, TimelineEvent } from "../data/types";
import { GENESIS, entryBody, sha256 } from "./hash";

export const PAGES = ["overview", "ledger", "schedule", "members", "requests", "rules", "audit"] as const;
export type Route =
  | { name: "home" } | { name: "join"; code: string } | { name: "groups" } | { name: "new" }
  | { name: "setup"; gid: string } | { name: "dash"; gid: string; page: string };

export interface State {
  // session and routing
  api: "checking" | "up" | "down"; sandbox: boolean; mode: string; llm: string; auth: Account | null; route: Route; theme: "light" | "dark"; toast: string | null; busy: boolean;
  // lists and the invite being viewed
  groups: GroupSummary[]; invite: InviteInfo | null;
  // the open group
  gid: string | null; loaded: boolean; group: GroupMeta | null; payment: { status: "linked" | "pending"; approveUrl: string; simulated: boolean } | null; pot: { collected: number; target: number } | null; repayments: { member: string; cycle: number; amount: number; status: string }[]; you: string; actAs: string | null; invites: Invite[]; now: number;
  ledger: LedgerRow[]; timeline: TimelineEvent[]; audit: AuditEntry[]; approvals: Approval[]; chat: ChatMsg[]; cycles: Cycle[]; drawOrder: string[];
  rules: RuleSet; ruleText: string; ruleHistory: { version: number; note: string; when: string }[]; skips: { member: string; cycle: number }[];
  flash: string[]; typing: boolean; tampered: number | null; drawerRow: string | null;
}

const EMPTY_RULES: RuleSet = { version: 1, currency: "USD", contribution: 50, cycleDays: 14, members: 5, order: "random", seed: "unset", graceDays: 2, ladder: [], swap: "", hardship: "", maxPayout: 300, approvalAbove: 200 };
const emptyGroup = () => ({
  gid: null as string | null, loaded: false, group: null as GroupMeta | null, payment: null as State["payment"], pot: null as State["pot"], repayments: [] as State["repayments"], you: "", actAs: null as string | null, invites: [] as Invite[], now: Date.now(),
  ledger: [] as LedgerRow[], timeline: [] as TimelineEvent[], audit: [] as AuditEntry[], approvals: [] as Approval[], chat: [] as ChatMsg[], cycles: [] as Cycle[], drawOrder: [] as string[],
  rules: EMPTY_RULES, ruleText: "", ruleHistory: [] as { version: number; note: string; when: string }[], skips: [] as { member: string; cycle: number }[],
  flash: [] as string[], typing: false, tampered: null as number | null, drawerRow: null as string | null,
});

export function parseRoute(hash: string): Route {
  const p = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (p[0] === "join" && p[1]) return { name: "join", code: p[1] };
  if (p[0] === "groups") return { name: "groups" };
  if (p[0] === "new") return { name: "new" };
  if (p[0] === "g" && p[1]) return p[2] === "setup" ? { name: "setup", gid: p[1] } : { name: "dash", gid: p[1], page: (PAGES as readonly string[]).includes(p[2]) ? p[2] : "overview" };
  return { name: "home" };
}

const TOKEN_KEY = "ajo-token";
const readToken = () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
const writeToken = (t: string | null) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ } };
let token: string | null = readToken();

const initial = (): State => ({
  api: "checking", sandbox: false, mode: "fake", llm: "none", auth: null, route: parseRoute(typeof location !== "undefined" ? location.hash : ""), busy: false, toast: null,
  theme: (typeof localStorage !== "undefined" && (localStorage.getItem("ajo-theme") as "light" | "dark")) || (typeof matchMedia !== "undefined" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
  groups: [], invite: null, ...emptyGroup(),
});

let state: State = initial();
const subs = new Set<() => void>();
export const getState = () => state;
export function set(patch: Partial<State> | ((s: State) => Partial<State>)) {
  state = { ...state, ...(typeof patch === "function" ? patch(state) : patch) };
  subs.forEach((f) => f());
}
export function useStore<T>(sel: (s: State) => T): T { return useSyncExternalStore((f) => { subs.add(f); return () => subs.delete(f); }, () => sel(state)); }

// ---------- talking to the API ----------
export const API: string = (import.meta as any).env?.VITE_API_URL ?? "http://127.0.0.1:8100";
class ApiError extends Error { constructor(m: string, readonly status: number) { super(m); } }
async function http<T>(path: string, init?: RequestInit & { actAs?: string | null }): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init?.headers as Record<string, string> ?? {}) };
  if (token) headers.Authorization = "Bearer " + token;
  const act = init?.actAs !== undefined ? init.actAs : state.actAs;
  if (act && (path.startsWith("/api/groups/") || path.startsWith("/api/sandbox/"))) headers["X-Act-As"] = act;
  let r: Response;
  try { r = await fetch(API + path, { ...init, headers }); } catch { throw new ApiError("Can't reach the Ajo server. Is it running?", 0); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401 && token && !path.startsWith("/api/auth/")) endSession();
    throw new ApiError((body as any).error ?? (typeof (body as any).detail === "string" ? (body as any).detail : null) ?? `Request failed (${r.status})`, r.status);
  }
  return body as T;
}
const post = <T,>(path: string, body?: unknown, actAs?: string | null) => http<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body), actAs });
let toastTimer: ReturnType<typeof setTimeout> | undefined;
export function toast(message: string) { set({ toast: message }); clearTimeout(toastTimer); toastTimer = setTimeout(() => set({ toast: null }), 4600); }
const fail = (e: unknown) => toast(e instanceof Error ? e.message : "Something went wrong");
async function guarded<T>(fn: () => Promise<T>): Promise<T | undefined> {
  set({ busy: true });
  try { return await fn(); } catch (e) { fail(e); return undefined; } finally { set({ busy: false }); }
}

// ---------- navigation ----------
export function navigate(hash: string) { if (location.hash !== hash) location.hash = hash; else applyRoute(); }
export const go = (page: string) => { if (state.gid) navigate(`#/g/${state.gid}/${page}`); };
let returnTo: string | null = null;

export function applyRoute() {
  const route = parseRoute(location.hash);
  const needsAuth = route.name === "groups" || route.name === "new" || route.name === "setup" || route.name === "dash";
  if (state.api === "up" && !state.auth && needsAuth) { returnTo = location.hash; navigate("#/"); return; }
  if (state.auth && route.name === "home") { navigate("#/groups"); return; }
  const gid = route.name === "setup" || route.name === "dash" ? route.gid : null;
  if (gid !== state.gid) { lastVersion = -1; set({ ...emptyGroup(), route, gid, theme: state.theme }); } else set({ route });
  if (route.name === "join") void loadInvite(route.code);
  if (route.name === "groups") void refreshGroups();
  if (gid && state.auth) void sync(true);
  window.scrollTo({ top: 0 });
}

// ---------- session ----------
function endSession() { token = null; writeToken(null); lastVersion = -1; set({ auth: null, groups: [], ...emptyGroup() }); if (parseRoute(location.hash).name !== "join") navigate("#/"); }
async function startSession(r: { token: string; user: Account }) {
  token = r.token; writeToken(token); set({ auth: r.user });
  const back = returnTo; returnTo = null;
  const route = parseRoute(location.hash);
  if (route.name === "join") { applyRoute(); return; }
  navigate(back && back !== "#/" ? back : "#/groups");
}
export const register = (name: string, email: string, password: string) => guarded(async () => startSession(await post("/api/auth/register", { name, email, password })));
export const login = (email: string, password: string) => guarded(async () => startSession(await post("/api/auth/login", { email, password })));
export const retryBoot = () => { set({ api: "checking" }); void boot(); };
export async function signOut() { try { await post("/api/auth/logout"); } catch { /* the token may already be gone */ } endSession(); }

export async function refreshGroups() { if (!state.auth) return; try { set({ groups: await http<GroupSummary[]>("/api/me/groups") }); } catch { /* shown by the next action */ } }
export const createGroup = (f: { name: string; size: number; contribution: number; cycleDays: number; currency: string }) =>
  guarded(async () => { const r = await post<{ id: string }>("/api/groups", f); navigate(`#/g/${r.id}/setup`); });

async function loadInvite(code: string) { set({ invite: null }); try { set({ invite: await http<InviteInfo>(`/api/invites/${code}`) }); } catch { set({ invite: { code, status: "revoked", forName: "", group: "", organiser: "", contribution: 0, currency: "USD", cycleDays: 0, size: 0, joined: 0 } }); } }
export const acceptInvite = (code: string) => guarded(async () => { const r = await post<{ group: string }>(`/api/invites/${code}/accept`); navigate(`#/g/${r.group}/setup`); });

// ---------- the open group ----------
let lastVersion = -1;
export async function sync(force = false) {
  const gid = state.gid; if (!gid || !state.auth) return;
  let s: any;
  try { s = await http(`/api/groups/${gid}/state`); } catch (e) { if (force || state.loaded) { if (e instanceof ApiError && (e.status === 403 || e.status === 404)) { toast("You don't have access to that circle."); navigate("#/groups"); } } return; }
  if (gid !== state.gid) return;
  if (!force && s.version === lastVersion && s.you === state.you) return;
  lastVersion = s.version;
  MEMBERS.splice(0, MEMBERS.length, ...(s.members as Member[]));
  Object.assign(GROUP, { name: s.group.name, currency: s.group.currency, contribution: s.rules.contribution, cycleDays: s.rules.cycleDays, cycles: s.cycles.length, currentCycle: s.currentCycle ?? 1, organiser: s.members.find((m: Member) => m.role === "organiser")?.id ?? "" });
  set({
    loaded: true, llm: s.model ?? "none", group: s.group, payment: s.payment, pot: s.pot, repayments: s.repayments, you: s.you, invites: s.invites, now: s.now, mode: s.mode, ledger: s.ledger, audit: s.audit, approvals: s.approvals, cycles: s.cycles, drawOrder: s.drawOrder, rules: s.rules, ruleText: s.ruleText, ruleHistory: s.ruleHistory, skips: s.skips,
    timeline: s.timeline.map((t: any) => ({ ...t, why: t.why ?? undefined })), chat: s.chat.map((c: any) => ({ ...c, checks: c.checks ?? undefined, who: c.who ?? undefined, approvalId: c.approvalId ?? undefined })),
  });
  // a circle that has not started (still forming, or waiting for PayPal approvals) lives on the setup page; a running one lives on the dashboard
  const r = state.route;
  if (r.name === "dash" && s.group.status !== "active" && s.group.status !== "complete") navigate(`#/g/${gid}/setup`);
  if (r.name === "setup" && (s.group.status === "active" || s.group.status === "complete")) navigate(`#/g/${gid}/overview`);
}
export const isOrganiser = (s: State) => !!s.you && MEMBERS.find((m) => m.id === s.you)?.role === "organiser";

export const addInvite = (name: string, email: string) => guarded(async () => { await post(`/api/groups/${state.gid}/invites`, { name, email }); await sync(true); });
export const removeMember = (mid: string) => guarded(async () => { await http(`/api/groups/${state.gid}/members/${mid}`, { method: "DELETE" }); await sync(true); });
export const revokeInvite = (code: string) => guarded(async () => { await http(`/api/groups/${state.gid}/invites/${code}`, { method: "DELETE" }); await sync(true); });
export interface Parsed { rules: RuleSet; raw: unknown; questions: string[]; problems: string[]; source: string }
export const parseRulesAsync = (text: string) => http<Parsed>(`/api/groups/${state.gid}/rules/parse`, { method: "POST", body: JSON.stringify({ text }) });
export async function confirmRulesAsync(text: string, parsed: Parsed): Promise<void> {
  try { await post(`/api/groups/${state.gid}/rules/confirm`, { text, raw: parsed.raw }); await sync(true); } catch (e) { fail(e); throw e; }
}
export async function appointTreasurer(text: string, parsed: Parsed): Promise<void> {
  try { await post(`/api/groups/${state.gid}/treasurer`, { text, raw: parsed.raw }); await sync(true); } catch (e) { fail(e); throw e; }
}
/** With real PayPal the member approves on PayPal's own page (approveUrl) and PayPal's webhook activates the subscription. The simulator stands in for that page. */
export const approveMySubscription = () => guarded(async () => { await post(`/api/groups/${state.gid}/subscription/approve`, undefined, null); await sync(true); });
export const simApproveFriends = () => guarded(async () => { await post(`/api/sandbox/${state.gid}/approve-friends`, undefined, null); await sync(true); });
export const startCircle = () => guarded(async () => { await post(`/api/groups/${state.gid}/activate`); await sync(true); });

export function decide(approvalId: string, who: string, verdict: "approved" | "declined") {
  void post(`/api/groups/${state.gid}/approvals/${approvalId}/decide`, { verdict }, who === state.you ? undefined : who).then(() => sync(true)).catch(fail);
}
export function reply(text: string) {
  const t = text.trim(); if (!t) return;
  set((s) => ({ typing: true, chat: [...s.chat, { id: "tmp" + Date.now(), from: "member", who: s.you, text: t, ts: s.now }] }));
  void post(`/api/groups/${state.gid}/chat`, { text: t }).then(() => sync(true)).catch(fail).finally(() => set({ typing: false }));
}
export function setActAs(id: string | null) { set({ actAs: id }); void sync(true); }
export function setTheme(t: "light" | "dark") { set({ theme: t }); try { localStorage.setItem("ajo-theme", t); } catch { /* private mode */ } }

// ---------- the treasurer's model ----------
export interface ModelInfo { provider: "default" | "ollama" | "openai_compat" | "anthropic"; baseUrl: string; model: string; hasKey: boolean; effective: string; installed: { name: string; sizeGb: number; params: string }[]; ollamaUrl: string }
export const loadModel = () => http<ModelInfo>(`/api/groups/${state.gid}/model`);
export async function saveModel(cfg: { provider: string; baseUrl?: string; model?: string; apiKey?: string }): Promise<ModelInfo | null> {
  try { const r = await http<ModelInfo>(`/api/groups/${state.gid}/model`, { method: "PUT", body: JSON.stringify(cfg) }); await sync(true); return { ...(await loadModel()), ...r }; } catch (e) { fail(e); return null; }
}
export const testModel = () => post<{ ok: boolean; ms: number; detail: string }>(`/api/groups/${state.gid}/model/test`);

// ---------- the sandbox simulator (PayPal and time stand-ins; the API refuses these unless it runs the PayPal simulator) ----------
const sim = (path: string, body?: unknown) => guarded(async () => { const r = await post<any>(`/api/sandbox/${state.gid}/${path}`, body, null); await sync(true); return r; });
export const simJoinFriends = () => sim("join-friends");
export const simPay = (member: string) => sim("pay", { member });
export const simFail = (member: string) => sim("fail", { member });
export const simPayInvoice = (member: string) => sim("pay-invoice", { member });
export const simAdvance = (days: number) => sim("advance", { days });

// ---------- the audit chain ----------
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
/** Checks the hash chain in the browser, from the entries the server sent, so the verdict does not depend on trusting the server's own check. */
export async function verifyChain(onStep?: (seq: number, ok: boolean) => void): Promise<number | null> {
  let prev = GENESIS;
  for (const e of state.audit) {
    const ok = e.prev === prev && e.hash === (await sha256(prev + entryBody(e)));
    onStep?.(e.seq, ok); await sleep(120);
    if (!ok) return e.seq;
    prev = e.hash;
  }
  return null;
}
export function tamper(seq: number | null) {
  const target = seq ?? state.tampered; if (target == null) return;
  set({ tampered: seq });
  void post(`/api/sandbox/${state.gid}/tamper/${target}${seq === null ? "?undo=true" : ""}`, undefined, null).then(() => sync(true)).catch(fail);
}
export async function replayCycle(n: number): Promise<{ cycle: number; recipient: string; amount: number; checksPassed: boolean; neededApproval: boolean; approvedBy: string | null; matchesRecord: boolean } | null> {
  try { return await http(`/api/groups/${state.gid}/audit/replay/${n}`); } catch (e) { fail(e); return null; }
}

// ---------- derived helpers ----------
export type MemberStatus = "paid" | "pending" | "late" | "invoiced" | "skipped";
export const currentCycle = (s: State) => s.cycles.find((c) => c.status === "collecting") ?? s.cycles[s.cycles.length - 1];
export function memberStatus(s: State, member: string, cycle: number): MemberStatus {
  if (s.skips.some((k) => k.member === member && k.cycle === cycle)) return "skipped";
  const rows = s.ledger.filter((r) => r.cycle === cycle && r.member === member);
  if (rows.some((r) => (r.kind === "contribution" || r.kind === "invoice_payment") && r.status === "completed")) return "paid";
  if (rows.some((r) => r.kind === "invoice")) return "invoiced";
  if (rows.some((r) => r.kind === "contribution" && r.status === "failed")) return "late";
  return "pending";
}
export const potTarget = (s: State, cycle: number) => (s.pot && currentCycle(s)?.n === cycle ? s.pot.target : s.rules.contribution * (MEMBERS.length - s.skips.filter((k) => k.cycle === cycle).length));
export const potCollected = (s: State, cycle: number) => (s.pot && currentCycle(s)?.n === cycle ? s.pot.collected : MEMBERS.reduce((sum, m) => sum + (memberStatus(s, m.id, cycle) === "paid" ? s.rules.contribution : 0), 0));
export type { Check };

// ---------- start-up ----------
let booted = false;
async function boot() {
  if (!booted) { booted = true; window.addEventListener("hashchange", applyRoute); setInterval(() => { if (document.hidden || !state.auth) return; if (state.gid) void sync(); else if (state.route.name === "groups") void refreshGroups(); }, 1500); }
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 2500);
    const r = await fetch(API + "/api/health", { signal: ctl.signal }); clearTimeout(t);
    if (!r.ok) throw new Error("unhealthy");
    const h = await r.json(); set({ sandbox: !!h.sandbox, mode: h.paypal, llm: h.llm ?? "none" });
  } catch { set({ api: "down" }); return; }
  if (token) { try { set({ auth: (await http<{ user: Account }>("/api/auth/me")).user }); } catch { /* the stored token expired */ } }
  set({ api: "up" });
  applyRoute();
}
void boot();

import { CalendarClock, Check, Coins, Dices, HeartHandshake, Repeat, ShieldCheck, Sparkles, TimerReset } from "lucide-react";
import type { Parsed } from "../state/store";
import type { RuleSet } from "../data/types";
import { money } from "./ui";

/** What the engine will enforce, as cards. Shared by the setup flow and the Rules page. */
export function RuleCards({ rules, busy = false }: { rules: RuleSet; busy?: boolean }) {
  const cards = [
    [Coins, "Contribution", `${money(rules.contribution)} from each of ${rules.members} members`], [CalendarClock, "Schedule", `A cycle every ${rules.cycleDays} days, ${rules.graceDays} day grace period`],
    [Dices, "Payout order", rules.order === "random" ? (rules.seed === "unset" ? "Random draw when the circle starts, recorded with its seed" : `Random draw, recorded with seed ${rules.seed}`) : "A fixed order agreed up front"],
    [TimerReset, "Late payments", rules.ladder.map((l) => `${l.after}: ${l.action}`).join(" · ")], [Repeat, "Swaps", rules.swap], [HeartHandshake, "Hardship", rules.hardship],
    [ShieldCheck, "Limits", `Never more than ${money(rules.maxPayout)} in one payout; a human approves anything over ${money(rules.approvalAbove)}`],
  ] as const;
  if (busy) return <>{Array.from({ length: 4 }).map((_, i) => <div key={i} className="rule-card" style={{ opacity: .5 }}><span className="rule-ic" /><div><h4>Reading…</h4><p>&nbsp;</p></div></div>)}</>;
  return <>{cards.map(([I, t, d], i) => <div className="rule-card" key={t} style={{ animationDelay: `${i * 50}ms` }}><span className="rule-ic"><I size={19} /></span><div><h4>{t}</h4><p>{d}</p></div></div>)}</>;
}

export function Findings({ parsed }: { parsed: Parsed | null }) {
  return (
    <>
      {parsed?.questions.length ? <div className="banner info" style={{ marginBottom: 0 }}><Sparkles size={18} /><span><b>I need to know:</b> {parsed.questions.join(" ")}</span></div> : null}
      {parsed?.problems.length ? <div className="banner bad" style={{ marginBottom: 0 }}><span><b>Conflict:</b> {parsed.problems.join(" ")}</span></div>
        : <div className="banner good" style={{ marginBottom: 0 }}><Check size={18} /><span>No conflicts. A hardship skip can't leave a pot short, and every limit is consistent.{parsed ? ` Read by: ${parsed.source}.` : ""}</span></div>}
    </>
  );
}

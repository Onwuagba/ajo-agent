import { CheckCircle2, Clock3, Coins } from "lucide-react";
import { memberById } from "../data/roster";
import { useStore } from "../state/store";
import { Avatar, Chip, money } from "./ui";

export function CycleStepper() {
  const cycles = useStore((s) => s.cycles);
  return (
    <div className="stepper">
      {cycles.map((c) => (
        <div key={c.n + c.recipient} className={`step ${c.status === "collecting" ? "now" : c.status} diff`}>
          <div className="row" style={{ justifyContent: "space-between" }}><span className="n">CYCLE {c.n}</span>
            {c.status === "paid" && <Chip tone="good" icon={<CheckCircle2 size={13} />}>Paid</Chip>}{c.status === "collecting" && <Chip tone="warn" icon={<Coins size={13} />}>Collecting</Chip>}{c.status === "upcoming" && <Chip icon={<Clock3 size={13} />}>Upcoming</Chip>}</div>
          <div className="who"><Avatar id={c.recipient} size={34} />{memberById(c.recipient).first}</div>
          <div className="amt num">{money(c.pot)}</div><div className="faint" style={{ fontSize: 13 }}>{c.date}</div>
        </div>))}
    </div>
  );
}

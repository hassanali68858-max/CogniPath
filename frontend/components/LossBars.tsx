import { GOALS, type Goal } from "@/lib/types";

const COLOR: Record<Goal, string> = { study: "var(--study)", career: "var(--career)", social: "var(--social)" };

/** Share of each goal's proposed value that the plan leaves out (0 % = everything kept). */
export function LossBars({ loss }: { loss: Record<Goal, number> }) {
  return (
    <div>
      {GOALS.map((g) => (
        <div className="loss" key={g}>
          <span>{g}</span>
          <div className="track">
            <div className="fill" style={{ width: `${Math.round(loss[g] * 100)}%`, background: COLOR[g] }} />
          </div>
          <span>{Math.round(loss[g] * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

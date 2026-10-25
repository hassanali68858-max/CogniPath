import { GOAL_META } from "@/lib/meta";
import { GOALS, type Goal } from "@/lib/types";

/** How much of each goal's suggested value made it into the plan (100 % = nothing left out). */
export function GoalMeters({ loss, compact = false }: { loss: Record<Goal, number>; compact?: boolean }) {
  return (
    <div className={`goal-meters${compact ? " compact" : ""}`}>
      {GOALS.map((g) => {
        const kept = Math.round((1 - loss[g]) * 100);
        const Icon = GOAL_META[g].icon;
        return (
          <div className="goal-meter" key={g} title={`${GOAL_META[g].label}: ${kept}% of suggested value kept`}>
            <span className="goal-name">
              <Icon size={13} /> {GOAL_META[g].label}
            </span>
            <div className="meter">
              <div className={`meter-fill ${g}`} style={{ width: `${kept}%` }} />
            </div>
            <span className="goal-pct">{kept}%</span>
          </div>
        );
      })}
    </div>
  );
}

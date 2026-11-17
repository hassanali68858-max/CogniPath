import { GOAL_META } from "@/lib/meta";
import { GOALS, type Goal } from "@/lib/types";

type Scores = { achieved: Partial<Record<Goal, number>>; ideal?: Partial<Record<Goal, number>> };

/**
 * How much of each goal's suggested value is in the plan (100 % = nothing left out).
 * The thin mark shows the best that goal could reach on its own: the gap is the price of balancing.
 */
export function GoalMeters({
  scores,
  compact = false,
  deltas,
}: {
  scores: Scores;
  compact?: boolean;
  deltas?: Partial<Record<Goal, number>>;
}) {
  return (
    <div className={`goal-meters${compact ? " compact" : ""}`}>
      {GOALS.map((g) => {
        const Icon = GOAL_META[g].icon;
        const a = scores.achieved[g];
        if (a === undefined)
          return (
            <div className="goal-meter" key={g} title={`Nothing was suggested for ${GOAL_META[g].label}`}>
              <span className="goal-name">
                <Icon size={13} /> {GOAL_META[g].label}
              </span>
              <div className="meter" />
              <span className="goal-pct faint">–</span>
            </div>
          );
        const kept = Math.round(a * 100);
        const best = scores.ideal?.[g];
        const d = deltas?.[g];
        return (
          <div
            className="goal-meter"
            key={g}
            title={`${GOAL_META[g].label}: ${kept}% of suggested value in this plan${best !== undefined ? ` (best possible ${Math.round(best * 100)}%)` : ""}`}
          >
            <span className="goal-name">
              <Icon size={13} /> {GOAL_META[g].label}
            </span>
            <div className="meter">
              <div className={`meter-fill ${g}`} style={{ width: `${kept}%` }} />
              {best !== undefined && <i className="meter-best" style={{ left: `${Math.round(best * 100)}%` }} />}
            </div>
            <span className="goal-pct">
              {kept}%
              {d !== undefined && Math.abs(d) >= 0.005 && (
                <em className={d > 0 ? "up" : "down"}>
                  {d > 0 ? "+" : "−"}
                  {Math.round(Math.abs(d) * 100)}
                </em>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

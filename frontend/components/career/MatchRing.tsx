/** Round match score (0-100). Shows a dash when the job has no score yet. */
export function MatchRing({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <div className="match-ring none" title="Not scored yet">
        <span>–</span>
      </div>
    );
  }
  return (
    <div className="match-ring" style={{ "--p": value } as React.CSSProperties} title={`${value}% skill match`}>
      <span>{value}%</span>
    </div>
  );
}

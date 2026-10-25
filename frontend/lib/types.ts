// TypeScript mirrors of shared/contracts (Python). Keep in sync when the contracts change.

export type Goal = "study" | "career" | "social";
export const GOALS: Goal[] = ["study", "career", "social"];

export type SourceAgent = "event" | "tutor" | "career" | "user";
export type Priority = "low" | "medium" | "high";
export type ActivityType = "event" | "learning" | "course_work" | "application" | "quiz" | "social" | "other";

export interface ActivityProposal {
  proposal_id: string;
  source_agent: SourceAgent;
  user_id: string;
  type: ActivityType;
  title: string;
  opportunity_ref?: string | null;
  resource_url?: string | null;
  fixed_time?: { start: string; end: string } | null;
  duration_min?: number | null;
  window?: { earliest: string; deadline: string } | null;
  split?: { min_session_min: number; max_session_min: number };
  value: Partial<Record<Goal, number>>;
  priority?: Priority;
  hard?: boolean;
  depends_on?: string[];
  location?: string | null;
  reason: string;
}

export interface BusyBlock {
  title: string;
  start: string;
  end: string;
}

export interface PlannerProfile {
  user_id: string;
  weights: Record<Goal, number>;
  day_start: string;
  day_end: string;
  evening_after: string;
  daily_cap_min: number;
  free_weekdays: number[];
  busy_blocks: BusyBlock[];
  fairness_weight: number;
  conflict_weight: number;
}

export type Decision = "pending" | "accepted" | "rejected";
export type PlanStatus = "draft" | "partial" | "approved" | "discarded" | "superseded";

export interface Session {
  start: string;
  end: string;
}

export interface PlanItem {
  item_id: string;
  proposal_id: string;
  source_agents: string[];
  title: string;
  sessions: Session[];
  value: Record<Goal, number>;
  explanation: string;
  decision: Decision;
}

export interface DroppedItem {
  proposal_id: string;
  source_agents: string[];
  title: string;
  explanation: string;
}

export interface PlanChanges {
  added: string[];
  removed: string[];
  moved: string[];
  kept: number;
  notes: string[];
  summary: string;
}

export interface Plan {
  plan_id: string;
  run_id?: string | null;
  based_on?: string | null;
  user_id: string;
  mode: string;
  horizon_start: string;
  horizon_end: string;
  status: PlanStatus;
  items: PlanItem[];
  dropped: DroppedItem[];
  scores: {
    loss: Record<Goal, number>;
    fairness_gap: number;
    soft_conflicts: number;
    scheduled_minutes: number;
  };
  solver_status: string;
  solve_seconds: number;
  changes?: PlanChanges | null;
}

export type ProposalStatus = "active" | "rejected" | "withdrawn";

export const MODES = ["balanced", "study_first", "career_first"] as const;

export type GoalType = 'study' | 'career' | 'social';
export type AgentSource = 'event' | 'tutor' | 'career' | 'user';
export type Decision = 'accepted' | 'rejected' | 'pending';
export type ChangeTag = 'NEW' | 'MOVED' | 'REJECTED' | 'UNCHANGED';

export interface ActivityProposal {
  proposal_id: string;
  source_agent: AgentSource;
  user_id: string;
  type: 'event' | 'learning' | 'course_work' | 'application' | 'quiz' | 'social' | 'other';
  title: string;
  reason: string;
  value: { study?: number; career?: number; social?: number };
  fixed_time?: { start: string; end: string };
  duration_min?: number;
  window?: { earliest: string; deadline: string };
  priority?: 'low' | 'medium' | 'high';
  hard?: boolean;
  depends_on?: string[];
  opportunity_ref?: string;
  resource_url?: string;
  location?: string;
}

export interface ScheduledItem {
  id: string;
  proposal: ActivityProposal;
  assigned_start: string; // ISO datetime e.g. "2026-11-04T14:00"
  assigned_end: string;
  status?: 'accepted' | 'rejected' | 'pending';
  change_tag?: ChangeTag;
}

export interface PlanVersion {
  id: string;
  version_type: 'balanced' | 'study_first' | 'career_first';
  kept_percentages: { study: number; career: number; social: number };
  items: ScheduledItem[];
  dropped_items: ActivityProposal[];
}

/* ---------- Career ---------- */
export interface InternshipMatch {
  id: string;
  title: string;
  org: string;
  deadline: string;
  match: number; // 0-100
  matchedSkills: string[];
  missingSkills: string[];
  coverLetter: string;
}

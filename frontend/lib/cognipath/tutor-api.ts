// Tutor Agent backend calls and response types (mirror backend/tutor.py and agents/tutor_agent).
// The browser calls /api/..., which next.config.ts forwards to the FastAPI backend.

export type MasteryLevel = 'strong' | 'weak' | 'untested';

export interface ModuleProgress {
  module_id: string;
  name: string;
  completed_credits: number;
  required_credits: number;
}

export interface ProgressReport {
  programme_name: string;
  completed_credits: number;
  required_credits: number;
  required_pace: number;
  status: 'on_track' | 'at_risk';
  modules: ModuleProgress[];
  current_courses: { code: string; name: string; credits: number; exam_date?: string | null }[];
  warnings: { kind: 'missing_mandatory' | 'missing_prerequisite' | 'behind_pace'; message: string }[];
}

export interface TopicStatus {
  topic_id: string;
  name: string;
  course_code: string;
  mastery: number | null; // 0-1
  level: MasteryLevel;
  next_review?: string | null; // strong topics only: when a refresh quiz is due
}

export interface TutorReport {
  proposals: { proposal_id: string }[];
  progress: ProgressReport;
  topics: TopicStatus[];
}

export interface QuizView {
  quiz_id: string;
  topic_id: string;
  topic_name: string;
  questions: { prompt: string; options: string[] }[];
}

export interface QuizResult {
  correct: number;
  total: number;
  answer_indexes: number[];
  mastery_before: number | null;
  mastery_after: number;
}

/** Where the course data comes from: the seed files, or live from JYU Sisu (agents/tutor_agent/sisu.py). */
export interface CatalogSource {
  source: 'seed' | 'sisu';
  url: string | null;
  linked: Record<string, string>; // seed code -> Sisu code
  unavailable: string[];
}

export interface UpcomingCourse {
  code: string;
  name: string;
  credits: number;
  language: string;
  start: string;
  end: string;
  registration_deadline: string;
  from_sisu: boolean;
}

/** The demo student and planning window, shared with the Planner demo. */
export interface TutorContext {
  userId: string;
  today: string;
  days: number;
}

export const tutorApi = {
  context: async (): Promise<TutorContext> => {
    const info = await call<{ user_id: string; horizon_start: string; days: number }>('/demo/info');
    return { userId: info.user_id, today: info.horizon_start, days: info.days };
  },
  report: (c: TutorContext) => call<TutorReport>(`/tutor/${enc(c.userId)}/report?${window_(c)}`),
  catalogSource: () => call<CatalogSource>('/tutor/catalog/source'),
  upcomingCourses: (c: TutorContext) => call<UpcomingCourse[]>(`/tutor/${enc(c.userId)}/courses?today=${c.today}`),
  sendToPlanner: (c: TutorContext) =>
    call<{ stored: number; withdrawn: string[] }>(`/tutor/${enc(c.userId)}/proposals?${window_(c)}`, { method: 'POST' }),
  newQuiz: (c: TutorContext, topicId: string) =>
    call<QuizView>(`/tutor/${enc(c.userId)}/quizzes`, { method: 'POST', body: JSON.stringify({ topic_id: topicId }) }),
  submitAnswers: (c: TutorContext, quizId: string, answers: number[]) =>
    call<QuizResult>(`/tutor/${enc(c.userId)}/quizzes/${enc(quizId)}/answers?today=${c.today}`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),
};

const enc = encodeURIComponent;
const window_ = (c: TutorContext) => `today=${c.today}&days=${c.days}`;

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, { ...init, headers: { 'Content-Type': 'application/json' } });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `The backend answered ${res.status}`);
  }
  return res.json();
}

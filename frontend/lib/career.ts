// Calls to the Career Agent API (agents/career_agent/src/api.py).
// It runs on its own port: uvicorn api:app --reload --port 8001

export const CAREER_URL = process.env.NEXT_PUBLIC_CAREER_URL ?? "http://127.0.0.1:8001";

export const STATUSES = ["planned", "applied", "interview", "rejected", "offer"] as const;
export type Status = (typeof STATUSES)[number];

export type CareerProfile = {
  countries: string[];
  job_types: string[];
  work_mode: string;
  target_title: string;
  interests: string[];
  saved?: boolean;
};

export type Job = {
  id: number;
  title: string;
  company: string;
  summary: string | null; // one sentence about the ad, written by the enricher
  url: string | null;
  deadline: string | null; // apply deadline found in the ad (YYYY-MM-DD)
  match: number | null; // 0-100, null if the pipeline has not scored this job for the user
  status: Status | null; // null = not in the tracker yet
  application_id: number | null;
};

export type Application = {
  application_id: number;
  title: string;
  company: string;
  match: number | null; // 0-1
  deadline: string | null;
  status: Status;
  interview_date: string | null;
};

// FastAPI errors look like {"detail": "text"}
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${CAREER_URL}${path}`, init);
  } catch {
    throw new Error("Career Agent is not running. Start it with: uvicorn api:app --reload --port 8001");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Career API answered ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const enc = encodeURIComponent;
const json = (body: unknown) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const careerApi = {
  getProfile: (u: string) => call<CareerProfile>(`/profile/${enc(u)}`),
  saveProfile: (u: string, p: CareerProfile) => call<{ status: string }>(`/profile/${enc(u)}`, json(p)),
  uploadCv: (u: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<{ skills: string[] }>(`/cv/${enc(u)}`, { method: "POST", body: form });
  },
  runPipeline: (u: string) => call<{ status: string }>(`/run/${enc(u)}`, { method: "POST" }),
  searchJobs: (u: string, q: string) => call<Job[]>(`/jobs/${enc(u)}?q=${enc(q)}`),
  tracker: (u: string) => call<Application[]>(`/tracker/${enc(u)}`),
  track: (u: string, title: string, applied: boolean) =>
    call<{ status: string; application_id: number }>(`/tracker/${enc(u)}`, json({ title, applied })),
  updateStatus: (u: string, appId: number, status: Status, interview_date?: string) =>
    call<{ status: string }>(`/tracker/${enc(u)}/${appId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, interview_date: interview_date || null }),
    }),
  calendarUrl: (u: string) => `${CAREER_URL}/calendar/${enc(u)}`,
  jobCalendarUrl: (u: string, jobId: number) => `${CAREER_URL}/calendar/${enc(u)}/job/${jobId}`,
};

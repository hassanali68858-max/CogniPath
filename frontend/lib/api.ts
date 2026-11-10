// Small client for the CogniPath backend. All calls go to /api/..., which
// next.config.ts forwards to the FastAPI server.

import type { ActivityProposal, Decision, Plan, PlannerProfile, Preference, ProposalStatus } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// FastAPI errors look like {"detail": "text"} or {"detail": [{"loc": [...], "msg": "..."}]}
function describe(body: unknown): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".") || "body"}: ${d.msg}`)
      .join("\n");
  }
  return JSON.stringify(body);
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Cannot reach the backend. Is `uvicorn backend.main:app --reload` running?");
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    if (res.status >= 500 && !body) throw new ApiError(res.status, "Backend error or backend not running.");
    throw new ApiError(res.status, describe(body));
  }
  return body as T;
}

const json = (data: unknown) => JSON.stringify(data);
const enc = encodeURIComponent;

export const api = {
  health: () => call<{ status: string }>("/health"),
  demoInfo: () => call<{ user_id: string; horizon_start: string; days: number }>("/demo/info"),
  seed: () => call<{ proposals: number }>("/demo/seed", { method: "POST" }),
  reset: (userId: string) => call<unknown>(`/demo/reset/${enc(userId)}`, { method: "POST" }),

  getProfile: (userId: string) => call<PlannerProfile>(`/profiles/${enc(userId)}`),
  putProfile: (p: PlannerProfile) => call<PlannerProfile>(`/profiles/${enc(p.user_id)}`, { method: "PUT", body: json(p) }),

  listProposals: (userId: string, status: ProposalStatus) =>
    call<ActivityProposal[]>(`/proposals?user_id=${enc(userId)}&status=${status}`),
  addProposals: (ps: ActivityProposal[]) => call<{ stored: number }>("/proposals", { method: "POST", body: json(ps) }),
  withdraw: (userId: string, proposalId: string) =>
    call<unknown>(`/proposals/${enc(userId)}/${enc(proposalId)}/withdraw`, { method: "POST" }),

  run: (userId: string, horizonStart: string, days: number) =>
    call<Plan[]>("/planner/runs", { method: "POST", body: json({ user_id: userId, horizon_start: horizonStart, days }) }),
  getRun: (runId: string) => call<Plan[]>(`/planner/runs/${enc(runId)}`),
  steer: (planId: string, pref: Preference) =>
    call<Plan>(`/planner/plans/${enc(planId)}/nimbus`, { method: "POST", body: json(pref) }),
  currentPlan: (userId: string) => call<Plan>(`/planner/users/${enc(userId)}/current`),
  getPlan: (planId: string) => call<Plan>(`/planner/plans/${enc(planId)}`),
  decide: (planId: string, decisions: { item_id: string; decision: Decision }[]) =>
    call<Plan>(`/planner/plans/${enc(planId)}/decisions`, { method: "POST", body: json(decisions) }),
  replan: (planId: string, notBefore?: string, modes?: string[]) =>
    call<Plan[]>(`/planner/plans/${enc(planId)}/replan`, {
      method: "POST",
      body: json({ not_before: notBefore || null, modes: modes?.length ? modes : null }),
    }),
  icsUrl: (planId: string) => `/api/planner/plans/${enc(planId)}/ics`,
};

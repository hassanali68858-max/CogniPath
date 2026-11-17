"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { ActivityProposal, Plan, PlannerProfile } from "@/lib/types";

import { useUser } from "./UserProvider";

export type AppStatus = {
  loading: boolean;
  backend: boolean;
  profile: PlannerProfile | null;
  proposals: ActivityProposal[];
  plan: Plan | null;
  /** active proposals the current plan has not considered yet */
  newSincePlan: ActivityProposal[];
};

const EMPTY: AppStatus = { loading: true, backend: true, profile: null, proposals: [], plan: null, newSincePlan: [] };

type Ctx = { status: AppStatus; refresh: () => Promise<void> };
const StatusContext = createContext<Ctx>({ status: EMPTY, refresh: async () => {} });

function unseen(proposals: ActivityProposal[], plan: Plan | null): ActivityProposal[] {
  if (!plan) return [];
  const seen = new Set([...plan.items.map((i) => i.proposal_id), ...plan.dropped.map((d) => d.proposal_id)]);
  const seenRefs = new Set(
    proposals.filter((p) => seen.has(p.proposal_id) && p.opportunity_ref).map((p) => p.opportunity_ref),
  );
  return proposals.filter((p) => !seen.has(p.proposal_id) && !(p.opportunity_ref && seenRefs.has(p.opportunity_ref)));
}

/** Loads what the guide and the sidebar need: is the backend up, is there a profile, proposals, a plan. */
export function StatusProvider({ children }: { children: React.ReactNode }) {
  const { userId } = useUser();
  const [status, setStatus] = useState<AppStatus>(EMPTY);

  const refresh = useCallback(async () => {
    const backend = await api.health().then(
      () => true,
      () => false,
    );
    if (!backend) {
      setStatus({ ...EMPTY, loading: false, backend: false });
      return;
    }
    const [profile, proposals, plan] = await Promise.all([
      api.getProfile(userId).catch(() => null),
      api.listProposals(userId, "active").catch(() => [] as ActivityProposal[]),
      api.currentPlan(userId).catch(() => null),
    ]);
    setStatus({ loading: false, backend, profile, proposals, plan, newSincePlan: unseen(proposals, plan) });
  }, [userId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return <StatusContext.Provider value={{ status, refresh }}>{children}</StatusContext.Provider>;
}

export const useStatus = () => useContext(StatusContext);

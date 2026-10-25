"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Message, type Msg, errorText } from "@/components/Message";
import { useUser } from "@/components/UserProvider";
import { api } from "@/lib/api";
import type { ActivityProposal, Plan } from "@/lib/types";

type Status = {
  backend: boolean;
  profile: boolean;
  proposals: ActivityProposal[];
  plan: Plan | null;
};

export default function Home() {
  const { userId, setUserId } = useUser();
  const [draftId, setDraftId] = useState(userId);
  const [status, setStatus] = useState<Status | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => setDraftId(userId), [userId]);

  const refresh = useCallback(async () => {
    const backend = await api.health().then(
      () => true,
      () => false,
    );
    if (!backend) {
      setStatus({ backend, profile: false, proposals: [], plan: null });
      return;
    }
    const [profile, proposals, plan] = await Promise.all([
      api.getProfile(userId).then(
        () => true,
        () => false,
      ),
      api.listProposals(userId, "active").catch(() => [] as ActivityProposal[]),
      api.currentPlan(userId).catch(() => null),
    ]);
    setStatus({ backend, profile, proposals, plan });
  }, [userId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function seed() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.seed();
      setUserId("student001");
      setMsg({ kind: "ok", text: `Loaded the demo student001: profile + ${r.proposals} proposals.` });
      await refresh();
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    if (!confirmReset) {
      setConfirmReset(true);
      return;
    }
    setConfirmReset(false);
    setBusy(true);
    try {
      await api.reset(userId);
      setMsg({ kind: "ok", text: `Deleted everything stored for ${userId}.` });
      await refresh();
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }

  const byAgent = (agent: string) => status?.proposals.filter((p) => p.source_agent === agent).length ?? 0;

  return (
    <>
      <h1>Planner test UI</h1>
      <p className="lead">
        A simple front end for the Planner API. Agents send proposals, the planner builds a plan, the student accepts or
        rejects items, and re-planning keeps what was accepted.
      </p>

      <div className="grid2">
        <section className="panel">
          <h2>Student</h2>
          <div className="row">
            <label>
              user_id
              <input value={draftId} onChange={(e) => setDraftId(e.target.value.trim())} />
            </label>
            <button onClick={() => draftId && setUserId(draftId)} disabled={!draftId || draftId === userId}>
              Use this student
            </button>
          </div>

          <h3>Demo data</h3>
          <p className="muted small">
            Loads the mock profile (lectures, work shifts, 3 h/day limit) and 20 proposals from the Event, Tutor and
            Career agents for <b>student001</b>.
          </p>
          <div className="row">
            <button className="primary" onClick={seed} disabled={busy}>
              Load demo data
            </button>
            <button className="danger" onClick={reset} disabled={busy}>
              {confirmReset ? `Click again to delete ${userId}` : `Reset ${userId}`}
            </button>
            <button onClick={refresh} disabled={busy}>
              Refresh
            </button>
          </div>
          <Message msg={msg} />
        </section>

        <section className="panel">
          <h2>Status</h2>
          {!status ? (
            <p className="muted">Checking…</p>
          ) : (
            <dl className="kv">
              <dt>Backend</dt>
              <dd>
                {status.backend ? (
                  <span className="badge accepted">running</span>
                ) : (
                  <span className="badge rejected">not reachable</span>
                )}
              </dd>
              <dt>Profile</dt>
              <dd>{status.profile ? "saved" : <Link href="/profile">not set yet</Link>}</dd>
              <dt>Active proposals</dt>
              <dd>
                {status.proposals.length} (event {byAgent("event")} · tutor {byAgent("tutor")} · career{" "}
                {byAgent("career")} · user {byAgent("user")})
              </dd>
              <dt>Current plan</dt>
              <dd>
                {status.plan ? (
                  <>
                    <span className={`badge ${status.plan.status}`}>{status.plan.status}</span>{" "}
                    {status.plan.items.length} items, {status.plan.dropped.length} dropped ·{" "}
                    <Link href="/plan">open</Link>
                  </>
                ) : (
                  "none yet"
                )}
              </dd>
            </dl>
          )}
          {status && !status.backend && (
            <p className="msg error">
              Start the backend from the repository root: <code>uvicorn backend.main:app --reload</code>
            </p>
          )}
        </section>
      </div>

      <section className="panel">
        <h2>How the flow works</h2>
        <ol className="steps">
          <li>
            <b>
              <Link href="/profile">Profile</Link>
            </b>{" "}
            — when the student is busy (lectures, shifts), day hours, daily limit and how much they care about study,
            career and social. Saved with <code>PUT /profiles/&#123;user_id&#125;</code>.
          </li>
          <li>
            <b>
              <Link href="/proposals">Proposals</Link>
            </b>{" "}
            — what the Event, Tutor and Career agents suggest. Fixed events have a start and end; flexible work has a
            duration and a deadline. Sent with <code>POST /proposals</code>.
          </li>
          <li>
            <b>
              <Link href="/plan">Plan</Link>
            </b>{" "}
            — the optimiser picks what to keep and when, with no overlaps, deadlines met and the daily limit respected,
            balancing the three goals. Every kept and dropped item is explained.
          </li>
          <li>
            <b>Decide</b> — accept or reject items. Rejected proposals are never planned again.
          </li>
          <li>
            <b>Re-plan</b> — after new proposals or a cancelled event, accepted items stay where they are and only the
            rest moves. The plan shows what changed.
          </li>
        </ol>
      </section>
    </>
  );
}

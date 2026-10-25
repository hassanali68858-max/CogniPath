"use client";

import { ArrowRight, CalendarCheck, Database, Loader2, RotateCcw, Scale, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AgentAvatar } from "@/components/AgentBadge";
import { useStatus } from "@/components/StatusProvider";
import { errorText, useToast } from "@/components/Toast";
import { useUser } from "@/components/UserProvider";
import { api } from "@/lib/api";
import { AGENTS, GOAL_META } from "@/lib/meta";
import { GOALS } from "@/lib/types";

export default function StartPage() {
  const { status, refresh } = useStatus();
  const { userId, setUserId } = useUser();
  const toast = useToast();
  const [busy, setBusy] = useState<"seed" | "reset" | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const pending = status.plan?.items.filter((i) => i.decision === "pending").length ?? 0;

  async function seed() {
    setBusy("seed");
    try {
      const r = await api.seed();
      setUserId("student001");
      toast("success", "Demo student loaded", `student001 now has a profile and ${r.proposals} suggestions.`);
      await refresh();
    } catch (e) {
      toast("error", "Could not load the demo", errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function reset() {
    if (!confirmReset) {
      setConfirmReset(true);
      setTimeout(() => setConfirmReset(false), 4000);
      return;
    }
    setConfirmReset(false);
    setBusy("reset");
    try {
      await api.reset(userId);
      toast("success", `Cleared ${userId}`, "Profile, suggestions, plans and decisions were deleted.");
      await refresh();
    } catch (e) {
      toast("error", "Could not reset", errorText(e));
    } finally {
      setBusy(null);
    }
  }

  const journey = [
    {
      href: "/profile",
      title: "About you",
      body: "Your day hours, a daily limit, fixed commitments like lectures, and how much study, career and social matter.",
      done: !!status.profile,
      status: status.profile ? "Saved" : "To do",
    },
    {
      href: "/suggestions",
      title: "Suggestions",
      body: "The Event, Tutor and Career agents propose things to do. Fixed events, or work with a deadline.",
      done: status.proposals.length > 0,
      status: status.proposals.length ? `${status.proposals.length} waiting` : "None yet",
    },
    {
      href: "/plan",
      title: "Your plan",
      body: "The planner fits the best mix into your week, never overlapping, and explains every choice.",
      done: !!status.plan,
      status: status.plan ? `${status.plan.items.length} planned · ${status.plan.dropped.length} didn't fit` : "Not made yet",
    },
    {
      href: "/plan",
      title: "Decide & adapt",
      body: "Accept or reject items. When something changes, re-plan: accepted items stay, the rest adapts.",
      done: !!status.plan && pending === 0,
      status: status.plan ? (pending ? `${pending} to review` : "All decided") : "After planning",
    },
  ];

  return (
    <>
      <section className="hero">
        <div>
          <span className="eyebrow">CogniPath · Planner Agent</span>
          <h1>
            Your week, <span>balanced</span>.
          </h1>
          <p>
            Three agents suggest events, study tasks and career steps. The planner turns them into one realistic plan
            that respects your time and doesn&apos;t let any goal fall behind. You stay in charge of every decision.
          </p>
          <div className="hero-actions">
            {!status.profile && !status.proposals.length ? (
              <button className="btn primary big" onClick={seed} disabled={!!busy || !status.backend}>
                {busy === "seed" ? <Loader2 size={18} className="spin" /> : <Sparkles size={18} />}
                Try it with the demo student
              </button>
            ) : (
              <Link className="btn primary big" href="/plan">
                <CalendarCheck size={18} /> Open your plan <ArrowRight size={18} />
              </Link>
            )}
            <Link className="btn big" href="/profile">
              Set up my own profile
            </Link>
          </div>
        </div>

        <div className="flow-visual" aria-label="How CogniPath works">
          <div className="flow-agents">
            {(["event", "tutor", "career"] as const).map((a) => (
              <div className="flow-node" key={a}>
                <AgentAvatar agent={a} size={28} />
                {AGENTS[a].short}
              </div>
            ))}
          </div>
          <div className="flow-arrow">suggest activities ↓</div>
          <div className="flow-node planner">
            <Scale size={18} /> Planner balances study · career · social
          </div>
          <div className="flow-arrow">one plan, every choice explained ↓</div>
          <div className="flow-node you">You accept, reject, and it adapts</div>
        </div>
      </section>

      <div className="card-head">
        <div className="grow">
          <h2>How it works, step by step</h2>
          <p>Follow the steps in order. The banner at the top always tells you what to do next.</p>
        </div>
      </div>
      <div className="journey" style={{ marginBottom: 20 }}>
        {journey.map((j, i) => (
          <Link key={j.title} href={j.href} className={`journey-card${j.done ? " done" : ""}`}>
            <span className="num">{j.done ? "✓" : i + 1}</span>
            <h3>{j.title}</h3>
            <p>{j.body}</p>
            <span className="status">{status.loading ? "…" : j.status}</span>
          </Link>
        ))}
      </div>

      <div className="grid two">
        <section className="card">
          <div className="card-head">
            <div className="grow">
              <h2>How the planner decides</h2>
              <p>Every suggestion has a value for each goal. The planner keeps as much value as it can.</p>
            </div>
          </div>
          <div className="explain-goals">
            {GOALS.map((g) => {
              const Icon = GOAL_META[g].icon;
              return (
                <div className="explain-goal" key={g}>
                  <Icon size={18} className="muted" />
                  <div>
                    <b>{GOAL_META[g].label}</b>
                    <p className="small muted">{GOAL_META[g].question}</p>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="small muted" style={{ marginTop: 14 }}>
            Hard rules: nothing overlaps, deadlines are met, your daily limit is respected, must-do items always stay.
            A fairness rule stops one goal from being sacrificed for the others.
          </p>
        </section>

        <section className="card">
          <div className="card-head">
            <div className="grow">
              <h2>Demo data</h2>
              <p>
                Working as <b>{userId}</b>. Change the student in the sidebar.
              </p>
            </div>
          </div>
          <div className="row">
            <button className="btn" onClick={seed} disabled={!!busy || !status.backend}>
              {busy === "seed" ? <Loader2 size={16} className="spin" /> : <Database size={16} />}
              Load demo student
            </button>
            <button className="btn danger" onClick={reset} disabled={!!busy || !status.backend}>
              {busy === "reset" ? <Loader2 size={16} className="spin" /> : <RotateCcw size={16} />}
              {confirmReset ? `Click again to clear ${userId}` : `Clear ${userId}`}
            </button>
          </div>
          <p className="small faint" style={{ marginTop: 12 }}>
            The demo student has lectures, two work shifts, a 3-hour daily limit and 20 suggestions for 2–15 November
            2026, including the Career Agent prototype&apos;s &quot;Learn Docker&quot;.
          </p>
        </section>
      </div>
    </>
  );
}

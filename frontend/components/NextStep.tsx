"use client";

import { ArrowRight, CalendarCheck, Compass, Database, Inbox, Loader2, PartyPopper, RefreshCw, Server, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api";

import { type AppStatus, useStatus } from "./StatusProvider";
import { errorText, useToast } from "./Toast";
import { useUser } from "./UserProvider";

type Step = {
  icon: typeof Compass;
  tone: "brand" | "warn" | "done";
  title: string;
  body: string;
  href?: string;
  action?: "seed" | "refresh";
  cta: string;
};

/** The one thing the user should do next, based on what is stored. */
export function nextStep(s: AppStatus): Step {
  if (!s.backend)
    return {
      icon: Server,
      tone: "warn",
      title: "The backend is not running",
      body: "Start it in a terminal from the CogniPath folder: uvicorn backend.main:app --reload",
      action: "refresh",
      cta: "Check again",
    };
  if (!s.profile && !s.proposals.length)
    return {
      icon: Database,
      tone: "brand",
      title: "Start with the demo student",
      body: "Loads a student with lectures and work shifts, plus 20 suggestions from the Event, Tutor and Career agents.",
      action: "seed",
      cta: "Load demo student",
    };
  if (!s.profile)
    return {
      icon: SlidersHorizontal,
      tone: "brand",
      title: "Tell the planner about your week",
      body: "Your day hours, daily limit, fixed commitments and what matters most to you.",
      href: "/profile",
      cta: "Set up About you",
    };
  if (!s.proposals.length)
    return {
      icon: Inbox,
      tone: "brand",
      title: "No suggestions yet",
      body: "The agents have not sent anything. Load the demo suggestions or add one yourself.",
      href: "/suggestions",
      cta: "Go to Suggestions",
    };
  if (!s.plan)
    return {
      icon: CalendarCheck,
      tone: "brand",
      title: "Make your plan",
      body: `${s.proposals.length} suggestions are waiting. The planner will fit what it can into your week and explain the rest.`,
      href: "/plan",
      cta: "Open Your plan",
    };
  if (s.newSincePlan.length)
    return {
      icon: RefreshCw,
      tone: "brand",
      title: `${s.newSincePlan.length} new suggestion${s.newSincePlan.length > 1 ? "s" : ""} since your plan`,
      body: "Re-plan to fit them in. Everything you accepted stays where it is.",
      href: "/plan",
      cta: "Re-plan",
    };
  const pending = s.plan.items.filter((i) => i.decision === "pending").length;
  if (pending)
    return {
      icon: Compass,
      tone: "brand",
      title: `Review your plan: ${pending} item${pending > 1 ? "s" : ""} to decide`,
      body: "Accept what you will do, reject what you won't. Rejected suggestions are never planned again.",
      href: "/plan",
      cta: "Review plan",
    };
  return {
    icon: PartyPopper,
    tone: "done",
    title: "Your plan is decided",
    body: "Try what happens when something changes: add an event as an agent, then re-plan.",
    href: "/suggestions",
    cta: "Simulate an agent",
  };
}

export function NextStep() {
  const { status, refresh } = useStatus();
  const { setUserId } = useUser();
  const toast = useToast();
  const path = usePathname();
  const [busy, setBusy] = useState(false);

  if (status.loading) return null;
  const step = nextStep(status);
  const here = step.href === path;
  const Icon = step.icon;

  async function run() {
    setBusy(true);
    try {
      if (step.action === "seed") {
        const r = await api.seed();
        setUserId("student001");
        toast("success", "Demo student loaded", `Profile and ${r.proposals} suggestions for student001.`);
      }
      await refresh();
    } catch (e) {
      toast("error", "Something went wrong", errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`next-step tone-${step.tone}`}>
      <div className="next-icon">
        <Icon size={20} />
      </div>
      <div className="next-text">
        <span className="eyebrow">Next step</span>
        <b>{step.title}</b>
        <p>{step.body}</p>
      </div>
      {step.action ? (
        <button className="btn primary" onClick={run} disabled={busy}>
          {busy ? <Loader2 size={16} className="spin" /> : null}
          {step.cta}
        </button>
      ) : here ? (
        <span className="next-here">You are here ↓</span>
      ) : (
        <Link className="btn primary" href={step.href!}>
          {step.cta} <ArrowRight size={16} />
        </Link>
      )}
    </div>
  );
}

"use client";

import { CalendarCheck, CircleCheckBig, CircleDashed, Compass, Inbox, SlidersHorizontal, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { NextStep } from "./NextStep";
import { useStatus } from "./StatusProvider";
import { useUser } from "./UserProvider";

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { status } = useStatus();
  const { userId, setUserId } = useUser();
  const [draft, setDraft] = useState(userId);
  useEffect(() => setDraft(userId), [userId]);

  const pending = status.plan?.items.filter((i) => i.decision === "pending").length ?? 0;
  const steps = [
    { href: "/", label: "Start", icon: Compass, done: !!status.profile || status.proposals.length > 0, hint: "Overview" },
    {
      href: "/profile",
      label: "About you",
      icon: SlidersHorizontal,
      done: !!status.profile,
      hint: status.profile ? `${status.profile.busy_blocks.length} commitments` : "Not set up",
    },
    {
      href: "/suggestions",
      label: "Suggestions",
      icon: Inbox,
      done: status.proposals.length > 0,
      hint: `${status.proposals.length} from agents`,
    },
    {
      href: "/plan",
      label: "Your plan",
      icon: CalendarCheck,
      done: !!status.plan && pending === 0,
      hint: status.plan ? (pending ? `${pending} to review` : "All decided") : "Not made yet",
    },
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <span className="brand-mark">
            <Sparkles size={16} />
          </span>
          <span>
            CogniPath
            <small>Planner</small>
          </span>
        </Link>

        <nav className="steps-nav">
          {steps.map((s, i) => {
            const Icon = s.icon;
            return (
              <Link key={s.href} href={s.href} className={`step-link${path === s.href ? " active" : ""}`}>
                <span className="step-icon">
                  <Icon size={17} />
                </span>
                <span className="step-text">
                  <span>
                    {i > 0 && <span className="step-num">{i}</span>}
                    {s.label}
                  </span>
                  <small>{status.loading ? "…" : s.hint}</small>
                </span>
                {i > 0 &&
                  (s.done ? (
                    <CircleCheckBig size={16} className="step-done" />
                  ) : (
                    <CircleDashed size={16} className="step-todo" />
                  ))}
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-foot">
          <label className="field-label" htmlFor="student">
            Student
          </label>
          <form
            className="student-switch"
            onSubmit={(e) => {
              e.preventDefault();
              if (draft) setUserId(draft);
            }}
          >
            <input id="student" value={draft} onChange={(e) => setDraft(e.target.value.trim())} />
            {draft !== userId && (
              <button className="btn small" type="submit">
                Switch
              </button>
            )}
          </form>
          <span className={`backend-dot ${status.backend ? "up" : "down"}`}>
            {status.backend ? "Backend connected" : "Backend offline"}
          </span>
        </div>
      </aside>

      <div className="content">
        <NextStep />
        <main>{children}</main>
      </div>
    </div>
  );
}

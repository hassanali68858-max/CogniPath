"use client";

import { Ban, CalendarClock, Clock, FileJson, Flag, Hourglass, Inbox, Link2, Loader2, Lock, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AgentBadge } from "@/components/AgentBadge";
import { Drawer } from "@/components/Drawer";
import { useStatus } from "@/components/StatusProvider";
import { errorText, useToast } from "@/components/Toast";
import { useUser } from "@/components/UserProvider";
import { api } from "@/lib/api";
import { dayLabel, minutesLabel, rangeLabel, slug } from "@/lib/format";
import { AGENTS, GOAL_META } from "@/lib/meta";
import {
  type ActivityProposal,
  type ActivityType,
  GOALS,
  type Goal,
  type Priority,
  type ProposalStatus,
  type SourceAgent,
} from "@/lib/types";

const PREFIX: Record<SourceAgent, string> = { event: "evt", tutor: "tut", career: "car", user: "usr" };
const STATUS_LABEL: Record<ProposalStatus, string> = {
  active: "Waiting",
  rejected: "Rejected by you",
  withdrawn: "Withdrawn by agent",
};
const DEFAULT_TYPE: Record<SourceAgent, ActivityType> = {
  event: "event",
  tutor: "course_work",
  career: "learning",
  user: "other",
};

function GoalDots({ value }: { value: ActivityProposal["value"] }) {
  return (
    <div className="goal-dots">
      {GOALS.filter((g) => (value[g] ?? 0) > 0).map((g) => {
        const Icon = GOAL_META[g].icon;
        return (
          <span className="goal-dot" key={g} title={`${GOAL_META[g].label} value ${value[g]}`}>
            <Icon size={12} />
            {GOAL_META[g].label}
            <i>
              <b style={{ width: `${(value[g] ?? 0) * 100}%`, background: `var(--${g})` }} />
            </i>
          </span>
        );
      })}
    </div>
  );
}

function When({ p }: { p: ActivityProposal }) {
  if (p.fixed_time)
    return (
      <span className="when">
        <CalendarClock size={14} /> {rangeLabel(p.fixed_time.start, p.fixed_time.end)}
      </span>
    );
  return (
    <span className="when">
      <Hourglass size={14} /> {minutesLabel(p.duration_min ?? 0)} · {dayLabel(p.window!.earliest)} → due{" "}
      {dayLabel(p.window!.deadline)}
    </span>
  );
}

type Form = {
  agent: SourceAgent;
  title: string;
  reason: string;
  kind: "fixed" | "flexible";
  start: string;
  end: string;
  duration: number;
  earliest: string;
  deadline: string;
  value: Record<Goal, number>;
  priority: Priority;
  hard: boolean;
};

const EMPTY_FORM: Form = {
  agent: "event",
  title: "Hack night",
  reason: "New event matching your interests",
  kind: "fixed",
  start: "2026-11-12T17:00",
  end: "2026-11-12T19:00",
  duration: 120,
  earliest: "2026-11-02",
  deadline: "2026-11-15",
  value: { study: 0, career: 0.6, social: 0.6 },
  priority: "high",
  hard: false,
};

export default function SuggestionsPage() {
  const { userId } = useUser();
  const { refresh } = useStatus();
  const toast = useToast();
  const [status, setStatus] = useState<ProposalStatus>("active");
  const [agent, setAgent] = useState<SourceAgent | "all">("all");
  const [items, setItems] = useState<ActivityProposal[] | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [tab, setTab] = useState<"form" | "json">("form");
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [bulk, setBulk] = useState("");
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await api.listProposals(userId, status));
    } catch (e) {
      setItems([]);
      toast("error", "Could not load suggestions", errorText(e));
    }
  }, [userId, status, toast]);

  useEffect(() => {
    setItems(null);
    load();
  }, [load]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: items?.length ?? 0 };
    for (const p of items ?? []) c[p.source_agent] = (c[p.source_agent] ?? 0) + 1;
    return c;
  }, [items]);
  const shown = (items ?? []).filter((p) => agent === "all" || p.source_agent === agent);

  async function withdraw(p: ActivityProposal) {
    try {
      await api.withdraw(userId, p.proposal_id);
      toast("info", `${AGENTS[p.source_agent].label} withdrew “${p.title}”`, "Re-plan to update your plan.");
      await Promise.all([load(), refresh()]);
    } catch (e) {
      toast("error", "Could not withdraw", errorText(e));
    }
  }

  async function send(list: ActivityProposal[]) {
    setSending(true);
    try {
      const r = await api.addProposals(list);
      toast(
        "success",
        `Sent ${r.stored} suggestion${r.stored > 1 ? "s" : ""} to the planner`,
        "Go to Your plan and re-plan to fit it in.",
      );
      setDrawer(false);
      setStatus("active");
      await Promise.all([load(), refresh()]);
    } catch (e) {
      toast("error", "The planner refused it", errorText(e));
    } finally {
      setSending(false);
    }
  }

  function sendForm() {
    const p: ActivityProposal = {
      proposal_id: `${PREFIX[form.agent]}-${slug(form.title)}`,
      source_agent: form.agent,
      user_id: userId,
      type: form.kind === "fixed" && form.agent === "event" ? "event" : DEFAULT_TYPE[form.agent],
      title: form.title,
      reason: form.reason,
      value: form.value,
      priority: form.priority,
      hard: form.hard,
      ...(form.kind === "fixed"
        ? { fixed_time: { start: form.start, end: form.end } }
        : { duration_min: form.duration, window: { earliest: form.earliest, deadline: form.deadline } }),
    };
    send([p]);
  }

  function sendJson() {
    try {
      const parsed = JSON.parse(bulk);
      const list: ActivityProposal[] = (Array.isArray(parsed) ? parsed : [parsed]).map((p: ActivityProposal) => ({
        ...p,
        user_id: p.user_id ?? userId,
      }));
      send(list);
    } catch (e) {
      toast("error", "That is not valid JSON", errorText(e));
    }
  }

  const f = <K extends keyof Form>(key: K, value: Form[K]) => setForm((x) => ({ ...x, [key]: value }));

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Step 2</span>
          <h1>Suggestions from your agents</h1>
          <p>
            Each agent proposes activities with a reason and a value for your goals. The planner chooses among the
            waiting ones. Want to see the planner react? Act as an agent and send something new.
          </p>
        </div>
        <button className="btn primary" onClick={() => setDrawer(true)}>
          <Wand2 size={16} /> Simulate an agent
        </button>
      </div>

      <div className="toolbar">
        <div className="segmented" role="tablist">
          {(Object.keys(STATUS_LABEL) as ProposalStatus[]).map((s) => (
            <button key={s} className={s === status ? "on" : ""} onClick={() => setStatus(s)} role="tab">
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>
        <span className="grow" />
        <div className="chips">
          {(["all", "event", "tutor", "career", "user"] as const).map((a) => (
            <button key={a} className={`chip${agent === a ? " on" : ""}`} onClick={() => setAgent(a)}>
              {a === "all" ? "All agents" : AGENTS[a].short}
              <span className="count">{counts[a] ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      {items === null ? (
        <div className="empty">
          <Loader2 className="spin" />
        </div>
      ) : shown.length === 0 ? (
        <div className="card empty">
          <div className="empty-icon">
            <Inbox size={26} />
          </div>
          <h2>{status === "active" ? "No suggestions waiting" : `Nothing ${STATUS_LABEL[status].toLowerCase()}`}</h2>
          <p>
            {status === "active"
              ? "Load the demo student on the Start page, or act as an agent and send a suggestion."
              : status === "rejected"
                ? "When you reject an item in your plan, it shows up here and is never planned again."
                : "When an agent takes a suggestion back (an event is cancelled), it shows up here."}
          </p>
          {status === "active" && (
            <button className="btn primary" onClick={() => setDrawer(true)}>
              <Wand2 size={16} /> Simulate an agent
            </button>
          )}
        </div>
      ) : (
        <div className="cards">
          {shown.map((p) => (
            <article className="s-card" key={p.proposal_id}>
              <div className="s-card-top">
                <AgentBadge agent={p.source_agent} />
                <span className="pill">{p.fixed_time ? "Fixed time" : "Flexible"}</span>
                {p.priority === "high" && (
                  <span className="pill partial">
                    <Flag size={10} /> High
                  </span>
                )}
                {p.hard && (
                  <span className="pill rejected">
                    <Lock size={10} /> Must happen
                  </span>
                )}
              </div>
              <h3>{p.title}</h3>
              <p className="reason">{p.reason}</p>
              <When p={p} />
              {!!p.depends_on?.length && (
                <span className="when">
                  <Link2 size={14} /> After {p.depends_on.join(", ")}
                </span>
              )}
              <div className="s-card-foot">
                <GoalDots value={p.value} />
                <span className="grow" />
                {status === "active" && (
                  <button className="btn ghost small" onClick={() => withdraw(p)} title="As the agent: take this back">
                    <Ban size={14} /> Withdraw
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <Drawer open={drawer} title="Simulate an agent" onClose={() => setDrawer(false)}>
        <p className="muted">
          Pretend to be one of the agents and send a suggestion to the planner, exactly like the real agents will. Then
          re-plan on Your plan to see what changes.
        </p>
        <div className="segmented">
          <button className={tab === "form" ? "on" : ""} onClick={() => setTab("form")}>
            <Wand2 size={13} /> Form
          </button>
          <button className={tab === "json" ? "on" : ""} onClick={() => setTab("json")}>
            <FileJson size={13} /> Paste JSON
          </button>
        </div>

        {tab === "form" ? (
          <>
            <div className="field">
              <span className="field-label">Who is sending it?</span>
              <div className="agent-pick">
                {(Object.keys(AGENTS) as SourceAgent[]).map((a) => {
                  const Icon = AGENTS[a].icon;
                  return (
                    <button key={a} className={form.agent === a ? "on" : ""} onClick={() => f("agent", a)}>
                      <Icon size={18} />
                      {AGENTS[a].short}
                    </button>
                  );
                })}
              </div>
            </div>
            <label className="field">
              <span className="field-label">Title</span>
              <input value={form.title} onChange={(e) => f("title", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">Why (the student sees this)</span>
              <input value={form.reason} onChange={(e) => f("reason", e.target.value)} />
            </label>
            <div className="field">
              <span className="field-label">When</span>
              <div className="segmented">
                <button className={form.kind === "fixed" ? "on" : ""} onClick={() => f("kind", "fixed")}>
                  <CalendarClock size={13} /> At a fixed time
                </button>
                <button className={form.kind === "flexible" ? "on" : ""} onClick={() => f("kind", "flexible")}>
                  <Clock size={13} /> Any time before a deadline
                </button>
              </div>
            </div>
            {form.kind === "fixed" ? (
              <div className="fields">
                <label className="field">
                  <span className="field-label">Starts</span>
                  <input type="datetime-local" value={form.start} onChange={(e) => f("start", e.target.value)} />
                </label>
                <label className="field">
                  <span className="field-label">Ends</span>
                  <input type="datetime-local" value={form.end} onChange={(e) => f("end", e.target.value)} />
                </label>
              </div>
            ) : (
              <div className="fields">
                <label className="field">
                  <span className="field-label">Needs {minutesLabel(form.duration)}</span>
                  <input type="range" min={30} max={480} step={30} value={form.duration} onChange={(e) => f("duration", Number(e.target.value))} />
                </label>
                <label className="field">
                  <span className="field-label">From</span>
                  <input type="date" value={form.earliest} onChange={(e) => f("earliest", e.target.value)} />
                </label>
                <label className="field">
                  <span className="field-label">Due</span>
                  <input type="date" value={form.deadline} onChange={(e) => f("deadline", e.target.value)} />
                </label>
              </div>
            )}
            <div className="field">
              <span className="field-label">How much does it help each goal?</span>
              {GOALS.map((g) => (
                <div className="goal-meter" key={g}>
                  <span className="goal-name">{GOAL_META[g].label}</span>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.1}
                    value={form.value[g]}
                    onChange={(e) => f("value", { ...form.value, [g]: Number(e.target.value) })}
                  />
                  <span className="goal-pct">{form.value[g].toFixed(1)}</span>
                </div>
              ))}
            </div>
            <div className="row">
              <div className="segmented">
                {(["low", "medium", "high"] as Priority[]).map((pr) => (
                  <button key={pr} className={form.priority === pr ? "on" : ""} onClick={() => f("priority", pr)}>
                    {pr[0].toUpperCase() + pr.slice(1)} priority
                  </button>
                ))}
              </div>
              <label className="row small">
                <input type="checkbox" checked={form.hard} onChange={(e) => f("hard", e.target.checked)} /> Must happen
              </label>
            </div>
            <button className="btn primary big" onClick={sendForm} disabled={sending || !form.title || !form.reason}>
              {sending ? <Loader2 size={16} className="spin" /> : <Wand2 size={16} />} Send to the planner
            </button>
          </>
        ) : (
          <>
            <p className="small muted">
              One suggestion or a list, in the shared format (see <code>shared/contracts/activity_proposal.py</code>).
              Missing <code>user_id</code> becomes {userId}.
            </p>
            <textarea rows={16} value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder='[{"proposal_id": "evt-...", ...}]' />
            <button className="btn primary big" onClick={sendJson} disabled={sending || !bulk.trim()}>
              {sending ? <Loader2 size={16} className="spin" /> : <FileJson size={16} />} Send to the planner
            </button>
          </>
        )}
      </Drawer>
    </>
  );
}

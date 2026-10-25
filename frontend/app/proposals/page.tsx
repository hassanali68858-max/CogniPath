"use client";

import { useCallback, useEffect, useState } from "react";

import { Message, type Msg, errorText } from "@/components/Message";
import { useUser } from "@/components/UserProvider";
import { api } from "@/lib/api";
import { dayLabel, minutesLabel, rangeLabel, slug } from "@/lib/format";
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
const TYPES: ActivityType[] = ["event", "learning", "course_work", "application", "quiz", "social", "other"];

type Form = {
  agent: SourceAgent;
  type: ActivityType;
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

const EMPTY: Form = {
  agent: "event",
  type: "event",
  title: "",
  reason: "",
  kind: "fixed",
  start: "2026-11-12T17:00",
  end: "2026-11-12T19:00",
  duration: 120,
  earliest: "2026-11-02",
  deadline: "2026-11-15",
  value: { study: 0, career: 0.5, social: 0.5 },
  priority: "medium",
  hard: false,
};

function when(p: ActivityProposal): string {
  if (p.fixed_time) return rangeLabel(p.fixed_time.start, p.fixed_time.end);
  if (p.window) return `${minutesLabel(p.duration_min ?? 0)} between ${dayLabel(p.window.earliest)} and ${dayLabel(p.window.deadline)}`;
  return "";
}

export default function ProposalsPage() {
  const { userId } = useUser();
  const [status, setStatus] = useState<ProposalStatus>("active");
  const [items, setItems] = useState<ActivityProposal[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [bulk, setBulk] = useState("");
  const [msg, setMsg] = useState<Msg>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api.listProposals(userId, status));
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    }
  }, [userId, status]);

  useEffect(() => {
    load();
  }, [load]);

  async function withdraw(p: ActivityProposal) {
    try {
      await api.withdraw(userId, p.proposal_id);
      setMsg({ kind: "ok", text: `Withdrawn: ${p.title}. Re-plan to update the current plan.` });
      await load();
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    }
  }

  async function add() {
    const p: ActivityProposal = {
      proposal_id: `${PREFIX[form.agent]}-${slug(form.title)}`,
      source_agent: form.agent,
      user_id: userId,
      type: form.type,
      title: form.title,
      reason: form.reason,
      value: form.value,
      priority: form.priority,
      hard: form.hard,
      ...(form.kind === "fixed"
        ? { fixed_time: { start: form.start, end: form.end } }
        : { duration_min: form.duration, window: { earliest: form.earliest, deadline: form.deadline } }),
    };
    try {
      await api.addProposals([p]);
      setMsg({ kind: "ok", text: `Stored ${p.proposal_id}. Make a plan or re-plan to use it.` });
      setForm({ ...form, title: "", reason: "" });
      await load();
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    }
  }

  async function addBulk() {
    try {
      const parsed = JSON.parse(bulk);
      const list: ActivityProposal[] = Array.isArray(parsed) ? parsed : [parsed];
      const r = await api.addProposals(list.map((p) => ({ ...p, user_id: p.user_id ?? userId })));
      setMsg({ kind: "ok", text: `Stored ${r.stored} proposals.` });
      setBulk("");
      await load();
    } catch (e) {
      setMsg({ kind: "error", text: e instanceof SyntaxError ? `Not valid JSON: ${e.message}` : errorText(e) });
    }
  }

  const f = <K extends keyof Form>(key: K, value: Form[K]) => setForm((x) => ({ ...x, [key]: value }));

  return (
    <>
      <h1>Proposals</h1>
      <p className="lead">
        What the agents suggest for <b>{userId}</b>. Here you can also act as an agent: add a proposal or withdraw one,
        then re-plan on the Plan page.
      </p>

      <section className="panel">
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="tabs" style={{ margin: 0 }}>
            {(["active", "rejected", "withdrawn"] as ProposalStatus[]).map((s) => (
              <button key={s} className={s === status ? "primary" : ""} onClick={() => setStatus(s)}>
                {s}
              </button>
            ))}
          </div>
          <span className="spacer" />
          <span className="muted small">{items.length} proposals</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Title</th>
                <th>When</th>
                <th>Value</th>
                <th>Priority</th>
                <th>Reason</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.proposal_id}>
                  <td>
                    <span className={`badge ${p.source_agent}`}>{p.source_agent}</span>
                  </td>
                  <td>
                    <b>{p.title}</b>
                    <div className="muted small">
                      {p.proposal_id}
                      {p.hard ? " · must happen" : ""}
                      {p.depends_on?.length ? ` · after ${p.depends_on.join(", ")}` : ""}
                    </div>
                  </td>
                  <td className="small">{when(p)}</td>
                  <td className="small">
                    {GOALS.filter((g) => (p.value[g] ?? 0) > 0)
                      .map((g) => `${g} ${p.value[g]}`)
                      .join(" · ")}
                  </td>
                  <td className="small">{p.priority ?? "medium"}</td>
                  <td className="small muted">{p.reason}</td>
                  <td>
                    {status === "active" && (
                      <button className="small danger" onClick={() => withdraw(p)}>
                        Withdraw
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!items.length && (
                <tr>
                  <td colSpan={7} className="muted">
                    No {status} proposals. Load the demo data on the Home page, or add one below.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <Message msg={msg} />

      <div className="grid2">
        <section className="panel">
          <h2>Add a proposal (act as an agent)</h2>
          <div className="form-grid">
            <label>
              Agent
              <select value={form.agent} onChange={(e) => f("agent", e.target.value as SourceAgent)}>
                {Object.keys(PREFIX).map((a) => (
                  <option key={a}>{a}</option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select value={form.type} onChange={(e) => f("type", e.target.value as ActivityType)}>
                {TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <label>
              Kind
              <select value={form.kind} onChange={(e) => f("kind", e.target.value as Form["kind"])}>
                <option value="fixed">fixed time</option>
                <option value="flexible">flexible (duration + window)</option>
              </select>
            </label>
            <label>
              Priority
              <select value={form.priority} onChange={(e) => f("priority", e.target.value as Priority)}>
                <option>low</option>
                <option>medium</option>
                <option>high</option>
              </select>
            </label>
          </div>
          <div className="form-grid">
            <label style={{ gridColumn: "span 2" }}>
              Title
              <input value={form.title} onChange={(e) => f("title", e.target.value)} placeholder="Hack night" />
            </label>
            <label style={{ gridColumn: "span 2" }}>
              Reason (shown to the student)
              <input value={form.reason} onChange={(e) => f("reason", e.target.value)} placeholder="Matches your interests" />
            </label>
          </div>
          {form.kind === "fixed" ? (
            <div className="form-grid">
              <label>
                Start
                <input type="datetime-local" value={form.start} onChange={(e) => f("start", e.target.value)} />
              </label>
              <label>
                End
                <input type="datetime-local" value={form.end} onChange={(e) => f("end", e.target.value)} />
              </label>
            </div>
          ) : (
            <div className="form-grid">
              <label>
                Duration (minutes)
                <input type="number" min={30} step={30} value={form.duration} onChange={(e) => f("duration", Number(e.target.value))} />
              </label>
              <label>
                Earliest day
                <input type="date" value={form.earliest} onChange={(e) => f("earliest", e.target.value)} />
              </label>
              <label>
                Deadline day
                <input type="date" value={form.deadline} onChange={(e) => f("deadline", e.target.value)} />
              </label>
            </div>
          )}
          <div className="form-grid">
            {GOALS.map((g) => (
              <label key={g}>
                {g} value (0–1)
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.1}
                  value={form.value[g]}
                  onChange={(e) => f("value", { ...form.value, [g]: Number(e.target.value) })}
                />
              </label>
            ))}
            <label className="inline">
              <input type="checkbox" checked={form.hard} onChange={(e) => f("hard", e.target.checked)} /> must happen
            </label>
          </div>
          <button className="primary" onClick={add} disabled={!form.title || !form.reason}>
            Send proposal
          </button>
        </section>

        <section className="panel">
          <h2>Paste JSON (one proposal or a list)</h2>
          <p className="muted small">
            Same format the agents use, e.g. the contents of <code>tests/planner_agent/fixtures/mock_proposals.json</code>.
            Missing <code>user_id</code> is filled with {userId}.
          </p>
          <textarea rows={12} value={bulk} onChange={(e) => setBulk(e.target.value)} placeholder='[{"proposal_id": "...", ...}]' />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="primary" onClick={addBulk} disabled={!bulk.trim()}>
              Send
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

"use client";

import {
  CalendarCheck,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  MousePointerClick,
  RefreshCw,
  Settings2,
  Sparkles,
  Undo2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AgentBadge } from "@/components/AgentBadge";
import { GoalMeters } from "@/components/GoalMeters";
import { useStatus } from "@/components/StatusProvider";
import { errorText, useToast } from "@/components/Toast";
import { useUser } from "@/components/UserProvider";
import { WeekCalendar } from "@/components/WeekCalendar";
import { api } from "@/lib/api";
import { addDays, datePart, dayLabel, minutesLabel, rangeLabel, timePart } from "@/lib/format";
import { MODE_META } from "@/lib/meta";
import { type Decision, MODES, type Plan, type PlanItem } from "@/lib/types";

const hourOf = (t: string, up = false) => {
  const h = Number(t.slice(0, 2)) + Number(t.slice(3, 5)) / 60;
  return up ? Math.ceil(h) : Math.floor(h);
};
const daysBetween = (a: string, b: string) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);

function PlanOptions({
  start,
  setStart,
  days,
  setDays,
  modes,
  setModes,
}: {
  start: string;
  setStart: (v: string) => void;
  days: number;
  setDays: (v: number) => void;
  modes: string[];
  setModes: (v: string[]) => void;
}) {
  return (
    <div className="fields" style={{ alignItems: "end" }}>
      <label className="field">
        <span className="field-label">First day</span>
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label className="field">
        <span className="field-label">Plan {days} days</span>
        <input type="range" min={7} max={28} step={7} value={days} onChange={(e) => setDays(Number(e.target.value))} />
      </label>
      <div className="field" style={{ gridColumn: "span 2" }}>
        <span className="field-label">Versions to compare</span>
        <div className="chips">
          {MODES.map((m) => (
            <button
              key={m}
              className={`chip${modes.includes(m) ? " on" : ""}`}
              onClick={() => setModes(modes.includes(m) ? modes.filter((x) => x !== m) : [...modes, m])}
              title={MODE_META[m].blurb}
            >
              {modes.includes(m) && <Check size={13} />} {MODE_META[m].label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function PlanPage() {
  const { userId } = useUser();
  const { status, refresh } = useStatus();
  const toast = useToast();

  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [planId, setPlanId] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [week, setWeek] = useState(0);
  const [start, setStart] = useState("2026-11-02");
  const [days, setDays] = useState(14);
  const [modes, setModes] = useState<string[]>([...MODES]);
  const [notBefore, setNotBefore] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const loadCurrent = useCallback(async () => {
    try {
      const current = await api.currentPlan(userId);
      setPlans([current]);
      setPlanId(current.plan_id);
      setStart(datePart(current.horizon_start));
    } catch {
      setPlans([]);
      api.demoInfo().then((d) => setStart(d.horizon_start), () => {});
    }
  }, [userId]);

  useEffect(() => {
    setPlans(null);
    setSelected(null);
    loadCurrent();
  }, [loadCurrent]);

  const plan = useMemo(() => plans?.find((p) => p.plan_id === planId) ?? plans?.[0] ?? null, [plans, planId]);
  const readOnly = !plan || plan.status === "discarded" || plan.status === "superseded";
  const profile = status.profile;

  const items = useMemo(
    () => [...(plan?.items ?? [])].sort((a, b) => a.sessions[0].start.localeCompare(b.sessions[0].start)),
    [plan],
  );
  const decided = items.filter((i) => i.decision !== "pending").length;
  const pending = items.filter((i) => i.decision === "pending");
  const chosen = items.find((i) => i.item_id === selected) ?? null;
  const horizon = plan ? datePart(plan.horizon_start) : start;
  const planDays = plan ? daysBetween(datePart(plan.horizon_start), datePart(plan.horizon_end)) : days;
  const weeks = Math.max(1, Math.ceil(planDays / 7));
  const tags = useMemo(() => {
    const t: Record<string, "NEW" | "MOVED"> = {};
    plan?.changes?.added.forEach((id) => (t[id] = "NEW"));
    plan?.changes?.moved.forEach((id) => (t[id] = "MOVED"));
    return t;
  }, [plan]);

  async function act(label: string, fn: () => Promise<void>) {
    setBusy(label);
    try {
      await fn();
      await refresh();
    } catch (e) {
      toast("error", "Something went wrong", errorText(e));
    } finally {
      setBusy(null);
    }
  }

  const makePlan = () =>
    act("run", async () => {
      if (!profile) throw new Error("Set up About you first, or load the demo student on the Start page.");
      if (!modes.length) throw new Error("Pick at least one version to compare.");
      const result = await api.run(userId, start, days, modes);
      setPlans(result);
      setPlanId(result[0].plan_id);
      setSelected(null);
      setWeek(0);
      setShowNew(false);
      toast(
        "success",
        result.length > 1 ? `${result.length} versions ready` : "Your plan is ready",
        result.length > 1 ? "Compare them, then start accepting items in the one you like." : "Review the items on the right.",
      );
    });

  const decide = (list: PlanItem[], decision: Decision) =>
    act("decide", async () => {
      if (!plan) return;
      const updated = await api.decide(
        plan.plan_id,
        list.map((i) => ({ item_id: i.item_id, decision })),
      );
      setPlans((ps) =>
        (ps ?? []).map((p) =>
          p.plan_id === updated.plan_id ? updated : p.status === "draft" ? { ...p, status: "discarded" } : p,
        ),
      );
      if (decision === "rejected" && list.length === 1)
        toast("info", `Rejected “${list[0].title}”`, "It will not be planned again. Undo it any time.");
      if (decision === "accepted" && list.length > 1) toast("success", `Accepted ${list.length} items`);
    });

  const replan = () =>
    act("replan", async () => {
      if (!plan) return;
      const result = await api.replan(plan.plan_id, notBefore || undefined);
      setPlans(result);
      setPlanId(result[0].plan_id);
      setSelected(null);
      toast("success", "Re-planned", result[0].changes?.summary ?? "");
    });

  function select(itemId: string) {
    setSelected(itemId);
    const it = items.find((i) => i.item_id === itemId);
    if (it) setWeek(Math.min(weeks - 1, Math.floor(daysBetween(horizon, datePart(it.sessions[0].start)) / 7)));
    requestAnimationFrame(() => document.getElementById(`item-${itemId}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }

  const fromHour = profile ? Math.min(8, hourOf(profile.day_start)) : 8;
  const toHour = profile ? Math.max(22, hourOf(profile.day_end, true)) : 22;
  const runs = plans && plans.length > 1;

  if (plans === null)
    return (
      <div className="empty">
        <Loader2 className="spin" />
      </div>
    );

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Step 3</span>
          <h1>Your plan</h1>
          <p>
            {plan
              ? `${dayLabel(horizon)} – ${dayLabel(addDays(horizon, planDays - 1))}. Click any block or item to see why it was planned. Accept what you will do, reject what you won't.`
              : "The planner reads your profile and the waiting suggestions, then fits the best mix into your free time."}
          </p>
        </div>
        {plan && (
          <div className="row">
            <button
              className={`btn${status.newSincePlan.length ? " primary" : ""}`}
              onClick={replan}
              disabled={!!busy || readOnly}
              title="Keep accepted items, drop rejected ones, plan the rest again"
            >
              {busy === "replan" ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
              Re-plan{status.newSincePlan.length ? ` (${status.newSincePlan.length} new)` : ""}
            </button>
            <a className="btn" href={api.icsUrl(plan.plan_id)} download="cognipath-plan.ics" title="Import into Outlook, Google or Apple Calendar">
              <Download size={16} /> Calendar file
            </a>
            <button className="btn ghost" onClick={() => setShowNew(!showNew)}>
              <Settings2 size={16} /> New plan
            </button>
          </div>
        )}
      </div>

      {!plan ? (
        <section className="card empty">
          <div className="empty-icon">
            <CalendarCheck size={26} />
          </div>
          <h2>Ready to plan your week</h2>
          <p>
            {status.proposals.length
              ? `${status.proposals.length} suggestions are waiting. You'll get up to three versions to compare: balanced, study first and career first.`
              : "There are no suggestions yet. Load the demo student on the Start page first."}
          </p>
          <div style={{ maxWidth: 640, margin: "0 auto 18px", textAlign: "left" }}>
            <PlanOptions start={start} setStart={setStart} days={days} setDays={setDays} modes={modes} setModes={setModes} />
          </div>
          <button className="btn primary big" onClick={makePlan} disabled={!!busy || !status.proposals.length}>
            {busy === "run" ? <Loader2 size={18} className="spin" /> : <Sparkles size={18} />} Make my plan
          </button>
        </section>
      ) : (
        <>
          {showNew && (
            <section className="card" style={{ marginBottom: 16 }}>
              <div className="card-head">
                <div className="grow">
                  <h2>Start a new plan</h2>
                  <p>Plans again from scratch with the current profile and suggestions. Use Re-plan instead to keep your decisions.</p>
                </div>
              </div>
              <PlanOptions start={start} setStart={setStart} days={days} setDays={setDays} modes={modes} setModes={setModes} />
              <div className="row" style={{ marginTop: 14 }}>
                <button className="btn primary" onClick={makePlan} disabled={!!busy}>
                  {busy === "run" ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />} Make new plan
                </button>
                <label className="field" style={{ marginLeft: "auto" }}>
                  <span className="field-label">Re-plan option: nothing new before</span>
                  <input type="datetime-local" value={notBefore} onChange={(e) => setNotBefore(e.target.value)} />
                </label>
              </div>
            </section>
          )}

          {runs && (
            <>
              <p className="muted" style={{ marginBottom: 10 }}>
                <b style={{ color: "var(--text)" }}>Pick a version.</b> They differ only when time is short. Your first
                accept or reject locks in the version you are looking at.
              </p>
              <div className="alt-grid">
                {plans!.map((p) => (
                  <button
                    key={p.plan_id}
                    className={`alt-card${p.plan_id === plan.plan_id ? " on" : ""}${p.status === "discarded" ? " off" : ""}`}
                    onClick={() => setPlanId(p.plan_id)}
                  >
                    <div className="row">
                      <b>{MODE_META[p.mode]?.label ?? p.mode}</b>
                      <span className="grow" />
                      <span className={`pill ${p.status}`}>{p.status}</span>
                    </div>
                    <span className="small muted">{MODE_META[p.mode]?.blurb}</span>
                    <GoalMeters loss={p.scores.loss} compact />
                    <span className="small faint">
                      {p.items.length} planned · {p.dropped.length} didn&apos;t fit
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}

          {plan.changes && (
            <div className="changes">
              <RefreshCw size={18} style={{ marginTop: 2, color: "var(--brand)" }} />
              <div>
                <b>What changed since your last plan: </b>
                {plan.changes.summary}. Look for the <span className="pill new">NEW</span> and{" "}
                <span className="pill moved">MOVED</span> tags in the calendar.
                {plan.changes.notes.length > 0 && (
                  <ul>
                    {plan.changes.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}

          <div className="stat-row">
            <div className="stat">
              <b>{plan.items.length}</b>
              <span>activities planned</span>
            </div>
            <div className="stat">
              <b>{minutesLabel(plan.scores.scheduled_minutes)}</b>
              <span>of planned time</span>
            </div>
            <div className="stat">
              <b>{plan.dropped.length}</b>
              <span>didn&apos;t fit</span>
            </div>
            <div className="stat">
              <b>
                {decided}/{items.length}
              </b>
              <span>decided by you</span>
            </div>
          </div>

          <div className="plan-layout">
            <div>
              <section className="card">
                <div className="card-head">
                  <div className="grow">
                    <h2>
                      Week {week + 1}{" "}
                      <span className="muted" style={{ fontWeight: 500 }}>
                        · {dayLabel(addDays(horizon, week * 7))} – {dayLabel(addDays(horizon, Math.min(planDays, week * 7 + 7) - 1))}
                      </span>
                    </h2>
                  </div>
                  <div className="week-tabs">
                    <button className="icon-btn" onClick={() => setWeek(Math.max(0, week - 1))} disabled={week === 0} aria-label="Previous week">
                      <ChevronLeft size={18} />
                    </button>
                    <div className="segmented">
                      {Array.from({ length: weeks }, (_, w) => (
                        <button key={w} className={w === week ? "on" : ""} onClick={() => setWeek(w)}>
                          Week {w + 1}
                        </button>
                      ))}
                    </div>
                    <button className="icon-btn" onClick={() => setWeek(Math.min(weeks - 1, week + 1))} disabled={week === weeks - 1} aria-label="Next week">
                      <ChevronRight size={18} />
                    </button>
                  </div>
                </div>
                <WeekCalendar
                  horizonStart={horizon}
                  days={planDays}
                  week={week}
                  items={plan.items}
                  busy={profile?.busy_blocks ?? []}
                  fromHour={fromHour}
                  toHour={toHour}
                  selected={selected}
                  tags={tags}
                  onSelect={select}
                />
                <div className="legend">
                  <span>
                    <i style={{ background: "var(--event)" }} />
                    Event
                  </span>
                  <span>
                    <i style={{ background: "var(--tutor)" }} />
                    Tutor
                  </span>
                  <span>
                    <i style={{ background: "var(--career)" }} />
                    Career
                  </span>
                  <span>
                    <i style={{ background: "var(--border-strong)" }} />
                    Your commitments
                  </span>
                  <span>Light = suggested · solid = accepted · struck through = rejected</span>
                </div>
              </section>

              <div className="grid two" style={{ marginTop: 16 }}>
                <section className="card">
                  <div className="card-head">
                    <div className="grow">
                      <h2>Goal balance</h2>
                      <p>How much of each goal&apos;s suggested value made it into the plan.</p>
                    </div>
                  </div>
                  <GoalMeters loss={plan.scores.loss} />
                  <p className="small faint" style={{ marginTop: 12 }}>
                    {MODE_META[plan.mode]?.label ?? plan.mode} version · solved {plan.solver_status.toLowerCase()} in{" "}
                    {plan.solve_seconds}s
                  </p>
                </section>

                <section className="card">
                  <div className="card-head">
                    <div className="grow">
                      <h2>Didn&apos;t fit ({plan.dropped.length})</h2>
                      <p>Left out, and why.</p>
                    </div>
                  </div>
                  {plan.dropped.length ? (
                    <div className="dropped-list" style={{ gridTemplateColumns: "1fr" }}>
                      {plan.dropped.map((d) => (
                        <div className="dropped" key={d.proposal_id}>
                          <X size={16} className="faint" style={{ flex: "none", marginTop: 2 }} />
                          <div>
                            <div className="row" style={{ gap: 6 }}>
                              <b>{d.title}</b>
                              {d.source_agents.map((a) => (
                                <AgentBadge key={a} agent={a} compact />
                              ))}
                            </div>
                            <p>{d.explanation}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="muted">Everything fits. Nothing was left out.</p>
                  )}
                </section>
              </div>
            </div>

            <aside className="card review">
              <div className="review-head">
                <div className="row">
                  <h2 className="grow">Review</h2>
                  <span className="small muted">
                    {decided} of {items.length} decided
                  </span>
                </div>
                <div className="progress">
                  <div style={{ width: `${items.length ? (decided / items.length) * 100 : 0}%` }} />
                </div>
                {readOnly ? (
                  <p className="small muted">This version is {plan.status}. Open the current plan to make decisions.</p>
                ) : (
                  <button className="btn small" onClick={() => decide(pending, "accepted")} disabled={!!busy || !pending.length}>
                    <Check size={14} /> Accept all {pending.length} remaining
                  </button>
                )}
              </div>

              {chosen ? (
                <div className="detail">
                  <div className="row" style={{ gap: 6 }}>
                    {chosen.source_agents.map((a) => (
                      <AgentBadge key={a} agent={a} />
                    ))}
                    <span className={`pill ${chosen.decision}`}>{chosen.decision}</span>
                    {tags[chosen.proposal_id] && <span className={`pill ${tags[chosen.proposal_id].toLowerCase()}`}>{tags[chosen.proposal_id]}</span>}
                  </div>
                  <h3 style={{ fontSize: 15 }}>{chosen.title}</h3>
                  <div className="small muted">{chosen.sessions.map((s) => rangeLabel(s.start, s.end)).join(" · ")}</div>
                  <p className="why">{chosen.explanation}</p>
                </div>
              ) : (
                <div className="detail" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <MousePointerClick size={16} className="faint" />
                  <span className="small muted">Select an item or a calendar block to see why it was planned.</span>
                </div>
              )}

              <div className="review-list">
                {items.map((i) => (
                  <div
                    key={i.item_id}
                    id={`item-${i.item_id}`}
                    className={`r-item${selected === i.item_id ? " selected" : ""}${i.decision === "rejected" ? " rejected" : ""}`}
                    onClick={() => select(i.item_id)}
                  >
                    <span className={`stripe ${i.source_agents[0] ?? "user"}`} />
                    <div style={{ minWidth: 0 }}>
                      <h4>
                        {i.title}
                        {tags[i.proposal_id] && <span className={`pill ${tags[i.proposal_id].toLowerCase()}`}>{tags[i.proposal_id]}</span>}
                      </h4>
                      <div className="when">
                        {dayLabel(datePart(i.sessions[0].start))} · {timePart(i.sessions[0].start)}
                        {i.sessions.length > 1 ? ` · ${i.sessions.length} sessions` : ""}
                      </div>
                    </div>
                    <div className="decide" onClick={(e) => e.stopPropagation()}>
                      {i.decision === "pending" ? (
                        <>
                          <button className="icon-btn accept" title="Accept" aria-label={`Accept ${i.title}`} disabled={!!busy || readOnly} onClick={() => decide([i], "accepted")}>
                            <Check size={16} />
                          </button>
                          <button className="icon-btn reject" title="Reject" aria-label={`Reject ${i.title}`} disabled={!!busy || readOnly} onClick={() => decide([i], "rejected")}>
                            <X size={16} />
                          </button>
                        </>
                      ) : (
                        <>
                          <button className={`icon-btn ${i.decision === "accepted" ? "accept" : "reject"} on`} title={i.decision} disabled>
                            {i.decision === "accepted" ? <Check size={16} /> : <X size={16} />}
                          </button>
                          <button className="icon-btn" title="Undo" aria-label={`Undo decision on ${i.title}`} disabled={!!busy || readOnly} onClick={() => decide([i], "pending")}>
                            <Undo2 size={16} />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </aside>
          </div>
        </>
      )}
    </>
  );
}

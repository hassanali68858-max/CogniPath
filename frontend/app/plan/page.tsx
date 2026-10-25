"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { LossBars } from "@/components/LossBars";
import { Message, type Msg, errorText } from "@/components/Message";
import { useUser } from "@/components/UserProvider";
import { WeekCalendar } from "@/components/WeekCalendar";
import { ApiError, api } from "@/lib/api";
import { datePart, minutesLabel, rangeLabel } from "@/lib/format";
import { type Decision, MODES, type Plan, type PlanItem, type PlannerProfile } from "@/lib/types";

const MODE_LABEL: Record<string, string> = {
  balanced: "Balanced",
  study_first: "Study first",
  career_first: "Career first",
};

const hour = (t: string, up = false) => {
  const h = Number(t.slice(0, 2)) + Number(t.slice(3, 5)) / 60;
  return up ? Math.ceil(h) : Math.floor(h);
};

export default function PlanPage() {
  const { userId } = useUser();
  const [profile, setProfile] = useState<PlannerProfile | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [horizonStart, setHorizonStart] = useState("2026-11-02");
  const [days, setDays] = useState(14);
  const [modes, setModes] = useState<string[]>([...MODES]);
  const [notBefore, setNotBefore] = useState("");
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);

  const plan = useMemo(() => plans.find((p) => p.plan_id === selectedPlan) ?? plans[0] ?? null, [plans, selectedPlan]);
  const locked = !plan || plan.status === "discarded" || plan.status === "superseded";

  const loadCurrent = useCallback(async () => {
    setMsg(null);
    setProfile(await api.getProfile(userId).catch(() => null));
    try {
      const current = await api.currentPlan(userId);
      setPlans([current]);
      setSelectedPlan(current.plan_id);
      setHorizonStart(datePart(current.horizon_start));
    } catch (e) {
      setPlans([]);
      if (!(e instanceof ApiError && e.status === 404)) setMsg({ kind: "error", text: errorText(e) });
      api.demoInfo().then((d) => setHorizonStart(d.horizon_start), () => {});
    }
  }, [userId]);

  useEffect(() => {
    loadCurrent();
  }, [loadCurrent]);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    } finally {
      setBusy(false);
    }
  }

  const runPlanner = () =>
    act(async () => {
      if (!profile) throw new Error("Save a profile first (Profile page), or load the demo data on the Home page.");
      const result = await api.run(userId, horizonStart, days, modes);
      setPlans(result);
      setSelectedPlan(result[0]?.plan_id ?? null);
      setSelectedItem(null);
      setMsg({
        kind: "ok",
        text: `Made ${result.length} alternative(s). Pick one; your first decision discards the others.`,
      });
    });

  const decide = (items: PlanItem[], decision: Decision) =>
    act(async () => {
      if (!plan) return;
      const updated = await api.decide(
        plan.plan_id,
        items.map((i) => ({ item_id: i.item_id, decision })),
      );
      setPlans((ps) =>
        ps.map((p) =>
          p.plan_id === updated.plan_id ? updated : p.status === "draft" ? { ...p, status: "discarded" } : p,
        ),
      );
    });

  const replan = () =>
    act(async () => {
      if (!plan) return;
      const result = await api.replan(plan.plan_id, notBefore || undefined);
      setPlans(result);
      setSelectedPlan(result[0]?.plan_id ?? null);
      setSelectedItem(null);
      setMsg({ kind: "ok", text: `Re-planned: ${result[0]?.changes?.summary ?? "done"}.` });
    });

  const fromHour = profile ? Math.min(8, hour(profile.day_start)) : 8;
  const toHour = profile ? Math.max(22, hour(profile.day_end, true)) : 22;
  const planDays = plan
    ? Math.round((Date.parse(datePart(plan.horizon_end)) - Date.parse(datePart(plan.horizon_start))) / 86400000)
    : days;
  const items = useMemo(
    () => [...(plan?.items ?? [])].sort((a, b) => a.sessions[0].start.localeCompare(b.sessions[0].start)),
    [plan],
  );
  const pending = items.filter((i) => i.decision === "pending");
  const chosen = items.find((i) => i.item_id === selectedItem);

  return (
    <>
      <h1>Plan</h1>
      <p className="lead">
        Make a plan from <b>{userId}</b>&apos;s profile and active proposals, accept or reject items, and re-plan after
        something changes.
      </p>

      <section className="panel">
        <h2>Make a new plan</h2>
        <div className="row">
          <label>
            First day
            <input type="date" value={horizonStart} onChange={(e) => setHorizonStart(e.target.value)} />
          </label>
          <label>
            Days
            <input type="number" min={1} max={28} value={days} onChange={(e) => setDays(Number(e.target.value))} />
          </label>
          {MODES.map((m) => (
            <label key={m} className="inline" style={{ alignSelf: "flex-end" }}>
              <input
                type="checkbox"
                checked={modes.includes(m)}
                onChange={() => setModes(modes.includes(m) ? modes.filter((x) => x !== m) : [...modes, m])}
              />
              {MODE_LABEL[m]}
            </label>
          ))}
          <button className="primary" onClick={runPlanner} disabled={busy || !modes.length} style={{ alignSelf: "flex-end" }}>
            {busy ? "Working…" : "Make plan"}
          </button>
          <button onClick={() => act(loadCurrent)} disabled={busy} style={{ alignSelf: "flex-end" }}>
            Load current plan
          </button>
        </div>
      </section>

      <Message msg={msg} />

      {!plan ? (
        <section className="panel muted">No plan yet. Make one above.</section>
      ) : (
        <>
          {plans.length > 1 && (
            <div className="tabs">
              {plans.map((p) => (
                <button
                  key={p.plan_id}
                  className={`tab${p.plan_id === plan.plan_id ? " selected" : ""}`}
                  onClick={() => setSelectedPlan(p.plan_id)}
                >
                  <div className="row">
                    <b>{MODE_LABEL[p.mode] ?? p.mode}</b>
                    <span className={`badge ${p.status}`}>{p.status}</span>
                  </div>
                  <div className="muted small">
                    {p.items.length} kept · {p.dropped.length} dropped
                  </div>
                  <LossBars loss={p.scores.loss} />
                </button>
              ))}
            </div>
          )}

          {plan.changes && (
            <div className="changes">
              <b>What changed:</b> {plan.changes.summary}
              {plan.changes.notes.map((n) => (
                <div key={n}>• {n}</div>
              ))}
            </div>
          )}

          <div className="grid2">
            <section className="panel">
              <div className="row">
                <h2 style={{ margin: 0 }}>{MODE_LABEL[plan.mode] ?? plan.mode} plan</h2>
                <span className={`badge ${plan.status}`}>{plan.status}</span>
              </div>
              <dl className="kv" style={{ marginTop: 10 }}>
                <dt>Planned</dt>
                <dd>
                  {plan.items.length} items, {minutesLabel(plan.scores.scheduled_minutes)}
                </dd>
                <dt>Dropped</dt>
                <dd>{plan.dropped.length}</dd>
                <dt>Solver</dt>
                <dd>
                  {plan.solver_status} in {plan.solve_seconds} s
                </dd>
                <dt>Plan id</dt>
                <dd className="small muted">{plan.plan_id}</dd>
              </dl>
            </section>
            <section className="panel">
              <h2>Goal loss</h2>
              <LossBars loss={plan.scores.loss} />
              <p className="muted small">
                Share of each goal&apos;s proposed value left out. Fairness gap {Math.round(plan.scores.fairness_gap * 100)}%.
              </p>
            </section>
            <section className="panel">
              <h2>Re-plan</h2>
              <p className="muted small">Keeps accepted items, drops rejected ones, plans the rest again.</p>
              <label>
                Nothing new before (optional)
                <input type="datetime-local" value={notBefore} onChange={(e) => setNotBefore(e.target.value)} />
              </label>
              <div className="row" style={{ marginTop: 8 }}>
                <button className="primary" onClick={replan} disabled={busy || locked}>
                  Re-plan
                </button>
                <a className="button" href={api.icsUrl(plan.plan_id)} download="cognipath-plan.ics">
                  Download .ics
                </a>
              </div>
            </section>
          </div>

          <section className="panel">
            <div className="legend">
              <span>
                <span className="dot" style={{ background: "var(--event)" }} />
                Event
              </span>
              <span>
                <span className="dot" style={{ background: "var(--tutor)" }} />
                Tutor
              </span>
              <span>
                <span className="dot" style={{ background: "var(--career)" }} />
                Career
              </span>
              <span>
                <span className="dot" style={{ background: "var(--busy)" }} />
                Busy (profile)
              </span>
              <span>Dark border = accepted · faded = rejected · click a block for details</span>
            </div>
            <WeekCalendar
              horizonStart={datePart(plan.horizon_start)}
              days={planDays}
              items={plan.items}
              busy={profile?.busy_blocks ?? []}
              fromHour={fromHour}
              toHour={toHour}
              selected={selectedItem}
              onSelect={setSelectedItem}
            />
            {chosen && (
              <div className="changes">
                <b>{chosen.title}</b> <span className={`badge ${chosen.decision}`}>{chosen.decision}</span>
                <div className="small">{chosen.sessions.map((s) => rangeLabel(s.start, s.end)).join(" · ")}</div>
                <div>{chosen.explanation}</div>
              </div>
            )}
          </section>

          <section className="panel">
            <div className="row">
              <h2 style={{ margin: 0 }}>Items ({items.length})</h2>
              <span className="spacer" />
              <button className="ok" onClick={() => decide(pending, "accepted")} disabled={busy || locked || !pending.length}>
                Accept all pending ({pending.length})
              </button>
            </div>
            {locked && <p className="muted small">This plan is {plan.status}; load the current plan to make decisions.</p>}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Activity</th>
                    <th>Why</th>
                    <th>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((i) => (
                    <tr
                      key={i.item_id}
                      onClick={() => setSelectedItem(i.item_id)}
                      style={{ background: i.item_id === selectedItem ? "#f2f5fd" : undefined }}
                    >
                      <td className="small" style={{ whiteSpace: "nowrap" }}>
                        {i.sessions.map((s) => (
                          <div key={s.start}>{rangeLabel(s.start, s.end)}</div>
                        ))}
                      </td>
                      <td>
                        <b>{i.title}</b>
                        <div>
                          {i.source_agents.map((a) => (
                            <span key={a} className={`badge ${a}`} style={{ marginRight: 4 }}>
                              {a}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="small muted">{i.explanation}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <span className={`badge ${i.decision}`}>{i.decision}</span>
                        <div className="row" style={{ marginTop: 4, gap: 4 }}>
                          <button className="small ok" disabled={busy || locked || i.decision === "accepted"} onClick={() => decide([i], "accepted")}>
                            Accept
                          </button>
                          <button className="small danger" disabled={busy || locked || i.decision === "rejected"} onClick={() => decide([i], "rejected")}>
                            Reject
                          </button>
                          {i.decision !== "pending" && (
                            <button className="small" disabled={busy || locked} onClick={() => decide([i], "pending")}>
                              Undo
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h2>Dropped ({plan.dropped.length})</h2>
            <div className="table-wrap">
              <table>
                <tbody>
                  {plan.dropped.map((d) => (
                    <tr key={d.proposal_id}>
                      <td>
                        <b>{d.title}</b>{" "}
                        {d.source_agents.map((a) => (
                          <span key={a} className={`badge ${a}`} style={{ marginLeft: 4 }}>
                            {a}
                          </span>
                        ))}
                      </td>
                      <td className="muted">{d.explanation}</td>
                    </tr>
                  ))}
                  {!plan.dropped.length && (
                    <tr>
                      <td className="muted">Nothing dropped — everything fits.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}

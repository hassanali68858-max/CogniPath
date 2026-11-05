"use client";

import { CalendarPlus, Clock, Loader2, Lock, Save, Scale, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useStatus } from "@/components/StatusProvider";
import { errorText, useToast } from "@/components/Toast";
import { useUser } from "@/components/UserProvider";
import { api } from "@/lib/api";
import { datePart, dayLabel, minutesLabel, timePart, weekday } from "@/lib/format";
import { GOAL_META } from "@/lib/meta";
import { type BusyBlock, GOALS, type PlannerProfile } from "@/lib/types";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const hhmm = (t: string) => t.slice(0, 5);
const toMin = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));

function defaults(userId: string): PlannerProfile {
  return {
    user_id: userId,
    day_start: "09:00",
    day_end: "22:00",
    evening_after: "20:00",
    daily_cap_min: 180,
    free_weekdays: [],
    busy_blocks: [],
    conflict_weight: 0.2,
  };
}

function normalise(p: PlannerProfile): PlannerProfile {
  // older saved profiles may still carry weights / fairness_weight; the backend ignores them, so drop them here too
  const { weights: _w, fairness_weight: _f, ...rest } = p as PlannerProfile & { weights?: unknown; fairness_weight?: unknown };
  return { ...rest, day_start: hhmm(p.day_start), day_end: hhmm(p.day_end), evening_after: hhmm(p.evening_after) };
}

export default function ProfilePage() {
  const { userId } = useUser();
  const { refresh } = useStatus();
  const toast = useToast();
  const [profile, setProfile] = useState<PlannerProfile>(defaults(userId));
  const [saved, setSaved] = useState<string>(JSON.stringify(defaults(userId)));
  const [exists, setExists] = useState(false);
  const [saving, setSaving] = useState(false);
  const [block, setBlock] = useState<BusyBlock>({ title: "", start: "", end: "" });

  useEffect(() => {
    api
      .getProfile(userId)
      .then((p) => {
        const n = normalise(p);
        setProfile(n);
        setSaved(JSON.stringify(n));
        setExists(true);
      })
      .catch(() => {
        const d = defaults(userId);
        setProfile(d);
        setSaved(JSON.stringify(d));
        setExists(false);
      });
  }, [userId]);

  const dirty = JSON.stringify(profile) !== saved || !exists;
  const set = <K extends keyof PlannerProfile>(key: K, value: PlannerProfile[K]) =>
    setProfile((p) => ({ ...p, [key]: value }));

  const blocks = useMemo(
    () => [...profile.busy_blocks].sort((a, b) => a.start.localeCompare(b.start)),
    [profile.busy_blocks],
  );

  function addBlock() {
    if (!block.title || !block.start || !block.end) {
      toast("error", "Fill in all three fields", "A commitment needs a name, a start and an end.");
      return;
    }
    if (block.end <= block.start) {
      toast("error", "End must be after start");
      return;
    }
    set("busy_blocks", [...profile.busy_blocks, block]);
    setBlock({ title: "", start: block.end.slice(0, 11) + "10:00", end: block.end.slice(0, 11) + "12:00" });
  }

  async function save() {
    setSaving(true);
    try {
      const p = normalise(await api.putProfile({ ...profile, user_id: userId }));
      setProfile(p);
      setSaved(JSON.stringify(p));
      setExists(true);
      toast("success", "Profile saved", "If you already have a plan, re-plan to apply the changes.");
      await refresh();
    } catch (e) {
      toast("error", "Could not save", errorText(e));
    } finally {
      setSaving(false);
    }
  }

  const pct = (t: string) => `${(toMin(t) / 1440) * 100}%`;

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Step 1</span>
          <h1>About you</h1>
          <p>
            The planner only uses your free time. Set when your day runs, how much planned work is realistic, and what
            is already fixed. {exists ? "" : "Nothing is saved yet for this student."}
          </p>
        </div>
      </div>

      <div className="grid two">
        <section className="card">
          <div className="card-head">
            <Clock size={18} className="muted" />
            <div className="grow">
              <h2>Your day</h2>
              <p>Nothing is planned outside this window. Sessions ending after the evening time count as less ideal.</p>
            </div>
          </div>
          <div className="day-bar" aria-hidden>
            <div className="window" style={{ left: pct(profile.day_start), right: `calc(100% - ${pct(profile.day_end)})` }} />
            <div className="evening" style={{ left: pct(profile.evening_after), right: `calc(100% - ${pct(profile.day_end)})` }} />
          </div>
          <div className="day-scale">
            <span>00</span>
            <span>06</span>
            <span>12</span>
            <span>18</span>
            <span>24</span>
          </div>
          <div className="fields" style={{ marginTop: 14 }}>
            <label className="field">
              <span className="field-label">Day starts</span>
              <input type="time" value={profile.day_start} onChange={(e) => set("day_start", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">Evening from</span>
              <input type="time" value={profile.evening_after} onChange={(e) => set("evening_after", e.target.value)} />
            </label>
            <label className="field">
              <span className="field-label">Day ends</span>
              <input type="time" value={profile.day_end} onChange={(e) => set("day_end", e.target.value)} />
            </label>
          </div>

          <label className="field" style={{ marginTop: 18 }}>
            <span className="field-label">
              Daily limit: <b style={{ color: "var(--text)" }}>{minutesLabel(profile.daily_cap_min)}</b> of planned activities
            </span>
            <input
              type="range"
              min={60}
              max={480}
              step={30}
              value={profile.daily_cap_min}
              onChange={(e) => set("daily_cap_min", Number(e.target.value))}
            />
            <span className="field-hint">Lectures and other commitments below don&apos;t count towards this.</span>
          </label>

          <div className="field" style={{ marginTop: 18 }}>
            <span className="field-label">Days off (nothing flexible is planned)</span>
            <div className="chips">
              {WEEKDAYS.map((d, i) => (
                <button
                  key={d}
                  className={`chip${profile.free_weekdays.includes(i) ? " on" : ""}`}
                  onClick={() =>
                    set(
                      "free_weekdays",
                      profile.free_weekdays.includes(i)
                        ? profile.free_weekdays.filter((x) => x !== i)
                        : [...profile.free_weekdays, i],
                    )
                  }
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <div className="grow">
              <h2>How your goals are balanced</h2>
              <p>No sliders and no priorities. The planner never ranks one goal or agent above another.</p>
            </div>
          </div>
          {GOALS.map((g) => {
            const Icon = GOAL_META[g].icon;
            return (
              <div className="weight-row" key={g} style={{ gridTemplateColumns: "36px 1fr" }}>
                <span className={`agent-avatar ${g === "study" ? "tutor" : g === "career" ? "career" : "event"}`} style={{ width: 36, height: 36 }}>
                  <Icon size={18} />
                </span>
                <div>
                  <b>{GOAL_META[g].label}</b> <span className="small faint">{GOAL_META[g].question}</span>
                </div>
              </div>
            );
          })}
          <div className="weight-row" style={{ gridTemplateColumns: "36px 1fr" }}>
            <span className="agent-avatar user" style={{ width: 36, height: 36 }}>
              <Scale size={18} />
            </span>
            <p className="small muted" style={{ margin: 0 }}>
              Each suggestion scores 0–1 for study, career and social. When time is short you get a balanced plan
              plus versions that lean towards one goal, and you can steer any of them on the plan page:{" "}
              <b>improve</b> this, <b>keep</b> that, this one <b>can give</b>.
            </p>
          </div>
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <Lock size={18} className="muted" />
          <div className="grow">
            <h2>Fixed commitments ({blocks.length})</h2>
            <p>Lectures, work shifts, appointments. The planner never puts anything on top of these.</p>
          </div>
        </div>

        <div className="fields" style={{ alignItems: "end", marginBottom: 16 }}>
          <label className="field">
            <span className="field-label">What</span>
            <input placeholder="e.g. Algorithms lecture" value={block.title} onChange={(e) => setBlock({ ...block, title: e.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">Starts</span>
            <input type="datetime-local" value={block.start} onChange={(e) => setBlock({ ...block, start: e.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">Ends</span>
            <input type="datetime-local" value={block.end} onChange={(e) => setBlock({ ...block, end: e.target.value })} />
          </label>
          <button className="btn" onClick={addBlock}>
            <CalendarPlus size={16} /> Add commitment
          </button>
        </div>

        {blocks.length ? (
          <div className="commitments">
            {blocks.map((b) => (
              <div className="commitment" key={`${b.start}-${b.title}`}>
                <div className="date">
                  <span>{WEEKDAYS[weekday(datePart(b.start))]}</span>
                  <b>{Number(b.start.slice(8, 10))}</b>
                </div>
                <div>
                  <b>{b.title}</b>
                  <div className="small muted">
                    {dayLabel(datePart(b.start))} · {timePart(b.start)}–{timePart(b.end)}
                  </div>
                </div>
                <button
                  className="icon-btn"
                  aria-label={`Remove ${b.title}`}
                  onClick={() => set("busy_blocks", profile.busy_blocks.filter((x) => x !== b))}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">No commitments yet. Add your lectures and shifts so nothing gets planned on top of them.</p>
        )}
      </section>

      {dirty && (
        <div className="save-bar">
          <span className="grow">{exists ? "You have unsaved changes." : "This profile is not saved yet."}</span>
          <button className="btn primary" onClick={save} disabled={saving}>
            {saving ? <Loader2 size={16} className="spin" /> : <Save size={16} />} Save profile
          </button>
        </div>
      )}
    </>
  );
}

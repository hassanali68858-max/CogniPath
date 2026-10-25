"use client";

import { useEffect, useState } from "react";

import { Message, type Msg, errorText } from "@/components/Message";
import { useUser } from "@/components/UserProvider";
import { ApiError, api } from "@/lib/api";
import { rangeLabel } from "@/lib/format";
import { type BusyBlock, GOALS, type PlannerProfile } from "@/lib/types";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function defaults(userId: string): PlannerProfile {
  return {
    user_id: userId,
    weights: { study: 1, career: 1, social: 1 },
    day_start: "09:00",
    day_end: "22:00",
    evening_after: "20:00",
    daily_cap_min: 180,
    free_weekdays: [],
    busy_blocks: [],
    fairness_weight: 1,
    conflict_weight: 0.2,
  };
}

const hhmm = (t: string) => t.slice(0, 5);

export default function ProfilePage() {
  const { userId } = useUser();
  const [profile, setProfile] = useState<PlannerProfile>(defaults(userId));
  const [exists, setExists] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const [block, setBlock] = useState<BusyBlock>({ title: "", start: "", end: "" });

  useEffect(() => {
    setMsg(null);
    api
      .getProfile(userId)
      .then((p) => {
        setProfile({ ...p, day_start: hhmm(p.day_start), day_end: hhmm(p.day_end), evening_after: hhmm(p.evening_after) });
        setExists(true);
      })
      .catch((e) => {
        setProfile(defaults(userId));
        setExists(false);
        if (!(e instanceof ApiError && e.status === 404)) setMsg({ kind: "error", text: errorText(e) });
      });
  }, [userId]);

  const set = <K extends keyof PlannerProfile>(key: K, value: PlannerProfile[K]) =>
    setProfile((p) => ({ ...p, [key]: value }));

  function toggleWeekday(d: number) {
    set(
      "free_weekdays",
      profile.free_weekdays.includes(d) ? profile.free_weekdays.filter((x) => x !== d) : [...profile.free_weekdays, d],
    );
  }

  function addBlock() {
    if (!block.title || !block.start || !block.end) {
      setMsg({ kind: "error", text: "A busy block needs a title, a start and an end." });
      return;
    }
    const sorted = [...profile.busy_blocks, block].sort((a, b) => a.start.localeCompare(b.start));
    set("busy_blocks", sorted);
    setBlock({ title: "", start: "", end: "" });
    setMsg(null);
  }

  async function save() {
    try {
      const saved = await api.putProfile({ ...profile, user_id: userId });
      setExists(true);
      setMsg({ kind: "ok", text: `Profile saved for ${saved.user_id}. Re-plan to apply changes to an existing plan.` });
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    }
  }

  return (
    <>
      <h1>Profile</h1>
      <p className="lead">
        What the planner needs to know about <b>{userId}</b> {exists ? "" : "(not saved yet)"}. In the real app this
        comes from onboarding and the student&apos;s timetable.
      </p>

      <section className="panel">
        <h2>Day and limits</h2>
        <div className="form-grid">
          <label>
            Day starts
            <input type="time" value={profile.day_start} onChange={(e) => set("day_start", e.target.value)} />
          </label>
          <label>
            Day ends
            <input type="time" value={profile.day_end} onChange={(e) => set("day_end", e.target.value)} />
          </label>
          <label>
            Evening after (soft penalty)
            <input type="time" value={profile.evening_after} onChange={(e) => set("evening_after", e.target.value)} />
          </label>
          <label>
            Daily limit (minutes)
            <input
              type="number"
              min={30}
              step={30}
              value={profile.daily_cap_min}
              onChange={(e) => set("daily_cap_min", Number(e.target.value))}
            />
          </label>
        </div>
        <div className="row">
          <span className="muted small">Days off:</span>
          {WEEKDAYS.map((d, i) => (
            <label key={d} className="inline">
              <input type="checkbox" checked={profile.free_weekdays.includes(i)} onChange={() => toggleWeekday(i)} /> {d}
            </label>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Goal weights</h2>
        <p className="muted small">How much this student cares about each goal. 1 = normal, 3 = much more.</p>
        <div className="form-grid">
          {GOALS.map((g) => (
            <label key={g}>
              {g}: {profile.weights[g]}
              <input
                type="range"
                min={0}
                max={3}
                step={0.5}
                value={profile.weights[g]}
                onChange={(e) => set("weights", { ...profile.weights, [g]: Number(e.target.value) })}
              />
            </label>
          ))}
          <label>
            Fairness (nobody gets ignored): {profile.fairness_weight}
            <input
              type="range"
              min={0}
              max={3}
              step={0.5}
              value={profile.fairness_weight}
              onChange={(e) => set("fairness_weight", Number(e.target.value))}
            />
          </label>
        </div>
      </section>

      <section className="panel">
        <h2>Busy time ({profile.busy_blocks.length})</h2>
        <p className="muted small">Lectures, work shifts and other fixed commitments. The planner never overlaps these.</p>
        <div className="row" style={{ marginBottom: 12 }}>
          <label>
            Title
            <input value={block.title} onChange={(e) => setBlock({ ...block, title: e.target.value })} />
          </label>
          <label>
            Start
            <input type="datetime-local" value={block.start} onChange={(e) => setBlock({ ...block, start: e.target.value })} />
          </label>
          <label>
            End
            <input type="datetime-local" value={block.end} onChange={(e) => setBlock({ ...block, end: e.target.value })} />
          </label>
          <button onClick={addBlock} style={{ alignSelf: "flex-end" }}>
            Add
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>When</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {profile.busy_blocks.map((b, i) => (
                <tr key={`${b.start}-${i}`}>
                  <td>{b.title}</td>
                  <td>{rangeLabel(b.start, b.end)}</td>
                  <td>
                    <button
                      className="small danger"
                      onClick={() => set("busy_blocks", profile.busy_blocks.filter((_, j) => j !== i))}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
              {!profile.busy_blocks.length && (
                <tr>
                  <td colSpan={3} className="muted">
                    No busy time yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="row">
        <button className="primary" onClick={save}>
          Save profile
        </button>
      </div>
      <Message msg={msg} />
    </>
  );
}

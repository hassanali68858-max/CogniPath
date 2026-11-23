"use client";

import { Briefcase, CalendarPlus, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { errorText, useToast } from "@/components/Toast";
import { useUser } from "@/components/UserProvider";
import { type Application, STATUSES, type Status, careerApi } from "@/lib/career";
import { MatchRing } from "./MatchRing";

/** The application tracker. The student applies; here they only record what happened. */
export function ApplicationsCard({
  refreshKey,
  onChanged,
  onLoaded,
}: {
  refreshKey: number;
  onChanged: () => void;
  onLoaded: (apps: Application[]) => void;
}) {
  const { userId } = useUser();
  const toast = useToast();
  const [apps, setApps] = useState<Application[] | null>(null);
  const [error, setError] = useState("");
  const [dates, setDates] = useState<Record<number, string>>({});

  useEffect(() => {
    careerApi
      .tracker(userId)
      .then((a) => {
        setApps(a);
        setError("");
        onLoaded(a);
      })
      .catch((e) => setError(errorText(e)));
    // onLoaded is a callback from the page; reloading only depends on the student and the data
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, refreshKey]);

  async function setStatus(a: Application, status: Status, interviewDate?: string) {
    try {
      await careerApi.updateStatus(userId, a.application_id, status, interviewDate);
      toast("success", "Status updated", `${a.title}: ${status}`);
      onChanged();
    } catch (e) {
      toast("error", "Could not update", errorText(e));
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <Briefcase size={18} className="muted" />
        <div className="grow">
          <h2>My applications</h2>
          <p>You apply yourself. Record each step here; deadlines and interviews go to your calendar.</p>
        </div>
        <a className="btn small" href={careerApi.calendarUrl(userId)}>
          <CalendarPlus size={14} /> Calendar (.ics)
        </a>
      </div>

      {error ? (
        <p className="small" style={{ color: "var(--bad)" }}>{error}</p>
      ) : apps === null ? (
        <div className="empty"><Loader2 className="spin" /></div>
      ) : apps.length === 0 ? (
        <div className="empty">
          <div className="empty-icon"><Briefcase size={26} /></div>
          <h2>No applications yet</h2>
          <p>Use Track or I applied on a job above to start your list.</p>
        </div>
      ) : (
        <div className="career-list">
          {apps.map((a) => (
            <div key={a.application_id} className="career-row">
              <MatchRing value={a.match === null ? null : Math.round(a.match * 100)} />
              <div className="grow">
                <div className="title">{a.title}</div>
                <div className="meta">
                  {a.company}
                  {a.deadline ? ` · Closes ${a.deadline}` : ""}
                  {a.interview_date ? ` · Interview ${a.interview_date}` : ""}
                </div>
              </div>
              <div className="career-actions">
                <span className={`pill st-${a.status}`}>{a.status}</span>
                <select
                  value={a.status}
                  aria-label={`Status of ${a.title}`}
                  onChange={(e) => setStatus(a, e.target.value as Status)}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {a.status === "interview" && (
                  <>
                    <input
                      type="date"
                      aria-label="Interview date"
                      value={dates[a.application_id] ?? a.interview_date ?? ""}
                      onChange={(e) => setDates({ ...dates, [a.application_id]: e.target.value })}
                    />
                    <button
                      className="btn small"
                      disabled={!dates[a.application_id]}
                      onClick={() => setStatus(a, "interview", dates[a.application_id])}
                    >
                      Save date
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

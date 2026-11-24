"use client";

import { CalendarPlus, Check, ExternalLink, Loader2, Plus, Search, SearchX } from "lucide-react";
import { useEffect, useState } from "react";

import { errorText, useToast } from "@/components/Toast";
import { useUser } from "@/components/UserProvider";
import { type Job, careerApi } from "@/lib/career";
import { MatchRing } from "./MatchRing";

/** "Closes 5 Dec 2026 · 11 days left" for the job card, or a note that the ad gives no date. */
function deadlineText(deadline: string | null) {
  // Many companies recruit on a rolling basis and give no closing date
  if (!deadline) return { text: "No closing date given · open until filled, apply early", soon: false };
  const day = new Date(`${deadline}T00:00:00`);
  const days = Math.round((day.getTime() - new Date().setHours(0, 0, 0, 0)) / 86_400_000);
  const nice = day.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const left = days < 0 ? "closed" : days === 0 ? "closes today" : `${days} day${days === 1 ? "" : "s"} left`;
  return { text: `Apply by ${nice} · ${left}`, soon: days >= 0 && days <= 7 };
}

/** Search the jobs the Career Agent found for this student. Shows the match score and whether the student already applied. */
export function JobSearchCard({ refreshKey, onTracked }: { refreshKey: number; onTracked: () => void }) {
  const { userId } = useUser();
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  // Search again when the text, the student or the data changes (small delay while typing)
  useEffect(() => {
    const t = setTimeout(() => {
      careerApi
        .searchJobs(userId, query)
        .then((j) => {
          setJobs(j);
          setError("");
        })
        .catch((e) => setError(errorText(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [userId, query, refreshKey]);

  async function track(job: Job, applied: boolean) {
    setBusyId(job.id);
    try {
      await careerApi.track(userId, job.title, applied);
      toast("success", applied ? "Marked as applied" : "Added to your applications", job.title);
      onTracked();
    } catch (e) {
      toast("error", "Could not add", errorText(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <Search size={18} className="muted" />
        <div className="grow">
          <h2>Find jobs</h2>
          <p>Jobs the Career Agent found for you. Best matches for your CV come first.</p>
        </div>
      </div>

      <div className="search-box" style={{ marginBottom: 14 }}>
        <Search size={16} />
        <input value={query} placeholder="Search title, company or skill…" onChange={(e) => setQuery(e.target.value)} />
      </div>

      {error ? (
        <p className="small" style={{ color: "var(--bad)" }}>{error}</p>
      ) : jobs === null ? (
        <div className="empty"><Loader2 className="spin" /></div>
      ) : jobs.length === 0 ? (
        <div className="empty">
          <div className="empty-icon"><SearchX size={26} /></div>
          {query ? (
            <>
              <h2>No jobs found</h2>
              <p>No job matches &ldquo;{query}&rdquo;. Try another word.</p>
            </>
          ) : (
            <>
              <h2>No jobs for you yet</h2>
              <p>Upload your CV above and press Run Career Agent. Jobs that fit you will appear here.</p>
            </>
          )}
        </div>
      ) : (
        <div className="career-list">
          {jobs.map((j) => (
            <div key={j.id} className="career-row">
              <MatchRing value={j.match} />
              <div className="grow">
                <div className="title">{j.title}</div>
                <div className="meta">
                  {j.company}
                  {j.match !== null && <> · {j.match}% match</>}
                </div>
                {j.summary && <p className="job-summary">{j.summary}</p>}
                <div className={`meta${deadlineText(j.deadline).soon ? " deadline-soon" : ""}`}>
                  {deadlineText(j.deadline).text}
                </div>
              </div>
              <div className="career-actions">
                {j.status ? (
                  <span className={`pill st-${j.status}`}>
                    <Check size={12} /> {j.status}
                  </span>
                ) : (
                  <>
                    <button className="btn small" onClick={() => track(j, false)} disabled={busyId === j.id}>
                      <Plus size={14} /> Track
                    </button>
                    <button className="btn small career" onClick={() => track(j, true)} disabled={busyId === j.id}>
                      <Check size={14} /> I applied
                    </button>
                  </>
                )}
                {j.deadline && (
                  <a className="icon-btn" href={careerApi.jobCalendarUrl(userId, j.id)} aria-label="Add deadline to calendar" title="Add deadline to calendar">
                    <CalendarPlus size={15} />
                  </a>
                )}
                {j.url && (
                  <a className="icon-btn" href={j.url} target="_blank" rel="noreferrer" aria-label="Open posting">
                    <ExternalLink size={15} />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
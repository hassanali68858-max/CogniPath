"use client";

import { Briefcase } from "lucide-react";
import { useCallback, useState } from "react";

import { ApplicationsCard } from "@/components/career/ApplicationsCard";
import { CvCard } from "@/components/career/CvCard";
import { JobSearchCard } from "@/components/career/JobSearchCard";
import { ProfileCard } from "@/components/career/ProfileCard";
import type { Application } from "@/lib/career";
import "./career.css";

/** Career Agent page: preferences, CV, job search and the application tracker in one place. */
export default function CareerPage() {
  // Bump this number to make the job list and the tracker load fresh data
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  const [apps, setApps] = useState<Application[]>([]);

  const applied = apps.filter((a) => a.status !== "planned").length;
  const interviews = apps.filter((a) => a.status === "interview").length;
  const offers = apps.filter((a) => a.status === "offer").length;

  return (
    <>
      <div className="page-head">
        <span className="agent-avatar career career-hero-icon">
          <Briefcase size={22} />
        </span>
        <div>
          <span className="eyebrow">Career Agent</span>
          <h1>Your career</h1>
          <p>
            Jobs that fit your CV, the skills you still need, and your applications in one place. The agent only
            advises and prepares; you decide and apply yourself.
          </p>
        </div>
      </div>

      <div className="career-stats">
        <div className="career-stat">
          <b>{apps.length}</b>
          <span>Tracked jobs</span>
        </div>
        <div className="career-stat">
          <b>{applied}</b>
          <span>Applied</span>
        </div>
        <div className="career-stat accent">
          <b>{interviews}</b>
          <span>Interviews</span>
        </div>
        <div className="career-stat accent">
          <b>{offers}</b>
          <span>Offers</span>
        </div>
      </div>

      <div className="grid two">
        <ProfileCard />
        <CvCard onPipelineDone={refresh} />
      </div>

      <div style={{ marginTop: 16 }}>
        <JobSearchCard refreshKey={refreshKey} onTracked={refresh} />
      </div>
      <div style={{ marginTop: 16 }}>
        <ApplicationsCard refreshKey={refreshKey} onChanged={refresh} onLoaded={setApps} />
      </div>
    </>
  );
}

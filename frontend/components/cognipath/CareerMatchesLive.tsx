'use client';

import { useEffect, useState } from 'react';
import type { InternshipMatch } from '@/lib/cognipath/types';
import { MOCK_MATCHES } from '@/lib/cognipath/mock-data';
import { useUser } from '@/components/UserProvider';
import CareerSkillGapCard from './CareerSkillGapCard';

// Where the Career Agent API runs (uvicorn api:app --port 8001)
const CAREER_URL = process.env.NEXT_PUBLIC_CAREER_URL ?? 'http://127.0.0.1:8001';

/** Loads real job matches from the Career Agent. Shows demo data if the API is not running. */
export default function CareerMatchesLive() {
  const { userId } = useUser();
  const [matches, setMatches] = useState<InternshipMatch[]>(MOCK_MATCHES);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${CAREER_URL}/matches/${encodeURIComponent(userId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Career API answered ${res.status}`);
        return res.json() as Promise<InternshipMatch[]>;
      })
      .then((data) => {
        if (!cancelled) { setMatches(data); setLive(true); }
      })
      .catch(() => {
        // API not running or user unknown: keep the demo data so the page still works
        if (!cancelled) { setMatches(MOCK_MATCHES); setLive(false); }
      });
    return () => { cancelled = true; };
  }, [userId]);

  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">
        {live ? `Live data from the Career Agent for "${userId}"` : 'Career Agent not reachable: showing demo data'}
      </p>
      <CareerSkillGapCard matches={matches} />
    </div>
  );
}
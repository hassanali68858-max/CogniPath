'use client';

import { useMemo, useState } from 'react';
import { Route } from 'lucide-react';
import type { ActivityProposal, Decision, PlanVersion, ScheduledItem } from '@/lib/cognipath/types';
import { DROP_REASONS, MOCK_MATCHES, MOCK_PLANS, NOW, TODAY, WEEK_START } from '@/lib/cognipath/mock-data';
import { addMinutes, fmtSlot, parseISO } from '@/lib/cognipath/theme';
import WeeklyCalendarGrid from './WeeklyCalendarGrid';
import PlanVersionSwitcher from './PlanVersionSwitcher';
import DecisionReviewPanel from './DecisionReviewPanel';
import TutorProgressCard from './TutorProgressCard';
import CareerSkillGapCard from './CareerSkillGapCard';

/**
 * STUB: replace with `POST /api/replan` to the Planner Agent.
 * Accepted items stay fixed, rejected items leave the plan, pending flexible items may move,
 * and dropped items the student accepted are pulled back in as NEW.
 */
function simulateReplan(plan: PlanVersion, decisions: Record<string, Decision>): PlanVersion {
  const items: ScheduledItem[] = [];
  const dropped: ActivityProposal[] = [];

  for (const it of plan.items) {
    const d = decisions[it.id] ?? 'pending';
    if (d === 'rejected') { dropped.push(it.proposal); continue; }
    if (d === 'accepted' || it.proposal.hard || it.proposal.fixed_time) { items.push({ ...it, status: d === 'accepted' ? 'accepted' : it.status, change_tag: 'UNCHANGED' }); continue; }
    const end = parseISO(it.assigned_end).minutes + 30;
    items.push(end <= 22 * 60
      ? { ...it, assigned_start: addMinutes(it.assigned_start, 30), assigned_end: addMinutes(it.assigned_end, 30), status: 'pending', change_tag: 'MOVED' }
      : { ...it, change_tag: 'UNCHANGED' });
  }
  for (const p of plan.dropped_items) {
    if ((decisions[p.proposal_id] ?? 'pending') === 'accepted') {
      const mins = p.duration_min ?? 60;
      items.push({ id: `${plan.id}-${p.proposal_id}-new`, proposal: p, assigned_start: '2026-11-08T15:00', assigned_end: addMinutes('2026-11-08T15:00', mins), status: 'accepted', change_tag: 'NEW' });
    } else dropped.push(p);
  }
  return { ...plan, items, dropped_items: dropped };
}

export default function CogniPathDashboard() {
  const [plans, setPlans] = useState<PlanVersion[]>(MOCK_PLANS);
  const [activeId, setActiveId] = useState(MOCK_PLANS[0].id);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [busy, setBusy] = useState(false);
  const [dropReasons, setDropReasons] = useState(DROP_REASONS);
  const [notice, setNotice] = useState<string | null>(null);

  const active = plans.find((p) => p.id === activeId)!;

  // Decisions are applied on top of the plan so the calendar updates instantly.
  const displayItems = useMemo<ScheduledItem[]>(
    () => active.items.map((it) => {
      const d = decisions[it.id];
      if (!d) return it;
      return { ...it, status: d, change_tag: d === 'rejected' ? 'REJECTED' : it.change_tag };
    }),
    [active, decisions],
  );

  function decide(id: string, d: Decision) {
    setDecisions((prev) => {
      const next = { ...prev };
      if (d === 'pending') delete next[id]; else next[id] = d;
      return next;
    });
  }

  function replan() {
    setBusy(true);
    setTimeout(() => {
      const next = simulateReplan(active, decisions);
      setDropReasons((r) => {
        const extra: Record<string, string> = { ...r };
        next.dropped_items.forEach((p) => { if (!extra[p.proposal_id]) extra[p.proposal_id] = 'You rejected this, so it is excluded from future plans.'; });
        return extra;
      });
      setPlans((ps) => ps.map((p) => (p.id === active.id ? next : p)));
      setDecisions({});
      const moved = next.items.filter((i) => i.change_tag === 'MOVED').length;
      const added = next.items.filter((i) => i.change_tag === 'NEW').length;
      setNotice(`Plan updated: ${moved} moved, ${added} new.`);
      setTimeout(() => setNotice(null), 4000);
      setBusy(false);
    }, 900);
  }

  const next = [...displayItems]
    .filter((i) => i.assigned_start >= NOW && i.status !== 'rejected')
    .sort((a, b) => a.assigned_start.localeCompare(b.assigned_start))[0];

  return (
    <div className="cognipath-dashboard min-h-screen bg-[#F6F7F9] text-slate-900">
      <header className="sticky top-0 z-40 bg-white/85 ring-1 ring-slate-900/5 backdrop-blur">
        <div className="mx-auto flex max-w-375 flex-wrap items-center justify-between gap-x-8 gap-y-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900 text-white"><Route className="h-4 w-4" /></span>
            <span className="font-display text-lg font-semibold tracking-tight">CogniPath</span>
          </div>
          <PlanVersionSwitcher versions={plans} activeId={activeId} onChange={(id) => { setActiveId(id); setDecisions({}); }} />
        </div>
      </header>

      <main className="mx-auto max-w-375 space-y-8 px-4 py-6 sm:px-6">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Week of 2 to 8 November</h1>
          <p className="mt-1 text-sm text-slate-600">
            {next ? <>Next up: <span className="font-medium text-slate-900">{next.proposal.title}</span>, {fmtSlot(next.assigned_start, next.assigned_end)}</> : 'Nothing left this week.'}
          </p>
        </div>

        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
          <WeeklyCalendarGrid items={displayItems} weekStart={WEEK_START} today={TODAY} now={NOW} />
          <DecisionReviewPanel
            className="xl:sticky xl:top-20"
            items={displayItems}
            dropped={active.dropped_items}
            dropReasons={dropReasons}
            decisions={decisions}
            onDecide={decide}
            onReplan={replan}
            isReplanning={busy}
          />
        </div>

        <section aria-labelledby="goals-heading">
          <h2 id="goals-heading" className="mb-3 font-display text-xl font-semibold tracking-tight">Keep your goals on track</h2>
          <div className="grid gap-5 lg:grid-cols-2">
            <TutorProgressCard />
            <CareerSkillGapCard matches={MOCK_MATCHES} />
          </div>
        </section>
      </main>

      {notice && (
        <p role="status" className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white shadow-xl">
          {notice}
        </p>
      )}
    </div>
  );
}
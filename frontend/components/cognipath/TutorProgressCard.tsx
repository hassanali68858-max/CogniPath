'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, BookOpen, CalendarDays, CheckCircle2, Loader2, RefreshCw, Send } from 'lucide-react';
import {
  tutorApi,
  type CatalogSource,
  type TopicStatus,
  type TutorContext,
  type TutorReport,
  type UpcomingCourse,
} from '@/lib/cognipath/tutor-api';
import { cn } from '@/lib/cognipath/theme';
import TutorQuizModal, { percent } from './TutorQuizModal';

const VISIBLE_TOPICS = 5;
const VISIBLE_COURSES = 4;

export default function TutorProgressCard({ className }: { className?: string }) {
  const [context, setContext] = useState<TutorContext | null>(null);
  const [report, setReport] = useState<TutorReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quizTopic, setQuizTopic] = useState<TopicStatus | null>(null);

  useEffect(() => {
    tutorApi.context().then(setContext, (e: Error) => setError(e.message));
  }, []);

  const load = useCallback(async () => {
    if (!context) return;
    try {
      setReport(await tutorApi.report(context));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [context]);

  useEffect(() => { load(); }, [load]);

  const closeQuiz = useCallback(() => setQuizTopic(null), []);

  return (
    <section className={cn('rounded-2xl bg-white p-6 ring-1 ring-slate-900/5', className)} aria-label="Study progress">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-blue-500" />
        <h2 className="font-display text-lg font-semibold text-slate-900">Study progress</h2>
        {report && <StatusPill atRisk={report.progress.status === 'at_risk'} />}
      </div>

      {error && <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-800">Could not load the Tutor Agent: {error}</p>}
      {!report && !error && <Loader2 className="mx-auto mt-8 h-6 w-6 animate-spin text-blue-500" aria-label="Loading study progress" />}

      {report && context && (
        <>
          <p className="mt-0.5 text-xs text-slate-500">{report.progress.programme_name} · as of {fmtDay(context.today)}</p>
          <Warnings report={report} />
          <Credits report={report} />
          <NextCourses context={context} />
          <PracticeTopics topics={report.topics} context={context} onQuiz={setQuizTopic} />
          <SendToPlanner context={context} count={report.proposals.length} onSent={load} />
          {quizTopic && <TutorQuizModal topic={quizTopic} context={context} onGraded={load} onClose={closeQuiz} />}
        </>
      )}
    </section>
  );
}

function StatusPill({ atRisk }: { atRisk: boolean }) {
  return (
    <span className={cn('ml-auto rounded-full px-2.5 py-0.5 text-xs font-semibold', atRisk ? 'bg-amber-100 text-amber-900' : 'bg-green-100 text-green-800')}>
      {atRisk ? 'At risk' : 'On track'}
    </span>
  );
}

function Warnings({ report }: { report: TutorReport }) {
  const { warnings, status } = report.progress;
  if (!warnings.length) return null;
  // The pace warning explains the at-risk status, so it goes first.
  const ordered = [...warnings].sort((a, b) => Number(b.kind === 'behind_pace') - Number(a.kind === 'behind_pace'));
  return (
    <div role="alert" className="mt-4 flex gap-3 rounded-xl border border-amber-300 bg-amber-50 p-3">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
      <div className="text-sm">
        <p className="font-semibold text-amber-900">{status === 'at_risk' ? 'Graduation is at risk' : 'Check your study plan'}</p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-amber-800">
          {ordered.map((w) => <li key={w.message}>{w.message}</li>)}
        </ul>
      </div>
    </div>
  );
}

function Credits({ report }: { report: TutorReport }) {
  const { modules, completed_credits, required_credits } = report.progress;
  return (
    <div className="mt-4 space-y-3">
      {modules.map((m) => (
        <div key={m.module_id}>
          <div className="flex justify-between text-sm"><span className="font-medium text-slate-800">{m.name}</span><span className="tabular-nums text-slate-600">{m.completed_credits}/{m.required_credits} credits</span></div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-blue-100" role="progressbar" aria-valuenow={m.completed_credits} aria-valuemin={0} aria-valuemax={m.required_credits} aria-label={`${m.name} credits`}>
            <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(100, (m.completed_credits / m.required_credits) * 100)}%` }} />
          </div>
        </div>
      ))}
      <p className="text-xs text-slate-500">{completed_credits} of {required_credits} credits complete</p>
    </div>
  );
}

function NextCourses({ context }: { context: TutorContext }) {
  const [source, setSource] = useState<CatalogSource | null>(null);
  const [courses, setCourses] = useState<UpcomingCourse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([tutorApi.catalogSource(), tutorApi.upcomingCourses(context)]).then(
      ([s, c]) => { setSource(s); setCourses(c); },
      (e: Error) => setError(e.message),
    );
  }, [context]);

  if (error) return <p className="mt-5 text-xs text-red-700">Could not load the next courses: {error}</p>;
  if (!source || !courses) return null;
  return (
    <div className="mt-5 border-t border-slate-100 pt-4">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Next courses</h3>
        <SourceBadge source={source} />
      </div>
      {!courses.length && <p className="mt-2 text-sm text-slate-600">No course offerings are published yet.</p>}
      <ul className="mt-2 list-none space-y-2 pl-0">
        {courses.slice(0, VISIBLE_COURSES).map((c) => (
          <li key={c.code} className="flex items-start justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-800">{c.code} {c.name}</p>
              <p className="text-xs text-slate-500">
                {c.credits} credits · {c.language.toUpperCase()} · {fmtDay(c.start)} – {fmtDay(c.end)}
                {source.source === 'sisu' && !c.from_sisu && ' · demo data'}
              </p>
            </div>
            <span className="inline-flex shrink-0 items-center gap-1 text-xs text-slate-600">
              <CalendarDays className="h-3.5 w-3.5" /> Register by {fmtDay(c.registration_deadline)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourceBadge({ source }: { source: CatalogSource }) {
  if (source.source === 'seed') {
    return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">Demo course data</span>;
  }
  const count = Object.keys(source.linked).length;
  return (
    <span className="rounded-full bg-green-100 px-2 py-0.5 text-[11px] font-medium text-green-800" title={source.url ?? undefined}>
      Live from JYU Sisu · {count} courses
    </span>
  );
}

type PracticeTopicsProps = { topics: TopicStatus[]; context: TutorContext; onQuiz: (t: TopicStatus) => void };

function PracticeTopics({ topics, context, onQuiz }: PracticeTopicsProps) {
  const [showAll, setShowAll] = useState(false);
  const toPractise = practiceList(topics, context);
  const visible = showAll ? toPractise : toPractise.slice(0, VISIBLE_TOPICS);

  return (
    <div className="mt-5 border-t border-slate-100 pt-4">
      <h3 className="text-sm font-semibold text-slate-900">Topics to practise</h3>
      {!toPractise.length && <p className="mt-2 flex items-center gap-1.5 text-sm text-slate-600"><CheckCircle2 className="h-4 w-4 text-green-600" /> All current topics are strong.</p>}
      <ul className="mt-2 list-none space-y-2 pl-0">
        {visible.map((t) => (
          <li key={t.topic_id} className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-800">{t.name}</p>
              <p className="text-xs text-slate-500">{t.course_code} · {topicHint(t, context)}</p>
            </div>
            <button onClick={() => onQuiz(t)} className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border-0 bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
              {t.level === 'strong' ? <RefreshCw className="h-3.5 w-3.5" /> : <BookOpen className="h-3.5 w-3.5" />}
              {t.level === 'strong' ? 'Refresh quiz' : 'Start practice quiz'}
            </button>
          </li>
        ))}
      </ul>
      {toPractise.length > VISIBLE_TOPICS && (
        <button onClick={() => setShowAll((s) => !s)} className="mt-2 border-0 bg-transparent p-0 text-xs font-semibold text-blue-700 hover:underline">
          {showAll ? 'Show fewer' : `Show all ${toPractise.length} topics`}
        </button>
      )}
    </div>
  );
}

function SendToPlanner({ context, count, onSent }: { context: TutorContext; count: number; onSent: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    try {
      const r = await tutorApi.sendToPlanner(context);
      const withdrawn = r.withdrawn.length ? ` and withdrew ${r.withdrawn.length} that are no longer needed` : '';
      setMessage(`Sent ${r.stored} suggestions to the Planner${withdrawn}.`);
      onSent();
    } catch (e) {
      setMessage(`Could not send to the Planner: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
      <p className="text-xs text-slate-600" role="status">{message ?? `${count} Tutor suggestions are ready for the Planner.`}</p>
      <button onClick={send} disabled={busy || !count} className="inline-flex items-center gap-1.5 rounded-lg border border-blue-600 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-50">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Send to Planner
      </button>
    </div>
  );
}

/** Weak topics (weakest first), then untested ones, then strong topics with a refresh due in the window. */
function practiceList(topics: TopicStatus[], context: TutorContext): TopicStatus[] {
  const horizonEnd = addDays(context.today, context.days - 1); // inclusive, as in the backend
  const weak = topics.filter((t) => t.level === 'weak').sort((a, b) => (a.mastery ?? 0) - (b.mastery ?? 0));
  const untested = topics.filter((t) => t.level === 'untested');
  const refresh = topics
    .filter((t) => t.level === 'strong' && t.next_review && t.next_review <= horizonEnd)
    .sort((a, b) => a.next_review!.localeCompare(b.next_review!));
  return [...weak, ...untested, ...refresh];
}

function topicHint(t: TopicStatus, context: TutorContext): string {
  if (t.level === 'untested') return 'not tested yet';
  if (t.level === 'weak') return `${percent(t.mastery ?? 0)} mastery`;
  const due = t.next_review! <= context.today ? 'refresh due now' : `refresh due ${fmtDay(t.next_review!)}`;
  return `${percent(t.mastery ?? 0)} mastery · ${due}`;
}

function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function fmtDay(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
}

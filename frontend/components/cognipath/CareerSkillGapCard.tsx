'use client';

import { useState } from 'react';
import { Check, Copy, Loader2, PenLine } from 'lucide-react';
import type { InternshipMatch } from '@/lib/cognipath/types';
import { cn } from '@/lib/cognipath/theme';
import { useUser } from '@/components/UserProvider';

// Where the Career Agent API runs (uvicorn api:app --port 8001)
const CAREER_URL = process.env.NEXT_PUBLIC_CAREER_URL ?? 'http://127.0.0.1:8001';

// What the Career Agent's /apply endpoints return while the graph waits for the user
type ApplyStep = {
  letter?: string; warnings?: string[];         // letter review
  match?: string; missing?: string[];           // weak match warning
  summary?: string; removed?: string[];         // tailored CV review
  question?: string; options?: string[];        // delivery choice
};
type ApplyReply = { status: 'waiting' | 'done'; job_id: number; step?: ApplyStep; has_letter?: boolean; has_cv?: boolean };

const btn = 'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-60';
const mainBtn = `${btn} bg-orange-500 text-white hover:bg-orange-600`;
const softBtn = `${btn} bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50`;

function MatchCard({ m }: { m: InternshipMatch }) {
  const { userId } = useUser();
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [step, setStep] = useState<ApplyStep | null>(null);
  const [reply, setReply] = useState<ApplyReply | null>(null);
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  // Send one request to the Career Agent and show the next pause (or the finished files)
  async function call(path: string, body: object) {
    setState('loading');
    setError('');
    try {
      const res = await fetch(`${CAREER_URL}/apply/${encodeURIComponent(userId)}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Career API answered ${res.status}`);
      const r = (await res.json()) as ApplyReply;
      setReply(r);
      setStep(r.status === 'waiting' ? r.step ?? null : null);
      setFeedback('');
      setState('ready');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Career Agent not reachable');
      setState('error');
    }
  }

  // Start the application graph; it pauses with a letter for review
  const draft = () => call('/start', { title: m.title });
  // Answer the current pause: "yes", "no", "download" or the user's change request
  const answer = (text: string) => reply && call(`/${reply.job_id}/answer`, { answer: text });

  async function copy() {
    if (!step?.letter) return;
    try { await navigator.clipboard.writeText(step.letter); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard unavailable */ }
  }

  const busy = state === 'loading';
  const fileUrl = (kind: 'letter' | 'cv') =>
    reply ? `${CAREER_URL}/apply/${encodeURIComponent(userId)}/${reply.job_id}/file/${kind}` : '#';

  // Text box + button to ask the agent for changes (used for the letter and the CV)
  const changeBox = (
    <div className="mt-3 flex gap-2">
      <input value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="What should change?"
        className="min-w-0 flex-1 rounded-lg border border-slate-300 px-2 py-1 text-xs" />
      <button onClick={() => answer(feedback)} disabled={busy || !feedback.trim()} className={softBtn}>Ask for changes</button>
    </div>
  );

  return (
    <li className="rounded-xl border border-orange-200 bg-orange-50/50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">{m.org}: {m.title}</p>
          <p className="text-xs text-slate-500">Closes {m.deadline}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-xl font-bold tabular-nums text-orange-600">{m.match}%</p>
          <p className="text-[11px] text-slate-500">skill match</p>
        </div>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-orange-100" role="progressbar" aria-valuenow={m.match} aria-valuemin={0} aria-valuemax={100} aria-label={`${m.org} skill match`}>
        <div className="h-full rounded-full bg-orange-500" style={{ width: `${m.match}%` }} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {m.matchedSkills.map((s) => (
          <span key={s} className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs text-slate-600 ring-1 ring-slate-200"><Check className="h-3 w-3 text-green-600" />{s}</span>
        ))}
      </div>
      <div className="mt-2">
        <p className="text-xs font-medium text-slate-600">Missing skills</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {m.missingSkills.map((s) => (
            <span key={s} className="rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-medium text-orange-800">{s}</span>
          ))}
        </div>
      </div>

      <button onClick={draft} disabled={busy}
        className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-orange-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-orange-600 disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PenLine className="h-3.5 w-3.5" />}
        {busy ? 'Working… (can take a minute)' : reply ? 'Start again' : 'Draft cover letter'}
      </button>

      {state === 'error' && (
        <p className="mt-3 text-xs text-red-700">Something went wrong: {error}</p>
      )}

      {/* 1. Weak match: the agent asks before writing a letter */}
      {step?.match && (
        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <p className="font-medium">{step.match}</p>
          {step.missing && step.missing.length > 0 && <p className="mt-1">Missing: {step.missing.join(', ')}</p>}
          <div className="mt-3 flex gap-2">
            <button onClick={() => answer('yes')} disabled={busy} className={mainBtn}>Write anyway</button>
            <button onClick={() => answer('no')} disabled={busy} className={softBtn}>Skip this job</button>
          </div>
        </div>
      )}

      {/* 2. Letter review: approve or ask for changes */}
      {step?.letter && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-500">AI draft. Review and edit before sending.</p>
            <button onClick={copy} className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900">
              {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}{copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          {step.warnings && step.warnings.length > 0 && (
            <ul className="mt-2 list-disc pl-4 text-xs text-amber-800">
              {step.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-800">{step.letter}</p>
          <div className="mt-3"><button onClick={() => answer('yes')} disabled={busy} className={mainBtn}>Approve letter</button></div>
          {changeBox}
        </div>
      )}

      {/* 3. Tailored CV review: approve the new profile or ask for changes */}
      {step?.summary && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
          <p className="text-xs font-medium text-slate-500">Tailored CV profile</p>
          {step.warnings && step.warnings.length > 0 && (
            <ul className="mt-2 list-disc pl-4 text-xs text-amber-800">
              {step.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-800">{step.summary}</p>
          {step.removed && step.removed.length > 0 && (
            <p className="mt-2 text-xs text-slate-500">{step.removed.length} less relevant items were left out of this CV.</p>
          )}
          <div className="mt-3"><button onClick={() => answer('yes')} disabled={busy} className={mainBtn}>Approve CV</button></div>
          {changeBox}
        </div>
      )}

      {/* 4. Delivery: only download works for now */}
      {step?.question && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
          <p className="text-xs font-medium text-slate-600">{step.question}</p>
          <div className="mt-3"><button onClick={() => answer('download')} disabled={busy} className={mainBtn}>Download</button></div>
        </div>
      )}

      {/* 5. Finished: links to the Word files (the student sends them, the agent never applies) */}
      {reply?.status === 'done' && (
        <div className="mt-3 rounded-xl border border-green-200 bg-green-50 p-3 text-xs text-green-900">
          {reply.has_letter || reply.has_cv ? (
            <div className="flex flex-wrap gap-3">
              {reply.has_letter && <a href={fileUrl('letter')} className="font-semibold underline">Download cover letter (.docx)</a>}
              {reply.has_cv && <a href={fileUrl('cv')} className="font-semibold underline">Download tailored CV (.docx)</a>}
            </div>
          ) : (
            <p>Skipped. No letter was written.</p>
          )}
        </div>
      )}
    </li>
  );
}

export default function CareerSkillGapCard({ matches, className }: { matches: InternshipMatch[]; className?: string }) {
  return (
    <section className={cn('rounded-2xl bg-white p-6 ring-1 ring-slate-900/5', className)} aria-label="Career skill gaps">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-orange-500" />
        <h2 className="font-display text-lg font-semibold text-slate-900">Internship matches</h2>
      </div>
      <p className="mt-0.5 text-xs text-slate-500">Skills you still need for your best-fit roles.</p>
      <ul className="mt-4 space-y-3">
        {[...matches].sort((a, b) => b.match - a.match).map((m) => <MatchCard key={m.id} m={m} />)}
      </ul>
    </section>
  );
}

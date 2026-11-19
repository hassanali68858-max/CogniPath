'use client';

import { useState } from 'react';
import { Check, Copy, Loader2, PenLine } from 'lucide-react';
import type { InternshipMatch } from '@/lib/cognipath/types';
import { cn } from '@/lib/cognipath/theme';

function MatchCard({ m }: { m: InternshipMatch }) {
  const [state, setState] = useState<'idle' | 'loading' | 'ready'>('idle');
  const [copied, setCopied] = useState(false);

  function draft() {
    setState('loading');
    // Replace with a call to the Career Agent's cover-letter endpoint.
    setTimeout(() => setState('ready'), 800);
  }
  async function copy() {
    try { await navigator.clipboard.writeText(m.coverLetter); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard unavailable */ }
  }

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

      <button onClick={draft} disabled={state === 'loading'}
        className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-orange-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-orange-600 disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500">
        {state === 'loading' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PenLine className="h-3.5 w-3.5" />}
        {state === 'loading' ? 'Drafting…' : state === 'ready' ? 'Redraft cover letter' : 'Draft cover letter'}
      </button>

      {state === 'ready' && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-500">AI draft. Review and edit before sending.</p>
            <button onClick={copy} className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900">
              {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}{copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-800">{m.coverLetter}</p>
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
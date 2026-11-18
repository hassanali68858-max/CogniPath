'use client';

import { useState } from 'react';
import { Check, ChevronDown, Loader2, Lock, RefreshCw, Undo2, X } from 'lucide-react';
import type { ActivityProposal, Decision, ScheduledItem } from '@/lib/cognipath/types';
import { CHANGE_TAG_STYLES, GOAL_STYLES, SOURCE_LABELS, cn, dominantGoal, fmtSlot } from '@/lib/cognipath/theme';

interface Props {
  items: ScheduledItem[];
  dropped: ActivityProposal[];
  dropReasons: Record<string, string>;
  decisions: Record<string, Decision>;
  onDecide: (id: string, decision: Decision) => void;
  onReplan: () => void;
  isReplanning?: boolean;
  className?: string;
}

const TAG_NOTE: Record<string, string> = {
  NEW: 'Added in the latest plan because a better slot opened up.',
  MOVED: 'Moved so your accepted items could stay where they are.',
};

function Actions({ id, decision, onDecide, label }: { id: string; decision: Decision; onDecide: Props['onDecide']; label: string }) {
  const btn = 'inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-900';
  return (
    <div className="flex items-center gap-1">
      <button type="button" aria-pressed={decision === 'accepted'} aria-label={`Accept ${label}`} title="Accept: keep this fixed when re-planning"
        onClick={() => onDecide(id, decision === 'accepted' ? 'pending' : 'accepted')}
        className={cn(btn, decision === 'accepted' ? 'bg-green-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-green-100 hover:text-green-700')}>
        <Check className="h-4 w-4" />
      </button>
      <button type="button" aria-pressed={decision === 'rejected'} aria-label={`Reject ${label}`} title="Reject: leave out of future plans"
        onClick={() => onDecide(id, decision === 'rejected' ? 'pending' : 'rejected')}
        className={cn(btn, decision === 'rejected' ? 'bg-red-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-red-100 hover:text-red-700')}>
        <X className="h-4 w-4" />
      </button>
      {decision !== 'pending' && (
        <button type="button" aria-label={`Undo decision on ${label}`} title="Undo" onClick={() => onDecide(id, 'pending')}
          className={cn(btn, 'text-slate-400 hover:bg-slate-100 hover:text-slate-700')}>
          <Undo2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function Row({ id, proposal, when, explanation, tag, decision, locked, onDecide }: {
  id: string; proposal: ActivityProposal; when?: string; explanation: string; tag?: string;
  decision: Decision; locked?: boolean; onDecide: Props['onDecide'];
}) {
  const [open, setOpen] = useState(false);
  const g = GOAL_STYLES[dominantGoal(proposal.value)];
  return (
    <li className="rounded-xl bg-white p-3 ring-1 ring-slate-900/5">
      <div className="flex items-center gap-3">
        <span className={cn('h-8 w-1 shrink-0 rounded-full', g.dot)} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className={cn('truncate text-sm font-semibold text-slate-900', decision === 'rejected' && 'line-through opacity-60')}>{proposal.title}</p>
            {tag && tag !== 'UNCHANGED' && (
              <span className={cn('shrink-0 rounded-full px-1.5 py-px text-[9px] font-bold', CHANGE_TAG_STYLES[tag as keyof typeof CHANGE_TAG_STYLES])}>{tag}</span>
            )}
          </div>
          <p className="text-xs tabular-nums text-slate-500">{when ?? 'Not scheduled'}</p>
        </div>
        {locked ? (
          <span className="inline-flex items-center gap-1 text-xs text-slate-400"><Lock className="h-3 w-3" />Fixed</span>
        ) : (
          <Actions id={id} decision={decision} onDecide={onDecide} label={proposal.title} />
        )}
      </div>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="mt-2 ml-4 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-900">
        Why is this here? <ChevronDown className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="mt-2 ml-4 rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-700">
          <p>{explanation}</p>
          <p className="mt-1.5 text-slate-500">Suggested by {SOURCE_LABELS[proposal.source_agent]}</p>
        </div>
      )}
    </li>
  );
}

export default function DecisionReviewPanel({ items, dropped, dropReasons, decisions, onDecide, onReplan, isReplanning, className }: Props) {
  const [tab, setTab] = useState<'planned' | 'left'>('planned');
  const [showFixed, setShowFixed] = useState(false);
  const accepted = Object.values(decisions).filter((d) => d === 'accepted').length;
  const rejected = Object.values(decisions).filter((d) => d === 'rejected').length;
  const sorted = [...items].sort((a, b) => a.assigned_start.localeCompare(b.assigned_start));
  const flexible = sorted.filter((i) => !i.proposal.hard);
  const fixed = sorted.filter((i) => i.proposal.hard);

  const explain = (it: ScheduledItem) => {
    const d = decisions[it.id] ?? 'pending';
    const note = d === 'rejected' ? 'You rejected this, so it will be left out of the next plan.'
      : d === 'accepted' ? 'You accepted this, so it stays at this time when you re-plan.'
      : it.change_tag ? TAG_NOTE[it.change_tag] : undefined;
    return note ? `${it.proposal.reason} ${note}` : it.proposal.reason;
  };

  const tabBtn = (id: 'planned' | 'left', label: string, n: number) => (
    <button role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
      className={cn('rounded-full px-3 py-1.5 text-sm font-medium transition-colors', tab === id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900')}>
      {label} <span className={tab === id ? 'text-slate-300' : 'text-slate-400'}>{n}</span>
    </button>
  );

  return (
    <aside aria-label="Review decisions" className={cn('flex flex-col rounded-2xl bg-slate-100/70 ring-1 ring-slate-900/5', className)}>
      <div className="px-5 pt-5">
        <h2 className="font-display text-lg font-semibold text-slate-900">Review your plan</h2>
        <p className="mt-0.5 text-sm text-slate-600">Accept what works, reject what does not, then re-plan.</p>
        <div role="tablist" className="mt-3 inline-flex rounded-full bg-white p-1 ring-1 ring-slate-900/5">
          {tabBtn('planned', 'Planned', flexible.length)}
          {tabBtn('left', 'Left out', dropped.length)}
        </div>
      </div>

      <div className="mt-4 flex-1 overflow-y-auto px-5 pb-4 lg:max-h-[440px]">
        {tab === 'planned' ? (
          <>
            <ul className="space-y-2">
              {flexible.map((it) => (
                <Row key={it.id} id={it.id} proposal={it.proposal} when={fmtSlot(it.assigned_start, it.assigned_end)}
                  explanation={explain(it)} tag={it.change_tag} decision={decisions[it.id] ?? 'pending'} onDecide={onDecide} />
              ))}
            </ul>
            {fixed.length > 0 && (
              <div className="mt-4">
                <button onClick={() => setShowFixed((s) => !s)} aria-expanded={showFixed}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-900">
                  <Lock className="h-3 w-3" /> Fixed commitments ({fixed.length})
                  <ChevronDown className={cn('h-3 w-3 transition-transform', showFixed && 'rotate-180')} />
                </button>
                {showFixed && (
                  <ul className="mt-2 space-y-2">
                    {fixed.map((it) => (
                      <Row key={it.id} id={it.id} proposal={it.proposal} when={fmtSlot(it.assigned_start, it.assigned_end)}
                        explanation={explain(it)} tag={it.change_tag} decision="pending" locked onDecide={onDecide} />
                    ))}
                  </ul>
                )}
              </div>
            )}
          </>
        ) : dropped.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500">Everything the agents suggested fits this week.</p>
        ) : (
          <ul className="space-y-2">
            {dropped.map((p) => (
              <Row key={p.proposal_id} id={p.proposal_id} proposal={p}
                explanation={dropReasons[p.proposal_id] ?? 'The planner could not fit this without breaking a higher-value item.'}
                decision={decisions[p.proposal_id] ?? 'pending'} onDecide={onDecide} />
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-b-2xl bg-white p-4 ring-1 ring-slate-900/5">
        <button type="button" onClick={onReplan} disabled={isReplanning}
          className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-slate-700 disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900">
          {isReplanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {isReplanning ? 'Re-planning…' : 'Re-plan schedule'}
        </button>
        <p className="mt-2 text-center text-xs text-slate-500">
          {accepted + rejected === 0 ? 'No decisions yet' : `${accepted} accepted, ${rejected} rejected`}
        </p>
      </div>
    </aside>
  );
}
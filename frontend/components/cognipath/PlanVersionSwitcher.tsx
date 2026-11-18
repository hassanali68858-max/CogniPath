'use client';

import type { GoalType, PlanVersion } from '@/lib/cognipath/types';
import { GOAL_STYLES, cn } from '@/lib/cognipath/theme';

const LABELS: Record<PlanVersion['version_type'], { label: string; blurb: string }> = {
  balanced: { label: 'Balanced', blurb: 'Keeps study, career and social time in proportion.' },
  study_first: { label: 'Study first', blurb: 'Protects course work and study deadlines first.' },
  career_first: { label: 'Career first', blurb: 'Prioritises skills and internship applications.' },
};

interface Props {
  versions: PlanVersion[];
  activeId: string;
  onChange: (id: string) => void;
}

export default function PlanVersionSwitcher({ versions, activeId, onChange }: Props) {
  const active = versions.find((v) => v.id === activeId) ?? versions[0];

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const next = (index + (e.key === 'ArrowRight' ? 1 : -1) + versions.length) % versions.length;
    onChange(versions[next].id);
    (e.currentTarget.parentElement?.children[next] as HTMLElement | undefined)?.focus();
  }

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <div role="tablist" aria-label="Plan versions" className="inline-flex rounded-full bg-slate-100 p-1">
        {versions.map((v, i) => {
          const selected = v.id === active.id;
          return (
            <button
              key={v.id}
              role="tab"
              id={`tab-${v.id}`}
              aria-selected={selected}
              aria-controls="plan-panel"
              tabIndex={selected ? 0 : -1}
              title={LABELS[v.version_type].blurb}
              onClick={() => onChange(v.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={cn(
                'rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-900',
                selected ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900',
              )}
            >
              {LABELS[v.version_type].label}
            </button>
          );
        })}
      </div>

      <div id="plan-panel" role="tabpanel" aria-labelledby={`tab-${active.id}`} className="flex items-center gap-4" aria-label="Goals kept in this plan">
        {(['study', 'career', 'social'] as GoalType[]).map((g) => {
          const pct = active.kept_percentages[g];
          return (
            <div key={g} className="flex items-center gap-2 text-sm">
              <span className="text-slate-600">{GOAL_STYLES[g].label}</span>
              <div className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${GOAL_STYLES[g].label} goals kept`}>
                <div className={cn('h-full rounded-full transition-[width] duration-500', GOAL_STYLES[g].bar)} style={{ width: `${pct}%` }} />
              </div>
              <span className="w-9 tabular-nums font-semibold text-slate-900">{pct}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
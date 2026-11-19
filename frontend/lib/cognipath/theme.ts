import type { ActivityProposal, AgentSource, ChangeTag, GoalType } from './types';

export const cn = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ');

export const GOAL_STYLES: Record<
  GoalType | 'neutral',
  { label: string; hex: string; card: string; bar: string; chip: string; dot: string; soft: string; softer: string }
> = {
  study: { label: 'Study', hex: '#3B82F6', card: 'bg-blue-50 border-blue-300 text-blue-950', bar: 'bg-blue-500', chip: 'bg-blue-100 text-blue-800', dot: 'bg-blue-500', soft: 'bg-blue-100 text-blue-950', softer: 'bg-blue-50 text-blue-900' },
  career: { label: 'Career', hex: '#F97316', card: 'bg-orange-50 border-orange-300 text-orange-950', bar: 'bg-orange-500', chip: 'bg-orange-100 text-orange-800', dot: 'bg-orange-500', soft: 'bg-orange-100 text-orange-950', softer: 'bg-orange-50 text-orange-900' },
  social: { label: 'Social', hex: '#22C55E', card: 'bg-green-50 border-green-300 text-green-950', bar: 'bg-green-500', chip: 'bg-green-100 text-green-800', dot: 'bg-green-500', soft: 'bg-green-100 text-green-950', softer: 'bg-green-50 text-green-900' },
  neutral: { label: 'Work & other', hex: '#64748B', card: 'bg-slate-100 border-slate-300 text-slate-800', bar: 'bg-slate-500', chip: 'bg-slate-200 text-slate-700', dot: 'bg-slate-500', soft: 'bg-slate-200 text-slate-800', softer: 'bg-slate-100 text-slate-700' },
};

export const CHANGE_TAG_STYLES: Partial<Record<ChangeTag, string>> = {
  NEW: 'bg-green-600 text-white',
  MOVED: 'bg-yellow-400 text-yellow-950',
  REJECTED: 'bg-red-600 text-white',
};

export const SOURCE_LABELS: Record<AgentSource, string> = {
  event: 'Event Agent',
  tutor: 'Tutor Agent',
  career: 'Career Agent',
  user: 'You',
};

export function dominantGoal(value: ActivityProposal['value']): GoalType | 'neutral' {
  const ranked = (Object.entries(value) as [GoalType, number | undefined][])
    .filter(([, v]) => (v ?? 0) > 0)
    .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0));
  return ranked[0]?.[0] ?? 'neutral';
}

/** Parse "2026-11-04T14:00" without timezone drift. */
export function parseISO(iso: string) {
  const [date, time] = iso.split('T');
  const [h, m] = time.split(':').map(Number);
  return { date, minutes: h * 60 + m };
}

export function addMinutes(iso: string, delta: number) {
  const { date, minutes } = parseISO(iso);
  const t = minutes + delta;
  const hh = String(Math.floor(t / 60)).padStart(2, '0');
  const mm = String(t % 60).padStart(2, '0');
  return `${date}T${hh}:${mm}`;
}

export function fmtSlot(start: string, end: string) {
  const s = parseISO(start);
  const [y, mo, d] = s.date.split('-').map(Number);
  const day = new Date(Date.UTC(y, mo - 1, d)).toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' });
  return `${day} ${start.split('T')[1]}–${end.split('T')[1]}`;
}
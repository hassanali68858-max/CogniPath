'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink, Lock, MapPin, Sparkles, X } from 'lucide-react';
import type { ScheduledItem } from '@/lib/cognipath/types';
import { CHANGE_TAG_STYLES, GOAL_STYLES, SOURCE_LABELS, cn, dominantGoal, fmtSlot, parseISO } from '@/lib/cognipath/theme';

const START_MIN = 8 * 60;
const END_MIN = 22 * 60;
const SLOT_MIN = 30;
const SLOT_PX = 32;
const SLOTS = (END_MIN - START_MIN) / SLOT_MIN;
const GRID_H = SLOTS * SLOT_PX;

interface Props {
  items: ScheduledItem[];
  weekStart: string; // Monday, "YYYY-MM-DD"
  today?: string;
  now?: string; // "YYYY-MM-DDTHH:mm", draws the current-time line
  className?: string;
}

function weekDays(start: string) {
  const [y, m, d] = start.split('-').map(Number);
  return Array.from({ length: 7 }, (_, i) => {
    const dt = new Date(Date.UTC(y, m - 1, d + i));
    return {
      iso: dt.toISOString().slice(0, 10),
      label: dt.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' }),
      day: dt.getUTCDate(),
    };
  });
}

interface Placed { item: ScheduledItem; top: number; height: number; lane: number; lanes: number }

function layoutDay(items: ScheduledItem[]): Placed[] {
  const sorted = [...items].sort((a, b) => parseISO(a.assigned_start).minutes - parseISO(b.assigned_start).minutes);
  const out: Placed[] = [];
  let cluster: Placed[] = [];
  let laneEnds: number[] = [];
  let clusterEnd = -1;
  const flush = () => {
    cluster.forEach((p) => (p.lanes = laneEnds.length));
    out.push(...cluster);
    cluster = [];
    laneEnds = [];
  };
  for (const item of sorted) {
    const s = Math.max(parseISO(item.assigned_start).minutes, START_MIN);
    const e = Math.min(parseISO(item.assigned_end).minutes, END_MIN);
    if (e <= s) continue;
    if (s >= clusterEnd && cluster.length) flush();
    let lane = laneEnds.findIndex((end) => end <= s);
    if (lane === -1) { lane = laneEnds.length; laneEnds.push(e); } else laneEnds[lane] = e;
    clusterEnd = Math.max(clusterEnd, e);
    cluster.push({
      item, lane, lanes: 1,
      top: ((s - START_MIN) / SLOT_MIN) * SLOT_PX,
      height: Math.max(((e - s) / SLOT_MIN) * SLOT_PX - 3, 22),
    });
  }
  flush();
  return out;
}

export default function WeeklyCalendarGrid({ items, weekStart, today, now, className }: Props) {
  const days = useMemo(() => weekDays(weekStart), [weekStart]);
  const byDay = useMemo(
    () => days.map((d) => layoutDay(items.filter((i) => parseISO(i.assigned_start).date === d.iso))),
    [days, items],
  );
  const nowInfo = now ? parseISO(now) : null;

  const outerRef = useRef<HTMLDivElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState<{ item: ScheduledItem; left: number; top: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (popRef.current?.contains(t) || t.closest('[data-item-card]')) return;
      setOpen(null);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(null);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  function openItem(item: ScheduledItem, el: HTMLElement) {
    const outer = outerRef.current!.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    const W = 340;
    let left = r.right - outer.left + 8;
    if (left + W > outer.width) left = Math.max(8, r.left - outer.left - W - 8);
    const top = Math.min(Math.max(r.top - outer.top, 72), Math.max(72, outer.height - 320));
    setOpen({ item, left, top });
  }

  const hours = Array.from({ length: SLOTS }, (_, i) => START_MIN + i * SLOT_MIN);

  return (
    <section aria-label="Weekly calendar" className={cn('overflow-hidden rounded-2xl bg-white ring-1 ring-slate-900/5', className)}>
      <div ref={outerRef} className="relative">
        <div className="max-h-[680px] overflow-auto">
          <div className="grid min-w-[880px]" style={{ gridTemplateColumns: '56px repeat(7, minmax(112px, 1fr))' }}>
            <div className="sticky top-0 z-20 bg-white/95 backdrop-blur" />
            {days.map((d) => {
              const isToday = d.iso === today;
              return (
                <div key={d.iso} className="sticky top-0 z-20 flex flex-col items-center gap-0.5 bg-white/95 py-2.5 backdrop-blur">
                  <span className={cn('text-xs font-medium', isToday ? 'text-slate-900' : 'text-slate-500')}>{d.label}</span>
                  <span className={cn('flex h-8 w-8 items-center justify-center rounded-full font-display text-base font-semibold tabular-nums', isToday ? 'bg-slate-900 text-white' : 'text-slate-800')}>
                    {d.day}
                  </span>
                </div>
              );
            })}

            <div className="relative" style={{ height: GRID_H }}>
              {hours.map((m, i) =>
                m % 60 === 0 && i > 0 ? (
                  <span key={m} className="absolute right-2 -translate-y-1/2 text-[11px] tabular-nums text-slate-400" style={{ top: i * SLOT_PX }}>
                    {String(m / 60).padStart(2, '0')}:00
                  </span>
                ) : null,
              )}
            </div>

            {days.map((d, di) => (
              <div key={d.iso} className={cn('relative', d.iso === today && 'bg-slate-50/70')} style={{ height: GRID_H }}>
                {hours.map((m, i) =>
                  m % 60 === 0 ? <div key={m} className="absolute inset-x-0 border-t border-slate-100" style={{ top: i * SLOT_PX }} /> : null,
                )}
                <div className="absolute inset-y-0 left-0 border-l border-slate-100" />

                {nowInfo && nowInfo.date === d.iso && nowInfo.minutes >= START_MIN && nowInfo.minutes <= END_MIN && (
                  <div aria-hidden className="pointer-events-none absolute inset-x-0 z-10 flex items-center" style={{ top: ((nowInfo.minutes - START_MIN) / SLOT_MIN) * SLOT_PX }}>
                    <span className="-ml-1 h-2 w-2 rounded-full bg-rose-500" />
                    <span className="h-px flex-1 bg-rose-500" />
                  </div>
                )}

                {byDay[di].map(({ item, top, height, lane, lanes }) => {
                  const g = GOAL_STYLES[dominantGoal(item.proposal.value)];
                  const isFixed = !!item.proposal.fixed_time;
                  const rejected = item.status === 'rejected' || item.change_tag === 'REJECTED';
                  const tag = item.change_tag && item.change_tag !== 'UNCHANGED' ? item.change_tag : undefined;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      data-item-card
                      onClick={(e) => openItem(item, e.currentTarget)}
                      aria-label={`${item.proposal.title}, ${fmtSlot(item.assigned_start, item.assigned_end)}`}
                      className={cn(
                        'absolute overflow-hidden rounded-lg border-l-[3px] px-2 py-1 text-left text-xs leading-tight transition-shadow hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-slate-900',
                        isFixed ? g.softer : g.soft,
                        rejected && 'opacity-50',
                      )}
                      style={{
                        top: top + 1,
                        height,
                        left: `calc(${(lane / lanes) * 100}% + 3px)`,
                        width: `calc(${100 / lanes}% - 6px)`,
                        borderLeftColor: g.hex,
                      }}
                    >
                      <span className="flex items-start gap-1 pr-10">
                        {isFixed ? <Lock className="mt-px h-3 w-3 shrink-0 opacity-50" aria-hidden /> : <Sparkles className="mt-px h-3 w-3 shrink-0 opacity-50" aria-hidden />}
                        <span className={cn('font-semibold', rejected && 'line-through')}>{item.proposal.title}</span>
                      </span>
                      {height >= 50 && (
                        <span className="mt-0.5 block tabular-nums opacity-70">
                          {item.assigned_start.split('T')[1]}–{item.assigned_end.split('T')[1]}
                        </span>
                      )}
                      {tag && (
                        <span className={cn('absolute right-1 top-1 rounded-full px-1.5 py-px text-[9px] font-bold', CHANGE_TAG_STYLES[tag])}>
                          {tag}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        {open && (
          <div
            ref={popRef}
            role="dialog"
            aria-label={open.item.proposal.title}
            className="absolute z-30 w-[340px] rounded-2xl bg-white p-5 shadow-2xl ring-1 ring-slate-900/10"
            style={{ left: open.left, top: open.top }}
          >
            <button onClick={() => setOpen(null)} className="absolute right-3 top-3 rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close details">
              <X className="h-4 w-4" />
            </button>
            {(() => {
              const p = open.item.proposal;
              const g = GOAL_STYLES[dominantGoal(p.value)];
              const tag = open.item.change_tag && open.item.change_tag !== 'UNCHANGED' ? open.item.change_tag : undefined;
              return (
                <>
                  <div className="flex items-center gap-2 pr-6">
                    <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', g.dot)} />
                    <h3 className="font-display text-base font-semibold text-slate-900">{p.title}</h3>
                    {tag && <span className={cn('rounded-full px-1.5 py-px text-[10px] font-bold', CHANGE_TAG_STYLES[tag])}>{tag}</span>}
                  </div>
                  <p className="mt-1 text-xs tabular-nums text-slate-500">{fmtSlot(open.item.assigned_start, open.item.assigned_end)}</p>
                  <p className="mt-3 text-sm leading-relaxed text-slate-700">{p.reason}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">Suggested by {SOURCE_LABELS[p.source_agent]}</span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-700">{p.fixed_time ? 'Fixed time' : 'Can be moved'}</span>
                    {p.location && <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-slate-700"><MapPin className="h-3 w-3" />{p.location}</span>}
                  </div>
                  {p.resource_url && (
                    <a href={p.resource_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-blue-700 hover:underline">
                      Open resource <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </>
              );
            })()}
          </div>
        )}
      </div>
    </section>
  );
}

"use client";

import { addDays, datePart, minutesOfDay, timePart, weekday } from "@/lib/format";
import type { BusyBlock, PlanItem } from "@/lib/types";

const PX_PER_MIN = 0.78;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type Props = {
  horizonStart: string; // YYYY-MM-DD
  days: number;
  week: number; // 0-based
  items: PlanItem[];
  busy: BusyBlock[];
  fromHour: number;
  toHour: number;
  selected?: string | null;
  tags?: Record<string, "NEW" | "MOVED">;
  onSelect?: (itemId: string) => void;
};

type Block = {
  key: string;
  day: number;
  start: string;
  end: string;
  label: string;
  cls: string;
  itemId?: string;
  tag?: string;
};

/** One week: days as columns, hours as rows; plan sessions and busy time as blocks. */
export function WeekCalendar({ horizonStart, days, week, items, busy, fromHour, toHour, selected, tags, onSelect }: Props) {
  const firstMin = fromHour * 60;
  const height = (toHour - fromHour) * 60 * PX_PER_MIN;
  const dayIndex = (iso: string) => Math.round((Date.parse(datePart(iso)) - Date.parse(horizonStart)) / 86400000);

  const blocks: Block[] = [
    ...busy.map((b) => ({
      key: `busy-${b.start}-${b.title}`,
      day: dayIndex(b.start),
      start: b.start,
      end: b.end,
      label: b.title,
      cls: "busy",
    })),
    ...items.flatMap((it) =>
      it.sessions.map((s, i) => ({
        key: `${it.item_id}-${i}`,
        day: dayIndex(s.start),
        start: s.start,
        end: s.end,
        label: it.title,
        cls: `${it.source_agents[0] ?? "user"} ${it.decision}${selected === it.item_id ? " selected" : ""}`,
        itemId: it.item_id,
        tag: tags?.[it.proposal_id],
      })),
    ),
  ];

  const hours = Array.from({ length: toHour - fromHour + 1 }, (_, i) => fromHour + i);
  const first = week * 7;

  return (
    <div className="cal-scroll">
      <div className="cal">
        <div className="cal-head" style={{ borderLeft: "none" }} />
        {Array.from({ length: 7 }, (_, d) => {
          const day = addDays(horizonStart, first + d);
          const wd = weekday(day);
          return (
            <div className={`cal-head${wd >= 5 ? " weekend" : ""}`} key={d}>
              <span>{WEEKDAYS[wd]}</span>
              <b>{Number(day.slice(8, 10))}</b>
            </div>
          );
        })}
        <div className="cal-hours" style={{ height }}>
          {hours.map((h) => (
            <span key={h} style={{ top: (h - fromHour) * 60 * PX_PER_MIN }}>
              {String(h).padStart(2, "0")}:00
            </span>
          ))}
        </div>
        {Array.from({ length: 7 }, (_, d) => {
          const idx = first + d;
          const wd = weekday(addDays(horizonStart, idx));
          return (
            <div
              key={d}
              className={`cal-day${idx >= days ? " outside" : ""}${wd >= 5 ? " weekend" : ""}`}
              style={{ height, backgroundSize: `100% ${60 * PX_PER_MIN}px` }}
            >
              {blocks
                .filter((b) => b.day === idx)
                .map((b) => {
                  const top = Math.max(0, (minutesOfDay(b.start) - firstMin) * PX_PER_MIN);
                  const bottom = Math.min(height, (minutesOfDay(b.end) - firstMin) * PX_PER_MIN);
                  const short = bottom - top < 34;
                  return (
                    <div
                      key={b.key}
                      className={`block ${b.cls}`}
                      style={{ top, height: Math.max(16, bottom - top - 2) }}
                      title={`${timePart(b.start)}–${timePart(b.end)} · ${b.label}`}
                      onClick={() => b.itemId && onSelect?.(b.itemId)}
                    >
                      {b.tag && <span className="tag">{b.tag}</span>}
                      <b>{b.label}</b>
                      {!short && (
                        <span className="t">
                          {timePart(b.start)}–{timePart(b.end)}
                        </span>
                      )}
                    </div>
                  );
                })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

"use client";

import { addDays, dayLabel, datePart, minutesOfDay, timePart } from "@/lib/format";
import type { BusyBlock, PlanItem } from "@/lib/types";

const PX_PER_MIN = 0.7;

type Props = {
  horizonStart: string; // YYYY-MM-DD
  days: number;
  items: PlanItem[];
  busy: BusyBlock[];
  fromHour: number;
  toHour: number;
  selected?: string | null;
  onSelect?: (itemId: string) => void;
};

type Block = { key: string; day: number; start: string; end: string; label: string; cls: string; itemId?: string };

/** One grid per week: days as columns, hours as rows, plan sessions and busy time as blocks. */
export function WeekCalendar({ horizonStart, days, items, busy, fromHour, toHour, selected, onSelect }: Props) {
  const firstMin = fromHour * 60;
  const height = (toHour - fromHour) * 60 * PX_PER_MIN;
  const dayIndex = (iso: string) => Math.round((Date.parse(datePart(iso)) - Date.parse(horizonStart)) / 86400000);

  const blocks: Block[] = [];
  for (const b of busy) {
    blocks.push({ key: `busy-${b.start}`, day: dayIndex(b.start), start: b.start, end: b.end, label: b.title, cls: "busy" });
  }
  for (const it of items) {
    it.sessions.forEach((s, i) =>
      blocks.push({
        key: `${it.item_id}-${i}`,
        day: dayIndex(s.start),
        start: s.start,
        end: s.end,
        label: it.title,
        cls: `${it.source_agents[0] ?? "user"} ${it.decision}${selected === it.item_id ? " selected" : ""}`,
        itemId: it.item_id,
      }),
    );
  }

  const weeks = Math.ceil(days / 7);
  const hours = Array.from({ length: toHour - fromHour + 1 }, (_, i) => fromHour + i);

  return (
    <div className="cal-scroll">
      {Array.from({ length: weeks }, (_, w) => (
        <div className="cal" key={w}>
          <div className="cal-head" style={{ borderLeft: "none" }} />
          {Array.from({ length: 7 }, (_, d) => (
            <div className="cal-head" key={d}>
              {w * 7 + d < days ? dayLabel(addDays(horizonStart, w * 7 + d)) : ""}
            </div>
          ))}
          <div className="cal-hours" style={{ height }}>
            {hours.map((h) => (
              <span key={h} style={{ top: (h - fromHour) * 60 * PX_PER_MIN }}>
                {String(h).padStart(2, "0")}
              </span>
            ))}
          </div>
          {Array.from({ length: 7 }, (_, d) => {
            const day = w * 7 + d;
            return (
              <div
                key={d}
                className={`cal-day${day >= days ? " outside" : ""}`}
                style={{ height, backgroundSize: `100% ${60 * PX_PER_MIN}px` }}
              >
                {blocks
                  .filter((b) => b.day === day)
                  .map((b) => {
                    const top = Math.max(0, (minutesOfDay(b.start) - firstMin) * PX_PER_MIN);
                    const bottom = Math.min(height, (minutesOfDay(b.end) - firstMin) * PX_PER_MIN);
                    return (
                      <div
                        key={b.key}
                        className={`block ${b.cls}`}
                        style={{ top, height: Math.max(14, bottom - top) }}
                        title={`${timePart(b.start)}–${timePart(b.end)} ${b.label}`}
                        onClick={() => b.itemId && onSelect?.(b.itemId)}
                      >
                        <b>{timePart(b.start)}</b> {b.label}
                      </div>
                    );
                  })}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

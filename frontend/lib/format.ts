// Date helpers. The backend sends naive local times like "2026-11-04T12:00:00",
// so we read them as text instead of letting the browser shift time zones.

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export const datePart = (iso: string) => iso.slice(0, 10);
export const timePart = (iso: string) => iso.slice(11, 16);

export function minutesOfDay(iso: string): number {
  return Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16));
}

function utc(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

/** 0 = Monday ... 6 = Sunday */
export function weekday(day: string): number {
  return (utc(day).getUTCDay() + 6) % 7;
}

export function addDays(day: string, n: number): string {
  const d = utc(day);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function dayLabel(day: string): string {
  const d = utc(day);
  return `${DAYS[weekday(day)]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

export function rangeLabel(start: string, end: string): string {
  return `${dayLabel(datePart(start))} ${timePart(start)}–${timePart(end)}`;
}

export function minutesLabel(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h ? (m ? `${h} h ${m} min` : `${h} h`) : `${m} min`;
}

export function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "item";
}

"use client";

export type Msg = { kind: "ok" | "error"; text: string } | null;

export function Message({ msg }: { msg: Msg }) {
  if (!msg) return null;
  return <div className={`msg ${msg.kind}`}>{msg.text}</div>;
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

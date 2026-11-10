import { AGENTS } from "@/lib/meta";
import type { SourceAgent } from "@/lib/types";

export function AgentBadge({ agent, compact = false }: { agent: string; compact?: boolean }) {
  const meta = AGENTS[agent as SourceAgent] ?? AGENTS.user;
  const Icon = meta.icon;
  return (
    <span className={`agent-badge ${agent}`} title={meta.label}>
      <Icon size={12} />
      {!compact && meta.short}
    </span>
  );
}

export function AgentAvatar({ agent, size = 36 }: { agent: string; size?: number }) {
  const meta = AGENTS[agent as SourceAgent] ?? AGENTS.user;
  const Icon = meta.icon;
  return (
    <span className={`agent-avatar ${agent}`} style={{ width: size, height: size }}>
      <Icon size={size * 0.5} />
    </span>
  );
}

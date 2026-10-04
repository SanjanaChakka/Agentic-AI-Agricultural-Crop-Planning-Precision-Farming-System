import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import { humaniseToken } from '../../lib/format';

export type BadgeTone =
  | 'neutral'
  | 'brand'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'violet'
  | 'slate';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-slate-100 text-slate-700 ring-slate-200',
  brand: 'bg-brand-50 text-brand-800 ring-brand-200',
  success: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  warning: 'bg-amber-50 text-amber-800 ring-amber-200',
  danger: 'bg-rose-50 text-rose-800 ring-rose-200',
  info: 'bg-sky-50 text-sky-800 ring-sky-200',
  violet: 'bg-violet-50 text-violet-800 ring-violet-200',
  slate: 'bg-slate-800 text-slate-100 ring-slate-700',
};

export interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  title?: string;
  className?: string;
  /** Adds a leading status dot. */
  dot?: boolean;
}

export function Badge({ children, tone = 'neutral', title, className, dot = false }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5',
        'text-[11px] font-medium ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Domain tone helpers                                                 */
/* ------------------------------------------------------------------ */

const STATUS_TONES: Record<string, BadgeTone> = {
  // workflow runs
  pending: 'warning',
  running: 'info',
  in_progress: 'info',
  queued: 'info',
  completed: 'success',
  completed_with_warnings: 'warning',
  failed: 'danger',
  error: 'danger',
  awaiting_human_review: 'warning',
  // approvals
  approved: 'success',
  rejected: 'danger',
  modified: 'violet',
  // activities
  planned: 'neutral',
  scheduled: 'info',
  cancelled: 'slate',
  // alerts
  open: 'danger',
  acknowledged: 'warning',
  resolved: 'success',
  // reports
  ready: 'success',
  generating: 'info',
  // sensors / generic
  ok: 'success',
  up: 'success',
  warning: 'warning',
  degraded: 'warning',
  fallback: 'warning',
  down: 'danger',
  deterministic: 'violet',
  simulated: 'violet',
};

export const toneForStatus = (status: string | null | undefined): BadgeTone =>
  STATUS_TONES[(status ?? '').toLowerCase()] ?? 'neutral';

/** Severity bands, ordered low -> critical. */
const SEVERITY_TONES: Record<string, BadgeTone> = {
  none: 'neutral',
  none_expected: 'neutral',
  low: 'info',
  moderate: 'warning',
  medium: 'warning',
  high: 'danger',
  critical: 'danger',
  severe: 'danger',
};

export const toneForSeverity = (severity: string | null | undefined): BadgeTone =>
  SEVERITY_TONES[(severity ?? '').toLowerCase()] ?? 'neutral';

/** Verdict bands used by suitability factor scores. */
const VERDICT_TONES: Record<string, BadgeTone> = {
  favourable: 'success',
  favorable: 'success',
  unfavourable: 'danger',
  unfavorable: 'danger',
  unknown: 'neutral',
};

export const toneForVerdict = (verdict: string | null | undefined): BadgeTone =>
  VERDICT_TONES[(verdict ?? '').toLowerCase()] ?? 'neutral';

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <Badge tone="neutral">Unknown</Badge>;
  return (
    <Badge tone={toneForStatus(status)} dot>
      {humaniseToken(status)}
    </Badge>
  );
}

export default Badge;
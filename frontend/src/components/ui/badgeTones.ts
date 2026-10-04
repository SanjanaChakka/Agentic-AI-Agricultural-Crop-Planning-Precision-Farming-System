import type { BadgeTone } from './Badge';

/**
 * Domain tone mappings for badges.
 *
 * These live apart from `Badge.tsx` so that file only exports components, which
 * keeps React Fast Refresh working in development. They are presentation-only:
 * an unmapped value degrades to `neutral` rather than throwing.
 */

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
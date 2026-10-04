import { containsDiagnosisLanguage } from '../../api/risk';
import { humaniseToken } from '../../lib/format';
import { toneForSeverity } from './badgeTones';
import type { BadgeTone } from './Badge';

/**
 * Presentation rules for environmental-risk severity.
 *
 * Kept apart from `RiskBadge.tsx` so that file only exports a component, which
 * keeps React Fast Refresh working in development.
 *
 * Two hard rules live here:
 *  1. Severity is rendered, never a diagnostic claim. "High" means the
 *     environmental conditions are unfavourable, not that anything is confirmed,
 *     present or identified.
 *  2. Any incoming string that would smuggle diagnosis language onto the screen
 *     is replaced with `Unrated`. This is enforced in code, not by convention, so
 *     a backend regression cannot leak diagnosis wording into the UI.
 */

const FORBIDDEN_OUTPUT = /confirm|diagnos|detect|present|positiv|identif|infect/i;

/** Severity bands that carry an explicit "environmental conditions" frame. */
const SEVERITY_LABEL: Record<string, string> = {
  none: 'None expected',
  none_expected: 'None expected',
  low: 'Low',
  moderate: 'Moderate',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
  severe: 'Severe',
};

const SEVERITY_TONE: Record<string, BadgeTone> = {
  none: 'neutral',
  none_expected: 'neutral',
  low: 'info',
  moderate: 'warning',
  medium: 'warning',
  high: 'danger',
  critical: 'danger',
  severe: 'danger',
};

/** Safe severity text. Never contains diagnosis language. */
export function safeSeverityLabel(severity: string | null | undefined): string {
  if (!severity) return 'Unrated';
  const key = severity.trim().toLowerCase();
  const label = SEVERITY_LABEL[key];
  if (label) return label;
  if (FORBIDDEN_OUTPUT.test(key) || containsDiagnosisLanguage(key)) return 'Unrated';
  return humaniseToken(key, 'Unrated');
}

export function safeSeverityTone(severity: string | null | undefined): BadgeTone {
  const key = (severity ?? '').trim().toLowerCase();
  return SEVERITY_TONE[key] ?? toneForSeverity(key);
}
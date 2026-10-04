import { ShieldAlert } from 'lucide-react';
import { Badge, toneForSeverity, type BadgeTone } from './Badge';
import { humaniseToken } from '../../lib/format';
import { containsDiagnosisLanguage } from '../../api/risk';

/**
 * Severity badge for environmental risk findings.
 *
 * Two hard rules:
 *  1. It renders *severity*, never a diagnostic claim. "High" means the
 *     environmental conditions are unfavourable, not that anything is
 *     confirmed, present or identified.
 *  2. Any incoming string that would smuggle diagnosis language onto the screen
 *     is replaced with `unrated`. This is enforced here, not just by convention,
 *     so a backend regression cannot leak diagnosis wording into the UI.
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

export interface RiskBadgeProps {
  severity: string | null | undefined;
  /** Rendered as an accessible suffix, e.g. "conditions severity". */
  qualifier?: string;
  className?: string;
}

export function RiskBadge({ severity, qualifier = 'conditions severity', className }: RiskBadgeProps) {
  const label = safeSeverityLabel(severity);
  const tone = safeSeverityTone(severity);
  return (
    <Badge
      tone={tone}
      className={className}
      title={`Environmental ${qualifier}. This system does not diagnose crop conditions.`}
      data-testid="risk-badge"
    >
      <ShieldAlert className="h-3 w-3" aria-hidden="true" />
      {label} {qualifier}
    </Badge>
  );
}

export default RiskBadge;
import { ShieldAlert } from 'lucide-react';
import { Badge } from './Badge';
import { safeSeverityLabel, safeSeverityTone } from './severityPresentation';

/**
 * Severity badge for environmental risk findings.
 *
 * Renders *severity*, never a diagnostic claim: "High" means the environmental
 * conditions are unfavourable, not that anything is confirmed or identified.
 * The wording rules themselves live in `severityPresentation.ts`.
 */
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
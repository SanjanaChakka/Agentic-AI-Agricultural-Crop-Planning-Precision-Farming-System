import { Badge } from './Badge';
import { evidenceKindMeta } from './evidenceKindMeta';

export interface EvidenceKindBadgeProps {
  kind: string;
  className?: string;
  /** Append the raw enum value, e.g. `retrieved_reference`. */
  showRaw?: boolean;
}

/**
 * Renders a provenance tag. Every value in `SourceKind` is supported; an
 * unrecognised value degrades to a neutral badge rather than rendering blank.
 */
export function EvidenceKindBadge({ kind, className, showRaw = false }: EvidenceKindBadgeProps) {
  const meta = evidenceKindMeta(kind);
  const { Icon } = meta;
  return (
    <Badge tone={meta.tone} title={`${meta.description} (kind: ${kind})`} className={className}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {meta.label}
      {showRaw ? <span className="font-mono opacity-70">({kind})</span> : null}
    </Badge>
  );
}

export default EvidenceKindBadge;
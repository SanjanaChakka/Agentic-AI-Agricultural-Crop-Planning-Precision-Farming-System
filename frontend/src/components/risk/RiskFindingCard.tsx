import { FlaskConical, Info, Microscope, Search } from 'lucide-react';
import type { RiskFinding } from '../../api/types';
import { safeStatement } from '../../api/risk';
import { RiskBadge } from '../ui/RiskBadge';
import { EvidenceKindBadge } from '../ui/EvidenceKindBadge';
import { CardHeader } from '../ui/Card';
import { formatDateTime, formatNumber, humaniseToken } from '../../lib/format';

export interface RiskFindingCardProps {
  finding: RiskFinding;
  /** Optional ML severity cross-check rendered alongside the finding. */
  mlCrossCheck?: { label: string; value: string; confidence?: number | null } | null;
}

/**
 * Renders one environmental risk finding.
 *
 * Wording contract (enforced, not just documented):
 *  - the backend statement is rendered VERBATIM - it is phrased
 *    "Environmental conditions favourable for X";
 *  - a defensive check downgrades any statement that has regressed into
 *    diagnosis language into a neutral environmental restatement;
 *  - the severity badge can never render "confirmed" or similar.
 */
export function RiskFindingCard({ finding, mlCrossCheck }: RiskFindingCardProps) {
  const statement = safeStatement(finding);

  return (
    <article
      className="card-surface overflow-hidden"
      data-testid="risk-finding"
      data-risk-type={finding.risk_type}
    >
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span>{humaniseToken(finding.risk_type)}</span>
            <RiskBadge severity={finding.severity} />
          </span>
        }
        subtitle={`Observed ${formatDateTime(finding.observed_at)}`}
        actions={
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
            <Microscope className="h-3.5 w-3.5" aria-hidden="true" />
            Environmental observation
          </span>
        }
      />

      <div className="space-y-4 p-5">
        {/*
          Rendered verbatim. The wording is the backend's guarantee that this is a
          statement about environment, not a diagnosis.
        */}
        <blockquote
          className="rounded-lg border-l-4 border-brand-500 bg-brand-50/60 px-4 py-3 text-sm leading-relaxed text-slate-800"
          data-testid="risk-statement"
        >
          {statement}
        </blockquote>

        <p className="flex items-start gap-2 text-xs text-slate-500">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>
            This system has no diagnostic capability. It reports conditions that are{' '}
            <strong className="font-medium text-slate-700">favourable</strong> for a condition
            <span className="text-slate-400">
              {' '}
              (is_diagnosis: {String(finding.is_diagnosis)})
            </span>
            . Field scouting is required to confirm or rule it out.
          </span>
        </p>

        <div className="grid gap-4 sm:grid-cols-2">
          {finding.potential_impact ? (
            <div>
              <p className="label-caps">Potential impact</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                {finding.potential_impact}
              </p>
            </div>
          ) : null}
          {finding.recommended_investigation ? (
            <div>
              <p className="label-caps">Recommended investigation</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                {finding.recommended_investigation}
              </p>
            </div>
          ) : null}
        </div>

        {mlCrossCheck ? (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="label-caps flex items-center gap-1.5">
              <Search className="h-3.5 w-3.5" aria-hidden="true" />
              ML severity cross-check
            </p>
            <p className="mt-1 text-xs text-slate-700">
              <span className="font-medium">{mlCrossCheck.label}</span>:{' '}
              {mlCrossCheck.value}
              {mlCrossCheck.confidence !== null && mlCrossCheck.confidence !== undefined
                ? ` (confidence ${formatNumber(mlCrossCheck.confidence, 2)})`
                : ''}
            </p>
            <p className="mt-1 text-[11px] text-slate-500">
              The model grades environmental severity. It does not identify a pathogen, pest or
              disorder, and it does not agree or disagree with the findings above beyond severity.
            </p>
          </div>
        ) : null}

        {finding.evidence.length > 0 ? (
          <div>
            <p className="label-caps mb-2">Evidence ({finding.evidence.length})</p>
            <ul className="space-y-2">
              {finding.evidence.map((item, index) => (
                <li key={`${item.label}-${index}`} className="flex flex-wrap items-start gap-2">
                  <EvidenceKindBadge kind={item.kind} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-slate-700">{item.label}</p>
                    <p className="tabular text-xs text-slate-600">
                      {item.value === null || item.value === undefined ? '-' : String(item.value)}
                      {item.unit ? ` ${item.unit}` : ''}
                      {item.note ? <span className="ml-1 text-slate-400">({item.note})</span> : null}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {finding.evidence.some((item) => item.kind === 'simulated') ? (
          <p className="flex items-center gap-1.5 text-[11px] font-medium text-amber-800">
            <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
            Some evidence in this finding is simulated, not measured.
          </p>
        ) : null}
      </div>
    </article>
  );
}

export default RiskFindingCard;
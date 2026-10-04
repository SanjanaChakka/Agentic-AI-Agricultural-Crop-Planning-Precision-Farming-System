import { useState } from 'react';
import { Cpu, Info, Microscope, RefreshCw, ScanSearch, ShieldQuestion } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { TextInput } from '../components/ui/Field';
import { SkeletonBlock, SkeletonTable } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';
import { RiskBadge } from '../components/ui/RiskBadge';
import { RiskFindingCard } from '../components/risk/RiskFindingCard';
import { FieldGate } from '../components/layout/FieldGate';
import {
  findMoisturePrediction,
  findSeverityPrediction,
  useFieldPredictions,
  useFieldRisk,
  useRiskDisclaimer,
  useRiskHistory,
} from '../hooks/useRisk';
import { useSelection } from '../context/SelectionContext';
import type { MLPrediction, RiskFinding } from '../api/types';
import { formatDateTime, formatNumber, humaniseToken } from '../lib/format';

/**
 * Crop Risk.
 *
 * GET /risk/fields/{id}?crop= · GET /risk/fields/{id}/history ·
 * GET /risk/disclaimer · GET /ml/fields/{id}/predictions
 *
 * WORDING CONTRACT, enforced in code by `RiskFindingCard` and `RiskBadge`:
 *  - backend statements are rendered verbatim, phrased "Environmental conditions
 *    favourable for X";
 *  - the words "confirmed"/"diagnosed"/"detected" never appear as an output of
 *    this page - any incoming value that tries to assert a diagnosis is
 *    replaced with a neutral environmental restatement;
 *  - the non-diagnostic disclaimer is rendered above the findings, always.
 */
export function CropRiskPage() {
  const { fieldId } = useSelection();
  const [crop, setCrop] = useState('');
  const activeCrop = crop.trim() || undefined;

  const risk = useFieldRisk(fieldId, activeCrop);
  const history = useRiskHistory(fieldId);
  const disclaimer = useRiskDisclaimer();
  const predictions = useFieldPredictions(fieldId);

  const severityPrediction = findSeverityPrediction(predictions.data ?? []);
  const moisturePrediction = findMoisturePrediction(predictions.data ?? []);

  const mlCrossCheck = severityPrediction
    ? {
        label: `${severityPrediction.model_name} (${severityPrediction.task})`,
        value: severityPrediction.prediction_label ?? formatNumber(severityPrediction.prediction_value, 2),
        confidence: severityPrediction.confidence,
      }
    : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Crop Risk"
        description="Environmental favourability for specific crop stresses. This page reports conditions; it never identifies a disease, pest or disorder."
        actions={
          <>
            <div className="flex items-center gap-2">
              <label htmlFor="risk-crop" className="label-caps">
                Crop
              </label>
              <TextInput
                id="risk-crop"
                className="h-8 w-40 py-1 text-xs"
                value={crop}
                placeholder="use field crop"
                onChange={(event) => setCrop(event.target.value)}
              />
            </div>
            <Button
              variant="secondary"
              loading={risk.isFetching}
              icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
              onClick={() => void risk.refetch()}
            >
              Rescan
            </Button>
          </>
        }
      />

      <DisclaimerCard
        loading={disclaimer.isLoading}
        error={disclaimer.error}
        disclaimer={disclaimer.data?.disclaimer ?? null}
        wordingRule={disclaimer.data?.wording_rule ?? null}
        onRetry={() => void disclaimer.refetch()}
      />

      <FieldGate>
        <div className="space-y-6">
          {risk.isLoading ? (
            <div className="space-y-4">
              <Card>
                <SkeletonBlock lines={3} />
              </Card>
              <Card>
                <SkeletonBlock lines={8} />
              </Card>
            </div>
          ) : risk.error ? (
            <ErrorBanner
              title="Could not scan this field for risk"
              error={risk.error}
              onRetry={() => void risk.refetch()}
            />
          ) : !risk.data ? (
            <EmptyState
              title="No risk scan available"
              description="The API returned no scan for this field."
              icon={<ScanSearch className="h-5 w-5" aria-hidden="true" />}
            />
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <StatCard
                  label="Overall risk level"
                  value={<RiskBadge severity={risk.data.risk_level} qualifier="overall" />}
                  hint="Highest severity across all findings"
                  tone="brand"
                  testId="risk-level"
                />
                <StatCard
                  label="Findings"
                  value={formatNumber(risk.data.findings.length, 0)}
                  hint="Environmental favourability statements"
                  icon={<Microscope className="h-4 w-4" aria-hidden="true" />}
                />
                <StatCard
                  label="Highest severity"
                  value={humaniseToken(
                    risk.data.findings.reduce(
                      (worst, finding) => (severityRank(finding.severity) > severityRank(worst) ? finding.severity : worst),
                      'none',
                    ),
                  )}
                  hint="Ranked low to critical"
                />
                <StatCard
                  label="Findings citing simulated evidence"
                  value={formatNumber(
                    risk.data.findings.filter((finding) =>
                      finding.evidence.some((item) => item.kind === 'simulated'),
                    ).length,
                    0,
                  )}
                  hint="Backed at least partly by simulator output"
                  icon={<Cpu className="h-4 w-4" aria-hidden="true" />}
                />
              </div>

              {risk.data.findings.length === 0 ? (
                <EmptyState
                  title="No environmental risk conditions flagged"
                  description="Nothing in the current measurements or forecast crosses a reporting threshold for this field and crop."
                  icon={<ShieldQuestion className="h-5 w-5" aria-hidden="true" />}
                />
              ) : (
                <div className="space-y-4">
                  {risk.data.findings.map((finding) => (
                    <RiskFindingCard key={finding.id} finding={finding} mlCrossCheck={mlCrossCheck} />
                  ))}
                </div>
              )}

              {/* The server's own disclaimer travels with the scan response. */}
              {risk.data.disclaimer ? (
                <p className="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2.5 text-[11px] leading-relaxed text-slate-500 ring-1 ring-inset ring-slate-200">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span>{risk.data.disclaimer}</span>
                </p>
              ) : null}

              <MlPanel
                loading={predictions.isLoading}
                error={predictions.error}
                severity={severityPrediction}
                moisture={moisturePrediction}
                total={predictions.data?.length ?? 0}
                onRetry={() => void predictions.refetch()}
              />

              <Card flush>
                <CardHeader
                  title={`Finding history (${history.data?.length ?? 0})`}
                  subtitle="GET /risk/fields/{field_id}/history - previous scans, newest first."
                  icon={<Microscope className="h-4 w-4" aria-hidden="true" />}
                />
                {history.isLoading ? (
                  <SkeletonTable rows={4} columns={5} />
                ) : (history.data?.length ?? 0) === 0 ? (
                  <div className="p-5">
                    <EmptyState title="No previous findings" description="This is the first recorded scan." />
                  </div>
                ) : (
                  <DataTable<RiskFinding>
                    columns={[
                      {
                        key: 'type',
                        header: 'Risk type',
                        render: (row) => (
                          <span className="font-medium text-slate-800">{humaniseToken(row.risk_type)}</span>
                        ),
                      },
                      { key: 'severity', header: 'Severity', render: (row) => <RiskBadge severity={row.severity} /> },
                      {
                        key: 'statement',
                        header: 'Statement',
                        render: (row) => (
                          <span className="block max-w-xl text-xs leading-relaxed text-slate-600">
                            {row.statement}
                          </span>
                        ),
                      },
                      {
                        key: 'observed',
                        header: 'Observed',
                        render: (row) => (
                          <span className="whitespace-nowrap text-xs text-slate-500">
                            {formatDateTime(row.observed_at)}
                          </span>
                        ),
                      },
                      {
                        key: 'run',
                        header: 'Run',
                        className: 'tabular',
                        render: (row) =>
                          row.workflow_run_id === null || row.workflow_run_id === undefined
                            ? '-'
                            : `#${row.workflow_run_id}`,
                      },
                    ]}
                    rows={history.data ?? []}
                    rowKey={(row) => row.id}
                    dense
                  />
                )}
              </Card>
            </>
          )}
        </div>
      </FieldGate>
    </div>
  );
}

const SEVERITY_ORDER = ['none', 'none_expected', 'low', 'moderate', 'medium', 'high', 'critical', 'severe'];

const severityRank = (severity: string): number => {
  const index = SEVERITY_ORDER.indexOf((severity ?? '').toLowerCase());
  return index === -1 ? 0 : index;
};

function DisclaimerCard({
  loading,
  error,
  disclaimer,
  wordingRule,
  onRetry,
}: {
  loading: boolean;
  error: unknown;
  disclaimer: string | null;
  wordingRule: string | null;
  onRetry: () => void;
}) {
  return (
    <Card flush>
      <CardHeader
        title="This system does not diagnose crop conditions"
        subtitle="GET /risk/disclaimer - the exact wording rule the backend enforces on every finding."
        icon={<ShieldQuestion className="h-4 w-4" aria-hidden="true" />}
      />
      {loading ? (
        <div className="p-5">
          <SkeletonBlock lines={3} />
        </div>
      ) : error ? (
        <ErrorBanner className="m-5" title="Could not load the disclaimer" error={error} onRetry={onRetry} />
      ) : (
        <div className="space-y-3 p-5">
          <p
            className="rounded-lg border-l-4 border-amber-400 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-slate-800"
            data-testid="risk-disclaimer"
          >
            {disclaimer ?? 'No disclaimer text returned by the API.'}
          </p>
          {wordingRule ? (
            <p className="flex items-start gap-2 text-[11px] leading-relaxed text-slate-500">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>
                <span className="font-medium text-slate-600">Wording rule:</span> {wordingRule}
              </span>
            </p>
          ) : null}
        </div>
      )}
    </Card>
  );
}

function MlPanel({
  loading,
  error,
  severity,
  moisture,
  total,
  onRetry,
}: {
  loading: boolean;
  error: unknown;
  severity: MLPrediction | undefined;
  moisture: MLPrediction | undefined;
  total: number;
  onRetry: () => void;
}) {
  return (
    <Card flush>
      <CardHeader
        title="Machine-learning cross-check"
        subtitle={`GET /ml/fields/{field_id}/predictions - ${total} prediction(s). The model grades severity; it does not name a pathogen or pest.`}
        icon={<Cpu className="h-4 w-4" aria-hidden="true" />}
      />
      {loading ? (
        <div className="p-5">
          <SkeletonBlock lines={4} />
        </div>
      ) : error ? (
        <ErrorBanner className="m-5" title="Could not load ML predictions" error={error} onRetry={onRetry} />
      ) : total === 0 ? (
        <div className="p-5">
          <EmptyState
            title="No model predictions"
            description="The ML layer has not produced a prediction for this field yet."
          />
        </div>
      ) : (
        <div className="grid gap-4 p-5 sm:grid-cols-2">
          <PredictionCard title="Severity model" prediction={severity} fallback="No severity prediction on record." />
          <PredictionCard title="Soil moisture model" prediction={moisture} fallback="No moisture prediction on record." />
        </div>
      )}
    </Card>
  );
}

function PredictionCard({
  title,
  prediction,
  fallback,
}: {
  title: string;
  prediction: MLPrediction | undefined;
  fallback: string;
}) {
  if (!prediction) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/60 p-4">
        <p className="label-caps">{title}</p>
        <p className="mt-2 text-xs text-slate-400">{fallback}</p>
      </div>
    );
  }

  const value =
    prediction.prediction_label ?? formatNumber(prediction.prediction_value, 2);

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <p className="label-caps">{title}</p>
      <p className="mt-1.5 flex flex-wrap items-baseline gap-2">
        <span className="text-lg font-semibold text-slate-900">{value}</span>
        {prediction.unit ? (
          <span className="text-xs text-slate-500">{prediction.unit}</span>
        ) : null}
        <Badge tone="neutral">{humaniseToken(prediction.status)}</Badge>
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {prediction.model_name} v{prediction.model_version} · task {prediction.task}
        {prediction.horizon_days ? ` · ${prediction.horizon_days} day horizon` : ''}
      </p>
      {prediction.confidence !== null && prediction.confidence !== undefined ? (
        <p className="mt-1 text-xs text-slate-500">
          Confidence {formatNumber(prediction.confidence, 2)}
        </p>
      ) : null}
      {prediction.message ? (
        <p className="mt-2 text-xs leading-relaxed text-slate-600">{prediction.message}</p>
      ) : null}
      {Object.keys(prediction.features).length > 0 ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11px] font-medium text-slate-500">
            Model features ({Object.keys(prediction.features).length})
          </summary>
          <dl className="mt-1.5 space-y-0.5">
            {Object.entries(prediction.features).map(([key, featureValue]) => (
              <div key={key} className="flex items-baseline justify-between gap-3 text-[11px]">
                <dt className="text-slate-500">{humaniseToken(key)}</dt>
                <dd className="tabular text-slate-700">
                  {featureValue === null ? 'imputed' : formatNumber(featureValue, 3)}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
      {(prediction.imputed_features?.length ?? 0) > 0 ? (
        <p className="mt-2 text-[11px] text-amber-700">
          Imputed features: {prediction.imputed_features?.join(', ')}
        </p>
      ) : null}
    </div>
  );
}

export default CropRiskPage;
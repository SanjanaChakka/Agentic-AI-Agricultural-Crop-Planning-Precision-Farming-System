import { useMemo, useState } from 'react';
import { Info, Leaf, Play, Scale, Sparkles, TriangleAlert } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { Badge, StatusBadge, toneForVerdict } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { SkeletonTable } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';
import { Select } from '../components/ui/Field';
import { FieldGate } from '../components/layout/FieldGate';
import { EvidenceLedger, ReferenceList } from '../components/evidence/EvidenceLedger';
import {
  useAssessSuitability,
  useCropCatalogue,
  useSuitabilityHistory,
} from '../hooks/useSuitability';
import { useSelection } from '../context/SelectionContext';
import { useToast } from '../components/feedback/ToastProvider';
import type { CropRequirement, FactorScore, Suitability } from '../api/types';
import { formatDateTime, formatNumber, humaniseToken } from '../lib/format';

/**
 * Crop Planner.
 *
 * GET /suitability/crops · POST /suitability/assess?field_id=N ·
 * GET /suitability/fields/{id}
 *
 * The assessment is deliberately NOT auto-run: it is a POST that spends an
 * agent cycle, so the operator picks a crop and presses the button.
 */
export function CropPlannerPage() {
  const { fieldId } = useSelection();
  const catalogue = useCropCatalogue();
  const history = useSuitabilityHistory(fieldId);
  const assess = useAssessSuitability();
  const toast = useToast();

const crops = useMemo(() => catalogue.data?.crops ?? [], [catalogue.data?.crops]);
const [crop, setCrop] = useState('');
  const [soilObservationId, setSoilObservationId] = useState('');

  const selectedRequirement = useMemo(
    () => crops.find((item) => item.name === crop) ?? null,
    [crops, crop],
  );

  const runAssessment = () => {
    if (fieldId === null) return;
    assess.mutate(
      {
        fieldId,
        payload: {
          crop: crop || null,
          soil_observation_id: soilObservationId ? Number(soilObservationId) : null,
          include_evidence: true,
        },
      },
      {
        onSuccess: (result) => {
          toast.push({
            tone: 'success',
            title: 'Suitability assessed',
            message: `${result.crop}: ${humaniseToken(result.status)} (${formatNumber(result.score, 1)}/100).`,
          });
        },
        onError: (error) => toast.pushError(error, 'Could not assess suitability'),
      },
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Crop Planner"
        description="A weighted, evidence-backed comparison of a crop against the field's measured soil, live telemetry and forecast. Every factor shows its own weight, verdict and source."
        actions={
          <Button
            variant="primary"
            disabled={fieldId === null}
            loading={assess.isPending}
            title={fieldId === null ? 'Select a field first' : undefined}
            icon={<Play className="h-4 w-4" aria-hidden="true" />}
            onClick={runAssessment}
          >
            Assess suitability
          </Button>
        }
      />

      <FieldGate>
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Assessment inputs"
              subtitle="POST /suitability/assess - leave the crop blank to let the agent choose from the field's proposed crop."
              icon={<Leaf className="h-4 w-4" aria-hidden="true" />}
            />
            <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
              <div className="space-y-1.5">
                <label htmlFor="planner-crop" className="label-caps block">
                  Crop
                </label>
                <Select
                  id="planner-crop"
                  value={crop}
                  onChange={(event) => setCrop(event.target.value)}
                  disabled={catalogue.isLoading}
                >
                  <option value="">
                    {catalogue.isLoading ? 'Loading crop catalogue...' : 'Use the field crop'}
                  </option>
                  {crops.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                    </option>
                  ))}
                </Select>
                <p className="text-[11px] text-slate-500">
                  {catalogue.data?.count ?? 0} crops in the catalogue
                  {catalogue.data ? ` (GET /suitability/crops)` : ''}
                </p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="planner-soil-obs" className="label-caps block">
                  Soil observation id
                </label>
                <TextLikeInput
                  id="planner-soil-obs"
                  value={soilObservationId}
                  onChange={setSoilObservationId}
                  placeholder="optional - defaults to latest"
                />
                <p className="text-[11px] text-slate-500">
                  Pin a specific soil test instead of the latest recorded one.
                </p>
              </div>

              {selectedRequirement ? <RequirementSummary requirement={selectedRequirement} /> : null}
            </div>
            {assess.error ? (
              <div className="px-5 pb-5">
                <ErrorBanner title="Could not assess suitability" error={assess.error} />
              </div>
            ) : null}
          </Card>

          {assess.data ? <AssessmentResult result={assess.data} /> : null}

          <Card flush>
            <CardHeader
              title={`Assessment history (${history.data?.length ?? 0})`}
              subtitle="GET /suitability/fields/{field_id} - every past assessment for this field."
              icon={<Scale className="h-4 w-4" aria-hidden="true" />}
            />
            {history.isLoading ? (
              <SkeletonTable rows={3} columns={5} />
            ) : history.error ? (
              <ErrorBanner
                className="m-5"
                title="Could not load the assessment history"
                error={history.error}
                onRetry={() => void history.refetch()}
              />
            ) : (history.data?.length ?? 0) === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No assessments yet"
                  description="Run an assessment above to create the first weighted score for this field."
                  icon={<Leaf className="h-5 w-5" aria-hidden="true" />}
                />
              </div>
            ) : (
              <DataTable<Suitability>
                columns={[
                  {
                    key: 'crop',
                    header: 'Crop',
                    render: (row) => <span className="font-medium text-slate-800">{row.crop}</span>,
                  },
                  { key: 'status', header: 'Status', render: (row) => <StatusBadge status={row.status} /> },
                  {
                    key: 'score',
                    header: 'Score',
                    className: 'tabular',
                    render: (row) => `${formatNumber(row.score, 1)} / 100`,
                  },
                  {
                    key: 'confidence',
                    header: 'Confidence',
                    className: 'tabular',
                    render: (row) => formatNumber(row.confidence, 2),
                  },
                  {
                    key: 'factors',
                    header: 'Factors',
                    className: 'tabular',
                    render: (row) => (
                      <span title={`${row.favorable_factors.length} favourable, ${row.limiting_factors.length} limiting`}>
                        {row.favorable_factors.length} / {row.limiting_factors.length}
                      </span>
                    ),
                  },
                  {
                    key: 'generated',
                    header: 'Generated',
                    render: (row) => (
                      <span className="whitespace-nowrap text-xs text-slate-500">
                        {formatDateTime(row.created_at)}
                      </span>
                    ),
                  },
                  {
                    key: 'by',
                    header: 'Produced by',
                    render: (row) => <span className="text-xs text-slate-500">{row.generated_by}</span>,
                  },
                ]}
                rows={history.data ?? []}
                rowKey={(row) => row.id}
                dense
              />
            )}
          </Card>
        </div>
      </FieldGate>
    </div>
  );
}

/** Small numeric input - kept local so the planner file stays self-contained. */
function TextLikeInput({
  id,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      id={id}
      type="number"
      min={1}
      step={1}
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
    />
  );
}

function RequirementSummary({ requirement }: { requirement: CropRequirement }) {
  const rows: Array<[string, string]> = [
    ['Optimal pH', range(requirement.ph_optimal)],
    ['Tolerable pH', range(requirement.ph_tolerable)],
    ['Optimal temperature', withUnit(range(requirement.temp_optimal), '\u00b0C')],
    ['Absolute max temp', withUnit(formatNumber(requirement.temp_absolute_max, 1), '\u00b0C')],
    ['Heat stress above', withUnit(formatNumber(requirement.heat_stress_threshold_c, 1), '\u00b0C')],
    ['Season rainfall', range(requirement.season_rainfall_mm, ' mm')],
    ['Water requirement', range(requirement.water_requirement_mm, ' mm')],
    ['Optimal moisture', withUnit(range(requirement.moisture_optimal), '% VWC')],
    ['Critical moisture at or below', withUnit(formatNumber(requirement.moisture_critical, 1), '% VWC')],
    ['Duration', range(requirement.duration_days, ' days')],
  ];

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 sm:col-span-2 lg:col-span-1">
      <p className="label-caps flex items-center gap-1.5">
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        {requirement.name} requirements
      </p>
      <dl className="mt-2 space-y-1">
        {rows
          .filter(([, value]) => value !== '-')
          .map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-3 text-xs">
              <dt className="text-slate-600">{label}</dt>
              <dd className="tabular font-mono text-[11px] text-slate-700">{value}</dd>
            </div>
          ))}
      </dl>
      {requirement.critical_stages?.length ? (
        <p className="mt-2 text-[11px] leading-snug text-slate-500">
          <span className="font-medium text-slate-600">Critical stages:</span>{' '}
          {requirement.critical_stages.join(', ')}
        </p>
      ) : null}
      {requirement.doc_key ? (
        <p className="mt-1 text-[11px] text-slate-400">
          Reference: <span className="font-mono">{requirement.doc_key}</span>
        </p>
      ) : null}
    </div>
  );
}

const range = (value: [number, number] | undefined, unit = ''): string =>
  value ? `${formatNumber(value[0], 1)} - ${formatNumber(value[1], 1)}${unit}` : '-';

const withUnit = (value: string, unit: string): string =>
  value === '-' ? '-' : `${value}${unit}`;

function AssessmentResult({ result }: { result: Suitability }) {
  const score = result.score ?? null;

  return (
    <div className="space-y-6" data-testid="suitability-result">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Weighted score"
          value={`${formatNumber(score, 1)} / 100`}
          hint={`${result.factor_scores.length} factors evaluated`}
          tone="brand"
          testId="suitability-score"
        />
        <StatCard
          label="Verdict"
          value={humaniseToken(result.status)}
          hint={`Generated by ${result.generated_by}`}
        />
        <StatCard
          label="Confidence"
          value={formatNumber(result.confidence, 2)}
          hint="Self-reported by the suitability agent"
        />
        <StatCard
          label="Evaluated weight"
          value={formatNumber(result.evaluated_weight, 2)}
          hint={
            result.missing_information.length > 0
              ? `${result.missing_information.length} factor(s) had no data`
              : 'All factors had data'
          }
        />
      </div>

      {result.missing_information.length > 0 ? (
        <div
          className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3"
          role="note"
        >
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-amber-900">Assessed with missing information</p>
            <p className="mt-0.5 text-xs text-amber-900/80">
              Unscored factors are reported as missing rather than assumed. Treat the score as a
              partial evaluation.
            </p>
            <ul className="mt-1.5 list-inside list-disc text-xs text-amber-900">
              {result.missing_information.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card flush>
            <CardHeader
              title={`Factor scores (${result.factor_scores.length})`}
              subtitle="Each factor carries an explicit weight, so the arithmetic behind the score is auditable."
              icon={<Scale className="h-4 w-4" aria-hidden="true" />}
            />
            {result.factor_scores.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No factor scores"
                  description="The agent returned no weighted factors for this crop."
                />
              </div>
            ) : (
              <DataTable<FactorScore>
                columns={[
                  {
                    key: 'factor',
                    header: 'Factor',
                    render: (factor) => (
                      <div className="min-w-[9rem]">
                        <p className="text-xs font-medium text-slate-800">{factor.label}</p>
                        <p className="font-mono text-[11px] text-slate-400">{factor.factor}</p>
                      </div>
                    ),
                  },
                  {
                    key: 'verdict',
                    header: 'Verdict',
                    render: (factor) => (
                      <Badge tone={toneForVerdict(factor.verdict)}>{humaniseToken(factor.verdict)}</Badge>
                    ),
                  },
                  {
                    key: 'score',
                    header: 'Score',
                    className: 'tabular',
                    render: (factor) => formatNumber(factor.score, 1),
                  },
                  {
                    key: 'weight',
                    header: 'Weight',
                    className: 'tabular',
                    render: (factor) => formatNumber(factor.weight, 2),
                  },
                  {
                    key: 'measured',
                    header: 'Measured',
                    className: 'tabular',
                    render: (factor) =>
                      factor.measured_value === null || factor.measured_value === undefined
                        ? '-'
                        : String(factor.measured_value),
                  },
                  {
                    key: 'required',
                    header: 'Required',
                    className: 'tabular',
                    render: (factor) => factor.required_range ?? '-',
                  },
                  {
                    key: 'detail',
                    header: 'Detail',
                    render: (factor) => (
                      <span className="block max-w-sm text-xs leading-relaxed text-slate-600">
                        {factor.detail}
                      </span>
                    ),
                  },
                ]}
                rows={result.factor_scores}
                rowKey={(factor) => factor.factor}
                dense
              />
            )}
          </Card>

          {result.narrative ? (
            <Card>
              <CardHeader
                title="Assessment narrative"
                subtitle={`Generated by ${result.generated_by}.`}
                icon={<Sparkles className="h-4 w-4" aria-hidden="true" />}
              />
              <p className="text-sm leading-relaxed text-slate-700">{result.narrative}</p>
            </Card>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Factor summary" icon={<Scale className="h-4 w-4" aria-hidden="true" />} />
            <div className="space-y-4 p-5">
              <TokenList
                title={`Favourable (${result.favorable_factors.length})`}
                tokens={result.favorable_factors}
                tone="success"
                empty="No factor was favourable."
              />
              <TokenList
                title={`Limiting (${result.limiting_factors.length})`}
                tokens={result.limiting_factors}
                tone="danger"
                empty="No limiting factor."
              />
              <TokenList
                title={`Missing information (${result.missing_information.length})`}
                tokens={result.missing_information}
                tone="warning"
                empty="Nothing missing."
              />
              {Object.keys(result.requirements_used).length > 0 ? (
                <div>
                  <p className="label-caps">Requirements applied</p>
                  <dl className="mt-1.5 space-y-1">
                    {Object.entries(result.requirements_used).map(([key, value]) => (
                      <div key={key} className="flex items-baseline justify-between gap-3 text-xs">
                        <dt className="text-slate-600">{humaniseToken(key)}</dt>
                        <dd className="tabular max-w-[60%] break-words text-right text-[11px] text-slate-700">
                          {typeof value === 'object' && value !== null
                            ? JSON.stringify(value)
                            : String(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ) : null}
            </div>
          </Card>

          {result.evidence.length > 0 ? (
            <EvidenceLedger
              evidence={result.evidence}
              title="Assessment evidence"
              subtitle="Every input the suitability agent used, tagged with its provenance."
              groupByKind
            />
          ) : null}
        </div>
      </div>

      {result.sources.length > 0 ? <ReferenceList sources={result.sources} /> : null}

      <p className="flex items-start gap-2 text-[11px] leading-relaxed text-slate-400">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span>
          A suitability score describes how well a crop matches the measured and forecast conditions
          for this field. It is decision support: it does not commit seed, land or water, and it does
          not diagnose the crop.
        </span>
      </p>
    </div>
  );
}

function TokenList({
  title,
  tokens,
  tone,
  empty,
}: {
  title: string;
  tokens: string[];
  tone: 'success' | 'danger' | 'warning';
  empty: string;
}) {
  return (
    <div>
      <p className="label-caps">{title}</p>
      {tokens.length === 0 ? (
        <p className="mt-1 text-xs text-slate-400">{empty}</p>
      ) : (
        <ul className="mt-1.5 flex flex-wrap gap-1.5">
          {tokens.map((token) => (
            <li key={token}>
              <Badge tone={tone}>{humaniseToken(token)}</Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default CropPlannerPage;
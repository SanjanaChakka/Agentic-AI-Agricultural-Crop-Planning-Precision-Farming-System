import { useState } from 'react';
import {
  CircleSlash,
  Droplets,
  Gauge,
  Play,
  ScrollText,
  ShieldAlert,
  TriangleAlert,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { Badge, StatusBadge, toneForSeverity, toneForStatus } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { FieldRow, FormGrid, TextInput } from '../components/ui/Field';
import { SkeletonBlock, SkeletonTable } from '../components/ui/Skeleton';
import { SimulatedBanner } from '../components/ui/SimulatedBanner';
import { StatCard } from '../components/ui/StatCard';
import { EvidenceLedger, ReferenceList } from '../components/evidence/EvidenceLedger';
import { FieldGate } from '../components/layout/FieldGate';
import { useAssessIrrigation, useIrrigationHistory } from '../hooks/useIrrigation';
import { useSelection } from '../context/SelectionContext';
import { useToast } from '../components/feedback/ToastProvider';
import type { Irrigation, IrrigationRule } from '../api/types';
import { formatDateTime, formatNumber, humaniseToken } from '../lib/format';

/**
 * Irrigation.
 *
 * POST /irrigation/assess?field_id=N · GET /irrigation/fields/{id}
 *
 * HARD CONSTRAINT: this page is decision support only. The backend exposes no
 * endpoint that actuates a valve, pump or irrigation set - so there is
 * deliberately no "apply water" control anywhere in this file. The only actions
 * offered are "assess" (a POST that produces a proposal) and reading history.
 */
export function IrrigationPage() {
  const { fieldId } = useSelection();
  const history = useIrrigationHistory(fieldId);
  const assess = useAssessIrrigation();
  const toast = useToast();

  const [crop, setCrop] = useState('');
  const [cropStage, setCropStage] = useState('');
  const [moistureOverride, setMoistureOverride] = useState('');

  const runAssessment = () => {
    if (fieldId === null) return;
    assess.mutate(
      {
        fieldId,
        payload: {
          crop: crop.trim() || null,
          crop_stage: cropStage.trim() || null,
          soil_moisture_percent:
            moistureOverride.trim() === '' ? null : Number(moistureOverride),
        },
      },
      {
        onSuccess: (result) => {
          toast.push({
            tone: 'success',
            title: 'Irrigation assessed',
            message: `${humaniseToken(result.recommendation)} (${formatNumber(result.estimated_water_mm, 1)} mm proposed).`,
          });
        },
        onError: (error) => toast.pushError(error, 'Could not assess irrigation'),
      },
    );
  };

  const assessments = history.data ?? [];
  const latest = assess.data ?? assessments[0] ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Irrigation"
        description="Water-need proposals computed from measured soil moisture, forecast rainfall and reference evapotranspiration."
        actions={
          <Button
            variant="primary"
            disabled={fieldId === null}
            loading={assess.isPending}
            title={fieldId === null ? 'Select a field first' : undefined}
            icon={<Play className="h-4 w-4" aria-hidden="true" />}
            onClick={runAssessment}
          >
            Assess irrigation need
          </Button>
        }
      />

      {/* Non-negotiable safety notice, rendered above everything on this page. */}
      <HumanAuthorisationNotice />

      <FieldGate>
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Assessment inputs"
              subtitle="POST /irrigation/assess - override the crop, growth stage or measured moisture only when a human observation supersedes the record."
              icon={<Droplets className="h-4 w-4" aria-hidden="true" />}
            />
            <FormGrid className="p-5">
              <FieldRow label="Crop override" hint="Blank uses the field's current crop.">
                {(id) => (
                  <TextInput
                    id={id}
                    value={crop}
                    placeholder="e.g. Cotton"
                    onChange={(event) => setCrop(event.target.value)}
                  />
                )}
              </FieldRow>
              <FieldRow label="Crop stage override">
                {(id) => (
                  <TextInput
                    id={id}
                    value={cropStage}
                    placeholder="e.g. flowering"
                    onChange={(event) => setCropStage(event.target.value)}
                  />
                )}
              </FieldRow>
              <FieldRow label="Soil moisture override (% VWC)" hint="Blank uses the latest probe reading.">
                {(id) => (
                  <TextInput
                    id={id}
                    type="number"
                    step="0.1"
                    min="0"
                    max="100"
                    value={moistureOverride}
                    onChange={(event) => setMoistureOverride(event.target.value)}
                  />
                )}
              </FieldRow>
            </FormGrid>
            {assess.error ? (
              <div className="px-5 pb-5">
                <ErrorBanner title="Could not assess irrigation" error={assess.error} />
              </div>
            ) : null}
          </Card>

          {history.isLoading && !assess.data ? (
            <Card>
              <SkeletonBlock lines={6} />
            </Card>
          ) : history.error && !assess.data ? (
            <ErrorBanner
              title="Could not load irrigation history"
              error={history.error}
              onRetry={() => void history.refetch()}
            />
          ) : latest ? (
            <AssessmentPanel
              assessment={latest}
              source={assess.data ? 'POST /irrigation/assess' : 'GET /irrigation/fields/{id}'}
            />
          ) : (
            <EmptyState
              title="No irrigation assessment yet"
              description="Run an assessment to see the proposed depth, the rules that fired and the evidence behind them."
              icon={<Droplets className="h-5 w-5" aria-hidden="true" />}
              action={
                <Button variant="primary" onClick={runAssessment}>
                  Assess irrigation need
                </Button>
              }
            />
          )}

          <Card flush>
            <CardHeader
              title={`Assessment history (${assessments.length})`}
              subtitle="GET /irrigation/fields/{field_id} - proposals only. None of these entries represent applied water."
              icon={<ScrollText className="h-4 w-4" aria-hidden="true" />}
            />
            {history.isLoading ? (
              <SkeletonTable rows={3} columns={6} />
            ) : assessments.length === 0 ? (
              <div className="p-5">
                <EmptyState title="No history yet" description="Run the first assessment to populate this list." />
              </div>
            ) : (
              <DataTable<Irrigation>
                columns={[
                  {
                    key: 'recommendation',
                    header: 'Recommendation',
                    render: (row) => (
                      <span className="font-medium text-slate-800">{humaniseToken(row.recommendation)}</span>
                    ),
                  },
                  {
                    key: 'urgency',
                    header: 'Urgency',
                    render: (row) => (
                      <Badge tone={toneForSeverity(row.urgency)}>{humaniseToken(row.urgency)}</Badge>
                    ),
                  },
                  {
                    key: 'depth',
                    header: 'Depth',
                    className: 'tabular',
                    render: (row) => `${formatNumber(row.estimated_water_mm, 1)} mm`,
                  },
                  {
                    key: 'volume',
                    header: 'Volume',
                    className: 'tabular',
                    render: (row) => `${formatNumber(row.estimated_volume_m3, 1)} m\u00b3`,
                  },
                  {
                    key: 'auth',
                    header: 'Authorisation',
                    render: (row) =>
                      row.requires_human_authorisation ? (
                        <Badge tone="warning">
                          <ShieldAlert className="h-3 w-3" aria-hidden="true" />
                          Human required
                        </Badge>
                      ) : (
                        <StatusBadge status={row.authorisation_state} />
                      ),
                  },
                  {
                    key: 'created',
                    header: 'Assessed',
                    render: (row) => (
                      <span className="whitespace-nowrap text-xs text-slate-500">
                        {formatDateTime(row.created_at)}
                      </span>
                    ),
                  },
                ]}
                rows={assessments}
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

/**
 * The safety notice. Deliberately loud and unmissable: this system proposes,
 * humans apply.
 */
export function HumanAuthorisationNotice({ className }: { className?: string }) {
  return (
    <div
      role="alert"
      data-testid="human-authorisation-notice"
      className={[
        'flex flex-wrap items-start gap-3 rounded-xl border-2 border-brand-600 bg-brand-50 px-5 py-4',
        className ?? '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-700 text-white">
        <ShieldAlert className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-brand-900">
          Every irrigation proposal requires human authorisation
        </p>
        <p className="mt-1 text-xs leading-relaxed text-brand-900/85">
          This system <strong className="font-semibold">cannot actuate equipment</strong>. It has no
          endpoint that opens a valve, starts a pump or logs applied water, and this page deliberately
          offers no apply control. What you see below is a <em>proposal</em>: review it, then act
          through your own irrigation controller or operator. A human decision is recorded separately
          on the{' '}
          <strong className="font-semibold">AI Advisory</strong> page.
        </p>
      </div>
      <span className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-[11px] font-medium text-brand-800 ring-1 ring-inset ring-brand-200">
        <CircleSlash className="h-3.5 w-3.5" aria-hidden="true" />
        Decision support only
      </span>
    </div>
  );
}

function AssessmentPanel({ assessment, source }: { assessment: Irrigation; source: string }) {
  const sensor = assessment.sensor_context;
  const weather = assessment.weather_context;

  return (
    <div className="space-y-6" data-testid="irrigation-assessment">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Recommendation"
          value={humaniseToken(assessment.recommendation)}
          hint={`Urgency: ${humaniseToken(assessment.urgency)}`}
          tone="brand"
          testId="irrigation-recommendation"
        />
        <StatCard
          label="Proposed depth"
          value={`${formatNumber(assessment.estimated_water_mm, 1)} mm`}
          hint={`${formatNumber(assessment.estimated_volume_m3, 1)} m\u00b3`}
          icon={<Droplets className="h-4 w-4" aria-hidden="true" />}
        />
        <StatCard
          label="Authorisation state"
          value={humaniseToken(assessment.authorisation_state)}
          hint={
            assessment.requires_human_authorisation
              ? 'requires_human_authorisation: true'
              : 'Recorded on the advisory page'
          }
          tone={assessment.requires_human_authorisation ? 'warning' : 'default'}
        />
        <StatCard
          label="Water availability"
          value={
            assessment.water_availability_m3_per_day === null ||
            assessment.water_availability_m3_per_day === undefined
              ? 'not recorded'
              : `${formatNumber(assessment.water_availability_m3_per_day, 0)} m\u00b3/day`
          }
          hint="Daily allocation recorded against the field"
          icon={<Gauge className="h-4 w-4" aria-hidden="true" />}
        />
      </div>

      <SimulatedBanner
        isSimulated={sensor.is_simulated === true || weather.is_simulated === true}
        subject="irrigation inputs"
        detail="The sensor or weather context feeding this proposal is simulated, so treat the proposed depth as illustrative."
      />

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader
              title="Rationale"
              subtitle={`${source} · generated by ${assessment.generated_by}`}
              icon={<ScrollText className="h-4 w-4" aria-hidden="true" />}
            />
            <p className="text-sm leading-relaxed text-slate-700">{assessment.rationale}</p>
            {assessment.requires_human_authorisation ? (
              <p className="mt-3 flex items-start gap-2 text-xs text-brand-800">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  This proposal is <strong>not authorised</strong>. It carries{' '}
                  <code className="font-mono">requires_human_authorisation: true</code> and cannot be
                  acted on until a person records a decision.
                </span>
              </p>
            ) : null}
          </Card>

          <Card flush>
            <CardHeader
              title={`Rules evaluated (${assessment.rules_evaluated.length})`}
              subtitle="Deterministic agronomic rules, in evaluation order. This is the audit trail for the proposed depth."
              icon={<Gauge className="h-4 w-4" aria-hidden="true" />}
            />
            {assessment.rules_evaluated.length === 0 ? (
              <div className="p-5">
                <EmptyState title="No rules recorded" description="The assessment returned no rule trail." />
              </div>
            ) : (
              <DataTable<IrrigationRule>
                columns={[
                  {
                    key: 'rule',
                    header: 'Rule',
                    render: (rule) => (
                      <span className="font-mono text-[11px] text-slate-700">{rule.rule}</span>
                    ),
                  },
                  {
                    key: 'outcome',
                    header: 'Outcome',
                    render: (rule) => (
                      <Badge tone={toneForStatus(rule.outcome)}>{humaniseToken(rule.outcome)}</Badge>
                    ),
                  },
                  {
                    key: 'detail',
                    header: 'Detail',
                    render: (rule) => (
                      <span className="block max-w-lg text-xs leading-relaxed text-slate-600">
                        {rule.detail}
                      </span>
                    ),
                  },
                ]}
                rows={assessment.rules_evaluated}
                rowKey={(rule) => rule.rule}
                dense
              />
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card flush>
            <CardHeader
              title="Sensor context"
              subtitle="The telemetry the proposal was computed from."
              icon={<Droplets className="h-4 w-4" aria-hidden="true" />}
            />
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 p-5">
              <ContextStat label="Latest reading" value={formatDateTime(sensor.latest_reading_at)} />
              <ContextStat label="Sensor" value={sensor.sensor_id ?? '-'} />
              <ContextStat
                label="Moisture"
                value={`${formatNumber(sensor.soil_moisture_percent, 1)}%`}
              />
              <ContextStat label="Soil temp" value={`${formatNumber(sensor.soil_temperature_c, 1)} \u00b0C`} />
              <ContextStat
                label="Refill trigger"
                value={`${formatNumber(sensor.refill_trigger_percent, 1)}%`}
              />
              <ContextStat
                label="Field capacity"
                value={`${formatNumber(sensor.field_capacity_percent, 1)}%`}
              />
            </dl>
            {sensor.quality_flags && sensor.quality_flags.length > 0 ? (
              <div className="px-5 pb-5">
                <p className="label-caps flex items-center gap-1.5">
                  <TriangleAlert className="h-3.5 w-3.5" aria-hidden="true" />
                  Quality flags
                </p>
                <ul className="mt-1.5 flex flex-wrap gap-1.5">
                  {sensor.quality_flags.map((flag) => (
                    <li key={flag}>
                      <Badge tone="warning">{humaniseToken(flag)}</Badge>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>

          <Card flush>
            <CardHeader
              title="Weather context"
              subtitle={
                weather.source
                  ? `${weather.source}${weather.is_simulated ? ' (simulated fallback)' : ''}`
                  : undefined
              }
            />
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 p-5">
              <ContextStat
                label="Rain next 48 h"
                value={`${formatNumber(weather.rainfall_next_48h_mm, 1)} mm`}
              />
              <ContextStat
                label="Rain next 3 d"
                value={`${formatNumber(weather.rainfall_next_3d_mm, 1)} mm`}
              />
              <ContextStat label="Rain next 7 d" value={`${formatNumber(weather.rainfall_7d_mm, 1)} mm`} />
              <ContextStat
                label="Max rain chance"
                value={`${formatNumber(weather.max_precipitation_probability_3d_percent, 0)}%`}
              />
              <ContextStat label="Max temp" value={`${formatNumber(weather.max_temp_c, 1)} \u00b0C`} />
              <ContextStat label="Total ET0" value={`${formatNumber(weather.total_et0_mm, 2)} mm`} />
              <ContextStat
                label="Mean humidity"
                value={`${formatNumber(weather.mean_humidity_percent, 0)}%`}
              />
            </dl>
          </Card>

          {assessment.ml_prediction ? (
            <Card flush>
              <CardHeader
                title="ML water-need prediction"
                subtitle="A trained model's independent estimate, shown alongside the rule-based proposal."
              />
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 p-5">
                {Object.entries(assessment.ml_prediction)
                  .filter(([, value]) => value === null || typeof value !== 'object')
                  .slice(0, 8)
                  .map(([key, value]) => (
                    <ContextStat key={key} label={humaniseToken(key)} value={String(value)} />
                  ))}
              </dl>
            </Card>
          ) : null}
        </div>
      </div>

      {assessment.evidence.length > 0 ? (
        <EvidenceLedger
          evidence={assessment.evidence}
          title="Irrigation evidence"
          subtitle="Every input behind this proposal, tagged with its provenance."
          groupByKind
        />
      ) : null}

      {assessment.sources.length > 0 ? <ReferenceList sources={assessment.sources} /> : null}
    </div>
  );
}

function ContextStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label-caps">{label}</dt>
      <dd className="tabular mt-0.5 break-words text-sm font-medium text-slate-800">{value}</dd>
    </div>
  );
}

export default IrrigationPage;
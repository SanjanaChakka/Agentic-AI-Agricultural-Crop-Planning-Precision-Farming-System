import { useMemo, useState, type FormEvent } from 'react';
import {
  Beaker,
  FlaskConical,
  Info,
  Plus,
  Sprout,
  TestTube2,
} from 'lucide-react';
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { SkeletonBlock, SkeletonChart, SkeletonTable } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';
import { EvidenceKindBadge } from '../components/ui/EvidenceKindBadge';
import { FieldRow, FormGrid, Select, TextArea, TextInput } from '../components/ui/Field';
import { FieldGate } from '../components/layout/FieldGate';
import { useLatestSoil, useSoilObservations, useSoilThresholds, useCreateSoilObservation } from '../hooks/useSoil';
import { useSelection } from '../context/SelectionContext';
import { useToast } from '../components/feedback/ToastProvider';
import type {
  SoilAnalysisResponse,
  SoilObservation,
  SoilObservationCreate,
  SoilThresholds,
} from '../api/types';
import { formatDate, formatDateTime, formatNumber, humaniseToken } from '../lib/format';

/**
 * Soil.
 *
 * GET /soil/fields/{id}/latest · GET /soil/observations?field_id= ·
 * GET /soil/thresholds · POST /soil/observations
 */
export function SoilPage() {
  const { fieldId } = useSelection();
  const latest = useLatestSoil(fieldId);
  const history = useSoilObservations(fieldId);
  const thresholds = useSoilThresholds();
  const [showForm, setShowForm] = useState(false);

  const historyChartData = useMemo(
    () =>
      [...(history.data ?? [])]
        .reverse()
        .map((observation) => ({
          observed_at: observation.observed_at,
          ph: observation.ph ?? null,
          soil_moisture_percent: observation.soil_moisture_percent ?? null,
          organic_carbon_percent: observation.organic_carbon_percent ?? null,
        })),
    [history.data],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Soil"
        description="Measured laboratory values are shown exactly as recorded; the interpretation layer is kept separate and always labels its own provenance."
        actions={
          <Button
            variant="primary"
            disabled={fieldId === null}
            title={fieldId === null ? 'Select a field first' : undefined}
            icon={<Plus className="h-4 w-4" aria-hidden="true" />}
            onClick={() => setShowForm((value) => !value)}
          >
            Add observation
          </Button>
        }
      />

      <FieldGate>
        {showForm && fieldId !== null ? (
          <AddObservationForm
            fieldId={fieldId}
            onDone={() => setShowForm(false)}
          />
        ) : null}

        {latest.isLoading || history.isLoading ? (
          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <SkeletonBlock lines={6} />
            </Card>
            <Card>
              <SkeletonBlock lines={4} />
            </Card>
          </div>
        ) : latest.error ? (
          <ErrorBanner
            title="Could not load the latest soil test"
            error={latest.error}
            onRetry={() => void latest.refetch()}
          />
        ) : !latest.data ? (
          <EmptyState
            title="No soil test recorded for this field"
            description="Record a measured observation to unlock soil interpretation and the soil-based suitability factors."
            icon={<TestTube2 className="h-5 w-5" aria-hidden="true" />}
            action={
              <Button variant="primary" onClick={() => setShowForm(true)}>
                Add the first observation
              </Button>
            }
          />
        ) : (
          <>
            <LatestSoilPanel analysis={latest.data} />
            <SoilThresholdsPanel thresholds={thresholds.data} loading={thresholds.isLoading} />
            <SoilHistoryPanel
              observations={history.data ?? []}
              loading={history.isLoading}
              error={history.error}
              chartData={historyChartData}
              onRetry={() => void history.refetch()}
            />
          </>
        )}
      </FieldGate>
    </div>
  );
}

function LatestSoilPanel({ analysis }: { analysis: SoilAnalysisResponse }) {
  const { observation, interpretation, measured_values_note } = analysis;
  const nutrientStatus = interpretation?.nutrient_status ?? {};

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="pH"
          value={formatNumber(observation.ph, 2)}
          hint={interpretation ? humaniseToken(interpretation.ph_class) : undefined}
        />
        <StatCard
          label="Soil moisture"
          value={`${formatNumber(observation.soil_moisture_percent, 1)}% VWC`}
          hint="Volumetric water content"
        />
        <StatCard
          label="Organic carbon"
          value={`${formatNumber(observation.organic_carbon_percent, 2)}%`}
          hint={interpretation ? `${humaniseToken(interpretation.organic_matter_status)} rating` : undefined}
        />
        <StatCard
          label="Observed"
          value={formatDate(observation.observed_at)}
          hint={`${observation.data_source}${observation.lab_name ? ` · ${observation.lab_name}` : ''}`}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card flush>
          <CardHeader
            title="Measured values"
            subtitle={measured_values_note}
            icon={<Beaker className="h-4 w-4" aria-hidden="true" />}
          />
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 p-5 sm:grid-cols-3">
            <Measurement label="Available N (kg/ha)" value={observation.nitrogen_available_kg_ha} rating={nutrientStatus.nitrogen_available_kg_ha} />
            <Measurement label="Available P2O5 (kg/ha)" value={observation.phosphorus_available_kg_ha} rating={nutrientStatus.phosphorus_available_kg_ha} />
            <Measurement label="Available K2O (kg/ha)" value={observation.potassium_available_kg_ha} rating={nutrientStatus.potassium_available_kg_ha} />
            <Measurement label="Organic carbon (%)" value={observation.organic_carbon_percent} rating={nutrientStatus.organic_carbon_percent} />
            <Measurement label="Soil moisture (% VWC)" value={observation.soil_moisture_percent} />
            <Measurement label="Conductivity (dS/m)" value={observation.electrical_conductivity_ds_m} />
            <Measurement label="Sample depth (cm)" value={observation.sample_depth_cm} />
            <Measurement label="Soil type recorded" value={observation.soil_type} isText />
            <Measurement label="Observation id" value={observation.id} isText />
          </dl>
          {(observation.missing_parameters?.length ?? 0) > 0 ? (
            <div className="mx-5 mb-5 rounded-lg bg-amber-50 px-3 py-2 text-[11px] text-amber-900 ring-1 ring-inset ring-amber-200">
              <p className="font-semibold">Missing parameters on this test</p>
              <ul className="mt-1 list-inside list-disc">
                {observation.missing_parameters?.map((parameter) => (
                  <li key={parameter}>{parameter}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </Card>

        <Card flush>
          <CardHeader
            title="AI interpretation"
            subtitle={
              interpretation
                ? `${interpretation.agent_name} · generated by ${interpretation.generated_by}${
                    interpretation.confidence !== null && interpretation.confidence !== undefined
                      ? ` · confidence ${formatNumber(interpretation.confidence, 2)}`
                      : ''
                  }`
                : 'No interpretation attached to this observation.'
            }
            icon={<FlaskConical className="h-4 w-4" aria-hidden="true" />}
          />
          <div className="space-y-4 p-5">
            {!interpretation ? (
              <EmptyState
                title="No interpretation"
                description="The AI layer has not interpreted this observation yet."
              />
            ) : (
              <>
                <p className="text-sm leading-relaxed text-slate-700">{interpretation.summary}</p>

                {interpretation.limitations.length > 0 ? (
                  <div>
                    <p className="label-caps">Limitations</p>
                    <ul className="mt-1 list-inside list-disc text-xs text-slate-600">
                      {interpretation.limitations.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {interpretation.recommendations.length > 0 ? (
                  <div>
                    <p className="label-caps">Recommendations</p>
                    <ul className="mt-1 space-y-2">
                      {interpretation.recommendations.map((recommendation, index) => (
                        <li
                          key={`${recommendation.action}-${index}`}
                          className="rounded-lg border border-slate-200 p-3"
                        >
                          <p className="flex flex-wrap items-center gap-2 text-xs font-medium text-slate-800">
                            {recommendation.action}
                            {recommendation.priority ? (
                              <Badge tone="neutral">{humaniseToken(recommendation.priority)}</Badge>
                            ) : null}
                            {recommendation.basis ? (
                              <Badge tone="neutral" title={recommendation.basis}>
                                {recommendation.basis}
                              </Badge>
                            ) : null}
                          </p>
                          <p className="mt-1 text-xs leading-relaxed text-slate-600">
                            {recommendation.detail}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {interpretation.missing_parameters.length > 0 ? (
                  <div>
                    <p className="label-caps">Missing information</p>
                    <ul className="mt-1 list-inside list-disc text-xs text-slate-600">
                      {interpretation.missing_parameters.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {interpretation.evidence.length > 0 ? (
                  <div>
                    <p className="label-caps">Evidence ({interpretation.evidence.length})</p>
                    <ul className="mt-1.5 space-y-1.5">
                      {interpretation.evidence.slice(0, 6).map((item, index) => (
                        <li key={`${item.label}-${index}`} className="flex flex-wrap items-start gap-2">
                          <EvidenceKindBadge kind={item.kind} />
                          <span className="min-w-0 flex-1 text-xs text-slate-600">
                            <span className="font-medium text-slate-700">{item.label}</span>:{' '}
                            {item.value === null || item.value === undefined ? '-' : String(item.value)}
                            {item.unit ? ` ${item.unit}` : ''}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function Measurement({
  label,
  value,
  rating,
  isText = false,
}: {
  label: string;
  value?: number | string | null;
  rating?: string;
  isText?: boolean;
}) {
  return (
    <div>
      <dt className="label-caps">{label}</dt>
      <dd className="tabular mt-0.5 text-sm font-medium text-slate-800">
        {isText ? (value === null || value === undefined ? '-' : String(value)) : formatNumber(value as number | null | undefined, 2)}
      </dd>
      {rating ? (
        <dd className="mt-0.5">
          <Badge tone="neutral">{humaniseToken(rating)}</Badge>
        </dd>
      ) : null}
    </div>
  );
}

function SoilThresholdsPanel({
  thresholds,
  loading,
}: {
  thresholds: SoilThresholds | undefined;
  loading: boolean;
}) {
  return (
    <Card flush>
      <CardHeader
        title="Rating thresholds applied by the system"
        subtitle="GET /soil/thresholds - the agronomic bands used to classify every soil test."
        icon={<Info className="h-4 w-4" aria-hidden="true" />}
      />
      {loading ? (
        <div className="p-5">
          <SkeletonBlock lines={3} />
        </div>
      ) : !thresholds ? (
        <div className="p-5">
          <EmptyState title="Thresholds unavailable" description="The API returned no threshold table." />
        </div>
      ) : (
        <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
          <ThresholdCard
            title="Available nitrogen"
            unit="kg/ha"
            band={thresholds.nitrogen_available_kg_ha}
          />
          <ThresholdCard
            title="Available phosphorus"
            unit="kg/ha"
            band={thresholds.phosphorus_available_kg_ha}
          />
          <ThresholdCard
            title="Available potassium"
            unit="kg/ha"
            band={thresholds.potassium_available_kg_ha}
          />
          <ThresholdCard
            title="Organic carbon"
            unit="%"
            band={thresholds.organic_carbon_percent}
          />
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="label-caps">pH classes</p>
            <ul className="mt-2 space-y-1">
              {Object.entries(thresholds.ph_classes).map(([name, range]) => (
                <li key={name} className="flex items-baseline justify-between gap-3 text-xs">
                  <span className="text-slate-600">{humaniseToken(name)}</span>
                  <span className="font-mono text-[11px] text-slate-500">{range}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Card>
  );
}

function ThresholdCard({
  title,
  unit,
  band,
}: {
  title: string;
  unit: string;
  band: { low_max: number; medium_max: number };
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <p className="label-caps">{title}</p>
      <ul className="mt-2 space-y-1 text-xs">
        <li className="flex items-baseline justify-between gap-3">
          <span className="text-rose-700">Low</span>
          <span className="font-mono text-[11px] text-slate-500">
            &lt; {formatNumber(band.low_max, 1)} {unit}
          </span>
        </li>
        <li className="flex items-baseline justify-between gap-3">
          <span className="text-amber-700">Medium</span>
          <span className="font-mono text-[11px] text-slate-500">
            {formatNumber(band.low_max, 1)} - {formatNumber(band.medium_max, 1)} {unit}
          </span>
        </li>
        <li className="flex items-baseline justify-between gap-3">
          <span className="text-emerald-700">High</span>
          <span className="font-mono text-[11px] text-slate-500">
            &gt; {formatNumber(band.medium_max, 1)} {unit}
          </span>
        </li>
      </ul>
    </div>
  );
}

function SoilHistoryPanel({
  observations,
  loading,
  error,
  chartData,
  onRetry,
}: {
  observations: SoilObservation[];
  loading: boolean;
  error: unknown;
  chartData: Array<Record<string, unknown>>;
  onRetry: () => void;
}) {
  return (
    <div className="space-y-6">
      <Card flush>
        <CardHeader
          title={`Parameter history (${observations.length})`}
          subtitle="pH, moisture and organic carbon over every recorded test for this field."
          icon={<Sprout className="h-4 w-4" aria-hidden="true" />}
        />
        {loading ? (
          <SkeletonChart />
        ) : error ? (
          <ErrorBanner className="m-5" title="Could not load the history" error={error} onRetry={onRetry} />
        ) : observations.length === 0 ? (
          <div className="p-5">
            <EmptyState title="No observations yet" description="Add the first test to start the history." />
          </div>
        ) : (
          <div className="p-4" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis
                  dataKey="observed_at"
                  tickFormatter={(value: string) => formatDate(value)}
                  tickLine={false}
                  axisLine={{ stroke: '#cbd5e1' }}
                  tickMargin={8}
                  minTickGap={20}
                />
                <YAxis yAxisId="ph" domain={[4, 9]} tickLine={false} axisLine={false} width={40} />
                <YAxis yAxisId="pct" orientation="right" tickLine={false} axisLine={false} width={44} />
                <Tooltip
                  contentStyle={{ fontSize: 12 }}
                  labelFormatter={(value) => formatDate(String(value), String(value))}
                />
                <Line
                  yAxisId="ph"
                  type="monotone"
                  dataKey="ph"
                  name="pH"
                  stroke="#047857"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="pct"
                  type="monotone"
                  dataKey="soil_moisture_percent"
                  name="Moisture (% VWC)"
                  stroke="#0369a1"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="pct"
                  type="monotone"
                  dataKey="organic_carbon_percent"
                  name="Organic carbon (%)"
                  stroke="#b45309"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card flush>
        <CardHeader title="All observations" />
        {loading ? (
          <SkeletonTable rows={4} columns={5} />
        ) : observations.length === 0 ? (
          <div className="p-5">
            <EmptyState title="Nothing recorded" />
          </div>
        ) : (
          <DataTable<SoilObservation>
            columns={[
              {
                key: 'observed',
                header: 'Observed',
                render: (observation) => (
                  <span className="whitespace-nowrap text-xs text-slate-700">
                    {formatDateTime(observation.observed_at)}
                  </span>
                ),
              },
              {
                key: 'ph',
                header: 'pH',
                className: 'tabular',
                render: (observation) => formatNumber(observation.ph, 2),
              },
              {
                key: 'n',
                header: 'N (kg/ha)',
                className: 'tabular',
                render: (observation) => formatNumber(observation.nitrogen_available_kg_ha, 0),
              },
              {
                key: 'p',
                header: 'P2O5 (kg/ha)',
                className: 'tabular',
                render: (observation) => formatNumber(observation.phosphorus_available_kg_ha, 0),
              },
              {
                key: 'k',
                header: 'K2O (kg/ha)',
                className: 'tabular',
                render: (observation) => formatNumber(observation.potassium_available_kg_ha, 0),
              },
              {
                key: 'moisture',
                header: 'Moisture',
                className: 'tabular',
                render: (observation) =>
                  `${formatNumber(observation.soil_moisture_percent, 1)}% VWC`,
              },
              {
                key: 'source',
                header: 'Source',
                render: (observation) => (
                  <div>
                    <p className="text-xs text-slate-700">{observation.data_source}</p>
                    {observation.lab_name ? (
                      <p className="text-[11px] text-slate-400">{observation.lab_name}</p>
                    ) : null}
                  </div>
                ),
              },
            ]}
            rows={observations}
            rowKey={(observation) => observation.id}
            dense
          />
        )}
      </Card>
    </div>
  );
}

function AddObservationForm({ fieldId, onDone }: { fieldId: number; onDone: () => void }) {
  const createObservation = useCreateSoilObservation();
  const toast = useToast();
  const [form, setForm] = useState({
    ph: '',
    nitrogen_available_kg_ha: '',
    phosphorus_available_kg_ha: '',
    potassium_available_kg_ha: '',
    organic_carbon_percent: '',
    soil_moisture_percent: '',
    electrical_conductivity_ds_m: '',
    sample_depth_cm: '15',
    soil_type: '',
    data_source: 'manual_entry',
    lab_name: '',
    notes: '',
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const numberOrNull = (value: string) => (value.trim() === '' ? null : Number(value));
    const payload: SoilObservationCreate = {
      field_id: fieldId,
      data_source: form.data_source.trim(),
      ph: numberOrNull(form.ph),
      nitrogen_available_kg_ha: numberOrNull(form.nitrogen_available_kg_ha),
      phosphorus_available_kg_ha: numberOrNull(form.phosphorus_available_kg_ha),
      potassium_available_kg_ha: numberOrNull(form.potassium_available_kg_ha),
      organic_carbon_percent: numberOrNull(form.organic_carbon_percent),
      soil_moisture_percent: numberOrNull(form.soil_moisture_percent),
      electrical_conductivity_ds_m: numberOrNull(form.electrical_conductivity_ds_m),
      sample_depth_cm: numberOrNull(form.sample_depth_cm),
      soil_type: form.soil_type.trim() || null,
      lab_name: form.lab_name.trim() || null,
      notes: form.notes.trim() || null,
    };

    createObservation.mutate(payload, {
      onSuccess: (result) => {
        toast.push({
          tone: 'success',
          title: 'Observation recorded',
          message: `Observation #${result.observation.id} saved and interpreted.`,
        });
        onDone();
      },
      onError: (error) => toast.pushError(error, 'Could not record the observation'),
    });
  };

  const set = (key: string) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  return (
    <Card>
      <CardHeader
        title="Add a soil observation"
        subtitle="POST /soil/observations - recorded values are stored exactly as supplied and never modified by the AI layer."
        icon={<TestTube2 className="h-4 w-4" aria-hidden="true" />}
        actions={
          <Button size="sm" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        }
      />
      <form onSubmit={submit} className="space-y-4 p-5">
        {createObservation.error ? (
          <ErrorBanner title="Could not record the observation" error={createObservation.error} />
        ) : null}
        <FormGrid>
          <FieldRow label="Soil pH">
            {(id) => (
              <TextInput id={id} type="number" step="0.01" min="0" max="14" value={form.ph} onChange={set('ph')} />
            )}
          </FieldRow>
          <FieldRow label="Available N (kg/ha)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.1"
                min="0"
                value={form.nitrogen_available_kg_ha}
                onChange={set('nitrogen_available_kg_ha')}
              />
            )}
          </FieldRow>
          <FieldRow label="Available P2O5 (kg/ha)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.1"
                min="0"
                value={form.phosphorus_available_kg_ha}
                onChange={set('phosphorus_available_kg_ha')}
              />
            )}
          </FieldRow>
          <FieldRow label="Available K2O (kg/ha)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.1"
                min="0"
                value={form.potassium_available_kg_ha}
                onChange={set('potassium_available_kg_ha')}
              />
            )}
          </FieldRow>
          <FieldRow label="Organic carbon (%)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.01"
                min="0"
                value={form.organic_carbon_percent}
                onChange={set('organic_carbon_percent')}
              />
            )}
          </FieldRow>
          <FieldRow label="Soil moisture (% VWC)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={form.soil_moisture_percent}
                onChange={set('soil_moisture_percent')}
              />
            )}
          </FieldRow>
          <FieldRow label="Conductivity (dS/m)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.01"
                min="0"
                value={form.electrical_conductivity_ds_m}
                onChange={set('electrical_conductivity_ds_m')}
              />
            )}
          </FieldRow>
          <FieldRow label="Sample depth (cm)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="1"
                min="0"
                value={form.sample_depth_cm}
                onChange={set('sample_depth_cm')}
              />
            )}
          </FieldRow>
          <FieldRow label="Soil type recorded">
            {(id) => <TextInput id={id} value={form.soil_type} onChange={set('soil_type')} />}
          </FieldRow>
          <FieldRow
            label="Data source"
            required
            hint="Where the measurement came from. These values are the backend's accepted provenance codes."
          >
            {(id) => (
              <Select id={id} value={form.data_source} onChange={set('data_source')}>
                <option value="lab_test">Laboratory report</option>
                <option value="manual_entry">Field measurement</option>
                <option value="sensor">Sensor reading</option>
                <option value="demo_seed">Demo seed data</option>
              </Select>
            )}
          </FieldRow>
          <FieldRow label="Laboratory name">
            {(id) => <TextInput id={id} value={form.lab_name} onChange={set('lab_name')} />}
          </FieldRow>
        </FormGrid>
        <FieldRow label="Notes">
          {(id) => <TextArea id={id} value={form.notes} onChange={set('notes')} />}
        </FieldRow>
        <div className="flex justify-end">
          <Button type="submit" variant="primary" loading={createObservation.isPending}>
            Record observation
          </Button>
        </div>
      </form>
    </Card>
  );
}

export default SoilPage;
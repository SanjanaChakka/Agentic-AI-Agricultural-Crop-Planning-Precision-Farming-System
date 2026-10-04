import { useMemo, useState } from 'react';
import {
  Activity,
  Battery,
  CircleAlert,
  Droplets,
  FlaskConical,
  RefreshCw,
  Thermometer,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { Badge, toneForStatus } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Checkbox, FieldGroup, FieldRow, FormGrid, Select, TextInput } from '../components/ui/Field';
import { SkeletonBlock, SkeletonChart, SkeletonStats, SkeletonTable } from '../components/ui/Skeleton';
import { SimulatedBanner } from '../components/ui/SimulatedBanner';
import { StatCard } from '../components/ui/StatCard';
import { EvidenceKindBadge } from '../components/ui/EvidenceKindBadge';
import { TrendChart } from '../components/charts/TrendChart';
import { FieldGate } from '../components/layout/FieldGate';
import {
  useLatestReading,
  useSensorQuality,
  useSensorTrend,
  useSimulateReadings,
} from '../hooks/useSensors';
import { useSelection } from '../context/SelectionContext';
import { useToast } from '../components/feedback/ToastProvider';
import type { SensorReading, SensorTrend } from '../api/types';
import { formatDateTime, formatNumber, formatShortDateTime, humaniseToken } from '../lib/format';

/**
 * Sensors.
 *
 * GET /sensors/fields/{id}/latest · GET /sensors/fields/{id}/trend ·
 * GET /sensors/fields/{id}/quality · POST /sensors/fields/{id}/simulate
 *
 * Simulated rows are flagged `is_simulated` by the backend, so the banner below
 * is driven by the server flag rather than a client-side guess.
 */
export function SensorsPage() {
  const { fieldId } = useSelection();
  const [hours, setHours] = useState(168);
  const [showSimulate, setShowSimulate] = useState(false);

  const latest = useLatestReading(fieldId);
  const trend = useSensorTrend(fieldId, hours);
  const quality = useSensorQuality(fieldId);

  const chartData = useMemo(
    () =>
      (trend.data?.points ?? []).map((point) => ({
        recorded_at: point.recorded_at,
        soil_moisture_percent: point.soil_moisture_percent ?? null,
        soil_temperature_c: point.soil_temperature_c ?? null,
        air_humidity_percent: point.air_humidity_percent ?? null,
      })),
    [trend.data],
  );

  const simulated =
    latest.data?.is_simulated === true || quality.data?.is_simulated === true;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sensors"
        description="Field telemetry with the server's own quality verdict attached. Readings the backend simulated are labelled as such, never presented as measurements."
        actions={
          <>
            <div className="flex items-center gap-2">
              <label htmlFor="trend-window" className="label-caps">
                Window
              </label>
              <Select
                id="trend-window"
                className="h-8 w-auto py-1 text-xs"
                value={hours}
                onChange={(event) => setHours(Number(event.target.value))}
              >
                {[24, 72, 168, 336].map((option) => (
                  <option key={option} value={option}>
                    {option} h
                  </option>
                ))}
              </Select>
            </div>
            <Button
              variant="secondary"
              loading={trend.isFetching}
              icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
              onClick={() => void trend.refetch()}
            >
              Refresh
            </Button>
            <Button
              variant="primary"
              disabled={fieldId === null}
              title={fieldId === null ? 'Select a field first' : undefined}
              icon={<FlaskConical className="h-4 w-4" aria-hidden="true" />}
              onClick={() => setShowSimulate((value) => !value)}
            >
              Simulate telemetry
            </Button>
          </>
        }
      />

      <FieldGate>
        <div className="space-y-6">
          {showSimulate && fieldId !== null ? (
            <SimulateForm
              fieldId={fieldId}
              onDone={() => setShowSimulate(false)}
            />
          ) : null}

          <SimulatedBanner
            isSimulated={simulated}
            subject="sensor telemetry"
            detail={
              quality.data?.is_simulated
                ? `The backend flags this field's telemetry as simulated (verdict: ${quality.data.verdict}).`
                : latest.data?.is_simulated
                  ? 'The most recent reading carries is_simulated: true.'
                  : null
            }
          />

          {latest.isLoading || trend.isLoading ? (
            <>
              <SkeletonStats count={4} />
              <Card flush>
                <SkeletonChart />
              </Card>
            </>
          ) : latest.error ? (
            <ErrorBanner
              title="Could not load sensor telemetry"
              error={latest.error}
              onRetry={() => void latest.refetch()}
            />
          ) : !latest.data ? (
            <EmptyState
              title="No sensor readings for this field"
              description="No probe has reported yet. Generate simulated telemetry to exercise the pipeline - every row will be flagged is_simulated."
              icon={<Thermometer className="h-5 w-5" aria-hidden="true" />}
              action={
                <Button variant="primary" onClick={() => setShowSimulate(true)}>
                  Simulate telemetry
                </Button>
              }
            />
          ) : (
            <>
              <LatestStats reading={latest.data} />
              <TrendChart
                title={`Telemetry trend (${hours} h)`}
                subtitle={`GET /sensors/fields/${fieldId}/trend?hours=${hours} - ${
                  trend.data?.statistics.sample_count ?? 0
                } samples, ${trend.data?.quality_issue_count ?? 0} with quality flags.`}
                data={chartData}
                xKey="recorded_at"
                height={280}
                series={[
                  {
                    key: 'soil_moisture_percent',
                    label: 'Soil moisture',
                    unit: '% VWC',
                    color: '#0369a1',
                  },
                  {
                    key: 'soil_temperature_c',
                    label: 'Soil temperature',
                    unit: '\u00b0C',
                    color: '#b45309',
                  },
                  {
                    key: 'air_humidity_percent',
                    label: 'Air humidity',
                    unit: '%',
                    color: '#047857',
                  },
                ]}
                emptyMessage="No readings in this window. Try a longer window, or generate simulated telemetry."
              />
              <div className="grid gap-6 xl:grid-cols-3">
                <QualityPanel
                  loading={quality.isLoading}
                  error={quality.error}
                  report={quality.data}
                  onRetry={() => void quality.refetch()}
                />
                <TrendStatistics trend={trend.data} />
              </div>
              <ReadingsTable
                loading={trend.isLoading}
                points={trend.data?.points ?? []}
                sensorId={trend.data?.sensor_id ?? null}
              />
            </>
          )}
        </div>
      </FieldGate>
    </div>
  );
}

function LatestStats({ reading }: { reading: SensorReading }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="Soil moisture"
        value={`${formatNumber(reading.soil_moisture_percent, 1)}%`}
        hint="Volumetric water content"
        icon={<Droplets className="h-4 w-4" aria-hidden="true" />}
        tone={reading.soil_moisture_percent !== null && reading.soil_moisture_percent !== undefined && reading.soil_moisture_percent < 20 ? 'warning' : 'default'}
      />
      <StatCard
        label="Soil temperature"
        value={`${formatNumber(reading.soil_temperature_c, 1)} \u00b0C`}
        hint={`Probe ${reading.sensor_id}`}
        icon={<Thermometer className="h-4 w-4" aria-hidden="true" />}
      />
      <StatCard
        label="Air conditions"
        value={`${formatNumber(reading.air_temperature_c, 1)} \u00b0C`}
        hint={`Humidity ${formatNumber(reading.air_humidity_percent, 0)}%`}
      />
      <StatCard
        label="Battery"
        value={`${formatNumber(reading.battery_percent, 0)}%`}
        hint={`Recorded ${formatDateTime(reading.recorded_at)}`}
        icon={<Battery className="h-4 w-4" aria-hidden="true" />}
        tone={reading.battery_percent !== null && reading.battery_percent !== undefined && reading.battery_percent < 20 ? 'warning' : 'default'}
      />
      <div className="sm:col-span-2 xl:col-span-4">
        <DataProvenanceRow reading={reading} />
      </div>
    </div>
  );
}

/** Every provenance detail the latest reading carries. */
function DataProvenanceRow({ reading }: { reading: SensorReading }) {
  return (
    <div className="card-surface flex flex-wrap items-center gap-3 px-5 py-3">
      <EvidenceKindBadge kind={reading.is_simulated ? 'simulated' : 'measured'} showRaw />
      <span className="text-xs text-slate-600">
        {reading.is_simulated
          ? 'This reading was generated by the simulator. It is not a physical measurement.'
          : 'This reading came from a physical probe.'}
      </span>
      {reading.quality_flags.length > 0 ? (
        <span className="flex flex-wrap items-center gap-1.5">
          {reading.quality_flags.map((flag) => (
            <Badge key={flag} tone="warning">
              <CircleAlert className="h-3 w-3" aria-hidden="true" />
              {humaniseToken(flag)}
            </Badge>
          ))}
        </span>
      ) : (
        <Badge tone="success">No quality flags</Badge>
      )}
      {reading.notes ? <span className="text-xs text-slate-500">{reading.notes}</span> : null}
    </div>
  );
}

function QualityPanel({
  loading,
  error,
  report,
  onRetry,
}: {
  loading: boolean;
  error: unknown;
  report: ReturnType<typeof useSensorQuality>['data'];
  onRetry: () => void;
}) {
  return (
    <Card flush className="xl:col-span-2">
      <CardHeader
        title="Data quality verdict"
        subtitle="GET /sensors/fields/{field_id}/quality - the server's own assessment of whether these readings can be trusted."
        icon={<CircleAlert className="h-4 w-4" aria-hidden="true" />}
      />
      {loading ? (
        <div className="p-5">
          <SkeletonBlock lines={4} />
        </div>
      ) : error ? (
        <ErrorBanner className="m-5" title="Could not load the quality report" error={error} onRetry={onRetry} />
      ) : !report ? (
        <div className="p-5">
          <EmptyState title="No quality report" description="The endpoint returned no verdict." />
        </div>
      ) : (
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={report.available ? toneForStatus(report.verdict) : 'danger'}>
              {humaniseToken(report.verdict)}
            </Badge>
            <Badge tone={report.is_simulated ? 'warning' : 'success'}>
              {report.is_simulated ? 'Simulated source' : 'Physical probe'}
            </Badge>
            {report.sensor_id ? <Badge tone="neutral">{report.sensor_id}</Badge> : null}
          </div>
          {report.note ? (
            <p className="text-xs leading-relaxed text-slate-600">{report.note}</p>
          ) : null}
          <div>
            <p className="label-caps">Quality flags</p>
            {report.quality_flags.length === 0 ? (
              <p className="mt-1 text-xs text-slate-400">None recorded.</p>
            ) : (
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {report.quality_flags.map((flag) => (
                  <li key={flag}>
                    <Badge tone="warning">{humaniseToken(flag)}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <p className="label-caps">Faults</p>
            {report.faults.length === 0 ? (
              <p className="mt-1 text-xs text-slate-400">No faults reported.</p>
            ) : (
              <ul className="mt-1.5 space-y-1">
                {report.faults.map((fault, index) => (
                  <li
                    key={index}
                    className="break-words rounded-lg bg-slate-50 px-2.5 py-1.5 font-mono text-[11px] text-slate-600"
                  >
                    {typeof fault === 'string' ? fault : JSON.stringify(fault)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

function TrendStatistics({ trend }: { trend: SensorTrend | undefined }) {
  if (!trend) return <Card flush />;
  const stats = trend.statistics;
  return (
    <Card flush>
      <CardHeader
        title="Window statistics"
        subtitle="Computed by the backend over the selected window."
        icon={<Activity className="h-4 w-4" aria-hidden="true" />}
      />
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 p-5">
        <Stat label="Samples" value={formatNumber(stats.sample_count, 0)} />
        <Stat label="Quality issues" value={formatNumber(trend.quality_issue_count, 0)} />
        <Stat label="Moisture mean" value={`${formatNumber(stats.moisture_mean, 1)}%`} />
        <Stat label="Moisture min" value={`${formatNumber(stats.moisture_min, 1)}%`} />
        <Stat label="Moisture max" value={`${formatNumber(stats.moisture_max, 1)}%`} />
        <Stat label="Moisture change" value={`${formatNumber(stats.moisture_change_over_window, 1)}%`} />
        <Stat label="Soil temp mean" value={`${formatNumber(stats.soil_temperature_mean, 1)} \u00b0C`} />
        <Stat label="Air humidity mean" value={`${formatNumber(stats.air_humidity_mean, 0)}%`} />
        <Stat
          label="Simulated samples"
          value={formatNumber(stats.simulated_sample_count, 0)}
          className="col-span-2"
        />
      </dl>
    </Card>
  );
}

function Stat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={className}>
      <dt className="label-caps">{label}</dt>
      <dd className="tabular mt-0.5 text-sm font-medium text-slate-800">{value}</dd>
    </div>
  );
}

interface TrendRow {
  recorded_at: string;
  soil_moisture_percent?: number | null;
  soil_temperature_c?: number | null;
  air_temperature_c?: number | null;
  air_humidity_percent?: number | null;
}

function ReadingsTable({
  loading,
  points,
  sensorId,
}: {
  loading: boolean;
  points: TrendRow[];
  sensorId: string | null;
}) {
  const rows = useMemo(() => [...points].reverse(), [points]);

  return (
    <Card flush>
      <CardHeader
        title={`Readings in window (${rows.length})`}
        subtitle={sensorId ? `Probe ${sensorId}, newest first.` : 'Newest first.'}
      />
      {loading ? (
        <SkeletonTable rows={5} columns={6} />
      ) : rows.length === 0 ? (
        <div className="p-5">
          <EmptyState title="No readings in this window" description="Widen the window or simulate telemetry." />
        </div>
      ) : (
        <DataTable<TrendRow>
          columns={[
            {
              key: 'recorded',
              header: 'Recorded',
              render: (row) => (
                <span className="whitespace-nowrap text-xs text-slate-700">
                  {formatShortDateTime(row.recorded_at)}
                </span>
              ),
            },
            {
              key: 'moisture',
              header: 'Moisture',
              className: 'tabular',
              render: (row) => `${formatNumber(row.soil_moisture_percent, 1)}%`,
            },
            {
              key: 'soiltemp',
              header: 'Soil temp',
              className: 'tabular',
              render: (row) => `${formatNumber(row.soil_temperature_c, 1)} \u00b0C`,
            },
            {
              key: 'airtemp',
              header: 'Air temp',
              className: 'tabular',
              render: (row) => `${formatNumber(row.air_temperature_c, 1)} \u00b0C`,
            },
            {
              key: 'humidity',
              header: 'Humidity',
              className: 'tabular',
              render: (row) => `${formatNumber(row.air_humidity_percent, 0)}%`,
            },
          ]}
          rows={rows}
          rowKey={(row) => row.recorded_at}
          dense
        />
      )}
    </Card>
  );
}

function SimulateForm({ fieldId, onDone }: { fieldId: number; onDone: () => void }) {
  const simulate = useSimulateReadings();
  const toast = useToast();
  const [form, setForm] = useState({
    hours: '72',
    interval_hours: '2',
    sensor_id: '',
    seed: '',
    initial_soil_moisture_percent: '',
    rainfall_events: true,
    inject_fault: false,
  });

  const submit = () => {
    // A blank numeric input must be omitted, not sent as null: the backend
    // declares these as required scalars, so `null` would fail validation.
    const numberOrUndefined = (value: string) =>
      value.trim() === '' ? undefined : Number(value);
    const textOrUndefined = (value: string) => value.trim() || undefined;
    simulate.mutate(
      {
        fieldId,
        payload: {
          hours: numberOrUndefined(form.hours),
          interval_hours: numberOrUndefined(form.interval_hours),
          sensor_id: textOrUndefined(form.sensor_id),
          seed: numberOrUndefined(form.seed),
          initial_soil_moisture_percent: numberOrUndefined(form.initial_soil_moisture_percent),
          rainfall_events: form.rainfall_events,
          inject_fault: form.inject_fault,
        },
      },
      {
        onSuccess: (result) => {
          toast.push({
            tone: 'success',
            title: 'Telemetry generated',
            message: `${result.readings_created} simulated readings for ${result.sensor_id}. All are flagged is_simulated.`,
          });
          onDone();
        },
        onError: (error) => toast.pushError(error, 'Could not generate telemetry'),
      },
    );
  };

  const set = (key: keyof typeof form) => (value: string | boolean) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <Card>
      <CardHeader
        title="Generate simulated telemetry"
        subtitle="POST /sensors/fields/{field_id}/simulate. The backend persists every generated row with is_simulated: true, which this UI surfaces everywhere."
        icon={<FlaskConical className="h-4 w-4" aria-hidden="true" />}
        actions={
          <Button size="sm" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        }
      />
      <div className="space-y-4 p-5">
        {simulate.error ? (
          <ErrorBanner title="Could not generate telemetry" error={simulate.error} />
        ) : null}
        <FormGrid>
          <FieldRow label="Hours to cover">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                min={1}
                max={720}
                value={form.hours}
                onChange={(event) => set('hours')(event.target.value)}
              />
            )}
          </FieldRow>
          <FieldRow label="Interval (hours)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                min={1}
                max={24}
                value={form.interval_hours}
                onChange={(event) => set('interval_hours')(event.target.value)}
              />
            )}
          </FieldRow>
          <FieldRow label="Sensor id" hint="Leave blank to let the backend allocate one.">
            {(id) => (
              <TextInput
                id={id}
                value={form.sensor_id}
                placeholder="auto"
                onChange={(event) => set('sensor_id')(event.target.value)}
              />
            )}
          </FieldRow>
          <FieldRow label="Seed" hint="Fixed seed makes the run reproducible.">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                value={form.seed}
                placeholder="random"
                onChange={(event) => set('seed')(event.target.value)}
              />
            )}
          </FieldRow>
          <FieldRow label="Initial soil moisture (% VWC)">
            {(id) => (
              <TextInput
                id={id}
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={form.initial_soil_moisture_percent}
                onChange={(event) => set('initial_soil_moisture_percent')(event.target.value)}
              />
            )}
          </FieldRow>
          <FieldGroup label="Simulation options">
            <div className="space-y-2 pt-1">
              <Checkbox
                label="Include rainfall events"
                hint="Wets the soil profile so irrigation logic has something to react to."
                checked={form.rainfall_events}
                onChange={(event) => set('rainfall_events')(event.target.checked)}
              />
              <Checkbox
                label="Inject a fault"
                hint="Produces a quality flag so the quality endpoint has something to report."
                checked={form.inject_fault}
                onChange={(event) => set('inject_fault')(event.target.checked)}
              />
            </div>
          </FieldGroup>
        </FormGrid>
        <div className="flex justify-end">
          <Button variant="primary" loading={simulate.isPending} onClick={submit}>
            Generate readings
          </Button>
        </div>
      </div>
    </Card>
  );
}

export default SensorsPage;
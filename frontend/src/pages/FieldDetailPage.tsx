import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Droplets, Pencil, Trash2 } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { SkeletonBlock } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';
import { useAlerts, useFarmWithFields, useField } from '../hooks/useFarms';
import { useLatestRun } from '../hooks/useWorkflow';
import { deleteField } from '../api/farms';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '../components/feedback/ToastProvider';
import { useSelection } from '../context/SelectionContext';
import { formatDateTime, formatNumber, formatRelative, humaniseToken } from '../lib/format';
import { queryKeys } from '../lib/queryKeys';

/**
 * Field detail. `GET /fields/{id}` for the record, plus the field's alerts and
 * latest run so the page answers "what is the current state of this field".
 */
export function FieldDetailPage() {
  const { fieldId: fieldIdParam } = useParams();
  const fieldId = fieldIdParam ? Number(fieldIdParam) : null;
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { setField } = useSelection();

  const field = useField(fieldId);
  const alerts = useAlerts({ fieldId: fieldId ?? undefined });
  const latestRun = useLatestRun(fieldId);
  const farm = useFarmWithFields(field?.data?.farm_id ?? null);

  const removeField = useMutation({
    mutationFn: (id: number) => deleteField(id),
    onSuccess: (_data, id) => {
      toast.push({ tone: 'success', title: 'Field deleted' });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
      setField(null);
      navigate('/farms');
      return id;
    },
    onError: (error) => toast.pushError(error, 'Could not delete the field'),
  });

  if (field.isLoading) {
    return (
      <div>
        <PageHeader title="Field" />
        <Card>
          <SkeletonBlock lines={6} />
        </Card>
      </div>
    );
  }

  if (field.error) {
    return (
      <div>
        <PageHeader title="Field" />
        <ErrorBanner
          title="Could not load this field"
          error={field.error}
          onRetry={() => void field.refetch()}
        />
      </div>
    );
  }

  const data = field.data;
  if (!data || !fieldId) {
    return (
      <div>
        <PageHeader title="Field" />
        <EmptyState title="Field not found" description="The field id in the URL is not valid." />
      </div>
    );
  }

  const run = latestRun.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={data.field_code}
        title={data.name}
        description={data.notes ?? undefined}
        actions={
          <>
            <Link to="/farms">
              <Button
                variant="ghost"
                icon={<ArrowLeft className="h-4 w-4" aria-hidden="true" />}
              >
                All farms
              </Button>
            </Link>
            <Link to={`/fields/${data.id}/edit`}>
              <Button
                variant="primary"
                icon={<Pencil className="h-4 w-4" aria-hidden="true" />}
              >
                Edit field
              </Button>
            </Link>
            <Button
              variant="danger"
              loading={removeField.isPending}
              icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
              onClick={() => {
                if (
                  window.confirm(
                    `Delete field ${data.field_code} (${data.name})? Its observations and telemetry are removed too.`,
                  )
                ) {
                  removeField.mutate(data.id);
                }
              }}
            >
              Delete
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Area" value={`${formatNumber(data.area_ha, 2)} ha`} />
        <StatCard label="Soil type" value={humaniseToken(data.soil_type)} />
        <StatCard
          label="Proposed crop"
          value={humaniseToken(data.proposed_crop ?? 'not set')}
          hint={`Stage: ${humaniseToken(data.crop_stage ?? 'unknown')}`}
        />
        <StatCard
          label="Water"
          value={humaniseToken(data.water_availability ?? 'unknown')}
          hint={
            data.water_availability_m3_per_day
              ? `${humaniseToken(data.irrigation_source ?? 'source unknown')} · ${formatNumber(data.water_availability_m3_per_day, 0)} m3/day`
              : humaniseToken(data.irrigation_source ?? 'source unknown')
          }
          icon={<Droplets className="h-4 w-4" aria-hidden="true" />}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card flush className="xl:col-span-2">
          <CardHeader title="Field record" subtitle={`Owned by ${farm.data?.name ?? `farm #${data.farm_id}`}`} />
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 p-5 sm:grid-cols-2">
            <Detail label="Field code" value={data.field_code} mono />
            <Detail label="Farm" value={farm.data?.name ?? `#${data.farm_id}`} />
            <Detail label="Owner" value={farm.data?.owner_name ?? '-'} />
            <Detail
              label="Location"
              value={
                data.effective_latitude !== null && data.effective_latitude !== undefined
                  ? `${formatNumber(data.effective_latitude, 4)}, ${formatNumber(data.effective_longitude, 4)}`
                  : '-'
              }
              hint={
                data.latitude === null || data.latitude === undefined
                  ? 'Inherited from the farm centroid.'
                  : undefined
              }
            />
            <Detail label="Previous crop" value={humaniseToken(data.previous_crop ?? 'none recorded')} />
            <Detail label="Crop stage" value={humaniseToken(data.crop_stage ?? 'unknown')} />
            <Detail
              label="Planting window"
              value={data.planting_window_start ? formatDateTime(data.planting_window_start) : 'not set'}
            />
            <Detail label="Irrigation source" value={humaniseToken(data.irrigation_source ?? 'unknown')} />
            <Detail label="Water availability" value={humaniseToken(data.water_availability ?? 'unknown')} />
            <Detail
              label="Daily water available"
              value={
                data.water_availability_m3_per_day
                  ? `${formatNumber(data.water_availability_m3_per_day, 0)} m3`
                  : 'not declared'
              }
            />
            <Detail label="Created" value={formatDateTime(data.created_at)} />
            <Detail label="Last updated" value={formatRelative(data.updated_at)} />
          </dl>
        </Card>

        <div className="space-y-6">
          <Card flush>
            <CardHeader
              title="Latest agent run"
              actions={
                <Link to="/advisory">
                  <Button size="sm" variant="ghost">
                    Advisory
                  </Button>
                </Link>
              }
            />
            <div className="p-5">
              {latestRun.isLoading ? (
                <SkeletonBlock lines={3} />
              ) : !run ? (
                <EmptyState
                  title="No run for this field"
                  description="Run the workflow to generate an advisory."
                />
              ) : (
                <div className="space-y-2">
                  <p className="font-mono text-xs text-slate-500">run #{run.id}</p>
                  <Badge tone="neutral">{humaniseToken(run.status)}</Badge>
                  <p className="text-xs text-slate-600">
                    {humaniseToken(run.crop ?? 'no crop')} · {formatRelative(run.created_at)}
                  </p>
                  {run.agents_invoked.length > 0 ? (
                    <p className="text-[11px] text-slate-400">
                      {run.agents_invoked.length} agents invoked
                    </p>
                  ) : null}
                </div>
              )}
            </div>
          </Card>

          <Card flush>
            <CardHeader title={`Alerts (${alerts.data?.length ?? 0})`} />
            <div className="p-5">
              {alerts.data && alerts.data.length > 0 ? (
                <ul className="space-y-2">
                  {alerts.data.slice(0, 6).map((alert) => (
                    <li key={alert.id} className="rounded-lg border border-slate-200 p-3">
                      <p className="text-xs font-medium text-slate-800">{alert.title}</p>
                      <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                        {alert.message}
                      </p>
                      <Badge className="mt-1.5" tone="neutral">
                        {humaniseToken(alert.status)} · {humaniseToken(alert.severity)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No alerts" description="Nothing has been raised for this field." />
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Detail({
  label,
  value,
  hint,
  mono = false,
}: {
  label: string;
  value: string;
  hint?: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="label-caps">{label}</dt>
      <dd className={`mt-0.5 text-sm text-slate-800 ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
      {hint ? <p className="mt-0.5 text-[11px] text-slate-400">{hint}</p> : null}
    </div>
  );
}

export default FieldDetailPage;
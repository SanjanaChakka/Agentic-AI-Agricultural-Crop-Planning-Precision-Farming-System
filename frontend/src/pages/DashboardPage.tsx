import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  BellRing,
  Bot,
  ClipboardCheck,
  Droplets,
  FileText,
  Map,
  Sprout,
  Thermometer,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '../components/ui/PageHeader';
import { StatCard } from '../components/ui/StatCard';
import { Card, CardHeader } from '../components/ui/Card';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { SkeletonStats, SkeletonBlock } from '../components/ui/Skeleton';
import { StatusBadge, Badge } from '../components/ui/Badge';
import { EvidenceKindBadge } from '../components/ui/EvidenceKindBadge';
import { Button } from '../components/ui/Button';
import { FieldGate } from '../components/layout/FieldGate';
import { useDashboard, useOpenAlerts } from '../hooks/useFarms';
import { queryKeys } from '../lib/queryKeys';
import { useSelection } from '../context/SelectionContext';
import { getLatestRunForField } from '../api/workflow';
import {
  formatDateTime,
  formatDuration,
  formatNumber,
  formatRelative,
  humaniseToken,
} from '../lib/format';

/**
 * Dashboard.
 *
 * Overview cards and component health come from `GET /dashboard`. The latest
 * advisory for the selected field comes from `GET /workflow/runs/field/{id}/latest`
 * and the alert list from `GET /alerts/open`.
 */
export function DashboardPage() {
  const { fieldId, farmId } = useSelection();
  const dashboard = useDashboard();
  const alerts = useOpenAlerts(farmId ?? undefined);

  if (dashboard.isLoading) {
    return (
      <div>
        <PageHeader title="Dashboard" description="Loading portfolio overview..." />
        <SkeletonStats count={5} />
      </div>
    );
  }

  if (dashboard.error) {
    return (
      <div>
        <PageHeader title="Dashboard" />
        <ErrorBanner
          title="Could not load the dashboard"
          error={dashboard.error}
          onRetry={() => void dashboard.refetch()}
        />
      </div>
    );
  }

  const data = dashboard.data;
  if (!data) {
    return (
      <div>
        <PageHeader title="Dashboard" />
        <EmptyState title="No dashboard data" description="The API returned an empty payload." />
      </div>
    );
  }

  const latestRun = data.workflow_runs.recent[0];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={`Generated ${formatDateTime(data.generated_at)}`}
        title="Dashboard"
        description="Portfolio overview across every registered farm, with the latest multi-agent run status and the alerts that need attention."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          label="Farms"
          value={formatNumber(data.farms, 0)}
          hint={`${formatNumber(data.total_area_ha, 1)} ha registered`}
          icon={<Map className="h-4 w-4" aria-hidden="true" />}
          to="/farms"
          testId="stat-farms"
        />
        <StatCard
          label="Fields"
          value={formatNumber(data.fields, 0)}
          hint="Across all farms"
          icon={<Sprout className="h-4 w-4" aria-hidden="true" />}
          to="/farms"
          testId="stat-fields"
        />
        <StatCard
          label="Open alerts"
          value={formatNumber(data.open_alerts, 0)}
          hint="Open and acknowledged"
          tone={data.open_alerts > 0 ? 'danger' : 'default'}
          icon={<BellRing className="h-4 w-4" aria-hidden="true" />}
          testId="stat-open-alerts"
        />
        <StatCard
          label="Pending approvals"
          value={formatNumber(data.pending_approvals, 0)}
          hint="Awaiting a human decision"
          tone={data.pending_approvals > 0 ? 'warning' : 'default'}
          icon={<ClipboardCheck className="h-4 w-4" aria-hidden="true" />}
          to="/advisory"
          testId="stat-pending-approvals"
        />
        <StatCard
          label="Latest run status"
          value={latestRun ? humaniseToken(latestRun.status) : 'No runs yet'}
          hint={
            latestRun
              ? `${humaniseToken(latestRun.crop ?? 'crop')} on field #${latestRun.field_id}, ${formatRelative(latestRun.created_at)}`
              : `${data.workflow_runs.total} run(s) recorded`
          }
          icon={<Bot className="h-4 w-4" aria-hidden="true" />}
          to="/advisory"
          testId="stat-latest-run"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Soil observations"
          value={formatNumber(data.soil_observations, 0)}
          hint="Measured laboratory tests on file"
          icon={<Sprout className="h-4 w-4" aria-hidden="true" />}
          to="/soil"
        />
        <StatCard
          label="Sensor readings"
          value={formatNumber(data.sensor_readings, 0)}
          hint={`${formatNumber(data.simulated_readings, 0)} flagged simulated`}
          tone={data.simulated_readings > 0 ? 'warning' : 'default'}
          icon={<Thermometer className="h-4 w-4" aria-hidden="true" />}
          to="/sensors"
        />
        <StatCard
          label="Planned activities"
          value={formatNumber(data.planned_activities, 0)}
          hint="Field work on the plan"
          icon={<ClipboardCheck className="h-4 w-4" aria-hidden="true" />}
          to="/activities"
        />
        <StatCard
          label="Workflow runs"
          value={formatNumber(data.workflow_runs.total, 0)}
          hint={`${formatNumber(data.workflow_runs.completed, 0)} completed`}
          icon={<Bot className="h-4 w-4" aria-hidden="true" />}
          to="/advisory"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <LatestAdvisoryCard fieldId={fieldId} />

          <Card flush>
            <CardHeader
              title={`Open alerts (${alerts.data?.length ?? 0})`}
              subtitle="Open and acknowledged alerts across the selected scope."
              icon={<BellRing className="h-4 w-4" aria-hidden="true" />}
              actions={
                <Link to="/sensors">
                  <Button size="sm" variant="ghost">
                    Review telemetry
                  </Button>
                </Link>
              }
            />
            {alerts.error ? (
              <ErrorBanner
                className="m-5"
                title="Could not load alerts"
                error={alerts.error}
                onRetry={() => void alerts.refetch()}
              />
            ) : alerts.isLoading ? (
              <div className="p-5">
                <SkeletonBlock lines={4} />
              </div>
            ) : (alerts.data?.length ?? 0) === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No open alerts"
                  description="Nothing needs attention right now. Run the agent workflow to refresh the assessment."
                  icon={<ClipboardCheck className="h-5 w-5" aria-hidden="true" />}
                />
              </div>
            ) : (
              <ul className="divide-y divide-slate-100" data-testid="alert-list">
                {alerts.data?.map((alert) => (
                  <li key={alert.id} className="px-5 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-slate-900">
                          <AlertTriangle
                            className="h-3.5 w-3.5 text-amber-600"
                            aria-hidden="true"
                          />
                          {alert.title}
                          <StatusBadge status={alert.status} />
                          <Badge tone="neutral">{humaniseToken(alert.alert_type)}</Badge>
                        </p>
                        <p className="mt-1 text-xs leading-relaxed text-slate-600">{alert.message}</p>
                        <p className="mt-1 text-[11px] text-slate-400">
                          Field #{alert.field_id} · farm #{alert.farm_id} · first seen{' '}
                          {formatDateTime(alert.triggered_at)} · seen{' '}
                          {alert.occurrence_count}x
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-1">
                        {alert.evidence.slice(0, 3).map((item, index) => (
                          <EvidenceKindBadge key={`${item.label}-${index}`} kind={item.kind} />
                        ))}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card flush>
            <CardHeader title="Platform components" icon={<Bot className="h-4 w-4" aria-hidden="true" />} />
            <div className="space-y-3 p-5">
              <ComponentRow label="Database" value={data.components.database} />
              <ComponentRow
                label="Retrieval"
                value={data.components.rag.available ? data.components.rag.backend : 'unavailable'}
              />
              <ComponentRow
                label="Retrieval corpus"
                value={`${data.components.rag.documents.length} documents · ${formatNumber(data.components.rag.chunks, 0)} chunks`}
              />
              <ComponentRow
                label="Machine learning"
                value={
                  data.components.ml.available
                    ? data.components.ml.models.join(', ') || 'available'
                    : 'unavailable'
                }
              />
              <ComponentRow
                label="LLM narrative"
                value={data.components.llm_configured ? 'configured' : 'deterministic fallback'}
              />
              {data.simulated_readings > 0 ? (
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-900 ring-1 ring-inset ring-amber-200">
                  {formatNumber(data.simulated_readings, 0)} of{' '}
                  {formatNumber(data.sensor_readings, 0)} sensor readings on this system are
                  simulated, not measured.
                </p>
              ) : null}
            </div>
          </Card>

          <Card flush>
            <CardHeader
              title={`Agents (${data.agents.length})`}
              subtitle="Specialists invoked by the workflow."
              icon={<Bot className="h-4 w-4" aria-hidden="true" />}
            />
            <ul className="divide-y divide-slate-100">
              {data.agents.map((agent) => (
                <li key={agent.name} className="px-5 py-3">
                  <p className="font-mono text-xs font-medium text-slate-800">{agent.name}</p>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
                    {agent.responsibility}
                  </p>
                </li>
              ))}
            </ul>
          </Card>

          <Card flush>
            <CardHeader title="Recent runs" icon={<FileText className="h-4 w-4" aria-hidden="true" />} />
            {data.workflow_runs.recent.length === 0 ? (
              <div className="p-5">
                <EmptyState title="No runs recorded" description="Start one from the AI Advisory page." />
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {data.workflow_runs.recent.map((run) => (
                  <li key={run.id} className="px-5 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-xs text-slate-700">run #{run.id}</span>
                      <StatusBadge status={run.status} />
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      Field #{run.field_id} · {humaniseToken(run.crop ?? 'no crop')} ·{' '}
                      {run.duration_ms ? formatDuration(run.duration_ms) : 'n/a'} ·{' '}
                      {formatDateTime(run.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card flush>
            <CardHeader title="Quick links" />
            <div className="grid gap-2 p-5">
              <Link to="/advisory">
                <Button variant="subtle" className="w-full" icon={<Bot className="h-4 w-4" aria-hidden="true" />}>
                  Run the agent workflow
                </Button>
              </Link>
              <Link to="/irrigation">
                <Button variant="secondary" className="w-full" icon={<Droplets className="h-4 w-4" aria-hidden="true" />}>
                  Irrigation assessment
                </Button>
              </Link>
              <Link to="/reports">
                <Button variant="secondary" className="w-full" icon={<FileText className="h-4 w-4" aria-hidden="true" />}>
                  Generate a PDF report
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ComponentRow({ label, value }: { label: string; value: string }) {
  const status = value.toLowerCase();
  const tone =
    status === 'up' || status.includes('faiss') || status.includes('configured')
      ? 'success'
      : status.includes('unavailable') || status.includes('deterministic') || status.includes('fallback')
        ? 'warning'
        : 'neutral';
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="label-caps pt-0.5">{label}</span>
      <Badge tone={tone} className="max-w-[60%] truncate" title={value}>
        {value}
      </Badge>
    </div>
  );
}

/**
 * Latest advisory for the selected field. Uses the run detail endpoint because
 * the narrative text lives in the run's persisted state.
 */
function LatestAdvisoryCard({ fieldId }: { fieldId: number | null }) {
  const latestRun = useQuery({
    queryKey: queryKeys.latestRun(fieldId ?? -1),
    queryFn: () => getLatestRunForField(fieldId as number),
    enabled: fieldId !== null,
  });

  return (
    <Card flush>
      <CardHeader
        title="Latest advisory"
        subtitle="Most recent multi-agent run for the selected field."
        icon={<Bot className="h-4 w-4" aria-hidden="true" />}
        actions={
          <Link to="/advisory">
            <Button size="sm" variant="secondary">
              Open advisory
            </Button>
          </Link>
        }
      />
      <div className="p-5">
        <FieldGate>
          {latestRun.isLoading ? (
            <SkeletonBlock lines={5} />
          ) : latestRun.error ? (
            <ErrorBanner
              title="Could not load the latest run"
              error={latestRun.error}
              onRetry={() => void latestRun.refetch()}
            />
          ) : !latestRun.data ? (
            <EmptyState
              title="No run for this field yet"
              description="Start the full agent workflow to generate an advisory with its evidence ledger."
              icon={<Bot className="h-5 w-5" aria-hidden="true" />}
            />
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-slate-500">
                  run #{latestRun.data.id} · field #{latestRun.data.field_id}
                </span>
                <StatusBadge status={latestRun.data.status} />
                {latestRun.data.approval_status ? (
                  <Badge tone="warning">
                    Approval {humaniseToken(latestRun.data.approval_status)}
                  </Badge>
                ) : null}
                <span className="text-[11px] text-slate-400">
                  {formatDateTime(latestRun.data.completed_at ?? latestRun.data.created_at)}
                  {latestRun.data.duration_ms ? ` · ${formatDuration(latestRun.data.duration_ms)}` : ''}
                </span>
              </div>
              <p
                className="whitespace-pre-line rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed text-slate-700"
                data-testid="latest-advisory-text"
              >
                {latestRun.data.state.advisory?.advisory ?? 'No advisory text was produced.'}
              </p>
              {(latestRun.data.state.advisory?.safety_notes?.length ?? 0) > 0 ? (
                <ul className="space-y-1">
                  {latestRun.data.state.advisory?.safety_notes?.map((note) => (
                    <li key={note} className="text-[11px] text-amber-800">
                      {note}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}
        </FieldGate>
      </div>
    </Card>
  );
}

export default DashboardPage;
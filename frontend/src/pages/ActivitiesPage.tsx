import { useState } from 'react';
import { CalendarCheck, CalendarClock, ListChecks, Pencil, RefreshCw, Sparkles } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { Badge, StatusBadge, toneForStatus } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { FieldRow, FormGrid, Select, TextInput } from '../components/ui/Field';
import { SkeletonTable } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';
import { EvidenceKindBadge } from '../components/ui/EvidenceKindBadge';
import { FieldGate } from '../components/layout/FieldGate';
import {
  useActivities,
  usePlanActivities,
  useUpdateActivity,
} from '../hooks/useActivities';
import { getUpcomingActivities } from '../api/activities';
import { useLatestRun } from '../hooks/useWorkflow';
import { useSelection } from '../context/SelectionContext';
import { useToast } from '../components/feedback/ToastProvider';
import { useQuery } from '@tanstack/react-query';
import type { ActivityStatus, FarmActivity } from '../api/types';
import { ACTIVITY_STATUSES } from '../api/types';
import { formatDate, formatDateTime, formatNumber, humaniseToken } from '../lib/format';

/**
 * Activities.
 *
 * GET /activities · GET /activities/fields/{id}/upcoming · PATCH /activities/{id} ·
 * POST /activities/plan
 *
 * Status transitions are the only per-activity mutation, because that is the
 * only one the contract exposes. Scheduling work is a proposal; completing it is
 * a human assertion.
 */
export function ActivitiesPage() {
  const { fieldId } = useSelection();
  const [statusFilter, setStatusFilter] = useState('');
  const [upcomingOnly, setUpcomingOnly] = useState(false);
  const [responsiblePerson, setResponsiblePerson] = useState('');

  const activities = useActivities({
    fieldId: fieldId ?? undefined,
    activityStatus: statusFilter || undefined,
  });

  const upcoming = useQuery({
    queryKey: ['activities', fieldId ?? -1, 'upcoming'],
    queryFn: () => getUpcomingActivities(fieldId as number, 14),
    enabled: fieldId !== null && upcomingOnly,
  });

  const latestRun = useLatestRun(fieldId);
  const plan = usePlanActivities();
  const update = useUpdateActivity();
  const toast = useToast();

  const rows = upcomingOnly ? (upcoming.data ?? []) : (activities.data ?? []);
  const completedRun = latestRun.data;

  const runPlan = () => {
    if (!completedRun) return;
    plan.mutate(
      {
        workflowRunId: completedRun.id,
        responsiblePerson: responsiblePerson.trim() || undefined,
      },
      {
        onSuccess: (result) => {
          toast.push({
            tone: 'success',
            title: 'Activity plan generated',
            message: `${result.length} activities scheduled from run #${completedRun.id}.`,
          });
        },
        onError: (error) => toast.pushError(error, 'Could not generate the activity plan'),
      },
    );
  };

  const changeStatus = (activity: FarmActivity, next: ActivityStatus) => {
    update.mutate(
      { activityId: activity.id, payload: { status: next } },
      {
        onSuccess: (result) => {
          toast.push({
            tone: 'success',
            title: 'Activity updated',
            message: `#${result.id} is now ${humaniseToken(result.status).toLowerCase()}.`,
          });
        },
        onError: (error) => toast.pushError(error, 'Could not update the activity'),
      },
    );
  };

  const loading = upcomingOnly ? upcoming.isLoading : activities.isLoading;
  const error = upcomingOnly ? upcoming.error : activities.error;
  const onRetry = () => {
    if (upcomingOnly) void upcoming.refetch();
    else void activities.refetch();
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Activities"
        description="Work the agents propose, and its human-tracked status. Nothing here schedules machinery - it records intent and progress."
        actions={
          <>
            <Button
              variant="secondary"
              loading={loading}
              icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
              onClick={onRetry}
            >
              Refresh
            </Button>
            <Button
              variant="primary"
              disabled={!completedRun || plan.isPending}
              loading={plan.isPending}
              title={
                completedRun
                  ? `Generate the plan from run #${completedRun.id}`
                  : 'Run the AI Advisory workflow first'
              }
              icon={<Sparkles className="h-4 w-4" aria-hidden="true" />}
              onClick={runPlan}
            >
              Generate plan from latest run
            </Button>
          </>
        }
      />

      <FieldGate>
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Activities"
              value={formatNumber(rows.length, 0)}
              hint={upcomingOnly ? 'Scheduled in the next 14 days' : 'All statuses'}
              icon={<ListChecks className="h-4 w-4" aria-hidden="true" />}
            />
            <StatCard
              label="Planned"
              value={formatNumber(rows.filter((row) => row.status === 'planned').length, 0)}
              hint="Awaiting a decision"
            />
            <StatCard
              label="In progress"
              value={formatNumber(rows.filter((row) => row.status === 'in_progress').length, 0)}
              hint="Being worked on now"
            />
            <StatCard
              label="Completed"
              value={formatNumber(rows.filter((row) => row.status === 'completed').length, 0)}
              hint="Signed off by a person"
              tone="brand"
            />
          </div>

          <Card>
            <CardHeader
              title="Filters and planning"
              subtitle="POST /activities/plan turns the most recent completed workflow run into scheduled work."
              icon={<CalendarClock className="h-4 w-4" aria-hidden="true" />}
            />
            <FormGrid className="p-5">
              <FieldRow label="Status" hint="GET /activities?activity_status=">
                {(id) => (
                  <Select
                    id={id}
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                  >
                    <option value="">All statuses</option>
                    {ACTIVITY_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {humaniseToken(status)}
                      </option>
                    ))}
                  </Select>
                )}
              </FieldRow>
              <FieldRow label="Window">
                {(id) => (
                  <Select
                    id={id}
                    value={upcomingOnly ? 'upcoming' : 'all'}
                    onChange={(event) => setUpcomingOnly(event.target.value === 'upcoming')}
                  >
                    <option value="all">Every recorded activity</option>
                    <option value="upcoming">Upcoming only (14 days)</option>
                  </Select>
                )}
              </FieldRow>
              <FieldRow
                label="Responsible person"
                hint="Written onto each generated activity as user-supplied evidence."
              >
                {(id) => (
                  <TextInput
                    id={id}
                    value={responsiblePerson}
                    placeholder="e.g. Ramesh Kumar"
                    onChange={(event) => setResponsiblePerson(event.target.value)}
                  />
                )}
              </FieldRow>
            </FormGrid>
            {plan.error ? (
              <div className="px-5 pb-5">
                <ErrorBanner title="Could not generate the activity plan" error={plan.error} />
              </div>
            ) : null}
            {completedRun ? (
              <p className="px-5 pb-5 text-xs text-slate-500">
                Latest run: <span className="font-medium text-slate-700">#{completedRun.id}</span>{' '}
                <StatusBadge status={completedRun.status} /> for field{' '}
                <span className="font-medium text-slate-700">{completedRun.field_id}</span>
                {completedRun.crop ? ` · ${completedRun.crop}` : ''} ·{' '}
                {formatDateTime(completedRun.created_at)}
              </p>
            ) : (
              <p className="px-5 pb-5 text-xs text-slate-500">
                This field has no workflow run yet. Open{' '}
                <strong className="font-medium text-slate-700">AI Advisory</strong> and start a run
                first - activities are generated from a completed run, never invented here.
              </p>
            )}
          </Card>

          <Card flush>
            <CardHeader
              title={`Activities (${rows.length})`}
              subtitle={
                upcomingOnly
                  ? 'GET /activities/fields/{field_id}/upcoming?days=14'
                  : 'GET /activities?field_id='
              }
              icon={<CalendarCheck className="h-4 w-4" aria-hidden="true" />}
            />
            {loading ? (
              <SkeletonTable rows={5} columns={6} />
            ) : error ? (
              <ErrorBanner className="m-5" title="Could not load activities" error={error} onRetry={onRetry} />
            ) : rows.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No activities"
                  description={
                    upcomingOnly
                      ? 'Nothing is scheduled in the next 14 days.'
                      : 'No activities recorded for this field yet.'
                  }
                  icon={<CalendarCheck className="h-5 w-5" aria-hidden="true" />}
                />
              </div>
            ) : (
              <DataTable<FarmActivity>
                columns={[
                  {
                    key: 'title',
                    header: 'Activity',
                    render: (row) => (
                      <div className="min-w-[12rem]">
                        <p className="text-xs font-medium text-slate-800">{row.title}</p>
                        <p className="text-[11px] text-slate-400">{humaniseToken(row.activity_type)}</p>
                      </div>
                    ),
                  },
                  {
                    key: 'scheduled',
                    header: 'Scheduled',
                    render: (row) => (
                      <span className="whitespace-nowrap text-xs text-slate-700">
                        {formatDate(row.scheduled_date)}
                        <span className="ml-1 text-slate-400">
                          ({formatNumber(row.window_days, 0)} d window)
                        </span>
                      </span>
                    ),
                  },
                  {
                    key: 'priority',
                    header: 'Priority',
                    render: (row) => <Badge tone={toneForStatus(row.priority)}>{humaniseToken(row.priority)}</Badge>,
                  },
                  {
                    key: 'status',
                    header: 'Status',
                    render: (row) => <StatusBadge status={row.status} />,
                  },
                  {
                    key: 'change',
                    header: 'Move to',
                    headerClassName: 'w-40',
                    render: (row) => (
                      <label className="flex items-center gap-1.5">
                        <span className="sr-only">
                          New status for activity {row.title} (PATCH /activities/{row.id})
                        </span>
                        <Pencil className="h-3 w-3 shrink-0 text-slate-400" aria-hidden="true" />
                        <Select
                          aria-label={`New status for activity ${row.title}`}
                          className="h-8 py-1 text-xs"
                          value={row.status}
                          disabled={update.isPending}
                          onChange={(event) => changeStatus(row, event.target.value as ActivityStatus)}
                        >
                          {ACTIVITY_STATUSES.map((status) => (
                            <option key={status} value={status}>
                              {humaniseToken(status)}
                            </option>
                          ))}
                        </Select>
                      </label>
                    ),
                  },
                  {
                    key: 'owner',
                    header: 'Responsible',
                    render: (row) => (
                      <span className="text-xs text-slate-600">{row.responsible_person ?? '-'}</span>
                    ),
                  },
                  {
                    key: 'reason',
                    header: 'Reason',
                    render: (row) => (
                      <span className="block max-w-md text-xs leading-relaxed text-slate-600">
                        {row.reason}
                      </span>
                    ),
                  },
                  {
                    key: 'evidence',
                    header: 'Evidence',
                    render: (row) =>
                      row.evidence.length === 0 ? (
                        <span className="text-xs text-slate-400">-</span>
                      ) : (
                        <span className="flex flex-wrap gap-1">
                          {row.evidence.slice(0, 3).map((item, index) => (
                            <EvidenceKindBadge key={`${item.label}-${index}`} kind={item.kind} />
                          ))}
                          {row.evidence.length > 3 ? (
                            <span className="text-[11px] text-slate-400">
                              +{row.evidence.length - 3}
                            </span>
                          ) : null}
                        </span>
                      ),
                  },
                ]}
                rows={rows}
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

export default ActivitiesPage;
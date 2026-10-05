import { useState } from 'react';
import { Download, FileText, FilePlus2, Loader2, Trash2 } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { Badge, StatusBadge } from '../components/ui/Badge';
import { toneForStatus } from '../components/ui/badgeTones';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { SkeletonTable } from '../components/ui/Skeleton';
import { StatCard } from '../components/ui/StatCard';
import { FieldGate } from '../components/layout/FieldGate';
import { useCreateReport, useDeleteReport, useReports } from '../hooks/useReports';
import { useLatestRun } from '../hooks/useWorkflow';
import { resolveApiUrl } from '../api/client';
import { useSelection } from '../context/SelectionContext';
import { useToast } from '../components/feedback/ToastProvider';
import type { Report } from '../api/types';
import { formatBytes, formatDateTime, formatNumber, humaniseToken } from '../lib/format';

/**
 * Reports.
 *
 * GET /reports · POST /reports?field_id=N · DELETE /reports/{id} ·
 * GET /reports/{id}/download
 *
 * The download link is built from the server-supplied `download_url` via
 * `resolveApiUrl`, so it honours the relative path the backend returns
 * (`/api/v1/reports/1/download`) and goes through the dev proxy like every other
 * call. Nothing is hardcoded to a backend host.
 */
export function ReportsPage() {
  const { fieldId } = useSelection();
  const reports = useReports(fieldId ?? undefined);
  const create = useCreateReport();
  const remove = useDeleteReport();
  const latestRun = useLatestRun(fieldId);
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const rows = reports.data ?? [];
  const completedRun = latestRun.data;

  const generate = () => {
    if (fieldId === null || !completedRun) return;
    create.mutate(
      { fieldId, workflowRunId: completedRun.id },
      {
        onSuccess: (report) => {
          toast.push({
            tone: 'success',
            title: 'Report generated',
            message: `Report #${report.id} · ${report.page_count ?? '?'} pages, ready to download.`,
          });
        },
        onError: (error) => toast.pushError(error, 'Could not generate the report'),
      },
    );
  };

  const destroy = (report: Report) => {
    remove.mutate(
      { reportId: report.id },
      {
        onSuccess: () => {
          setConfirmDelete(null);
          toast.push({ tone: 'success', title: 'Report deleted', message: `Report #${report.id} removed.` });
        },
        onError: (error) => toast.pushError(error, 'Could not delete the report'),
      },
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="PDF reports rendered from a completed workflow run, including its evidence ledger and citations."
        actions={
          <Button
            variant="primary"
            disabled={fieldId === null || !completedRun}
            loading={create.isPending}
            title={
              completedRun
                ? `Generate from run #${completedRun.id}`
                : 'This field has no workflow run yet'
            }
            icon={<FilePlus2 className="h-4 w-4" aria-hidden="true" />}
            onClick={generate}
          >
            Generate report
          </Button>
        }
      />

      <FieldGate>
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Reports"
              value={formatNumber(rows.length, 0)}
              hint="For the selected field"
              icon={<FileText className="h-4 w-4" aria-hidden="true" />}
            />
            <StatCard
              label="Ready to download"
              value={formatNumber(rows.filter((row) => row.status === 'ready').length, 0)}
              hint="Rendered successfully"
            />
            <StatCard
              label="Total pages"
              value={formatNumber(
                rows.reduce((total, row) => total + (row.page_count ?? 0), 0),
                0,
              )}
              hint="Across every report"
            />
            <StatCard
              label="Evidence items cited"
              value={formatNumber(
                rows.reduce((total, row) => total + (row.section_summary.evidence_items ?? 0), 0),
                0,
              )}
              hint="Provenance-tagged facts embedded"
              tone="brand"
            />
          </div>

          {completedRun ? (
            <Card>
              <CardHeader
                title="Report source run"
                subtitle="POST /reports?field_id=N with a JSON body carrying workflow_run_id."
                icon={<FileText className="h-4 w-4" aria-hidden="true" />}
              />
              <div className="flex flex-wrap items-center gap-3 p-5 text-xs text-slate-600">
                <span className="flex items-center gap-2">
                  Run <span className="font-medium text-slate-800">#{completedRun.id}</span>
                  <StatusBadge status={completedRun.status} />
                </span>
                {completedRun.crop ? (
                  <span>
                    crop <span className="font-medium text-slate-800">{completedRun.crop}</span>
                  </span>
                ) : null}
                <span>{formatDateTime(completedRun.created_at)}</span>
                <span>{completedRun.agents_invoked.length} agents</span>
                <Button
                  size="sm"
                  variant="subtle"
                  className="ml-auto"
                  loading={create.isPending}
                  onClick={generate}
                >
                  Generate from this run
                </Button>
              </div>
            </Card>
          ) : (
            <Card>
              <CardHeader title="No source run available" />
              <div className="p-5">
                <EmptyState
                  title="This field has no workflow run"
                  description="A report is always rendered from a completed run. Start one on the AI Advisory page first."
                  icon={<FileText className="h-5 w-5" aria-hidden="true" />}
                />
              </div>
            </Card>
          )}

          {create.error ? (
            <ErrorBanner title="Could not generate the report" error={create.error} />
          ) : null}
          {remove.error ? <ErrorBanner title="Could not delete the report" error={remove.error} /> : null}

          <Card flush>
            <CardHeader
              title={`Generated reports (${rows.length})`}
              subtitle={
                fieldId === null
                  ? 'GET /reports'
                  : `GET /reports?field_id=${fieldId}`
              }
              icon={<FileText className="h-4 w-4" aria-hidden="true" />}
            />
            {reports.isLoading ? (
              <SkeletonTable rows={4} columns={6} />
            ) : reports.error ? (
              <ErrorBanner
                className="m-5"
                title="Could not load reports"
                error={reports.error}
                onRetry={() => void reports.refetch()}
              />
            ) : rows.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  title="No reports yet"
                  description="Generate a report from the completed run above to produce a downloadable PDF."
                  icon={<FileText className="h-5 w-5" aria-hidden="true" />}
                  action={
                    <Button variant="primary" disabled={!completedRun} onClick={generate}>
                      Generate report
                    </Button>
                  }
                />
              </div>
            ) : (
              <DataTable<Report>
                columns={[
                  {
                    key: 'title',
                    header: 'Report',
                    render: (row) => (
                      <div className="min-w-[12rem]">
                        <p className="text-xs font-medium text-slate-800">{row.title}</p>
                        <p className="text-[11px] text-slate-400">
                          #{row.id} · field #{row.field_id}
                          {row.workflow_run_id ? ` · run #${row.workflow_run_id}` : ''}
                        </p>
                      </div>
                    ),
                  },
                  {
                    key: 'status',
                    header: 'Status',
                    render: (row) => <StatusBadge status={row.status} />,
                  },
                  {
                    key: 'pages',
                    header: 'Pages',
                    className: 'tabular',
                    render: (row) => formatNumber(row.page_count, 0),
                  },
                  {
                    key: 'size',
                    header: 'Size',
                    className: 'tabular',
                    render: (row) => formatBytes(row.size_bytes),
                  },
                  {
                    key: 'sections',
                    header: 'Contents',
                    render: (row) => <SectionChips report={row} />,
                  },
                  {
                    key: 'created',
                    header: 'Created',
                    render: (row) => (
                      <span className="whitespace-nowrap text-xs text-slate-500">
                        {formatDateTime(row.created_at)}
                      </span>
                    ),
                  },
                  {
                    key: 'download',
                    header: 'Actions',
                    headerClassName: 'w-52',
                    render: (row) => <ReportActions report={row} onDelete={destroy} confirming={confirmDelete === row.id} onConfirm={() => setConfirmDelete(row.id)} onCancel={() => setConfirmDelete(null)} busy={remove.isPending} />,
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

function SectionChips({ report }: { report: Report }) {
  const sections = report.section_summary.sections ?? [];
  const summary = report.section_summary;
  if (sections.length === 0) {
    return (
      <span className="text-xs text-slate-400">
        {summary.section_count ? `${summary.section_count} sections` : 'not recorded'}
      </span>
    );
  }
  return (
    <span className="flex flex-wrap gap-1">
      {sections.slice(0, 4).map((section) => (
        <Badge key={section} tone={toneForStatus(section)}>
          {humaniseToken(section)}
        </Badge>
      ))}
      {sections.length > 4 ? (
        <span className="text-[11px] text-slate-400">+{sections.length - 4}</span>
      ) : null}
    </span>
  );
}

function ReportActions({
  report,
  onDelete,
  confirming,
  onConfirm,
  onCancel,
  busy,
}: {
  report: Report;
  onDelete: (report: Report) => void;
  confirming: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const href = resolveApiUrl(report.download_url);

  if (report.status !== 'ready' || !href) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-slate-400">
        {report.status === 'generating' ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            rendering
          </>
        ) : report.error ? (
          <span title={report.error}>generation failed</span>
        ) : (
          'not downloadable'
        )}
      </span>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <a
        href={href}
        target="_blank"
        rel="noreferrer noopener"
        download={report.file_name ?? undefined}
        data-testid="report-download"
        className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50"
      >
        <Download className="h-3.5 w-3.5" aria-hidden="true" />
        PDF
      </a>
      {confirming ? (
        <>
          <Button
            size="sm"
            variant="danger"
            loading={busy}
            onClick={() => onDelete(report)}
            aria-label={`Confirm deleting report ${report.title}`}
          >
            Confirm
          </Button>
          <Button size="sm" variant="ghost" onClick={onCancel} aria-label="Cancel delete">
            Cancel
          </Button>
        </>
      ) : (
        <Button
          size="sm"
          variant="ghost"
          onClick={onConfirm}
          aria-label={`Delete report ${report.title}`}
          icon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
        >
          Delete
        </Button>
      )}
    </div>
  );
}

export default ReportsPage;
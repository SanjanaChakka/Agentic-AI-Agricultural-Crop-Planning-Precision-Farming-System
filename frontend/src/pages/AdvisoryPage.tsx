import { useMemo, useState } from 'react';
import {
  Brain,
  Check,
  ChevronDown,
  Cpu,
  FileSearch,
  Gavel,
  Pencil,
  Play,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge, StatusBadge } from '../components/ui/Badge';
import { toneForStatus } from '../components/ui/badgeTones';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Checkbox, FieldGroup, FieldRow, FormGrid, TextArea, TextInput } from '../components/ui/Field';
import { SkeletonBlock, SkeletonTable } from '../components/ui/Skeleton';
import { RunProgress } from '../components/ui/Spinner';
import { StatCard } from '../components/ui/StatCard';
import { EvidenceLedger, ReferenceList } from '../components/evidence/EvidenceLedger';
import { RiskBadge } from '../components/ui/RiskBadge';
import { FieldGate } from '../components/layout/FieldGate';
import {
  useLatestRun,
  useRunSummary,
  useRunTraces,
  useStartWorkflowRun,
} from '../hooks/useWorkflow';
import {
  useApprovals,
  useDecideApproval,
  usePendingApprovals,
  useRequestReanalysis,
  useSafetyContract,
} from '../hooks/useApprovals';
import { useSelection } from '../context/SelectionContext';
import { useToast } from '../components/feedback/ToastProvider';
import type {
  AgentTrace,
  Approval,
  ApprovalStatus,
  Evidence,
  MLPrediction,
  SafetyContract,
  SourceReference,
  WorkflowRunDetail,
  WorkflowRunSummary,
} from '../api/types';
import { formatDateTime, formatDuration, formatNumber, humaniseToken } from '../lib/format';

/**
 * AI Advisory.
 *
 * POST /workflow/runs · GET /workflow/runs/field/{id}/latest ·
 * GET /workflow/runs/{id}/summary · GET /workflow/runs/{id}/traces ·
 * GET /approvals · GET /approvals/pending · GET /approvals/safety-contract ·
 * POST /approvals/{id}/decision · POST /workflow/runs/{id}/reanalyse
 *
 * This is the page where a human authorises (or does not) a plan. Every control
 * here maps to a real endpoint; there is nothing decorative.
 */

/** Streaming progress text while the twelve agents execute. */
const RUN_STEPS = [
  'Telemetry agent',
  'Soil interpretation agent',
  'Weather retrieval agent',
  'Knowledge retrieval agent',
  'ML inference agent',
  'Crop suitability agent',
  'Irrigation agent',
  'Crop risk agent',
  'Alert agent',
  'Activity planner',
  'Narrative agent',
  'Approval agent',
];

type AdvisoryAction = 'approved' | 'rejected' | 'modified' | 'reanalysis';

export function AdvisoryPage() {
  const { fieldId } = useSelection();
  const startRun = useStartWorkflowRun();

  const latestRun = useLatestRun(fieldId);
  const runId = latestRun.data?.id ?? null;
  const summary = useRunSummary(runId);
  const traces = useRunTraces(runId);
  const pending = usePendingApprovals();
  const approvals = useApprovals(fieldId ?? undefined);
  const safetyContract = useSafetyContract();
  const toast = useToast();

  const [form, setForm] = useState({
    crop: '',
    notes: '',
    responsible_person: '',
    force_refresh_weather: false,
    simulate_sensors_if_missing: false,
    include_approved_only: false,
  });

  const [lastRunSummary, setLastRunSummary] = useState<WorkflowRunSummary | null>(null);

  const advisory = latestRun.data?.state?.advisory ?? null;
  const evidence: Evidence[] = useMemo(
    () => summary.data?.evidence ?? [],
    [summary.data],
  );
  const sources: SourceReference[] = useMemo(
    () => summary.data?.sources ?? [],
    [summary.data],
  );

  const start = () => {
    if (fieldId === null) return;
    startRun.mutate(
      {
        field_id: fieldId,
        crop: form.crop.trim() || null,
        force_refresh_weather: form.force_refresh_weather,
        simulate_sensors_if_missing: form.simulate_sensors_if_missing,
        include_approved_only: form.include_approved_only,
        responsible_person: form.responsible_person.trim() || null,
        notes: form.notes.trim() || null,
      },
      {
        onSuccess: (result) => {
          setLastRunSummary(result);
          toast.push({
            tone: 'success',
            title: 'Agent run finished',
            message: `Run #${result.workflow_run_id} completed with status ${humaniseToken(result.status)}.`,
          });
        },
        onError: (error) => toast.pushError(error, 'The agent run failed'),
      },
    );
  };

  const pendingForField = (pending.data ?? []).filter(
    (approval) => approval.field_id === fieldId,
  );
  const allPending = pending.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Human-in-the-loop"
        title="AI Advisory"
        description="Run the multi-agent planning cycle for the selected field, read the narrative with its full evidence ledger, then authorise, modify or reject the plan."
        actions={
          <Button
            variant="primary"
            disabled={fieldId === null}
            loading={startRun.isPending}
            title={fieldId === null ? 'Select a field first' : undefined}
            icon={<Play className="h-4 w-4" aria-hidden="true" />}
            onClick={start}
          >
            Start agent run
          </Button>
        }
      />

      <FieldGate>
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Run configuration"
              subtitle="POST /workflow/runs - twelve specialised agents execute against live soil, telemetry and forecast data."
              icon={<Sparkles className="h-4 w-4" aria-hidden="true" />}
            />
            <FormGrid className="p-5">
              <FieldRow label="Crop" hint="Blank uses the field's proposed crop.">
                {(id) => (
                  <TextInput
                    id={id}
                    value={form.crop}
                    placeholder="e.g. Cotton"
                    onChange={(event) => setForm((c) => ({ ...c, crop: event.target.value }))}
                  />
                )}
              </FieldRow>
              <FieldRow label="Responsible person" hint="Recorded as user-supplied evidence.">
                {(id) => (
                  <TextInput
                    id={id}
                    value={form.responsible_person}
                    placeholder="e.g. Ramesh Kumar"
                    onChange={(event) =>
                      setForm((c) => ({ ...c, responsible_person: event.target.value }))
                    }
                  />
                )}
              </FieldRow>
              <FieldGroup label="Run options">
                <div className="space-y-2 pt-1">
                  <Checkbox
                    label="Force-refresh the weather forecast"
                    hint="Bypasses the cache so the agents see the newest provider data."
                    checked={form.force_refresh_weather}
                    onChange={(event) =>
                      setForm((c) => ({ ...c, force_refresh_weather: event.target.checked }))
                    }
                  />
                  <Checkbox
                    label="Simulate sensors if telemetry is missing"
                    hint="Generates flagged synthetic readings so the run is not blocked by an absent probe."
                    checked={form.simulate_sensors_if_missing}
                    onChange={(event) =>
                      setForm((c) => ({ ...c, simulate_sensors_if_missing: event.target.checked }))
                    }
                  />
                  <Checkbox
                    label="Approved activities only"
                    hint="Carry forward only work a human has already authorised."
                    checked={form.include_approved_only}
                    onChange={(event) =>
                      setForm((c) => ({ ...c, include_approved_only: event.target.checked }))
                    }
                  />
                </div>
              </FieldGroup>
              <FieldRow label="Notes for this run" className="sm:col-span-2 lg:col-span-3">
                {(id) => (
                  <TextArea
                    id={id}
                    value={form.notes}
                    placeholder="Anything the agents should know about this field right now."
                    onChange={(event) => setForm((c) => ({ ...c, notes: event.target.value }))}
                  />
                )}
              </FieldRow>
            </FormGrid>
            {startRun.error ? (
              <div className="px-5 pb-5">
                <ErrorBanner title="The agent run failed" error={startRun.error} />
              </div>
            ) : null}
          </Card>

          {startRun.isPending ? (
            <RunProgress steps={RUN_STEPS} label="Running the twelve agents..." />
          ) : null}

          {lastRunSummary && !startRun.isPending ? (
            <RunStatusCard summary={lastRunSummary} isFresh />
          ) : null}

          {latestRun.isLoading ? (
            <Card>
              <SkeletonBlock lines={5} />
            </Card>
          ) : latestRun.error ? (
            <ErrorBanner
              title="Could not load the latest run"
              error={latestRun.error}
              onRetry={() => void latestRun.refetch()}
            />
          ) : !latestRun.data ? (
            <EmptyState
              title="No workflow run yet for this field"
              description="Start an agent run above. The narrative, evidence ledger and approval request all arrive with it."
              icon={<Brain className="h-5 w-5" aria-hidden="true" />}
              action={
                <Button variant="primary" loading={startRun.isPending} onClick={start}>
                  Start the first run
                </Button>
              }
            />
          ) : (
            <RunStatusCard summary={summary.data} run={latestRun.data} />
          )}

          {/* Narrative: the run detail's `state.advisory` is the only place the
              full advisory text is served - the summary omits the narrative. */}
          <AdvisoryNarrative
            loading={latestRun.isLoading}
            advisoryText={advisory?.advisory ?? null}
            narrativeSource={advisory?.narrative_source ?? null}
            model={advisory?.model ?? null}
            warnings={advisory?.warnings ?? []}
            safetyNotes={advisory?.safety_notes ?? []}
            deterministicFallback={advisory?.deterministic_fallback ?? null}
          />

          <div className="grid gap-6 xl:grid-cols-2">
            <EvidenceLedger
              evidence={evidence}
              title="Run evidence ledger"
              subtitle="GET /workflow/runs/{id}/summary - every provenance-tagged fact behind this run."
              groupByKind
            />
            <AgentTraceList
              loading={traces.isLoading}
              error={traces.error}
              traces={traces.data ?? []}
              onRetry={() => void traces.refetch()}
            />
          </div>

          <MlPredictionsPanel
            loading={summary.isLoading}
            predictions={summary.data?.ml_predictions ?? []}
          />

          {sources.length > 0 ? <ReferenceList sources={sources} title="References cited" /> : null}

          <SafetyContractCard contract={safetyContract.data} loading={safetyContract.isLoading} />

          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-slate-900">
                Pending human authorisation ({pendingForField.length})
              </h2>
              {allPending.length > pendingForField.length ? (
                <span className="text-xs text-slate-500">
                  {allPending.length} pending across all fields
                </span>
              ) : null}
            </div>

            {pending.isLoading ? (
              <Card flush>
                <SkeletonTable rows={2} columns={4} />
              </Card>
            ) : pendingForField.length === 0 ? (
              <EmptyState
                title="Nothing awaiting authorisation"
                description="No plan for this field is waiting on a human decision."
                icon={<Gavel className="h-5 w-5" aria-hidden="true" />}
              />
            ) : (
              pendingForField.map((approval) => (
                <ApprovalPanel key={approval.id} approval={approval} />
              ))
            )}
          </div>

          <DecisionHistory
            loading={approvals.isLoading}
            error={approvals.error}
            approvals={(approvals.data ?? []).filter((approval) => approval.status !== 'pending')}
            onRetry={() => void approvals.refetch()}
          />
        </div>
      </FieldGate>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Run status                                                          */
/* ------------------------------------------------------------------ */

export function RunStatusCard({
  summary,
  run,
  isFresh = false,
}: {
  summary: WorkflowRunSummary | undefined;
  run?: WorkflowRunDetail | null;
  isFresh?: boolean;
}) {
  if (!summary && !run) return null;

  const status = run?.status ?? summary?.status ?? 'unknown';
  const crop = run?.crop ?? summary?.crop ?? null;
  const agents = run?.agents_invoked ?? summary?.agents_invoked ?? [];
  const warnings = run?.warnings ?? summary?.warnings ?? [];
  const duration = run?.duration_ms ?? summary?.duration_ms ?? null;
  const completedAt = run?.completed_at ?? summary?.completed_at ?? null;

  return (
    <Card flush data-testid="run-status">
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            Run #{summary?.workflow_run_id ?? run?.id ?? '-'}
            <StatusBadge status={status} />
            {isFresh ? <Badge tone="success">just completed</Badge> : null}
          </span>
        }
        subtitle={
          summary
            ? `${summary.farm_name} · ${summary.field_name}${crop ? ` · ${crop}` : ''}`
            : `Field ${run?.field_id ?? '-'}`
        }
        icon={<Brain className="h-4 w-4" aria-hidden="true" />}
      />
      <div className="space-y-5 p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Risk level"
            value={<RiskBadge severity={summary?.risk_level ?? 'none'} qualifier="overall" />}
            hint={`${summary?.risk_findings.length ?? 0} finding(s)`}
          />
          <StatCard
            label="Duration"
            value={formatDuration(duration)}
            hint={completedAt ? `Completed ${formatDateTime(completedAt)}` : 'Still running'}
          />
          <StatCard
            label="Agents invoked"
            value={formatNumber(agents.length, 0)}
            hint={`${agents.length} of 12 specialisations`}
            icon={<Cpu className="h-4 w-4" aria-hidden="true" />}
          />
          <StatCard
            label="Approval"
            value={summary?.approval ? humaniseToken(summary.approval.status) : 'none requested'}
            hint={summary?.approval ? `Approval #${summary.approval.id}` : 'No action required'}
          />
        </div>

        {warnings.length > 0 ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-900">
              <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
              Warnings from this run ({warnings.length})
            </p>
            <ul className="mt-1 list-inside list-disc text-xs text-amber-900/85">
              {warnings.map((warning) => (
                <li key={warning} className="leading-relaxed">
                  {warning}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div>
          <p className="label-caps">Agent sequence</p>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {agents.map((agent) => (
              <li key={agent}>
                <Badge tone="brand">{humaniseToken(agent)}</Badge>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Advisory narrative                                                  */
/* ------------------------------------------------------------------ */

export function AdvisoryNarrative({
  loading,
  advisoryText,
  narrativeSource,
  model,
  warnings,
  safetyNotes,
  deterministicFallback,
}: {
  loading: boolean;
  advisoryText: string | null;
  narrativeSource: string | null;
  model: string | null;
  warnings: string[];
  safetyNotes: string[];
  deterministicFallback: string | null;
}) {
  if (loading) {
    return (
      <Card>
        <SkeletonBlock lines={6} />
      </Card>
    );
  }

  return (
    <Card flush data-testid="advisory-panel">
      <CardHeader
        title="Advisory"
        subtitle="GET /workflow/runs/{id} · state.advisory - composed from the run's own evidence."
        icon={<Brain className="h-4 w-4" aria-hidden="true" />}
        actions={
          narrativeSource ? (
            <Badge tone={narrativeSource === 'deterministic' ? 'neutral' : 'violet'}>
              {narrativeSource === 'deterministic' ? 'Rule narrative' : 'LLM narrative'}
              {narrativeSource === 'deterministic' ? '' : ` · ${model ?? 'model'}`}
            </Badge>
          ) : null
        }
      />
      <div className="space-y-4 p-5">
        {advisoryText ? (
          <p
            className="whitespace-pre-line text-sm leading-relaxed text-slate-800"
            data-testid="latest-advisory-text"
          >
            {advisoryText}
          </p>
        ) : (
          <EmptyState
            title="No advisory text"
            description="The run did not produce a narrative. Check the warnings above and the agent traces below."
            icon={<FileSearch className="h-5 w-5" aria-hidden="true" />}
          />
        )}

        {deterministicFallback ? (
          <div className="rounded-lg bg-slate-50 p-3 ring-1 ring-inset ring-slate-200">
            <p className="label-caps">Deterministic fallback</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-600">{deterministicFallback}</p>
          </div>
        ) : null}

        {safetyNotes.length > 0 ? (
          <div className="rounded-lg border-l-4 border-brand-500 bg-brand-50/60 px-4 py-3">
            <p className="text-xs font-semibold text-brand-900">Safety notes from the agents</p>
            <ul className="mt-1 list-inside list-disc text-xs leading-relaxed text-brand-900/85">
              {safetyNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {warnings.length > 0 ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
            <p className="text-xs font-semibold text-amber-900">Warnings</p>
            <ul className="mt-1 list-inside list-disc text-xs leading-relaxed text-amber-900/85">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Agent traces                                                        */
/* ------------------------------------------------------------------ */

export function AgentTraceList({
  loading,
  error,
  traces,
  onRetry,
}: {
  loading: boolean;
  error: unknown;
  traces: AgentTrace[];
  onRetry: () => void;
}) {
  return (
    <Card flush data-testid="agent-trace-list">
      <CardHeader
        title={`Per-agent trace (${traces.length})`}
        subtitle="GET /workflow/runs/{id}/traces - inputs, outputs and reasoning recorded per agent."
        icon={<Cpu className="h-4 w-4" aria-hidden="true" />}
      />
      {loading ? (
        <div className="p-5">
          <SkeletonBlock lines={6} />
        </div>
      ) : error ? (
        <ErrorBanner className="m-5" title="Could not load agent traces" error={error} onRetry={onRetry} />
      ) : traces.length === 0 ? (
        <div className="p-5">
          <EmptyState title="No traces" description="This run recorded no agent traces." />
        </div>
      ) : (
        <ol className="divide-y divide-slate-100">
          {traces.map((trace) => (
            <li key={trace.id}>
              <details className="group px-5 py-3.5">
                <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
                  <span className="tabular w-6 shrink-0 text-[11px] text-slate-400">
                    {trace.sequence}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-800">
                    {trace.agent_name}
                  </span>
                  <StatusBadge status={trace.status} />
                  <span className="tabular text-[11px] text-slate-400">
                    {formatDuration(trace.duration_ms)}
                  </span>
                  <ChevronDown
                    className="h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform group-open:rotate-180"
                    aria-hidden="true"
                  />
                </summary>
                <div className="mt-3 space-y-3 pl-8">
                  <p className="text-xs text-slate-500">{trace.responsibility}</p>
                  {trace.reasoning ? (
                    <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-700">
                      {trace.reasoning}
                    </p>
                  ) : null}
                  {trace.error ? (
                    <ErrorBanner title={`${trace.agent_name} failed`} error={new Error(trace.error)} />
                  ) : null}
                  <TraceBlock title="Input summary" value={trace.input_summary} />
                  <TraceBlock title="Output" value={trace.output} />
                  {trace.evidence.length > 0 ? (
                    <div>
                      <p className="label-caps">Evidence ({trace.evidence.length})</p>
                      <ul className="mt-1 space-y-0.5">
                        {trace.evidence.slice(0, 8).map((item, index) => (
                          <li key={`${item.label}-${index}`} className="text-[11px] text-slate-600">
                            <span className="font-medium text-slate-700">{item.label}</span>:{' '}
                            {item.value === null || item.value === undefined ? '-' : String(item.value)}
                            {item.unit ? ` ${item.unit}` : ''}
                            <span className="ml-1 font-mono text-slate-400">({item.kind})</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {trace.sources.length > 0 ? (
                    <div>
                      <p className="label-caps">Sources ({trace.sources.length})</p>
                      <ul className="mt-1 space-y-0.5">
                        {trace.sources.map((source) => (
                          <li key={source.doc_key} className="text-[11px] text-slate-600">
                            {source.url ? (
                              <a
                                href={source.url}
                                target="_blank"
                                rel="noreferrer noopener"
                                className="text-brand-800 underline underline-offset-2"
                              >
                                {source.title}
                              </a>
                            ) : (
                              source.title
                            )}
                            <span className="ml-1 font-mono text-slate-400">{source.doc_key}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  <p className="text-[11px] text-slate-400">
                    {trace.model_used ? `model: ${trace.model_used} · ` : ''}
                    {formatDateTime(trace.created_at)}
                  </p>
                </div>
              </details>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function TraceBlock({ title, value }: { title: string; value: Record<string, unknown> }) {
  const keys = Object.keys(value ?? {});
  if (keys.length === 0) return null;
  return (
    <div>
      <p className="label-caps">{title}</p>
      <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-900/95 p-3 font-mono text-[11px] leading-relaxed text-slate-100">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* ML predictions                                                      */
/* ------------------------------------------------------------------ */

function MlPredictionsPanel({ loading, predictions }: { loading: boolean; predictions: MLPrediction[] }) {
  return (
    <Card flush>
      <CardHeader
        title={`Machine-learning predictions (${predictions.length})`}
        subtitle="Attached to this run. The models grade or forecast; they do not diagnose."
        icon={<Cpu className="h-4 w-4" aria-hidden="true" />}
      />
      {loading ? (
        <div className="p-5">
          <SkeletonBlock lines={4} />
        </div>
      ) : predictions.length === 0 ? (
        <div className="p-5">
          <EmptyState
            title="No ML predictions on this run"
            description="The inference agent produced nothing for this field."
          />
        </div>
      ) : (
        <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
          {predictions.map((prediction) => (
            <div key={prediction.id} className="rounded-lg border border-slate-200 p-4">
              <p className="label-caps">{humaniseToken(prediction.task)}</p>
              <p className="mt-1.5 flex flex-wrap items-baseline gap-2">
                <span className="text-lg font-semibold text-slate-900">
                  {prediction.prediction_label ?? formatNumber(prediction.prediction_value, 2)}
                </span>
                {prediction.unit ? (
                  <span className="text-xs text-slate-500">{prediction.unit}</span>
                ) : null}
                <Badge tone={toneForStatus(prediction.status)}>{humaniseToken(prediction.status)}</Badge>
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                {prediction.model_name} v{prediction.model_version}
                {prediction.confidence !== null && prediction.confidence !== undefined
                  ? ` · confidence ${formatNumber(prediction.confidence, 2)}`
                  : ''}
                {prediction.horizon_days ? ` · ${prediction.horizon_days} day horizon` : ''}
              </p>
              {prediction.message ? (
                <p className="mt-2 text-xs leading-relaxed text-slate-600">{prediction.message}</p>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Safety contract                                                     */
/* ------------------------------------------------------------------ */

function SafetyContractCard({
  contract,
  loading,
}: {
  contract: SafetyContract | undefined;
  loading: boolean;
}) {
  return (
    <Card flush>
      <CardHeader
        title="What a human decision does and does not do"
        subtitle="GET /approvals/safety-contract - the contract enforced by the backend."
        icon={<ShieldAlert className="h-4 w-4" aria-hidden="true" />}
      />
      {loading ? (
        <div className="p-5">
          <SkeletonBlock lines={4} />
        </div>
      ) : !contract ? (
        <div className="p-5">
          <EmptyState title="Contract unavailable" description="The endpoint returned nothing." />
        </div>
      ) : (
        <dl className="divide-y divide-slate-100">
          {(
            [
              ['Approve', contract.approved, 'success'],
              ['Reject', contract.rejected, 'danger'],
              ['Modify', contract.modified, 'violet'],
              ['Request re-analysis', contract.reanalysis_requested, 'warning'],
              ['Never', contract.never, 'slate'],
            ] as const
          ).map(([label, text, tone]) => (
            <div key={label} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 py-3">
              <dt className="w-40 shrink-0">
                <Badge tone={tone}>{label}</Badge>
              </dt>
              <dd className="min-w-0 flex-1 text-xs leading-relaxed text-slate-600">{text}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Approval panel                                                      */
/* ------------------------------------------------------------------ */

const ACTION_LABELS: Record<AdvisoryAction, string> = {
  approved: 'Approve',
  rejected: 'Reject',
  modified: 'Modify',
  reanalysis: 'Request re-analysis',
};

/**
 * One pending approval with all four real decision paths.
 *
 * - Approve / Reject / Modify  -> POST /approvals/{id}/decision
 * - Request re-analysis        -> POST /approvals/{id}/decision (flagging the
 *   observation) followed by POST /workflow/runs/{run_id}/reanalyse
 */
export function ApprovalPanel({ approval }: { approval: Approval }) {
  const decide = useDecideApproval();
  const reanalysis = useRequestReanalysis();
  const toast = useToast();

  const [action, setAction] = useState<AdvisoryAction>('approved');
  const [reviewerName, setReviewerName] = useState('');
  const [note, setNote] = useState('');
  const [observation, setObservation] = useState('');
  const [depth, setDepth] = useState(
    approval.recommendation.depth_mm === undefined || approval.recommendation.depth_mm === null
      ? ''
      : String(approval.recommendation.depth_mm),
  );
  const [urgency, setUrgency] = useState(
    approval.recommendation.urgency === undefined ? '' : String(approval.recommendation.urgency),
  );

  const busy = decide.isPending || reanalysis.isPending;
  const trimmedName = reviewerName.trim();
  const trimmedObservation = observation.trim();

  const validationError = ((): string | null => {
    if (trimmedName.length < 2) return 'Enter your name (at least 2 characters) to record a decision.';
    if (action === 'reanalysis' && trimmedObservation.length < 3) {
      return 'Describe what you observed so the agents can act on it (at least 3 characters).';
    }
    return null;
  })();

  const modifiedAction = (): Record<string, unknown> => {
    const base: Record<string, unknown> = { ...approval.recommendation };
    if (depth.trim() !== '') base.depth_mm = Number(depth);
    if (urgency.trim() !== '') base.urgency = urgency.trim();
    return base;
  };

  const submit = () => {
    if (validationError) return;

    if (action === 'reanalysis') {
      reanalysis.mutate(
        {
          approvalId: approval.id,
          runId: approval.workflow_run_id,
          reviewerName: trimmedName,
          observation: trimmedObservation,
        },
        {
          onSuccess: (run) => {
            toast.push({
              tone: 'success',
              title: 'Re-analysis requested',
              message: `A fresh agent run (#${run.workflow_run_id}) started with your observation.`,
            });
          },
          onError: (error) => toast.pushError(error, 'Could not request re-analysis'),
        },
      );
      return;
    }

    const status: ApprovalStatus = action;
    decide.mutate(
      {
        approvalId: approval.id,
        decision: {
          status,
          reviewer_name: trimmedName,
          decision_note: note.trim() || null,
          observation: trimmedObservation.length >= 3 ? trimmedObservation : null,
          ...(action === 'modified' ? { modified_action: modifiedAction() } : {}),
        },
      },
      {
        onSuccess: (result) => {
          toast.push({
            tone: 'success',
            title: `Plan ${humaniseToken(result.status).toLowerCase()}`,
            message:
              result.status === 'approved'
                ? 'The plan is authorised. Applying it remains a physical task performed by a person.'
                : `Recorded against approval #${result.id} by ${trimmedName}.`,
          });
        },
        onError: (error) => toast.pushError(error, 'Could not record the decision'),
      },
    );
  };

  return (
    <Card flush data-testid="approval-panel" data-approval-id={approval.id}>
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {approval.title}
            <StatusBadge status={approval.status} />
          </span>
        }
        subtitle={`Approval #${approval.id} · run #${approval.workflow_run_id} · field #${approval.field_id} · ${humaniseToken(approval.action_type)} · raised ${formatDateTime(approval.created_at)}`}
        icon={<Gavel className="h-4 w-4" aria-hidden="true" />}
      />
      <div className="space-y-5 p-5">
        <RecommendationDetail recommendation={approval.recommendation} />

        {approval.evidence.length > 0 ? (
          <div>
            <p className="label-caps mb-2">Evidence attached to this request ({approval.evidence.length})</p>
            <ul className="space-y-1">
              {approval.evidence.slice(0, 10).map((item, index) => (
                <li key={`${item.label}-${index}`} className="text-xs text-slate-600">
                  <span className="font-mono text-slate-400">({item.kind})</span>{' '}
                  <span className="font-medium text-slate-700">{item.label}</span>:{' '}
                  {item.value === null || item.value === undefined ? '-' : String(item.value)}
                  {item.unit ? ` ${item.unit}` : ''}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
          <p className="label-caps">Record your decision</p>

          <div
            role="radiogroup"
            aria-label="Approval decision"
            className="mt-2 flex flex-wrap gap-2"
          >
            {(['approved', 'rejected', 'modified', 'reanalysis'] as const).map((option) => (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={action === option}
                onClick={() => setAction(option)}
                disabled={busy}
                className={[
                  'inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-60',
                  action === option
                    ? option === 'approved'
                      ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
                      : option === 'rejected'
                        ? 'border-rose-300 bg-rose-50 text-rose-800'
                        : option === 'modified'
                          ? 'border-violet-300 bg-violet-50 text-violet-800'
                          : 'border-amber-300 bg-amber-50 text-amber-800'
                    : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-100',
                ].join(' ')}
              >
                {option === 'approved' ? (
                  <Check className="h-3.5 w-3.5" aria-hidden="true" />
                ) : option === 'rejected' ? (
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                ) : option === 'modified' ? (
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {ACTION_LABELS[option]}
              </button>
            ))}
          </div>

          <FormGrid className="mt-4">
            <FieldRow
              label="Your name"
              required
              hint="Recorded on the approval. The backend requires at least 2 characters."
            >
              {(id) => (
                <TextInput
                  id={id}
                  value={reviewerName}
                  placeholder="e.g. Ramesh Kumar"
                  onChange={(event) => setReviewerName(event.target.value)}
                  disabled={busy}
                />
              )}
            </FieldRow>
            <FieldRow label="Decision note" hint="Optional free text stored with the decision.">
              {(id) => (
                <TextInput
                  id={id}
                  value={note}
                  placeholder="Why you decided this way"
                  onChange={(event) => setNote(event.target.value)}
                  disabled={busy}
                />
              )}
            </FieldRow>
            <FieldRow
              label="Field observation"
              required={action === 'reanalysis'}
              hint={
                action === 'reanalysis'
                  ? 'Required. Carried into the fresh agent run verbatim.'
                  : 'Optional. At least 3 characters if supplied.'
              }
            >
              {(id) => (
                <TextArea
                  id={id}
                  value={observation}
                  placeholder="e.g. Leaves are curling on the western edge; no visible pest."
                  onChange={(event) => setObservation(event.target.value)}
                  disabled={busy}
                />
              )}
            </FieldRow>

            {action === 'modified' ? (
              <>
                <FieldRow label="Adjusted depth (mm)" hint="Sent as modified_action.depth_mm.">
                  {(id) => (
                    <TextInput
                      id={id}
                      type="number"
                      step="0.1"
                      min="0"
                      value={depth}
                      onChange={(event) => setDepth(event.target.value)}
                      disabled={busy}
                    />
                  )}
                </FieldRow>
                <FieldRow label="Adjusted urgency" hint="Sent as modified_action.urgency.">
                  {(id) => (
                    <TextInput
                      id={id}
                      value={urgency}
                      onChange={(event) => setUrgency(event.target.value)}
                      disabled={busy}
                    />
                  )}
                </FieldRow>
              </>
            ) : null}
          </FormGrid>

          <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
            {action === 'reanalysis'
              ? 'This records your observation against the approval and immediately starts a fresh agent run (POST /workflow/runs/{id}/reanalyse).'
              : 'POST /approvals/{id}/decision - approving authorises the plan only. It never actuates equipment.'}
          </p>

          {decide.error ? (
            <ErrorBanner className="mt-3" title="Could not record the decision" error={decide.error} />
          ) : null}
          {reanalysis.error ? (
            <ErrorBanner className="mt-3" title="Could not request re-analysis" error={reanalysis.error} />
          ) : null}

          <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
            {validationError ? (
              <p className="mr-auto text-[11px] text-amber-700">{validationError}</p>
            ) : null}
            <Button
              variant="primary"
              disabled={validationError !== null}
              loading={busy}
              onClick={submit}
              icon={
                action === 'reanalysis' ? (
                  <RefreshCcw className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Gavel className="h-4 w-4" aria-hidden="true" />
                )
              }
            >
              {ACTION_LABELS[action]}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function RecommendationDetail({ recommendation }: { recommendation: Record<string, unknown> }) {
  const orderedKeys = ['action_type', 'crop', 'depth_mm', 'volume_m3', 'urgency', 'method'];
  const keys = [
    ...orderedKeys.filter((key) => key in recommendation),
    ...Object.keys(recommendation).filter((key) => !orderedKeys.includes(key)),
  ];

  return (
    <div>
      <p className="label-caps">Recommended action</p>
      <dl className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-2.5 sm:grid-cols-3">
        {keys.map((key) => (
          <div key={key}>
            <dt className="label-caps">{humaniseToken(key)}</dt>
            <dd className="tabular mt-0.5 break-words text-sm font-medium text-slate-800">
              {formatValue(recommendation[key])}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') return formatNumber(value, 2);
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/* ------------------------------------------------------------------ */
/* Decision history                                                    */
/* ------------------------------------------------------------------ */

function DecisionHistory({
  loading,
  error,
  approvals,
  onRetry,
}: {
  loading: boolean;
  error: unknown;
  approvals: Approval[];
  onRetry: () => void;
}) {
  return (
    <Card flush>
      <CardHeader
        title={`Decision history (${approvals.length})`}
        subtitle="Approvals for this field that a person has already decided."
        icon={<Gavel className="h-4 w-4" aria-hidden="true" />}
      />
      {loading ? (
        <SkeletonTable rows={3} columns={5} />
      ) : error ? (
        <ErrorBanner className="m-5" title="Could not load approvals" error={error} onRetry={onRetry} />
      ) : approvals.length === 0 ? (
        <div className="p-5">
          <EmptyState
            title="No decisions recorded"
            description="No approval for this field has been decided yet."
          />
        </div>
      ) : (
        <ul className="divide-y divide-slate-100">
          {approvals.map((approval) => (
            <li key={approval.id} className="space-y-1.5 px-5 py-3.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-slate-800">{approval.title}</span>
                <StatusBadge status={approval.status} />
                {approval.reanalysis_requested ? (
                  <Badge tone="warning">Re-analysis requested</Badge>
                ) : null}
                <span className="ml-auto text-[11px] text-slate-400">
                  {formatDateTime(approval.decided_at ?? approval.created_at)}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Approval #{approval.id} · run #{approval.workflow_run_id}
                {approval.reviewer_name ? ` · decided by ${approval.reviewer_name}` : ''}
              </p>
              {approval.decision_note ? (
                <p className="text-xs leading-relaxed text-slate-600">{approval.decision_note}</p>
              ) : null}
              {approval.observation ? (
                <p className="text-xs leading-relaxed text-slate-600">
                  <span className="font-medium text-slate-700">Observation:</span> {approval.observation}
                </p>
              ) : null}
              {approval.modified_action ? (
                <div className="rounded-lg bg-violet-50 px-3 py-2 ring-1 ring-inset ring-violet-200">
                  <p className="label-caps text-violet-800">Adjusted action</p>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[11px] text-violet-900">
                    {JSON.stringify(approval.modified_action, null, 2)}
                  </pre>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default AdvisoryPage;
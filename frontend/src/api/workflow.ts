import { apiClient } from './client';
import type {
  AgentTrace,
  ReanalysisRequest,
  Report,
  WorkflowRun,
  WorkflowRunDetail,
  WorkflowRunRequest,
  WorkflowRunSummary,
} from './types';

/** Execute the full multi-agent planning cycle for a field. Long-running. */
export const startWorkflowRun = async (payload: WorkflowRunRequest): Promise<WorkflowRunSummary> => {
  const { data } = await apiClient.post<WorkflowRunSummary>('/workflow/runs', payload);
  return data;
};

/** Re-run the agents carrying the reviewer's observations. */
export const reanalyseRun = async (
  runId: number,
  payload: ReanalysisRequest = {},
): Promise<WorkflowRunSummary> => {
  const { data } = await apiClient.post<WorkflowRunSummary>(`/workflow/runs/${runId}/reanalyse`, {
    force_refresh_weather: false,
    ...payload,
  });
  return data;
};

export const getWorkflowRun = async (runId: number): Promise<WorkflowRunDetail> => {
  const { data } = await apiClient.get<WorkflowRunDetail>(`/workflow/runs/${runId}`);
  return data;
};

export const getRunSummary = async (runId: number): Promise<WorkflowRunSummary> => {
  const { data } = await apiClient.get<WorkflowRunSummary>(`/workflow/runs/${runId}/summary`);
  return data;
};

export const getRunTraces = async (runId: number): Promise<AgentTrace[]> => {
  const { data } = await apiClient.get<AgentTrace[]>(`/workflow/runs/${runId}/traces`);
  return data;
};

/** Latest run for a field, including its agent traces. `null` when never run. */
export const getLatestRunForField = async (fieldId: number): Promise<WorkflowRunDetail | null> => {
  const { data } = await apiClient.get<WorkflowRunDetail | null>(
    `/workflow/runs/field/${fieldId}/latest`,
  );
  return data;
};

export const listWorkflowRuns = async (params: {
  farmId?: number;
  fieldId?: number;
  runStatus?: string;
  limit?: number;
} = {}): Promise<WorkflowRun[]> => {
  const { data } = await apiClient.get<WorkflowRun[]>('/workflow/runs', {
    params: {
      farm_id: params.farmId,
      field_id: params.fieldId,
      run_status: params.runStatus,
      limit: params.limit ?? 25,
    },
  });
  return data;
};

export const getRunCount = async (params: { farmId?: number; fieldId?: number } = {}) => {
  const { data } = await apiClient.get<{ total: number; limit: number; offset: number }>(
    '/workflow/runs/count',
    { params: { farm_id: params.farmId, field_id: params.fieldId } },
  );
  return data;
};

/* ------------------------------------------------------------------ */
/* Reports                                                             */
/* ------------------------------------------------------------------ */

export const listReports = async (params: {
  fieldId?: number;
  farmId?: number;
  limit?: number;
} = {}): Promise<Report[]> => {
  const { data } = await apiClient.get<Report[]>('/reports', {
    params: {
      field_id: params.fieldId,
      farm_id: params.farmId,
      limit: params.limit ?? 50,
    },
  });
  return data;
};

export const getReport = async (reportId: number): Promise<Report> => {
  const { data } = await apiClient.get<Report>(`/reports/${reportId}`);
  return data;
};

export const createReport = async (fieldId: number, workflowRunId: number): Promise<Report> => {
  const { data } = await apiClient.post<Report>(
    '/reports',
    { workflow_run_id: workflowRunId, include_evidence: true },
    { params: { field_id: fieldId } },
  );
  return data;
};

export const deleteReport = async (reportId: number): Promise<void> => {
  await apiClient.delete(`/reports/${reportId}`);
};

/** `GET /workflow/runs/{id}/report` - convenience alias that builds on `createReport`. */
export const createReportForRun = async (runId: number, fieldId: number): Promise<Report> => {
  return createReport(fieldId, runId);
};
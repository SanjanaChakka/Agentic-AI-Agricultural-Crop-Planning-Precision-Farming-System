import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getLatestRunForField,
  getRunSummary,
  getRunTraces,
  getWorkflowRun,
  listWorkflowRuns,
  reanalyseRun,
  startWorkflowRun,
} from '../api/workflow';
import type { ReanalysisRequest, WorkflowRunRequest } from '../api/types';
import { queryKeys } from '../lib/queryKeys';

/** Everything a completed run exposes, keyed by run id. */
export const useRunDetail = (runId: number | null) =>
  useQuery({
    queryKey: queryKeys.run(runId ?? -1),
    queryFn: () => getWorkflowRun(runId as number),
    enabled: runId !== null,
  });

export const useRunSummary = (runId: number | null) =>
  useQuery({
    queryKey: queryKeys.runSummary(runId ?? -1),
    queryFn: () => getRunSummary(runId as number),
    enabled: runId !== null,
  });

export const useRunTraces = (runId: number | null) =>
  useQuery({
    queryKey: queryKeys.runTraces(runId ?? -1),
    queryFn: () => getRunTraces(runId as number),
    enabled: runId !== null,
  });

export const useLatestRun = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.latestRun(fieldId ?? -1),
    queryFn: () => getLatestRunForField(fieldId as number),
    enabled: fieldId !== null,
  });

export const useWorkflowRuns = (params: { farmId?: number; fieldId?: number } = {}) =>
  useQuery({
    queryKey: queryKeys.runs(params.fieldId),
    queryFn: () => listWorkflowRuns(params),
  });

const runInvalidation = (queryClient: ReturnType<typeof useQueryClient>) => {
  void queryClient.invalidateQueries({ queryKey: ['runs'] });
  void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
  void queryClient.invalidateQueries({ queryKey: ['approvals'] });
  void queryClient.invalidateQueries({ queryKey: ['activities'] });
  void queryClient.invalidateQueries({ queryKey: ['alerts'] });
  void queryClient.invalidateQueries({ queryKey: ['irrigation'] });
  void queryClient.invalidateQueries({ queryKey: ['risk'] });
  void queryClient.invalidateQueries({ queryKey: ['ml'] });
  void queryClient.invalidateQueries({ queryKey: ['suitability'] });
};

/** Start the full agent workflow. Long-running, so it is a mutation with a spinner. */
export const useStartWorkflowRun = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WorkflowRunRequest) => startWorkflowRun(payload),
    onSuccess: () => runInvalidation(queryClient),
  });
};

export const useReanalyseRun = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { runId: number; payload?: ReanalysisRequest }) =>
      reanalyseRun(variables.runId, variables.payload ?? {}),
    onSuccess: () => runInvalidation(queryClient),
  });
};
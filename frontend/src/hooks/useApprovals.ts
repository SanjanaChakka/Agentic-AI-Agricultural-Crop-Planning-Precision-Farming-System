import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  decideApproval,
  getSafetyContract,
  listApprovals,
  listPendingApprovals,
} from '../api/approvals';
import type { ApprovalDecision } from '../api/types';
import { queryKeys } from '../lib/queryKeys';
import { reanalyseRun } from '../api/workflow';

export const useApprovals = (fieldId?: number) =>
  useQuery({
    queryKey: queryKeys.approvals(fieldId),
    queryFn: () => listApprovals(fieldId ? { fieldId } : {}),
  });

export const usePendingApprovals = () =>
  useQuery({ queryKey: queryKeys.pendingApprovals(), queryFn: () => listPendingApprovals() });

export const useSafetyContract = () =>
  useQuery({ queryKey: queryKeys.safetyContract(), queryFn: getSafetyContract, staleTime: 600_000 });

/**
 * A human decision changes runs, approvals, activities and the dashboard, so all
 * of them are invalidated together.
 */
export const useDecideApproval = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { approvalId: number; decision: ApprovalDecision }) =>
      decideApproval(variables.approvalId, variables.decision),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['approvals'] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      void queryClient.invalidateQueries({ queryKey: ['activities'] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
    },
  });
};

/**
 * "Request re-analysis" is two real API calls:
 *  1. record the reviewer's observation on the approval with
 *     `reanalysis_requested: true` (and withdraw the stale plan), then
 *  2. start a fresh agent run carrying that observation.
 * Both endpoints exist, so neither control is decorative.
 */
export const useRequestReanalysis = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (variables: {
      approvalId: number;
      runId: number;
      reviewerName: string;
      observation: string;
      forceRefreshWeather?: boolean;
    }) => {
      await decideApproval(variables.approvalId, {
        status: 'rejected',
        reviewer_name: variables.reviewerName,
        decision_note: 'Re-analysis requested: the reviewer supplied new observations.',
        observation: variables.observation,
        reanalysis_requested: true,
      });
      return reanalyseRun(variables.runId, {
        notes: variables.observation,
        force_refresh_weather: Boolean(variables.forceRefreshWeather),
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['approvals'] });
      void queryClient.invalidateQueries({ queryKey: ['runs'] });
      void queryClient.invalidateQueries({ queryKey: ['activities'] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
    },
  });
};
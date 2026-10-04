import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { listActivities, planActivities, updateActivity } from '../api/activities';
import type { ActivityStatus, FarmActivityUpdate } from '../api/types';
import { queryKeys } from '../lib/queryKeys';

export const useActivities = (params: {
  fieldId?: number;
  activityStatus?: string;
  workflowRunId?: number;
} = {}) =>
  useQuery({
    queryKey: queryKeys.activities(params.fieldId, params.activityStatus),
    queryFn: () => listActivities(params),
  });

export const useUpdateActivity = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { activityId: number; payload: FarmActivityUpdate }) =>
      updateActivity(variables.activityId, variables.payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['activities'] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
    },
  });
};

export const usePlanActivities = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { workflowRunId: number; responsiblePerson?: string }) =>
      planActivities({
        workflow_run_id: variables.workflowRunId,
        include_approved_only: false,
        responsible_person: variables.responsiblePerson ?? null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['activities'] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
    },
  });
};

export type { ActivityStatus };
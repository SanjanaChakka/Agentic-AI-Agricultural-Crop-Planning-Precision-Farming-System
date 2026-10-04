import { apiClient } from './client';
import type {
  ActivityPlanRequest,
  ActivityStatus,
  FarmActivity,
  FarmActivityUpdate,
} from './types';

export const listActivities = async (params: {
  fieldId?: number;
  activityStatus?: ActivityStatus | string;
  workflowRunId?: number;
  limit?: number;
} = {}): Promise<FarmActivity[]> => {
  const { data } = await apiClient.get<FarmActivity[]>('/activities', {
    params: {
      field_id: params.fieldId,
      activity_status: params.activityStatus,
      workflow_run_id: params.workflowRunId,
      limit: params.limit ?? 50,
    },
  });
  return data;
};

export const getUpcomingActivities = async (
  fieldId: number,
  days = 14,
): Promise<FarmActivity[]> => {
  const { data } = await apiClient.get<FarmActivity[]>(
    `/activities/fields/${fieldId}/upcoming`,
    { params: { days } },
  );
  return data;
};

/** The only activity mutation the UI offers: move an activity between states. */
export const updateActivity = async (
  activityId: number,
  payload: FarmActivityUpdate,
): Promise<FarmActivity> => {
  const { data } = await apiClient.patch<FarmActivity>(`/activities/${activityId}`, payload);
  return data;
};

/** Generate the activity plan for a completed workflow run. */
export const planActivities = async (payload: ActivityPlanRequest): Promise<FarmActivity[]> => {
  const { data } = await apiClient.post<FarmActivity[]>('/activities/plan', payload);
  return data;
};
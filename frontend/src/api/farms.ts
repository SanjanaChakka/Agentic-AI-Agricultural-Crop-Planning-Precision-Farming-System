import { apiClient } from './client';
import type {
  AgentInfo,
  Alert,
  AlertUpdate,
  DashboardResponse,
  DedupPolicy,
  Farm,
  FarmCreate,
  FarmSummary,
  FarmUpdate,
  FarmWithFields,
  Field,
  FieldCounts,
  FieldCreate,
  FieldUpdate,
} from './types';

/* ------------------------------------------------------------------ */
/* Dashboard                                                           */
/* ------------------------------------------------------------------ */

export const getDashboard = async (): Promise<DashboardResponse> => {
  const { data } = await apiClient.get<DashboardResponse>('/dashboard');
  return data;
};

/* ------------------------------------------------------------------ */
/* Farms                                                               */
/* ------------------------------------------------------------------ */

export const listFarms = async (search?: string): Promise<Farm[]> => {
  const { data } = await apiClient.get<Farm[]>('/farms', {
    params: search ? { search } : undefined,
  });
  return data;
};

export const createFarm = async (payload: FarmCreate): Promise<Farm> => {
  const { data } = await apiClient.post<Farm>('/farms', payload);
  return data;
};

export const getFarm = async (farmId: number): Promise<FarmWithFields> => {
  const { data } = await apiClient.get<FarmWithFields>(`/farms/${farmId}`);
  return data;
};

export const updateFarm = async (farmId: number, payload: FarmUpdate): Promise<Farm> => {
  const { data } = await apiClient.patch<Farm>(`/farms/${farmId}`, payload);
  return data;
};

export const deleteFarm = async (farmId: number): Promise<void> => {
  await apiClient.delete(`/farms/${farmId}`);
};

export const getFarmSummary = async (farmId: number): Promise<FarmSummary> => {
  const { data } = await apiClient.get<FarmSummary>(`/farms/${farmId}/summary`);
  return data;
};

/* ------------------------------------------------------------------ */
/* Fields                                                              */
/* ------------------------------------------------------------------ */

/** Fields for one farm. The contract exposes `/fields?farm_id=`, not `/farms/{id}/fields`. */
export const listFields = async (farmId?: number): Promise<Field[]> => {
  const { data } = await apiClient.get<Field[]>('/fields', {
    params: farmId ? { farm_id: farmId } : undefined,
  });
  return data;
};

export const createField = async (farmId: number, payload: FieldCreate): Promise<Field> => {
  const { data } = await apiClient.post<Field>('/fields', payload, { params: { farm_id: farmId } });
  return data;
};

export const getField = async (fieldId: number): Promise<Field> => {
  const { data } = await apiClient.get<Field>(`/fields/${fieldId}`);
  return data;
};

export const updateField = async (fieldId: number, payload: FieldUpdate): Promise<Field> => {
  const { data } = await apiClient.patch<Field>(`/fields/${fieldId}`, payload);
  return data;
};

export const deleteField = async (fieldId: number): Promise<void> => {
  await apiClient.delete(`/fields/${fieldId}`);
};

export const getFieldCounts = async (farmId?: number): Promise<FieldCounts> => {
  const { data } = await apiClient.get<FieldCounts>('/fields/counts', {
    params: farmId ? { farm_id: farmId } : undefined,
  });
  return data;
};

/* ------------------------------------------------------------------ */
/* Alerts                                                              */
/* ------------------------------------------------------------------ */

/** Open *and* acknowledged alerts - the actionable list. */
export const listOpenAlerts = async (farmId?: number): Promise<Alert[]> => {
  const { data } = await apiClient.get<Alert[]>('/alerts/open', {
    params: farmId ? { farm_id: farmId } : undefined,
  });
  return data;
};

export const listAlerts = async (params: {
  farmId?: number;
  fieldId?: number;
  alertStatus?: string;
  severity?: string;
}): Promise<Alert[]> => {
  const { data } = await apiClient.get<Alert[]>('/alerts', {
    params: {
      farm_id: params.farmId,
      field_id: params.fieldId,
      alert_status: params.alertStatus,
      severity: params.severity,
    },
  });
  return data;
};

export const updateAlert = async (alertId: number, payload: AlertUpdate): Promise<Alert> => {
  const { data } = await apiClient.patch<Alert>(`/alerts/${alertId}`, payload);
  return data;
};

export const getDedupPolicy = async (): Promise<DedupPolicy> => {
  const { data } = await apiClient.get<DedupPolicy>('/alerts/dedup-policy');
  return data;
};

/* ------------------------------------------------------------------ */
/* Agents                                                              */
/* ------------------------------------------------------------------ */

export const listAgents = async (): Promise<AgentInfo[]> => {
  const { data } = await apiClient.get<{ count?: number; agents: AgentInfo[] }>('/agents');
  return data.agents ?? [];
};
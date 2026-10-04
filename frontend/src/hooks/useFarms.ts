import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createFarm,
  createField,
  getDashboard,
  getDedupPolicy,
  getFarm,
  getFarmSummary,
  getField,
  getFieldCounts,
  listAgents,
  listAlerts,
  listFarms,
  listFields,
  listOpenAlerts,
  updateAlert,
  updateField,
} from '../api/farms';
import type {
  Alert,
  AlertUpdate,
  Farm,
  FarmCreate,
  Field,
  FieldCreate,
  FieldUpdate,
} from '../api/types';
import { queryKeys } from '../lib/queryKeys';

/* ------------------------------------------------------------------ */
/* Farms & fields                                                      */
/* ------------------------------------------------------------------ */

export const useFarms = () =>
  useQuery({ queryKey: queryKeys.farms(), queryFn: () => listFarms(), staleTime: 30_000 });

export const useFarmWithFields = (farmId: number | null) =>
  useQuery({
    queryKey: queryKeys.farm(farmId ?? -1),
    queryFn: () => getFarm(farmId as number),
    enabled: farmId !== null,
  });

export const useFarmSummary = (farmId: number | null) =>
  useQuery({
    queryKey: queryKeys.farmSummary(farmId ?? -1),
    queryFn: () => getFarmSummary(farmId as number),
    enabled: farmId !== null,
  });

export const useFields = (farmId?: number) =>
  useQuery({
    queryKey: queryKeys.fields(farmId),
    queryFn: () => listFields(farmId),
    staleTime: 30_000,
  });

export const useFieldCounts = (farmId?: number) =>
  useQuery({
    queryKey: queryKeys.fieldCounts(farmId),
    queryFn: () => getFieldCounts(farmId),
  });

export const useField = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.field(fieldId ?? -1),
    queryFn: () => getField(fieldId as number),
    enabled: fieldId !== null,
  });

export const useCreateFarm = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FarmCreate): Promise<Farm> => createFarm(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.farms() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
    },
  });
};

export const useCreateField = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { farmId: number; payload: FieldCreate }): Promise<Field> =>
      createField(variables.farmId, variables.payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields(variables.farmId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fieldCounts() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
    },
  });
};

export const useUpdateField = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { fieldId: number; payload: FieldUpdate }): Promise<Field> =>
      updateField(variables.fieldId, variables.payload),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.field(updated.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields(updated.farm_id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields() });
    },
  });
};

/* ------------------------------------------------------------------ */
/* Dashboard, alerts, agents                                           */
/* ------------------------------------------------------------------ */

export const useDashboard = () =>
  useQuery({ queryKey: queryKeys.dashboard(), queryFn: getDashboard, staleTime: 15_000 });

export const useOpenAlerts = (farmId?: number) =>
  useQuery({
    queryKey: queryKeys.alertsOpen(farmId),
    queryFn: () => listOpenAlerts(farmId),
    staleTime: 15_000,
  });

export const useAlerts = (params: {
  farmId?: number;
  fieldId?: number;
  alertStatus?: string;
  severity?: string;
}) =>
  useQuery({
    queryKey: queryKeys.alerts(params as unknown as Record<string, unknown>),
    queryFn: () => listAlerts(params),
  });

export const useDedupPolicy = () =>
  useQuery({ queryKey: ['alerts', 'dedup-policy'], queryFn: getDedupPolicy, staleTime: 300_000 });

export const useUpdateAlert = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { alertId: number; payload: AlertUpdate }): Promise<Alert> =>
      updateAlert(variables.alertId, variables.payload),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ['alerts'] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.fields(updated.farm_id) });
    },
  });
};

export const useAgents = () =>
  useQuery({ queryKey: queryKeys.agents(), queryFn: listAgents, staleTime: 300_000 });
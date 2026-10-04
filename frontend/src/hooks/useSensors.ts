import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getLatestReading,
  getSensorQuality,
  getSensorTrend,
  simulateReadings,
} from '../api/sensors';
import type { SensorSimulationRequest } from '../api/types';
import { queryKeys } from '../lib/queryKeys';

export const useLatestReading = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.sensorsLatest(fieldId ?? -1),
    queryFn: () => getLatestReading(fieldId as number),
    enabled: fieldId !== null,
  });

export const useSensorTrend = (fieldId: number | null, hours = 168) =>
  useQuery({
    queryKey: queryKeys.sensorsTrend(fieldId ?? -1, hours),
    queryFn: () => getSensorTrend(fieldId as number, hours),
    enabled: fieldId !== null,
  });

export const useSensorQuality = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.sensorsQuality(fieldId ?? -1),
    queryFn: () => getSensorQuality(fieldId as number),
    enabled: fieldId !== null,
  });

export const useSimulateReadings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { fieldId: number; payload?: SensorSimulationRequest }) =>
      simulateReadings(variables.fieldId, variables.payload ?? {}),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.sensorsLatest(variables.fieldId) });
      void queryClient.invalidateQueries({ queryKey: ['sensors', variables.fieldId] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
    },
  });
};
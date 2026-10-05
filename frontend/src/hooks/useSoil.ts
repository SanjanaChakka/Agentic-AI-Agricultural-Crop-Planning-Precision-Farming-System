import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createSoilObservation,
  getLatestSoil,
  getSoilThresholds,
  listSoilObservations,
} from '../api/soil';
import type { SoilObservationCreate } from '../api/types';
import { queryKeys } from '../lib/queryKeys';

export const useLatestSoil = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.soilLatest(fieldId ?? -1),
    queryFn: () => getLatestSoil(fieldId as number),
    enabled: fieldId !== null,
  });

export const useSoilObservations = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.soilObservations(fieldId ?? -1),
    queryFn: () => listSoilObservations(fieldId as number),
    enabled: fieldId !== null,
  });

export const useSoilThresholds = () =>
  useQuery({ queryKey: queryKeys.soilThresholds(), queryFn: getSoilThresholds, staleTime: 600_000 });

export const useCreateSoilObservation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SoilObservationCreate) => createSoilObservation(payload),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.soilLatest(created.observation.field_id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.soilObservations(created.observation.field_id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard() });
    },
  });
};
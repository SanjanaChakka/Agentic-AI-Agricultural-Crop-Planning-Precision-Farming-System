import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { assessSuitability, getCropCatalogue, getSuitabilityHistory } from '../api/suitability';
import type { SuitabilityRequest } from '../api/types';
import { queryKeys } from '../lib/queryKeys';

export const useCropCatalogue = () =>
  useQuery({ queryKey: queryKeys.crops(), queryFn: getCropCatalogue, staleTime: 600_000 });

export const useSuitabilityHistory = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.suitabilityHistory(fieldId ?? -1),
    queryFn: () => getSuitabilityHistory(fieldId as number),
    enabled: fieldId !== null,
  });

/** One assessment per click - not auto-run, so no query key is needed. */
export const useAssessSuitability = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { fieldId: number; payload?: SuitabilityRequest }) =>
      assessSuitability(variables.fieldId, variables.payload ?? { include_evidence: true }),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.suitabilityHistory(variables.fieldId) });
    },
  });
};
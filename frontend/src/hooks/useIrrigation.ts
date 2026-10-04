import { useMutation, useQuery } from '@tanstack/react-query';
import { assessIrrigation, getIrrigationHistory } from '../api/irrigation';
import type { IrrigationAssessRequest } from '../api/types';
import { queryKeys } from '../lib/queryKeys';

export const useIrrigationHistory = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.irrigationHistory(fieldId ?? -1),
    queryFn: () => getIrrigationHistory(fieldId as number),
    enabled: fieldId !== null,
  });

/** Proposal only. There is deliberately no mutation that applies water. */
export const useAssessIrrigation = () =>
  useMutation({
    mutationFn: (variables: { fieldId: number; payload?: IrrigationAssessRequest }) =>
      assessIrrigation(variables.fieldId, variables.payload ?? {}),
  });
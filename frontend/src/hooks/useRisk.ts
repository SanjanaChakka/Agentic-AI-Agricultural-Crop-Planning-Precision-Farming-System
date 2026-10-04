import { useQuery } from '@tanstack/react-query';
import { getRiskDisclaimer, getRiskHistory, scanFieldRisk } from '../api/risk';
import { findMoisturePrediction, findSeverityPrediction, getFieldPredictions } from '../api/ml';
import { queryKeys } from '../lib/queryKeys';

export const useFieldRisk = (fieldId: number | null, crop?: string) =>
  useQuery({
    queryKey: queryKeys.risk(fieldId ?? -1, crop),
    queryFn: () => scanFieldRisk(fieldId as number, crop),
    enabled: fieldId !== null,
    staleTime: 60_000,
  });

export const useRiskHistory = (fieldId: number | null) =>
  useQuery({
    queryKey: ['risk', fieldId ?? -1, 'history'],
    queryFn: () => getRiskHistory(fieldId as number),
    enabled: fieldId !== null,
  });

export const useRiskDisclaimer = () =>
  useQuery({ queryKey: queryKeys.riskDisclaimer(), queryFn: getRiskDisclaimer, staleTime: 600_000 });

export const useFieldPredictions = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.mlPredictions(fieldId ?? -1),
    queryFn: () => getFieldPredictions(fieldId as number),
    enabled: fieldId !== null,
  });

export { findSeverityPrediction, findMoisturePrediction };
import { apiClient } from './client';
import type { MLModelInfo, MLPrediction, MLStatus } from './types';

export const getMlStatus = async (): Promise<MLStatus> => {
  const { data } = await apiClient.get<MLStatus>('/ml/status');
  return data;
};

export const getMlModels = async (): Promise<MLModelInfo[]> => {
  const { data } = await apiClient.get<MLModelInfo[]>('/ml/models');
  return data;
};

export const getFieldPredictions = async (
  fieldId: number,
  limit = 20,
): Promise<MLPrediction[]> => {
  const { data } = await apiClient.get<MLPrediction[]>(`/ml/fields/${fieldId}/predictions`, {
    params: { limit },
  });
  return data;
};

/** The severity model prediction used as the ML cross-check on the risk page. */
export const SEVERITY_TASK_KEYWORDS = ['risk', 'severity'];

export function findSeverityPrediction(
  predictions: MLPrediction[],
): MLPrediction | undefined {
  return predictions.find((prediction) =>
    SEVERITY_TASK_KEYWORDS.some(
      (keyword) => prediction.task?.toLowerCase().includes(keyword),
    ),
  );
}

export function findMoisturePrediction(
  predictions: MLPrediction[],
): MLPrediction | undefined {
  return predictions.find((prediction) =>
    prediction.task?.toLowerCase().includes('moisture'),
  );
}
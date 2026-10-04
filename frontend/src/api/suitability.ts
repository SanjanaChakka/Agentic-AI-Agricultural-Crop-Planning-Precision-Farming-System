import { apiClient } from './client';
import type { CropCatalogue, Suitability, SuitabilityRequest } from './types';

/** Supported crops and their agronomic thresholds. */
export const getCropCatalogue = async (): Promise<CropCatalogue> => {
  const { data } = await apiClient.get<CropCatalogue>('/suitability/crops');
  return data;
};

/** Run a weighted suitability assessment for one field and crop. */
export const assessSuitability = async (
  fieldId: number,
  payload: SuitabilityRequest = {},
): Promise<Suitability> => {
  const { data } = await apiClient.post<Suitability>(
    '/suitability/assess',
    { include_evidence: true, ...payload },
    { params: { field_id: fieldId } },
  );
  return data;
};

export const getSuitabilityHistory = async (
  fieldId: number,
  limit = 20,
): Promise<Suitability[]> => {
  const { data } = await apiClient.get<Suitability[]>(`/suitability/fields/${fieldId}`, {
    params: { limit },
  });
  return data;
};
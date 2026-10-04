import { apiClient } from './client';
import type { Irrigation, IrrigationAssessRequest } from './types';

/**
 * Irrigation decision support.
 *
 * This is a PROPOSAL ONLY. The backend exposes no endpoint that actuates a
 * valve or pump, so the UI must never offer an "apply water" action.
 */
export const assessIrrigation = async (
  fieldId: number,
  payload: IrrigationAssessRequest = {},
): Promise<Irrigation> => {
  const { data } = await apiClient.post<Irrigation>(
    '/irrigation/assess',
    payload,
    { params: { field_id: fieldId } },
  );
  return data;
};

export const getIrrigationHistory = async (
  fieldId: number,
  limit = 20,
): Promise<Irrigation[]> => {
  const { data } = await apiClient.get<Irrigation[]>(`/irrigation/fields/${fieldId}`, {
    params: { limit },
  });
  return data;
};
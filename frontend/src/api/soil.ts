import { apiClient } from './client';
import type {
  SoilAnalysisResponse,
  SoilInterpretation,
  SoilObservation,
  SoilObservationCreate,
  SoilThresholds,
} from './types';

/** Latest measured soil test for a field plus its AI interpretation. `null` when none exists. */
export const getLatestSoil = async (fieldId: number): Promise<SoilAnalysisResponse | null> => {
  const { data } = await apiClient.get<SoilAnalysisResponse | null>(
    `/soil/fields/${fieldId}/latest`,
  );
  return data;
};

/** Parameter history for the trend chart / table. */
export const listSoilObservations = async (fieldId: number): Promise<SoilObservation[]> => {
  const { data } = await apiClient.get<SoilObservation[]>('/soil/observations', {
    params: { field_id: fieldId },
  });
  return data;
};

export const createSoilObservation = async (
  payload: SoilObservationCreate,
): Promise<SoilAnalysisResponse> => {
  const { data } = await apiClient.post<SoilAnalysisResponse>('/soil/observations', payload);
  return data;
};

export const getSoilObservation = async (
  observationId: number,
): Promise<SoilAnalysisResponse> => {
  const { data } = await apiClient.get<SoilAnalysisResponse>(`/soil/observations/${observationId}`);
  return data;
};

/** Agronomic rating bands the system applies - shown as the transparency reference. */
export const getSoilThresholds = async (): Promise<SoilThresholds> => {
  const { data } = await apiClient.get<SoilThresholds>('/soil/thresholds');
  return data;
};

/** Re-run the interpretation for a measured observation against a named crop. */
export const reinterpretObservation = async (
  observationId: number,
  crop: string,
): Promise<SoilInterpretation> => {
  const { data } = await apiClient.post<SoilInterpretation>(
    `/soil/observations/${observationId}/reinterpret`,
    undefined,
    { params: { crop } },
  );
  return data;
};
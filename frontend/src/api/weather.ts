import { apiClient } from './client';
import type { Evidence, SourceReference, WeatherBundle, WeatherEvidenceResponse } from './types';

/**
 * 7-day forecast for a registered field.
 *
 * `bundle.source`, `bundle.provider` and `bundle.is_simulated` are mandatory in
 * the contract and MUST be surfaced in the UI - fallback climatology is never
 * presented as live provider data.
 */
export const getFieldWeather = async (fieldId: number, days = 7): Promise<WeatherBundle> => {
  const { data } = await apiClient.get<WeatherBundle>(`/weather/fields/${fieldId}`, {
    params: { days },
  });
  return data;
};

export const getFieldWeatherEvidence = async (
  fieldId: number,
  days = 7,
): Promise<{ evidence: Evidence[]; sources: SourceReference[] }> => {
  const { data } = await apiClient.get<WeatherEvidenceResponse>(
    `/weather/fields/${fieldId}/evidence`,
    { params: { days } },
  );
  return {
    evidence: Array.isArray(data?.evidence) ? data.evidence : [],
    sources: Array.isArray(data?.sources) ? data.sources : [],
  };
};
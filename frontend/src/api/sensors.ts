import { apiClient } from './client';
import type {
  SensorQualityReport,
  SensorReading,
  SensorSimulationRequest,
  SensorSimulationResponse,
  SensorTrend,
} from './types';

export const getLatestReading = async (
  fieldId: number,
  sensorId?: string,
): Promise<SensorReading | null> => {
  const { data } = await apiClient.get<SensorReading | null>(`/sensors/fields/${fieldId}/latest`, {
    params: sensorId ? { sensor_id: sensorId } : undefined,
  });
  return data;
};

/** Telemetry trend + statistics for the chart. `hours` defaults to the 7-day window server-side. */
export const getSensorTrend = async (fieldId: number, hours = 168): Promise<SensorTrend> => {
  const { data } = await apiClient.get<SensorTrend>(`/sensors/fields/${fieldId}/trend`, {
    params: { hours },
  });
  return data;
};

export const getSensorQuality = async (fieldId: number): Promise<SensorQualityReport> => {
  const { data } = await apiClient.get<SensorQualityReport>(`/sensors/fields/${fieldId}/quality`);
  return data;
};

/** Generate simulated telemetry. Every persisted row is flagged `is_simulated`. */
export const simulateReadings = async (
  fieldId: number,
  payload: SensorSimulationRequest = {},
): Promise<SensorSimulationResponse> => {
  const { data } = await apiClient.post<SensorSimulationResponse>(
    `/sensors/fields/${fieldId}/simulate`,
    { hours: 72, interval_hours: 2, rainfall_events: true, ...payload },
  );
  return data;
};
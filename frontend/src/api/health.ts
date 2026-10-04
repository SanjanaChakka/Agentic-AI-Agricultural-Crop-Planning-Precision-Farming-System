import { apiClient } from './client';
import type { HealthResponse } from './types';

export const getHealth = async (): Promise<HealthResponse> => {
  const { data } = await apiClient.get<HealthResponse>('/health');
  return data;
};
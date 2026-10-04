import { useQuery } from '@tanstack/react-query';
import { getFieldWeather, getFieldWeatherEvidence } from '../api/weather';
import { queryKeys } from '../lib/queryKeys';

export const useFieldWeather = (fieldId: number | null, days = 7) =>
  useQuery({
    queryKey: queryKeys.weather(fieldId ?? -1, days),
    queryFn: () => getFieldWeather(fieldId as number, days),
    enabled: fieldId !== null,
    staleTime: 5 * 60_000,
  });

export const useFieldWeatherEvidence = (fieldId: number | null) =>
  useQuery({
    queryKey: queryKeys.weatherEvidence(fieldId ?? -1),
    queryFn: () => getFieldWeatherEvidence(fieldId as number),
    enabled: fieldId !== null,
    staleTime: 5 * 60_000,
  });
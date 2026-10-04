import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns';

const toDate = (value: string | null | undefined): Date | null => {
  if (!value) return null;
  const parsed = parseISO(value);
  return isValid(parsed) ? parsed : null;
};

/** `04 Oct 2026` */
export const formatDate = (value: string | null | undefined, fallback = '-'): string => {
  const date = toDate(value);
  return date ? format(date, 'dd MMM yyyy') : fallback;
};

/** `04 Oct 2026, 09:30` */
export const formatDateTime = (value: string | null | undefined, fallback = '-'): string => {
  const date = toDate(value);
  return date ? format(date, 'dd MMM yyyy, HH:mm') : fallback;
};

/** `2 hours ago` */
export const formatRelative = (value: string | null | undefined, fallback = '-'): string => {
  const date = toDate(value);
  return date ? `${formatDistanceToNowStrict(date)} ago` : fallback;
};

/** `04 Oct` - used inside dense chart axes and table cells. */
export const formatShortDate = (value: string | null | undefined, fallback = '-'): string => {
  const date = toDate(value);
  return date ? format(date, 'dd MMM') : fallback;
};

/** `04 Oct 09:00` */
export const formatShortDateTime = (value: string | null | undefined, fallback = '-'): string => {
  const date = toDate(value);
  return date ? format(date, 'dd MMM HH:mm') : fallback;
};

/** Numbers render with a thousands separator and a fixed-ish precision. */
export const formatNumber = (value: number | null | undefined, digits = 1): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value);
};

export const formatPercent = (
  value: number | null | undefined,
  digits = 0,
): string => (value === null || value === undefined ? '-' : `${formatNumber(value, digits)}%`);

export const formatBytes = (bytes: number | null | undefined): string => {
  if (!bytes || bytes <= 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
};

export const formatDuration = (ms: number | null | undefined): string => {
  if (ms === null || ms === undefined) return '-';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
};

/** `suitable_with_conditions` -> `Suitable with conditions`. */
export const humaniseToken = (value: string | null | undefined, fallback = '-'): string => {
  if (!value) return fallback;
  const cleaned = value.replace(/[_-]+/g, ' ').trim();
  if (!cleaned) return fallback;
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
};

/** `North Black Cotton Plot` from an object map id -> value. */
export const optionLabel = (
  value: number | null | undefined,
  map: Map<number, string>,
  fallback = 'Unknown field',
): string => (value === null || value === undefined ? fallback : (map.get(value) ?? `#${value}`));
import axios, { AxiosError, AxiosResponse } from 'axios';

/**
 * Central HTTP layer.
 *
 * - `baseURL` is always relative (`/api/v1` by default) so the browser talks to
 *   the same origin that served the SPA. Vite proxies `/api` to the backend in
 *   dev; a reverse proxy does the same in production.
 * - No backend host is ever hardcoded in application code.
 */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || '/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { Accept: 'application/json' },
  timeout: 120_000,
});

/** A backend validation problem (`HTTPValidationError.detail: ValidationError[]`). */
export interface ApiFieldIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/** Normalised error thrown by the client so the UI never sees raw axios guts. */
export class ApiError extends Error {
  readonly status: number | null;
  readonly issues: ApiFieldIssue[];
  readonly url: string | null;

  constructor(message: string, status: number | null, issues: ApiFieldIssue[] = [], url: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.issues = issues;
    this.url = url;
  }
}

const isFieldIssue = (value: unknown): value is ApiFieldIssue => {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.msg === 'string' && Array.isArray(candidate.loc);
};

/**
 * Turn a FastAPI `detail` payload into one readable line.
 *
 * FastAPI uses three shapes:
 *  - `{"detail": "Not found"}`                  - raised via HTTPException
 *  - `{"detail": [{"loc": [...], "msg": ...}]}` - request validation failure
 *  - `{"detail": {...}}`                        - any custom mapping
 */
export function detailToMessage(detail: unknown): string | null {
  if (detail === null || detail === undefined) return null;
  if (typeof detail === 'string') return detail.trim() || null;
  if (Array.isArray(detail)) {
    const lines = detail
      .filter(isFieldIssue)
      .map((issue) => {
        const field = issue.loc.filter((part) => part !== 'body').join('.');
        return field ? `${field}: ${issue.msg}` : issue.msg;
      });
    if (lines.length > 0) return lines.join('; ');
    return null;
  }
  if (typeof detail === 'object') {
    const record = detail as Record<string, unknown>;
    if (isFieldIssue(record)) {
      const field = record.loc.filter((part) => part !== 'body').join('.');
      return field ? `${field}: ${record.msg}` : record.msg;
    }
    if (typeof record.message === 'string') return record.message;
    return null;
  }
  return null;
}

/** Normalise any thrown value into a human-readable message. */
export function extractApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;

  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<unknown>;
    const payload = axiosError.response?.data;
    if (payload !== undefined && payload !== null) {
      if (typeof payload === 'string' && payload.trim()) {
        // FastAPI can emit plain-text bodies from proxies in front of it.
        try {
          const parsed: unknown = JSON.parse(payload);
          const fromDetail = detailToMessage(
            typeof parsed === 'object' && parsed !== null
              ? (parsed as Record<string, unknown>).detail
              : undefined,
          );
          if (fromDetail) return fromDetail;
        } catch {
          return payload.trim();
        }
        const rawDetail = detailToMessage(
          typeof payload === 'object' && payload !== null
            ? (payload as Record<string, unknown>).detail
            : undefined,
        );
        if (rawDetail) return rawDetail;
        return payload.trim();
      }
      const fromDetail = detailToMessage(
        typeof payload === 'object' ? (payload as Record<string, unknown>).detail : undefined,
      );
      if (fromDetail) return fromDetail;
    }
    if (axiosError.code === 'ECONNABORTED') return 'The request timed out.';
    if (axiosError.response) {
      return `Request failed with status ${axiosError.response.status}.`;
    }
    return axiosError.message || 'Network error.';
  }

  if (error instanceof Error) return error.message;
  if (typeof error === 'string' && error.trim()) return error;
  return 'An unexpected error occurred.';
}

function normaliseError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<unknown>;
    const payload = axiosError.response?.data;
    const issues = Array.isArray(payload) ? payload.filter(isFieldIssue) : [];
    const detail = typeof payload === 'object' && payload !== null ? (payload as Record<string, unknown>).detail : undefined;
    const validationIssues = Array.isArray(detail) ? detail.filter(isFieldIssue) : [];
    return new ApiError(
      extractApiErrorMessage(error),
      axiosError.response?.status ?? null,
      [...issues, ...validationIssues],
      axiosError.config?.url ?? null,
    );
  }
  return new ApiError(extractApiErrorMessage(error), null);
}

/** Unwrap the axios envelope so callers get plain response data. */
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: unknown) => Promise.reject(normaliseError(error)),
);

/**
 * Resolve a server-supplied path to a URL the browser can request.
 *
 * `download_url` comes back as `/api/v1/reports/1/download`; honour it verbatim
 * so the dev proxy / reverse proxy handles it. Absolute URLs pass through.
 */
export function resolveApiUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  if (path.startsWith('/api/')) return path;
  const base = API_BASE_URL.replace(/\/$/, '');
  return `${base}/${path.replace(/^\//, '')}`;
}

export default apiClient;
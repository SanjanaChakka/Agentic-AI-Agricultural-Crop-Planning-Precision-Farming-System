import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { App } from './AppRoutes';
import { SelectionProvider } from './context/SelectionContext';
import { ApiError } from './api/client';
import './index.css';

/**
 * Shared QueryClient factory. Tests build their own client with retries and
 * network calls disabled; the app instance keeps one retry and no refetch on
 * focus for a decision-support tool that is usually left open on a monitor.
 *
 * Retries are limited to transport failures and 5xx. A 4xx means the request
 * itself is wrong - retrying it just duplicates the failure and spams the
 * console, which is exactly what a missing-geolocation field used to do.
 *
 * Deliberately not exported: this module exports components only, so React Fast
 * Refresh works in development. `API_BASE_URL` lives in `api/client.ts`.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status !== null) {
    return error.status >= 500 && failureCount < 1;
  }
  return failureCount < 1;
}

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
      mutations: { retry: 0 },
    },
  });
}

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createQueryClient()}>
      <SelectionProvider>
        <BrowserRouter>{children}</BrowserRouter>
      </SelectionProvider>
    </QueryClientProvider>
  );
}

export function AppRoot() {
  return (
    <AppProviders>
      <App />
    </AppProviders>
  );
}

export default AppRoot;
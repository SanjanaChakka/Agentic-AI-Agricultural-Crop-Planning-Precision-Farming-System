import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { App } from './AppRoutes';
import { SelectionProvider } from './context/SelectionContext';
import { API_BASE_URL } from './api/client';
import './index.css';

/**
 * Shared QueryClient factory. Tests build their own client with retries and
 * network calls disabled; the app instance keeps one retry and no refetch on
 * focus for a decision-support tool that is usually left open on a monitor.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
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

export { API_BASE_URL };
export default AppRoot;
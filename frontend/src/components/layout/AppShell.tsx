import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { useIsFetching } from '@tanstack/react-query';
import { AppHeader } from './AppHeader';
import { AppSidebar } from './AppSidebar';
import { ToastProvider } from '../feedback/ToastProvider';

export interface AppShellProps {
  /** Rendered instead of the router `Outlet` in tests / storybook-style harnesses. */
  children?: React.ReactNode;
}

/**
 * Application chrome: collapsible sidebar + header, with the routed page in the
 * main column. A global toast layer surfaces API errors from anywhere.
 */
export function AppShell({ children }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const isFetching = useIsFetching();

  return (
    <ToastProvider>
      <div className="flex min-h-screen bg-slate-50">
        <AppSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <div className="flex min-w-0 flex-1 flex-col">
          <AppHeader onOpenSidebar={() => setSidebarOpen(true)} />
          {isFetching > 0 ? (
            <div
              className="h-0.5 w-full overflow-hidden bg-brand-100"
              role="progressbar"
              aria-label="Loading data"
            >
              <div className="h-full w-1/3 animate-pulse bg-brand-500" />
            </div>
          ) : null}
          <main className="min-w-0 flex-1 px-4 py-6 lg:px-6 lg:py-8">
            <div className="mx-auto w-full max-w-[1400px]">{children ?? <Outlet />}</div>
          </main>
          <footer className="border-t border-slate-200 bg-white px-4 py-4 lg:px-6">
            <p className="mx-auto max-w-[1400px] text-[11px] leading-relaxed text-slate-400">
              Agentic AI Agricultural Crop Planning &amp; Precision Farming System. Decision
              support only: this system cannot actuate equipment, and it does not diagnose crop
              conditions. Every recommendation is traceable to tagged evidence.
            </p>
          </footer>
        </div>
      </div>
    </ToastProvider>
  );
}

export default AppShell;
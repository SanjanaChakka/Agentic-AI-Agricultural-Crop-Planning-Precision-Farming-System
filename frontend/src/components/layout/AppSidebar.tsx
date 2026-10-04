import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Activity, Sprout, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../../api/health';
import { queryKeys } from '../../lib/queryKeys';
import { useSelection } from '../../context/SelectionContext';
import { SidebarNav } from './SidebarNav';
import { cn } from '../../lib/cn';

export interface AppSidebarProps {
  /** Mobile drawer state. On large screens the sidebar is always visible. */
  open: boolean;
  onClose: () => void;
}

export function AppSidebar({ open, onClose }: AppSidebarProps) {
  const { fieldId } = useSelection();
  const { pathname } = useLocation();
  const { data: health } = useQuery({
    queryKey: queryKeys.health(),
    queryFn: getHealth,
    staleTime: 60_000,
    retry: false,
  });

  // Close the drawer on Escape.
  useEffect(() => {
    if (!open) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // Auto-collapse the drawer when navigating on small screens.
  useEffect(() => {
    onClose();
  }, [pathname, onClose]);

  return (
    <>
      {/* Backdrop, small screens only. */}
      <div
        className={cn(
          'fixed inset-0 z-30 bg-slate-900/40 transition-opacity lg:hidden',
          open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        aria-label="Sidebar"
        data-testid="app-sidebar"
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-slate-200 bg-white',
          'transition-transform duration-200 lg:static lg:z-auto lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-700 text-white">
            <Sprout className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold leading-tight text-slate-900">Precision Farming</p>
            <p className="mt-0.5 text-[11px] leading-tight text-slate-500">
              Agentic crop planning platform
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 lg:hidden"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <SidebarNav onNavigate={onClose} />

        <div className="border-t border-slate-200 px-5 py-4">
          <p className="text-[11px] leading-relaxed text-slate-500">
            {fieldId
              ? 'Field-scoped pages are filtered to the field chosen in the header.'
              : 'Choose a field in the header to scope the analysis pages.'}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <span
              className={cn(
                'h-2 w-2 shrink-0 rounded-full',
                health?.status === 'healthy' ? 'bg-emerald-500' : 'bg-amber-500',
              )}
              aria-hidden="true"
            />
            <span
              className="flex items-center gap-1 truncate text-[11px] text-slate-500"
              data-testid="sidebar-health"
            >
              <Activity className="h-3 w-3" aria-hidden="true" />
              {health ? `API ${health.status}` : 'Checking API status'}
            </span>
          </div>
        </div>
      </aside>
    </>
  );
}

export default AppSidebar;
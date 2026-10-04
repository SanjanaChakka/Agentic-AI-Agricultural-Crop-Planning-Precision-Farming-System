import { NavLink, useLocation } from 'react-router-dom';
import { cn } from '../../lib/cn';
import { NAV_ITEMS, isNavItemActive } from './navItems';

export interface SidebarNavProps {
  /** Called after a link is activated - used to close the mobile drawer. */
  onNavigate?: () => void;
  className?: string;
}

export function SidebarNav({ onNavigate, className }: SidebarNavProps) {
  const { pathname } = useLocation();

  return (
    <nav aria-label="Primary" className={cn('flex-1 overflow-y-auto px-3 py-4', className)}>
      <ul className="space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = isNavItemActive(item, pathname);
          return (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === '/'}
                onClick={onNavigate}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'group flex items-start gap-3 rounded-lg px-3 py-2 transition-colors',
                  active
                    ? 'bg-brand-50 text-brand-900 ring-1 ring-inset ring-brand-200'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                )}
              >
                <Icon
                  className={cn(
                    'mt-0.5 h-4 w-4 shrink-0',
                    active ? 'text-brand-700' : 'text-slate-400 group-hover:text-slate-600',
                  )}
                  aria-hidden="true"
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium leading-tight">{item.label}</span>
                  <span className="mt-0.5 block text-[11px] leading-tight text-slate-400">
                    {item.description}
                  </span>
                </span>
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export default SidebarNav;
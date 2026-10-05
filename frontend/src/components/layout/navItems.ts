import {
  Activity,
  CalendarCheck,
  CloudSun,
  Droplets,
  FileText,
  Leaf,
  LayoutDashboard,
  Map,
  ShieldAlert,
  Sprout,
  Thermometer,
  type LucideIcon,
} from 'lucide-react';

/**
 * Primary navigation model.
 *
 * Kept apart from `SidebarNav.tsx` so that file only exports a component, which
 * keeps React Fast Refresh working in development. `NotFoundPage` also renders
 * this list, which is why it lives in its own module.
 */
export interface NavItem {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
  /** Extra path prefixes that should also highlight this item. */
  activePrefixes?: string[];
}

export const NAV_ITEMS: NavItem[] = [
  {
    to: '/',
    label: 'Dashboard',
    description: 'Portfolio overview and open alerts',
    icon: LayoutDashboard,
  },
  {
    to: '/farms',
    label: 'Farms & Fields',
    description: 'Register farms, manage fields',
    icon: Map,
    // Field detail / edit sub-pages belong to this section.
    activePrefixes: ['/fields'],
  },
  { to: '/soil', label: 'Soil', description: 'Measurements, history and thresholds', icon: Sprout },
  { to: '/weather', label: 'Weather', description: '7-day forecast with provenance', icon: CloudSun },
  { to: '/planner', label: 'Crop Planner', description: 'Weighted crop suitability', icon: Leaf },
  { to: '/sensors', label: 'Sensors', description: 'Telemetry, trends and quality', icon: Thermometer },
  {
    to: '/irrigation',
    label: 'Irrigation',
    description: 'Decision support, never actuation',
    icon: Droplets,
  },
  {
    to: '/risk',
    label: 'Crop Risk',
    description: 'Environmental favourability only',
    icon: ShieldAlert,
  },
  {
    to: '/activities',
    label: 'Activities',
    description: 'Planned work and its status',
    icon: CalendarCheck,
  },
  {
    to: '/advisory',
    label: 'AI Advisory',
    description: 'Run the agents, approve the plan',
    icon: Activity,
  },
  { to: '/reports', label: 'Reports', description: 'Generate and download PDF reports', icon: FileText },
];

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  if (item.to === '/') return pathname === '/';
  if (pathname === item.to) return true;
  return (item.activePrefixes ?? []).some((prefix) => pathname.startsWith(prefix));
}
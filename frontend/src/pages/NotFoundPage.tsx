import { Link, useLocation } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { NAV_ITEMS } from '../components/layout/SidebarNav';

/** Catch-all route. No dead end: every primary destination is one click away. */
export function NotFoundPage() {
  const location = useLocation();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Page not found"
        description={`Nothing is routed at ${location.pathname}.`}
        eyebrow="404"
      />
      <Card flush>
        <CardHeader
          title="Where would you like to go?"
          subtitle="Every section of the system is listed below."
          icon={<Compass className="h-4 w-4" aria-hidden="true" />}
        />
        <ul className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  className="flex items-start gap-3 rounded-lg border border-slate-200 p-3 transition-colors hover:border-brand-300 hover:bg-brand-50/40"
                >
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                    <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-slate-800">{item.label}</span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-slate-500">
                      {item.description}
                    </span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

export default NotFoundPage;
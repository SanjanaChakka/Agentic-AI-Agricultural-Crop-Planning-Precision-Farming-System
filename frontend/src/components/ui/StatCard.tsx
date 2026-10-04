import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { cn } from '../../lib/cn';
import { Skeleton } from './Skeleton';

export interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  to?: string;
  loading?: boolean;
  tone?: 'default' | 'brand' | 'warning' | 'danger';
  testId?: string;
}

const TONES = {
  default: 'text-slate-900',
  brand: 'text-brand-800',
  warning: 'text-amber-700',
  danger: 'text-rose-700',
} as const;

export function StatCard({
  label,
  value,
  hint,
  icon,
  to,
  loading = false,
  tone = 'default',
  testId,
}: StatCardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="label-caps">{label}</span>
        {icon ? <span className="text-slate-400">{icon}</span> : null}
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-7 w-20" />
      ) : (
        <p className={cn('tabular mt-2 text-2xl font-semibold tracking-tight', TONES[tone])}>{value}</p>
      )}
      {hint ? <p className="mt-1 text-xs leading-snug text-slate-500">{hint}</p> : null}
    </>
  );

  const className = 'card-surface p-5';

  if (to) {
    return (
      <Link
        to={to}
        data-testid={testId}
        className={cn(className, 'transition-colors hover:border-brand-300 hover:bg-brand-50/30')}
      >
        {body}
      </Link>
    );
  }

  return (
    <div className={className} data-testid={testId}>
      {body}
    </div>
  );
}

export default StatCard;
import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import { humaniseToken } from '../../lib/format';
import { toneForStatus } from './badgeTones';

export type BadgeTone =
  | 'neutral'
  | 'brand'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'violet'
  | 'slate';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-slate-100 text-slate-700 ring-slate-200',
  brand: 'bg-brand-50 text-brand-800 ring-brand-200',
  success: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  warning: 'bg-amber-50 text-amber-800 ring-amber-200',
  danger: 'bg-rose-50 text-rose-800 ring-rose-200',
  info: 'bg-sky-50 text-sky-800 ring-sky-200',
  violet: 'bg-violet-50 text-violet-800 ring-violet-200',
  slate: 'bg-slate-800 text-slate-100 ring-slate-700',
};

export interface BadgeProps {
  children?: ReactNode;
  tone?: BadgeTone;
  title?: string;
  className?: string;
  /** Adds a leading status dot. */
  dot?: boolean;
  /** Forwarded to the root span so badges stay addressable from tests. */
  'data-testid'?: string;
}

export function Badge({
  children,
  tone = 'neutral',
  title,
  className,
  dot = false,
  'data-testid': testId,
}: BadgeProps) {
  return (
    <span
      title={title}
      data-testid={testId}
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5',
        'text-[11px] font-medium ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <Badge tone="neutral">Unknown</Badge>;
  return (
    <Badge tone={toneForStatus(status)} dot>
      {humaniseToken(status)}
    </Badge>
  );
}

export default Badge;
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/cn';

export interface SpinnerProps {
  className?: string;
  label?: string;
}

export function Spinner({ className, label = 'Loading' }: SpinnerProps) {
  return (
    <span className={cn('inline-flex items-center gap-2 text-xs text-slate-500', className)} role="status">
      <Loader2 className="h-4 w-4 animate-spin text-brand-600" aria-hidden="true" />
      {label}
    </span>
  );
}

/**
 * Full-panel progress indicator used while the multi-agent run executes.
 * The agent list is streamed in so the user can see real progress, not a spinner
 * over a blank screen.
 */
export function RunProgress({ steps, label }: { steps: string[]; label: string }) {
  return (
    <div
      className="flex flex-col items-center rounded-xl border border-brand-200 bg-brand-50/60 px-6 py-8"
      data-testid="run-progress"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-6 w-6 animate-spin text-brand-700" aria-hidden="true" />
      <p className="mt-3 text-sm font-semibold text-brand-900">{label}</p>
      <p className="mt-1 text-xs text-brand-800/80">
        Twelve specialised agents are running. This usually takes a few seconds.
      </p>
      <ol className="mt-4 grid w-full max-w-2xl gap-1 text-left sm:grid-cols-2">
        {steps.map((step) => (
          <li key={step} className="flex items-center gap-2 text-xs text-brand-900/80">
            <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-brand-600" aria-hidden="true" />
            <span className="truncate">{step}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default Spinner;
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { extractApiErrorMessage } from '../../api/client';
import { cn } from '../../lib/cn';
import { Button } from './Button';

export interface ErrorBannerProps {
  /** Any thrown value - normalised through the api client's error mapper. */
  error?: unknown;
  title?: string;
  /** Render retry only when a real refetch is wired up. */
  onRetry?: () => void;
  className?: string;
  tone?: 'error' | 'warning';
}

export function ErrorBanner({
  error,
  title = 'Something went wrong',
  onRetry,
  className,
  tone = 'error',
}: ErrorBannerProps) {
  if (error === null || error === undefined) return null;
  const message = extractApiErrorMessage(error);
  if (!message) return null;

  const isWarning = tone === 'warning';

  return (
    <div
      role="alert"
      data-testid="error-banner"
      className={cn(
        'flex flex-wrap items-start gap-3 rounded-xl border px-4 py-3',
        isWarning
          ? 'border-amber-200 bg-amber-50 text-amber-900'
          : 'border-rose-200 bg-rose-50 text-rose-900',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{title}</p>
        <p className="mt-0.5 break-words text-xs leading-relaxed">{message}</p>
      </div>
      {onRetry ? (
        <Button
          size="sm"
          variant="secondary"
          onClick={onRetry}
          icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
        >
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export default ErrorBanner;
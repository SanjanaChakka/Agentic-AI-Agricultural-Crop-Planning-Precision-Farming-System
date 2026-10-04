import { AlertTriangle } from 'lucide-react';
import { cn } from '../../lib/cn';

export interface SimulatedBannerProps {
  /** The API's own flag. `is_simulated` is mandatory in the weather contract. */
  isSimulated: boolean;
  /** Optional context line, e.g. the fallback reason from `notes`. */
  detail?: string | null;
  /** What kind of data is being flagged. */
  subject?: string;
  className?: string;
}

/**
 * Loud, unmissable banner shown when the backend served fallback / simulated data.
 *
 * Rule: fallback data is NEVER presented as live API data. When `is_simulated`
 * is true this banner is rendered and the surrounding content is framed as
 * simulation output. When it is false nothing is rendered at all.
 */
export function SimulatedBanner({
  isSimulated,
  detail,
  subject = 'data',
  className,
}: SimulatedBannerProps) {
  if (!isSimulated) return null;

  return (
    <div
      role="alert"
      data-testid="simulated-banner"
      className={cn(
        'flex flex-wrap items-start gap-3 rounded-xl border-2 border-amber-400 bg-amber-50 px-4 py-3',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-amber-900">
          Simulated / fallback {subject} - not live data
        </p>
        <p className="mt-0.5 text-xs leading-relaxed text-amber-900/80">
          The backend could not reach its live upstream provider for this request, so it served
          clearly-labelled fallback data (<code className="font-mono">is_simulated: true</code>).
          Treat the numbers below as illustrative. They are not measurements from this field.
        </p>
        {detail ? (
          <p className="mt-1.5 text-xs font-medium text-amber-900">{detail}</p>
        ) : null}
      </div>
    </div>
  );
}

export default SimulatedBanner;
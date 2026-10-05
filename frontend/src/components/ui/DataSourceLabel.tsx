import { Radio } from 'lucide-react';
import { cn } from '../../lib/cn';

export interface DataSourceLabelProps {
  /** Raw `source` token from the API, e.g. `open-meteo` or `offline-climatology`. */
  source: string | null | undefined;
  /** Human readable provider name from the API. */
  provider?: string | null;
  /** True when the backend served fallback / climatology data. */
  isSimulated?: boolean | null;
  fetchedAt?: string | null;
  fallbackUsed?: boolean;
  className?: string;
}

/**
 * Always-visible provenance line for weather data.
 *
 * This renders on every weather surface regardless of whether the data is live,
 * so the reader always knows which provider the numbers came from.
 *
 * The mode flag fails *closed*: only an explicit `isSimulated === false` is
 * labelled live. A missing or unrecognised flag is treated as simulated, because
 * presenting an unlabelled fallback number as live data is the failure mode this
 * component exists to prevent.
 */
export function DataSourceLabel({
  source,
  provider,
  isSimulated,
  fetchedAt,
  fallbackUsed,
  className,
}: DataSourceLabelProps) {
  const simulated = isSimulated !== false;
  const explicitlyLive = isSimulated === false;
  return (
    <div
      data-testid="data-source-label"
      className={cn(
        'flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-600',
        className,
      )}
    >
      <Radio
        className={simulated ? 'h-3.5 w-3.5 text-amber-600' : 'h-3.5 w-3.5 text-brand-600'}
        aria-hidden="true"
      />
      <span className="label-caps">Data source</span>
      <span className="font-medium text-slate-800">{provider || source || 'unknown provider'}</span>
      {source ? <span className="font-mono text-slate-500">({source})</span> : null}
      <span
        className={cn(
          'rounded-full px-2 py-0.5 font-medium ring-1 ring-inset',
          simulated
            ? 'bg-amber-50 text-amber-800 ring-amber-300'
            : 'bg-emerald-50 text-emerald-800 ring-emerald-300',
        )}
        data-testid="data-source-mode"
      >
        {simulated ? 'Simulated fallback - not live provider data' : 'Live provider data'}
      </span>
      {simulated && !explicitlyLive ? (
        <span className="text-amber-700">is_simulated flag missing or unrecognised</span>
      ) : null}
      {fallbackUsed ? <span className="text-amber-700">fallback_used: true</span> : null}
      {fetchedAt ? <span className="text-slate-500">fetched {fetchedAt}</span> : null}
    </div>
  );
}

export default DataSourceLabel;
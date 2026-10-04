import { Menu, RefreshCw, ShieldCheck } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { listFarms, listFields } from '../../api/farms';
import { queryKeys } from '../../lib/queryKeys';
import { useSelection } from '../../context/SelectionContext';
import { Select } from '../ui/Field';
import { Button } from '../ui/Button';
import { ErrorBanner } from '../ui/ErrorBanner';

export interface AppHeaderProps {
  onOpenSidebar: () => void;
}

/**
 * Header carries the global farm/field selection that scopes every field-scoped
 * page, plus a manual refresh for the active queries.
 */
export function AppHeader({ onOpenSidebar }: AppHeaderProps) {
  const queryClient = useQueryClient();
  const { farmId, fieldId, setFarm, setField } = useSelection();

  const farmsQuery = useQuery({
    queryKey: queryKeys.farms(),
    queryFn: () => listFarms(),
    staleTime: 30_000,
  });

  const fieldsQuery = useQuery({
    queryKey: queryKeys.fields(farmId ?? undefined),
    queryFn: () => listFields(farmId ?? undefined),
    enabled: farmId !== null,
    staleTime: 30_000,
  });

  const farms = farmsQuery.data ?? [];
  const fields = fieldsQuery.data ?? [];

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 lg:px-6">
        <Button
          variant="ghost"
          size="sm"
          className="lg:hidden"
          aria-label="Open navigation"
          onClick={onOpenSidebar}
          icon={<Menu className="h-4 w-4" aria-hidden="true" />}
        >
          <span className="sr-only">Menu</span>
        </Button>

        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="farm-selector">
            Farm
          </label>
          <Select
            id="farm-selector"
            aria-label="Farm"
            className="h-9 w-auto min-w-[11rem] py-1 text-xs"
            value={farmId === null ? '' : String(farmId)}
            onChange={(event) => {
              const next = event.target.value ? Number(event.target.value) : null;
              const farm = farms.find((item) => item.id === next) ?? null;
              setFarm(next, farm);
            }}
          >
            <option value="">All farms</option>
            {farms.map((farm) => (
              <option key={farm.id} value={farm.id}>
                {farm.name} ({farm.field_count ?? 0} fields)
              </option>
            ))}
          </Select>

          <label className="sr-only" htmlFor="field-selector">
            Field
          </label>
          <Select
            id="field-selector"
            aria-label="Field"
            className="h-9 w-auto min-w-[13rem] py-1 text-xs"
            disabled={farmId === null}
            value={fieldId === null ? '' : String(fieldId)}
            onChange={(event) => {
              const next = event.target.value ? Number(event.target.value) : null;
              const field = fields.find((item) => item.id === next) ?? null;
              setField(next, field);
            }}
          >
            <option value="">{farmId === null ? 'Select a farm first' : 'All fields'}</option>
            {fields.map((field) => (
              <option key={field.id} value={field.id}>
                {field.field_code} · {field.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span
            className="hidden items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-medium text-brand-800 ring-1 ring-inset ring-brand-200 md:inline-flex"
            title="Every physical action requires explicit human authorisation."
          >
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Human-in-the-loop
          </span>
          <Button
            size="sm"
            variant="secondary"
            aria-label="Refresh data"
            onClick={() => void queryClient.invalidateQueries()}
            icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {farmsQuery.error ? (
        <ErrorBanner
          className="mx-4 mb-3 lg:mx-6"
          title="Could not load farms"
          error={farmsQuery.error}
          onRetry={() => void farmsQuery.refetch()}
        />
      ) : null}
      {fieldsQuery.error ? (
        <ErrorBanner
          className="mx-4 mb-3 lg:mx-6"
          title="Could not load fields"
          error={fieldsQuery.error}
          onRetry={() => void fieldsQuery.refetch()}
        />
      ) : null}
    </header>
  );
}

export default AppHeader;
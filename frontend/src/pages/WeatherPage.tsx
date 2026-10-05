import { useState } from 'react';
import {
  CalendarDays,
  CloudRain,
  Droplets,
  RefreshCw,
  Thermometer,
  Wind,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { Button } from '../components/ui/Button';
import { StatCard } from '../components/ui/StatCard';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { SkeletonBlock, SkeletonStats, SkeletonTable } from '../components/ui/Skeleton';
import { SimulatedBanner } from '../components/ui/SimulatedBanner';
import { DataSourceLabel } from '../components/ui/DataSourceLabel';
import { EvidenceKindBadge } from '../components/ui/EvidenceKindBadge';
import { FieldGate } from '../components/layout/FieldGate';
import { DailyWeatherChart } from '../components/charts/DailyWeatherChart';
import { useFieldWeather, useFieldWeatherEvidence } from '../hooks/useWeather';
import { useSelection } from '../context/SelectionContext';
import { ApiError } from '../api/client';
import type { Evidence, WeatherBundle, WeatherDay } from '../api/types';
import { formatDateTime, formatNumber, formatShortDate } from '../lib/format';

/**
 * The backend rejects a forecast for a field with no coordinates with 422 and
 * an explanatory message. That is a missing-input state, not a failure, so it
 * gets an actionable empty state instead of a red error banner.
 */
function isMissingGeolocation(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 422 &&
    /no geolocation/i.test(error.message)
  );
}

/**
 * Weather.
 *
 * GET /weather/fields/{id}?days=7 · GET /weather/fields/{id}/evidence
 *
 * The contract makes `source`, `provider` and `is_simulated` mandatory. The
 * source label is always rendered; the simulated banner appears whenever
 * `is_simulated` is true, and the surrounding content is framed as fallback
 * output so it is never mistaken for live provider data.
 */
export function WeatherPage() {
  const { fieldId } = useSelection();
  const [days, setDays] = useState(7);
  const weather = useFieldWeather(fieldId, days);
  const evidence = useFieldWeatherEvidence(fieldId);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Weather"
        description="Seven-day forecast context for the selected field, with the provider and any fallback labelling always visible."
        actions={
          <>
            <div className="flex items-center gap-2">
              <label htmlFor="forecast-days" className="label-caps">
                Days
              </label>
              <select
                id="forecast-days"
                value={days}
                onChange={(event) => setDays(Number(event.target.value))}
                className="h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs"
              >
                {[3, 5, 7, 10, 14].map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <Button
              variant="secondary"
              loading={weather.isFetching}
              icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
              onClick={() => void weather.refetch()}
            >
              Refresh
            </Button>
          </>
        }
      />

      <FieldGate>
        {weather.isLoading ? (
          <div className="space-y-6">
            <SkeletonStats count={4} />
            <Card>
              <SkeletonBlock lines={5} />
            </Card>
          </div>
        ) : weather.error ? (
          isMissingGeolocation(weather.error) ? (
            <EmptyState
              title="This field has no coordinates"
              description="Weather cannot be requested without a latitude and longitude. Open the field's edit page and set both, or add them to the farm so every field inherits them. Until then the agents fall back to offline climatology."
              icon={<CloudRain className="h-5 w-5" aria-hidden="true" />}
            />
          ) : (
            <ErrorBanner
              title="Could not load the forecast"
              error={weather.error}
              onRetry={() => void weather.refetch()}
            />
          )
        ) : !weather.data ? (
          <EmptyState
            title="No forecast available"
            description="The API returned no weather bundle for this field."
            icon={<CloudRain className="h-5 w-5" aria-hidden="true" />}
          />
        ) : (
          <WeatherContent
            weather={weather.data}
            evidence={evidence.data?.evidence ?? []}
            evidenceLoading={evidence.isLoading}
          />
        )}
      </FieldGate>
    </div>
  );
}

function WeatherContent({
  weather,
  evidence,
  evidenceLoading,
}: {
  weather: WeatherBundle;
  evidence: Evidence[];
  evidenceLoading: boolean;
}) {
  const { daily } = weather;

  return (
    <div className="space-y-6">
      {/* Loud, mandatory banner whenever the backend served fallback data. */}
      <SimulatedBanner
        isSimulated={weather.is_simulated}
        subject="weather"
        detail={weather.notes?.length ? weather.notes.join(' · ') : null}
      />

      {/* Always visible, live or simulated. */}
      <DataSourceLabel
        source={weather.source}
        provider={weather.provider}
        isSimulated={weather.is_simulated}
        fallbackUsed={weather.fallback_used}
        fetchedAt={formatDateTime(weather.fetched_at)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2"
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          label="Max temperature"
          value={`${formatNumber(weather.max_temp_c, 1)} °C`}
          hint={`Min ${formatNumber(weather.min_temp_c, 1)} °C`}
          icon={<Thermometer className="h-4 w-4" aria-hidden="true" />}
        />
        <StatCard
          label="Total precipitation"
          value={`${formatNumber(weather.total_precipitation_mm, 1)} mm`}
          hint={`${formatNumber(weather.rainfall_next_3_days_mm, 1)} mm in the next 3 days`}
          icon={<CloudRain className="h-4 w-4" aria-hidden="true" />}
        />
        <StatCard
          label="Reference ET0"
          value={`${formatNumber(weather.total_et0_mm, 1)} mm`}
          hint="Sum over the forecast window"
          icon={<Droplets className="h-4 w-4" aria-hidden="true" />}
        />
        <StatCard
          label="Mean humidity"
          value={`${formatNumber(weather.mean_humidity_percent, 0)}%`}
          hint="Across the forecast window"
        />
        <StatCard
          label="Current conditions"
          value={weather.current?.condition ?? 'not reported'}
          hint={
            weather.current
              ? `${formatNumber(weather.current.temperature_c, 1)} °C, ${formatNumber(weather.current.humidity_percent, 0)}% RH, wind ${formatNumber(weather.current.wind_speed_ms, 1)} m/s`
              : undefined
          }
          icon={<Wind className="h-4 w-4" aria-hidden="true" />}
        />
      </div>

      <DailyWeatherChart data={daily} height={280} />

      <Card flush>
        <CardHeader
          title={`${daily.length}-day forecast`}
          subtitle={
            weather.location_name
              ? `${weather.location_name} (${formatNumber(weather.latitude, 3)}, ${formatNumber(weather.longitude, 3)})`
              : undefined
          }
          icon={<CalendarDays className="h-4 w-4" aria-hidden="true" />}
        />
        {daily.length === 0 ? (
          <div className="p-5">
            <EmptyState title="No daily rows" description="The provider returned an empty forecast window." />
          </div>
        ) : (
          <DataTable<WeatherDay>
            columns={[
              {
                key: 'date',
                header: 'Date',
                render: (day) => (
                  <span className="whitespace-nowrap text-xs font-medium text-slate-800">
                    {formatShortDate(day.forecast_date)}
                  </span>
                ),
              },
              {
                key: 'condition',
                header: 'Condition',
                render: (day) => <span className="text-xs text-slate-700">{day.condition ?? '-'}</span>,
              },
              {
                key: 'minmax',
                header: 'Min / max',
                className: 'tabular whitespace-nowrap',
                render: (day) =>
                  `${formatNumber(day.temp_min_c, 1)} / ${formatNumber(day.temp_max_c, 1)} °C`,
              },
              {
                key: 'precip',
                header: 'Precipitation',
                className: 'tabular whitespace-nowrap',
                render: (day) => (
                  <>
                    {formatNumber(day.precipitation_mm, 1)} mm
                    {day.precipitation_probability_percent !== null &&
                    day.precipitation_probability_percent !== undefined ? (
                      <span className="ml-1 text-[11px] text-slate-400">
                        ({formatNumber(day.precipitation_probability_percent, 0)}%)
                      </span>
                    ) : null}
                  </>
                ),
              },
              {
                key: 'humidity',
                header: 'Humidity',
                className: 'tabular',
                render: (day) => `${formatNumber(day.humidity_percent, 0)}%`,
              },
              {
                key: 'wind',
                header: 'Wind',
                className: 'tabular',
                render: (day) => `${formatNumber(day.wind_speed_ms, 1)} m/s`,
              },
              {
                key: 'et0',
                header: 'ET0',
                className: 'tabular',
                render: (day) => `${formatNumber(day.et0_mm, 2)} mm`,
              },
            ]}
            rows={daily}
            rowKey={(day) => day.forecast_date}
            dense
          />
        )}
      </Card>

      {weather.notes.length > 0 ? (
        <Card>
          <CardHeader title="Provider notes" />
          <ul className="space-y-1 p-5">
            {weather.notes.map((note) => (
              <li key={note} className="text-xs leading-relaxed text-slate-600">
                {note}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card flush>
        <CardHeader
          title={`Weather evidence (${evidence.length})`}
          subtitle="GET /weather/fields/{id}/evidence - the provenance-tagged facts behind this forecast."
        />
        <div className="p-5">
          {evidenceLoading ? (
            <SkeletonTable rows={3} columns={2} />
          ) : evidence.length === 0 ? (
            <EmptyState
              title="No weather evidence recorded"
              description="The evidence endpoint returned no tagged facts for this field."
            />
          ) : (
            <ul className="space-y-2">
              {evidence.map((item, index) => (
                <li key={`${item.label}-${index}`} className="flex flex-wrap items-start gap-2">
                  <EvidenceKindBadge kind={item.kind} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-slate-700">{item.label}</p>
                    <p className="tabular text-xs text-slate-600">
                      {item.value === null || item.value === undefined ? '-' : String(item.value)}
                      {item.unit ? ` ${item.unit}` : ''}
                      {item.note ? <span className="ml-1 text-slate-400">({item.note})</span> : null}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </div>
  );
}

export default WeatherPage;
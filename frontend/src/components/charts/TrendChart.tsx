import { useMemo } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardHeader } from '../ui/Card';

export interface TrendSeries {
  key: string;
  label: string;
  color: string;
  unit?: string;
}

export interface TrendChartProps {
  title: string;
  subtitle?: string;
  data: Array<Record<string, unknown>>;
  series: TrendSeries[];
  xKey: string;
  /** Rendered on the left axis. */
  height?: number;
  referenceLines?: Array<{ y: number; label: string; color?: string }>;
  emptyMessage?: string;
}

/**
 * Shared multi-series line chart. Data always comes from the API - there is no
 * generated or placeholder series anywhere in the app.
 */
export function TrendChart({
  title,
  subtitle,
  data,
  series,
  xKey,
  height = 260,
  referenceLines = [],
  emptyMessage = 'No readings in this window.',
}: TrendChartProps) {
  const hasData = data.length > 0;
  const axisLabel = useMemo(() => {
    const units = series.map((item) => item.unit).filter(Boolean);
    return Array.from(new Set(units)).join(' / ');
  }, [series]);

  return (
    <Card flush>
      <CardHeader
        title={title}
        subtitle={subtitle ?? (axisLabel ? `Units: ${axisLabel}` : undefined)}
      />
      {!hasData ? (
        <p className="px-5 py-10 text-center text-xs text-slate-500">{emptyMessage}</p>
      ) : (
        <div className="p-4" style={{ height: height + 32 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis
                dataKey={xKey}
                tickLine={false}
                axisLine={{ stroke: '#cbd5e1' }}
                minTickGap={24}
                tickMargin={8}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={56}
                tickMargin={8}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{ fontSize: 12 }}
                labelFormatter={(value) => String(value)}
              />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
              {referenceLines.map((line) => (
                <ReferenceLine
                  key={line.label}
                  y={line.y}
                  stroke={line.color ?? '#94a3b8'}
                  strokeDasharray="4 4"
                  label={{ value: line.label, position: 'insideTopRight', fontSize: 10, fill: '#64748b' }}
                />
              ))}
              {series.map((item) => (
                <Line
                  key={item.key}
                  type="monotone"
                  dataKey={item.key}
                  name={item.unit ? `${item.label} (${item.unit})` : item.label}
                  stroke={item.color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 3 }}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

export default TrendChart;
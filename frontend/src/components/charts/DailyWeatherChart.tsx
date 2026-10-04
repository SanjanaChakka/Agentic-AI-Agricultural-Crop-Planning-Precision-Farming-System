import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardHeader } from '../ui/Card';
import { formatShortDate } from '../../lib/format';
import type { WeatherDay } from '../../api/types';

export interface DailyWeatherChartProps {
  /** Rows straight from the API's `daily` forecast array. */
  data: WeatherDay[];
  dateKey?: string;
  height?: number;
}

/** Daily min/max temperature band plus forecast rainfall on a second axis. */
export function DailyWeatherChart({
  data,
  dateKey = 'forecast_date',
  height = 280,
}: DailyWeatherChartProps) {
  return (
    <Card flush>
      <CardHeader
        title="7-day temperature and rainfall"
        subtitle="Bars show forecast precipitation (mm); lines show daily minimum and maximum temperature."
      />
      <div className="p-4" style={{ height: height + 32 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey={dateKey}
              tickLine={false}
              axisLine={{ stroke: '#cbd5e1' }}
              tickMargin={8}
              tickFormatter={(value: string) => formatShortDate(value)}
            />
            <YAxis yAxisId="temp" tickLine={false} axisLine={false} width={48} />
            <YAxis yAxisId="rain" orientation="right" tickLine={false} axisLine={false} width={40} />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              labelFormatter={(value) => formatShortDate(String(value), String(value))}
            />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
            <Bar
              yAxisId="rain"
              dataKey="precipitation_mm"
              name="Precipitation (mm)"
              fill="#7dd3fc"
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
            <Line
              yAxisId="temp"
              type="monotone"
              dataKey="temp_max_c"
              name="Max temp (C)"
              stroke="#b45309"
              strokeWidth={2}
              dot={{ r: 2 }}
              isAnimationActive={false}
            />
            <Line
              yAxisId="temp"
              type="monotone"
              dataKey="temp_min_c"
              name="Min temp (C)"
              stroke="#0369a1"
              strokeWidth={2}
              dot={{ r: 2 }}
              isAnimationActive={false}
            />
            <ReferenceLine yAxisId="rain" y={0} stroke="#cbd5e1" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

export default DailyWeatherChart;
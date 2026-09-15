import { useId } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useChartTheme } from "../../lib/chartTheme";

export interface TrendSeries {
  key: string;
  label: string;
  type?: "area" | "line" | "bar";
  colorIndex?: number;
  dashed?: boolean;
  /** Areas with the same `stack` id are layered instead of overlaid. */
  stack?: boolean;
}

interface TooltipPayloadItem {
  name?: string;
  value?: number | string;
  color?: string;
  dataKey?: string;
}

function TooltipCard({
  active,
  payload,
  label,
  valueFormatter,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string | number;
  valueFormatter?: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__label">{label}</div>
      {payload.map((item, i) => (
        <div className="chart-tooltip__row" key={`${item.dataKey}-${i}`}>
          <span className="chart-tooltip__dot" style={{ background: item.color }} />
          <span>{item.name}</span>
          <span className="spacer" />
          <span className="num">
            {typeof item.value === "number" && valueFormatter
              ? valueFormatter(item.value)
              : item.value}
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * Time-series chart with Phoenix chart tokens: solid low-opacity gridlines,
 * quiet axis text, themed tooltip panel.
 */
export function TrendChart({
  data,
  xKey = "day",
  series,
  height = 240,
  valueFormatter,
}: {
  data: Record<string, unknown>[];
  xKey?: string;
  series: TrendSeries[];
  height?: number;
  valueFormatter?: (value: number) => string;
}) {
  const theme = useChartTheme();
  const gradientId = useId().replace(/:/g, "");

  const axisProps = {
    stroke: theme.axis,
    tick: { fontSize: 12, fill: theme.axisText },
    tickLine: false,
    axisLine: false,
  } as const;

  const tooltip = (
    <Tooltip
      cursor={{ fill: theme.grid }}
      content={<TooltipCard valueFormatter={valueFormatter} />}
    />
  );

  const renders = series.map((s) => {
    const color = theme.series[s.colorIndex ?? 0];
    return { ...s, color };
  });

  const isBar = renders.every((s) => (s.type ?? "area") === "bar");
  const hasArea = renders.some((s) => (s.type ?? "area") === "area");

  return (
    <ResponsiveContainer width="100%" height={height}>
      {isBar ? (
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={theme.grid} vertical={false} />
          <XAxis dataKey={xKey} {...axisProps} />
          <YAxis {...axisProps} width={56} tickFormatter={valueFormatter} />
          {tooltip}
          {renders.map((s) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              fill={s.color}
              radius={[2, 2, 0, 0]}
              maxBarSize={28}
            />
          ))}
        </BarChart>
      ) : hasArea ? (
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            {renders.map((s, i) => (
              <linearGradient key={s.key} id={`${gradientId}-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.28} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke={theme.grid} vertical={false} />
          <XAxis dataKey={xKey} {...axisProps} />
          <YAxis {...axisProps} width={56} tickFormatter={valueFormatter} />
          {tooltip}
          {renders.map((s, i) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stackId={s.stack ? "stack" : undefined}
              stroke={s.color}
              fill={`url(#${gradientId}-${i})`}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
            />
          ))}
        </AreaChart>
      ) : (
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={theme.grid} vertical={false} />
          <XAxis dataKey={xKey} {...axisProps} />
          <YAxis {...axisProps} width={56} tickFormatter={valueFormatter} />
          {tooltip}
          {renders.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={s.dashed ? "5 4" : undefined}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
            />
          ))}
        </LineChart>
      )}
    </ResponsiveContainer>
  );
}

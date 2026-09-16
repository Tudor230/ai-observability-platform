/** Linear least-squares forecast on a cost time series (labeled estimate). */

export interface ForecastPoint {
  day: string;
  cost: number;
}

export const MIN_FORECAST_POINTS = 3;

function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysBetween(from: string, to: string): number {
  const a = Date.parse(`${from}T00:00:00Z`);
  const b = Date.parse(`${to}T00:00:00Z`);
  if (isNaN(a) || isNaN(b)) throw new Error(`invalid day range: ${from}..${to}`);
  return Math.round((b - a) / 86_400_000);
}

export function buildForecast(
  history: { day: string; cost: number }[],
  days: number,
  asOf?: string
): ForecastPoint[] {
  const points = history
    .map((p) => [daysBetween(history[0].day, p.day), p.cost] as const)
    .filter(([, v]) => v > 0);
  if (points.length < MIN_FORECAST_POINTS) return [];

  const n = points.length;
  const meanX = points.reduce((s, [x]) => s + x, 0) / n;
  const meanY = points.reduce((s, [, y]) => s + y, 0) / n;
  let num = 0;
  let den = 0;
  for (const [x, y] of points) {
    num += (x - meanX) * (y - meanY);
    den += (x - meanX) ** 2;
  }
  const slope = den ? num / den : 0;
  const intercept = meanY - slope * meanX;

  // Forecast starts after today (or after the last data day, whichever is
  // later) so a stale dataset is not projected onto days that already passed.
  const lastDay = history[history.length - 1].day;
  const anchor = asOf && asOf > lastDay ? asOf : lastDay;
  return Array.from({ length: days }, (_, i) => {
    const day = dayOffset(anchor, i + 1);
    const x = daysBetween(history[0].day, day);
    return { day, cost: Math.max(0, slope * x + intercept) };
  });
}

export function dayOffset(day: string, offset: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  if (isNaN(d.getTime())) throw new Error(`invalid day: ${day}`);
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}

export function forecastAsOf(): string {
  return todayUtc();
}

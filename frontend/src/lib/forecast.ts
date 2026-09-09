/** Linear least-squares forecast on a cost time series (labeled estimate). */

export interface ForecastPoint {
  day: string;
  cost: number;
}

export function buildForecast(
  history: { day: string; cost: number }[],
  days: number
): ForecastPoint[] {
  const points = history.map((p, i) => [i, p.cost] as const).filter(([, v]) => v > 0);
  if (points.length < 3) return [];
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
  const last = history.length - 1;
  const lastDay = history[last].day;
  return Array.from({ length: days }, (_, i) => {
    const x = last + 1 + i;
    return { day: dayOffset(lastDay, i + 1), cost: Math.max(0, slope * x + intercept) };
  });
}

export function dayOffset(day: string, offset: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  if (isNaN(d.getTime())) throw new Error(`invalid day: ${day}`);
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}
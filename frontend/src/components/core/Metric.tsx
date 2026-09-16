import type { ReactNode } from "react";
import { IconTrendDown, IconTrendUp } from "./icons";

/** A metric tile (Phoenix-style stat card). */
export function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "danger" | "warning" | "success";
}) {
  return (
    <div className="metric">
      <div className="metric__label">{label}</div>
      <div className="metric__value" data-tone={tone && tone !== "default" ? tone : undefined}>
        {value}
      </div>
      {sub ? <div className="metric__sub">{sub}</div> : null}
    </div>
  );
}

/**
 * A period-over-period delta. `polarity` says which direction is bad
 * ("up" is bad for cost, "down" is bad for throughput, "neutral" never
 * colors the value).
 */
export function Delta({
  pct,
  polarity = "up-is-bad",
  label = "vs prev",
}: {
  pct: number | null | undefined;
  polarity?: "up-is-bad" | "down-is-bad" | "neutral";
  label?: string;
}) {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return null;
  const direction = pct >= 0 ? "up" : "down";
  return (
    <span
      className="metric__delta"
      data-direction={direction}
      data-polarity={polarity === "up-is-bad" ? "bad" : polarity === "down-is-bad" ? "plain" : "neutral"}
    >
      {direction === "up" ? <IconTrendUp size={12} /> : <IconTrendDown size={12} />}
      {pct >= 0 ? "+" : ""}
      {pct.toFixed(1)}% {label}
    </span>
  );
}

export function Progress({
  fraction,
  label,
  detail,
}: {
  fraction: number;
  label: ReactNode;
  detail?: ReactNode;
}) {
  const clamped = Math.max(0, Math.min(1, fraction));
  const state = fraction >= 1 ? "danger" : fraction >= 0.8 ? "warning" : "ok";
  return (
    <div className="progress">
      <div className="row">
        <span className="truncate">{label}</span>
        <span className="spacer" />
        <span className="muted num">{detail}</span>
      </div>
      <div className="progress__track">
        <div
          className="progress__fill"
          data-state={state}
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
    </div>
  );
}

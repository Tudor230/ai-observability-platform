import { useState } from "react";
import type { MarginTotals } from "../api/types";
import { CardPanel, Select } from "./core";
import { TrendChart } from "./charts/TrendChart";
import { formatMoney, formatPct } from "../lib/format";

const SCALES = [1, 2, 5, 10];

/**
 * Scaling forecast (ADR-0013): today's unit economics multiplied by a volume
 * factor. Revenue and manual cost stay as entered (a contract does not grow
 * with usage), so the projection answers "how much volume does this revenue
 * support?" — including the break-even multiple.
 */
export function MarginScaling({ totals }: { totals: MarginTotals }) {
  const [scale, setScale] = useState(2);

  const project = (factor: number) => {
    const aiCost = totals.ai_cost * factor;
    const margin = totals.revenue - totals.manual_cost - aiCost;
    return {
      label: `×${factor}`,
      ai_cost: aiCost,
      margin,
      margin_pct: totals.revenue > 0 ? margin / totals.revenue : null,
    };
  };

  const rows = SCALES.map(project);
  const selected = project(scale);
  const breakEven = totals.break_even_scale;

  let breakEvenText: string;
  if (!breakEven || totals.ai_cost === 0) {
    breakEvenText = "No AI cost in this window — nothing to break even.";
  } else if (breakEven >= 1) {
    breakEvenText = `Revenue covers AI cost up to ×${breakEven.toFixed(1)} of today's volume; past that, margin inverts.`;
  } else {
    breakEvenText = `AI cost already exceeds the contribution — margin only holds below ×${breakEven.toFixed(2)} of today's volume.`;
  }

  return (
    <CardPanel
      title="Scaling forecast"
      subTitle="Cost and margin as volume multiplies — estimate from today's unit economics"
    >
      <div className="stack" style={{ padding: "var(--global-dimension-size-100)" }}>
        <div className="row" style={{ justifyContent: "space-between", gap: 12 }}>
          <span className="muted">{totals.executions.toLocaleString("en-US")} executions in window</span>
          <Select
            value={String(scale)}
            aria-label="Scale"
            onChange={(event) => setScale(Number(event.target.value))}
          >
            {SCALES.map((factor) => (
              <option key={factor} value={factor}>
                ×{factor} volume
              </option>
            ))}
          </Select>
        </div>

        <TrendChart
          data={rows}
          xKey="label"
          series={[{ key: "margin", label: "Margin", type: "bar", colorIndex: 0 }]}
          valueFormatter={formatMoney}
          height={180}
        />

        <p className="muted" style={{ margin: 0 }}>
          At ×{scale}: AI cost {formatMoney(selected.ai_cost)} · margin{" "}
          {formatMoney(selected.margin)}
          {selected.margin_pct === null ? "" : ` (${formatPct(selected.margin_pct)} of revenue)`}
        </p>
        <p style={{ margin: 0 }}>{breakEvenText}</p>
      </div>
    </CardPanel>
  );
}

import type { LoopInfo } from "../api/types";

/** Human labels for the backend's loop signals (ADR-0014). */
export const LOOP_SIGNAL_LABELS: Record<string, string> = {
  tool_repeat: "Repeated tool calls",
  llm_repeat: "Repeated LLM calls",
  cycle: "Repeating cycle",
};

export function loopSignalLabels(info: LoopInfo | null | undefined): string[] {
  if (!info) return [];
  return info.signals.map((signal) => LOOP_SIGNAL_LABELS[signal] ?? signal);
}

/** One-line summary for badges/tooltips: counts per signal, cycle steps included. */
export function loopSummary(info: LoopInfo | null | undefined): string {
  if (!info) return "Loop detected";
  const bits: string[] = [];
  if (info.tool_repeats > 1) bits.push(`${info.tool_repeats}× the same tool call`);
  if (info.llm_repeats > 1) bits.push(`${info.llm_repeats}× the same LLM call`);
  if (info.cycle_repeats > 1 && info.cycle_steps.length > 0) {
    bits.push(`${info.cycle_repeats}× the cycle ${info.cycle_steps.join(" → ")}`);
  }
  return bits.length > 0 ? `Loop detected: ${bits.join(", ")}` : "Loop detected";
}

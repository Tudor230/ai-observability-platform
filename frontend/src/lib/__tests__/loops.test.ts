import { describe, expect, it } from "vitest";
import type { LoopInfo } from "../../api/types";
import { loopSignalLabels, loopSummary } from "../loops";

const info: LoopInfo = {
  signals: ["tool_repeat", "cycle"],
  tool_repeats: 4,
  llm_repeats: 1,
  cycle_repeats: 3,
  cycle_steps: ["llm_call", "lookup_order"],
};

describe("loop helpers", () => {
  it("maps signals to human labels", () => {
    expect(loopSignalLabels(info)).toEqual(["Repeated tool calls", "Repeating cycle"]);
    expect(loopSignalLabels(null)).toEqual([]);
  });

  it("summarises counts and cycle steps", () => {
    expect(loopSummary(info)).toBe(
      "Loop detected: 4× the same tool call, 3× the cycle llm_call → lookup_order"
    );
  });

  it("never invents counts when only a signal is present", () => {
    expect(loopSummary({ signals: ["cycle"], tool_repeats: 1, llm_repeats: 1, cycle_repeats: 1, cycle_steps: [] })).toBe(
      "Loop detected"
    );
    expect(loopSummary(null)).toBe("Loop detected");
  });
});

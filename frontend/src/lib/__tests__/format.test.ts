import { describe, expect, it } from "vitest";
import { formatMoney, formatTokens, formatMs, formatPct, formatDate } from "../format";

describe("formatMoney", () => {
  it("keeps precision for sub-cent amounts", () => {
    expect(formatMoney(0.00045)).toBe("$0.00045");
    expect(formatMoney(0.005)).toBe("$0.005");
  });

  it("groups and rounds normal amounts", () => {
    expect(formatMoney(1234.5)).toBe("$1,234.50");
    expect(formatMoney(0)).toBe("$0.00");
    expect(formatMoney(12)).toBe("$12.00");
  });

  it("handles null/undefined", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
  });
});

describe("formatTokens", () => {
  it("formats thousands and millions", () => {
    expect(formatTokens(999)).toBe("999");
    expect(formatTokens(1500)).toBe("1.5k");
    expect(formatTokens(1_500_000)).toBe("1.50M");
  });

  it("handles null", () => {
    expect(formatTokens(null)).toBe("—");
  });
});

describe("formatMs", () => {
  it("uses seconds above 1000ms", () => {
    expect(formatMs(250)).toBe("250ms");
    expect(formatMs(3200)).toBe("3.20s");
  });
});

describe("formatPct", () => {
  it("converts ratio to percent", () => {
    expect(formatPct(0.0625)).toBe("6.3%");
    expect(formatPct(0.5)).toBe("50.0%");
  });
});

describe("formatDate", () => {
  it("renders ISO strings", () => {
    const out = formatDate("2026-09-09T10:00:00Z");
    expect(out).not.toBe("—");
  });

  it("handles missing", () => {
    expect(formatDate(null)).toBe("—");
  });
});
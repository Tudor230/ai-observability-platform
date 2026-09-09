import { describe, expect, it } from "vitest";
import { buildForecast, dayOffset } from "../forecast";

describe("dayOffset", () => {
  it("rolls across month boundaries", () => {
    expect(dayOffset("2026-09-30", 1)).toBe("2026-10-01");
    expect(dayOffset("2026-12-31", 1)).toBe("2027-01-01");
  });
});

describe("buildForecast", () => {
  it("returns empty for sparse history", () => {
    expect(buildForecast([{ day: "2026-09-01", cost: 1 }], 7)).toEqual([]);
    expect(buildForecast([], 7)).toEqual([]);
  });

  it("produces the requested number of future points", () => {
    const history = [
      { day: "2026-09-01", cost: 1 },
      { day: "2026-09-02", cost: 2 },
      { day: "2026-09-03", cost: 3 },
      { day: "2026-09-04", cost: 4 },
    ];
    const forecast = buildForecast(history, 7);
    expect(forecast).toHaveLength(7);
    expect(forecast[0].day).toBe("2026-09-05");
    // Perfectly linear history -> slope 1, next value 5.
    expect(forecast[0].cost).toBeCloseTo(5, 6);
  });

  it("never returns negative costs", () => {
    const history = [
      { day: "2026-09-01", cost: 0 },
      { day: "2026-09-02", cost: 0 },
      { day: "2026-09-03", cost: 1 },
      { day: "2026-09-04", cost: 0 },
    ];
    const forecast = buildForecast(history, 5);
    expect(forecast.every((p) => p.cost >= 0)).toBe(true);
  });
});
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { BreakdownBars } from "./BreakdownBars";
import { TrendChart } from "./TrendChart";

const data = [
  { day: "01-01", cost: 1, executions: 2 },
  { day: "01-02", cost: 3, executions: 4 },
];

describe("TrendChart", () => {
  it("renders an accessible chart container with series labels", () => {
    render(
      <TrendChart
        data={data}
        series={[
          { key: "cost", label: "Cost" },
          { key: "executions", label: "Executions", type: "bar" },
        ]}
      />
    );
    const chart = screen.getByRole("img");
    expect(chart).toHaveAttribute("aria-label", "Chart: Cost, Executions");
  });

  it("supports a custom aria label", () => {
    render(
      <TrendChart
        data={data}
        series={[{ key: "cost", label: "Cost" }]}
        ariaLabel="Cost over time"
      />
    );
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "Cost over time");
  });

  it("renders with empty data without crashing", () => {
    render(<TrendChart data={[]} series={[{ key: "cost", label: "Cost" }]} />);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });
});

describe("BreakdownBars", () => {
  it("renders labels, values and sublabels", () => {
    render(
      <BreakdownBars
        rows={[
          { key: "a", label: "checkout", value: 10, valueLabel: "$10.00", sublabel: "5 executions" },
          { key: "b", label: "refund", value: 5, valueLabel: "$5.00" },
        ]}
      />
    );
    expect(screen.getByText("checkout")).toBeInTheDocument();
    expect(screen.getByText("$10.00")).toBeInTheDocument();
    expect(screen.getByText("5 executions")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      "Breakdown: checkout, refund"
    );
  });

  it("renders links when href is provided", () => {
    render(
      <MemoryRouter>
        <BreakdownBars
          rows={[
            {
              key: "a",
              label: "checkout",
              value: 1,
              valueLabel: "$1",
              href: "/engineering?workflow=x",
            },
          ]}
        />
      </MemoryRouter>
    );
    const link = screen.getByRole("link", { name: "checkout" });
    expect(link).toHaveAttribute("href", "/engineering?workflow=x");
  });
});

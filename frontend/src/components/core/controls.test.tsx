import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { EmptyState } from "./Feedback";
import { SearchableSelect } from "./SearchableSelect";
import { Delta, Metric, Progress } from "./Metric";
import { Button } from "./Button";
import { Tabs } from "./Tabs";

const options = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

describe("SearchableSelect", () => {
  it("filters options and selects on mousedown", () => {
    const onChange = vi.fn();
    render(
      <SearchableSelect value="" onChange={onChange} options={options} aria-label="Scope" />
    );
    const input = screen.getByLabelText("Scope");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "bet" } });
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
    fireEvent.mouseDown(screen.getByText("Beta"));
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("supports keyboard selection", () => {
    const onChange = vi.fn();
    render(
      <SearchableSelect value="" onChange={onChange} options={options} aria-label="Scope" />
    );
    const input = screen.getByLabelText("Scope");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("shows the selected option label when closed", () => {
    render(
      <SearchableSelect value="c" onChange={() => {}} options={options} aria-label="Scope" />
    );
    expect(screen.getByLabelText("Scope")).toHaveValue("Gamma");
  });

  it("respects the disabled state", () => {
    render(
      <SearchableSelect value="" onChange={() => {}} options={options} disabled aria-label="Scope" />
    );
    expect(screen.getByLabelText("Scope")).toBeDisabled();
  });
});

describe("Metric / Delta / Progress", () => {
  it("renders label, value and sub", () => {
    render(<Metric label="Cost" value="$1.23" sub="today" />);
    expect(screen.getByText("Cost")).toBeInTheDocument();
    expect(screen.getByText("$1.23")).toBeInTheDocument();
    expect(screen.getByText("today")).toBeInTheDocument();
  });

  it("tones deltas by polarity", () => {
    const { container } = render(<Delta pct={12.5} polarity="up-is-bad" />);
    expect(container.textContent).toContain("12.5%");
    const delta = container.querySelector(".metric__delta") as HTMLElement;
    expect(delta).toHaveAttribute("data-polarity", "bad");
    expect(delta).toHaveAttribute("data-direction", "up");
  });

  it("clamps only the progress bar width, not the number", () => {
    const { container } = render(
      <Progress fraction={2.5} label="Budget" detail="250%" />
    );
    const fill = container.querySelector(".progress__fill") as HTMLElement;
    expect(fill.style.width).toBe("100%");
    expect(screen.getByText("250%")).toBeInTheDocument();
  });
});

describe("EmptyState / Button / Tabs", () => {
  it("renders an action slot in the empty state", () => {
    render(
      <EmptyState
        title="Nothing"
        description="Create one"
        extra={<Button variant="primary">Create</Button>}
      />
    );
    expect(screen.getByText("Nothing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
  });

  it("applies button variants and sizes", () => {
    render(
      <Button variant="danger" size="M">
        Delete
      </Button>
    );
    const button = screen.getByRole("button", { name: "Delete" });
    expect(button).toHaveAttribute("data-variant", "danger");
    expect(button).toHaveAttribute("data-size", "M");
  });

  it("switches tabs", () => {
    const onSelect = vi.fn();
    render(
      <Tabs
        tabs={[
          { id: "a", label: "First" },
          { id: "b", label: "Second" },
        ]}
        selected="a"
        onSelect={onSelect}
      >
        <div>content</div>
      </Tabs>
    );
    fireEvent.click(screen.getByRole("tab", { name: "Second" }));
    expect(onSelect).toHaveBeenCalledWith("b");
    expect(screen.getByText("content")).toBeInTheDocument();
  });
});

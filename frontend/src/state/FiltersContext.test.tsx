import { describe, expect, it } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { FiltersProvider, useFilters } from "./FiltersContext";

function Probe() {
  const { filters, setFilters } = useFilters();
  const location = useLocation();
  return (
    <div>
      <span data-testid="days">{filters.days}</span>
      <span data-testid="workflow">{filters.workflow ?? "-"}</span>
      <span data-testid="project">{filters.project_id ?? "-"}</span>
      <span data-testid="q">{location.search}</span>
      <button onClick={() => setFilters({ days: 7, workflow: "wf" })}>set</button>
    </div>
  );
}

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <FiltersProvider>
        <Probe />
      </FiltersProvider>
    </MemoryRouter>
  );
}

describe("FiltersProvider", () => {
  it("reads filters from the URL", () => {
    renderAt("/engineering?days=14&project_id=p1&workflow=checkout");
    expect(screen.getByTestId("days")).toHaveTextContent("14");
    expect(screen.getByTestId("workflow")).toHaveTextContent("checkout");
    expect(screen.getByTestId("project")).toHaveTextContent("p1");
  });

  it("falls back to 30 days for missing/invalid values", () => {
    renderAt("/manager?days=bogus");
    expect(screen.getByTestId("days")).toHaveTextContent("30");
  });

  it("writes changes to the URL and preserves other params", () => {
    renderAt("/engineering?days=14&project_id=p1&q=refund&sort=duration_ms");
    fireEvent.click(screen.getByText("set"));
    const search = screen.getByTestId("q").textContent ?? "";
    expect(search).toContain("days=7");
    expect(search).toContain("workflow=wf");
    // Non-filter params survive (search/sort live in the same URL).
    expect(search).toContain("q=refund");
    expect(search).toContain("sort=duration_ms");
    expect(search).not.toContain("project_id");
  });

  it("drops default values from the URL", () => {
    renderAt("/overview?days=14");
    fireEvent.click(screen.getByText("set"));
    expect(screen.getByTestId("q").textContent).not.toContain("days=14");
  });
});

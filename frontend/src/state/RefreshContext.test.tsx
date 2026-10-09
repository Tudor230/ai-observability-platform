import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RefreshProvider, useRefresh, useRefetchInterval } from "./RefreshContext";

function Probe() {
  const { interval, setIntervalMs } = useRefresh();
  const refetch = useRefetchInterval();
  return (
    <div>
      <span data-testid="interval">{interval}</span>
      <span data-testid="refetch">{String(refetch)}</span>
      <button onClick={() => setIntervalMs(60_000)}>minute</button>
    </div>
  );
}

beforeEach(() => localStorage.clear());

describe("RefreshProvider", () => {
  it("defaults to off and reports false refetchInterval", () => {
    render(
      <RefreshProvider>
        <Probe />
      </RefreshProvider>
    );
    expect(screen.getByTestId("interval")).toHaveTextContent("0");
    expect(screen.getByTestId("refetch")).toHaveTextContent("false");
  });

  it("persists a cadence and exposes it to queries", () => {
    render(
      <RefreshProvider>
        <Probe />
      </RefreshProvider>
    );
    fireEvent.click(screen.getByText("minute"));
    expect(screen.getByTestId("interval")).toHaveTextContent("60000");
    expect(screen.getByTestId("refetch")).toHaveTextContent("60000");
    expect(localStorage.getItem("aiobs.refresh")).toBe("60000");
  });

  it("restores the stored cadence on mount", () => {
    localStorage.setItem("aiobs.refresh", "300000");
    render(
      <RefreshProvider>
        <Probe />
      </RefreshProvider>
    );
    expect(screen.getByTestId("interval")).toHaveTextContent("300000");
  });
});

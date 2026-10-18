import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { KindBadge, KindIcon, SeverityBadge, StatusBadge } from "./domain";

describe("domain badges", () => {
  it("tones execution status badges", () => {
    const { rerender } = render(<StatusBadge status="ok" />);
    expect(screen.getByText("ok")).toBeInTheDocument();
    rerender(<StatusBadge status="error" />);
    expect(screen.getByText("error")).toBeInTheDocument();
    rerender(<StatusBadge status="running" />);
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("tones severities and falls back for unknown values", () => {
    const { rerender } = render(<SeverityBadge severity="critical" />);
    expect(screen.getByText("critical")).toBeInTheDocument();
    rerender(<SeverityBadge severity="warning" />);
    expect(screen.getByText("warning")).toBeInTheDocument();
    rerender(<SeverityBadge severity="info" />);
    expect(screen.getByText("info")).toBeInTheDocument();
    rerender(<SeverityBadge severity="unknown" />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });

  it("renders every span-kind icon and badge", () => {
    const { container } = render(
      <div>
        <KindIcon kind="LLM" />
        <KindIcon kind="TOOL" size={20} />
        <KindIcon kind="RETRIEVER" />
        <KindIcon kind="AGENT" />
        <KindIcon kind="CHAIN" />
        <KindBadge kind="LLM" />
      </div>
    );
    expect(container.querySelectorAll("svg").length).toBeGreaterThanOrEqual(6);
    expect(screen.getByText("LLM")).toBeInTheDocument();
  });
});

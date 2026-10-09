import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ToastProvider, useToast } from "./Toast";

function Trigger() {
  const toast = useToast();
  return (
    <div>
      <button onClick={() => toast.success("Saved!")}>ok</button>
      <button onClick={() => toast.error("Boom")}>fail</button>
    </div>
  );
}

function renderToasts() {
  return render(
    <ToastProvider>
      <Trigger />
    </ToastProvider>
  );
}

describe("ToastProvider", () => {
  it("shows success and error toasts with status roles", () => {
    renderToasts();
    fireEvent.click(screen.getByText("ok"));
    fireEvent.click(screen.getByText("fail"));
    expect(screen.getByText("Saved!")).toBeInTheDocument();
    expect(screen.getByText("Boom")).toBeInTheDocument();
    expect(document.querySelectorAll('[role="status"]')).toHaveLength(2);
  });

  it("dismisses a toast", () => {
    renderToasts();
    fireEvent.click(screen.getByText("ok"));
    fireEvent.click(screen.getByLabelText("Dismiss notification"));
    expect(screen.queryByText("Saved!")).not.toBeInTheDocument();
  });

  it("auto-dismisses after 4 seconds", () => {
    vi.useFakeTimers();
    try {
      renderToasts();
      act(() => {
        fireEvent.click(screen.getByText("ok"));
      });
      expect(screen.getByText("Saved!")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(4000);
      });
      expect(screen.queryByText("Saved!")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

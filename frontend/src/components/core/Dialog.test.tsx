import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Dialog } from "./Dialog";

describe("Dialog", () => {
  it("renders with dialog semantics and a labelled title", () => {
    render(
      <Dialog open title="Delete key" onClose={() => {}}>
        <p>Body</p>
      </Dialog>
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Delete key");
    expect(screen.getByText("Body")).toBeInTheDocument();
  });

  it("moves initial focus inside the dialog", () => {
    render(
      <Dialog open title="Focus" onClose={() => {}}>
        <button type="button">First</button>
      </Dialog>
    );
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("closes on Escape and backdrop click", () => {
    const onClose = vi.fn();
    const { container } = render(
      <Dialog open title="Close me" onClose={onClose}>
        <button type="button">Inside</button>
      </Dialog>
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(container.querySelector(".modal-backdrop")!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("traps Tab between the first and last focusable elements", () => {
    render(
      <Dialog open title="Trap" onClose={() => {}}>
        <button type="button">First</button>
        <button type="button">Last</button>
      </Dialog>
    );
    const close = screen.getByLabelText("Close");
    const last = screen.getByText("Last");
    // Focus order is [Close, First, Last]; Tab wraps last → close.
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(close);
    close.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("renders nothing when closed", () => {
    render(
      <Dialog open={false} title="Hidden" onClose={() => {}}>
        <p>nope</p>
      </Dialog>
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

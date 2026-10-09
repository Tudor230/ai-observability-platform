import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { SortableTh, Table, TableEmpty, Td, Th, Tr } from "./Table";

describe("Table primitives", () => {
  it("renders headers, rows and cells", () => {
    render(
      <Table>
        <thead>
          <tr>
            <Th>Name</Th>
            <Th align="right">Cost</Th>
          </tr>
        </thead>
        <tbody>
          <Tr>
            <Td>checkout</Td>
            <Td align="right">$0.45</Td>
          </Tr>
        </tbody>
      </Table>
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "$0.45" })).toBeInTheDocument();
  });

  it("renders an empty state row spanning the table", () => {
    render(
      <Table>
        <TableEmpty colSpan={3}>Nothing here</TableEmpty>
      </Table>
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });

  describe("SortableTh", () => {
    it("exposes aria-sort and calls onSort with the key", () => {
      const onSort = vi.fn();
      render(
        <Table>
          <thead>
            <tr>
              <SortableTh sortKey="cost" active direction="desc" onSort={onSort}>
                Cost
              </SortableTh>
            </tr>
          </thead>
        </Table>
      );
      const header = screen.getByRole("columnheader", { name: /Cost/ });
      expect(header).toHaveAttribute("aria-sort", "descending");
      fireEvent.click(screen.getByRole("button", { name: /Cost/ }));
      expect(onSort).toHaveBeenCalledWith("cost");
    });

    it("reports aria-sort none when inactive", () => {
      render(
        <Table>
          <thead>
            <tr>
              <SortableTh sortKey="cost" active={false} direction="asc" onSort={() => {}}>
                Cost
              </SortableTh>
            </tr>
          </thead>
        </Table>
      );
      expect(screen.getByRole("columnheader", { name: /Cost/ })).toHaveAttribute(
        "aria-sort",
        "none"
      );
    });

    it("marks plain headers with scope=col", () => {
      render(
        <Table>
          <thead>
            <tr>
              <Th>Workflow</Th>
            </tr>
          </thead>
        </Table>
      );
      expect(screen.getByRole("columnheader", { name: "Workflow" })).toHaveAttribute(
        "scope",
        "col"
      );
    });
  });
});

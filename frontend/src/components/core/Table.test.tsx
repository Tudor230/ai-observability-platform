import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Table, TableEmpty, Td, Th, Tr } from "./Table";

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
});

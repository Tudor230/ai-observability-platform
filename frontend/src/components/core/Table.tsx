import type { ReactNode, ThHTMLAttributes, TdHTMLAttributes } from "react";

/** A scroll container so the header can stick. */
export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="table-wrap">{children}</div>;
}

export function Table({
  children,
  interactive = false,
}: {
  children: ReactNode;
  interactive?: boolean;
}) {
  return (
    <table className="table" data-interactive={interactive ? "true" : undefined}>
      {children}
    </table>
  );
}

export function Th({
  children,
  align,
  ...rest
}: { children?: ReactNode; align?: "left" | "right" } & ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th align={align} {...rest}>
      {children}
    </th>
  );
}

export function Td({
  children,
  align,
  ...rest
}: { children?: ReactNode; align?: "left" | "right" } & TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td align={align} {...rest}>
      {children}
    </td>
  );
}

export function Tr({
  children,
  status,
  ...rest
}: { children: ReactNode; status?: string } & React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr data-status={status} {...rest}>
      {children}
    </tr>
  );
}

export function TableEmpty({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tbody className="is-empty">
      <tr>
        <td className="table__empty" colSpan={colSpan}>
          {children}
        </td>
      </tr>
    </tbody>
  );
}

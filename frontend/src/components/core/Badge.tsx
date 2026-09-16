import type { ReactNode } from "react";

export type BadgeVariant =
  | "default"
  | "info"
  | "success"
  | "warning"
  | "danger"
  | "severe"
  | "kind";

export function Badge({
  children,
  variant = "default",
  size = "S",
  title,
}: {
  children: ReactNode;
  variant?: BadgeVariant;
  size?: "S" | "M" | "L";
  title?: string;
}) {
  return (
    <span className="badge" data-variant={variant} data-size={size} title={title}>
      {children}
    </span>
  );
}

import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "quiet" | "danger";
  size?: "S" | "M";
  iconOnly?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = "default",
  size = "S",
  iconOnly = false,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className="button"
      data-variant={variant}
      data-size={size}
      data-icon-only={iconOnly ? "true" : undefined}
      {...rest}
    >
      {children}
    </button>
  );
}

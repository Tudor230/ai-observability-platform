import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      {children}
    </label>
  );
}

export function TextInput({
  variant,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { variant?: "search" }) {
  return <input className="field__input" data-variant={variant} {...rest} />;
}

export function Select({
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select className="field__select" {...rest}>
      {children}
    </select>
  );
}

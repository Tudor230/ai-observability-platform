import type { ReactNode } from "react";
import { IconCheckCircle, IconInfo, IconAlertTriangle, IconXCircle, IconSparkle } from "./icons";

export type AlertVariant = "info" | "success" | "warning" | "danger";

function AlertIcon({ variant }: { variant: AlertVariant }) {
  switch (variant) {
    case "success":
      return <IconCheckCircle />;
    case "warning":
      return <IconAlertTriangle />;
    case "danger":
      return <IconXCircle />;
    default:
      return <IconInfo />;
  }
}

export function Alert({
  variant = "info",
  message,
  detail,
  extra,
}: {
  variant?: AlertVariant;
  message: ReactNode;
  detail?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <div className="alert" data-variant={variant} role="alert">
      <span className="alert__icon">
        <AlertIcon variant={variant} />
      </span>
      <div className="alert__body">
        <div className="alert__message">{message}</div>
        {detail ? <div className="alert__detail">{detail}</div> : null}
      </div>
      {extra ? <span className="spacer" /> : null}
      {extra}
    </div>
  );
}

/** Standard inline error for a failed query. */
export function QueryError({ what, error }: { what: string; error: unknown }) {
  const message = error instanceof Error ? error.message : error ? String(error) : "";
  return (
    <Alert
      variant="danger"
      message={`Failed to load ${what}.`}
      detail={message || undefined}
    />
  );
}

export function Skeleton({ shape = "text", width }: { shape?: "text" | "title" | "chart"; width?: number | string }) {
  return <div className="skeleton" data-shape={shape} style={width ? { width } : undefined} />;
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-state__graphic">
        <IconSparkle size={32} />
      </span>
      <div className="empty-state__title">{title}</div>
      {description ? <div className="empty-state__description">{description}</div> : null}
    </div>
  );
}

import { Badge, type BadgeVariant } from "./core";
import {
  IconBot,
  IconDatabase,
  IconLayers,
  IconSparkle,
  IconWrench,
} from "./core/icons";

/** Execution status → badge. */
export function StatusBadge({ status }: { status: string }) {
  const ok = status === "ok" || status === "success";
  const variant: BadgeVariant = ok ? "success" : status === "error" ? "danger" : "warning";
  return <Badge variant={variant}>{status}</Badge>;
}

const SEVERITY_VARIANTS: Record<string, BadgeVariant> = {
  critical: "danger",
  warning: "warning",
  info: "info",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge variant={SEVERITY_VARIANTS[severity] ?? "default"}>{severity}</Badge>;
}

/** OpenInference span kind → icon. */
export function KindIcon({ kind, size = 14 }: { kind: string; size?: number }) {
  switch (kind) {
    case "LLM":
      return <IconSparkle size={size} />;
    case "TOOL":
      return <IconWrench size={size} />;
    case "RETRIEVER":
      return <IconDatabase size={size} />;
    case "AGENT":
      return <IconBot size={size} />;
    default:
      return <IconLayers size={size} />;
  }
}

export function KindBadge({ kind }: { kind: string }) {
  return (
    <span className="badge" data-variant="kind" data-size="S" title={kind}>
      <KindIcon kind={kind} size={11} />
      {kind}
    </span>
  );
}

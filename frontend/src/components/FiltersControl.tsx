import { useEffect, useRef, useState } from "react";
import { useDirectoryProjects } from "../api/hooks";
import type { Filters } from "../api/types";
import { useFilters } from "../state/FiltersContext";
import { Button, Field, Select, TextInput } from "./core";
import { IconFilter, IconX } from "./core/icons";

export type FilterDimension = "days" | "project" | "client" | "workflow";

const DAY_OPTIONS = [1, 7, 14, 30, 90];

export const DAY_LABELS: Record<number, string> = {
  1: "Last 24 hours",
  7: "Last 7 days",
  14: "Last 14 days",
  30: "Last 30 days",
  90: "Last 90 days",
};

export const DEFAULT_DAYS = 30;

function activeCount(filters: Filters, dimensions: FilterDimension[]): number {
  let count = 0;
  if (dimensions.includes("days") && filters.days !== DEFAULT_DAYS) count += 1;
  if (dimensions.includes("project") && filters.project_id) count += 1;
  if (dimensions.includes("client") && filters.client_id) count += 1;
  if (dimensions.includes("workflow") && filters.workflow) count += 1;
  return count;
}

/**
 * Compact filters control (refinements v2): a button in the page header that
 * opens a small panel with only the filters relevant to the page. Active
 * filters render as removable chips via `FilterChips` under the header.
 */
export function FiltersControl({ dimensions }: { dimensions: FilterDimension[] }) {
  const { filters, setFilters } = useFilters();
  const projects = useDirectoryProjects();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  const count = activeCount(filters, dimensions);

  return (
    <div className="filters-control" ref={ref}>
      <Button
        variant="quiet"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        title="Filters"
      >
        <IconFilter size={14} />
        Filters{count ? ` (${count})` : ""}
      </Button>
      {open ? (
        <div className="filters-control__panel" role="dialog" aria-label="Filters">
          {dimensions.includes("days") ? (
            <Field label="Time range">
              <Select
                value={String(filters.days)}
                aria-label="Time range"
                onChange={(e) => setFilters({ ...filters, days: Number(e.target.value) })}
              >
                {DAY_OPTIONS.map((days) => (
                  <option key={days} value={days}>
                    {DAY_LABELS[days] ?? `Last ${days} days`}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}
          {dimensions.includes("project") ? (
            <Field label="Project">
              <Select
                value={filters.project_id ?? ""}
                aria-label="Project"
                onChange={(e) =>
                  setFilters({ ...filters, project_id: e.target.value || undefined })
                }
              >
                <option value="">All projects</option>
                {(projects.data?.items ?? []).map((project) => (
                  <option key={project.id} value={project.project_id}>
                    {project.name}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}
          {dimensions.includes("client") ? (
            <Field label="Client">
              <TextInput
                value={filters.client_id ?? ""}
                placeholder="client id"
                aria-label="Client"
                onChange={(e) =>
                  setFilters({ ...filters, client_id: e.target.value || undefined })
                }
              />
            </Field>
          ) : null}
          {dimensions.includes("workflow") ? (
            <Field label="Workflow">
              <TextInput
                value={filters.workflow ?? ""}
                placeholder="workflow name"
                aria-label="Workflow"
                onChange={(e) =>
                  setFilters({ ...filters, workflow: e.target.value || undefined })
                }
              />
            </Field>
          ) : null}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <Button
              variant="quiet"
              disabled={!count}
              onClick={() => setFilters({ days: DEFAULT_DAYS })}
            >
              Reset
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Removable chips for the filters active on this page. */
export function FilterChips({ dimensions }: { dimensions: FilterDimension[] }) {
  const { filters, setFilters } = useFilters();
  // Project chips show the human name; the raw id never renders (ADR-0012).
  const projects = useDirectoryProjects();
  const projectName = (id: string) =>
    (projects.data?.items ?? []).find((project) => project.project_id === id)?.name ?? id;
  const chips: { key: string; label: string; clear: () => void }[] = [];
  if (dimensions.includes("days") && filters.days !== DEFAULT_DAYS) {
    chips.push({
      key: "days",
      label: DAY_LABELS[filters.days] ?? `Last ${filters.days} days`,
      clear: () => setFilters({ ...filters, days: DEFAULT_DAYS }),
    });
  }
  if (dimensions.includes("project") && filters.project_id) {
    chips.push({
      key: "project",
      label: `Project: ${projectName(filters.project_id)}`,
      clear: () => setFilters({ ...filters, project_id: undefined }),
    });
  }
  if (dimensions.includes("client") && filters.client_id) {
    chips.push({
      key: "client",
      label: `Client: ${filters.client_id}`,
      clear: () => setFilters({ ...filters, client_id: undefined }),
    });
  }
  if (dimensions.includes("workflow") && filters.workflow) {
    chips.push({
      key: "workflow",
      label: `Workflow: ${filters.workflow}`,
      clear: () => setFilters({ ...filters, workflow: undefined }),
    });
  }
  if (!chips.length) return null;
  return (
    <div className="filter-chips" role="group" aria-label="Active filters">
      {chips.map((chip) => (
        <span key={chip.key} className="filter-chip">
          {chip.label}
          <button
            type="button"
            aria-label={`Remove ${chip.label}`}
            onClick={chip.clear}
          >
            <IconX size={12} />
          </button>
        </span>
      ))}
      <Button variant="quiet" onClick={() => setFilters({ days: DEFAULT_DAYS })}>
        Clear all
      </Button>
    </div>
  );
}

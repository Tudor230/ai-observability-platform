import { useEffect, useRef, useState } from "react";
import { useDirectoryProjects } from "../api/hooks";
import { Button, Field, SearchableSelect, TextInput } from "./core";
import { IconFilter, IconX } from "./core/icons";
import {
  TABLE_FILTER_FIELDS,
  useTableFilters,
  type TableFilterField,
} from "../state/useTableFilters";

/**
 * Per-table filter control (refinements v3): a compact button for the card
 * header plus removable chips for the card body. State is namespaced per card
 * in the URL, so two cards on one page filter independently.
 */
export function TableFilters({
  card,
  title,
  fields = [...TABLE_FILTER_FIELDS],
}: {
  card: string;
  title: string;
  /** Which fields this card's endpoint actually supports (default: all). */
  fields?: TableFilterField[];
}) {
  const { filters, setFilter, clear, activeCount } = useTableFilters(card);
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

  return (
    <div className="filters-control" ref={ref}>
      <Button
        variant="quiet"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        title={`${title} filters`}
      >
        <IconFilter size={14} />
        Filters{activeCount ? ` (${activeCount})` : ""}
      </Button>
      {open ? (
        <div
          className="filters-control__panel"
          role="dialog"
          aria-label={`${title} filters`}
        >
          {fields.includes("project_id") ? (
            <Field label="Project">
              <SearchableSelect
                value={filters.project_id ?? ""}
                onChange={(value) => setFilter("project_id", value || undefined)}
                options={(projects.data?.items ?? []).map((project) => ({
                  value: project.project_id,
                  label: project.name,
                }))}
                placeholder="All projects"
                aria-label="Project"
              />
            </Field>
          ) : null}
          {fields.includes("workflow") ? (
            <Field label="Workflow">
              <TextInput
                value={filters.workflow ?? ""}
                placeholder="workflow name"
                aria-label="Workflow"
                onChange={(e) => setFilter("workflow", e.target.value || undefined)}
              />
            </Field>
          ) : null}
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <Button variant="quiet" disabled={!activeCount} onClick={clear}>
              Reset
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Removable chips for one card's active filters (rendered in the card body). */
export function TableFilterChips({ card }: { card: string }) {
  const { filters, setFilter, clear, activeCount } = useTableFilters(card);
  const projects = useDirectoryProjects();
  const projectName = (id: string) =>
    (projects.data?.items ?? []).find((project) => project.project_id === id)?.name ?? id;
  if (!activeCount) return null;

  return (
    <div className="filter-chips" role="group" aria-label="Active table filters">
      {filters.project_id ? (
        <span className="filter-chip">
          {`Project: ${projectName(filters.project_id)}`}
          <button
            type="button"
            aria-label={`Remove Project: ${projectName(filters.project_id)}`}
            onClick={() => setFilter("project_id", undefined)}
          >
            <IconX size={12} />
          </button>
        </span>
      ) : null}
      {filters.workflow ? (
        <span className="filter-chip">
          {`Workflow: ${filters.workflow}`}
          <button
            type="button"
            aria-label={`Remove Workflow: ${filters.workflow}`}
            onClick={() => setFilter("workflow", undefined)}
          >
            <IconX size={12} />
          </button>
        </span>
      ) : null}
      {TABLE_FILTER_FIELDS.length > 1 ? (
        <Button variant="quiet" onClick={clear}>
          Clear all
        </Button>
      ) : null}
    </div>
  );
}

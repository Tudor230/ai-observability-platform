import { Button, Field, Select, TextInput } from "./core";
import { IconFilter, IconX } from "./core/icons";
import { useFilters } from "../state/FiltersContext";

const DAY_OPTIONS = [1, 7, 14, 30, 90];

/** The global filter toolbar — days and attribution dimensions. */
export function FilterToolbar() {
  const { filters, setFilters } = useFilters();
  const isFiltered = Boolean(filters.project_id || filters.client_id || filters.workflow);

  return (
    <div className="toolbar" role="search" aria-label="Filters">
      <Field label="Time range">
        <Select
          value={filters.days}
          onChange={(e) => setFilters({ ...filters, days: Number(e.target.value) })}
          aria-label="Time range in days"
        >
          {DAY_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {d === 1 ? "Last 24 hours" : `Last ${d} days`}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Project">
        <TextInput
          value={filters.project_id ?? ""}
          placeholder="project id"
          onChange={(e) => setFilters({ ...filters, project_id: e.target.value || undefined })}
        />
      </Field>
      <Field label="Client">
        <TextInput
          value={filters.client_id ?? ""}
          placeholder="client id"
          onChange={(e) => setFilters({ ...filters, client_id: e.target.value || undefined })}
        />
      </Field>
      <Field label="Workflow">
        <TextInput
          value={filters.workflow ?? ""}
          placeholder="workflow"
          onChange={(e) => setFilters({ ...filters, workflow: e.target.value || undefined })}
        />
      </Field>
      <span className="toolbar__spacer" />
      <span className="row muted" style={{ marginBottom: 3 }}>
        <IconFilter size={14} />
        {filters.days === 1 ? "24h" : `${filters.days}d`}
      </span>
      {isFiltered ? (
        <Button
          variant="quiet"
          onClick={() => setFilters({ days: filters.days })}
          style={{ marginBottom: 1 }}
        >
          <IconX size={14} />
          Clear
        </Button>
      ) : null}
    </div>
  );
}

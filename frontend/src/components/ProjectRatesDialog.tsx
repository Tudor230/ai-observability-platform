import { useState } from "react";
import { useProjectRates } from "../api/hooks";
import { Dialog, Field, SearchableSelect, Button } from "./core";
import { ProjectRateEditor } from "./ProjectRateEditor";

/**
 * Cross-project rate book (ADR-0013): the Executive page's entry point for
 * maintaining every project's rate. The per-project editor itself lives in
 * `ProjectRateEditor`, which the project page embeds as well.
 */
export function ProjectRatesDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const rates = useProjectRates(open);
  const [projectId, setProjectId] = useState("");

  const entries = rates.data?.items ?? [];
  const entry = entries.find((item) => item.project_id === projectId) ?? entries[0] ?? null;

  return (
    <Dialog
      open={open}
      title="Project rates"
      onClose={onClose}
      footer={
        <Button variant="quiet" onClick={onClose}>
          Close
        </Button>
      }
    >
      <p className="muted" style={{ marginTop: 0 }}>
        What each project pays, and what it costs to serve. Rates are versions: a
        newer one starts a new price from its date and never rewrites history.
      </p>

      {rates.isLoading ? (
        <p className="muted">Loading projects…</p>
      ) : !entries.length ? (
        <p className="muted">No projects yet — create one first.</p>
      ) : (
        <>
          <Field label="Project">
            <SearchableSelect
              value={entry?.project_id ?? ""}
              onChange={(value) => setProjectId(value)}
              options={entries.map((item) => ({
                value: item.project_id,
                label: item.project_name,
              }))}
              placeholder="Select a project"
              aria-label="Project"
            />
          </Field>
          {entry ? <ProjectRateEditor key={entry.project_id} entry={entry} /> : null}
        </>
      )}
    </Dialog>
  );
}

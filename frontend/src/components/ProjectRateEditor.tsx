import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ProjectRateVersion, ProjectRatesEntry } from "../api/types";
import { Button, Field, Select, TextInput, useToast } from "./core";

/**
 * One project's rate book (ADR-0013): what the project pays and what it costs
 * to serve, entered as *versions*. A version applies from its `effective_from`;
 * a newer version starts a new price instead of overwriting the old one, and
 * two versions may not share a date (the `409` lands inline). Internal projects
 * need no revenue and are flagged here.
 *
 * Extracted so the Executive page (cross-project dialog) and the project page
 * (single project) share one implementation.
 */

interface DraftState {
  effective_from: string;
  revenue_amount: string;
  revenue_period: "month" | "year";
  manual_cost_amount: string;
  manual_cost_period: "month" | "year";
}

function emptyDraft(): DraftState {
  return {
    effective_from: new Date().toISOString().slice(0, 10),
    revenue_amount: "",
    revenue_period: "month",
    manual_cost_amount: "",
    manual_cost_period: "month",
  };
}

function draftFrom(version: ProjectRateVersion): DraftState {
  return {
    effective_from: version.effective_from,
    revenue_amount: String(version.revenue_amount),
    revenue_period: version.revenue_period,
    manual_cost_amount: version.manual_cost_amount ? String(version.manual_cost_amount) : "",
    manual_cost_period: version.manual_cost_period,
  };
}

/** `409` is the duplicate-version clash; checked by shape so a mocked client works. */
function isConflict(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { status?: number }).status === 409
  );
}

export function ProjectRateEditor({ entry }: { entry: ProjectRatesEntry }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState>(emptyDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["project-rates"] });
    void queryClient.invalidateQueries({ queryKey: ["margin"] });
  };

  const startEdit = (version: ProjectRateVersion) => {
    setEditingId(version.id);
    setDraft(draftFrom(version));
    setError(null);
  };

  const resetForm = () => {
    setEditingId(null);
    setDraft(emptyDraft());
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      effective_from: draft.effective_from,
      revenue_amount: Number(draft.revenue_amount || 0),
      revenue_period: draft.revenue_period,
      manual_cost_amount: Number(draft.manual_cost_amount || 0),
      manual_cost_period: draft.manual_cost_period,
    };
    try {
      if (editingId) {
        await api.projectRates.update(editingId, body);
        toast.success("Rate version updated.");
      } else {
        await api.projectRates.create({ project_id: entry.project_id, ...body });
        toast.success("Rate version added.");
      }
      resetForm();
      refresh();
    } catch (err) {
      setError(
        isConflict(err)
          ? "A rate version already starts on that date."
          : err instanceof Error
            ? err.message
            : "Failed to save the rate."
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async (version: ProjectRateVersion) => {
    setBusy(true);
    setError(null);
    try {
      await api.projectRates.remove(version.id);
      toast.success("Rate version deleted.");
      if (editingId === version.id) resetForm();
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete the rate.");
    } finally {
      setBusy(false);
    }
  };

  const toggleInternal = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.projectRates.setInternal(entry.project_id, !entry.internal);
      toast.success(
        entry.internal
          ? "Project is client-facing again."
          : "Project marked internal — no revenue expected."
      );
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update the project.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack" style={{ padding: "var(--global-dimension-size-100)" }}>
      <div className="row" style={{ justifyContent: "space-between", gap: 12 }}>
        <span className="muted">
          {entry.internal
            ? "Internal project — no revenue expected"
            : entry.versions.length
              ? `${entry.versions.length} rate version${entry.versions.length === 1 ? "" : "s"}`
              : "No rate yet — margin shows “no rate”"}
        </span>
        <Button variant="quiet" disabled={busy} onClick={() => void toggleInternal()}>
          {entry.internal ? "Make client-facing" : "Mark internal"}
        </Button>
      </div>

      {entry.versions.length ? (
        <div className="stack" style={{ gap: 6 }}>
          {entry.versions.map((version) => (
            <div
              key={version.id}
              className="row"
              style={{ justifyContent: "space-between", gap: 12 }}
            >
              <span>
                <strong>{version.effective_from}</strong>
                <span className="muted">
                  {" · "}
                  {version.revenue_amount.toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                  })}{" "}
                  /{version.revenue_period}
                  {version.manual_cost_amount
                    ? ` · manual ${version.manual_cost_amount.toLocaleString("en-US", {
                        minimumFractionDigits: 2,
                      })} /${version.manual_cost_period}`
                    : " · no manual cost"}
                </span>
              </span>
              <span className="row" style={{ gap: 8 }}>
                <Button variant="quiet" onClick={() => startEdit(version)}>
                  Edit
                </Button>
                <Button variant="quiet" disabled={busy} onClick={() => void remove(version)}>
                  Delete
                </Button>
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <form className="stack" onSubmit={(event) => void submit(event)}>
        <Field label={editingId ? "Edit version" : "Add a version"}>
          <div className="grid grid-2" style={{ gap: 12 }}>
            <TextInput
              type="date"
              value={draft.effective_from}
              aria-label="Effective from"
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, effective_from: e.target.value }))
              }
            />
            <div className="row" style={{ gap: 8 }}>
              <TextInput
                inputMode="decimal"
                placeholder="Revenue"
                aria-label="Revenue amount"
                value={draft.revenue_amount}
                onChange={(e) =>
                  setDraft((prev) => ({ ...prev, revenue_amount: e.target.value }))
                }
              />
              <Select
                value={draft.revenue_period}
                aria-label="Revenue period"
                onChange={(e) =>
                  setDraft((prev) => ({
                    ...prev,
                    revenue_period: e.target.value as "month" | "year",
                  }))
                }
              >
                <option value="month">/ month</option>
                <option value="year">/ year</option>
              </Select>
            </div>
            <TextInput
              inputMode="decimal"
              placeholder="Manual cost (optional)"
              aria-label="Manual cost amount"
              value={draft.manual_cost_amount}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, manual_cost_amount: e.target.value }))
              }
            />
            <Select
              value={draft.manual_cost_period}
              aria-label="Manual cost period"
              onChange={(e) =>
                setDraft((prev) => ({
                  ...prev,
                  manual_cost_period: e.target.value as "month" | "year",
                }))
              }
            >
              <option value="month">/ month</option>
              <option value="year">/ year</option>
            </Select>
          </div>
        </Field>
        {error ? <p className="text-danger">{error}</p> : null}
        <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
          {editingId ? (
            <Button variant="quiet" type="button" onClick={resetForm}>
              Cancel
            </Button>
          ) : null}
          <Button variant="primary" type="submit" disabled={busy}>
            {editingId ? "Save version" : "Add version"}
          </Button>
        </div>
      </form>
    </div>
  );
}

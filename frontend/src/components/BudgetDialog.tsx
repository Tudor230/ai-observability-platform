import { useState } from "react";
import { api } from "../api/client";
import { useDepartments, useDirectoryProjects, useTeams } from "../api/hooks";
import type { BudgetInput, BudgetStatus } from "../api/types";
import {
  Alert,
  Button,
  Dialog,
  Field,
  SearchableSelect,
  Select,
  TextInput,
  useToast,
} from "./core";

const today = () => new Date().toISOString().slice(0, 10);

function scopeLabel(budget: BudgetStatus | null): string {
  if (!budget) return "global";
  return budget.scope || "global";
}

/**
 * Create/edit dialog for budgets (audit item 5). Managers must pick one of
 * department/team/project; exec/admin may check "Global budget" (no scope).
 * Mount it with a `key` per budget so state starts fresh.
 */
export function BudgetDialog({
  open,
  budget,
  canCreateGlobal,
  onClose,
  onSaved,
}: {
  open: boolean;
  budget: BudgetStatus | null;
  canCreateGlobal: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const departments = useDepartments();
  const [department, setDepartment] = useState(budget?.department ?? "");
  const [team, setTeam] = useState(budget?.team ?? "");
  const teams = useTeams(department || undefined);
  const projects = useDirectoryProjects();
  const [project, setProject] = useState(budget?.project ?? "");
  const [name, setName] = useState(budget?.name ?? "");
  const [amount, setAmount] = useState(budget ? String(budget.amount) : "");
  const [periodType, setPeriodType] = useState(budget?.period_type ?? "month");
  const [period, setPeriod] = useState(budget?.period?.slice(0, 10) ?? today());
  const [client, setClient] = useState(budget?.client ?? "");
  const [workflow, setWorkflow] = useState(budget?.workflow_name ?? "");
  const [globalScope, setGlobalScope] = useState(
    canCreateGlobal && (budget === null || budget.scope === "global")
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const departmentOptions = (departments.data?.items ?? []).map((d) => ({
    value: d.id,
    label: d.name,
  }));
  const teamOptions = (teams.data?.items ?? []).map((t) => ({
    value: t.id,
    label: `${t.name} (${t.department_name})`,
  }));
  const projectOptions = (projects.data?.items ?? [])
    .filter((p) => !team || p.team_id === team)
    .map((p) => ({ value: p.project_id, label: `${p.project_id} · ${p.name}` }));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const numeric = Number(amount);
      if (!Number.isFinite(numeric) || numeric <= 0) {
        throw new Error("Amount must be a positive number.");
      }
      const payload: BudgetInput = {
        name: name.trim() || null,
        amount: numeric,
        period,
        period_type: periodType,
        department: globalScope ? null : department || null,
        team: globalScope ? null : team || null,
        project: globalScope ? null : project || null,
        client: client.trim() || null,
        workflow_name: workflow.trim() || null,
      };
      if (budget) await api.budgets.update(budget.id, payload);
      else await api.budgets.create(payload);
      toast.success(budget ? "Budget updated." : "Budget created.");
      onSaved();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save the budget.";
      setError(message);
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      title={budget ? `Edit budget — ${scopeLabel(budget)}` : "New budget"}
      onClose={onClose}
      footer={
        <>
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            {budget ? "Save changes" : "Create budget"}
          </Button>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <div className="stack">
        {error ? <Alert variant="danger" message={error} /> : null}
        <Field label="Name">
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Team A monthly cap"
          />
        </Field>
        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Amount (USD)">
            <TextInput
              value={amount}
              inputMode="decimal"
              onChange={(e) => setAmount(e.target.value)}
              placeholder="100"
            />
          </Field>
          <Field label="Period">
            <Select
              value={periodType}
              onChange={(e) => setPeriodType(e.target.value)}
              aria-label="Budget period type"
            >
              <option value="day">Day</option>
              <option value="week">Week</option>
              <option value="month">Month</option>
            </Select>
          </Field>
          <Field label="Anchor date">
            <TextInput
              type="date"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              aria-label="Budget anchor date"
            />
          </Field>
        </div>

        {canCreateGlobal ? (
          <label className="row" style={{ gap: 8 }}>
            <input
              type="checkbox"
              checked={globalScope}
              onChange={(e) => setGlobalScope(e.target.checked)}
            />
            <span>
              Global budget (no department/team/project scope — exec/admin only)
            </span>
          </label>
        ) : null}

        {!globalScope ? (
          <>
            <Field label="Department (optional)">
              <SearchableSelect
                value={department}
                onChange={(value) => {
                  setDepartment(value);
                  setTeam("");
                  setProject("");
                }}
                options={departmentOptions}
                placeholder="Select a department…"
                aria-label="Budget department"
              />
            </Field>
            <Field label="Team (optional)">
              <SearchableSelect
                value={team}
                onChange={(value) => {
                  setTeam(value);
                  setProject("");
                }}
                options={teamOptions}
                placeholder={department ? "Select a team…" : "Select a department first…"}
                disabled={!department}
                aria-label="Budget team"
              />
            </Field>
            <Field label="Project (optional)">
              <SearchableSelect
                value={project}
                onChange={setProject}
                options={projectOptions}
                placeholder="Select a project…"
                aria-label="Budget project"
              />
            </Field>
            <p className="muted" style={{ margin: 0 }}>
              A manager must set at least one of department, team or project.
            </p>
          </>
        ) : null}

        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Client filter (optional)">
            <TextInput
              value={client}
              onChange={(e) => setClient(e.target.value)}
              placeholder="client id"
            />
          </Field>
          <Field label="Workflow filter (optional)">
            <TextInput
              value={workflow}
              onChange={(e) => setWorkflow(e.target.value)}
              placeholder="workflow name"
            />
          </Field>
        </div>
      </div>
    </Dialog>
  );
}

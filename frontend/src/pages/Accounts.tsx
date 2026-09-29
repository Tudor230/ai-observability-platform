import { useMemo, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  useDepartments,
  useDirectoryProjects,
  useTeams,
  useUsers,
} from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import {
  Alert,
  Badge,
  Button,
  CardPanel,
  Dialog,
  EmptyState,
  Field,
  QueryError,
  SearchableSelect,
  Select,
  Skeleton,
  Table,
  TableEmpty,
  TableWrap,
  Td,
  TextInput,
  Th,
  Tr,
} from "../components/core";
import { IconCopy, IconKey } from "../components/core/icons";
import type { Role, UserAccount } from "../api/types";

const ROLES: Role[] = ["admin", "exec", "manager", "engineer", "client"];
const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  exec: "Executive",
  manager: "Manager",
  engineer: "Engineer",
  client: "Client",
};

export default function Accounts() {
  const queryClient = useQueryClient();
  const users = useUsers();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<{ email: string; password: string } | null>(
    null
  );
  const [managingId, setManagingId] = useState<string | null>(null);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["users"] });

  const selectedUser = useMemo(
    () => users.data?.items.find((item) => item.id === managingId) ?? null,
    [users.data, managingId]
  );

  const createAccount = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.users.create(email.trim(), password || undefined);
      setRevealed({ email: created.email, password: created.password });
      setEmail("");
      setPassword("");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create the account.");
    } finally {
      setBusy(false);
    }
  };

  const resetPassword = async (user: UserAccount) => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.users.resetPassword(user.id);
      setRevealed({ email: result.email, password: result.password });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset the password.");
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (user: UserAccount) => {
    setBusy(true);
    setError(null);
    try {
      if (user.enabled) await api.users.disable(user.id);
      else await api.users.enable(user.id);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update the account.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title="Accounts"
        subTitle="Provision logins and manage each user's memberships directly."
      />

      {error ? <Alert variant="danger" message={error} /> : null}

      {revealed ? (
        <Alert
          variant="warning"
          message={
            <>
              <IconKey size={14} /> Password for {revealed.email} — copy it now, it will
              not be shown again.
            </>
          }
          detail={<code className="inline-code">{revealed.password}</code>}
          extra={
            <>
              <Button
                variant="quiet"
                onClick={() => void navigator.clipboard.writeText(revealed.password)}
              >
                <IconCopy size={14} />
                Copy
              </Button>
              <Button variant="quiet" onClick={() => setRevealed(null)}>
                Dismiss
              </Button>
            </>
          }
        />
      ) : null}

      <CardPanel title="Add account" subTitle="The password is shown once after creation">
        <form className="request-form" onSubmit={createAccount}>
          <Field label="Email">
            <TextInput
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
              required
            />
          </Field>
          <Field label="Password (optional — generated when empty)">
            <TextInput
              type="text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="leave empty to auto-generate"
              autoComplete="new-password"
            />
          </Field>
          <div className="row">
            <Button variant="primary" type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create account"}
            </Button>
          </div>
        </form>
      </CardPanel>

      <CardPanel
        title="Users"
        subTitle={users.data ? `${users.data.total} accounts` : undefined}
      >
        {users.isError ? (
          <div style={{ padding: 16 }}>
            <QueryError what="users" error={users.error} />
          </div>
        ) : users.isLoading ? (
          <div className="stack" style={{ padding: 16 }}>
            <Skeleton width="70%" />
            <Skeleton width="50%" />
          </div>
        ) : users.data?.items.length ? (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Email</Th>
                  <Th>Roles</Th>
                  <Th>Memberships</Th>
                  <Th>Status</Th>
                  <Th align="right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {users.data.items.map((user) => (
                  <Tr key={user.id}>
                    <Td className="table__cell--primary">{user.email}</Td>
                    <Td>
                      {user.roles.length ? (
                        <span className="row row--wrap" style={{ gap: 4 }}>
                          {user.roles.map((role) => (
                            <Badge key={role} variant="info">
                              {ROLE_LABELS[role]}
                            </Badge>
                          ))}
                        </span>
                      ) : (
                        <span className="muted">none</span>
                      )}
                    </Td>
                    <Td className="muted">
                      {user.memberships
                        .map(
                          (m) =>
                            `${ROLE_LABELS[m.role]}${
                              m.scope_name ? ` · ${m.scope_name}` : ""
                            }`
                        )
                        .join(", ") || "—"}
                    </Td>
                    <Td>
                      <Badge variant={user.enabled ? "success" : "default"}>
                        {user.enabled ? "enabled" : "disabled"}
                      </Badge>
                    </Td>
                    <Td align="right">
                      <span className="row" style={{ justifyContent: "flex-end" }}>
                        <Button
                          variant="quiet"
                          disabled={busy}
                          onClick={() => setManagingId(user.id)}
                        >
                          Memberships
                        </Button>
                        <Button
                          variant="quiet"
                          disabled={busy}
                          onClick={() => void resetPassword(user)}
                        >
                          Reset password
                        </Button>
                        <Button
                          variant={user.enabled ? "danger" : "default"}
                          disabled={busy}
                          onClick={() => void toggle(user)}
                        >
                          {user.enabled ? "Disable" : "Enable"}
                        </Button>
                      </span>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <TableEmpty colSpan={5}>No accounts yet.</TableEmpty>
        )}
      </CardPanel>

      <MembershipDialog
        user={selectedUser}
        onClose={() => setManagingId(null)}
        onChanged={refresh}
      />
    </div>
  );
}

function MembershipDialog({
  user,
  onClose,
  onChanged,
}: {
  user: UserAccount | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const departments = useDepartments();
  const teams = useTeams();
  const projects = useDirectoryProjects();
  const [role, setRole] = useState<Role>("engineer");
  const [scopeKey, setScopeKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scopeOptions = useMemo(() => {
    if (role === "admin" || role === "exec") {
      return [{ value: "global:", label: "Global" }];
    }
    if (role === "manager") {
      return [
        ...(departments.data?.items ?? []).map((d) => ({
          value: `department:${d.id}`,
          label: `Department — ${d.name}`,
        })),
        ...(teams.data?.items ?? []).map((t) => ({
          value: `team:${t.id}`,
          label: `Team — ${t.name} (${t.department_name})`,
        })),
      ];
    }
    if (role === "client") {
      return (projects.data?.items ?? []).map((p) => ({
        value: `project:${p.id}`,
        label: `Project — ${p.project_id} · ${p.name}`,
      }));
    }
    return (teams.data?.items ?? []).map((t) => ({
      value: `team:${t.id}`,
      label: `Team — ${t.name} (${t.department_name})`,
    }));
  }, [role, departments.data, teams.data, projects.data]);

  const grant = async () => {
    if (!user || !scopeKey) return;
    const [scopeType, scopeId] = scopeKey.split(":");
    setBusy(true);
    setError(null);
    try {
      await api.users.grantMembership(
        user.id,
        role,
        scopeType as "global" | "department" | "team" | "project",
        scopeType === "global" ? null : scopeId
      );
      setScopeKey("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to grant the membership.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (membershipId: string) => {
    if (!user) return;
    setBusy(true);
    setError(null);
    try {
      await api.users.revokeMembership(user.id, membershipId);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke the membership.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={user !== null}
      title={user ? `Memberships — ${user.email}` : "Memberships"}
      onClose={onClose}
      footer={
        <>
          <Button variant="primary" disabled={busy || !scopeKey} onClick={() => void grant()}>
            Grant membership
          </Button>
          <Button variant="quiet" onClick={onClose}>
            Close
          </Button>
        </>
      }
    >
      {error ? <Alert variant="danger" message={error} /> : null}
      {user?.memberships.length ? (
        <div className="stack">
          {user.memberships.map((membership) => (
            <div className="list-row" key={membership.id}>
              <Badge variant="info">{ROLE_LABELS[membership.role]}</Badge>
              <div className="list-row__main">
                <span>{membership.scope_name ?? membership.scope_id ?? "Global"}</span>
                <span className="muted" style={{ fontSize: 12 }}>
                  {membership.scope_type}
                </span>
              </div>
              <span className="spacer" />
              <Button
                variant="danger"
                disabled={busy}
                onClick={() => void revoke(membership.id)}
              >
                Revoke
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          title="No memberships"
          description="Grant a role and scope to give this account access."
        />
      )}
      <Field label="Role">
        <Select
          value={role}
          onChange={(e) => {
            setRole(e.target.value as Role);
            setScopeKey("");
          }}
        >
          {ROLES.map((option) => (
            <option key={option} value={option}>
              {ROLE_LABELS[option]}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Scope">
        <SearchableSelect
          value={scopeKey}
          onChange={setScopeKey}
          options={scopeOptions}
          placeholder="Select a scope…"
          aria-label="Membership scope"
        />
      </Field>
    </Dialog>
  );
}

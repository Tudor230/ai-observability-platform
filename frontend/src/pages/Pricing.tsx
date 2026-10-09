import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { usePricing } from "../api/hooks";
import type { PricingInput } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { RefreshButton } from "../components/RefreshButton";
import {
  Alert,
  Badge,
  Button,
  CardPanel,
  Dialog,
  EmptyState,
  Field,
  QueryError,
  Select,
  Skeleton,
  SortableTh,
  Table,
  TableWrap,
  Td,
  TextInput,
  Th,
  Tr,
} from "../components/core";
import { formatMoney } from "../lib/format";

type SortKey = "provider" | "model" | "effective_from";

function localNow(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

export default function PricingPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("provider");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<{ id: string; label: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const pricing = usePricing({ q: q || undefined, sort, order });
  const items = pricing.data?.items ?? [];

  const toggleSort = (key: string) => {
    const next = key as SortKey;
    if (next === sort) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(next);
      setOrder(next === "effective_from" ? "desc" : "asc");
    }
  };

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["pricing"] });

  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    setError(null);
    try {
      await api.pricing.remove(deleting.id);
      setDeleting(null);
      refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message.includes("409")
            ? "This price is referenced by cost records — add a newer effective-dated price instead of deleting history."
            : err.message
          : "Failed to delete the price."
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        title="Pricing"
        subTitle="Model rates used by the cost engine; history is immutable (corrections are new effective-dated rows)."
        extra={
          <>
            <TextInput
              variant="search"
              value={search}
              aria-label="Search pricing"
              placeholder="Search provider or model…"
              onChange={(e) => setSearch(e.target.value)}
            />
            <Button variant="primary" onClick={() => setAdding(true)}>
              Add price
            </Button>
            <RefreshButton />
          </>
        }
      />

      {error ? <Alert variant="danger" message={error} /> : null}
      {pricing.isError ? <QueryError what="pricing" error={pricing.error} /> : null}

      <CardPanel
        title="Model pricing"
        subTitle={pricing.data ? `${pricing.data.total} rows` : undefined}
      >
        {pricing.isLoading ? (
          <div className="stack" style={{ padding: 16 }}>
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} shape="text" width="100%" />
            ))}
          </div>
        ) : items.length ? (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <SortableTh
                    sortKey="provider"
                    active={sort === "provider"}
                    direction={order}
                    onSort={toggleSort}
                  >
                    Provider
                  </SortableTh>
                  <SortableTh
                    sortKey="model"
                    active={sort === "model"}
                    direction={order}
                    onSort={toggleSort}
                  >
                    Model
                  </SortableTh>
                  <Th>Match</Th>
                  <Th align="right">Input /1M</Th>
                  <Th align="right">Output /1M</Th>
                  <Th align="right">Cache read</Th>
                  <Th align="right">Cache write</Th>
                  <Th align="right">Reasoning</Th>
                  <SortableTh
                    sortKey="effective_from"
                    active={sort === "effective_from"}
                    direction={order}
                    onSort={toggleSort}
                  >
                    Effective from
                  </SortableTh>
                  <Th align="right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <Tr key={p.id}>
                    <Td className="table__cell--primary">{p.provider}</Td>
                    <Td>{p.model}</Td>
                    <Td>
                      <Badge variant={p.model_match === "default" ? "warning" : "default"}>
                        {p.model_match}
                      </Badge>
                    </Td>
                    <Td align="right" className="num">{formatMoney(p.input_price_per_1m)}</Td>
                    <Td align="right" className="num">{formatMoney(p.output_price_per_1m)}</Td>
                    <Td align="right" className="num">
                      {p.cache_read_price_per_1m === null ? "—" : formatMoney(p.cache_read_price_per_1m)}
                    </Td>
                    <Td align="right" className="num">
                      {p.cache_write_price_per_1m === null ? "—" : formatMoney(p.cache_write_price_per_1m)}
                    </Td>
                    <Td align="right" className="num">
                      {p.reasoning_price_per_1m === null ? "—" : formatMoney(p.reasoning_price_per_1m)}
                    </Td>
                    <Td className="muted num">
                      {p.effective_from ? new Date(p.effective_from).toLocaleString() : "—"}
                    </Td>
                    <Td align="right">
                      <Button
                        variant="danger"
                        onClick={() => setDeleting({ id: p.id, label: `${p.provider} · ${p.model}` })}
                      >
                        Delete
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        ) : (
          <EmptyState
            title={q ? "No prices match the search" : "No prices configured"}
            description="Unpriced models surface without a cost in dashboards until a matching price is added."
            extra={
              <Button variant="primary" onClick={() => setAdding(true)}>
                Add the first price
              </Button>
            }
          />
        )}
      </CardPanel>

      {adding ? (
        <AddPricingDialog
          onClose={() => setAdding(false)}
          onSaved={() => {
            refresh();
            setAdding(false);
          }}
        />
      ) : null}

      <Dialog
        open={deleting !== null}
        title="Delete price"
        onClose={() => setDeleting(null)}
        footer={
          <>
            <Button variant="danger" disabled={busy} onClick={() => void remove()}>
              Delete price
            </Button>
            <Button variant="quiet" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
          </>
        }
      >
        <p className="muted">
          {deleting?.label} will no longer price new calls. Rows referenced by
          cost records cannot be deleted (add a newer effective-dated price
          instead).
        </p>
      </Dialog>
    </div>
  );
}

function AddPricingDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [match, setMatch] = useState<"exact" | "prefix" | "default">("exact");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [cacheRead, setCacheRead] = useState("");
  const [cacheWrite, setCacheWrite] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(localNow());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!provider.trim() || !model.trim()) {
        throw new Error("Provider and model are required.");
      }
      const payload: PricingInput = {
        provider: provider.trim(),
        model: model.trim(),
        model_match: match,
        input_price_per_1m: Number(input || 0),
        output_price_per_1m: Number(output || 0),
        cache_read_price_per_1m: cacheRead === "" ? null : Number(cacheRead),
        cache_write_price_per_1m: cacheWrite === "" ? null : Number(cacheWrite),
        reasoning_price_per_1m: reasoning === "" ? null : Number(reasoning),
        currency: "USD",
        effective_from: effectiveFrom ? new Date(effectiveFrom).toISOString() : null,
      };
      if (
        ![payload.input_price_per_1m, payload.output_price_per_1m].every(
          (value) => Number.isFinite(value) && value >= 0
        )
      ) {
        throw new Error("Prices must be non-negative numbers.");
      }
      await api.pricing.create(payload);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create the price.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      title="Add price"
      onClose={onClose}
      footer={
        <>
          <Button variant="primary" disabled={busy} onClick={() => void submit()}>
            Add price
          </Button>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <div className="stack">
        {error ? <Alert variant="danger" message={error} /> : null}
        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Provider">
            <TextInput value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="openai" />
          </Field>
          <Field label="Model">
            <TextInput value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o-mini" />
          </Field>
          <Field label="Match">
            <Select
              value={match}
              onChange={(e) => setMatch(e.target.value as "exact" | "prefix" | "default")}
              aria-label="Model match kind"
            >
              <option value="exact">exact</option>
              <option value="prefix">prefix</option>
              <option value="default">default</option>
            </Select>
          </Field>
        </div>
        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Input $/1M">
            <TextInput value={input} inputMode="decimal" onChange={(e) => setInput(e.target.value)} placeholder="0.15" />
          </Field>
          <Field label="Output $/1M">
            <TextInput value={output} inputMode="decimal" onChange={(e) => setOutput(e.target.value)} placeholder="0.60" />
          </Field>
          <Field label="Cache read $/1M">
            <TextInput value={cacheRead} inputMode="decimal" onChange={(e) => setCacheRead(e.target.value)} placeholder="optional" />
          </Field>
        </div>
        <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
          <Field label="Cache write $/1M">
            <TextInput value={cacheWrite} inputMode="decimal" onChange={(e) => setCacheWrite(e.target.value)} placeholder="optional" />
          </Field>
          <Field label="Reasoning $/1M">
            <TextInput value={reasoning} inputMode="decimal" onChange={(e) => setReasoning(e.target.value)} placeholder="optional" />
          </Field>
          <Field label="Effective from">
            <TextInput
              type="datetime-local"
              value={effectiveFrom}
              onChange={(e) => setEffectiveFrom(e.target.value)}
              aria-label="Effective from"
            />
          </Field>
        </div>
      </div>
    </Dialog>
  );
}

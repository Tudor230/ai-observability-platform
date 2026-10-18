import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRefresh } from "../state/RefreshContext";
import { Button, Select } from "./core";
import { IconRefresh } from "./core/icons";

/** Re-fetches every active query, plus the persisted auto-refresh cadence. */
export function RefreshButton() {
  const queryClient = useQueryClient();
  const { interval, setIntervalMs } = useRefresh();
  const [busy, setBusy] = useState(false);
  return (
    <span className="row" style={{ gap: 6, alignItems: "center" }}>
      <Button
        variant="quiet"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await queryClient.invalidateQueries();
          } finally {
            setBusy(false);
          }
        }}
        title="Refresh data"
      >
        <IconRefresh size={14} />
        Refresh
      </Button>
      <Select
        value={String(interval)}
        aria-label="Auto-refresh interval"
        title="Auto-refresh interval"
        onChange={(e) => setIntervalMs(Number(e.target.value))}
      >
        <option value="0">Auto: off</option>
        <option value="30000">30s</option>
        <option value="60000">1m</option>
        <option value="300000">5m</option>
      </Select>
    </span>
  );
}

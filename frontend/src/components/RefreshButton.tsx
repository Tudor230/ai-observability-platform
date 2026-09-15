import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "./core";
import { IconRefresh } from "./core/icons";

/** Re-fetches every active query (and their dependents). */
export function RefreshButton() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  return (
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
  );
}

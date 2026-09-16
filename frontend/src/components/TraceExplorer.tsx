import { useCallback, useMemo, useState } from "react";
import type { TraceSpan } from "@evilmartians/agent-prism-types";
import {
  filterSpansRecursively,
  flattenSpans,
} from "@evilmartians/agent-prism-data";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";

import { DetailsView } from "./agent-prism/DetailsView/DetailsView";
import { TraceViewerPlaceholder } from "./agent-prism/TraceViewer/TraceViewerPlaceholder";
import { TraceViewerTreeViewContainer } from "./agent-prism/TraceViewer/TraceViewerTreeViewContainer";

/**
 * The span explorer: a resizable [span tree | span details] split built from
 * the vendored AgentPrism components (search, expand/collapse, connector tree,
 * timeline and the details panel all come from the library).
 *
 * Mount it with a `key` per trace: the initial expansion/selection is derived
 * from the spans on first render, so a new trace gets a fresh explorer.
 */
export function TraceExplorer({ spans }: { spans: TraceSpan[] }) {
  const flat = useMemo(() => flattenSpans(spans), [spans]);
  const allIds = useMemo(() => flat.map((span) => span.id), [flat]);

  const [searchValue, setSearchValue] = useState("");
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [expandedSpansIds, setExpandedSpansIds] = useState<string[]>(allIds);

  const selectedSpan = useMemo(
    () => flat.find((span) => span.id === selectedSpanId) ?? spans[0],
    [flat, selectedSpanId, spans]
  );

  const filteredSpans = useMemo(
    () => (searchValue.trim() ? filterSpansRecursively(spans, searchValue) : spans),
    [spans, searchValue]
  );

  const handleExpandAll = useCallback(() => setExpandedSpansIds(allIds), [allIds]);
  const handleCollapseAll = useCallback(() => setExpandedSpansIds([]), []);
  const handleSpanSelect = useCallback(
    (span: TraceSpan | undefined) => setSelectedSpanId(span?.id ?? null),
    []
  );

  return (
    <div className="trace-explorer">
      <PanelGroup direction="horizontal" autoSaveId="aiobs.trace-explorer">
        <Panel id="span-tree" defaultSize={55} minSize={25} className="trace-explorer__pane">
          <TraceViewerTreeViewContainer
            showHeader={false}
            searchValue={searchValue}
            setSearchValue={setSearchValue}
            handleExpandAll={handleExpandAll}
            handleCollapseAll={handleCollapseAll}
            filteredSpans={filteredSpans}
            selectedSpan={selectedSpan}
            setSelectedSpan={handleSpanSelect}
            expandedSpansIds={expandedSpansIds}
            setExpandedSpansIds={setExpandedSpansIds}
          />
        </Panel>
        <PanelResizeHandle className="trace-explorer__handle" />
        <Panel id="span-details" defaultSize={45} minSize={25} className="trace-explorer__pane">
          {selectedSpan ? (
            <DetailsView data={selectedSpan} allSpans={spans} />
          ) : (
            <TraceViewerPlaceholder title="Select a span to see the details" />
          )}
        </Panel>
      </PanelGroup>
    </div>
  );
}

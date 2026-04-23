import { forwardRef } from "react";
import type { QueryResult } from "../../../shared/types";
import { getSnapshotRows } from "../lib/queryPresentation";
import { ResultChart } from "./ResultChart";
import { ResultTable } from "./ResultTable";

export const VisualizationPanel = forwardRef<HTMLElement, { query: QueryResult }>(function VisualizationPanel(
  { query },
  ref,
) {
  const rows = getSnapshotRows(query);

  return (
    <section ref={ref} className="analytics-card visualization-card-shell">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Visualization</span>
          <h3>Chart and table from the semantic plan</h3>
        </div>
      </div>
      <ResultChart query={query} />
      <ResultTable rows={rows} />
    </section>
  );
});

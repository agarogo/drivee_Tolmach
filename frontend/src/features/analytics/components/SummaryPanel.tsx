import type { QueryResult } from "../../../shared/types";
import { getSummaryText } from "../lib/queryPresentation";

export function SummaryPanel({ query }: { query: QueryResult }) {
  const summary = getSummaryText(query);
  if (!summary) return null;

  return (
    <section className="analytics-card">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Summary</span>
          <h3>Summary only from returned rows</h3>
        </div>
      </div>
      <p className="analytics-lead">{summary}</p>
      <small className="analytics-note">
        Этот блок показывается только после безопасного выполнения SQL и строится по фактическим rows.
      </small>
    </section>
  );
}

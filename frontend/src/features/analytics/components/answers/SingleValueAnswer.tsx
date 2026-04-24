import type { SingleValueResponse } from "../../../../shared/types";
import type { AnalyticsViewMode } from "../../lib/answerUi";
import {
  formatMetricValue,
  formatPercent,
  formatSignedDelta,
  formatTimestamp,
  statusTone,
} from "../../lib/answerUi";
import { ResultTable } from "../ResultTable";

function DeltaBadge({ payload }: { payload: SingleValueResponse }) {
  const tone = statusTone(payload.delta_abs);
  if (payload.delta_abs === null && payload.delta_pct === null) {
    return <span className="delta-badge neutral">{payload.availability_note || "Previous-period delta unavailable"}</span>;
  }
  return (
    <span className={`delta-badge ${tone}`}>
      {formatSignedDelta(payload.delta_abs)} / {formatPercent(payload.delta_pct)}
    </span>
  );
}

export function SingleValueAnswer({
  payload,
  activeView,
  summary,
}: {
  payload: SingleValueResponse;
  activeView: AnalyticsViewMode;
  summary: string;
}) {
  if (activeView === "table") {
    return (
      <ResultTable
        title="Supporting rows"
        description={payload.context}
        rows={payload.supporting_rows}
        columns={payload.columns}
        showControls={false}
        emptyMessage="No supporting rows were returned for this KPI."
      />
    );
  }

  return (
    <section className="answer-card single-value-answer">
      <div className="single-value-hero">
        <div>
          <span className="eyebrow">Single KPI</span>
          <h3>{payload.metric_label || payload.metric_key}</h3>
        </div>
        <DeltaBadge payload={payload} />
      </div>

      <div className="single-value-number">{formatMetricValue(payload.current_value, { compact: true })}</div>

      <div className="single-value-meta">
        <div>
          <span className="field-label">Current value</span>
          <strong>{formatMetricValue(payload.current_value)}</strong>
        </div>
        <div>
          <span className="field-label">Previous period</span>
          <strong>{formatMetricValue(payload.previous_value)}</strong>
        </div>
        <div>
          <span className="field-label">Freshness</span>
          <strong>{formatTimestamp(payload.freshness_timestamp)}</strong>
        </div>
      </div>

      <p className="answer-lead">{summary || payload.context}</p>
      <div className="answer-footnote">
        <span>{payload.context}</span>
        {payload.availability_note && <span>{payload.availability_note}</span>}
      </div>
    </section>
  );
}

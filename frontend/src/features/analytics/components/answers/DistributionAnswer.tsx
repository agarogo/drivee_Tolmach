import type { DistributionResponse, QueryResultRow } from "../../../../shared/types";
import type { AnalyticsViewMode } from "../../lib/answerUi";
import { formatMetricValue, formatPercent } from "../../lib/answerUi";
import { ResultTable } from "../ResultTable";
import { DistributionDonutChart } from "./AnswerCharts";

export function DistributionAnswer({
  payload,
  activeView,
  summary,
}: {
  payload: DistributionResponse;
  activeView: AnalyticsViewMode;
  summary: string;
}) {
  const chartRows: QueryResultRow[] = payload.items.map((item) => ({
    label: item.label,
    value: typeof item.value === "number" ? item.value : Number(item.value || 0),
    share_pct: item.share_pct ?? 0,
  }));

  if (activeView === "table") {
    return (
      <ResultTable
        title="Distribution table"
        description={payload.insight}
        rows={payload.rows}
        columns={payload.columns}
        defaultSort={{ key: payload.metric_key, direction: "desc" }}
      />
    );
  }

  return (
    <section className="answer-card distribution-answer">
      <div className="answer-card-head">
        <div>
          <span className="eyebrow">Distribution</span>
          <h3>{payload.metric_label || payload.metric_key}</h3>
        </div>
        <span className="answer-chip">100% integrity: {formatPercent(payload.integrity_pct)}</span>
      </div>

      <p className="answer-lead">{summary || payload.insight}</p>

      <div className="distribution-layout">
        <DistributionDonutChart data={chartRows} labelKey="label" valueKey="value" />

        <div className="distribution-list-card">
          <div className="distribution-list-head">
            <strong>{payload.dimension_label || payload.dimension_key}</strong>
            <small>Total: {formatMetricValue(payload.total_value)}</small>
          </div>
          <div className="distribution-list">
            {payload.items.map((item) => (
              <div key={`${item.rank}-${item.label}`} className="distribution-row">
                <div>
                  <strong>{item.label}</strong>
                  {item.is_other && <small>Collapsed long tail bucket</small>}
                </div>
                <div>
                  <strong>{formatPercent(item.share_pct)}</strong>
                  <small>{formatMetricValue(item.value)}</small>
                </div>
              </div>
            ))}
          </div>
          {payload.other_bucket_applied && (
            <p className="answer-footnote">
              Categories beyond the visible limit were collapsed into <strong>Other</strong> so the distribution still
              sums to 100%.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

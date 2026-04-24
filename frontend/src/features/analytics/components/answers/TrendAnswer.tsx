import type { TrendResponse } from "../../../../shared/types";
import type { AnalyticsViewMode } from "../../lib/answerUi";
import { formatMetricValue } from "../../lib/answerUi";
import { ResultTable } from "../ResultTable";
import { TrendLineChart } from "./AnswerCharts";

export function TrendAnswer({
  payload,
  activeView,
  summary,
}: {
  payload: TrendResponse;
  activeView: AnalyticsViewMode;
  summary: string;
}) {
  if (activeView === "table") {
    return (
      <ResultTable
        title="Trend table"
        description={payload.insight}
        rows={payload.rows}
        columns={payload.columns}
        defaultSort={{ key: payload.time_key, direction: "asc" }}
      />
    );
  }

  return (
    <section className="answer-card trend-answer">
      <div className="answer-card-head">
        <div>
          <span className="eyebrow">Trend</span>
          <h3>{payload.metric_label || payload.metric_key}</h3>
        </div>
        <span className="answer-chip">{payload.points.length} points</span>
      </div>

      <p className="answer-lead">{summary || payload.insight}</p>
      <TrendLineChart
        data={payload.rows}
        xKey={payload.time_key}
        lineKey={payload.metric_key}
        label={payload.metric_label || payload.metric_key}
      />

      <div className="trend-highlights">
        <article className="trend-highlight">
          <span>Peak</span>
          <strong>{payload.peak.label || "Not available"}</strong>
          <small>{formatMetricValue(payload.peak.value)}</small>
        </article>
        <article className="trend-highlight">
          <span>Low</span>
          <strong>{payload.low.label || "Not available"}</strong>
          <small>{formatMetricValue(payload.low.value)}</small>
        </article>
        <article className="trend-highlight trend-highlight--insight">
          <span>Insight</span>
          <p>{payload.insight || summary || "Time-series response is ready from the current answer grain."}</p>
        </article>
      </div>
    </section>
  );
}

import type { ComparisonResponse } from "../../../../shared/types";
import type { AnalyticsViewMode } from "../../lib/answerUi";
import { formatMetricValue, formatPercent } from "../../lib/answerUi";
import { ResultTable } from "../ResultTable";
import { RankingBarChart } from "./AnswerCharts";

export function ComparisonTopAnswer({
  payload,
  activeView,
  summary,
}: {
  payload: ComparisonResponse;
  activeView: AnalyticsViewMode;
  summary: string;
}) {
  const leader = payload.items[0];

  if (activeView === "table") {
    return (
      <ResultTable
        title="Comparison table"
        description={payload.insight}
        rows={payload.rows}
        columns={payload.columns}
        defaultSort={{ key: payload.metric_key, direction: "desc" }}
      />
    );
  }

  return (
    <section className="answer-card comparison-answer">
      <div className="answer-card-head">
        <div>
          <span className="eyebrow">Comparison / Top</span>
          <h3>{payload.metric_label || payload.metric_key}</h3>
        </div>
        {leader && (
          <div className="leader-chip">
            <span>Leader</span>
            <strong>{leader.label}</strong>
            <small>{formatMetricValue(leader.value)}</small>
          </div>
        )}
      </div>

      <p className="answer-lead">{summary || payload.insight}</p>

      <div className="comparison-layout">
        <RankingBarChart
          data={payload.rows}
          xKey={payload.dimension_key}
          barKey={payload.metric_key}
          label={payload.metric_label || payload.metric_key}
        />

        <div className="comparison-ranking-card">
          <div className="comparison-ranking-head">
            <strong>Ranking</strong>
            <span>{payload.dimension_label || payload.dimension_key}</span>
          </div>
          <div className="comparison-ranking-list">
            {payload.items.map((item) => (
              <div key={`${item.rank}-${item.label}`} className="comparison-ranking-row">
                <div>
                  <small>#{item.rank}</small>
                  <strong>{item.label}</strong>
                </div>
                <div>
                  <strong>{formatMetricValue(item.value)}</strong>
                  <small>{item.share_pct !== null ? formatPercent(item.share_pct) : payload.metric_label}</small>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <ResultTable
        title="Detailed ranking"
        description="The table mirrors the same governed comparison grain as the chart."
        rows={payload.rows}
        columns={payload.columns}
        defaultSort={{ key: payload.metric_key, direction: "desc" }}
        showControls={false}
      />
    </section>
  );
}

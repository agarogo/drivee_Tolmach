import type {
  FullReportChartSection,
  FullReportInsightSection,
  FullReportResponse,
  FullReportTableSection,
} from "../../../../shared/types";
import type { AnalyticsViewMode } from "../../lib/answerUi";
import { formatMetricValue } from "../../lib/answerUi";
import { ResultTable } from "../ResultTable";
import { RankingBarChart, TrendLineChart } from "./AnswerCharts";

function ReportChartPanel({ section }: { section: FullReportChartSection }) {
  return (
    <article className="report-section-card">
      <div className="report-section-head">
        <strong>{section.title}</strong>
        <span>{section.metric_label || section.metric_key}</span>
      </div>
      {section.chart_type === "line" ? (
        <TrendLineChart
          data={section.rows}
          xKey={section.x_key}
          lineKey={section.metric_key}
          label={section.metric_label || section.metric_key}
        />
      ) : (
        <RankingBarChart
          data={section.rows}
          xKey={section.x_key}
          barKey={section.metric_key}
          label={section.metric_label || section.metric_key}
        />
      )}
    </article>
  );
}

function ReportTablePanel({ section }: { section: FullReportTableSection }) {
  return (
    <ResultTable
      title={section.title}
      description="This preview is part of the current report payload."
      rows={section.rows}
      columns={section.columns}
      showControls={false}
      emptyMessage="This report payload does not include a table preview."
    />
  );
}

function ReportInsightPanel({ section }: { section: FullReportInsightSection }) {
  return (
    <article className="report-section-card report-section-card--insight">
      <div className="report-section-head">
        <strong>{section.title}</strong>
      </div>
      <p>{section.body}</p>
    </article>
  );
}

export function FullReportAnswer({
  payload,
  activeView,
  summary,
  onRequestSave,
  onReuseQuestion,
}: {
  payload: FullReportResponse;
  activeView: AnalyticsViewMode;
  summary: string;
  onRequestSave: () => void;
  onReuseQuestion: () => void;
}) {
  const chartSections = payload.sections.filter((section): section is FullReportChartSection => section.kind === "chart");
  const tableSections = payload.sections.filter((section): section is FullReportTableSection => section.kind === "table");
  const insightSections = payload.sections.filter((section): section is FullReportInsightSection => section.kind === "insight");

  if (activeView === "number") {
    return (
      <section className="answer-card full-report-answer">
        <div className="answer-card-head">
          <div>
            <span className="eyebrow">Report KPI View</span>
            <h3>{payload.title}</h3>
          </div>
        </div>
        <div className="report-kpi-grid">
          {payload.kpis.map((item) => (
            <article key={item.key} className="report-kpi-card">
              <span>{item.label}</span>
              <strong>{formatMetricValue(item.value, { compact: true })}</strong>
            </article>
          ))}
        </div>
      </section>
    );
  }

  if (activeView === "chart") {
    return (
      <section className="answer-card full-report-answer">
        <div className="answer-card-head">
          <div>
            <span className="eyebrow">Report Charts</span>
            <h3>{payload.title}</h3>
          </div>
        </div>
        <div className="report-charts-grid">
          {chartSections.slice(0, 2).map((section) => (
            <ReportChartPanel key={section.title} section={section} />
          ))}
        </div>
      </section>
    );
  }

  if (activeView === "table") {
    if (tableSections[0]) {
      return (
        <section className="answer-card full-report-answer">
          <div className="answer-card-head">
            <div>
              <span className="eyebrow">Report Table</span>
              <h3>{payload.title}</h3>
            </div>
          </div>
          <ReportTablePanel section={tableSections[0]} />
        </section>
      );
    }
    return (
      <section className="answer-card full-report-answer">
        <div className="answer-card-head">
          <div>
            <span className="eyebrow">Report Table</span>
            <h3>{payload.title}</h3>
          </div>
        </div>
        <p className="answer-lead">This report does not include a table section in the current payload.</p>
      </section>
    );
  }

  return (
    <section className="answer-card full-report-answer">
      <div className="answer-card-head">
        <div>
          <span className="eyebrow">Full Report</span>
          <h3>{payload.title}</h3>
        </div>
        <div className="answer-action-group">
          <button type="button" className="run-btn small" onClick={onRequestSave}>
            Save report
          </button>
          <button type="button" className="ghost-btn compact" onClick={onReuseQuestion}>
            Re-run in composer
          </button>
        </div>
      </div>

      <p className="answer-lead">{payload.summary || summary}</p>

      <div className="report-kpi-grid">
        {payload.kpis.map((item) => (
          <article key={item.key} className="report-kpi-card">
            <span>{item.label}</span>
            <strong>{formatMetricValue(item.value, { compact: true })}</strong>
            {item.unit_label && <small>{item.unit_label}</small>}
          </article>
        ))}
      </div>

      {!!insightSections.length && (
        <div className="report-insight-grid">
          {insightSections.map((section) => (
            <ReportInsightPanel key={section.title} section={section} />
          ))}
        </div>
      )}

      {!!chartSections.length && (
        <div className="report-charts-grid">
          {chartSections.slice(0, 2).map((section) => (
            <ReportChartPanel key={section.title} section={section} />
          ))}
        </div>
      )}

      {!!tableSections.length && <ReportTablePanel section={tableSections[0]} />}

      {!!payload.insights.length && (
        <div className="report-callout-list">
          {payload.insights.map((insight, index) => (
            <article key={`${index}-${insight}`} className="report-callout">
              <strong>Insight {index + 1}</strong>
              <p>{insight}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

import { forwardRef, useEffect, useState } from "react";
import type {
  ChatHelpResponse,
  ComparisonResponse,
  DistributionResponse,
  FullReportResponse,
  QueryResult,
  SingleValueResponse,
  TableResponse,
  TrendResponse,
} from "../../../shared/types";
import { getAnswerEnvelope, type AnalyticsViewMode } from "../lib/answerUi";
import { ViewModeSwitcher } from "./ViewModeSwitcher";
import { ChatHelpAnswer } from "./answers/ChatHelpAnswer";
import { ComparisonTopAnswer } from "./answers/ComparisonTopAnswer";
import { DistributionAnswer } from "./answers/DistributionAnswer";
import { FullReportAnswer } from "./answers/FullReportAnswer";
import { SingleValueAnswer } from "./answers/SingleValueAnswer";
import { TableAnswer } from "./answers/TableAnswer";
import { TrendAnswer } from "./answers/TrendAnswer";

function analyticsView(answerPrimaryView: string): AnalyticsViewMode {
  if (answerPrimaryView === "number" || answerPrimaryView === "chart" || answerPrimaryView === "table" || answerPrimaryView === "report") {
    return answerPrimaryView;
  }
  return "table";
}

export const AnswerRenderer = forwardRef<HTMLElement, {
  query: QueryResult;
  onReuseQuestion: (value: string) => void;
  onRequestSave: () => void;
}>(function AnswerRenderer({ query, onReuseQuestion, onRequestSave }, ref) {
  const answer = getAnswerEnvelope(query);
  const [activeView, setActiveView] = useState<AnalyticsViewMode>(analyticsView(answer?.primary_view_mode || "table"));

  useEffect(() => {
    setActiveView(analyticsView(answer?.primary_view_mode || "table"));
  }, [answer?.primary_view_mode, answer?.metadata?.query_id, query.id]);

  if (!answer || !answer.render_payload) {
    return (
      <section ref={ref} className="answer-card legacy-answer-panel">
        <div className="answer-card-head">
          <div>
            <span className="eyebrow">Typed Answer Missing</span>
            <h3>This response needs a fresh run</h3>
          </div>
        </div>
        <p className="answer-lead">
          The frontend no longer guesses a layout from legacy chart metadata. Re-run the question to get a first-class
          answer_type payload.
        </p>
        <div className="answer-action-group">
          <button type="button" className="run-btn small" onClick={() => onReuseQuestion(query.natural_text)}>
            Put question back into composer
          </button>
        </div>
      </section>
    );
  }

  const payload = answer.render_payload;
  const summary = query.ai_answer || answer.answer_type_reason;

  return (
    <section ref={ref} className="answer-renderer-shell">
      <section className="answer-card answer-card--meta">
        <div className="answer-card-head">
          <div>
            <span className="eyebrow">Answer Type</span>
            <h3>{answer.answer_type_label}</h3>
          </div>
          <div className="answer-chip-stack">
            <span className="answer-chip">{answer.result_grain}</span>
            <span className="answer-chip">{query.rows_returned} rows</span>
            <span className="answer-chip">{query.execution_ms} ms</span>
          </div>
        </div>
        <p className="answer-lead">{answer.explanation_why_this_type || answer.answer_type_reason}</p>
      </section>

      {answer.answer_type_key !== "chat_help" && (
        <ViewModeSwitcher answer={answer} activeView={activeView} onChange={setActiveView} />
      )}

      {answer.answer_type_key === "chat_help" && (
        <ChatHelpAnswer payload={payload as ChatHelpResponse} onReuseQuestion={onReuseQuestion} />
      )}

      {answer.answer_type_key === "single_value" && (
        <SingleValueAnswer payload={payload as SingleValueResponse} activeView={activeView} summary={summary} />
      )}

      {answer.answer_type_key === "comparison_top" && (
        <ComparisonTopAnswer payload={payload as ComparisonResponse} activeView={activeView} summary={summary} />
      )}

      {answer.answer_type_key === "trend" && (
        <TrendAnswer payload={payload as TrendResponse} activeView={activeView} summary={summary} />
      )}

      {answer.answer_type_key === "distribution" && (
        <DistributionAnswer payload={payload as DistributionResponse} activeView={activeView} summary={summary} />
      )}

      {answer.answer_type_key === "table" && <TableAnswer payload={payload as TableResponse} summary={summary} />}

      {answer.answer_type_key === "full_report" && (
        <FullReportAnswer
          payload={payload as FullReportResponse}
          activeView={activeView}
          summary={summary}
          onRequestSave={onRequestSave}
          onReuseQuestion={() => onReuseQuestion(query.natural_text)}
        />
      )}
    </section>
  );
});

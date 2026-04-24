import { useRef, useState } from "react";
import type { RefObject } from "react";
import type { QueryResult } from "../../../shared/types";
import { formatDate } from "../../../shared/utils/format";
import { getAnswerEnvelope } from "../lib/answerUi";
import { buildPipelineStages } from "../lib/queryPresentation";
import { AnswerRenderer } from "./AnswerRenderer";
import { BlockedQueryPanel } from "./BlockedQueryPanel";
import { ClarificationPanel } from "./ClarificationPanel";
import { PipelineTimeline } from "./PipelineTimeline";
import { RequestUnderstandingPanel } from "./RequestUnderstandingPanel";
import { ResultExportActions } from "./ResultExportActions";
import { SqlDiagnosticsPanel } from "./SqlDiagnosticsPanel";

function SaveReportPanel({
  query,
  onSave,
  saving,
  anchorRef,
}: {
  query: QueryResult;
  onSave: (title: string, schedule: Record<string, unknown> | null, recipients: string[]) => void;
  saving: boolean;
  anchorRef: RefObject<HTMLElement>;
}) {
  const [title, setTitle] = useState(
    query.interpretation?.metric
      ? `${String(query.interpretation.metric)} отчёт ${formatDate(query.created_at)}`
      : "Аналитический отчёт",
  );
  const [enabled, setEnabled] = useState(query.answer?.answer_type_key === "full_report");
  const [frequency, setFrequency] = useState("weekly");
  const [recipients, setRecipients] = useState("ops-team@drivee.example");

  return (
    <section ref={anchorRef} className="answer-card save-report-card">
      <div className="answer-card-head">
        <div>
          <span className="eyebrow">Сохранение отчёта</span>
          <h3>Сохранить этот ответ как полноценный отчёт</h3>
        </div>
      </div>
      <div className="save-panel">
        <div>
          <label className="field-label">Название</label>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </div>
        <label className="toggle-line">
          <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
          Включить расписание
        </label>
        <div>
          <label className="field-label">Частота</label>
          <select value={frequency} onChange={(event) => setFrequency(event.target.value)}>
            <option value="daily">ежедневно</option>
            <option value="weekly">еженедельно</option>
            <option value="monthly">ежемесячно</option>
          </select>
        </div>
        <div>
          <label className="field-label">Получатели</label>
          <input
            value={recipients}
            onChange={(event) => setRecipients(event.target.value)}
            placeholder="ops-team@drivee.example"
          />
        </div>
        <button
          type="button"
          className="run-btn"
          disabled={saving}
          onClick={() =>
            onSave(
              title,
              enabled ? { frequency, run_at_time: "09:00:00", day_of_week: 1 } : null,
              recipients
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
            )
          }
        >
          {saving ? "Сохраняем..." : "Сохранить отчёт"}
        </button>
      </div>
    </section>
  );
}

function ExecutionFailurePanel({ query, onReuseQuestion }: { query: QueryResult; onReuseQuestion: (value: string) => void }) {
  return (
    <section className="analytics-card analytics-state-card danger">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Ошибка выполнения</span>
          <h3>Запрос не завершился корректно</h3>
        </div>
        <span className="state-pill danger">{query.status}</span>
      </div>
      <p className="analytics-lead">
        {query.error_message || "Выполнение остановилось после SQL-валидации. Ниже показана последняя безопасная диагностика от backend."}
      </p>
      <div className="action-strip">
        <button type="button" className="ghost-btn" onClick={() => onReuseQuestion(query.natural_text)}>
          Вернуть вопрос в поле ввода
        </button>
      </div>
    </section>
  );
}

export function ResultMessage({
  query,
  saving,
  onSave,
  onClarify,
  onReuseQuestion,
}: {
  query: QueryResult;
  saving: boolean;
  onSave: (title: string, schedule: Record<string, unknown> | null, recipients: string[]) => void;
  onClarify: (value: string, freeform?: string) => void;
  onReuseQuestion: (text: string) => void;
}) {
  const exportRef = useRef<HTMLElement>(null);
  const savePanelRef = useRef<HTMLElement>(null);
  const stages = buildPipelineStages(query, false);
  const answer = getAnswerEnvelope(query);

  return (
    <div className="assistant-card result-stack analytics-flow-shell">
      <PipelineTimeline stages={stages} running={false} />

      {query.status === "clarification_required" && (
        <ClarificationPanel query={query} onClarify={onClarify} />
      )}

      {query.status === "blocked" && (
        <BlockedQueryPanel query={query} onReuseQuestion={onReuseQuestion} />
      )}

      {(query.status === "sql_error" || query.status === "autofix_failed") && (
        <ExecutionFailurePanel query={query} onReuseQuestion={onReuseQuestion} />
      )}

      {query.status === "success" && (
        <div className="answer-message-layout">
          <div className="answer-message-main">
            <AnswerRenderer
              ref={exportRef}
              query={query}
              onReuseQuestion={onReuseQuestion}
              onRequestSave={() => savePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })}
            />

            {answer?.answer_type_key !== "chat_help" && <ResultExportActions query={query} exportRef={exportRef} />}

            {answer?.requires_sql && (
              <SaveReportPanel query={query} saving={saving} onSave={onSave} anchorRef={savePanelRef} />
            )}
          </div>

          <div className="answer-message-side">
            <RequestUnderstandingPanel query={query} />
            <SqlDiagnosticsPanel query={query} />
          </div>
        </div>
      )}
    </div>
  );
}

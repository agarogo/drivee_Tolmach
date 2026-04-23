import { useRef, useState } from "react";
import type { QueryResult } from "../../../shared/types";
import { formatDate } from "../../../shared/utils/format";
import { buildPipelineStages } from "../lib/queryPresentation";
import { BlockedQueryPanel } from "./BlockedQueryPanel";
import { ClarificationPanel } from "./ClarificationPanel";
import { PipelineTimeline } from "./PipelineTimeline";
import { RequestUnderstandingPanel } from "./RequestUnderstandingPanel";
import { ResultExportActions } from "./ResultExportActions";
import { SqlDiagnosticsPanel } from "./SqlDiagnosticsPanel";
import { SummaryPanel } from "./SummaryPanel";
import { VisualizationPanel } from "./VisualizationPanel";

function SaveReportPanel({
  query,
  onSave,
  saving,
}: {
  query: QueryResult;
  onSave: (title: string, schedule: Record<string, unknown> | null, recipients: string[]) => void;
  saving: boolean;
}) {
  const [title, setTitle] = useState(
    query.interpretation?.metric
      ? `${String(query.interpretation.metric)} · ${formatDate(query.created_at)}`
      : "Новый отчет",
  );
  const [enabled, setEnabled] = useState(true);
  const [frequency, setFrequency] = useState("weekly");
  const [recipients, setRecipients] = useState("ops-team@drivee.example");

  return (
    <section className="analytics-card save-report-card">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Report</span>
          <h3>Save as report</h3>
        </div>
      </div>
      <div className="save-panel">
        <div>
          <label className="field-label">Title</label>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </div>
        <label className="toggle-line">
          <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
          Enable schedule
        </label>
        <div>
          <label className="field-label">Frequency</label>
          <select value={frequency} onChange={(event) => setFrequency(event.target.value)}>
            <option value="daily">daily</option>
            <option value="weekly">weekly</option>
            <option value="monthly">monthly</option>
          </select>
        </div>
        <div>
          <label className="field-label">Recipients</label>
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
          {saving ? "Saving..." : "Save report"}
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
          <span className="eyebrow">Execution Error</span>
          <h3>Query did not finish safely</h3>
        </div>
        <span className="state-pill danger">{query.status}</span>
      </div>
      <p className="analytics-lead">
        {query.error_message || "Execution failed after SQL validation. Frontend shows the last safe diagnostics from backend."}
      </p>
      <div className="action-strip">
        <button type="button" className="ghost-btn" onClick={() => onReuseQuestion(query.natural_text)}>
          Put question back into composer
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
  const stages = buildPipelineStages(query, false);

  return (
    <div className="assistant-card result-stack analytics-flow-shell">
      <PipelineTimeline stages={stages} running={false} />
      <RequestUnderstandingPanel query={query} />

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
        <>
          <SummaryPanel query={query} />
          <VisualizationPanel ref={exportRef} query={query} />
          <ResultExportActions query={query} exportRef={exportRef} />
          <SaveReportPanel query={query} saving={saving} onSave={onSave} />
        </>
      )}

      <SqlDiagnosticsPanel query={query} />
    </div>
  );
}

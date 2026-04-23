import { useMemo, useState } from "react";
import type { QueryResult } from "../../../shared/types";
import { formatDate } from "../../../shared/utils/format";
import { ResultChart } from "./ResultChart";
import { ResultTable } from "./ResultTable";

function exportCsv(rows: Array<Record<string, any>>, fileName = "tolmach-result.csv") {
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => JSON.stringify(row[column] ?? "")).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

function MetricsCards({ rows }: { rows: Array<Record<string, any>> }) {
  const metrics = useMemo(() => {
    if (!rows.length) return [];
    const first = rows[0];
    const numeric = Object.keys(first).filter((key) => typeof first[key] === "number");
    return [
      ["Строк", rows.length, "в результате"],
      ["Главная метрика", numeric[0] ? first[numeric[0]] : "n/a", numeric[0] || ""],
      ["Лидер", first.city || first.day || first.driver_id || "n/a", "первая строка"],
      ["Покрытие", `${Math.min(rows.length, 200)}`, "snapshot rows"],
    ];
  }, [rows]);
  return (
    <div className="metrics">
      {metrics.map(([label, value, meta]) => (
        <div className="metric-card" key={label}>
          <span>{label}</span>
          <strong>{String(value)}</strong>
          <small>{meta}</small>
        </div>
      ))}
    </div>
  );
}

function ExplainBlock({ query }: { query: QueryResult }) {
  const explain = query.interpretation?.explain || {};
  const resolved = query.resolved_request || {};
  const filters = resolved.filters || explain.filters || {};
  return (
    <div className="explain-block">
      <div className="card-label">Система поняла запрос так</div>
      <dl>
        <dt>метрика</dt>
        <dd>{resolved.metric || explain.metric || query.interpretation.metric || "не определена"}</dd>
        <dt>разрез</dt>
        <dd>{(resolved.dimensions || explain.dimensions || query.interpretation.dimensions || []).join(", ") || "нет"}</dd>
        <dt>период</dt>
        <dd>{resolved.period?.label || explain.period || query.interpretation.date_range?.label || "не указан"}</dd>
        <dt>фильтры</dt>
        <dd>{JSON.stringify(filters)}</dd>
        <dt>сортировка</dt>
        <dd>{explain.sorting || query.sql_plan?.order_by || "нет"}</dd>
        <dt>ограничение</dt>
        <dd>{resolved.limit || explain.limit || query.sql_plan?.limit || "policy limit"}</dd>
        <dt>pipeline</dt>
        <dd>{explain.source || query.interpretation.source || "unknown"}</dd>
        <dt>provider confidence</dt>
        <dd>{Math.round((explain.provider_confidence || query.interpretation.provider_confidence || 0) * 100)}%</dd>
        <dt>EXPLAIN cost</dt>
        <dd>{query.sql_explain_cost || 0}</dd>
      </dl>
      <div className="semantic-chips">
        {(query.semantic_terms || []).slice(0, 8).map((term) => (
          <span key={term.term}>{term.term}</span>
        ))}
      </div>
      <div className="reason-list">
        {(query.confidence_reasons || []).map((reason) => (
          <div key={reason} className="reason info">
            {reason}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SaveReportPanel({
  query,
  onSave,
  saving,
}: {
  query: QueryResult;
  onSave: (title: string, schedule: Record<string, any> | null, recipients: string[]) => void;
  saving: boolean;
}) {
  const [title, setTitle] = useState(query.interpretation?.metric ? `${query.interpretation.metric} - ${formatDate(query.created_at)}` : "Новый отчёт");
  const [enabled, setEnabled] = useState(true);
  const [frequency, setFrequency] = useState("weekly");
  const [recipients, setRecipients] = useState("ops-team@drivee.example");
  return (
    <div className="save-panel">
      <div>
        <div className="card-label">Сохранить как отчёт</div>
        <input value={title} onChange={(event) => setTitle(event.target.value)} />
      </div>
      <label className="toggle-line">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
        Включить расписание
      </label>
      <select value={frequency} onChange={(event) => setFrequency(event.target.value)}>
        <option value="daily">daily</option>
        <option value="weekly">weekly</option>
        <option value="monthly">monthly</option>
      </select>
      <input value={recipients} onChange={(event) => setRecipients(event.target.value)} placeholder="получатели через запятую" />
      <button
        className="run-btn"
        disabled={saving}
        onClick={() =>
          onSave(
            title,
            enabled ? { frequency, run_at_time: "09:00:00", day_of_week: 1 } : null,
            recipients
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean)
          )
        }
      >
        {saving ? "Сохраняю" : "Сохранить отчёт"}
      </button>
    </div>
  );
}

export function ClarificationCard({ query, onClarify }: { query: QueryResult; onClarify: (value: string, freeform?: string) => void }) {
  const [custom, setCustom] = useState("");
  const clarification = query.clarifications[0];
  return (
    <div className="assistant-card state-card warning">
      <div className="state-title">Уточните запрос</div>
      <p>SQL не выполнялся: confidence ниже порога.</p>
      <div className="reason-list">
        {query.ambiguity_flags.map((flag) => (
          <div key={flag} className="reason warning">
            {flag}
          </div>
        ))}
      </div>
      <div className="option-list">
        {(clarification?.options_json || []).map((option) => (
          <button key={option.value} onClick={() => onClarify(option.value)}>
            <strong>{option.label}</strong>
            <span>{option.description}</span>
          </button>
        ))}
      </div>
      <div className="custom-row">
        <input value={custom} onChange={(event) => setCustom(event.target.value)} placeholder="Например: чистая выручка по городам за апрель" />
        <button className="run-btn small" disabled={!custom.trim()} onClick={() => onClarify("", custom)}>
          Уточнить
        </button>
      </div>
    </div>
  );
}

export function BlockedRequestCard({ query, onUseSafe }: { query: QueryResult; onUseSafe: (text: string) => void }) {
  const alternatives = [
    "Показать водителей с рейтингом ниже 3.5 по городам",
    "Количество водителей с рейтингом ниже 3.5 по городам",
    "Динамика среднего рейтинга водителей за последние 30 дней",
  ];
  return (
    <div className="assistant-card state-card danger">
      <div className="state-title">Запрос заблокирован</div>
      <p>{query.block_reason || "Нарушение guardrails: доступны только read-only SELECT запросы."}</p>
      <div className="reason-list">
        {query.guardrail_logs.map((log) => (
          <div key={log.id} className={`reason ${log.severity}`}>
            <b>{log.check_name}</b>
            <span>{log.message}</span>
          </div>
        ))}
      </div>
      <div className="safe-alternatives">
        <div className="card-label">Возможно, вы имели в виду</div>
        {alternatives.map((item) => (
          <button key={item} onClick={() => onUseSafe(item)}>
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ResultMessage({
  query,
  saving,
  onSave,
  onClarify,
  onUseSafe,
}: {
  query: QueryResult;
  saving: boolean;
  onSave: (title: string, schedule: Record<string, any> | null, recipients: string[]) => void;
  onClarify: (value: string, freeform?: string) => void;
  onUseSafe: (text: string) => void;
}) {
  if (query.status === "clarification_required") {
    return <ClarificationCard query={query} onClarify={onClarify} />;
  }
  if (query.status === "blocked") {
    return <BlockedRequestCard query={query} onUseSafe={onUseSafe} />;
  }
  if (query.status === "autofix_failed" || query.status === "sql_error") {
    return (
      <div className="assistant-card state-card danger">
        <div className="state-title">SQL не выполнен</div>
        <p>{query.error_message || "Auto-fix не смог безопасно исправить SQL."}</p>
      </div>
    );
  }

  return (
    <div className="assistant-card result-stack">
      <div className={`confidence-line ${query.confidence_band}`}>
        <span>{query.confidence_score}% confidence</span>
        <b>{query.confidence_band === "high" ? "Запрос распознан уверенно" : "Есть допущения"}</b>
      </div>
      <div className="ai-summary">
        <div className="card-label">Ответ Толмача</div>
        <p>{query.ai_answer}</p>
      </div>
      <MetricsCards rows={query.result_snapshot} />
      <ResultChart rows={query.result_snapshot} chartSpec={query.chart_spec} />
      <ResultTable rows={query.result_snapshot} />
      <ExplainBlock query={query} />
      <details className="sql-details">
        <summary>Семантический SQL plan</summary>
        <pre>{JSON.stringify(query.sql_plan, null, 2)}</pre>
      </details>
      <details className="sql-details">
        <summary>DB EXPLAIN plan</summary>
        <pre>{JSON.stringify(query.sql_explain_plan, null, 2)}</pre>
      </details>
      <details className="sql-details">
        <summary>Итоговый SQL</summary>
        <code>{query.corrected_sql || query.generated_sql}</code>
      </details>
      <div className="action-strip">
        <button className="ghost-btn" onClick={() => exportCsv(query.result_snapshot)}>
          Экспорт CSV
        </button>
        <button className="ghost-btn" onClick={() => window.print()}>
          Экспорт PNG
        </button>
        <button className="ghost-btn" onClick={() => onUseSafe(query.natural_text)}>
          Переиспользовать запрос
        </button>
      </div>
      <SaveReportPanel query={query} saving={saving} onSave={onSave} />
    </div>
  );
}

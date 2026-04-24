import type { QueryResult } from "../../../shared/types";
import { getAnswerEnvelope } from "../lib/answerUi";
import { getSelectionEntries, getUnderstandingEntries } from "../lib/queryPresentation";

function EntryList({ entries }: { entries: Array<{ label: string; value: string }> }) {
  return (
    <dl className="analytics-definition-list">
      {entries.map((entry) => (
        <div key={entry.label}>
          <dt>{entry.label}</dt>
          <dd>{entry.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function RequestUnderstandingPanel({ query }: { query: QueryResult }) {
  const answer = getAnswerEnvelope(query);
  const semanticTerms = query.semantic_terms
    .slice(0, 8)
    .map((item) => String(item.term || item.mapped_entity_key || ""))
    .filter(Boolean);

  return (
    <section className="answer-side-stack">
      <details className="detail-panel">
        <summary>
          <span>Пояснение</span>
          <small>
            {Math.round(query.confidence_score)}% {query.confidence_band}
          </small>
        </summary>
        <div className="detail-panel-body">
          <EntryList entries={getUnderstandingEntries(query)} />
          {!!semanticTerms.length && (
            <div className="analytics-tags">
              {semanticTerms.map((term) => (
                <span key={term}>{term}</span>
              ))}
            </div>
          )}
        </div>
      </details>

      <details className="detail-panel">
        <summary>
          <span>Выбор ответа</span>
          <small>{answer?.answer_type_label || query.answer_type_key || "Неизвестный тип"}</small>
        </summary>
        <div className="detail-panel-body">
          <EntryList entries={getSelectionEntries(query)} />
          {answer && (
            <div className="detail-callout">
              <strong>Почему выбран этот тип ответа</strong>
              <p>{answer.explanation_why_this_type || answer.answer_type_reason}</p>
            </div>
          )}
        </div>
      </details>

      {answer && (
        <details className="detail-panel">
          <summary>
            <span>Совместимость режимов</span>
            <small>{answer.primary_view_mode}</small>
          </summary>
          <div className="detail-panel-body">
            <div className="compatibility-list">
              <div>
                <span>Основной режим</span>
                <strong>{answer.primary_view_mode}</strong>
              </div>
              <div>
                <span>Доступно сразу</span>
                <strong>{answer.compatibility_info.compatible_view_modes.join(", ") || "Нет"}</strong>
              </div>
              <div>
                <span>Нужен новый запрос</span>
                <strong>{answer.compatibility_info.requery_required_for_views.join(", ") || "Нет"}</strong>
              </div>
            </div>
            <div className="detail-callout">
              <strong>Логика выбора режима на сервере</strong>
              <p>{answer.explainability.view_reasoning}</p>
            </div>
          </div>
        </details>
      )}
    </section>
  );
}

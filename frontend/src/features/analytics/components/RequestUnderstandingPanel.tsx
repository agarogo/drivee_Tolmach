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
      <details className="detail-panel" open>
        <summary>
          <span>Explainability</span>
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
          <span>Selection</span>
          <small>{answer?.answer_type_label || query.answer_type_key || "Unknown type"}</small>
        </summary>
        <div className="detail-panel-body">
          <EntryList entries={getSelectionEntries(query)} />
          {answer && (
            <div className="detail-callout">
              <strong>Why this answer type</strong>
              <p>{answer.explanation_why_this_type || answer.answer_type_reason}</p>
            </div>
          )}
        </div>
      </details>

      {answer && (
        <details className="detail-panel">
          <summary>
            <span>View compatibility</span>
            <small>{answer.primary_view_mode}</small>
          </summary>
          <div className="detail-panel-body">
            <div className="compatibility-list">
              <div>
                <span>Primary view</span>
                <strong>{answer.primary_view_mode}</strong>
              </div>
              <div>
                <span>Compatible now</span>
                <strong>{answer.compatibility_info.compatible_view_modes.join(", ") || "None"}</strong>
              </div>
              <div>
                <span>Needs re-query</span>
                <strong>{answer.compatibility_info.requery_required_for_views.join(", ") || "None"}</strong>
              </div>
            </div>
            <div className="detail-callout">
              <strong>Server-side view reasoning</strong>
              <p>{answer.explainability.view_reasoning}</p>
            </div>
          </div>
        </details>
      )}
    </section>
  );
}

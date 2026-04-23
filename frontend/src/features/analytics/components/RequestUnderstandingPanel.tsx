import type { QueryResult } from "../../../shared/types";
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
  const semanticTerms = query.semantic_terms.slice(0, 8).map((item) => String(item.term || item.mapped_entity_key || ""));

  return (
    <div className="analytics-side-grid">
      <section className="analytics-card">
        <div className="analytics-card-head">
          <div>
            <span className="eyebrow">Understanding</span>
            <h3>Как я понял запрос</h3>
          </div>
          <span className={`confidence-pill ${query.confidence_band}`}>
            {Math.round(query.confidence_score)}% {query.confidence_band}
          </span>
        </div>
        <EntryList entries={getUnderstandingEntries(query)} />
        {!!semanticTerms.length && (
          <div className="analytics-tags">
            {semanticTerms.map((term) => (
              <span key={term}>{term}</span>
            ))}
          </div>
        )}
      </section>
      <section className="analytics-card">
        <div className="analytics-card-head">
          <div>
            <span className="eyebrow">Selection</span>
            <h3>Какие метрики и разрезы выбраны</h3>
          </div>
        </div>
        <EntryList entries={getSelectionEntries(query)} />
      </section>
    </div>
  );
}

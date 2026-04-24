import { useState } from "react";
import type { QueryResult } from "../../../shared/types";
import { getClarificationReasons } from "../lib/queryPresentation";

export function ClarificationPanel({
  query,
  onClarify,
}: {
  query: QueryResult;
  onClarify: (value: string, freeform?: string) => void;
}) {
  const [freeform, setFreeform] = useState("");
  const clarification = query.clarifications[0];
  const reasons = getClarificationReasons(query);

  return (
    <section className="analytics-card analytics-state-card warning">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Уточнение</span>
          <h3>Нужно уточнение перед выполнением</h3>
        </div>
        <span className="state-pill warning">Нужно действие</span>
      </div>
      <p className="analytics-lead">
        {clarification?.question_text || "Backend остановился до SQL execution и просит уточнить метрику, период или разрез."}
      </p>
      <div className="reason-stack">
        {reasons.length ? (
          reasons.map((reason, index) => (
            <article key={`${reason.code}-${index}`} className="reason-card warning">
              <strong>{reason.code}</strong>
              <p>{reason.message}</p>
            </article>
          ))
        ) : (
          <article className="reason-card warning">
            <strong>ambiguous_request</strong>
            <p>Backend вернул состояние clarification_required, но не прислал явные причины.</p>
          </article>
        )}
      </div>
      {!!clarification?.options_json.length && (
        <div className="clarification-options">
          {clarification.options_json.map((option) => (
            <button key={option.value} type="button" className="choice-card" onClick={() => onClarify(option.value)}>
              <strong>{option.label}</strong>
              <span>{option.description}</span>
            </button>
          ))}
        </div>
      )}
      <div className="clarification-freeform">
        <textarea
          value={freeform}
          onChange={(event) => setFreeform(event.target.value)}
          placeholder="Например: выручка по городам за последние 30 дней без отмен"
          rows={3}
        />
        <button
          type="button"
          className="run-btn"
          disabled={!freeform.trim()}
          onClick={() => onClarify("", freeform)}
        >
          Уточнить запрос
        </button>
      </div>
    </section>
  );
}

import type { QueryResult } from "../../../shared/types";
import { getBlockReasons } from "../lib/queryPresentation";

export function BlockedQueryPanel({
  query,
  onReuseQuestion,
}: {
  query: QueryResult;
  onReuseQuestion: (value: string) => void;
}) {
  const blockReasons = getBlockReasons(query);

  return (
    <section className="analytics-card analytics-state-card danger">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Blocked</span>
          <h3>Почему запрос заблокирован</h3>
        </div>
        <span className="state-pill danger">Blocked</span>
      </div>
      <p className="analytics-lead">
        {query.block_reason || "Backend заблокировал запрос на этапе safety checks."}
      </p>
      <div className="reason-stack">
        {blockReasons.map((reason, index) => (
          <article key={`${reason.code}-${index}`} className="reason-card danger">
            <strong>{reason.code}</strong>
            <p>{reason.message}</p>
          </article>
        ))}
      </div>
      {!!query.guardrail_logs.length && (
        <div className="guardrail-log-list">
          {query.guardrail_logs.map((log) => (
            <article key={log.id} className={`guardrail-log ${log.severity}`}>
              <header>
                <strong>{log.check_name}</strong>
                <span>{log.severity}</span>
              </header>
              <p>{log.message}</p>
            </article>
          ))}
        </div>
      )}
      <div className="action-strip">
        <button type="button" className="ghost-btn" onClick={() => onReuseQuestion(query.natural_text)}>
          Вернуть вопрос в composer
        </button>
      </div>
    </section>
  );
}

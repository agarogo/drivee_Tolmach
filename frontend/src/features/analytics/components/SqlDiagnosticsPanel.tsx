import type { QueryResult } from "../../../shared/types";
import { getAnswerEnvelope } from "../lib/answerUi";
import { getCompiledPlan, getPlannerResult, getVisibleSql } from "../lib/queryPresentation";

export function SqlDiagnosticsPanel({ query }: { query: QueryResult }) {
  const answer = getAnswerEnvelope(query);
  const planner = getPlannerResult(query);
  const compiledPlan = getCompiledPlan(query);
  const finalSql = getVisibleSql(query);
  const showSql = Boolean(answer?.requires_sql && answer.sql_visibility.show_sql_panel);

  if (!showSql) return null;

  return (
    <section className="answer-side-stack">
      <details className="detail-panel">
        <summary>
          <span>SQL details</span>
          <small>{answer?.sql_visibility.explain_cost || query.sql_explain_cost || 0} explain cost</small>
        </summary>
        <div className="detail-panel-body detail-panel-body--sql">
          <div className="sql-pane">
            <h4>Planner result</h4>
            <pre>{JSON.stringify(planner, null, 2)}</pre>
          </div>
          <div className="sql-pane">
            <h4>Compiled semantic plan</h4>
            <pre>{JSON.stringify(compiledPlan, null, 2)}</pre>
          </div>
          {!!query.sql_explain_plan && Object.keys(query.sql_explain_plan).length > 0 && (
            <div className="sql-pane">
              <h4>DB EXPLAIN plan</h4>
              <pre>{JSON.stringify(query.sql_explain_plan, null, 2)}</pre>
            </div>
          )}
          <div className="sql-pane">
            <h4>Final SQL</h4>
            <code>{finalSql || "SQL text is not available for this answer."}</code>
          </div>
        </div>
      </details>

      {!!query.guardrail_logs.length && (
        <details className="detail-panel">
          <summary>
            <span>Guardrails</span>
            <small>{query.guardrail_logs.length} log entries</small>
          </summary>
          <div className="detail-panel-body">
            <div className="guardrail-log-list">
              {query.guardrail_logs.map((log) => (
                <article key={log.id} className={`guardrail-log ${log.severity}`}>
                  <header>
                    <strong>{log.check_name}</strong>
                    <span>{log.status}</span>
                  </header>
                  <p>{log.message}</p>
                </article>
              ))}
            </div>
          </div>
        </details>
      )}
    </section>
  );
}

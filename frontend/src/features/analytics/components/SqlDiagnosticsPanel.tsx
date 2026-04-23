import type { QueryResult } from "../../../shared/types";
import { getCompiledPlan, getPlannerResult, getVisibleSql } from "../lib/queryPresentation";

export function SqlDiagnosticsPanel({ query }: { query: QueryResult }) {
  const planner = getPlannerResult(query);
  const compiledPlan = getCompiledPlan(query);
  const finalSql = getVisibleSql(query);

  return (
    <section className="analytics-card">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">SQL Diagnostics</span>
          <h3>SQL plan + final SQL</h3>
        </div>
      </div>
      <div className="sql-panel-grid">
        <div className="sql-pane">
          <h4>Planner result</h4>
          <pre>{JSON.stringify(planner, null, 2)}</pre>
        </div>
        <div className="sql-pane">
          <h4>Compiled semantic plan</h4>
          <pre>{JSON.stringify(compiledPlan, null, 2)}</pre>
        </div>
      </div>
      {!!query.sql_explain_plan && Object.keys(query.sql_explain_plan).length > 0 && (
        <div className="sql-pane">
          <h4>DB EXPLAIN plan</h4>
          <pre>{JSON.stringify(query.sql_explain_plan, null, 2)}</pre>
        </div>
      )}
      <div className="sql-pane">
        <h4>Final SQL</h4>
        <code>{finalSql || "SQL was not rendered because the request stopped before compilation."}</code>
      </div>
    </section>
  );
}

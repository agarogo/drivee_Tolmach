import type { QueryResultRow } from "../../../shared/types";

export function ResultTable({ rows }: { rows: QueryResultRow[] }) {
  if (!rows.length) {
    return <div className="empty-card">No rows were returned by backend for this result.</div>;
  }

  const columns = Object.keys(rows[0]);
  return (
    <div className="table-card-shell">
      <div className="table-card-head">
        <strong>Result snapshot</strong>
        <span>Frontend shows and exports the rows it actually received.</span>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${index}-${columns[0]}`}>
                {columns.map((column) => (
                  <td key={column}>{String(row[column] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

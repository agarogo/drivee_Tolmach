export function ResultTable({ rows }: { rows: Array<Record<string, any>> }) {
  if (!rows.length) return <div className="empty-card">Нет строк для отображения.</div>;
  const columns = Object.keys(rows[0]);
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 80).map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{String(row[column] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

import { useEffect, useState } from "react";
import type { QueryResultRow, TableColumn, TableSortSpec } from "../../../shared/types";
import { exportRowsToCsv } from "../lib/exports";

function comparableValue(value: unknown): number | string {
  if (typeof value === "number") return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  return String(value ?? "").toLowerCase();
}

function sortedRows(rows: QueryResultRow[], sort: TableSortSpec | null): QueryResultRow[] {
  if (!sort?.key) return rows;
  return [...rows].sort((left, right) => {
    const leftValue = comparableValue(left[sort.key]);
    const rightValue = comparableValue(right[sort.key]);
    if (leftValue === rightValue) return 0;
    const direction = sort.direction === "asc" ? 1 : -1;
    return leftValue > rightValue ? direction : -direction;
  });
}

export function ResultTable({
  rows,
  columns,
  title = "Table",
  description = "",
  defaultSort = null,
  initialPageSize = 10,
  showControls = true,
  backendHasMore = false,
  backendPageOffset = 0,
  exportFileName = "result-table.csv",
  emptyMessage = "No rows were returned for this answer.",
}: {
  rows: QueryResultRow[];
  columns: TableColumn[];
  title?: string;
  description?: string;
  defaultSort?: TableSortSpec | null;
  initialPageSize?: number;
  showControls?: boolean;
  backendHasMore?: boolean;
  backendPageOffset?: number;
  exportFileName?: string;
  emptyMessage?: string;
}) {
  const allColumnKeys = columns.map((column) => column.key);
  const [visibleColumnKeys, setVisibleColumnKeys] = useState<string[]>(allColumnKeys);
  const [sort, setSort] = useState<TableSortSpec | null>(defaultSort);
  const [pageSize, setPageSize] = useState(Math.max(1, initialPageSize));
  const [pageIndex, setPageIndex] = useState(0);

  useEffect(() => {
    setVisibleColumnKeys(allColumnKeys);
  }, [allColumnKeys.join("|")]);

  useEffect(() => {
    setSort(defaultSort);
  }, [defaultSort?.key, defaultSort?.direction]);

  useEffect(() => {
    setPageSize(Math.max(1, initialPageSize));
  }, [initialPageSize]);

  useEffect(() => {
    setPageIndex(0);
  }, [rows.length, sort?.key, sort?.direction, pageSize]);

  if (!rows.length) {
    return (
      <section className="answer-card answer-table-card">
        <div className="answer-card-head">
          <div>
            <span className="eyebrow">Table</span>
            <h4>{title}</h4>
          </div>
        </div>
        <div className="empty-card">{emptyMessage}</div>
      </section>
    );
  }

  const effectiveColumns = columns.filter((column) => visibleColumnKeys.includes(column.key));
  const orderedColumns = effectiveColumns.length ? effectiveColumns : columns;
  const visibleRows = sortedRows(rows, sort);
  const totalPages = Math.max(1, Math.ceil(visibleRows.length / pageSize));
  const safePageIndex = Math.min(pageIndex, totalPages - 1);
  const pageRows = visibleRows.slice(safePageIndex * pageSize, safePageIndex * pageSize + pageSize);

  return (
    <section className="answer-card answer-table-card">
      <div className="table-card-head">
        <div>
          <span className="eyebrow">Table View</span>
          <h4>{title}</h4>
          {description && <p className="analytics-note">{description}</p>}
        </div>
        <div className="table-card-meta">
          <span>{rows.length} loaded rows</span>
          {backendHasMore && <span>More rows exist on the backend</span>}
        </div>
      </div>

      {showControls && (
        <div className="table-toolbar">
          <details className="table-toolbar-panel">
            <summary>Columns</summary>
            <div className="table-column-toggles">
              {columns.map((column) => {
                const checked = visibleColumnKeys.includes(column.key);
                return (
                  <label key={column.key} className="table-toggle-chip">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        if (event.target.checked) {
                          setVisibleColumnKeys([...visibleColumnKeys, column.key]);
                          return;
                        }
                        if (visibleColumnKeys.length === 1) return;
                        setVisibleColumnKeys(visibleColumnKeys.filter((key) => key !== column.key));
                      }}
                    />
                    <span>{column.label}</span>
                  </label>
                );
              })}
            </div>
          </details>

          <div className="table-toolbar-group">
            <label className="table-page-size">
              <span>Rows per page</span>
              <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>
                {[5, 10, 25, 50].filter((value, index, array) => array.indexOf(value) === index).map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="ghost-btn compact"
              onClick={() =>
                exportRowsToCsv(
                  visibleRows,
                  exportFileName,
                  orderedColumns.map((column) => column.key),
                )
              }
            >
              Export CSV
            </button>
          </div>
        </div>
      )}

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {orderedColumns.map((column) => {
                const active = sort?.key === column.key;
                return (
                  <th key={column.key}>
                    <button
                      type="button"
                      className={`table-header-button ${active ? "active" : ""}`}
                      onClick={() =>
                        setSort((current) => {
                          if (!current || current.key !== column.key) {
                            return { key: column.key, direction: "asc" };
                          }
                          if (current.direction === "asc") {
                            return { key: column.key, direction: "desc" };
                          }
                          return null;
                        })
                      }
                    >
                      <span>{column.label}</span>
                      <small>{active ? sort?.direction : "sort"}</small>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, index) => (
              <tr key={`${safePageIndex}-${index}-${String(row[orderedColumns[0]?.key || "row"] ?? "row")}`}>
                {orderedColumns.map((column) => (
                  <td key={column.key}>{String(row[column.key] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="table-footer">
        <div>
          Showing rows {safePageIndex * pageSize + 1}-{Math.min((safePageIndex + 1) * pageSize, visibleRows.length)} of{" "}
          {visibleRows.length}
          {backendPageOffset > 0 ? ` | backend offset ${backendPageOffset}` : ""}
        </div>
        <div className="table-pagination">
          <button
            type="button"
            className="ghost-btn compact"
            disabled={safePageIndex === 0}
            onClick={() => setPageIndex(safePageIndex - 1)}
          >
            Previous
          </button>
          <span>
            Page {safePageIndex + 1} / {totalPages}
          </span>
          <button
            type="button"
            className="ghost-btn compact"
            disabled={safePageIndex >= totalPages - 1}
            onClick={() => setPageIndex(safePageIndex + 1)}
          >
            Next
          </button>
        </div>
      </div>

      {backendHasMore && (
        <p className="answer-footnote">
          Backend reported additional rows outside this snapshot. The UI stays honest and does not invent extra pages
          that were not returned in the current answer.
        </p>
      )}
    </section>
  );
}

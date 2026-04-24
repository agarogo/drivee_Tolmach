import type { TableResponse } from "../../../../shared/types";
import { ResultTable } from "../ResultTable";

export function TableAnswer({
  payload,
  summary,
}: {
  payload: TableResponse;
  summary: string;
}) {
  return (
    <section className="answer-card table-answer">
      <div className="answer-card-head">
        <div>
          <span className="eyebrow">Table</span>
          <h3>Record-level answer</h3>
        </div>
        <span className="answer-chip">
          {payload.snapshot_row_count} rows loaded{payload.has_more ? " + more on backend" : ""}
        </span>
      </div>

      <p className="answer-lead">
        {summary || "This answer is intentionally table-first because the backend returned row-level records."}
      </p>

      <ResultTable
        title="Result table"
        description="Column sorting and visibility controls operate on the current loaded snapshot. When backend reports more rows, this UI stays honest and does not fake extra pages."
        rows={payload.rows}
        columns={payload.columns}
        defaultSort={payload.sort}
        initialPageSize={payload.page_size}
        backendHasMore={payload.has_more}
        backendPageOffset={payload.page_offset}
        exportFileName="table-answer.csv"
      />
    </section>
  );
}

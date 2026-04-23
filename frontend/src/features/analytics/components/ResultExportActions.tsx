import { useState } from "react";
import type { RefObject } from "react";
import type { QueryResult } from "../../../shared/types";
import { exportNodeToPdf, exportNodeToPng, exportRowsToCsv } from "../lib/exports";
import { getSnapshotRows } from "../lib/queryPresentation";

export function ResultExportActions({
  query,
  exportRef,
}: {
  query: QueryResult;
  exportRef: RefObject<HTMLElement>;
}) {
  const [exporting, setExporting] = useState<"" | "png" | "pdf">("");
  const rows = getSnapshotRows(query);
  const fileBaseName = `tolmach-${query.id.slice(0, 8)}`;
  const canExportVisual = query.status === "success" && rows.length > 0 && Boolean(exportRef.current);

  async function handlePng() {
    if (!exportRef.current) return;
    setExporting("png");
    try {
      await exportNodeToPng(exportRef.current, `${fileBaseName}.png`);
    } finally {
      setExporting("");
    }
  }

  async function handlePdf() {
    if (!exportRef.current) return;
    setExporting("pdf");
    try {
      await exportNodeToPdf(exportRef.current, `${fileBaseName}.pdf`);
    } finally {
      setExporting("");
    }
  }

  return (
    <section className="analytics-card">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Export</span>
          <h3>Honest export actions</h3>
        </div>
      </div>
      <p className="analytics-note">
        CSV exports the current result snapshot that the frontend actually has. PNG and PDF export the visible
        analytics card instead of opening a print dialog.
      </p>
      <div className="action-strip">
        <button
          type="button"
          className="ghost-btn"
          disabled={!rows.length}
          onClick={() => exportRowsToCsv(rows, `${fileBaseName}-snapshot.csv`)}
        >
          Export CSV snapshot
        </button>
        <button type="button" className="ghost-btn" disabled={!canExportVisual || exporting === "png"} onClick={handlePng}>
          {exporting === "png" ? "Exporting PNG..." : "Export PNG"}
        </button>
        <button type="button" className="ghost-btn" disabled={!canExportVisual || exporting === "pdf"} onClick={handlePdf}>
          {exporting === "pdf" ? "Exporting PDF..." : "Export PDF"}
        </button>
      </div>
    </section>
  );
}

import type { Report } from "../../shared/types";
import { formatDate } from "../../shared/utils/format";
import { ResultChart } from "../analytics/components/ResultChart";
import { ResultTable } from "../analytics/components/ResultTable";

function ReportsList({ reports, selectedId, onSelect }: { reports: Report[]; selectedId?: string; onSelect: (id: string) => void }) {
  return (
    <div className="list-panel">
      {reports.map((report) => (
        <button key={report.id} className={selectedId === report.id ? "list-item active" : "list-item"} onClick={() => onSelect(report.id)}>
          <strong>{report.title}</strong>
          <span>{formatDate(report.updated_at)}</span>
        </button>
      ))}
      {!reports.length && <div className="empty-card">Сохранённых отчётов пока нет.</div>}
    </div>
  );
}

function ReportEditor({ report, onRun }: { report: Report | null; onRun: (id: string) => void }) {
  if (!report) return <div className="empty-card page-empty">Выберите отчёт.</div>;
  return (
    <div className="report-editor">
      <div className="breadcrumbs">Отчёты / {report.title}</div>
      <div className="report-head">
        <div>
          <h1>{report.title}</h1>
          <span className={report.is_active ? "status-pill ok" : "status-pill muted"}>{report.is_active ? "active" : "paused"}</span>
        </div>
        <div className="actions-row">
          <button className="run-btn small" onClick={() => onRun(report.id)}>
            Запустить сейчас
          </button>
          <button className="ghost-btn">Поделиться</button>
          <button className="ghost-btn">Скачать CSV</button>
        </div>
      </div>
      <details className="sql-details open-like" open>
        <summary>SQL</summary>
        <code>{report.generated_sql}</code>
      </details>
      <ResultChart rows={report.result_snapshot} chartSpec={report.chart_spec} />
      <ResultTable rows={report.result_snapshot} />
      <div className="report-side">
        <div className="panel">
          <h3>Параметры</h3>
          <p>{report.natural_text}</p>
        </div>
        <div className="panel">
          <h3>Получатели</h3>
          <p>{report.recipients.join(", ") || "не заданы"}</p>
        </div>
        <div className="panel">
          <h3>Версии</h3>
          {report.versions.slice(0, 5).map((version) => (
            <div key={version.id}>
              v{version.version_number} · {formatDate(version.created_at)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ReportsPage({
  reports,
  currentReport,
  onSelect,
  onRun,
}: {
  reports: Report[];
  currentReport: Report | null;
  onSelect: (id: string) => void;
  onRun: (id: string) => void;
}) {
  return (
    <div className="split-page">
      <ReportsList reports={reports} selectedId={currentReport?.id} onSelect={onSelect} />
      <ReportEditor report={currentReport} onRun={onRun} />
    </div>
  );
}

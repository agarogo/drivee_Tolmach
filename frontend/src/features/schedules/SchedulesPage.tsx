import type { Schedule } from "../../shared/types";
import { formatDate } from "../../shared/utils/format";

export function SchedulesPage({
  schedules,
  selectedId,
  onSelect,
  onToggle,
}: {
  schedules: Schedule[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
}) {
  const selected = schedules.find((item) => item.id === selectedId) || schedules[0];
  return (
    <div className="schedule-layout">
      <div className="schedule-list">
        {schedules.map((schedule) => (
          <button key={schedule.id} className={selected?.id === schedule.id ? "schedule-row active" : "schedule-row"} onClick={() => onSelect(schedule.id)}>
            <strong>{schedule.report_title}</strong>
            <span>{schedule.frequency} · next {formatDate(schedule.next_run_at)}</span>
            <i>{schedule.is_active ? "enabled" : "disabled"}</i>
          </button>
        ))}
        {!schedules.length && <div className="empty-card">Расписаний пока нет.</div>}
      </div>
      <div className="schedule-detail">
        {selected ? (
          <>
            <div className="report-head">
              <div>
                <h1>{selected.report_title}</h1>
                <span>{selected.frequency}</span>
              </div>
              <button className="ghost-btn" onClick={() => onToggle(selected.id)}>
                {selected.is_active ? "Выключить" : "Включить"}
              </button>
            </div>
            <div className="detail-grid">
              <div className="panel">
                <span>Next run</span>
                <strong>{formatDate(selected.next_run_at)}</strong>
              </div>
              <div className="panel">
                <span>Last run</span>
                <strong>{formatDate(selected.last_run_at)}</strong>
              </div>
              <div className="panel">
                <span>Status</span>
                <strong>{selected.is_active ? "active" : "paused"}</strong>
              </div>
              <div className="panel">
                <span>Recipients</span>
                <strong>{selected.recipients.join(", ") || "none"}</strong>
              </div>
            </div>
            <h3>Run history</h3>
            {selected.runs.map((run) => (
              <div key={run.id} className="run-history-row">
                <span>{formatDate(run.ran_at)}</span>
                <b>{run.status}</b>
                <i>{run.rows_returned} rows · {run.execution_ms} ms</i>
              </div>
            ))}
          </>
        ) : (
          <div className="empty-card">Расписание появится после сохранения отчёта.</div>
        )}
      </div>
    </div>
  );
}

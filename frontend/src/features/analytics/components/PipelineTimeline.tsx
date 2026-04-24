import type { PipelineStageView } from "../lib/queryPresentation";

function stageBadge(status: PipelineStageView["status"]) {
  if (status === "done") return "Готово";
  if (status === "active") return "Идёт";
  if (status === "blocked") return "Стоп";
  if (status === "needs_input") return "Нужно уточнение";
  if (status === "skipped") return "Пропущено";
  return "Ожидание";
}

export function PipelineTimeline({
  stages,
  running,
}: {
  stages: PipelineStageView[];
  running: boolean;
}) {
  return (
    <section className="analytics-card">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Пайплайн</span>
          <h3>{running ? "Этапы, которые ожидаются во время выполнения" : "Фактические этапы после ответа backend"}</h3>
        </div>
        <span className={`pipeline-overview ${running ? "pending" : "complete"}`}>
          {running ? "Live progress пока нет" : "События зафиксированы backend"}
        </span>
      </div>
      <div className="pipeline-grid">
        {stages.map((stage) => (
          <article key={stage.id} className={`pipeline-stage ${stage.status}`}>
            <div className="pipeline-stage-head">
              <strong>{stage.label}</strong>
              <span>{stageBadge(stage.status)}</span>
            </div>
            <p>{stage.description}</p>
            <div className="pipeline-stage-detail">{stage.detail}</div>
            <small>{stage.durationMs != null ? `${stage.durationMs} ms` : "duration available after response"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

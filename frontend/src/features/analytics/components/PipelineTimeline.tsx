import type { PipelineStageView } from "../lib/queryPresentation";

function stageBadge(status: PipelineStageView["status"]) {
  if (status === "done") return "Done";
  if (status === "active") return "Waiting";
  if (status === "blocked") return "Blocked";
  if (status === "needs_input") return "Clarify";
  if (status === "skipped") return "Skipped";
  return "Planned";
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
          <span className="eyebrow">Pipeline</span>
          <h3>{running ? "Planned pipeline while backend is running" : "Actual pipeline after backend response"}</h3>
        </div>
        <span className={`pipeline-overview ${running ? "pending" : "complete"}`}>
          {running ? "No live streaming from backend yet" : "Events recorded by backend"}
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

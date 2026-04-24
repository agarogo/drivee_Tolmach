import { buildPipelineStages } from "../lib/queryPresentation";
import { PipelineTimeline } from "./PipelineTimeline";

export function LoadingConfidence({ question }: { question: string }) {
  return (
    <div className="assistant-card loading-confidence">
      <div className="loading-head">
        <span className="loader-ring" />
        <div>
          <strong>Request is running through the backend pipeline</strong>
          <span>{question}</span>
        </div>
      </div>
      <p className="analytics-note">
        The backend does not stream stage-by-stage progress yet, so the timeline below shows the expected pipeline.
        Real stage statuses arrive in the final response together with `query.events`.
      </p>
      <PipelineTimeline stages={buildPipelineStages(null, true)} running />
    </div>
  );
}

import { buildPipelineStages } from "../lib/queryPresentation";
import { PipelineTimeline } from "./PipelineTimeline";

export function LoadingConfidence({ question }: { question: string }) {
  return (
    <div className="assistant-card loading-confidence">
      <div className="loading-head">
        <span className="loader-ring" />
        <div>
          <strong>Запрос отправлен на backend pipeline</strong>
          <span>{question}</span>
        </div>
      </div>
      <p className="analytics-note">
        Backend пока не стримит пошаговый прогресс, поэтому ниже показан ожидаемый pipeline. Фактические статусы появятся после ответа вместе с `query.events`.
      </p>
      <PipelineTimeline stages={buildPipelineStages(null, true)} running />
    </div>
  );
}

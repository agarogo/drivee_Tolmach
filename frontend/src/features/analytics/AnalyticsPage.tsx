import type { QueryResult, Template } from "../../shared/types";
import { LoadingConfidence } from "./components/LoadingConfidence";
import { QueryComposer } from "./components/QueryComposer";
import { QueryExamples } from "./components/QueryExamples";
import { ResultMessage } from "./components/ResultMessage";

export function AnalyticsPage({
  draft,
  running,
  pendingQuestion,
  currentQuery,
  templates,
  saving,
  onDraftChange,
  onRun,
  onSave,
  onClarify,
  onReuseQuestion,
}: {
  draft: string;
  running: boolean;
  pendingQuestion: string;
  currentQuery: QueryResult | null;
  templates: Template[];
  saving: boolean;
  onDraftChange: (value: string) => void;
  onRun: () => void;
  onSave: (title: string, schedule: Record<string, unknown> | null, recipients: string[]) => void;
  onClarify: (value: string, freeform?: string) => void;
  onReuseQuestion: (text: string) => void;
}) {
  const visibleQuestion = pendingQuestion || currentQuery?.natural_text || "";

  return (
    <main className="chat-page">
      <div className="chat-scroll">
        {!visibleQuestion && (
          <section className="chat-welcome">
            <h1>Tolmach Analytics</h1>
            <p>
              Ask in natural language. The UI mirrors the real backend pipeline: parsing, semantic match,
              confidence, planning, guardrails, execution, and visualization.
            </p>
            <QueryExamples templates={templates} onUse={onDraftChange} />
          </section>
        )}

        {visibleQuestion && <div className="chat-bubble user-bubble">{visibleQuestion}</div>}

        {running && pendingQuestion && <LoadingConfidence question={pendingQuestion} />}

        {!running && currentQuery && (
          <ResultMessage
            query={currentQuery}
            saving={saving}
            onSave={onSave}
            onClarify={onClarify}
            onReuseQuestion={onReuseQuestion}
          />
        )}
      </div>

      <div className="composer-dock">
        <QueryComposer value={draft} running={running} onChange={onDraftChange} onRun={onRun} />
      </div>
    </main>
  );
}

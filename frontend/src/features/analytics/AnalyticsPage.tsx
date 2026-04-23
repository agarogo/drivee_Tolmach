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
  onUseSafe,
}: {
  draft: string;
  running: boolean;
  pendingQuestion: string;
  currentQuery: QueryResult | null;
  templates: Template[];
  saving: boolean;
  onDraftChange: (value: string) => void;
  onRun: () => void;
  onSave: (title: string, schedule: Record<string, any> | null, recipients: string[]) => void;
  onClarify: (value: string, freeform?: string) => void;
  onUseSafe: (text: string) => void;
}) {
  const visibleQuestion = pendingQuestion || currentQuery?.natural_text || "";
  return (
    <main className="chat-page">
      <div className="chat-scroll">
        {!visibleQuestion && (
          <section className="chat-welcome">
            <h1>Толмач by Drivee</h1>
            <p>Задайте вопрос обычным языком. Толмач проверит confidence, выполнит только безопасный read-only SQL и вернёт результат.</p>
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
            onUseSafe={onUseSafe}
          />
        )}
      </div>
      <div className="composer-dock">
        <QueryComposer value={draft} running={running} onChange={onDraftChange} onRun={onRun} />
      </div>
    </main>
  );
}

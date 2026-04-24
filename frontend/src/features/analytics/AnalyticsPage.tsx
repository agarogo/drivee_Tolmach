import type { ChatMessage, QueryResult, Template } from "../../shared/types";
import "./stage4-answer-ui.css";
import "./stage5-chat-flow.css";
import { LoadingConfidence } from "./components/LoadingConfidence";
import { QueryComposer } from "./components/QueryComposer";
import { QueryExamples } from "./components/QueryExamples";
import { ResultMessage } from "./components/ResultMessage";

function queryFromMessage(message: ChatMessage): QueryResult | null {
  const payload = message.payload as QueryResult | undefined;
  if (!payload || typeof payload !== "object") return null;
  if (typeof payload.id !== "string" || typeof payload.status !== "string") return null;
  return payload;
}

function AssistantBubble({ message }: { message: ChatMessage }) {
  return <div className="chat-bubble assistant-bubble">{message.content}</div>;
}

function ChatStateCard({
  eyebrow,
  title,
  body,
  actionLabel,
  onAction,
}: {
  eyebrow: string;
  title: string;
  body: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <section className="assistant-card chat-state-card">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h3>{title}</h3>
        </div>
      </div>
      <p className="analytics-lead">{body}</p>
      {actionLabel && onAction && (
        <div className="action-strip">
          <button type="button" className="ghost-btn" onClick={onAction}>
            {actionLabel}
          </button>
        </div>
      )}
    </section>
  );
}

export function AnalyticsPage({
  draft,
  running,
  pendingQuestion,
  currentQuery,
  currentChatId,
  messages,
  templates,
  saving,
  loadingChat,
  chatError,
  restoringChatSelection,
  onDraftChange,
  onRun,
  onSave,
  onClarify,
  onReuseQuestion,
  onCreateChat,
  onRetryCurrentChat,
}: {
  draft: string;
  running: boolean;
  pendingQuestion: string;
  currentQuery: QueryResult | null;
  currentChatId: string | null;
  messages: ChatMessage[];
  templates: Template[];
  saving: boolean;
  loadingChat: boolean;
  chatError: string;
  restoringChatSelection: boolean;
  onDraftChange: (value: string) => void;
  onRun: () => void;
  onSave: (title: string, schedule: Record<string, unknown> | null, recipients: string[]) => void;
  onClarify: (value: string, freeform?: string) => void;
  onReuseQuestion: (text: string) => void;
  onCreateChat: () => void;
  onRetryCurrentChat: () => void;
}) {
  const hasConversation = Boolean(messages.length || pendingQuestion || currentChatId);
  const showWelcome = !hasConversation && !restoringChatSelection && !loadingChat;
  const showSelectedChatEmpty =
    Boolean(currentChatId) &&
    !loadingChat &&
    !chatError &&
    !messages.length &&
    !pendingQuestion &&
    !running;

  return (
    <main className="chat-page">
      <div className="chat-scroll">
        {restoringChatSelection && !messages.length && (
          <ChatStateCard
            eyebrow="Restoring"
            title="Recovering your latest chat"
            body="Tolmach is loading the most relevant chat thread so follow-up questions stay in the same conversation after refresh."
          />
        )}

        {showWelcome && (
          <section className="chat-welcome">
            <h1>Tolmach Analytics</h1>
            <p>
              Ask in natural language. One chat keeps one thread, follow-ups stay attached to the same `chat_id`, and
              each assistant answer arrives with a typed backend render contract.
            </p>
            <div className="action-strip">
              <button type="button" className="run-btn small" onClick={onCreateChat}>
                Start a new chat
              </button>
            </div>
            <QueryExamples templates={templates} onUse={onDraftChange} />
          </section>
        )}

        {loadingChat && currentChatId && !pendingQuestion && (
          <ChatStateCard
            eyebrow="Loading"
            title="Opening chat history"
            body="Messages and prior analytics answers are loading for the selected chat."
          />
        )}

        {Boolean(currentChatId && chatError) && (
          <ChatStateCard
            eyebrow="Chat Error"
            title="Could not load this chat"
            body={chatError}
            actionLabel="Retry chat"
            onAction={onRetryCurrentChat}
          />
        )}

        {showSelectedChatEmpty && (
          <section className="assistant-card chat-empty-thread">
            <div className="analytics-card-head">
              <div>
                <span className="eyebrow">Empty Thread</span>
                <h3>This chat is ready for the first question</h3>
              </div>
            </div>
            <p className="analytics-lead">
              Send a question below or reuse one of the governed templates to start building history in this thread.
            </p>
            <QueryExamples templates={templates} onUse={onDraftChange} />
          </section>
        )}

        {messages.map((message) => {
          if (message.role === "user") {
            return (
              <div key={message.id} className="chat-bubble user-bubble">
                {message.content}
              </div>
            );
          }

          const query = queryFromMessage(message);
          if (query) {
            return (
              <ResultMessage
                key={message.id}
                query={query}
                saving={saving && currentQuery?.id === query.id}
                onSave={onSave}
                onClarify={onClarify}
                onReuseQuestion={onReuseQuestion}
              />
            );
          }

          return <AssistantBubble key={message.id} message={message} />;
        })}

        {pendingQuestion && <div className="chat-bubble user-bubble pending-bubble">{pendingQuestion}</div>}
        {running && pendingQuestion && <LoadingConfidence question={pendingQuestion} />}
      </div>

      <div className="composer-dock">
        <QueryComposer value={draft} running={running} onChange={onDraftChange} onRun={onRun} />
      </div>
    </main>
  );
}

import type { ChatMessage, LlmErrorMessagePayload, QueryResult, Template } from "../../shared/types";
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

function llmErrorFromMessage(message: ChatMessage): LlmErrorMessagePayload | null {
  const payload = message.payload as LlmErrorMessagePayload | undefined;
  if (!payload || typeof payload !== "object") return null;
  if (payload.type !== "llm_error") return null;
  if (payload.error_code !== "llm_timeout" && payload.error_code !== "llm_unavailable") return null;
  return payload;
}

function AssistantBubble({ message }: { message: ChatMessage }) {
  return <div className="chat-bubble assistant-bubble">{message.content}</div>;
}

function ErrorAnswerBubble({
  error,
  question,
  onRetryQuestion,
  onReuseQuestion,
}: {
  error: LlmErrorMessagePayload;
  question: string;
  onRetryQuestion: (text: string) => void;
  onReuseQuestion: (text: string) => void;
}) {
  const title = error.title || "Запрос выполнялся слишком долго";
  const body =
    error.body || "LLM не успела ответить за лимит времени. Проверь GPU/Ollama или упрости запрос.";

  return (
    <section className="assistant-card analytics-state-card danger error-answer-card">
      <div className="analytics-card-head">
        <div>
          <span className="eyebrow">Ошибка LLM</span>
          <h3>{title}</h3>
        </div>
        <span className="state-pill danger">{error.error_code}</span>
      </div>
      <p className="analytics-lead">{body}</p>
      <div className="error-answer-meta">
        <span>Провайдер: {error.provider || "unknown"}</span>
        <span>Модель: {error.model || "unknown"}</span>
        <span>Устройство: {error.device_hint || "unknown"}</span>
      </div>
      <div className="action-strip">
        <button type="button" className="ghost-btn" onClick={() => onRetryQuestion(question)} disabled={!question}>
          Повторить
        </button>
        <button type="button" className="ghost-btn" onClick={() => onReuseQuestion(question)} disabled={!question}>
          Вернуть вопрос в поле ввода
        </button>
      </div>
    </section>
  );
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
  onRetryQuestion,
  onCancelPending,
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
  onRetryQuestion: (text: string) => void;
  onCancelPending: () => void;
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
    <main className={`chat-page ${running ? "running" : ""}`}>
      <div className="chat-scroll">
        {restoringChatSelection && !messages.length && (
          <ChatStateCard
            eyebrow="Восстановление"
            title="Открываем последний чат"
            body="Поднимаем последний тред, чтобы продолжение разговора осталось в том же чате."
          />
        )}

        {showWelcome && (
          <section className="chat-welcome">
            <h1>Толмач Analytics</h1>
            <p>
              Пишите вопрос обычным языком. Один чат хранит один тред, а ответ приходит с типизированным backend
              контрактом без скрытой магии на фронте.
            </p>
            <div className="action-strip">
              <button type="button" className="run-btn small" onClick={onCreateChat}>
                Новый чат
              </button>
            </div>
            <QueryExamples templates={templates} onUse={onDraftChange} />
          </section>
        )}

        {loadingChat && currentChatId && !pendingQuestion && (
          <ChatStateCard
            eyebrow="Загрузка"
            title="Открываем историю чата"
            body="Подгружаем сообщения и прошлые ответы для выбранного треда."
          />
        )}

        {Boolean(currentChatId && chatError) && (
          <ChatStateCard
            eyebrow="Ошибка чата"
            title="Не удалось открыть чат"
            body={chatError}
            actionLabel="Повторить"
            onAction={onRetryCurrentChat}
          />
        )}

        {showSelectedChatEmpty && (
          <section className="assistant-card chat-empty-thread">
            <div className="analytics-card-head">
              <div>
                <span className="eyebrow">Пустой чат</span>
                <h3>Этот чат ждёт первый вопрос</h3>
              </div>
            </div>
            <p className="analytics-lead">
              Отправьте вопрос ниже или возьмите один из шаблонов, чтобы начать историю в этом треде.
            </p>
            <QueryExamples templates={templates} onUse={onDraftChange} />
          </section>
        )}

        <div className="conversation-history">
          {messages.map((message, index) => {
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

            const llmError = llmErrorFromMessage(message);
            if (llmError) {
              const previousMessage = messages[index - 1];
              const question = previousMessage?.role === "user" ? previousMessage.content : "";
              return (
                <ErrorAnswerBubble
                  key={message.id}
                  error={llmError}
                  question={question}
                  onRetryQuestion={onRetryQuestion}
                  onReuseQuestion={onReuseQuestion}
                />
              );
            }

            return <AssistantBubble key={message.id} message={message} />;
          })}
        </div>

        {pendingQuestion && <div className="chat-bubble user-bubble pending-bubble">{pendingQuestion}</div>}
        {running && pendingQuestion && <LoadingConfidence onCancel={onCancelPending} />}
      </div>

      <div className="composer-dock">
        <QueryComposer value={draft} running={running} onChange={onDraftChange} onRun={onRun} />
      </div>
    </main>
  );
}

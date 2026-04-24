import type { ChatHelpResponse } from "../../../../shared/types";

export function ChatHelpAnswer({
  payload,
  onReuseQuestion,
}: {
  payload: ChatHelpResponse;
  onReuseQuestion: (question: string) => void;
}) {
  return (
    <section className="answer-card chat-help-answer">
      <div className="chat-help-thread">
        <div className="chat-help-avatar">AI</div>
        <div className="chat-help-bubble">
          <span className="eyebrow">Semantic Help</span>
          <h3>Help and glossary answer</h3>
          <p>{payload.message}</p>
        </div>
      </div>

      {!!payload.help_cards.length && (
        <div className="help-card-grid">
          {payload.help_cards.map((card) => (
            <article key={`${card.category}-${card.title}`} className="help-card">
              <span>{card.category}</span>
              <strong>{card.title}</strong>
              <p>{card.body}</p>
            </article>
          ))}
        </div>
      )}

      {!!payload.suggested_questions.length && (
        <div className="answer-action-group">
          {payload.suggested_questions.map((question) => (
            <button key={question} type="button" className="ghost-btn compact" onClick={() => onReuseQuestion(question)}>
              {question}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

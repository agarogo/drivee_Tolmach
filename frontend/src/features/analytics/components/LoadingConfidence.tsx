export function LoadingConfidence({ question }: { question: string }) {
  return (
    <div className="assistant-card loading-confidence">
      <div className="loading-head">
        <span className="loader-ring" />
        <div>
          <strong>Проверяю confidence</strong>
          <span>{question}</span>
        </div>
      </div>
      <div className="confidence-meter">
        <span />
      </div>
      <div className="loading-grid">
        <div>
          <b>Интерпретация</b>
          <small>метрика, период, фильтры</small>
        </div>
        <div>
          <b>Semantic layer</b>
          <small>термины и aliases</small>
        </div>
        <div>
          <b>Guardrails</b>
          <small>только read-only</small>
        </div>
      </div>
    </div>
  );
}

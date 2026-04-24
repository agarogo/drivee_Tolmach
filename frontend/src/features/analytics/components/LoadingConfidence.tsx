export function LoadingConfidence({ onCancel }: { onCancel: () => void }) {
  return (
    <div className="assistant-card loading-confidence">
      <div className="loading-head">
        <span className="loader-ring" />
        <div>
          <strong>Подготавливаю ответ...</strong>
          <span>Это может занять до 60-120 секунд при CPU.</span>
        </div>
      </div>
      <p className="analytics-note">Backend пока не стримит прогресс, поэтому показываем только честное состояние ожидания.</p>
      <div className="action-strip">
        <button type="button" className="ghost-btn" onClick={onCancel}>
          Вернуть вопрос в поле ввода
        </button>
      </div>
    </div>
  );
}

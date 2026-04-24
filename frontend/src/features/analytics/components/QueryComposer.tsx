export function QueryComposer({
  value,
  running,
  onChange,
  onRun,
}: {
  value: string;
  running: boolean;
  onChange: (value: string) => void;
  onRun: () => void;
}) {
  return (
    <form
      className="chat-composer"
      onSubmit={(event) => {
        event.preventDefault();
        onRun();
      }}
    >
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onRun();
          }
        }}
        placeholder="Спросите Толмач, например: покажи выручку по 10 главным городам за последние 30 дней"
        rows={1}
      />
      <button className="send-btn" disabled={!value.trim() || running} aria-label="Отправить вопрос">
        {running ? "..." : ">"}
      </button>
    </form>
  );
}

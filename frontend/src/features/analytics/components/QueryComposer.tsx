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
        placeholder="Ask Tolmach, for example: show revenue by top 10 cities for the last 30 days"
        rows={1}
      />
      <button className="send-btn" disabled={!value.trim() || running} aria-label="Send question">
        {running ? "..." : "Send"}
      </button>
    </form>
  );
}

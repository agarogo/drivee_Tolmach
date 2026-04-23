import type { QueryResult, Template } from "../types";

export function Sidebar({
  history,
  templates,
  onNew,
  onPickQuery,
  onUseTemplate,
}: {
  history: QueryResult[];
  templates: Template[];
  onNew: () => void;
  onPickQuery: (query: QueryResult) => void;
  onUseTemplate: (text: string) => void;
}) {
  return (
    <aside className="sidebar">
      <button className="new-btn" onClick={onNew}>
        <span>+</span>
        Новый запрос
      </button>
      <section>
        <div className="sb-section">История</div>
        <div className="sb-list">
          {history.slice(0, 8).map((query) => (
            <button key={query.id} className={`sb-item ${query.status}`} onClick={() => onPickQuery(query)}>
              <span>{query.natural_text}</span>
              <b>{query.confidence_score || 0}%</b>
            </button>
          ))}
          {!history.length && <div className="muted-line padded">Пока нет запросов</div>}
        </div>
      </section>
      <section>
        <div className="sb-section">Быстрые шаблоны</div>
        <div className="sb-list">
          {templates.slice(0, 5).map((template) => (
            <button key={template.id} className="sb-item" onClick={() => onUseTemplate(template.natural_text)}>
              <span>{template.title}</span>
            </button>
          ))}
        </div>
      </section>
      <div className="sb-footer">
        <div>
          <span className="dot ok" /> drivee_prod
        </div>
        <div>Режим: READ-ONLY</div>
        <div>Dataset: orders, cities, drivers, clients</div>
      </div>
    </aside>
  );
}

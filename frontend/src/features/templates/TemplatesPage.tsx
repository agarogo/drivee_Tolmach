import type { Template } from "../../shared/types";

export function TemplatesPage({ templates, onUse }: { templates: Template[]; onUse: (text: string) => void }) {
  const categories = Array.from(new Set(templates.map((item) => item.category)));
  return (
    <div className="page-scroll">
      <div className="page-title">
        <h1>Шаблоны</h1>
        <span>{templates.length} готовых сценариев</span>
      </div>
      {categories.map((category) => (
        <section key={category} className="template-section">
          <h2>{category}</h2>
          <div className="template-grid">
            {templates.filter((item) => item.category === category).map((template) => (
              <div key={template.id} className="template-card">
                <div className="template-preview">{template.chart_type}</div>
                <h3>{template.title}</h3>
                <p>{template.description}</p>
                <code>{template.natural_text}</code>
                <button className="ghost-btn" onClick={() => onUse(template.natural_text)}>
                  Использовать
                </button>
              </div>
            ))}
            <div className="template-card create-card">
              <h3>Создать шаблон</h3>
              <p>Сохраните частый вопрос из результата запроса.</p>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}

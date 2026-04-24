import type { Template } from "../../../shared/types";

export function QueryExamples({ templates, onUse }: { templates: Template[]; onUse: (text: string) => void }) {
  return (
    <div className="examples-grid compact-examples">
      {templates.slice(0, 4).map((template) => (
        <button key={template.id} className="example-card" onClick={() => onUse(template.natural_text)}>
          <span>{template.category}</span>
          <strong>{template.title}</strong>
          <small>{template.description}</small>
        </button>
      ))}
    </div>
  );
}

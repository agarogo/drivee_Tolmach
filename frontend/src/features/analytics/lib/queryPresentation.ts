import type {
  AnswerEnvelope,
  BlockReason,
  JsonObject,
  QueryEvent,
  QueryResult,
  QueryResultRow,
  TableColumn,
} from "../../../shared/types";

export type PipelineStageId =
  | "parsing"
  | "semantic_match"
  | "confidence"
  | "planning"
  | "guardrails"
  | "execution"
  | "visualization";

export type PipelineStageStatus =
  | "planned"
  | "done"
  | "active"
  | "blocked"
  | "needs_input"
  | "skipped";

export type PipelineStageView = {
  id: PipelineStageId;
  label: string;
  description: string;
  status: PipelineStageStatus;
  detail: string;
  durationMs: number | null;
};

const BASE_PIPELINE: Array<{
  id: PipelineStageId;
  label: string;
  description: string;
  stepNames: string[];
}> = [
  {
    id: "parsing",
    label: "Разбор",
    description: "LLM извлекает из вопроса структурированное намерение.",
    stepNames: ["AI intent extraction"],
  },
  {
    id: "semantic_match",
    label: "Семантика",
    description: "Запрос сопоставляется с управляемыми терминами, примерами и semantic catalog.",
    stepNames: ["Semantic layer", "Chat continuity"],
  },
  {
    id: "confidence",
    label: "Уверенность",
    description: "Система оценивает, достаточно ли надёжно распознано намерение.",
    stepNames: ["Confidence scoring"],
  },
  {
    id: "planning",
    label: "План",
    description: "Система собирает план ответа и компилирует разрешённый semantic SQL.",
    stepNames: ["AI SQL plan draft", "Semantic SQL compilation", "AI clarification planning", "Clarification required"],
  },
  {
    id: "guardrails",
    label: "Проверки",
    description: "SQL проходит валидацию, лимиты и EXPLAIN перед выполнением.",
    stepNames: ["Guardrails"],
  },
  {
    id: "execution",
    label: "Выполнение",
    description: "Проверенный запрос запускается в read-only режиме с таймаутами и лимитами.",
    stepNames: ["SQL execution", "Auto-fix attempt 1", "Auto-fix attempt 2", "Auto-fix node"],
  },
  {
    id: "visualization",
    label: "Ответ",
    description: "Backend выбирает тип ответа и допустимые режимы отображения перед рендером результата.",
    stepNames: ["Answer contract selection", "AI answer summary"],
  },
];

function asObject(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as JsonObject;
}

function asArray<T = JsonObject>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function answerEnvelope(query: QueryResult): AnswerEnvelope | null {
  return query.answer || null;
}

function payloadRows(query: QueryResult): QueryResultRow[] {
  const payload = answerEnvelope(query)?.render_payload;
  if (!payload) return query.result_snapshot || [];
  if ("rows" in payload && Array.isArray(payload.rows)) return payload.rows;
  if ("supporting_rows" in payload && Array.isArray(payload.supporting_rows)) return payload.supporting_rows;
  if (payload.kind === "full_report") {
    const tableSection = payload.sections.find((section) => section.kind === "table");
    if (tableSection?.rows?.length) return tableSection.rows;
    const chartSection = payload.sections.find((section) => section.kind === "chart");
    if (chartSection?.rows?.length) return chartSection.rows;
  }
  return query.result_snapshot || [];
}

function payloadColumns(query: QueryResult): TableColumn[] {
  const payload = answerEnvelope(query)?.render_payload;
  if (!payload) return [];
  if ("columns" in payload && Array.isArray(payload.columns)) return payload.columns;
  if (payload.kind === "full_report") {
    const tableSection = payload.sections.find((section) => section.kind === "table");
    if (tableSection?.columns?.length) return tableSection.columns;
    const chartSection = payload.sections.find((section) => section.kind === "chart");
    if (chartSection?.columns?.length) return chartSection.columns;
  }
  return [];
}

export function getCompiledPlan(query: QueryResult): JsonObject {
  const sqlPlan = asObject(query.sql_plan);
  return asObject(sqlPlan.server_compiled_plan) || asObject(sqlPlan.planner_result) || sqlPlan;
}

export function getPlannerResult(query: QueryResult): JsonObject {
  return asObject(asObject(query.sql_plan).planner_result);
}

export function getClarificationReasons(query: QueryResult): BlockReason[] {
  const interpretation = asObject(query.interpretation);
  const resolvedRequest = asObject(query.resolved_request);
  const plan = getCompiledPlan(query);

  return [
    ...asArray<BlockReason>(interpretation.clarification_reasons),
    ...asArray<BlockReason>(resolvedRequest.clarification_reasons),
    ...asArray<BlockReason>(plan.clarification_reasons),
  ].filter((item) => Boolean(item?.message));
}

export function getBlockReasons(query: QueryResult): BlockReason[] {
  if (query.block_reasons?.length) return query.block_reasons;
  const sqlPlan = asObject(query.sql_plan);
  const blockReasons = asArray<BlockReason>(sqlPlan.block_reasons);
  if (blockReasons.length) return blockReasons;
  return query.block_reason ? [{ code: "blocked", message: query.block_reason, details: {} }] : [];
}

function findStageEvents(query: QueryResult, stageId: PipelineStageId): QueryEvent[] {
  const stage = BASE_PIPELINE.find((item) => item.id === stageId);
  if (!stage) return [];
  return query.events.filter((event) => stage.stepNames.includes(event.step_name));
}

function stageStatusFromEvents(query: QueryResult, stageId: PipelineStageId): PipelineStageStatus {
  const events = findStageEvents(query, stageId);
  if (!events.length) {
    if (query.status === "clarification_required") {
      if (stageId === "planning" || stageId === "confidence") return "needs_input";
      if (stageId === "guardrails" || stageId === "execution" || stageId === "visualization") return "skipped";
    }
    if (query.status === "blocked") {
      if (stageId === "guardrails") return "blocked";
      if (stageId === "execution" || stageId === "visualization") return "skipped";
      if (stageId === "planning" && !query.corrected_sql && !query.generated_sql) return "blocked";
    }
    if (query.status === "sql_error" || query.status === "autofix_failed") {
      if (stageId === "execution") return "blocked";
      if (stageId === "visualization") return "skipped";
    }
    return "planned";
  }

  if (events.some((event) => event.status === "needs_input")) return "needs_input";
  if (events.some((event) => event.status === "blocked" || event.status === "error")) return "blocked";
  if (events.some((event) => event.status === "running")) return "active";
  if (events.some((event) => event.status === "ok")) return "done";
  return "planned";
}

function stageDetail(query: QueryResult, stageId: PipelineStageId): string {
  const answer = answerEnvelope(query);
  const explainability = answer?.explainability;
  if (stageId === "parsing") {
    return String(asObject(query.interpretation).source || explainability?.source || "Источник распознавания появится после завершения запроса.");
  }
  if (stageId === "semantic_match") {
    const semanticTerms = (explainability?.semantic_terms || []).slice(0, 4);
    return semanticTerms.length ? `Совпавшие термины: ${semanticTerms.join(", ")}` : "Совпавшие термины не записаны.";
  }
  if (stageId === "confidence") {
    return `${Math.round(query.confidence_score)}% уверенности (${query.confidence_band})`;
  }
  if (stageId === "planning") {
    const metric = explainability?.metric || String(getCompiledPlan(query).metric_label || getCompiledPlan(query).metric || "не выбрана");
    return `Метрика: ${metric}`;
  }
  if (stageId === "guardrails") {
    if (query.status === "blocked") {
      const firstReason = getBlockReasons(query)[0];
      return firstReason?.message || query.block_reason || "Запрос остановлен защитными проверками.";
    }
    return answer?.sql_visibility.explain_cost
      ? `EXPLAIN cost: ${answer.sql_visibility.explain_cost}`
      : query.sql_explain_cost
        ? `EXPLAIN cost: ${query.sql_explain_cost}`
        : "Логи guardrails появятся после валидации.";
  }
  if (stageId === "execution") {
    if (query.status === "success") return `${query.rows_returned} строк за ${query.execution_ms} мс`;
    if (query.error_message) return query.error_message;
    return "Выполнение не началось.";
  }
  if (stageId === "visualization") {
    if (!answer) return "Активен упрощённый fallback-рендер.";
    return `${answer.answer_type_label} через режим ${answer.primary_view_mode}.`;
  }
  return "";
}

function stageDuration(query: QueryResult, stageId: PipelineStageId): number | null {
  const events = findStageEvents(query, stageId);
  if (!events.length) return null;
  return events.reduce((total, event) => total + (event.duration_ms || 0), 0);
}

export function buildPipelineStages(query: QueryResult | null, running: boolean): PipelineStageView[] {
  if (!query) {
    return BASE_PIPELINE.map((stage, index) => ({
      id: stage.id,
      label: stage.label,
      description: stage.description,
      status: running ? (index === 0 ? "active" : "planned") : "planned",
      detail: running ? "Настоящие события этапов появятся только после ответа backend." : stage.description,
      durationMs: null,
    }));
  }

  return BASE_PIPELINE.map((stage) => ({
    id: stage.id,
    label: stage.label,
    description: stage.description,
    status: stageStatusFromEvents(query, stage.id),
    detail: stageDetail(query, stage.id),
    durationMs: stageDuration(query, stage.id),
  }));
}

export function getUnderstandingEntries(query: QueryResult): Array<{ label: string; value: string }> {
  const answer = answerEnvelope(query);
  const explainability = answer?.explainability;
  const resolved = asObject(query.resolved_request);
  const interpretation = asObject(query.interpretation);
  const filters = explainability?.filters || asObject(resolved.filters || interpretation.filters);
  const dimensions = explainability?.dimensions || asArray<string>(resolved.dimensions || interpretation.dimensions);
  const period = explainability?.period || String(asObject(resolved.period || interpretation.date_range).label || "Не указан");

  return [
    { label: "Вопрос", value: query.natural_text },
    { label: "Метрика", value: explainability?.metric || String(resolved.metric || interpretation.metric || "Не определена") },
    { label: "Разрез", value: dimensions.length ? dimensions.join(", ") : "Без разреза" },
    { label: "Период", value: period },
    { label: "Фильтры", value: Object.keys(filters).length ? JSON.stringify(filters) : "Явных фильтров нет" },
    { label: "Источник intent", value: explainability?.source || String(interpretation.source || "unknown") },
    { label: "LLM-провайдер", value: query.llm_provider || query.provider || "не использовался" },
    { label: "LLM использовалась", value: query.llm_used ? "Да" : "Нет" },
    { label: "Fallback использован", value: query.fallback_used ? "Да" : "Нет" },
    { label: "Retrieval использован", value: query.retrieval_used ? "Да" : "Нет" },
  ];
}

export function getSelectionEntries(query: QueryResult): Array<{ label: string; value: string }> {
  const answer = answerEnvelope(query);
  const explainability = answer?.explainability;
  const plan = getCompiledPlan(query);
  const planner = getPlannerResult(query);
  const dimensions = explainability?.dimensions || asArray<string>(plan.dimensions);
  const dimensionLabels = explainability?.dimension_labels || asObject(plan.dimension_labels);
  const sourceTables = asArray<string>(asObject(query.sql_plan).source_tables);

  return [
    { label: "Тип ответа", value: answer?.answer_type_label || query.answer_type_key || "unknown" },
    { label: "Основной режим", value: answer?.primary_view_mode || query.primary_view_mode || "table" },
    { label: "Метрика", value: explainability?.metric || String(plan.metric_label || plan.metric || "Не выбрана") },
    { label: "Гранулярность", value: answer?.result_grain || String(planner.grain || "unknown") },
    {
      label: "Измерения",
      value: dimensions.length ? dimensions.map((key) => String(dimensionLabels[key] || key)).join(", ") : "Без измерений",
    },
    { label: "Таблицы-источники", value: sourceTables.length ? sourceTables.join(", ") : String(plan.source_table || "unknown") },
  ];
}

export function getVisibleSql(query: QueryResult): string {
  return query.answer?.sql_visibility.sql || query.corrected_sql || query.generated_sql || "";
}

export function getSnapshotRows(query: QueryResult): QueryResultRow[] {
  return payloadRows(query);
}

export function getSnapshotColumns(query: QueryResult): TableColumn[] {
  const columns = payloadColumns(query);
  if (columns.length) return columns;
  const rows = payloadRows(query);
  const orderedKeys: string[] = [];
  const seen = new Set<string>();
  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!seen.has(key)) {
        seen.add(key);
        orderedKeys.push(key);
      }
    });
  });
  return orderedKeys.map((key) => ({ key, label: key.replace(/_/g, " "), data_type: "unknown" }));
}

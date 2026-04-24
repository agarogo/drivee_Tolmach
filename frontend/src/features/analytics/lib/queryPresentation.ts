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
    label: "Parsing",
    description: "LLM extracts structured intent from the question.",
    stepNames: ["AI intent extraction"],
  },
  {
    id: "semantic_match",
    label: "Semantic Match",
    description: "The request is matched against governed terms, examples, and semantic catalog.",
    stepNames: ["Semantic layer", "Chat continuity"],
  },
  {
    id: "confidence",
    label: "Confidence",
    description: "The system estimates whether the interpretation is strong enough to continue.",
    stepNames: ["Confidence scoring"],
  },
  {
    id: "planning",
    label: "Planning",
    description: "The system drafts the plan and compiles approved semantic SQL.",
    stepNames: ["AI SQL plan draft", "Semantic SQL compilation", "AI clarification planning", "Clarification required"],
  },
  {
    id: "guardrails",
    label: "Guardrails",
    description: "SQL is validated, capped, and checked with EXPLAIN before execution.",
    stepNames: ["Guardrails"],
  },
  {
    id: "execution",
    label: "Execution",
    description: "The validated query runs in read-only mode with timeouts and row caps.",
    stepNames: ["SQL execution", "Auto-fix attempt 1", "Auto-fix attempt 2", "Auto-fix node"],
  },
  {
    id: "visualization",
    label: "Visualization",
    description: "Backend selects answer_type and compatible view modes before the UI renders the result.",
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
    return String(asObject(query.interpretation).source || explainability?.source || "Structured intent recorded after the run finishes.");
  }
  if (stageId === "semantic_match") {
    const semanticTerms = (explainability?.semantic_terms || []).slice(0, 4);
    return semanticTerms.length ? `Matched terms: ${semanticTerms.join(", ")}` : "No semantic terms recorded.";
  }
  if (stageId === "confidence") {
    return `${Math.round(query.confidence_score)}% confidence (${query.confidence_band})`;
  }
  if (stageId === "planning") {
    const metric = explainability?.metric || String(getCompiledPlan(query).metric_label || getCompiledPlan(query).metric || "not selected");
    return `Metric: ${metric}`;
  }
  if (stageId === "guardrails") {
    if (query.status === "blocked") {
      const firstReason = getBlockReasons(query)[0];
      return firstReason?.message || query.block_reason || "Blocked by safety checks.";
    }
    return answer?.sql_visibility.explain_cost
      ? `EXPLAIN cost: ${answer.sql_visibility.explain_cost}`
      : query.sql_explain_cost
        ? `EXPLAIN cost: ${query.sql_explain_cost}`
        : "Guardrails log available after validation.";
  }
  if (stageId === "execution") {
    if (query.status === "success") return `${query.rows_returned} rows in ${query.execution_ms} ms`;
    if (query.error_message) return query.error_message;
    return "Execution did not start.";
  }
  if (stageId === "visualization") {
    if (!answer) return "Legacy visualization fallback is active.";
    return `${answer.answer_type_label} via ${answer.primary_view_mode} view.`;
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
      detail: running ? "Backend will return real stage events when the query finishes." : stage.description,
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
  const period = explainability?.period || String(asObject(resolved.period || interpretation.date_range).label || "Not specified");

  return [
    { label: "Question", value: query.natural_text },
    { label: "Metric", value: explainability?.metric || String(resolved.metric || interpretation.metric || "Not resolved") },
    { label: "Breakdown", value: dimensions.length ? dimensions.join(", ") : "No breakdown" },
    { label: "Period", value: period },
    { label: "Filters", value: Object.keys(filters).length ? JSON.stringify(filters) : "No explicit filters" },
    { label: "Intent source", value: explainability?.source || String(interpretation.source || "unknown") },
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
    { label: "Answer type", value: answer?.answer_type_label || query.answer_type_key || "unknown" },
    { label: "Primary view", value: answer?.primary_view_mode || query.primary_view_mode || "table" },
    { label: "Metric", value: explainability?.metric || String(plan.metric_label || plan.metric || "Not selected") },
    { label: "Grain", value: answer?.result_grain || String(planner.grain || "unknown") },
    {
      label: "Dimensions",
      value: dimensions.length ? dimensions.map((key) => String(dimensionLabels[key] || key)).join(", ") : "No dimensions",
    },
    { label: "Source tables", value: sourceTables.length ? sourceTables.join(", ") : String(plan.source_table || "unknown") },
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

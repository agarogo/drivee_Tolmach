import type {
  BlockReason,
  JsonObject,
  QueryChartSeries,
  QueryChartSpec,
  QueryEvent,
  QueryResult,
  QueryResultRow,
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

export type SemanticVisualizationModel = {
  chartType: string;
  xKey: string | null;
  series: QueryChartSeries[];
  reason: string;
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
    stepNames: ["Semantic layer"],
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
    description: "Result rows are summarized and rendered as chart/table using the semantic plan.",
    stepNames: ["Chart selection", "AI answer summary"],
  },
];

function asObject(value: unknown): JsonObject {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as JsonObject;
}

function asArray<T = JsonObject>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export function getCompiledPlan(query: QueryResult): JsonObject {
  const sqlPlan = asObject(query.sql_plan);
  return (
    asObject(sqlPlan.server_compiled_plan) ||
    asObject(sqlPlan.planner_result) ||
    sqlPlan
  );
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
  return query.block_reason
    ? [{ code: "blocked", message: query.block_reason, details: {} }]
    : [];
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
  if (stageId === "parsing") {
    return String(asObject(query.interpretation).source || "Structured intent recorded after the run finishes.");
  }
  if (stageId === "semantic_match") {
    const semanticTerms = query.semantic_terms.slice(0, 4).map((item) => String(item.term || ""));
    return semanticTerms.length ? `Matched terms: ${semanticTerms.join(", ")}` : "No semantic terms recorded.";
  }
  if (stageId === "confidence") {
    return `${Math.round(query.confidence_score)}% confidence (${query.confidence_band})`;
  }
  if (stageId === "planning") {
    const plan = getCompiledPlan(query);
    const metric = String(plan.metric_label || plan.metric || asObject(query.resolved_request).metric || "not selected");
    return `Metric: ${metric}`;
  }
  if (stageId === "guardrails") {
    if (query.status === "blocked") {
      const firstReason = getBlockReasons(query)[0];
      return firstReason?.message || query.block_reason || "Blocked by safety checks.";
    }
    return query.sql_explain_cost ? `EXPLAIN cost: ${query.sql_explain_cost}` : "Guardrails log available after validation.";
  }
  if (stageId === "execution") {
    if (query.status === "success") return `${query.rows_returned} rows in ${query.execution_ms} ms`;
    if (query.error_message) return query.error_message;
    return "Execution did not start.";
  }
  if (stageId === "visualization") {
    const model = deriveSemanticVisualization(query);
    return model.chartType === "table_only"
      ? "Table view only."
      : `${model.chartType} chart selected from the semantic plan.`;
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
      detail: running
        ? "Backend will return real stage events when the query finishes."
        : stage.description,
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
  const resolved = asObject(query.resolved_request);
  const interpretation = asObject(query.interpretation);
  const filters = asObject(resolved.filters || interpretation.filters);
  const dimensions = asArray<string>(resolved.dimensions || interpretation.dimensions);
  const period = asObject(resolved.period || interpretation.date_range);

  return [
    {
      label: "Question",
      value: query.natural_text,
    },
    {
      label: "Metric",
      value: String(resolved.metric || interpretation.metric || "Not resolved"),
    },
    {
      label: "Breakdown",
      value: dimensions.length ? dimensions.join(", ") : "No breakdown",
    },
    {
      label: "Period",
      value: String(period.label || period.kind || "Not specified"),
    },
    {
      label: "Filters",
      value: Object.keys(filters).length ? JSON.stringify(filters) : "No explicit filters",
    },
    {
      label: "Intent source",
      value: String(interpretation.source || "unknown"),
    },
  ];
}

export function getSelectionEntries(query: QueryResult): Array<{ label: string; value: string }> {
  const plan = getCompiledPlan(query);
  const planner = getPlannerResult(query);
  const dimensions = asArray<string>(plan.dimensions);
  const dimensionLabels = asObject(plan.dimension_labels);
  const filters = asArray<string>(plan.filters);
  const sourceTables = asArray<string>(asObject(query.sql_plan).source_tables);

  return [
    {
      label: "Metric",
      value: String(plan.metric_label || plan.metric || "Not selected"),
    },
    {
      label: "Grain",
      value: String(planner.grain || "unknown"),
    },
    {
      label: "Dimensions",
      value: dimensions.length
        ? dimensions.map((key) => String(dimensionLabels[key] || key)).join(", ")
        : "No dimensions",
    },
    {
      label: "Filters",
      value: filters.length ? filters.join("; ") : "No compiled filters",
    },
    {
      label: "Source tables",
      value: sourceTables.length ? sourceTables.join(", ") : String(plan.source_table || "unknown"),
    },
    {
      label: "Semantic chart",
      value: String(plan.chart_type || query.chart_type || "table_only"),
    },
  ];
}

export function deriveSemanticVisualization(query: QueryResult): SemanticVisualizationModel {
  const plan = getCompiledPlan(query);
  const chartType = String(plan.chart_type || query.chart_type || "table_only");
  const dimensions = asArray<string>(plan.dimensions);
  const metricKey = String(plan.metric || asObject(query.resolved_request).metric || "");
  const metricLabel = String(plan.metric_label || metricKey || "value");
  const chartSpec = (query.chart_spec || {}) as QueryChartSpec;
  const semanticXKey = dimensions[0] || null;
  const xKey = semanticXKey || chartSpec.x || null;
  const series = metricKey
    ? [{ key: metricKey, name: metricLabel }]
    : Array.isArray(chartSpec.series)
      ? chartSpec.series
      : [];

  return {
    chartType,
    xKey,
    series,
    reason: chartType === "table_only"
      ? "Semantic plan says that a table is safer than a chart for this result."
      : "Visualization uses chart type selected by the semantic plan.",
  };
}

export function getVisibleSql(query: QueryResult): string {
  return query.corrected_sql || query.generated_sql || "";
}

export function getSummaryText(query: QueryResult): string {
  if (query.status !== "success") return "";
  return query.ai_answer || "";
}

export function getSnapshotRows(query: QueryResult): QueryResultRow[] {
  return query.result_snapshot || [];
}

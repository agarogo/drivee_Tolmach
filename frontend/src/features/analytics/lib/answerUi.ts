import type {
  AnswerEnvelope,
  AnswerRenderPayload,
  QueryResult,
  QueryResultRow,
  TableColumn,
  ViewMode,
} from "../../../shared/types";

export type AnalyticsViewMode = Extract<ViewMode, "number" | "chart" | "table" | "report">;
export type ViewSwitchState = "active" | "ready" | "requery" | "unsupported";

export const ANALYTICS_VIEW_ORDER: AnalyticsViewMode[] = ["number", "chart", "table", "report"];

export function getAnswerEnvelope(query: QueryResult): AnswerEnvelope | null {
  return query.answer || null;
}

export function getAnswerPayload(query: QueryResult): AnswerRenderPayload | null {
  return getAnswerEnvelope(query)?.render_payload || null;
}

export function formatMetricValue(
  value: number | string | null | undefined,
  options: {
    compact?: boolean;
    maximumFractionDigits?: number;
  } = {},
): string {
  if (value === null || value === undefined || value === "") return "No data";
  if (typeof value === "number") {
    const formatter = new Intl.NumberFormat("en-US", {
      notation: options.compact ? "compact" : "standard",
      maximumFractionDigits: options.maximumFractionDigits ?? (Math.abs(value) >= 100 ? 0 : 2),
    });
    return formatter.format(value);
  }
  return String(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "No data";
  return `${value.toFixed(2)}%`;
}

export function formatSignedDelta(value: number | null | undefined): string {
  if (value === null || value === undefined) return "No delta";
  return `${value >= 0 ? "+" : ""}${value.toFixed(Math.abs(value) >= 100 ? 0 : 2)}`;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Freshness timestamp unavailable";
  return new Date(value).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function answerRows(payload: AnswerRenderPayload | null): QueryResultRow[] {
  if (!payload) return [];
  if ("rows" in payload && Array.isArray(payload.rows)) return payload.rows;
  if ("supporting_rows" in payload && Array.isArray(payload.supporting_rows)) return payload.supporting_rows;
  if (payload.kind === "full_report") {
    const firstTable = payload.sections.find((section) => section.kind === "table");
    if (firstTable?.rows?.length) return firstTable.rows;
    const firstChart = payload.sections.find((section) => section.kind === "chart");
    if (firstChart?.rows?.length) return firstChart.rows;
  }
  return [];
}

export function answerColumns(payload: AnswerRenderPayload | null): TableColumn[] {
  if (!payload) return [];
  if ("columns" in payload && Array.isArray(payload.columns)) return payload.columns;
  if (payload.kind === "full_report") {
    const firstTable = payload.sections.find((section) => section.kind === "table");
    if (firstTable?.columns?.length) return firstTable.columns;
    const firstChart = payload.sections.find((section) => section.kind === "chart");
    if (firstChart?.columns?.length) return firstChart.columns;
  }
  return [];
}

export function modeState(
  answer: AnswerEnvelope | null,
  mode: AnalyticsViewMode,
  activeView: AnalyticsViewMode,
): ViewSwitchState {
  if (!answer) return "unsupported";
  if (mode === activeView) return "active";
  if (answer.compatibility_info.compatible_view_modes.includes(mode)) return "ready";
  if (answer.compatibility_info.requery_required_for_views.includes(mode)) return "requery";
  return "unsupported";
}

export function modeCaption(state: ViewSwitchState): string {
  if (state === "active") return "Current";
  if (state === "ready") return "Switch now";
  if (state === "requery") return "Needs re-query";
  return "Unavailable";
}

export function modeDescription(answer: AnswerEnvelope | null, mode: AnalyticsViewMode): string {
  if (!answer) return "No typed answer payload is available.";
  const option = answer.switch_options.find((item) => item.view_mode === mode);
  if (option?.reason) return option.reason;
  if (answer.compatibility_info.compatible_view_modes.includes(mode)) {
    return "This mode can be rendered from the current answer payload.";
  }
  if (answer.compatibility_info.requery_required_for_views.includes(mode)) {
    return "This view would require a new backend answer type or a new SQL strategy.";
  }
  return "This mode is not available for the current answer.";
}

export function nextViewNotice(answer: AnswerEnvelope | null, mode: AnalyticsViewMode): string {
  if (!answer) return "No typed answer payload is available for switching.";
  return modeDescription(answer, mode);
}

export function tableColumnsFromRows(rows: QueryResultRow[]): TableColumn[] {
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
  return orderedKeys.map((key) => ({
    key,
    label: key.replace(/_/g, " ").replace(/\b\w/g, (value) => value.toUpperCase()),
    data_type: "unknown",
  }));
}

export function statusTone(value: number | null | undefined): "positive" | "negative" | "neutral" {
  if (value === null || value === undefined) return "neutral";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

export function visibleModes(answer: AnswerEnvelope | null): AnalyticsViewMode[] {
  if (!answer || answer.answer_type_key === "chat_help") return [];
  return ANALYTICS_VIEW_ORDER;
}

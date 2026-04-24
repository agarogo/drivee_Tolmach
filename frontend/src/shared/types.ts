export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonObject
  | JsonValue[];

export type JsonObject = {
  [key: string]: JsonValue;
};

export type User = {
  id: string;
  email: string;
  role: "user" | "admin";
  full_name: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type RegisterPayload = {
  email: string;
  password: string;
  full_name: string;
  role?: "user";
};

export type AppView = "analytics" | "reports" | "templates" | "schedules" | "profile";

export type QueryStatus =
  | "idle"
  | "running"
  | "clarification_required"
  | "blocked"
  | "success"
  | "sql_error"
  | "autofix_running"
  | "autofix_failed"
  | "clarified";

export type ConfidenceBand = "high" | "medium" | "low";
export type ViewMode = "chat" | "number" | "chart" | "table" | "report";
export type ResultGrain = "chat" | "kpi" | "category" | "time_series" | "distribution" | "record" | "report" | "unknown";

export type QueryEvent = {
  id: string;
  step_name: string;
  status: string;
  payload_json: JsonObject;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
};

export type GuardrailLog = {
  id: string;
  check_name: string;
  status: string;
  severity: string;
  message: string;
  details_json: JsonObject;
  created_at: string;
};

export type ClarificationOption = {
  label: string;
  value: string;
  description: string;
};

export type Clarification = {
  id: string;
  question_text: string;
  options_json: ClarificationOption[];
  chosen_option: string;
  freeform_answer: string;
  created_at: string;
  answered_at: string | null;
};

export type BlockReason = {
  code: string;
  message: string;
  details: JsonObject;
};

export type QueryChartSeries = {
  key: string;
  name: string;
};

export type QueryChartSpec = {
  type?: string;
  x?: string;
  series?: QueryChartSeries[];
  [key: string]: JsonValue | QueryChartSeries[] | undefined;
};

export type QueryResultRow = Record<string, string | number | boolean | null>;

export type TableColumn = {
  key: string;
  label: string;
  data_type: string;
};

export type HelpCard = {
  title: string;
  body: string;
  category: string;
};

export type ComparisonItem = {
  rank: number;
  label: string;
  value: number | string | null;
  share_pct: number | null;
  is_other: boolean;
};

export type TrendPoint = {
  label: string;
  value: number | string | null;
};

export type TrendExtrema = {
  label: string;
  value: number | string | null;
};

export type ChatHelpResponse = {
  kind: "chat_help";
  message: string;
  help_cards: HelpCard[];
  suggested_questions: string[];
};

export type SingleValueResponse = {
  kind: "single_value";
  metric_key: string;
  metric_label: string;
  current_value: number | string | null;
  previous_value: number | null;
  delta_abs: number | null;
  delta_pct: number | null;
  freshness_timestamp: string | null;
  unit_label: string;
  context: string;
  availability_note: string;
  columns: TableColumn[];
  supporting_rows: QueryResultRow[];
};

export type ComparisonResponse = {
  kind: "comparison_top";
  metric_key: string;
  metric_label: string;
  dimension_key: string;
  dimension_label: string;
  items: ComparisonItem[];
  columns: TableColumn[];
  rows: QueryResultRow[];
  insight: string;
};

export type TrendResponse = {
  kind: "trend";
  metric_key: string;
  metric_label: string;
  time_key: string;
  points: TrendPoint[];
  peak: TrendExtrema;
  low: TrendExtrema;
  columns: TableColumn[];
  rows: QueryResultRow[];
  insight: string;
};

export type DistributionResponse = {
  kind: "distribution";
  metric_key: string;
  metric_label: string;
  dimension_key: string;
  dimension_label: string;
  items: ComparisonItem[];
  total_value: number;
  integrity_pct: number;
  other_bucket_applied: boolean;
  columns: TableColumn[];
  rows: QueryResultRow[];
  insight: string;
};

export type TableSortSpec = {
  key: string;
  direction: "asc" | "desc";
};

export type TableResponse = {
  kind: "table";
  columns: TableColumn[];
  rows: QueryResultRow[];
  snapshot_row_count: number;
  total_row_count: number | null;
  pagination_mode: string;
  page_size: number;
  page_offset: number;
  has_more: boolean;
  sort: TableSortSpec;
  export_formats: string[];
};

export type FullReportKpi = {
  key: string;
  label: string;
  value: number | string | null;
  unit_label: string;
};

export type FullReportResponse = {
  kind: "full_report";
  title: string;
  summary: string;
  kpis: FullReportKpi[];
  sections: FullReportSection[];
  insights: string[];
  actionability: FullReportActionability;
  rerun_supported: boolean;
  save_supported: boolean;
};

export type FullReportInsightSection = {
  kind: "insight";
  title: string;
  body: string;
};

export type FullReportChartSection = {
  kind: "chart";
  title: string;
  chart_type: string;
  metric_key: string;
  metric_label: string;
  x_key: string;
  columns: TableColumn[];
  rows: QueryResultRow[];
};

export type FullReportTableSection = {
  kind: "table";
  title: string;
  columns: TableColumn[];
  rows: QueryResultRow[];
};

export type FullReportSection =
  | FullReportInsightSection
  | FullReportChartSection
  | FullReportTableSection;

export type FullReportActionability = {
  rerun_supported: boolean;
  save_supported: boolean;
  schedule_supported: boolean;
  export_formats: string[];
};

export type AnswerRenderPayload =
  | ChatHelpResponse
  | SingleValueResponse
  | ComparisonResponse
  | TrendResponse
  | DistributionResponse
  | TableResponse
  | FullReportResponse;

export type AnswerMetadata = {
  query_id: string | null;
  chat_id: string | null;
  status: string;
  rows_returned: number;
  execution_ms: number;
  created_at: string | null;
  updated_at: string | null;
};

export type AnswerExplainability = {
  metric: string;
  dimensions: string[];
  dimension_labels: Record<string, string>;
  period: string;
  filters: JsonObject;
  grouping: string[];
  sorting: string;
  limit: number;
  source: string;
  provider_confidence: number;
  fallback_used: boolean;
  semantic_terms: string[];
  sql_reasoning: string[];
  answer_type_reasoning: string;
  view_reasoning: string;
};

export type SqlVisibility = {
  show_sql_panel: boolean;
  sql: string;
  explain_cost: number;
  explain_plan_available: boolean;
};

export type ViewSwitchOption = {
  view_mode: ViewMode;
  label: string;
  can_switch_without_requery: boolean;
  requery_required: boolean;
  reason: string;
};

export type CompatibilityInfo = {
  compatible_view_modes: ViewMode[];
  can_switch_without_requery: boolean;
  requery_required_for_views: ViewMode[];
};

export type AnswerEnvelope = {
  answer_type: number;
  answer_type_key: "chat_help" | "single_value" | "comparison_top" | "trend" | "distribution" | "table" | "full_report";
  answer_type_label: string;
  answer_type_reason: string;
  primary_view_mode: ViewMode;
  available_view_modes: ViewMode[];
  rerender_policy: string;
  requires_sql: boolean;
  result_grain: ResultGrain;
  can_switch_without_requery: boolean;
  explanation_why_this_type: string;
  metadata: AnswerMetadata;
  explainability: AnswerExplainability;
  sql_visibility: SqlVisibility;
  render_payload: AnswerRenderPayload | null;
  switch_options: ViewSwitchOption[];
  compatibility_info: CompatibilityInfo;
};

export type QueryResult = {
  id: string;
  chat_id?: string | null;
  natural_text: string;
  generated_sql: string;
  corrected_sql: string;
  confidence_score: number;
  confidence_band: ConfidenceBand;
  status: QueryStatus;
  block_reason: string;
  block_reasons: BlockReason[];
  interpretation: JsonObject;
  resolved_request: JsonObject;
  semantic_terms: JsonObject[];
  sql_plan: JsonObject;
  sql_explain_plan: JsonObject;
  sql_explain_cost: number;
  confidence_reasons: string[];
  ambiguity_flags: string[];
  rows_returned: number;
  execution_ms: number;
  answer_type_code: number;
  answer_type_key: AnswerEnvelope["answer_type_key"];
  primary_view_mode: ViewMode;
  answer: AnswerEnvelope | null;
  chart_type: string;
  chart_spec: QueryChartSpec;
  result_snapshot: QueryResultRow[];
  ai_answer: string;
  error_message: string;
  auto_fix_attempts: number;
  clarifications: Clarification[];
  events: QueryEvent[];
  guardrail_logs: GuardrailLog[];
  created_at: string;
  updated_at: string;
};

export type Chat = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type ChatMessage = {
  id: string;
  chat_id: string;
  role: string;
  content: string;
  payload: JsonObject;
  created_at: string;
};

export type MessagesPage = {
  items: ChatMessage[];
  has_more: boolean;
  next_offset: number;
};

export type ChatDeleteResult = {
  id: string;
  deleted: boolean;
  deleted_related_counts: Record<string, number>;
};

export type Template = {
  id: string;
  title: string;
  description: string;
  natural_text: string;
  canonical_intent_json: JsonObject;
  category: string;
  chart_type: string;
  is_public: boolean;
  use_count: number;
  created_at: string;
};

export type ReportVersion = {
  id: string;
  version_number: number;
  generated_sql: string;
  chart_type: string;
  config_json: JsonObject;
  created_at: string;
};

export type ScheduleRun = {
  id: string;
  status: string;
  rows_returned: number;
  execution_ms: number;
  error_message: string;
  ran_at: string;
};

export type Schedule = {
  id: string;
  report_id: string;
  report_title: string;
  frequency: "daily" | "weekly" | "monthly";
  run_at_time: string | null;
  day_of_week: number | null;
  day_of_month: number | null;
  next_run_at: string | null;
  last_run_at: string | null;
  is_active: boolean;
  recipients: string[];
  runs: ScheduleRun[];
};

export type Report = {
  id: string;
  title: string;
  natural_text: string;
  generated_sql: string;
  chart_type: string;
  chart_spec: QueryChartSpec;
  result_snapshot: QueryResultRow[];
  config_json: JsonObject;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  recipients: string[];
  schedules: Schedule[];
  versions: ReportVersion[];
};

export type SemanticTerm = {
  id: string;
  term: string;
  aliases: string[];
  sql_expression: string;
  table_name: string;
  description: string;
  metric_type: string;
  dimension_type: string;
  updated_at: string;
};

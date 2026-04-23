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
  role?: "user" | "admin";
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

export type QueryEvent = {
  id: string;
  step_name: string;
  status: string;
  payload_json: Record<string, any>;
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
  details_json: Record<string, any>;
  created_at: string;
};

export type Clarification = {
  id: string;
  question_text: string;
  options_json: Array<{ label: string; value: string; description: string }>;
  chosen_option: string;
  freeform_answer: string;
  created_at: string;
  answered_at: string | null;
};

export type QueryResult = {
  id: string;
  natural_text: string;
  generated_sql: string;
  corrected_sql: string;
  confidence_score: number;
  confidence_band: "high" | "medium" | "low";
  status: QueryStatus;
  block_reason: string;
  interpretation: Record<string, any>;
  resolved_request: Record<string, any>;
  semantic_terms: Array<Record<string, any>>;
  sql_plan: Record<string, any>;
  sql_explain_plan: Record<string, any>;
  sql_explain_cost: number;
  confidence_reasons: string[];
  ambiguity_flags: string[];
  rows_returned: number;
  execution_ms: number;
  chart_type: string;
  chart_spec: Record<string, any>;
  result_snapshot: Array<Record<string, any>>;
  ai_answer: string;
  error_message: string;
  auto_fix_attempts: number;
  clarifications: Clarification[];
  events: QueryEvent[];
  guardrail_logs: GuardrailLog[];
  created_at: string;
  updated_at: string;
};

export type Template = {
  id: string;
  title: string;
  description: string;
  natural_text: string;
  canonical_intent_json: Record<string, any>;
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
  config_json: Record<string, any>;
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
  chart_spec: Record<string, any>;
  result_snapshot: Array<Record<string, any>>;
  config_json: Record<string, any>;
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

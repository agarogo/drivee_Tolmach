import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AnswerEnvelope, QueryResult } from "../../../shared/types";
import { AnswerRenderer } from "./AnswerRenderer";
import { ViewModeSwitcher } from "./ViewModeSwitcher";

function baseAnswer(overrides: Partial<AnswerEnvelope>): AnswerEnvelope {
  return {
    answer_type: 1,
    answer_type_key: "single_value",
    answer_type_label: "Single KPI",
    answer_type_reason: "Single KPI answer",
    primary_view_mode: "number",
    available_view_modes: ["number", "table"],
    rerender_policy: "client_safe_only",
    requires_sql: true,
    result_grain: "kpi",
    can_switch_without_requery: true,
    explanation_why_this_type: "Single KPI selected.",
    metadata: {
      query_id: "query-1",
      chat_id: "chat-1",
      status: "success",
      rows_returned: 1,
      execution_ms: 42,
      created_at: "2026-04-24T10:00:00.000Z",
      updated_at: "2026-04-24T10:00:00.000Z",
    },
    explainability: {
      metric: "revenue",
      dimensions: [],
      dimension_labels: {},
      period: "last 30 days",
      filters: {},
      grouping: [],
      sorting: "revenue desc",
      limit: 1,
      source: "answer_type_classifier",
      provider_confidence: 0.96,
      fallback_used: false,
      semantic_terms: ["revenue"],
      sql_reasoning: ["single aggregate"],
      answer_type_reasoning: "Single KPI answer",
      view_reasoning: "Number and table are compatible with the same KPI grain.",
    },
    sql_visibility: {
      show_sql_panel: true,
      sql: "SELECT 1",
      explain_cost: 11,
      explain_plan_available: true,
    },
    render_payload: {
      kind: "single_value",
      metric_key: "revenue",
      metric_label: "Revenue",
      current_value: 1200,
      previous_value: 960,
      delta_abs: 240,
      delta_pct: 25,
      freshness_timestamp: "2026-04-24T10:00:00.000Z",
      unit_label: "",
      context: "Revenue for last 30 days.",
      availability_note: "",
      columns: [{ key: "revenue", label: "Revenue", data_type: "number" }],
      supporting_rows: [{ revenue: 1200 }],
    },
    switch_options: [
      {
        view_mode: "number",
        label: "Number",
        can_switch_without_requery: true,
        requery_required: false,
        reason: "Compatible",
      },
      {
        view_mode: "chart",
        label: "Chart",
        can_switch_without_requery: false,
        requery_required: true,
        reason: "Needs a different answer type.",
      },
      {
        view_mode: "table",
        label: "Table",
        can_switch_without_requery: true,
        requery_required: false,
        reason: "Compatible",
      },
      {
        view_mode: "report",
        label: "Report",
        can_switch_without_requery: false,
        requery_required: true,
        reason: "Needs a different answer type.",
      },
    ],
    compatibility_info: {
      compatible_view_modes: ["number", "table"],
      can_switch_without_requery: true,
      requery_required_for_views: ["chart", "report"],
    },
    ...overrides,
  };
}

function baseQuery(answer: AnswerEnvelope): QueryResult {
  return {
    id: "query-1",
    chat_id: "chat-1",
    natural_text: "show revenue",
    generated_sql: "SELECT 1",
    corrected_sql: "SELECT 1",
    confidence_score: 96,
    confidence_band: "high",
    status: "success",
    block_reason: "",
    block_reasons: [],
    interpretation: {},
    resolved_request: {},
    semantic_terms: [{ term: "revenue" }],
    sql_plan: {},
    sql_explain_plan: {},
    sql_explain_cost: 11,
    confidence_reasons: [],
    ambiguity_flags: [],
    rows_returned: 1,
    execution_ms: 42,
    provider: "ollama",
    llm_provider: "ollama",
    llm_model: "qwen3:4b",
    llm_used: true,
    fallback_used: false,
    retrieval_used: true,
    answer_type_code: answer.answer_type,
    answer_type_key: answer.answer_type_key,
    primary_view_mode: answer.primary_view_mode,
    answer,
    chart_type: "table_only",
    chart_spec: {},
    result_snapshot: [],
    ai_answer: "Revenue: 1200",
    error_message: "",
    auto_fix_attempts: 0,
    clarifications: [],
    events: [],
    guardrail_logs: [],
    created_at: "2026-04-24T10:00:00.000Z",
    updated_at: "2026-04-24T10:00:00.000Z",
  };
}

describe("AnswerRenderer", () => {
  it("renders chat help with glossary cards and no view switcher", () => {
    const answer = baseAnswer({
      answer_type: 0,
      answer_type_key: "chat_help",
      answer_type_label: "Chat Help",
      primary_view_mode: "chat",
      available_view_modes: ["chat"],
      requires_sql: false,
      result_grain: "chat",
      render_payload: {
        kind: "chat_help",
        message: "This request is routed to semantic help.",
        help_cards: [{ title: "status_tender", body: "Tender status glossary entry.", category: "glossary" }],
        suggested_questions: ["What does status_tender mean?"],
      },
      switch_options: [],
      compatibility_info: {
        compatible_view_modes: ["chat"],
        can_switch_without_requery: false,
        requery_required_for_views: ["number", "chart", "table", "report"],
      },
      sql_visibility: {
        show_sql_panel: false,
        sql: "",
        explain_cost: 0,
        explain_plan_available: false,
      },
    });

    const html = renderToStaticMarkup(
      <AnswerRenderer query={baseQuery(answer)} onReuseQuestion={() => undefined} onRequestSave={() => undefined} />,
    );

    expect(html).toContain("Semantic Help");
    expect(html).toContain("status_tender");
    expect(html).not.toContain("View Modes");
  });

  it("renders single value answer with KPI and freshness", () => {
    const html = renderToStaticMarkup(
      <AnswerRenderer query={baseQuery(baseAnswer({}))} onReuseQuestion={() => undefined} onRequestSave={() => undefined} />,
    );

    expect(html).toContain("Single KPI");
    expect(html).toContain("Revenue");
    expect(html).toContain("Freshness");
    expect(html).toContain("1,200");
  });

  it("renders full report answer with save action", () => {
    const answer = baseAnswer({
      answer_type: 6,
      answer_type_key: "full_report",
      answer_type_label: "Full Report",
      primary_view_mode: "report",
      available_view_modes: ["report", "number", "chart", "table"],
      result_grain: "report",
      render_payload: {
        kind: "full_report",
        title: "Revenue report",
        summary: "Report assembled from governed blocks.",
        kpis: [{ key: "revenue", label: "Revenue", value: 1200, unit_label: "" }],
        sections: [
          { kind: "insight", title: "Executive Summary", body: "Revenue is up." },
          {
            kind: "chart",
            title: "Trend",
            chart_type: "line",
            metric_key: "revenue",
            metric_label: "Revenue",
            x_key: "day",
            columns: [],
            rows: [{ day: "2026-04-20", revenue: 1000 }],
          },
          {
            kind: "table",
            title: "Preview",
            columns: [{ key: "order_id", label: "Order ID", data_type: "string" }],
            rows: [{ order_id: "ord-1" }],
          },
        ],
        insights: ["Revenue is up."],
        actionability: {
          rerun_supported: true,
          save_supported: true,
          schedule_supported: true,
          export_formats: ["csv"],
        },
        rerun_supported: true,
        save_supported: true,
      },
      switch_options: [
        {
          view_mode: "report",
          label: "Report",
          can_switch_without_requery: true,
          requery_required: false,
          reason: "Compatible",
        },
      ],
      compatibility_info: {
        compatible_view_modes: ["report", "number", "chart", "table"],
        can_switch_without_requery: true,
        requery_required_for_views: [],
      },
    });

    const html = renderToStaticMarkup(
      <AnswerRenderer query={baseQuery(answer)} onReuseQuestion={() => undefined} onRequestSave={() => undefined} />,
    );

    expect(html).toContain("Revenue report");
    expect(html).toContain("Save report");
    expect(html).toContain("Executive Summary");
  });

  it("renders comparison, trend, distribution, and table layouts from answer_type_key", () => {
    const cases: Array<{ answer: AnswerEnvelope; marker: string }> = [
      {
        answer: baseAnswer({
          answer_type: 2,
          answer_type_key: "comparison_top",
          answer_type_label: "Comparison / Top",
          primary_view_mode: "chart",
          available_view_modes: ["chart", "table"],
          result_grain: "category",
          render_payload: {
            kind: "comparison_top",
            metric_key: "revenue",
            metric_label: "Revenue",
            dimension_key: "city",
            dimension_label: "City",
            items: [{ rank: 1, label: "Tokyo", value: 1200, share_pct: null, is_other: false }],
            columns: [
              { key: "city", label: "City", data_type: "string" },
              { key: "revenue", label: "Revenue", data_type: "number" },
            ],
            rows: [{ city: "Tokyo", revenue: 1200 }],
            insight: "Tokyo leads the ranking.",
          },
          compatibility_info: {
            compatible_view_modes: ["chart", "table"],
            can_switch_without_requery: true,
            requery_required_for_views: ["number", "report"],
          },
        }),
        marker: "Ranking",
      },
      {
        answer: baseAnswer({
          answer_type: 3,
          answer_type_key: "trend",
          answer_type_label: "Trend",
          primary_view_mode: "chart",
          available_view_modes: ["chart", "table"],
          result_grain: "time_series",
          render_payload: {
            kind: "trend",
            metric_key: "revenue",
            metric_label: "Revenue",
            time_key: "day",
            points: [
              { label: "2026-04-20", value: 1000 },
              { label: "2026-04-21", value: 1200 },
            ],
            peak: { label: "2026-04-21", value: 1200 },
            low: { label: "2026-04-20", value: 1000 },
            columns: [{ key: "day", label: "Day", data_type: "date" }],
            rows: [
              { day: "2026-04-20", revenue: 1000 },
              { day: "2026-04-21", revenue: 1200 },
            ],
            insight: "Peak on Apr 21.",
          },
          compatibility_info: {
            compatible_view_modes: ["chart", "table"],
            can_switch_without_requery: true,
            requery_required_for_views: ["number", "report"],
          },
        }),
        marker: "Peak",
      },
      {
        answer: baseAnswer({
          answer_type: 4,
          answer_type_key: "distribution",
          answer_type_label: "Distribution",
          primary_view_mode: "chart",
          available_view_modes: ["chart", "table"],
          result_grain: "distribution",
          render_payload: {
            kind: "distribution",
            metric_key: "revenue",
            metric_label: "Revenue",
            dimension_key: "city",
            dimension_label: "City",
            items: [{ rank: 1, label: "Tokyo", value: 1200, share_pct: 60, is_other: false }],
            total_value: 2000,
            integrity_pct: 100,
            other_bucket_applied: false,
            columns: [{ key: "city", label: "City", data_type: "string" }],
            rows: [{ city: "Tokyo", revenue: 1200 }],
            insight: "Tokyo is the largest share.",
          },
          compatibility_info: {
            compatible_view_modes: ["chart", "table"],
            can_switch_without_requery: true,
            requery_required_for_views: ["number", "report"],
          },
        }),
        marker: "100% integrity",
      },
      {
        answer: baseAnswer({
          answer_type: 5,
          answer_type_key: "table",
          answer_type_label: "Table",
          primary_view_mode: "table",
          available_view_modes: ["table"],
          result_grain: "record",
          can_switch_without_requery: false,
          render_payload: {
            kind: "table",
            columns: [{ key: "order_id", label: "Order ID", data_type: "string" }],
            rows: [{ order_id: "ord-1" }],
            snapshot_row_count: 1,
            total_row_count: null,
            pagination_mode: "server_ready",
            page_size: 25,
            page_offset: 0,
            has_more: true,
            sort: { key: "order_id", direction: "asc" },
            export_formats: ["csv"],
          },
          compatibility_info: {
            compatible_view_modes: ["table"],
            can_switch_without_requery: false,
            requery_required_for_views: ["number", "chart", "report"],
          },
        }),
        marker: "More rows exist on the backend",
      },
    ];

    cases.forEach(({ answer, marker }) => {
      const html = renderToStaticMarkup(
        <AnswerRenderer query={baseQuery(answer)} onReuseQuestion={() => undefined} onRequestSave={() => undefined} />,
      );
      expect(html).toContain(marker);
    });
  });
});

describe("ViewModeSwitcher", () => {
  it("marks compatible and requery-only modes honestly", () => {
    const html = renderToStaticMarkup(
      <ViewModeSwitcher answer={baseAnswer({})} activeView="number" onChange={() => undefined} />,
    );

    expect(html).toContain("Current");
    expect(html).toContain("Switch now");
    expect(html).toContain("Needs re-query");
  });
});

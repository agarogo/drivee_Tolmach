/** @vitest-environment jsdom */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Chat, ChatDeleteResult, ChatMessage, JsonObject, QueryResult } from "../../../shared/types";
import { CHAT_SELECTION_KEY } from "../lib/chatSelection";
import { useAnalyticsFlow } from "./useAnalyticsFlow";

const createChatMock = vi.fn();
const deleteChatMock = vi.fn();
const fetchChatMessagesMock = vi.fn();
const runQueryMock = vi.fn();
const clarifyQueryMock = vi.fn();
const createReportMock = vi.fn();

vi.mock("../../../shared/api/chats", () => ({
  createChat: (...args: unknown[]) => createChatMock(...args),
  deleteChat: (...args: unknown[]) => deleteChatMock(...args),
  fetchChatMessages: (...args: unknown[]) => fetchChatMessagesMock(...args),
}));

vi.mock("../../../shared/api/queries", () => ({
  runQuery: (...args: unknown[]) => runQueryMock(...args),
  clarifyQuery: (...args: unknown[]) => clarifyQueryMock(...args),
}));

vi.mock("../../../shared/api/reports", () => ({
  createReport: (...args: unknown[]) => createReportMock(...args),
}));

function makeAnswerTypeEnvelope(): QueryResult["answer"] {
  return {
    answer_type: 5,
    answer_type_key: "table",
    answer_type_label: "Table",
    answer_type_reason: "Record answer",
    primary_view_mode: "table",
    available_view_modes: ["table"],
    rerender_policy: "locked",
    requires_sql: true,
    result_grain: "record",
    can_switch_without_requery: false,
    explanation_why_this_type: "Row-level answer.",
    metadata: {
      query_id: "query-1",
      chat_id: "chat-1",
      status: "success",
      rows_returned: 1,
      execution_ms: 12,
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
      sorting: "created_at desc",
      limit: 25,
      source: "test",
      provider_confidence: 0.95,
      fallback_used: false,
      semantic_terms: ["revenue"],
      sql_reasoning: [],
      answer_type_reasoning: "Table answer",
      view_reasoning: "Only table is compatible.",
    },
    sql_visibility: {
      show_sql_panel: true,
      sql: "SELECT 1",
      explain_cost: 1,
      explain_plan_available: true,
    },
    render_payload: {
      kind: "table",
      columns: [{ key: "city", label: "City", data_type: "string" }],
      rows: [{ city: "Tokyo" }],
      snapshot_row_count: 1,
      total_row_count: null,
      pagination_mode: "server_ready",
      page_size: 25,
      page_offset: 0,
      has_more: false,
      sort: { key: "city", direction: "asc" },
      export_formats: ["csv"],
    },
    switch_options: [],
    compatibility_info: {
      compatible_view_modes: ["table"],
      can_switch_without_requery: false,
      requery_required_for_views: ["number", "chart", "report"],
    },
  };
}

function makeQuery(chatId: string, queryId: string, naturalText: string): QueryResult {
  return {
    id: queryId,
    chat_id: chatId,
    natural_text: naturalText,
    generated_sql: "SELECT 1",
    corrected_sql: "SELECT 1",
    confidence_score: 95,
    confidence_band: "high",
    status: "success",
    block_reason: "",
    block_reasons: [],
    interpretation: {},
    resolved_request: {},
    semantic_terms: [{ term: "revenue" }],
    sql_plan: {},
    sql_explain_plan: {},
    sql_explain_cost: 1,
    confidence_reasons: [],
    ambiguity_flags: [],
    rows_returned: 1,
    execution_ms: 12,
    answer_type_code: 5,
    answer_type_key: "table",
    primary_view_mode: "table",
    answer: makeAnswerTypeEnvelope(),
    chart_type: "table_only",
    chart_spec: {},
    result_snapshot: [{ city: "Tokyo" }],
    ai_answer: "Tokyo row",
    error_message: "",
    auto_fix_attempts: 0,
    clarifications: [],
    events: [],
    guardrail_logs: [],
    created_at: "2026-04-24T10:00:00.000Z",
    updated_at: "2026-04-24T10:00:00.000Z",
  };
}

function makeAssistantMessage(chatId: string, query: QueryResult): ChatMessage {
  return {
    id: `assistant-${query.id}`,
    chat_id: chatId,
    role: "assistant",
    content: query.ai_answer,
    payload: query as unknown as JsonObject,
    created_at: "2026-04-24T10:00:00.000Z",
  };
}

function makeMessagesPage(chatId: string, query: QueryResult) {
  return {
    items: [
      {
        id: `user-${query.id}`,
        chat_id: chatId,
        role: "user",
        content: query.natural_text,
        payload: {},
        created_at: "2026-04-24T10:00:00.000Z",
      },
      makeAssistantMessage(chatId, query),
    ],
    has_more: false,
    next_offset: 2,
  };
}

function makeChats(): Chat[] {
  return [
    {
      id: "chat-1",
      title: "Revenue by city",
      created_at: "2026-04-24T10:00:00.000Z",
      updated_at: "2026-04-24T10:10:00.000Z",
      message_count: 2,
    },
    {
      id: "chat-2",
      title: "Driver quality",
      created_at: "2026-04-24T11:00:00.000Z",
      updated_at: "2026-04-24T11:10:00.000Z",
      message_count: 3,
    },
  ];
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("useAnalyticsFlow", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("hydrates the persisted chat after refresh and restores message history", async () => {
    localStorage.setItem(CHAT_SELECTION_KEY, "chat-2");
    const chats = makeChats();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const query = makeQuery("chat-2", "query-2", "show driver quality");
    fetchChatMessagesMock.mockResolvedValue(makeMessagesPage("chat-2", query));

    const { result } = renderHook(
      () =>
        useAnalyticsFlow({
          initialDraft: "",
          onToast: vi.fn(),
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await act(async () => {
      await result.current.hydrateSelection(chats);
    });

    expect(fetchChatMessagesMock).toHaveBeenCalledWith("chat-2");
    expect(result.current.currentChatId).toBe("chat-2");
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.currentQuery?.id).toBe("query-2");
  });

  it("sends follow-up questions with the current chat_id instead of creating a new chat", async () => {
    const chats = makeChats();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    queryClient.setQueryData<Chat[]>(["chats"], chats);

    const initialQuery = makeQuery("chat-1", "query-1", "show revenue");
    const followUpQuery = makeQuery("chat-1", "query-2", "and by driver");
    let loadCount = 0;
    fetchChatMessagesMock.mockImplementation(async (chatId: string) => {
      if (chatId === "chat-1") {
        loadCount += 1;
        return loadCount === 1
          ? makeMessagesPage("chat-1", initialQuery)
          : makeMessagesPage("chat-1", followUpQuery);
      }
      return makeMessagesPage("chat-2", makeQuery("chat-2", "query-3", "show quality"));
    });
    runQueryMock.mockResolvedValue(followUpQuery);

    const { result } = renderHook(
      () =>
        useAnalyticsFlow({
          initialDraft: "",
          onToast: vi.fn(),
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await act(async () => {
      await result.current.openChat("chat-1");
    });

    act(() => {
      result.current.setDraft("and by driver");
    });
    act(() => {
      result.current.submitQuery();
    });

    await waitFor(() => expect(runQueryMock).toHaveBeenCalled());
    expect(runQueryMock.mock.calls[0][0]).toBe("and by driver");
    expect(runQueryMock.mock.calls[0][1]).toBe("chat-1");
    expect(createChatMock).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.currentQuery?.id).toBe("query-2"));
    expect(result.current.currentChatId).toBe("chat-1");
  });

  it("creates a new chat explicitly and opens it as the active thread", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const newChat: Chat = {
      id: "chat-3",
      title: "New chat",
      created_at: "2026-04-24T12:00:00.000Z",
      updated_at: "2026-04-24T12:00:00.000Z",
      message_count: 0,
    };
    createChatMock.mockResolvedValue(newChat);
    fetchChatMessagesMock.mockResolvedValue({ items: [], has_more: false, next_offset: 0 });

    const { result } = renderHook(
      () =>
        useAnalyticsFlow({
          initialDraft: "",
          onToast: vi.fn(),
        }),
      { wrapper: createWrapper(queryClient) },
    );

    act(() => {
      result.current.createChat();
    });

    await waitFor(() => expect(result.current.currentChatId).toBe("chat-3"));
    expect(fetchChatMessagesMock).toHaveBeenCalledWith("chat-3");
    expect(localStorage.getItem(CHAT_SELECTION_KEY)).toBe("chat-3");
  });

  it("switches between chats and refreshes the selected thread history", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    fetchChatMessagesMock.mockImplementation(async (chatId: string) =>
      makeMessagesPage(chatId, makeQuery(chatId, `query-${chatId}`, `question for ${chatId}`)),
    );

    const { result } = renderHook(
      () =>
        useAnalyticsFlow({
          initialDraft: "",
          onToast: vi.fn(),
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await act(async () => {
      await result.current.openChat("chat-1");
    });
    await act(async () => {
      await result.current.openChat("chat-2");
    });

    expect(result.current.currentChatId).toBe("chat-2");
    expect(result.current.currentQuery?.chat_id).toBe("chat-2");
    expect(localStorage.getItem(CHAT_SELECTION_KEY)).toBe("chat-2");
  });

  it("deletes the current chat and selects the next available one", async () => {
    const chats = makeChats();
    const deleteResult: ChatDeleteResult = {
      id: "chat-1",
      deleted: true,
      deleted_related_counts: { messages: 2, queries: 1 },
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    queryClient.setQueryData<Chat[]>(["chats"], chats);

    fetchChatMessagesMock.mockImplementation(async (chatId: string) =>
      makeMessagesPage(chatId, makeQuery(chatId, `query-${chatId}`, `question for ${chatId}`)),
    );
    deleteChatMock.mockResolvedValue(deleteResult);

    const { result } = renderHook(
      () =>
        useAnalyticsFlow({
          initialDraft: "",
          onToast: vi.fn(),
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await act(async () => {
      await result.current.openChat("chat-1");
    });

    act(() => {
      result.current.deleteChat("chat-1");
    });

    await waitFor(() => expect(deleteChatMock).toHaveBeenCalled());
    expect(deleteChatMock.mock.calls[0][0]).toBe("chat-1");
    await waitFor(() => expect(result.current.currentChatId).toBe("chat-2"));
    expect(fetchChatMessagesMock).toHaveBeenLastCalledWith("chat-2");
  });

  it("deletes a non-active chat without disturbing the current thread", async () => {
    const chats = makeChats();
    const deleteResult: ChatDeleteResult = {
      id: "chat-1",
      deleted: true,
      deleted_related_counts: { messages: 2, queries: 1 },
    };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    queryClient.setQueryData<Chat[]>(["chats"], chats);

    fetchChatMessagesMock.mockImplementation(async (chatId: string) =>
      makeMessagesPage(chatId, makeQuery(chatId, `query-${chatId}`, `question for ${chatId}`)),
    );
    deleteChatMock.mockResolvedValue(deleteResult);

    const { result } = renderHook(
      () =>
        useAnalyticsFlow({
          initialDraft: "",
          onToast: vi.fn(),
        }),
      { wrapper: createWrapper(queryClient) },
    );

    await act(async () => {
      await result.current.openChat("chat-2");
    });

    act(() => {
      result.current.deleteChat("chat-1");
    });

    await waitFor(() => expect(deleteChatMock).toHaveBeenCalled());
    expect(result.current.currentChatId).toBe("chat-2");
    expect(fetchChatMessagesMock).toHaveBeenCalledTimes(1);
  });
});

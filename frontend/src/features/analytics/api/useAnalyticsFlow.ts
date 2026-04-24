import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createChat,
  deleteChat as deleteChatRequest,
  fetchChatMessages,
} from "../../../shared/api/chats";
import { clarifyQuery, runQuery } from "../../../shared/api/queries";
import { createReport } from "../../../shared/api/reports";
import type {
  Chat,
  ChatMessage,
  ControlledQueryError,
  JsonObject,
  LlmErrorMessagePayload,
  QueryResult,
} from "../../../shared/types";
import {
  nextChatAfterDeletion,
  persistChatId,
  readPersistedChatId,
  resolvePreferredChatId,
} from "../lib/chatSelection";

type SaveReportPayload = {
  title: string;
  schedule: Record<string, unknown> | null;
  recipients: string[];
};

function queryFromMessage(message: ChatMessage): QueryResult | null {
  const payload = message.payload as QueryResult | undefined;
  if (!payload || typeof payload !== "object") return null;
  if (typeof payload.id !== "string" || typeof payload.status !== "string") return null;
  return payload;
}

function latestQuery(messages: ChatMessage[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const candidate = queryFromMessage(messages[index]);
    if (candidate) return candidate;
  }
  return null;
}

function mutationErrorMessage(error: any, fallback: string) {
  return controlledQueryErrorFrom(error)?.message || error?.response?.data?.detail || error?.message || fallback;
}

function isControlledQueryError(value: unknown): value is ControlledQueryError {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  return (
    (item.error_code === "llm_timeout" || item.error_code === "llm_unavailable") &&
    typeof item.message === "string" &&
    typeof item.provider === "string" &&
    typeof item.model === "string" &&
    typeof item.device_hint === "string" &&
    typeof item.fallback_used === "boolean"
  );
}

function controlledQueryErrorFrom(error: any): ControlledQueryError | null {
  const data = error?.response?.data;
  if (isControlledQueryError(data)) return data;
  if (isControlledQueryError(data?.detail)) return data.detail;
  return null;
}

function isRequestCanceled(error: any) {
  return error?.code === "ERR_CANCELED" || error?.name === "CanceledError";
}

function llmErrorPayload(error: ControlledQueryError): LlmErrorMessagePayload {
  return {
    ...error,
    type: "llm_error",
    title: error.title || "Запрос выполнялся слишком долго",
    body: error.body || "LLM не успела ответить за лимит времени. Проверь GPU/Ollama или упрости запрос.",
    actions: error.actions || ["Повторить", "Вернуть вопрос в поле ввода"],
  };
}

function buildLocalMessage(chatId: string, role: "user" | "assistant", content: string, payload: JsonObject): ChatMessage {
  return {
    id: `local-${role}-${Date.now()}-${Math.round(Math.random() * 1_000_000)}`,
    chat_id: chatId,
    role,
    content,
    payload,
    created_at: new Date().toISOString(),
  };
}

export function useAnalyticsFlow({
  initialDraft,
  onToast,
  onReportSaved,
}: {
  initialDraft: string;
  onToast: (message: string) => void;
  onReportSaved?: (reportId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(initialDraft);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentQuery, setCurrentQuery] = useState<QueryResult | null>(null);
  const [loadingChat, setLoadingChat] = useState(false);
  const [loadedChatId, setLoadedChatId] = useState<string | null>(null);
  const [chatError, setChatError] = useState("");
  const [selectionHydrated, setSelectionHydrated] = useState(false);
  const activeRunController = useRef<AbortController | null>(null);
  const activeClarifyController = useRef<AbortController | null>(null);

  const loadChat = useCallback(
    async (chatId: string | null, options: { force?: boolean } = {}) => {
      if (!chatId) {
        persistChatId(null);
        setCurrentChatId(null);
        setMessages([]);
        setCurrentQuery(null);
        setLoadedChatId(null);
        setLoadingChat(false);
        setChatError("");
        return true;
      }

      const force = Boolean(options.force);
      if (!force && currentChatId === chatId && loadedChatId === chatId && !chatError) {
        return true;
      }

      persistChatId(chatId);
      setCurrentChatId(chatId);
      setMessages([]);
      setCurrentQuery(null);
      setLoadingChat(true);
      setChatError("");

      try {
        const page = await fetchChatMessages(chatId);
        setMessages(page.items);
        setCurrentQuery(latestQuery(page.items));
        setLoadedChatId(chatId);
        return true;
      } catch (error: any) {
        setLoadedChatId(chatId);
        setChatError(mutationErrorMessage(error, "Не удалось загрузить историю чата."));
        onToast(mutationErrorMessage(error, "Не удалось загрузить историю чата."));
        return false;
      } finally {
        setLoadingChat(false);
      }
    },
    [chatError, currentChatId, loadedChatId, onToast],
  );

  const appendLocalLlmErrorConversation = useCallback(
    (chatId: string, question: string, error: ControlledQueryError) => {
      const payload = llmErrorPayload(error);
      persistChatId(chatId);
      setSelectionHydrated(true);
      setCurrentChatId(chatId);
      setLoadedChatId(chatId);
      setChatError("");
      setMessages((current) => [
        ...current,
        buildLocalMessage(chatId, "user", question, {}),
        buildLocalMessage(
          chatId,
          "assistant",
          payload.body || payload.message,
          payload as unknown as JsonObject,
        ),
      ]);
    },
    [],
  );

  const hydrateSelection = useCallback(
    async (availableChats: Chat[]) => {
      const targetChatId = resolvePreferredChatId(
        availableChats,
        currentChatId,
        readPersistedChatId(),
      );

      if (!selectionHydrated) {
        setSelectionHydrated(true);
      }

      if (!targetChatId) {
        if (currentChatId) {
          await loadChat(null, { force: true });
        }
        return;
      }

      if (currentChatId !== targetChatId || loadedChatId !== targetChatId || Boolean(chatError)) {
        await loadChat(targetChatId, { force: true });
      }
    },
    [chatError, currentChatId, loadChat, loadedChatId, selectionHydrated],
  );

  const createChatMutation = useMutation({
    mutationFn: createChat,
    onSuccess: async (chat) => {
      queryClient.setQueryData<Chat[]>(["chats"], (current) => {
        const next = current || [];
        return [chat, ...next.filter((item) => item.id !== chat.id)];
      });
      setSelectionHydrated(true);
      await loadChat(chat.id, { force: true });
    },
    onError: (error: any) => {
      onToast(mutationErrorMessage(error, "Не удалось создать чат."));
    },
  });

  const runMutation = useMutation({
    mutationFn: async ({ question, controller }: { question: string; controller: AbortController }) => {
      let targetChatId = currentChatId;
      if (!targetChatId) {
        const chat = await createChat();
        targetChatId = chat.id;
        queryClient.setQueryData<Chat[]>(["chats"], (current) => {
          const next = current || [];
          return [chat, ...next.filter((item) => item.id !== chat.id)];
        });
      }
      try {
        const query = await runQuery(question, targetChatId, { signal: controller.signal });
        return { chatId: targetChatId, query };
      } catch (error: any) {
        throw Object.assign(error || new Error("Не удалось выполнить запрос."), {
          chatId: targetChatId,
          question,
        });
      }
    },
    onSuccess: async ({ chatId, query }) => {
      activeRunController.current = null;
      setPendingQuestion("");
      setSelectionHydrated(true);
      await loadChat(chatId, { force: true });
      await queryClient.invalidateQueries({ queryKey: ["chats"] });
      if (query.status === "success") onToast("Ответ готов.");
      if (query.status === "clarification_required") onToast("Нужно уточнение.");
      if (query.status === "blocked") onToast("Запрос заблокирован guardrails.");
    },
    onError: async (error: any, variables) => {
      activeRunController.current = null;
      if (isRequestCanceled(error)) {
        return;
      }

      const controlledError = controlledQueryErrorFrom(error);
      if (controlledError) {
        const targetChatId = String(error?.chatId || currentChatId || "");
        const restored = targetChatId ? await loadChat(targetChatId, { force: true }) : false;
        if (!restored && targetChatId) {
          appendLocalLlmErrorConversation(targetChatId, variables.question, controlledError);
        }
        setPendingQuestion("");
        await queryClient.invalidateQueries({ queryKey: ["chats"] });
        return;
      }

      setPendingQuestion("");
      onToast(mutationErrorMessage(error, "Не удалось выполнить запрос."));
    },
  });

  const clarifyMutation = useMutation({
    mutationFn: async ({
      value,
      freeform,
      controller,
    }: {
      value: string;
      freeform?: string;
      controller: AbortController;
    }) => {
      if (!currentQuery) {
        throw new Error("Нет запроса для уточнения.");
      }
      try {
        return await clarifyQuery(currentQuery.id, value, freeform, { signal: controller.signal });
      } catch (error: any) {
        throw Object.assign(error || new Error("Не удалось отправить уточнение."), {
          chatId: currentQuery.chat_id || currentChatId,
          question: freeform || value,
        });
      }
    },
    onSuccess: async (query) => {
      activeClarifyController.current = null;
      if (query.chat_id) {
        setSelectionHydrated(true);
        await loadChat(query.chat_id, { force: true });
      } else {
        setCurrentQuery(query);
      }
      await queryClient.invalidateQueries({ queryKey: ["chats"] });
      if (query.status === "success") onToast("Уточнение применено, ответ обновлён.");
      if (query.status === "clarification_required") onToast("Нужно ещё одно уточнение.");
      if (query.status === "blocked") onToast("Запрос заблокирован после уточнения.");
    },
    onError: async (error: any, variables) => {
      activeClarifyController.current = null;
      if (isRequestCanceled(error)) {
        return;
      }

      const controlledError = controlledQueryErrorFrom(error);
      if (controlledError) {
        const targetChatId = String(error?.chatId || currentChatId || "");
        const restored = targetChatId ? await loadChat(targetChatId, { force: true }) : false;
        if (!restored && targetChatId) {
          appendLocalLlmErrorConversation(targetChatId, variables.freeform || variables.value, controlledError);
        }
        await queryClient.invalidateQueries({ queryKey: ["chats"] });
        return;
      }

      onToast(mutationErrorMessage(error, "Не удалось отправить уточнение."));
    },
  });

  const deleteChatMutation = useMutation({
    mutationFn: deleteChatRequest,
    onSuccess: async (result) => {
      const currentChats = queryClient.getQueryData<Chat[]>(["chats"]) || [];
      const nextChats = currentChats.filter((chat) => chat.id !== result.id);
      queryClient.setQueryData<Chat[]>(["chats"], nextChats);

      const nextChatId = nextChatAfterDeletion(nextChats, result.id, currentChatId);
      if (currentChatId === result.id) {
        await loadChat(nextChatId, { force: true });
      } else {
        persistChatId(currentChatId);
      }

      await queryClient.invalidateQueries({ queryKey: ["chats"] });
      onToast("Чат удалён.");
    },
    onError: (error: any) => {
      onToast(mutationErrorMessage(error, "Не удалось удалить чат."));
    },
  });

  const saveReportMutation = useMutation({
    mutationFn: ({ title, schedule, recipients }: SaveReportPayload) => {
      if (!currentQuery) {
        throw new Error("Нет результата, который можно сохранить.");
      }
      return createReport({
        query_id: currentQuery.id,
        title,
        recipients,
        schedule,
      });
    },
    onSuccess: async (report) => {
      onToast("Отчёт сохранён.");
      onReportSaved?.(report.id);
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      await queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
    onError: (error: any) => {
      onToast(mutationErrorMessage(error, "Не удалось сохранить отчёт."));
    },
  });

  useEffect(() => {
    if (!messages.length) {
      setCurrentQuery(null);
      return;
    }
    setCurrentQuery(latestQuery(messages));
  }, [messages]);

  const startQuery = useCallback(
    (value: string) => {
      const question = value.trim();
      if (!question || runMutation.isPending) return;
      const controller = new AbortController();
      activeRunController.current = controller;
      setPendingQuestion(question);
      setDraft("");
      runMutation.mutate({ question, controller });
    },
    [runMutation],
  );

  const submitQuery = useCallback(() => {
    startQuery(draft);
  }, [draft, startQuery]);

  const reuseQuestion = useCallback((text: string) => {
    setDraft(text);
  }, []);

  const retryQuestion = useCallback((text: string) => {
    startQuery(text);
  }, [startQuery]);

  const cancelPendingRequest = useCallback(() => {
    if (!activeRunController.current || !pendingQuestion) return;
    activeRunController.current.abort();
    activeRunController.current = null;
    setDraft((currentDraft) => currentDraft || pendingQuestion);
    setPendingQuestion("");
  }, [pendingQuestion]);

  const resetAnalytics = useCallback(() => {
    activeRunController.current?.abort();
    activeClarifyController.current?.abort();
    activeRunController.current = null;
    activeClarifyController.current = null;
    persistChatId(null);
    setCurrentChatId(null);
    setMessages([]);
    setCurrentQuery(null);
    setPendingQuestion("");
    setDraft("");
    setLoadedChatId(null);
    setLoadingChat(false);
    setChatError("");
    setSelectionHydrated(false);
  }, []);

  const busyChatId = useMemo(() => {
    if (deleteChatMutation.isPending && typeof deleteChatMutation.variables === "string") {
      return deleteChatMutation.variables;
    }
    if (loadingChat && currentChatId) return currentChatId;
    return null;
  }, [currentChatId, deleteChatMutation.isPending, deleteChatMutation.variables, loadingChat]);

  return {
    draft,
    setDraft,
    pendingQuestion,
    currentChatId,
    messages,
    currentQuery,
    running: runMutation.isPending || clarifyMutation.isPending,
    saving: saveReportMutation.isPending,
    loadingChat,
    chatError,
    selectionHydrated,
    creatingChat: createChatMutation.isPending,
    deletingChatId:
      deleteChatMutation.isPending && typeof deleteChatMutation.variables === "string"
        ? deleteChatMutation.variables
        : null,
    busyChatId,
    reuseQuestion,
    retryQuestion,
    cancelPendingRequest,
    resetAnalytics,
    submitQuery,
    hydrateSelection,
    reloadCurrentChat: () => loadChat(currentChatId, { force: true }),
    createChat: () => createChatMutation.mutate(),
    openChat: (chatId: string) => loadChat(chatId, { force: true }),
    deleteChat: (chatId: string) => deleteChatMutation.mutate(chatId),
    clarify: (value: string, freeform?: string) => {
      const controller = new AbortController();
      activeClarifyController.current = controller;
      clarifyMutation.mutate({ value, freeform, controller });
    },
    saveReport: (payload: SaveReportPayload) => saveReportMutation.mutate(payload),
  };
}

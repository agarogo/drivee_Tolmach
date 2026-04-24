import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createChat,
  deleteChat as deleteChatRequest,
  fetchChatMessages,
} from "../../../shared/api/chats";
import { clarifyQuery, runQuery } from "../../../shared/api/queries";
import { createReport } from "../../../shared/api/reports";
import type { Chat, ChatMessage, QueryResult } from "../../../shared/types";
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
  return error?.response?.data?.detail || error?.message || fallback;
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
        return;
      }

      const force = Boolean(options.force);
      if (!force && currentChatId === chatId && loadedChatId === chatId && !chatError) {
        return;
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
      } catch (error: any) {
        setLoadedChatId(chatId);
        setChatError(mutationErrorMessage(error, "Failed to load chat history."));
        onToast(mutationErrorMessage(error, "Failed to load chat history"));
      } finally {
        setLoadingChat(false);
      }
    },
    [chatError, currentChatId, loadedChatId, onToast],
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
      onToast(mutationErrorMessage(error, "Failed to create chat"));
    },
  });

  const runMutation = useMutation({
    mutationFn: async (question: string) => {
      let targetChatId = currentChatId;
      if (!targetChatId) {
        const chat = await createChat();
        targetChatId = chat.id;
        queryClient.setQueryData<Chat[]>(["chats"], (current) => {
          const next = current || [];
          return [chat, ...next.filter((item) => item.id !== chat.id)];
        });
      }
      const query = await runQuery(question, targetChatId);
      return { chatId: targetChatId, query };
    },
    onSuccess: async ({ chatId, query }) => {
      setPendingQuestion("");
      setSelectionHydrated(true);
      await loadChat(chatId, { force: true });
      await queryClient.invalidateQueries({ queryKey: ["chats"] });
      if (query.status === "success") onToast("Query completed");
      if (query.status === "clarification_required") onToast("Clarification required");
      if (query.status === "blocked") onToast("Query blocked by guardrails");
    },
    onError: (error: any) => {
      setPendingQuestion("");
      onToast(mutationErrorMessage(error, "Failed to run query"));
    },
  });

  const clarifyMutation = useMutation({
    mutationFn: ({ value, freeform }: { value: string; freeform?: string }) => {
      if (!currentQuery) {
        throw new Error("No query available for clarification");
      }
      return clarifyQuery(currentQuery.id, value, freeform);
    },
    onSuccess: async (query) => {
      if (query.chat_id) {
        setSelectionHydrated(true);
        await loadChat(query.chat_id, { force: true });
      } else {
        setCurrentQuery(query);
      }
      await queryClient.invalidateQueries({ queryKey: ["chats"] });
      if (query.status === "success") onToast("Clarified query completed");
      if (query.status === "clarification_required") onToast("Another clarification is still required");
      if (query.status === "blocked") onToast("Query was blocked after clarification");
    },
    onError: (error: any) => {
      onToast(mutationErrorMessage(error, "Failed to clarify query"));
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
      onToast("Chat deleted");
    },
    onError: (error: any) => {
      onToast(mutationErrorMessage(error, "Failed to delete chat"));
    },
  });

  const saveReportMutation = useMutation({
    mutationFn: ({ title, schedule, recipients }: SaveReportPayload) => {
      if (!currentQuery) {
        throw new Error("No query available to save");
      }
      return createReport({
        query_id: currentQuery.id,
        title,
        recipients,
        schedule,
      });
    },
    onSuccess: async (report) => {
      onToast("Report saved");
      onReportSaved?.(report.id);
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      await queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
    onError: (error: any) => {
      onToast(mutationErrorMessage(error, "Failed to save report"));
    },
  });

  useEffect(() => {
    if (!messages.length) {
      setCurrentQuery(null);
      return;
    }
    setCurrentQuery(latestQuery(messages));
  }, [messages]);

  const submitQuery = useCallback(() => {
    const question = draft.trim();
    if (!question || runMutation.isPending) return;
    setPendingQuestion(question);
    setDraft("");
    runMutation.mutate(question);
  }, [draft, runMutation]);

  const reuseQuestion = useCallback((text: string) => {
    setDraft(text);
  }, []);

  const resetAnalytics = useCallback(() => {
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
    resetAnalytics,
    submitQuery,
    hydrateSelection,
    reloadCurrentChat: () => loadChat(currentChatId, { force: true }),
    createChat: () => createChatMutation.mutate(),
    openChat: (chatId: string) => loadChat(chatId, { force: true }),
    deleteChat: (chatId: string) => deleteChatMutation.mutate(chatId),
    clarify: (value: string, freeform?: string) => clarifyMutation.mutate({ value, freeform }),
    saveReport: (payload: SaveReportPayload) => saveReportMutation.mutate(payload),
  };
}

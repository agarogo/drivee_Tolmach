import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { clarifyQuery, runQuery } from "../../../shared/api/queries";
import { createReport } from "../../../shared/api/reports";
import type { QueryResult } from "../../../shared/types";

type SaveReportPayload = {
  title: string;
  schedule: Record<string, unknown> | null;
  recipients: string[];
};

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
  const [currentQuery, setCurrentQuery] = useState<QueryResult | null>(null);

  const runMutation = useMutation({
    mutationFn: (question: string) => runQuery(question),
    onSuccess: (query) => {
      setCurrentQuery(query);
      setPendingQuestion("");
      queryClient.invalidateQueries({ queryKey: ["history"] });
      if (query.status === "success") onToast("Query completed");
      if (query.status === "clarification_required") onToast("Clarification required");
      if (query.status === "blocked") onToast("Query blocked by guardrails");
    },
    onError: (error: any) => {
      setPendingQuestion("");
      onToast(error?.response?.data?.detail || "Failed to run query");
    },
  });

  const clarifyMutation = useMutation({
    mutationFn: ({ value, freeform }: { value: string; freeform?: string }) => {
      if (!currentQuery) {
        throw new Error("No query available for clarification");
      }
      return clarifyQuery(currentQuery.id, value, freeform);
    },
    onSuccess: (query) => {
      setCurrentQuery(query);
      queryClient.invalidateQueries({ queryKey: ["history"] });
      if (query.status === "success") onToast("Clarified query completed");
      if (query.status === "clarification_required") onToast("Another clarification is still required");
      if (query.status === "blocked") onToast("Query was blocked after clarification");
    },
    onError: (error: any) => {
      onToast(error?.response?.data?.detail || "Failed to clarify query");
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
    onSuccess: (report) => {
      onToast("Report saved");
      onReportSaved?.(report.id);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
    onError: (error: any) => {
      onToast(error?.response?.data?.detail || "Failed to save report");
    },
  });

  function submitQuery() {
    const question = draft.trim();
    if (!question || runMutation.isPending) return;
    setPendingQuestion(question);
    setCurrentQuery(null);
    setDraft("");
    runMutation.mutate(question);
  }

  function selectQuery(query: QueryResult | null) {
    setCurrentQuery(query);
    setPendingQuestion("");
  }

  function reuseQuestion(text: string) {
    setDraft(text);
  }

  function resetAnalytics() {
    setCurrentQuery(null);
    setPendingQuestion("");
    setDraft("");
  }

  return {
    draft,
    setDraft,
    pendingQuestion,
    currentQuery,
    running: runMutation.isPending || clarifyMutation.isPending,
    saving: saveReportMutation.isPending,
    selectQuery,
    reuseQuestion,
    resetAnalytics,
    submitQuery,
    clarify: (value: string, freeform?: string) => clarifyMutation.mutate({ value, freeform }),
    saveReport: (payload: SaveReportPayload) => saveReportMutation.mutate(payload),
  };
}

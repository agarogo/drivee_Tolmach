import { api } from "./client";
import type { QueryResult } from "../types";

export async function runQuery(question: string, chatId?: string | null) {
  const { data } = await api.post<QueryResult>("/queries/run", {
    question,
    chat_id: chatId ?? null,
  });
  return data;
}

export async function clarifyQuery(queryId: string, chosenOption: string, freeformAnswer = "") {
  const { data } = await api.post<QueryResult>(`/queries/${queryId}/clarify`, {
    chosen_option: chosenOption,
    freeform_answer: freeformAnswer,
  });
  return data;
}

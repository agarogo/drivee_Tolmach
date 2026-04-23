import { api } from "./client";
import type { QueryResult } from "../types";

export async function runQuery(question: string) {
  const { data } = await api.post<QueryResult>("/queries/run", { question });
  return data;
}

export async function clarifyQuery(queryId: string, chosenOption: string, freeformAnswer = "") {
  const { data } = await api.post<QueryResult>(`/queries/${queryId}/clarify`, {
    chosen_option: chosenOption,
    freeform_answer: freeformAnswer,
  });
  return data;
}

export async function fetchHistory() {
  const { data } = await api.get<QueryResult[]>("/queries/history");
  return data;
}

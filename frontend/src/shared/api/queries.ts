import { api } from "./client";
import type { QueryResult } from "../types";

function assertTypedSuccessPayload(query: QueryResult): QueryResult {
  if (query.status === "success" && (!query.answer || !query.answer.render_payload)) {
    throw new Error("Successful queries must include a typed render_payload.");
  }
  return query;
}

type RequestOptions = {
  signal?: AbortSignal;
};

export async function runQuery(question: string, chatId?: string | null, options: RequestOptions = {}) {
  const { data } = await api.post<QueryResult>("/queries/run", {
    question,
    chat_id: chatId ?? null,
  }, {
    signal: options.signal,
  });
  return assertTypedSuccessPayload(data);
}

export async function clarifyQuery(
  queryId: string,
  chosenOption: string,
  freeformAnswer = "",
  options: RequestOptions = {},
) {
  const { data } = await api.post<QueryResult>(`/queries/${queryId}/clarify`, {
    chosen_option: chosenOption,
    freeform_answer: freeformAnswer,
  }, {
    signal: options.signal,
  });
  return assertTypedSuccessPayload(data);
}

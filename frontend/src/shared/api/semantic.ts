import { api } from "./client";
import type { SemanticTerm } from "../types";

export async function fetchSemanticLayer() {
  const { data } = await api.get<SemanticTerm[]>("/semantic-layer");
  return data;
}

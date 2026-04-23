import { api } from "./client";
import type { Template } from "../types";

export async function fetchTemplates() {
  const { data } = await api.get<Template[]>("/templates");
  return data;
}

export async function createTemplate(payload: Partial<Template> & { title: string; natural_text: string }) {
  const { data } = await api.post<Template>("/templates", payload);
  return data;
}

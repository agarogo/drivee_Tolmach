import { api } from "./client";
import type { Report } from "../types";

export async function fetchReports() {
  const { data } = await api.get<Report[]>("/reports");
  return data;
}

export async function fetchReport(id: string) {
  const { data } = await api.get<Report>(`/reports/${id}`);
  return data;
}

export async function createReport(payload: Record<string, any>) {
  const { data } = await api.post<Report>("/reports", payload);
  return data;
}

export async function runReport(id: string) {
  const { data } = await api.post<Report>(`/reports/${id}/run`);
  return data;
}

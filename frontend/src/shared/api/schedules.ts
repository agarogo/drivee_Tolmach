import { api } from "./client";
import type { Schedule } from "../types";

export async function fetchSchedules() {
  const { data } = await api.get<Schedule[]>("/schedules");
  return data;
}

export async function createSchedule(payload: Record<string, any>) {
  const { data } = await api.post<Schedule>("/schedules", payload);
  return data;
}

export async function patchSchedule(id: string, payload: Record<string, any>) {
  const { data } = await api.patch<Schedule>(`/schedules/${id}`, payload);
  return data;
}

export async function toggleSchedule(id: string) {
  const { data } = await api.post<Schedule>(`/schedules/${id}/toggle`);
  return data;
}

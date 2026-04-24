import { api } from "./client";
import type { Chat, ChatDeleteResult, MessagesPage } from "../types";

export async function fetchChats() {
  const { data } = await api.get<Chat[]>("/api/chats");
  return data;
}

export async function createChat() {
  const { data } = await api.post<Chat>("/api/chats");
  return data;
}

export async function fetchChatMessages(chatId: string, limit = 50, offset = 0) {
  const { data } = await api.get<MessagesPage>(`/api/chats/${chatId}/messages`, {
    params: { limit, offset },
  });
  return data;
}

export async function deleteChat(chatId: string) {
  const { data } = await api.delete<ChatDeleteResult>(`/api/chats/${chatId}`);
  return data;
}

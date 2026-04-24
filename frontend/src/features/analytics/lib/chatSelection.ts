import type { Chat } from "../../../shared/types";

export const CHAT_SELECTION_KEY = "tolmach_selected_chat";

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function storageOrNull(storage?: StorageLike | null): StorageLike | null {
  if (storage) return storage;
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

export function readPersistedChatId(storage?: StorageLike | null): string | null {
  const resolved = storageOrNull(storage);
  if (!resolved) return null;
  const value = resolved.getItem(CHAT_SELECTION_KEY);
  return value?.trim() ? value : null;
}

export function persistChatId(chatId: string | null, storage?: StorageLike | null): void {
  const resolved = storageOrNull(storage);
  if (!resolved) return;
  if (!chatId) {
    resolved.removeItem(CHAT_SELECTION_KEY);
    return;
  }
  resolved.setItem(CHAT_SELECTION_KEY, chatId);
}

export function resolvePreferredChatId(
  chats: Array<Pick<Chat, "id">>,
  currentChatId: string | null,
  persistedChatId: string | null,
): string | null {
  const availableIds = new Set(chats.map((chat) => chat.id));
  if (currentChatId && availableIds.has(currentChatId)) return currentChatId;
  if (persistedChatId && availableIds.has(persistedChatId)) return persistedChatId;
  return chats[0]?.id || null;
}

export function nextChatAfterDeletion(
  chats: Array<Pick<Chat, "id">>,
  deletedChatId: string,
  currentChatId: string | null,
): string | null {
  const remaining = chats.filter((chat) => chat.id !== deletedChatId);
  if (!remaining.length) return null;
  if (currentChatId && currentChatId !== deletedChatId) {
    const currentStillExists = remaining.some((chat) => chat.id === currentChatId);
    if (currentStillExists) return currentChatId;
  }
  return remaining[0].id;
}

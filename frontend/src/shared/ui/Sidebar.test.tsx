/** @vitest-environment jsdom */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Chat, Template } from "../types";
import { Sidebar } from "./Sidebar";

afterEach(() => {
  cleanup();
});

const chats: Chat[] = [
  {
    id: "chat-1",
    title: "Revenue by city",
    created_at: "2026-04-24T10:00:00.000Z",
    updated_at: "2026-04-24T10:00:00.000Z",
    message_count: 4,
  },
  {
    id: "chat-2",
    title: "Driver quality",
    created_at: "2026-04-24T11:00:00.000Z",
    updated_at: "2026-04-24T11:30:00.000Z",
    message_count: 2,
  },
];

const templates: Template[] = [
  {
    id: "template-1",
    title: "Revenue trend",
    description: "",
    natural_text: "show revenue trend",
    canonical_intent_json: {},
    category: "analytics",
    chart_type: "line",
    is_public: true,
    use_count: 5,
    created_at: "2026-04-24T10:00:00.000Z",
  },
];

function renderSidebar(overrides: Partial<Parameters<typeof Sidebar>[0]> = {}) {
  const onRetryChats = vi.fn();
  const onNew = vi.fn();
  const onPickChat = vi.fn();
  const onDeleteChat = vi.fn();
  const onUseTemplate = vi.fn();

  render(
    <Sidebar
      chats={chats}
      selectedChatId="chat-1"
      templates={templates}
      onRetryChats={onRetryChats}
      onNew={onNew}
      onPickChat={onPickChat}
      onDeleteChat={onDeleteChat}
      onUseTemplate={onUseTemplate}
      {...overrides}
    />,
  );

  return { onRetryChats, onNew, onPickChat, onDeleteChat, onUseTemplate };
}

describe("Sidebar", () => {
  it("renders chat list and opens the selected chat", async () => {
    const user = userEvent.setup();
    const { onPickChat } = renderSidebar();

    expect(screen.getByText("Chats")).toBeTruthy();
    expect(screen.getByText("Revenue by city")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Open chat Driver quality" }));

    expect(onPickChat).toHaveBeenCalledWith("chat-2");
  });

  it("confirms delete inline before removing a chat", async () => {
    const user = userEvent.setup();
    const { onDeleteChat } = renderSidebar();

    await user.click(screen.getByRole("button", { name: "Delete chat Revenue by city" }));

    expect(screen.getByText("Delete this chat and its message history?")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Confirm delete" }));

    expect(onDeleteChat).toHaveBeenCalledWith("chat-1");
  });

  it("shows chat loading state", () => {
    renderSidebar({ chats: [], templates: [], loadingChats: true, chatsError: "" });
    expect(screen.getByText("Loading chat list...")).toBeTruthy();
  });

  it("shows chat error state with retry", async () => {
    const user = userEvent.setup();
    const { onRetryChats } = renderSidebar({ chats: [], templates: [], chatsError: "Could not load chats." });

    expect(screen.getByText("Could not load chats.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetryChats).toHaveBeenCalledTimes(1);
  });

  it("shows empty state when no chats exist", () => {
    renderSidebar({ chats: [], templates: [], loadingChats: false, chatsError: "" });
    expect(screen.getByText("No chats yet")).toBeTruthy();
  });
});

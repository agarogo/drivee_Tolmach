import { useEffect, useState } from "react";
import type { Chat, Template } from "../types";
import { formatDate } from "../utils/format";
import "./sidebar-stage5.css";

export function Sidebar({
  chats,
  selectedChatId,
  templates,
  loadingChats = false,
  chatsError = "",
  creatingChat = false,
  deletingChatId = null,
  busyChatId = null,
  onRetryChats,
  onNew,
  onPickChat,
  onDeleteChat,
  onUseTemplate,
}: {
  chats: Chat[];
  selectedChatId?: string | null;
  templates: Template[];
  loadingChats?: boolean;
  chatsError?: string;
  creatingChat?: boolean;
  deletingChatId?: string | null;
  busyChatId?: string | null;
  onRetryChats: () => void;
  onNew: () => void;
  onPickChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  onUseTemplate: (text: string) => void;
}) {
  const [confirmingChatId, setConfirmingChatId] = useState<string | null>(null);

  useEffect(() => {
    if (confirmingChatId && !chats.some((chat) => chat.id === confirmingChatId)) {
      setConfirmingChatId(null);
    }
  }, [chats, confirmingChatId]);

  return (
    <aside className="sidebar">
      <button className="new-btn" onClick={onNew} disabled={creatingChat}>
        <span>+</span>
        {creatingChat ? "Creating chat..." : "New chat"}
      </button>

      <section>
        <div className="sidebar-section-head">
          <div className="sb-section">Chats</div>
          {!!chats.length && <small>{chats.length}</small>}
        </div>

        <div className="sb-list">
          {loadingChats && <div className="sidebar-state">Loading chat list...</div>}

          {!loadingChats && Boolean(chatsError) && (
            <div className="sidebar-state sidebar-state--error">
              <p>{chatsError}</p>
              <button type="button" className="ghost-btn compact" onClick={onRetryChats}>
                Retry
              </button>
            </div>
          )}

          {!loadingChats && !chatsError && !chats.length && (
            <div className="sidebar-empty">
              <strong>No chats yet</strong>
              <span>Start a new chat to keep follow-up analytics in one thread.</span>
            </div>
          )}

          {!loadingChats &&
            !chatsError &&
            chats.map((chat) => {
              const confirming = confirmingChatId === chat.id;
              const deleting = deletingChatId === chat.id;
              const active = selectedChatId === chat.id;
              const busy = busyChatId === chat.id;
              return (
                <div key={chat.id} className={`sb-chat-row ${active ? "active" : ""}`}>
                  <button
                    type="button"
                    className="sb-item sb-chat-item"
                    aria-label={`Open chat ${chat.title}`}
                    disabled={deleting}
                    onClick={() => {
                      setConfirmingChatId(null);
                      onPickChat(chat.id);
                    }}
                  >
                    <span>{chat.title}</span>
                    <div className="sidebar-chat-meta">
                      <small>{chat.message_count} messages</small>
                      <small>{formatDate(chat.updated_at)}</small>
                    </div>
                    {busy && <em>{deleting ? "Deleting..." : "Loading..."}</em>}
                  </button>

                  {!confirming && (
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Delete chat ${chat.title}`}
                      disabled={deleting}
                      onClick={() => setConfirmingChatId(chat.id)}
                    >
                      Delete
                    </button>
                  )}

                  {confirming && (
                    <div className="sidebar-delete-confirm" role="alert">
                      <p>Delete this chat and its message history?</p>
                      <div className="sidebar-delete-actions">
                        <button
                          type="button"
                          className="ghost-btn compact"
                          onClick={() => setConfirmingChatId(null)}
                          disabled={deleting}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="run-btn small danger"
                          onClick={() => {
                            onDeleteChat(chat.id);
                            setConfirmingChatId(null);
                          }}
                          disabled={deleting}
                        >
                          {deleting ? "Deleting..." : "Confirm delete"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      </section>

      <section>
        <div className="sidebar-section-head">
          <div className="sb-section">Quick templates</div>
          {!!templates.length && <small>{Math.min(templates.length, 5)}</small>}
        </div>
        <div className="sb-list">
          {templates.slice(0, 5).map((template) => (
            <button
              key={template.id}
              type="button"
              className="sb-item"
              onClick={() => onUseTemplate(template.natural_text)}
            >
              <span>{template.title}</span>
            </button>
          ))}
          {!templates.length && <div className="sidebar-state">No reusable templates available.</div>}
        </div>
      </section>

      <div className="sb-footer">
        <div>
          <span className="dot ok" /> drivee analytics
        </div>
        <div>Mode: read-only</div>
        <div>Datasets: orders, cities, drivers, clients</div>
      </div>
    </aside>
  );
}

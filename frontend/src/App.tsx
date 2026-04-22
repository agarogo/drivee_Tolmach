import axios from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("tolmach_token");
  if (token) {
    config.headers = config.headers || {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

type User = {
  id: number;
  email: string;
  role: "user" | "admin";
};

type Chat = {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

type Message = {
  id: number;
  chat_id: number;
  role: "user" | "assistant";
  content: string;
  payload: any;
  created_at: string;
};

type Template = {
  id: number;
  title: string;
  content: string;
};

type Report = {
  id: number;
  title: string;
  question: string;
  sql_text: string;
  result: Record<string, any>[];
  chart_spec: any;
  schedule: any;
  created_at: string;
};

type LogRow = {
  id: number;
  created_at: string;
  user_email: string | null;
  question: string;
  generated_sql: string;
  status: string;
  duration_ms: number;
  prompt: string;
  raw_response: string;
  error: string;
};

function formatDate(value: string) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function DataTable({ rows }: { rows: Record<string, any>[] }) {
  if (!rows?.length) {
    return <div className="empty-state">Нет данных</div>;
  }

  const columns = Object.keys(rows[0]);
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{String(row[column] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartView({ rows, chartSpec }: { rows: Record<string, any>[]; chartSpec: any }) {
  if (!rows?.length || !chartSpec || chartSpec.type === "table_only") {
    return <div className="empty-state">Таблица подходит лучше графика</div>;
  }

  const x = chartSpec.x;
  const series = chartSpec.series || [];
  const colors = ["#20756b", "#c15c32", "#4f6fb2", "#8c5aa6"];

  return (
    <div className="chart-box">
      <ResponsiveContainer>
        {chartSpec.type === "line" ? (
          <LineChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d9dedb" />
            <XAxis dataKey={x} stroke="#5d6964" />
            <YAxis stroke="#5d6964" />
            <Tooltip />
            <Legend />
            {series.map((item: any, index: number) => (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.key}
                stroke={colors[index % colors.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={rows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d9dedb" />
            <XAxis dataKey={x} stroke="#5d6964" />
            <YAxis stroke="#5d6964" />
            <Tooltip />
            <Legend />
            {series.map((item: any, index: number) => (
              <Bar key={item.key} dataKey={item.key} fill={colors[index % colors.length]} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function AuthScreen({ onAuth }: { onAuth: (token: string, user: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("user@tolmach.local");
  const [password, setPassword] = useState("user123");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const url = mode === "login" ? "/auth/login" : "/auth/register";
      const payload = mode === "login" ? { email, password } : { email, password, role };
      const { data } = await api.post(url, payload);
      onAuth(data.access_token, data.user);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Не удалось войти");
    } finally {
      setLoading(false);
    }
  };

  const useDemo = (nextRole: "user" | "admin") => {
    setMode("login");
    setRole(nextRole);
    setEmail(nextRole === "admin" ? "admin@tolmach.local" : "user@tolmach.local");
    setPassword(nextRole === "admin" ? "admin123" : "user123");
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-title">Толмач</div>
        <div className="auth-subtitle">self-service AI-аналитика</div>
        <div className="segmented">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            Вход
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            Регистрация
          </button>
        </div>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {mode === "register" && (
          <label>
            Роль
            <select value={role} onChange={(event) => setRole(event.target.value as "user" | "admin")}>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </label>
        )}
        {error && <div className="auth-error">{error}</div>}
        <button className="primary-button" disabled={loading}>
          {loading ? "Проверяем..." : mode === "login" ? "Войти" : "Создать аккаунт"}
        </button>
        <div className="demo-buttons">
          <button type="button" onClick={() => useDemo("user")}>user demo</button>
          <button type="button" onClick={() => useDemo("admin")}>admin demo</button>
        </div>
      </form>
    </div>
  );
}

function Sidebar({
  user,
  chats,
  reports,
  templates,
  currentChatId,
  draft,
  view,
  onNewChat,
  onSelectChat,
  onTemplate,
  onSaveTemplate,
  onNavigate,
  onLogout,
}: {
  user: User;
  chats: Chat[];
  reports: Report[];
  templates: Template[];
  currentChatId: number | null;
  draft: string;
  view: "chat" | "admin";
  onNewChat: () => void;
  onSelectChat: (id: number) => void;
  onTemplate: (text: string) => void;
  onSaveTemplate: () => void;
  onNavigate: (view: "chat" | "admin") => void;
  onLogout: () => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand-row">
        <div>
          <div className="brand">Толмач</div>
          <div className="user-email">{user.email}</div>
        </div>
        <button className="icon-button" onClick={onLogout} title="Выйти">×</button>
      </div>

      <button className="new-chat" onClick={onNewChat}>Новый запрос</button>

      {user.role === "admin" && (
        <button className={view === "admin" ? "nav-link active" : "nav-link"} onClick={() => onNavigate("admin")}>
          Логи
        </button>
      )}

      <section className="nav-section">
        <h2>История</h2>
        <div className="nav-list">
          {chats.map((chat) => (
            <button
              key={chat.id}
              className={chat.id === currentChatId && view === "chat" ? "history-item active" : "history-item"}
              onClick={() => onSelectChat(chat.id)}
            >
              <span>{chat.title}</span>
              <b>{chat.message_count}</b>
            </button>
          ))}
          {!chats.length && <div className="muted-line">Пока пусто</div>}
        </div>
      </section>

      <section className="nav-section">
        <h2>Шаблоны</h2>
        <button className="template-item template-new" onClick={onSaveTemplate} disabled={!draft.trim()}>
          Новый шаблон
        </button>
        {templates.map((template) => (
          <button key={template.id} className="template-item" onClick={() => onTemplate(template.content)}>
            {template.title}
          </button>
        ))}
      </section>

      <section className="nav-section reports-section">
        <h2>Сохранённые отчёты</h2>
        {reports.slice(0, 6).map((report) => (
          <div className="report-link" key={report.id} title={report.title}>
            {report.title}
          </div>
        ))}
        {!reports.length && <div className="muted-line">Нет отчётов</div>}
      </section>
    </aside>
  );
}

function AssistantBubble({
  message,
  chatId,
  onSaved,
}: {
  message: Message;
  chatId: number | null;
  onSaved: () => void;
}) {
  const payload = message.payload || {};
  const rows = payload.rows || [];
  const sql = payload.sql || "";
  const queryClient = useQueryClient();
  const [scheduleEmail, setScheduleEmail] = useState("");
  const [savedReport, setSavedReport] = useState<Report | null>(null);

  const saveReport = useMutation({
    mutationFn: async () => {
      const title = payload.interpretation?.metric
        ? `${payload.interpretation.metric}: ${payload.interpretation.dimension || "итог"}`
        : "Отчёт Толмач";
      const { data } = await api.post("/api/reports", {
        chat_id: chatId,
        title,
        question: payload.question || "",
        sql_text: sql,
        result: rows,
        chart_spec: payload.chart_spec,
      });
      return data as Report;
    },
    onSuccess: (report) => {
      setSavedReport(report);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      onSaved();
    },
  });

  const scheduleReport = useMutation({
    mutationFn: async (frequency: "daily" | "weekly") => {
      if (!savedReport) return null;
      const { data } = await api.post(`/api/reports/${savedReport.id}/schedule`, {
        frequency,
        email: scheduleEmail || "analytics@example.com",
      });
      return data as Report;
    },
    onSuccess: (report) => {
      if (report) setSavedReport(report);
    },
  });

  return (
    <div className="message assistant">
      <div className="bubble">
        <p>{message.content}</p>
        {payload.confidence !== undefined && (
          <div className="confidence">confidence: {Number(payload.confidence).toFixed(2)}</div>
        )}
        {payload.guardrails?.length > 0 && (
          <div className="guardrails">
            {payload.guardrails.map((item: string) => (
              <div key={item}>{item}</div>
            ))}
          </div>
        )}
        {sql && (
          <pre className="sql-block">
            <code>{sql}</code>
          </pre>
        )}
        {rows.length > 0 && (
          <>
            <ChartView rows={rows} chartSpec={payload.chart_spec} />
            <DataTable rows={rows} />
            <div className="report-actions">
              <button onClick={() => saveReport.mutate()} disabled={saveReport.isPending}>
                Сохранить отчёт
              </button>
              {savedReport && (
                <>
                  <input
                    value={scheduleEmail}
                    onChange={(event) => setScheduleEmail(event.target.value)}
                    placeholder="email для рассылки"
                  />
                  <button onClick={() => scheduleReport.mutate("weekly")} disabled={scheduleReport.isPending}>
                    Настроить рассылку
                  </button>
                </>
              )}
            </div>
            {savedReport?.schedule?.last_demo_log && <div className="success-line">{savedReport.schedule.last_demo_log}</div>}
          </>
        )}
      </div>
    </div>
  );
}

function MessageList({
  messages,
  hasMore,
  loadingMore,
  chatId,
  onLoadMore,
  onSavedReport,
}: {
  messages: Message[];
  hasMore: boolean;
  loadingMore: boolean;
  chatId: number | null;
  onLoadMore: () => void;
  onSavedReport: () => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [chatId]);

  const onScroll = () => {
    const node = ref.current;
    if (!node || loadingMore || !hasMore) return;
    if (node.scrollTop < 32) {
      onLoadMore();
    }
  };

  return (
    <div className="message-list" ref={ref} onScroll={onScroll}>
      {hasMore && <div className="load-more">{loadingMore ? "Загружаем..." : "Прокрутите выше"}</div>}
      {messages.map((message) =>
        message.role === "user" ? (
          <div className="message user" key={message.id}>
            <div className="bubble">{message.content}</div>
          </div>
        ) : (
          <AssistantBubble key={message.id} message={message} chatId={chatId} onSaved={onSavedReport} />
        ),
      )}
      {!messages.length && (
        <div className="empty-chat">
          <div>ЗАДАЙТЕ ВОПРОС НА РУССКОМ</div>
          <span>покажи выручку по топ-10 городам за последние 30 дней</span>
        </div>
      )}
    </div>
  );
}

function InputArea({
  value,
  loading,
  disabled,
  onChange,
  onSend,
}: {
  value: string;
  loading: boolean;
  disabled: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
}) {
  const submit = () => {
    if (!value.trim() || loading || disabled) return;
    onSend();
  };

  return (
    <div className="input-area">
      <label>ЗАДАЙТЕ ВОПРОС НА РУССКОМ</label>
      <div className="composer">
        <textarea
          value={value}
          placeholder="покажи выручку по топ-10 городам за последние 30 дней"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <button onClick={submit} disabled={!value.trim() || loading || disabled} title="Отправить">
          {loading ? "..." : "↑"}
        </button>
      </div>
    </div>
  );
}

function AdminLogs({ user }: { user: User }) {
  const [filters, setFilters] = useState({ user_email: "", date_from: "", date_to: "" });
  const [selected, setSelected] = useState<LogRow | null>(null);
  const { data = [], isLoading } = useQuery({
    queryKey: ["admin-logs", filters],
    queryFn: async () => {
      const { data } = await api.get("/admin/logs", {
        params: {
          user_email: filters.user_email || undefined,
          date_from: filters.date_from || undefined,
          date_to: filters.date_to || undefined,
        },
      });
      return data as LogRow[];
    },
    enabled: user.role === "admin",
  });

  if (user.role !== "admin") {
    return <main className="admin-page"><div className="empty-state">Доступ закрыт</div></main>;
  }

  return (
    <main className="admin-page">
      <div className="admin-header">
        <div>
          <h1>Логи запросов</h1>
          <p>вопрос, SQL, статус, время, промпт, ошибки</p>
        </div>
        <div className="filters">
          <input
            value={filters.user_email}
            placeholder="пользователь"
            onChange={(event) => setFilters({ ...filters, user_email: event.target.value })}
          />
          <input
            type="date"
            value={filters.date_from}
            onChange={(event) => setFilters({ ...filters, date_from: event.target.value })}
          />
          <input
            type="date"
            value={filters.date_to}
            onChange={(event) => setFilters({ ...filters, date_to: event.target.value })}
          />
        </div>
      </div>
      <div className="logs-table-wrap">
        <table className="logs-table">
          <thead>
            <tr>
              <th>Время</th>
              <th>Пользователь</th>
              <th>Вопрос</th>
              <th>SQL</th>
              <th>Статус</th>
              <th>ms</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.id} onClick={() => setSelected(row)}>
                <td>{formatDate(row.created_at)}</td>
                <td>{row.user_email}</td>
                <td>{row.question}</td>
                <td><code>{row.generated_sql}</code></td>
                <td><span className={`status ${row.status}`}>{row.status}</span></td>
                <td>{row.duration_ms}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <div className="empty-state">Загрузка...</div>}
      </div>
      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={() => setSelected(null)}>×</button>
            <h2>Детали запроса</h2>
            <h3>Промпт</h3>
            <pre>{selected.prompt || "нет данных"}</pre>
            <h3>Raw-ответ модели</h3>
            <pre>{selected.raw_response || "нет данных"}</pre>
            {selected.error && (
              <>
                <h3>Ошибка</h3>
                <pre>{selected.error}</pre>
              </>
            )}
          </div>
        </div>
      )}
    </main>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const [token, setToken] = useState(() => localStorage.getItem("tolmach_token") || "");
  const [user, setUser] = useState<User | null>(() => {
    const saved = localStorage.getItem("tolmach_user");
    return saved ? JSON.parse(saved) : null;
  });
  const [view, setView] = useState<"chat" | "admin">(
    window.location.pathname === "/admin/logs" ? "admin" : "chat",
  );
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);
  const [draft, setDraft] = useState("покажи выручку по топ-10 городам за последние 30 дней");
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageOffset, setMessageOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [toast, setToast] = useState("");

  const authenticated = Boolean(token && user);

  const chatsQuery = useQuery({
    queryKey: ["chats"],
    queryFn: async () => {
      const { data } = await api.get("/api/chats");
      return data as Chat[];
    },
    enabled: authenticated,
  });

  const templatesQuery = useQuery({
    queryKey: ["templates"],
    queryFn: async () => {
      const { data } = await api.get("/api/templates");
      return data as Template[];
    },
    enabled: authenticated,
  });

  const reportsQuery = useQuery({
    queryKey: ["reports"],
    queryFn: async () => {
      const { data } = await api.get("/api/reports");
      return data as Report[];
    },
    enabled: authenticated,
  });

  const createChat = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/api/chats");
      return data as Chat;
    },
    onSuccess: (chat) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      setCurrentChatId(chat.id);
      setMessages([]);
      setMessageOffset(0);
      setHasMore(false);
      navigate("chat");
    },
  });

  const messagesQuery = useQuery({
    queryKey: ["messages", currentChatId],
    queryFn: async () => {
      const { data } = await api.get(`/api/chats/${currentChatId}/messages`, {
        params: { limit: 50, offset: 0 },
      });
      return data as { items: Message[]; has_more: boolean; next_offset: number };
    },
    enabled: authenticated && Boolean(currentChatId) && view === "chat",
  });

  const sendMessage = useMutation({
    mutationFn: async () => {
      const { data } = await api.post(`/api/chats/${currentChatId}/messages`, { question: draft });
      return data as { chat: Chat; user_message: Message; assistant_message: Message };
    },
    onSuccess: (data) => {
      setMessages((items) => [...items, data.user_message, data.assistant_message]);
      setMessageOffset((offset) => offset + 2);
      setDraft("");
      queryClient.invalidateQueries({ queryKey: ["chats"] });
    },
    onError: (error: any) => {
      setToast(error?.response?.data?.detail || "Не удалось отправить вопрос");
    },
  });

  const saveTemplate = useMutation({
    mutationFn: async () => {
      const title = draft.trim().slice(0, 30) || "Новый шаблон";
      const { data } = await api.post("/api/templates", { title, content: draft.trim() });
      return data as Template;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      setToast("Шаблон сохранён");
    },
  });

  useEffect(() => {
    if (!messagesQuery.data) return;
    setMessages(messagesQuery.data.items);
    setMessageOffset(messagesQuery.data.next_offset);
    setHasMore(messagesQuery.data.has_more);
  }, [messagesQuery.data]);

  useEffect(() => {
    if (!authenticated || currentChatId || chatsQuery.isLoading) return;
    const chats = chatsQuery.data || [];
    if (chats.length) {
      setCurrentChatId(chats[0].id);
    } else {
      createChat.mutate();
    }
  }, [authenticated, chatsQuery.data, chatsQuery.isLoading, currentChatId]);

  useEffect(() => {
    const onPop = () => setView(window.location.pathname === "/admin/logs" ? "admin" : "chat");
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const chats = useMemo(() => chatsQuery.data || [], [chatsQuery.data]);

  function onAuth(nextToken: string, nextUser: User) {
    localStorage.setItem("tolmach_token", nextToken);
    localStorage.setItem("tolmach_user", JSON.stringify(nextUser));
    setToken(nextToken);
    setUser(nextUser);
    setView("chat");
  }

  function logout() {
    localStorage.removeItem("tolmach_token");
    localStorage.removeItem("tolmach_user");
    setToken("");
    setUser(null);
    setCurrentChatId(null);
    setMessages([]);
    queryClient.clear();
  }

  function navigate(nextView: "chat" | "admin") {
    setView(nextView);
    window.history.pushState(null, "", nextView === "admin" ? "/admin/logs" : "/");
  }

  async function loadMoreMessages() {
    if (!currentChatId || loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const { data } = await api.get(`/api/chats/${currentChatId}/messages`, {
        params: { limit: 50, offset: messageOffset },
      });
      setMessages((items) => [...data.items, ...items]);
      setMessageOffset(data.next_offset);
      setHasMore(data.has_more);
    } finally {
      setLoadingMore(false);
    }
  }

  if (!authenticated || !user) {
    return <AuthScreen onAuth={onAuth} />;
  }

  return (
    <div className="app-shell">
      <Sidebar
        user={user}
        chats={chats}
        reports={reportsQuery.data || []}
        templates={templatesQuery.data || []}
        currentChatId={currentChatId}
        draft={draft}
        view={view}
        onNewChat={() => createChat.mutate()}
        onSelectChat={(id) => {
          setCurrentChatId(id);
          navigate("chat");
        }}
        onTemplate={(text) => {
          setDraft(text);
          navigate("chat");
        }}
        onSaveTemplate={() => saveTemplate.mutate()}
        onNavigate={navigate}
        onLogout={logout}
      />
      {view === "admin" ? (
        <AdminLogs user={user} />
      ) : (
        <main className="chat-area">
          <header className="chat-header">
            <h1>Отправь шаблоны</h1>
            <div className="chat-meta">
              {currentChatId ? `чат #${currentChatId}` : "чат не выбран"}
            </div>
          </header>
          <MessageList
            messages={messages}
            hasMore={hasMore}
            loadingMore={loadingMore}
            chatId={currentChatId}
            onLoadMore={loadMoreMessages}
            onSavedReport={() => setToast("Отчёт сохранён")}
          />
          <InputArea
            value={draft}
            loading={sendMessage.isPending}
            disabled={!currentChatId}
            onChange={setDraft}
            onSend={() => sendMessage.mutate()}
          />
        </main>
      )}
      {toast && (
        <div className="toast" onAnimationEnd={() => setToast("")}>
          {toast}
        </div>
      )}
    </div>
  );
}

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useAnalyticsFlow } from "../features/analytics/api/useAnalyticsFlow";
import { AnalyticsPage } from "../features/analytics/AnalyticsPage";
import { AuthPage } from "../features/auth/AuthPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { ReportsPage } from "../features/reports/ReportsPage";
import { SchedulesPage } from "../features/schedules/SchedulesPage";
import { TemplatesPage } from "../features/templates/TemplatesPage";
import { fetchMe, logout as logoutRequest } from "../shared/api/auth";
import { fetchChats } from "../shared/api/chats";
import { fetchReport, fetchReports, runReport } from "../shared/api/reports";
import { fetchSchedules, toggleSchedule } from "../shared/api/schedules";
import { fetchTemplates } from "../shared/api/templates";
import type { AppView, AuthResponse, User } from "../shared/types";
import { Sidebar } from "../shared/ui/Sidebar";
import { TopNav } from "../shared/ui/TopNav";

const DEFAULT_ANALYTICS_DRAFT = "Покажи выручку по 10 главным городам за последние 30 дней";

export default function App() {
  const queryClient = useQueryClient();
  const [authStatus, setAuthStatus] = useState<"checking" | "guest" | "authenticated">("checking");
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<AppView>("analytics");
  const [selectedReportId, setSelectedReportId] = useState("");
  const [selectedScheduleId, setSelectedScheduleId] = useState("");
  const [toast, setToast] = useState("");
  const analytics = useAnalyticsFlow({
    initialDraft: DEFAULT_ANALYTICS_DRAFT,
    onToast: setToast,
    onReportSaved: setSelectedReportId,
  });
  const {
    currentChatId,
    openChat,
    createChat: createChatSession,
    deleteChat: deleteChatSession,
    hydrateSelection,
  } = analytics;

  const authenticated = authStatus === "authenticated" && Boolean(user);

  useEffect(() => {
    fetchMe()
      .then((nextUser) => {
        setUser(nextUser);
        setAuthStatus("authenticated");
      })
      .catch(() => {
        setUser(null);
        setAuthStatus("guest");
      });
  }, []);

  const templatesQuery = useQuery({ queryKey: ["templates"], queryFn: fetchTemplates, enabled: authenticated });
  const chatsQuery = useQuery({ queryKey: ["chats"], queryFn: fetchChats, enabled: authenticated });
  const reportsQuery = useQuery({ queryKey: ["reports"], queryFn: fetchReports, enabled: authenticated });
  const selectedReportQuery = useQuery({
    queryKey: ["report", selectedReportId],
    queryFn: () => fetchReport(selectedReportId),
    enabled: authenticated && Boolean(selectedReportId),
  });
  const schedulesQuery = useQuery({ queryKey: ["schedules"], queryFn: fetchSchedules, enabled: authenticated });

  const templates = templatesQuery.data || [];
  const chats = chatsQuery.data || [];
  const reports = reportsQuery.data || [];
  const schedules = schedulesQuery.data || [];

  useEffect(() => {
    if (!authenticated) return;
    if (chatsQuery.isLoading || chatsQuery.isError) return;
    void hydrateSelection(chats);
  }, [authenticated, chats, chatsQuery.isError, chatsQuery.isLoading, hydrateSelection]);

  useEffect(() => {
    if (!selectedReportId && reports[0]?.id) setSelectedReportId(reports[0].id);
  }, [reports, selectedReportId]);

  useEffect(() => {
    if (!selectedScheduleId && schedules[0]?.id) setSelectedScheduleId(schedules[0].id);
  }, [schedules, selectedScheduleId]);

  const currentReport =
    selectedReportQuery.data || reports.find((report) => report.id === selectedReportId) || reports[0] || null;
  const currentScheduleId = selectedScheduleId || schedules[0]?.id;

  function onAuth(auth: AuthResponse) {
    setUser(auth.user);
    setAuthStatus("authenticated");
  }

  async function logout() {
    try {
      await logoutRequest();
    } catch {
      // Clear local state even if the backend session is already gone.
    } finally {
      setUser(null);
      setAuthStatus("guest");
      setView("analytics");
      analytics.resetAnalytics();
      setSelectedReportId("");
      setSelectedScheduleId("");
      queryClient.clear();
    }
  }

  async function handleRunReport(id: string) {
    const report = await runReport(id);
    setToast("Report refreshed");
    await queryClient.invalidateQueries({ queryKey: ["reports"] });
    await queryClient.invalidateQueries({ queryKey: ["report", report.id] });
    await queryClient.invalidateQueries({ queryKey: ["schedules"] });
  }

  async function handleToggleSchedule(id: string) {
    await toggleSchedule(id);
    await queryClient.invalidateQueries({ queryKey: ["schedules"] });
  }

  let page;
  if (view === "templates") {
    page = (
      <TemplatesPage
        templates={templates}
        onUse={(text) => {
          analytics.reuseQuestion(text);
          setView("analytics");
        }}
      />
    );
  } else if (view === "reports") {
    page = (
      <ReportsPage
        reports={reports}
        currentReport={currentReport}
        onSelect={setSelectedReportId}
        onRun={handleRunReport}
      />
    );
  } else if (view === "schedules") {
    page = (
      <SchedulesPage
        schedules={schedules}
        selectedId={currentScheduleId}
        onSelect={setSelectedScheduleId}
        onToggle={handleToggleSchedule}
      />
    );
  } else if (view === "profile" && user) {
    page = <ProfilePage user={user} onLogout={logout} />;
  } else {
    page = (
      <AnalyticsPage
        draft={analytics.draft}
        running={analytics.running}
        pendingQuestion={analytics.pendingQuestion}
        currentQuery={analytics.currentQuery}
        currentChatId={currentChatId}
        messages={analytics.messages}
        templates={templates}
        saving={analytics.saving}
        loadingChat={analytics.loadingChat}
        chatError={analytics.chatError}
        restoringChatSelection={authenticated && chatsQuery.isLoading && !analytics.selectionHydrated}
        onDraftChange={analytics.setDraft}
        onRun={analytics.submitQuery}
        onSave={(title, schedule, recipients) => analytics.saveReport({ title, schedule, recipients })}
        onClarify={analytics.clarify}
        onReuseQuestion={analytics.reuseQuestion}
        onRetryQuestion={analytics.retryQuestion}
        onCancelPending={analytics.cancelPendingRequest}
        onCreateChat={() => createChatSession()}
        onRetryCurrentChat={() => analytics.reloadCurrentChat()}
      />
    );
  }

  if (authStatus === "checking") {
    return (
        <div className="auth-page">
        <div className="auth-card checking-card">Проверяем сессию...</div>
      </div>
    );
  }

  if (!authenticated || !user) return <AuthPage onAuth={onAuth} />;

  return (
    <div className="app-shell">
      <TopNav view={view} user={user} onView={setView} onLogout={logout} />
      <div className="app-body">
        <Sidebar
          chats={chats}
          selectedChatId={currentChatId}
          templates={templates}
          loadingChats={chatsQuery.isLoading}
          chatsError={chatsQuery.isError ? "Could not load chats." : ""}
          creatingChat={analytics.creatingChat}
          deletingChatId={analytics.deletingChatId}
          busyChatId={analytics.busyChatId}
          onRetryChats={() => {
            void chatsQuery.refetch();
          }}
          onNew={() => {
            createChatSession();
            setView("analytics");
          }}
          onPickChat={(chatId) => {
            void openChat(chatId);
            setView("analytics");
          }}
          onDeleteChat={(chatId) => deleteChatSession(chatId)}
          onUseTemplate={(text) => {
            analytics.reuseQuestion(text);
            setView("analytics");
          }}
        />
        <div className="page-host">{page}</div>
      </div>
      {toast && (
        <div className="toast" onAnimationEnd={() => setToast("")}>
          {toast}
        </div>
      )}
    </div>
  );
}

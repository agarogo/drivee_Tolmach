import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { AnalyticsPage } from "../features/analytics/AnalyticsPage";
import { AuthPage } from "../features/auth/AuthPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { ReportsPage } from "../features/reports/ReportsPage";
import { SchedulesPage } from "../features/schedules/SchedulesPage";
import { TemplatesPage } from "../features/templates/TemplatesPage";
import { fetchMe } from "../shared/api/auth";
import { clearToken, getStoredToken, storeToken } from "../shared/api/client";
import { clarifyQuery, fetchHistory, runQuery } from "../shared/api/queries";
import { createReport, fetchReport, fetchReports, runReport } from "../shared/api/reports";
import { fetchSchedules, toggleSchedule } from "../shared/api/schedules";
import { fetchTemplates } from "../shared/api/templates";
import type { AppView, AuthResponse, QueryResult, User } from "../shared/types";
import { Sidebar } from "../shared/ui/Sidebar";
import { TopNav } from "../shared/ui/TopNav";

export default function App() {
  const queryClient = useQueryClient();
  const [authStatus, setAuthStatus] = useState<"checking" | "guest" | "authenticated">("checking");
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<AppView>("analytics");
  const [draft, setDraft] = useState("покажи выручку по топ-10 городам за последние 30 дней");
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [currentQuery, setCurrentQuery] = useState<QueryResult | null>(null);
  const [selectedReportId, setSelectedReportId] = useState("");
  const [selectedScheduleId, setSelectedScheduleId] = useState("");
  const [toast, setToast] = useState("");

  const authenticated = authStatus === "authenticated" && Boolean(user);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setAuthStatus("guest");
      return;
    }
    fetchMe()
      .then((nextUser) => {
        setUser(nextUser);
        setAuthStatus("authenticated");
      })
      .catch(() => {
        clearToken();
        setUser(null);
        setAuthStatus("guest");
      });
  }, []);

  const templatesQuery = useQuery({ queryKey: ["templates"], queryFn: fetchTemplates, enabled: authenticated });
  const historyQuery = useQuery({ queryKey: ["history"], queryFn: fetchHistory, enabled: authenticated });
  const reportsQuery = useQuery({ queryKey: ["reports"], queryFn: fetchReports, enabled: authenticated });
  const selectedReportQuery = useQuery({
    queryKey: ["report", selectedReportId],
    queryFn: () => fetchReport(selectedReportId),
    enabled: authenticated && Boolean(selectedReportId),
  });
  const schedulesQuery = useQuery({ queryKey: ["schedules"], queryFn: fetchSchedules, enabled: authenticated });

  const templates = templatesQuery.data || [];
  const history = historyQuery.data || [];
  const reports = reportsQuery.data || [];
  const schedules = schedulesQuery.data || [];

  useEffect(() => {
    if (!selectedReportId && reports[0]?.id) setSelectedReportId(reports[0].id);
  }, [reports, selectedReportId]);

  useEffect(() => {
    if (!selectedScheduleId && schedules[0]?.id) setSelectedScheduleId(schedules[0].id);
  }, [schedules, selectedScheduleId]);

  const runMutation = useMutation({
    mutationFn: (question: string) => runQuery(question),
    onSuccess: (query) => {
      setCurrentQuery(query);
      setPendingQuestion("");
      queryClient.invalidateQueries({ queryKey: ["history"] });
      if (query.status === "success") setToast("Запрос выполнен");
      if (query.status === "clarification_required") setToast("Нужно уточнение");
      if (query.status === "blocked") setToast("Запрос заблокирован");
    },
    onError: (err: any) => {
      setPendingQuestion("");
      setToast(err?.response?.data?.detail || "Не удалось выполнить запрос");
    },
  });

  const clarifyMutation = useMutation({
    mutationFn: ({ value, freeform }: { value: string; freeform?: string }) => clarifyQuery(currentQuery!.id, value, freeform),
    onSuccess: (query) => {
      setCurrentQuery(query);
      queryClient.invalidateQueries({ queryKey: ["history"] });
    },
  });

  const saveReportMutation = useMutation({
    mutationFn: ({ title, schedule, recipients }: { title: string; schedule: Record<string, any> | null; recipients: string[] }) => {
      if (!currentQuery) throw new Error("Нет запроса для сохранения");
      return createReport({
        query_id: currentQuery.id,
        title,
        recipients,
        schedule,
      });
    },
    onSuccess: (report) => {
      setToast("Отчёт сохранён");
      setSelectedReportId(report.id);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
  });

  const runReportMutation = useMutation({
    mutationFn: runReport,
    onSuccess: (report) => {
      setToast("Отчёт обновлён");
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.invalidateQueries({ queryKey: ["report", report.id] });
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
  });

  const toggleScheduleMutation = useMutation({
    mutationFn: toggleSchedule,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["schedules"] }),
  });

  const currentReport = selectedReportQuery.data || reports.find((report) => report.id === selectedReportId) || reports[0] || null;
  const currentScheduleId = selectedScheduleId || schedules[0]?.id;

  function onAuth(auth: AuthResponse) {
    storeToken(auth.access_token);
    setUser(auth.user);
    setAuthStatus("authenticated");
  }

  function logout() {
    clearToken();
    setUser(null);
    setAuthStatus("guest");
    setView("analytics");
    setCurrentQuery(null);
    setPendingQuestion("");
    queryClient.clear();
  }

  function submitQuery() {
    const question = draft.trim();
    if (!question || runMutation.isPending) return;
    setPendingQuestion(question);
    setCurrentQuery(null);
    setDraft("");
    runMutation.mutate(question);
  }

  const page = useMemo(() => {
    if (view === "templates") {
      return <TemplatesPage templates={templates} onUse={(text) => { setDraft(text); setView("analytics"); }} />;
    }
    if (view === "reports") {
      return (
        <ReportsPage
          reports={reports}
          currentReport={currentReport}
          onSelect={setSelectedReportId}
          onRun={(id) => runReportMutation.mutate(id)}
        />
      );
    }
    if (view === "schedules") {
      return (
        <SchedulesPage
          schedules={schedules}
          selectedId={currentScheduleId}
          onSelect={setSelectedScheduleId}
          onToggle={(id) => toggleScheduleMutation.mutate(id)}
        />
      );
    }
    if (view === "profile" && user) {
      return <ProfilePage user={user} onLogout={logout} />;
    }
    return (
      <AnalyticsPage
        draft={draft}
        running={runMutation.isPending || clarifyMutation.isPending}
        pendingQuestion={pendingQuestion}
        currentQuery={currentQuery}
        templates={templates}
        saving={saveReportMutation.isPending}
        onDraftChange={setDraft}
        onRun={submitQuery}
        onSave={(title, schedule, recipients) => saveReportMutation.mutate({ title, schedule, recipients })}
        onClarify={(value, freeform) => clarifyMutation.mutate({ value, freeform })}
        onUseSafe={(text) => setDraft(text)}
      />
    );
  }, [
    view,
    templates,
    reports,
    currentReport,
    schedules,
    currentScheduleId,
    user,
    draft,
    pendingQuestion,
    currentQuery,
    runMutation.isPending,
    clarifyMutation.isPending,
    saveReportMutation.isPending,
  ]);

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
          history={history}
          templates={templates}
          onNew={() => { setCurrentQuery(null); setPendingQuestion(""); setDraft(""); setView("analytics"); }}
          onPickQuery={(query) => { setCurrentQuery(query); setPendingQuestion(""); setView("analytics"); }}
          onUseTemplate={(text) => { setDraft(text); setView("analytics"); }}
        />
        <div className="page-host">{page}</div>
      </div>
      {toast && <div className="toast" onAnimationEnd={() => setToast("")}>{toast}</div>}
    </div>
  );
}

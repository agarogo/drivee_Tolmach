import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { login, register } from "../../shared/api/auth";
import type { AuthResponse } from "../../shared/types";
import { Logo } from "../../shared/ui/Logo";

export function AuthPage({ onAuth }: { onAuth: (auth: AuthResponse) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("user@tolmach.local");
  const [password, setPassword] = useState("user123");
  const [fullName, setFullName] = useState("Пользователь Толмача");
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: () => (mode === "login" ? login(email, password) : register({ email, password, full_name: fullName, role: "user" })),
    onSuccess: (auth) => onAuth(auth),
    onError: (err: any) => setError(err?.response?.data?.detail || "Не удалось авторизоваться"),
  });

  return (
    <div className="auth-page">
      <form
        className="auth-card"
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          mutation.mutate();
        }}
      >
        <Logo />
        <p>Self-service аналитика на естественном языке. Главные экраны доступны только после входа или регистрации.</p>
        <div className="auth-tabs">
          <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
            Вход
          </button>
          <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
            Регистрация
          </button>
        </div>
        {mode === "register" && (
          <label>
            Имя
            <input value={fullName} onChange={(event) => setFullName(event.target.value)} />
          </label>
        )}
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error && <div className="auth-error">{error}</div>}
        <button className="run-btn" disabled={mutation.isPending}>
          {mutation.isPending ? "Проверяем" : mode === "login" ? "Войти" : "Создать аккаунт"}
        </button>
        <div className="demo-row">
          <button type="button" className="ghost-btn" onClick={() => { setMode("login"); setEmail("user@tolmach.local"); setPassword("user123"); }}>
            user demo
          </button>
          <button type="button" className="ghost-btn" onClick={() => { setMode("login"); setEmail("admin@tolmach.local"); setPassword("admin123"); }}>
            admin demo
          </button>
        </div>
      </form>
    </div>
  );
}

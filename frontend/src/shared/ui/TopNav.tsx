import { Logo } from "./Logo";
import { initials } from "../utils/format";
import type { AppView, User } from "../types";

const navItems: Array<[AppView, string]> = [
  ["analytics", "Аналитика"],
  ["reports", "Отчёты"],
  ["templates", "Шаблоны"],
  ["schedules", "Расписание"],
];

export function TopNav({
  view,
  user,
  onView,
  onLogout,
}: {
  view: AppView;
  user: User;
  onView: (view: AppView) => void;
  onLogout: () => void;
}) {
  return (
    <header className="topbar">
      <button className="logo-button" onClick={() => onView("analytics")} aria-label="На главный экран">
        <Logo />
      </button>
      <nav className="topbar-nav">
        {navItems.map(([key, label]) => (
          <button key={key} className={view === key ? "nav-btn active" : "nav-btn"} onClick={() => onView(key)}>
            {label}
          </button>
        ))}
      </nav>
      <button className={view === "profile" ? "avatar-chip active" : "avatar-chip"} onClick={() => onView("profile")} title="Профиль">
        <span className="avatar">{initials(user.full_name || user.email)}</span>
        <span>{user.full_name || user.email}</span>
      </button>
      <button className="ghost-btn compact" onClick={onLogout}>
        Выйти
      </button>
    </header>
  );
}

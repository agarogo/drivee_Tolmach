import type { User } from "../../shared/types";
import { initials } from "../../shared/utils/format";

export function ProfilePage({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <div className="profile-page">
      <section className="profile-card">
        <div className="profile-avatar">{initials(user.full_name || user.email)}</div>
        <div>
          <h1>{user.full_name || "Пользователь Толмача"}</h1>
          <p>{user.email}</p>
        </div>
        <span className="status-pill ok">{user.role}</span>
      </section>
      <section className="profile-grid">
        <div className="panel">
          <span>Активная БД</span>
          <strong>drivee_prod</strong>
          <p>Только аналитический read-only доступ к датасету Drivee.</p>
        </div>
        <div className="panel">
          <span>Dataset</span>
          <strong>orders, cities, drivers, clients</strong>
          <p>Служебные таблицы Толмача хранятся отдельно в схеме tolmach.</p>
        </div>
        <div className="panel">
          <span>Режим</span>
          <strong>READ-ONLY</strong>
          <p>Write/DDL операции блокируются guardrails до выполнения SQL.</p>
        </div>
      </section>
      <button className="ghost-btn danger-text" onClick={onLogout}>
        Выйти из аккаунта
      </button>
    </div>
  );
}

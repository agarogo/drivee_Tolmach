export function formatDate(value?: string | null) {
  if (!value) return "не задано";
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function initials(nameOrEmail: string) {
  const parts = nameOrEmail
    .replace(/@.*/, "")
    .split(/[.\s_-]+/)
    .filter(Boolean);
  return (parts[0]?.[0] || "T").toUpperCase() + (parts[1]?.[0] || "").toUpperCase();
}

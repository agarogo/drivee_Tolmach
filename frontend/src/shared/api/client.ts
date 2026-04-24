import axios, { AxiosHeaders } from "axios";

const CSRF_COOKIE_NAME = import.meta.env.VITE_CSRF_COOKIE_NAME || "tolmach_csrf";
const CSRF_HEADER_NAME = import.meta.env.VITE_CSRF_HEADER_NAME || "X-CSRF-Token";
const SAFE_METHODS = new Set(["get", "head", "options"]);

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  withCredentials: true,
});

function readCookie(name: string) {
  if (typeof document === "undefined") return "";
  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
}

api.interceptors.request.use((config) => {
  const method = (config.method || "get").toLowerCase();
  if (!SAFE_METHODS.has(method)) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    const headers = AxiosHeaders.from(config.headers);
    if (csrfToken) {
      headers.set(CSRF_HEADER_NAME, csrfToken);
    }
    config.headers = headers;
  }
  return config;
});

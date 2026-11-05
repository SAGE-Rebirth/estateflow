export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// Sessions live in httpOnly cookies set by the API; page scripts never see a token.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let refreshing: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) {
    const loc = (detail[0].loc ?? []).slice(1).join(".");
    return loc ? `${loc}: ${detail[0].msg}` : detail[0].msg;
  }
  if (status === 429) return "Too many attempts. Please wait a few minutes and try again.";
  return `Request failed (${status})`;
}

const PUBLIC_PATHS = ["/login", "/signup", "/s/"];

export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown; auth?: boolean } = {},
): Promise<T> {
  const { json, auth = true, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (json !== undefined) headers.set("Content-Type", "application/json");
  const send = () =>
    fetch(`${API_URL}${path}`, {
      ...rest,
      headers,
      credentials: "include",
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  let res = await send();
  if (res.status === 401 && auth && (await refreshSession())) res = await send();
  if (res.status === 401 && auth && typeof window !== "undefined") {
    if (!PUBLIC_PATHS.some((p) => location.pathname.startsWith(p))) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
    }
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, res.status));
  return body as T;
}

export function signOut(everywhere = false) {
  return api<void>(everywhere ? "/auth/logout-all" : "/auth/logout", { method: "POST" });
}

export function mediaUrl(conversationId: string, messageId: string) {
  return `${API_URL}/conversations/${conversationId}/messages/${messageId}/media`;
}

export function qs(params: Record<string, string | number | boolean | null | undefined>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

// Client API. Étoffé au fil des lots.

export type Role = "analyste" | "admin";

export interface Health {
  status: string;
  app: string;
  version: string;
  env?: string;
  components?: Record<string, boolean>;
}

export interface Me {
  id: number;
  username: string;
  role: Role;
}

export interface User {
  id: number;
  username: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const getHealth = () => request<Health>("/api/health");

// --- Auth ---
export const login = (username: string, password: string) =>
  request<Me>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
export const logout = () => request<{ status: string }>("/api/auth/logout", { method: "POST" });
export const getMe = () => request<Me>("/api/auth/me");

// --- Users (admin) ---
export const listUsers = () => request<User[]>("/api/users");
export const createUser = (username: string, password: string, role: Role) =>
  request<User>("/api/users", { method: "POST", body: JSON.stringify({ username, password, role }) });
export const updateUser = (id: number, patch: Partial<{ role: Role; is_active: boolean; password: string }>) =>
  request<User>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
export const deactivateUser = (id: number) => request<User>(`/api/users/${id}`, { method: "DELETE" });

export { ApiError };

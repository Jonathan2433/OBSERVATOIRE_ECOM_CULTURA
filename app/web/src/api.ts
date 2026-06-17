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

// --- Lots (batches) ---
export interface Batch {
  id: number;
  label: string;
  status: string; // pending | running | done | failed | canceled
  created_by?: number | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  model_label?: string | null;
  seuil_revue: number;
  n_total: number;
  n_processed: number;
  n_review: number;
  n_errors: number;
  duration_s?: number | null;
  error_message?: string | null;
}

export interface BatchProgress {
  id: number;
  status: string;
  n_total: number;
  n_processed: number;
  progress: number;
}

export const listBatches = () => request<Batch[]>("/api/batches");
export const getBatch = (id: number) => request<Batch>(`/api/batches/${id}`);
export const getBatchProgress = (id: number) => request<BatchProgress>(`/api/batches/${id}/progress`);

export async function createBatch(opts: {
  label?: string;
  seuilRevue: number;
  mdtc?: File | null;
  mopinion?: File | null;
}): Promise<Batch> {
  const form = new FormData();
  if (opts.label) form.append("label", opts.label);
  form.append("seuil_revue", String(opts.seuilRevue));
  if (opts.mdtc) form.append("mdtc", opts.mdtc);
  if (opts.mopinion) form.append("mopinion", opts.mopinion);
  // Pas de Content-Type manuel : le navigateur pose le boundary multipart.
  const res = await fetch("/api/batches", { method: "POST", credentials: "include", body: form });
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const b = await res.json();
      if (b?.detail) detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

// --- Modèles ---
export interface ModelVersion {
  id: number;
  kind: string; // stub | real
  label: string;
  is_active: boolean;
  available: boolean;
  metrics?: Record<string, unknown> | null;
  registered_at?: string | null;
}
export const listModels = () => request<ModelVersion[]>("/api/models");
export const activateModel = (id: number) => request<ModelVersion>(`/api/models/${id}/activate`, { method: "POST" });
export const rescanModels = () => request<{ status: string }>("/api/models/rescan", { method: "POST" });

export { ApiError };
